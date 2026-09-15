"""Create or check the CNAME records PawPal needs at Porkbun.

manushri.dev's DNS is hosted at Porkbun, not Route 53, so two records are
added by hand -- or with this script:

- ACM's DNS validation record for the CloudFront certificate, and
- ``pawpal`` -> the CloudFront distribution's domain name.

Credentials come from a file outside the repository (default
``~/.pawpal/porkbun.env``: ``PORKBUN_API_KEY=...`` and
``PORKBUN_SECRET_KEY=...``), and API Access must be enabled for the domain in
Porkbun's dashboard. The script only ever touches the one name it is given,
refuses to change an existing record that points somewhere else unless told
to, and never prints the keys.

    python scripts/porkbun_dns.py cname <name> <target> [--domain manushri.dev] [--replace]
    python scripts/porkbun_dns.py show <name> [--domain manushri.dev]

<name> is relative to the domain (``pawpal``, ``_3f2a....pawpal``).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.porkbun.com/api/json/v3"
DEFAULT_KEYS_FILE = Path.home() / ".pawpal" / "porkbun.env"


def load_keys(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    missing = {"PORKBUN_API_KEY", "PORKBUN_SECRET_KEY"} - values.keys()
    if missing:
        raise SystemExit(f"{path} is missing {sorted(missing)}")
    return {"apikey": values["PORKBUN_API_KEY"], "secretapikey": values["PORKBUN_SECRET_KEY"]}


def call(endpoint: str, keys: dict[str, str], **payload) -> dict:
    body = json.dumps({**keys, **payload}).encode("utf-8")
    request = urllib.request.Request(
        f"{API}/{endpoint}", data=body, method="POST", headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "SUCCESS":
        raise SystemExit(f"Porkbun {endpoint.split('/')[1]} failed: {data.get('message', data)}")
    return data


def normalize(target: str) -> str:
    return target.strip().rstrip(".").lower()


def existing_cname(domain: str, name: str, keys: dict[str, str]) -> list[dict]:
    return call(f"dns/retrieveByNameType/{domain}/CNAME/{name}", keys).get("records", [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", default="manushri.dev")
    parser.add_argument("--keys-file", type=Path, default=DEFAULT_KEYS_FILE)
    sub = parser.add_subparsers(dest="command", required=True)
    cname = sub.add_parser("cname")
    cname.add_argument("name")
    cname.add_argument("target")
    cname.add_argument("--replace", action="store_true", help="change a record that points elsewhere")
    show = sub.add_parser("show")
    show.add_argument("name")
    args = parser.parse_args(argv)

    keys = load_keys(args.keys_file)
    name = args.name.strip().rstrip(".")
    suffix = "." + args.domain
    if name.endswith(suffix):
        name = name[: -len(suffix)]

    records = existing_cname(args.domain, name, keys)
    fqdn = f"{name}.{args.domain}"
    if args.command == "show":
        print(json.dumps([{"name": r["name"], "content": r["content"], "ttl": r["ttl"]} for r in records], indent=2))
        return 0

    target = normalize(args.target)
    if records:
        current = normalize(records[0]["content"])
        if current == target:
            print(f"{fqdn} CNAME {target} already exists")
            return 0
        if not args.replace:
            print(f"{fqdn} already points to {current}; rerun with --replace to change it", file=sys.stderr)
            return 1
        call(f"dns/editByNameType/{args.domain}/CNAME/{name}", keys, content=target, ttl="600")
        print(f"updated {fqdn} CNAME {target}")
        return 0

    call(f"dns/create/{args.domain}", keys, name=name, type="CNAME", content=target, ttl="600")
    print(f"created {fqdn} CNAME {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
