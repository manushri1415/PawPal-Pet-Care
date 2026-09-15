# PawPal+ on AWS

The whole app, serverless, behind one domain:

```
browser ── https://pawpal.manushri.dev ── CloudFront ──┬─ default ─▶ S3 (private, OAC)        React build
                                                        └─ /api/* ──▶ API Gateway (HTTP API)
                                                                        └─▶ Lambda (Python 3.13, Mangum + FastAPI)
                                                                              ├─▶ DynamoDB (one table, TTL)
                                                                              └─▶ SSM Parameter Store (secrets, at cold start)
```

| Piece | Where | Why this shape |
| --- | --- | --- |
| `template.yaml` | the app stack (SAM) | Lambda, HTTP API, DynamoDB, S3, CloudFront + SPA rewrite function, cache policy, log group |
| `certificate.yaml` | us-east-1 | ACM certificate for the CloudFront alias (DNS validated at Porkbun) |
| `github-oidc.yaml` | once per account | GitHub Actions deploy role (OIDC, `main` only) + CloudFormation execution role + artifacts bucket |

No VPC, no NAT gateway, no always-on server. Idle cost is effectively zero (see [Costs](#costs)).

## How requests flow

- **Pages**: CloudFront serves the build from S3. A CloudFront Function rewrites any path without a file extension (`/app`, `/app/health`) to `/index.html`, so deep links survive a refresh. Files keep their own names, so a missing bundle is a 404, never the app shell.
- **Caching**: set per object at upload by `scripts/deploy_frontend.sh` — `assets/*` (content-hashed) `public, max-age=31536000, immutable`; `index.html` and the other root files `no-cache`. The cache policy's MinTTL is 0 so `no-cache` is honoured.
- **API**: `/api/*` (and `/api`) go to the HTTP API with caching disabled and every viewer header, cookie and query string forwarded (the managed *AllViewerExceptHostHeader* policy) — so the `pawpal_session` cookie, `X-PawPal-Owner-Key` and `X-PawPal-Client-Now` reach the app. The frontend keeps calling relative `/api/...`: same origin, no CORS.
- **Origin check**: CloudFront adds `X-PawPal-Origin-Verify` (from the SSM String parameter `/pawpal/prod/origin-verify`); the app refuses requests without it (`api/origin.py`), so the public `execute-api` URL cannot be used to go around CloudFront.
- **Sessions and data**: each visitor gets a seeded demo sandbox (cookie, 48 h, `expires_at` TTL on every item); the owner key opens the persistent owner space (no TTL). One DynamoDB partition per owner — see `api/repositories/dynamodb.py`.
- **AI**: demo visitors use the free rule-based extractor; only the owner space uses Claude, and only when `/pawpal/prod/anthropic-api-key` exists.

## Limits, and where the numbers come from

| Setting | Production | Reason |
| --- | --- | --- |
| Lambda timeout | 29 s | HTTP API integrations time out at 30 s |
| `PAWPAL_MAX_UPLOAD_BYTES` | 4 MB | The upload arrives base64-encoded inside Lambda's 6,291,456-byte invoke payload. `tests/test_lambda_handler.py::TestPayloadBudget` builds the real event: 4 MB fits with >512 KB to spare, 5 MB does not. |
| `PAWPAL_MAX_DOCUMENT_CHARS` | 200,000 | Extraction and every later Ask re-embed a document's text. Measured locally (rule-based model): 200k chars → 1.4 s extract / 0.8 s Ask; 4M chars → 18 s / 21 s. |
| `PAWPAL_MAX_ATTEMPTS` × `PAWPAL_LLM_TIMEOUT_SECONDS` | 2 × 13 s, no SDK retries | Keeps a failing Claude extraction inside 29 s. **Not yet measured against real Claude latency** — run `scripts/smoke_prod.py --owner --claude` after the Anthropic key is added. |
| API throttling | 10 req/s, burst 20 | Bounds what a runaway client can cost |
| Reserved concurrency | parameter (`0` = unset) | New accounts have a concurrency quota of 10 and cannot reserve any; set e.g. `10` once the quota is 1,000 |

## One-time setup

Everything below runs from the repository root in Git Bash with an active AWS session (`aws login`), region `us-east-1`.

### 1. Secrets in SSM Parameter Store

The owner key is generated locally, kept in `~/.pawpal/` (outside the repo), and uploaded; its value is never printed.

```bash
mkdir -p ~/.pawpal && chmod 700 ~/.pawpal
python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > ~/.pawpal/owner-key.txt
python -c "import secrets; print(secrets.token_urlsafe(32), end='')" > ~/.pawpal/origin-verify.txt

aws ssm put-parameter --name /pawpal/prod/owner-key     --type SecureString --value "file://$HOME/.pawpal/owner-key.txt"
aws ssm put-parameter --name /pawpal/prod/origin-verify --type String       --value "file://$HOME/.pawpal/origin-verify.txt"
# Later, when Claude should be enabled for the owner space (a dedicated key with a spend limit):
# aws ssm put-parameter --name /pawpal/prod/anthropic-api-key --type SecureString --value "file://$HOME/.pawpal/anthropic-api-key.txt"
```

### 2. Certificate (validated at Porkbun)

```bash
aws cloudformation create-stack --region us-east-1 --stack-name pawpal-certificate \
  --template-body file://infra/certificate.yaml
# ACM publishes the validation record within a minute:
aws acm list-certificates --region us-east-1 --query "CertificateSummaryList[?DomainName=='pawpal.manushri.dev'].CertificateArn" --output text
aws acm describe-certificate --region us-east-1 --certificate-arn <arn> \
  --query "Certificate.DomainValidationOptions[0].ResourceRecord" --output json
python scripts/porkbun_dns.py cname <ResourceRecord.Name> <ResourceRecord.Value>
aws cloudformation wait stack-create-complete --region us-east-1 --stack-name pawpal-certificate
```

`scripts/porkbun_dns.py` reads `~/.pawpal/porkbun.env` (`PORKBUN_API_KEY`, `PORKBUN_SECRET_KEY`) and needs *API Access* enabled for the domain in Porkbun. It only touches the name it is given.

### 3. GitHub deploy role

```bash
aws iam list-open-id-connect-providers   # an existing token.actions.githubusercontent.com provider? then CreateOidcProvider=false
aws cloudformation deploy --stack-name pawpal-github-oidc --template-file infra/github-oidc.yaml \
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides CreateOidcProvider=true
aws cloudformation describe-stacks --stack-name pawpal-github-oidc --query "Stacks[0].Outputs" --output table
```

The role trusts one exact OIDC subject: `GitHubSubjectPrefix` followed by `:ref:refs/heads/main`. This repository issues tokens in GitHub's immutable subject format (`repo:owner@ownerId/repo@repoId`), not the classic `repo:owner/repo`. Check the prefix with `gh api repos/OWNER/REPO/actions/oidc/customization/sub` (the `sub_claim_prefix` field). If a deploy fails with *Not authorized to perform sts:AssumeRoleWithWebIdentity*, CloudTrail's `AssumeRoleWithWebIdentity` event shows the subject GitHub actually sent.

### 4. First deploy of the app

```bash
python scripts/stage_lambda.py
sam build --template-file infra/template.yaml --build-dir build/sam --use-container   # Linux wheels on Windows/macOS
sam deploy --template-file build/sam/template.yaml --stack-name pawpal \
  --s3-bucket <ArtifactsBucketName> --s3-prefix sam --role-arn <CloudFormationExecutionRoleArn> \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-confirm-changeset \
  --parameter-overrides CertificateArn=<certificate arn>

(cd frontend && npm ci && npm run build)
bash scripts/deploy_frontend.sh <FrontendBucketName> <DistributionId>
python scripts/porkbun_dns.py cname pawpal <DistributionDomainName>
python scripts/smoke_prod.py https://pawpal.manushri.dev
PAWPAL_SMOKE_OWNER_KEY="$(cat ~/.pawpal/owner-key.txt)" python scripts/smoke_prod.py https://pawpal.manushri.dev --owner
```

### 5. Continuous deployment

Set the repository variables once; from then on every push to `main` runs the full CI and, if it passes, deploys (`.github/workflows/ci.yml`, job `deploy`):

```bash
gh variable set AWS_REGION --body us-east-1
gh variable set AWS_DEPLOY_ROLE_ARN --body <DeployRoleArn>
gh variable set AWS_CFN_EXECUTION_ROLE_ARN --body <CloudFormationExecutionRoleArn>
gh variable set AWS_ARTIFACTS_BUCKET --body <ArtifactsBucketName>
gh variable set PAWPAL_STACK_NAME --body pawpal
gh variable set PAWPAL_DOMAIN --body pawpal.manushri.dev
gh variable set PAWPAL_CERTIFICATE_ARN --body <certificate arn>
```

These are identifiers, not secrets. GitHub never holds AWS keys: the job exchanges its OIDC token for the deploy role, which trusts only pushes to `main` of this repository.

## Operations

- **Logs**: CloudWatch log group `/aws/lambda/pawpal-api` (14-day retention). App events are redacted JSON lines (`pawpal_ai/logging_setup.py`).
- **Owner key rotation**: overwrite `/pawpal/prod/owner-key` (`--overwrite`), then publish a new function version (any deploy) or wait for cold starts.
- **Turn Claude off**: delete `/pawpal/prod/anthropic-api-key`; the owner space falls back to the free model on the next cold start.
- **Tear down**: `aws cloudformation delete-stack --stack-name pawpal`. The DynamoDB table is retained (deletion protection) — delete it separately only if the owner space is no longer wanted.

## Costs

At portfolio traffic, per month, us-east-1:

| Service | Idle | ~10k page views |
| --- | --- | --- |
| Lambda | $0 (billed per invocation; 1M requests + 400k GB-s always free) | $0 |
| API Gateway HTTP API | $0 | ~$0.03 after the 12-month free tier ($1 per million) |
| DynamoDB on-demand | ~$0 (25 GB storage free; PITR on a few MB ≈ $0.00) | < $0.05 |
| CloudFront | $0 (1 TB and 10M requests always free) | $0 |
| S3 (≈5 MB) | < $0.01 | < $0.01 |
| CloudWatch Logs, SSM standard parameters, ACM | $0 | $0 |

There is no hourly component anywhere in the stack. Claude usage in the owner space is billed by Anthropic against its own key and spend limit.
