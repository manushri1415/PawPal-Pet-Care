"""Checks on the AWS infrastructure definitions and the Lambda package staging.

These do not deploy anything. They pin down the parts of infra/template.yaml
that the application's own behaviour depends on -- which paths reach the API,
what is cached, what the Lambda is configured with -- and run the CloudFront
Function's real JavaScript against the routes the SPA has.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INFRA = REPO_ROOT / "infra"

CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
ALL_VIEWER_EXCEPT_HOST = "b689b0a8-53d0-40ab-baf2-68738e2966ac"


class _CfnLoader(yaml.SafeLoader):
    """YAML loader that keeps CloudFormation's short-form tags as plain data."""


def _cfn_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return {tag_suffix: value}


_CfnLoader.add_multi_constructor("!", _cfn_tag)


def load(name: str) -> dict:
    return yaml.load((INFRA / name).read_text(encoding="utf-8"), Loader=_CfnLoader)


@pytest.fixture(scope="module")
def template() -> dict:
    return load("template.yaml")


def resource(template, logical_id):
    return template["Resources"][logical_id]["Properties"]


class TestTemplate:
    def test_api_paths_go_to_the_api_uncached_with_cookies_and_headers(self, template):
        config = resource(template, "Distribution")["DistributionConfig"]
        behaviors = {b["PathPattern"]: b for b in config["CacheBehaviors"]}
        for pattern in ("/api/*", "/api"):
            api = behaviors[pattern]
            assert api["TargetOriginId"] == "api"
            assert api["CachePolicyId"] == CACHING_DISABLED
            assert api["OriginRequestPolicyId"] == ALL_VIEWER_EXCEPT_HOST
            assert set(api["AllowedMethods"]) == {"GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"}
            assert "FunctionAssociations" not in api  # the SPA rewrite never sees an API path
        default = config["DefaultCacheBehavior"]
        assert default["TargetOriginId"] == "frontend"
        assert default["FunctionAssociations"][0]["EventType"] == "viewer-request"
        assert default["ViewerProtocolPolicy"] == "redirect-to-https"

    def test_api_origin_carries_the_origin_secret_from_ssm(self, template):
        origins = {o["Id"]: o for o in resource(template, "Distribution")["DistributionConfig"]["Origins"]}
        [header] = origins["api"]["OriginCustomHeaders"]
        assert header["HeaderName"] == "X-PawPal-Origin-Verify"
        assert header["HeaderValue"] == {"Sub": "{{resolve:ssm:${OriginVerifyParameterName}}}"}
        assert origins["api"]["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"
        assert "OriginAccessControlId" in origins["frontend"]

    def test_static_cache_policy_honours_no_cache(self, template):
        policy = resource(template, "StaticCachePolicy")["CachePolicyConfig"]
        assert policy["MinTTL"] == 0
        assert policy["MaxTTL"] >= 31536000

    def test_frontend_bucket_is_private(self, template):
        bucket = resource(template, "FrontendBucket")
        assert all(bucket["PublicAccessBlockConfiguration"].values())
        statements = resource(template, "FrontendBucketPolicy")["PolicyDocument"]["Statement"]
        assert all(s["Principal"] == {"Service": "cloudfront.amazonaws.com"} for s in statements)
        assert all("AWS:SourceArn" in s["Condition"]["StringEquals"] for s in statements)

    def test_table_has_ttl_and_is_protected(self, template):
        table = template["Resources"]["DataTable"]
        props = table["Properties"]
        assert props["TimeToLiveSpecification"] == {"AttributeName": "expires_at", "Enabled": True}
        assert props["BillingMode"] == "PAY_PER_REQUEST"
        assert [k["AttributeName"] for k in props["KeySchema"]] == ["PK", "SK"]
        assert "GlobalSecondaryIndexes" not in props
        assert table["DeletionPolicy"] == "Retain" and props["DeletionProtectionEnabled"] is True

    def test_function_configuration(self, template):
        fn = resource(template, "ApiFunction")
        assert fn["Handler"] == "api.lambda_handler.handler"
        assert template["Globals"]["Function"]["Runtime"] == "python3.13"
        assert fn["Timeout"] < 30  # inside API Gateway's integration timeout
        env = fn["Environment"]["Variables"]
        assert env["PAWPAL_STORAGE_BACKEND"] == "dynamodb"
        assert env["PAWPAL_COOKIE_SECURE"] == "1"
        assert env["PAWPAL_MAX_ATTEMPTS"] == "2"
        assert env["PAWPAL_LLM_MAX_RETRIES"] == "0"
        attempts, timeout = int(env["PAWPAL_MAX_ATTEMPTS"]), float(env["PAWPAL_LLM_TIMEOUT_SECONDS"])
        assert attempts * timeout < fn["Timeout"]
        assert env["PAWPAL_MAX_UPLOAD_BYTES"] == str(4 * 1024 * 1024)
        assert int(env["PAWPAL_MAX_DOCUMENT_CHARS"]) > 0
        for secret in ("PAWPAL_OWNER_KEY", "ANTHROPIC_API_KEY", "PAWPAL_ORIGIN_VERIFY_SECRET"):
            assert secret not in env  # only the *_PARAMETER names are configured
        assert "ReservedConcurrentExecutions" in fn

    def test_function_permissions_are_scoped(self, template):
        statements = resource(template, "ApiFunction")["Policies"][0]["Statement"]
        by_sid = {s["Sid"]: s for s in statements}
        assert by_sid["OwnDataTable"]["Resource"] == {"GetAtt": "DataTable.Arn"}
        assert not any(a in ("dynamodb:*", "dynamodb:Scan") for a in by_sid["OwnDataTable"]["Action"])
        assert by_sid["ReadOwnSecrets"]["Action"] == "ssm:GetParameters"
        assert len(by_sid["ReadOwnSecrets"]["Resource"]) == 3

    def test_api_is_throttled_and_routes_everything_to_the_function(self, template):
        api = resource(template, "HttpApi")
        assert api["DefaultRouteSettings"]["ThrottlingRateLimit"] == {"Ref": "ApiRateLimit"}
        events = resource(template, "ApiFunction")["Events"]
        assert events == {"Api": {"Type": "HttpApi", "Properties": {"ApiId": {"Ref": "HttpApi"}}}}

    def test_no_secret_values_anywhere_in_infra(self):
        for path in INFRA.glob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            assert "sk-ant" not in text and "AKIA" not in text, path.name

    def test_deploy_role_trusts_only_main_of_this_repo(self):
        oidc = load("github-oidc.yaml")
        role = oidc["Resources"]["GitHubDeployRole"]["Properties"]
        [statement] = role["AssumeRolePolicyDocument"]["Statement"]
        condition = statement["Condition"]["StringEquals"]
        assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
        assert condition["token.actions.githubusercontent.com:sub"] == {
            "Sub": "${GitHubSubjectPrefix}:ref:refs/heads/${DeployBranch}"
        }
        # This repository's tokens carry GitHub's immutable subject (names plus
        # numeric ids). A role trusting the classic repo:owner/name form never
        # matches them -- which is how the first automatic deploy failed.
        assert oidc["Parameters"]["GitHubSubjectPrefix"]["Default"] == (
            "repo:manushri1415@98506313/PawPal-Pet-Care@1320543806"
        )


def test_execution_role_can_expand_sam_and_read_the_packaged_code():
    """`sam deploy --role-arn` makes CloudFormation expand the Serverless
    transform and create the function as the execution role. Without these two
    grants the change set fails before any resource exists (found on the first
    real deploy)."""
    oidc = load("github-oidc.yaml")
    statements = oidc["Resources"]["CloudFormationExecutionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    by_sid = {s["Sid"]: s for s in statements}

    transform = by_sid["SamTransform"]
    assert transform["Action"] == "cloudformation:CreateChangeSet"
    assert transform["Resource"]["Sub"].endswith(":aws:transform/Serverless-2016-10-31")

    code = by_sid["PackagedCode"]
    assert "s3:GetObject" in code["Action"]
    assert code["Resource"] == {"Sub": "${ArtifactsBucket.Arn}/*"}

    # Every name the app stack gives its resources falls inside the
    # execution role's `${AppStackName}-*` grants.
    template_text = (INFRA / "template.yaml").read_text(encoding="utf-8")
    for named in ('"${AWS::StackName}-data"', '"${AWS::StackName}-api"', '"${AWS::StackName}-frontend-${AWS::AccountId}"',
                  '"/aws/lambda/${AWS::StackName}-api"'):
        assert named in template_text, named


def test_the_deploy_job_presents_the_oidc_subject_the_role_trusts():
    """GitHub derives the OIDC token's `sub` claim from the job: a job with an
    `environment:` gets repo:<repo>:environment:<name>, any other push job gets
    repo:<repo>:ref:<ref>. The deploy role trusts exactly one of those shapes,
    so the workflow and the trust policy have to agree or no deploy can ever
    assume the role."""
    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    deploy = workflow["jobs"]["deploy"]
    oidc = load("github-oidc.yaml")
    trusted = oidc["Resources"]["GitHubDeployRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    subject = trusted["Condition"]["StringEquals"]["token.actions.githubusercontent.com:sub"]["Sub"]

    assert ":ref:refs/heads/${DeployBranch}" in subject
    assert "environment" not in deploy, "an environment changes the OIDC subject away from ref:refs/heads/main"
    assert deploy["permissions"]["id-token"] == "write"
    assert "refs/heads/main" in deploy["if"] and "push" in deploy["if"]
    assert oidc["Parameters"]["DeployBranch"]["Default"] == "main"
    # The role is assumed with the variable the runbook tells you to set.
    steps = {s.get("uses", "").split("@")[0]: s for s in deploy["steps"]}
    assert steps["aws-actions/configure-aws-credentials"]["with"]["role-to-assume"] == "${{ vars.AWS_DEPLOY_ROLE_ARN }}"


ROUTES = {
    "/": "/index.html",
    "/app": "/index.html",
    "/app/": "/index.html",
    "/app/health": "/index.html",
    "/health": "/index.html",
    "/index.html": "/index.html",
    "/assets/index-AbC123.js": "/assets/index-AbC123.js",
    "/assets/index-AbC123.css": "/assets/index-AbC123.css",
    "/favicon.svg": "/favicon.svg",
    "/assets/pets/dog.v2.svg": "/assets/pets/dog.v2.svg",
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_cloudfront_spa_rewrite_function(template, tmp_path):
    code = resource(template, "SpaRewriteFunction")["FunctionCode"]
    script = tmp_path / "run.js"
    script.write_text(
        code
        + "\nconst routes = "
        + json.dumps(list(ROUTES))
        + ";\nconsole.log(JSON.stringify(routes.map(u => handler({request: {uri: u}}).uri)));\n",
        encoding="utf-8",
    )
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    assert dict(zip(ROUTES, json.loads(out))) == ROUTES


def test_stage_lambda_copies_the_app_and_drops_server_and_sdk_requirements(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("stage_lambda", REPO_ROOT / "scripts" / "stage_lambda.py")
    stage_lambda = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage_lambda)

    out = stage_lambda.stage(tmp_path / "lambda-src")
    assert (out / "api" / "lambda_handler.py").is_file()
    assert (out / "api" / "demo" / "seed.json").is_file()
    assert (out / "pawpal_ai" / "llm.py").is_file()
    assert (out / "pawpal_system.py").is_file()
    assert not list(out.rglob("__pycache__"))
    assert not (out / "tests").exists() and not (out / "frontend").exists()

    requirements = (out / "requirements.txt").read_text(encoding="utf-8").split()
    names = {r.split("==")[0].split("[")[0].lower() for r in requirements}
    assert {"fastapi", "mangum", "pydantic", "numpy", "pypdf", "python-docx", "anthropic"} <= names
    assert "uvicorn" not in names and "boto3" not in names
    assert all("==" in r for r in requirements)
