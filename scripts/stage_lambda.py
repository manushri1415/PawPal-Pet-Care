"""Stage the Lambda function's source for ``sam build`` (infra/template.yaml).

Copies only what the function imports -- ``api/``, ``pawpal_ai/``,
``pawpal_system.py`` -- into ``build/lambda-src/`` and writes a
``requirements.txt`` for it: the runtime pins from the repo's
requirements.txt, minus

- ``uvicorn`` -- Lambda runs the app through Mangum, not a server; and
- ``boto3`` -- the python3.13 Lambda runtime ships boto3, so bundling another
  copy would only add ~80 MB of botocore to the package and the cold start.

``sam build`` then installs those pins for Linux: natively on CI's
ubuntu runner, or with ``--use-container`` on Windows/macOS.

    python scripts/stage_lambda.py
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGE = REPO_ROOT / "build" / "lambda-src"
SOURCES = ("api", "pawpal_ai", "pawpal_system.py")
EXCLUDED_REQUIREMENTS = {"uvicorn", "boto3"}
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def lambda_requirements(requirements_text: str) -> list[str]:
    out = []
    for line in requirements_text.splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        name = re.split(r"[\[=<>~! ]", requirement, maxsplit=1)[0].lower()
        if name in EXCLUDED_REQUIREMENTS:
            continue
        out.append(requirement)
    return out


def stage(destination: Path = STAGE) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for source in SOURCES:
        path = REPO_ROOT / source
        if path.is_dir():
            shutil.copytree(path, destination / source, ignore=_IGNORE)
        else:
            shutil.copy2(path, destination / source)
    requirements = lambda_requirements((REPO_ROOT / "requirements.txt").read_text(encoding="utf-8"))
    (destination / "requirements.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    out = stage(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else STAGE)
    print(f"Staged Lambda source in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
