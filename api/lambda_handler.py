"""AWS Lambda entry point: the whole FastAPI app as one function behind API
Gateway's HTTP API (infra/template.yaml).

One function serves every route. Splitting the API into a function per route
would multiply cold starts and deployment surface for no benefit at this size,
and would give up the single app -- routers, session middleware, dependency
graph -- that uvicorn and Docker run unchanged.

Everything slow happens here, once per execution environment, during Lambda's
init phase: secrets from SSM, the storage backend's client, the parsed demo
seed and (in the owner space) the Anthropic client. Mangum's lifespan support
is off because Mangum would run the app's startup and shutdown around *every*
invocation; the only startup work the app has is constructing the backend,
which is done here instead.
"""

from __future__ import annotations

from api.secrets import load_secrets_from_ssm

# Before anything imports the app: api.main reads the origin secret when it
# builds the app, and the owner key and Anthropic key are read per request
# from the environment these calls fill in.
load_secrets_from_ssm()

from mangum import Mangum  # noqa: E402

from api.backend import get_storage_backend  # noqa: E402
from api.demo.seed import load_default_seeder  # noqa: E402
from api.deps import get_claude_llm  # noqa: E402
from api.main import create_app  # noqa: E402

# API only: CloudFront serves the frontend from S3 and routes only /api/* here.
app = create_app(serve_frontend=False)

get_storage_backend()
load_default_seeder()
get_claude_llm()

handler = Mangum(app, lifespan="off")
