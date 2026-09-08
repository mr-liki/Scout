"""
Push the current backend tunnel URL to the deployed Cloudflare Worker
("scout") as its BACKEND_API_URL binding, via the Workers API -- no
Cloudflare dashboard visit needed.

Uses the "Upload Worker Module" endpoint with keep_assets=true, so this
redeploys the *same* frontend/worker.js code with only the BACKEND_API_URL
binding changed; static assets are retained unmodified from the previous
upload. This updates the binding on the actual live deployed version
directly (rather than relying on dashboard "Variables", whose propagation
to a Git-connected Worker's Production environment is not always
immediate/reliable -- see docs/QUICK_TUNNEL_TESTING.md).

Requires CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in
infra/.env.production (gitignored, never printed). Stdlib only -- no
extra dependency needed.

Usage:
    python sync_worker_backend_url.py https://xxxx.trycloudflare.com
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / "infra" / ".env.production"
WORKER_JS_PATH = REPO_ROOT / "frontend" / "worker.js"
WRANGLER_TOML_PATH = REPO_ROOT / "wrangler.toml"
WORKER_SCRIPT_NAME = "scout"
API_BASE = "https://api.cloudflare.com/client/v4"


def load_env_value(key: str) -> str:
    if not ENV_FILE.exists():
        raise SystemExit(f"Missing {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{key}="):
            value = line.split("=", 1)[1].strip()
            if not value:
                raise SystemExit(f"{key} is blank in {ENV_FILE}. See docs/QUICK_TUNNEL_TESTING.md.")
            return value
    raise SystemExit(f"{key} not set in {ENV_FILE}. See docs/QUICK_TUNNEL_TESTING.md.")


def load_compatibility_date() -> str:
    content = WRANGLER_TOML_PATH.read_text(encoding="utf-8")
    match = re.search(r'^compatibility_date\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise SystemExit(f"compatibility_date not found in {WRANGLER_TOML_PATH}")
    return match.group(1)


def build_multipart_body(metadata: dict, worker_source: str, boundary: str) -> bytes:
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="metadata"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(metadata)}\r\n".encode("utf-8"),
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
        f"Content-Type: application/javascript+module\r\n\r\n".encode("utf-8")
        + worker_source.encode("utf-8")
        + b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts)


def sync(backend_url: str) -> None:
    if not backend_url.startswith("https://"):
        raise SystemExit("Backend URL must start with https://")

    token = load_env_value("CLOUDFLARE_API_TOKEN")
    account_id = load_env_value("CLOUDFLARE_ACCOUNT_ID")
    compatibility_date = load_compatibility_date()
    worker_source = WORKER_JS_PATH.read_text(encoding="utf-8")

    metadata = {
        "main_module": "worker.js",
        "bindings": [
            {"type": "assets", "name": "ASSETS"},
            {"type": "plain_text", "name": "BACKEND_API_URL", "text": backend_url},
        ],
        "compatibility_date": compatibility_date,
        "keep_assets": True,
    }

    boundary = "----scoutjobsworkersync"
    body = build_multipart_body(metadata, worker_source, boundary)

    url = f"{API_BASE}/accounts/{account_id}/workers/scripts/{WORKER_SCRIPT_NAME}"
    request = urllib.request.Request(url, data=body, method="PUT")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _report_errors(e.code, e.read().decode("utf-8", errors="replace"))
        raise SystemExit(1)

    if result.get("success"):
        print("[OK] Worker 'scout' redeployed: BACKEND_API_URL synced (code and assets unchanged).")
    else:
        _report_errors(200, json.dumps(result))
        raise SystemExit(1)


def _report_errors(status_code: int, raw_body: str) -> None:
    print(f"[FAIL] Cloudflare API returned status {status_code}")
    try:
        parsed = json.loads(raw_body)
        for err in parsed.get("errors", []):
            print(f"       {err.get('code')}: {err.get('message')}")
    except (json.JSONDecodeError, AttributeError):
        print("       (could not parse error response body)")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: sync_worker_backend_url.py <backend-tunnel-url>")
    sync(sys.argv[1].strip())


if __name__ == "__main__":
    main()
