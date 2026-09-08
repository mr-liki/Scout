"""
test_cloudflare_proxy.py - Cloudflare Worker /api/* proxy tests for SCOUTJOBS.

frontend/worker.js is actually executed under Node (which provides native
fetch/Request/Response/Headers), with the global `fetch` and `env.ASSETS`
replaced by mocks -- no real Cloudflare, no real backend, no network calls,
no live LinkedIn requests. Node is required for these tests; if it is not
on PATH, tests are skipped rather than failing the whole suite.

Static (non-executed) checks cover wrangler.toml shape and that no tunnel
URL is hardcoded anywhere in the frontend.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
WORKER_PATH = REPO_ROOT / "frontend" / "worker.js"
WORKER_URI = WORKER_PATH.as_uri()

NODE_AVAILABLE = shutil.which("node") is not None


def _run_worker(
    request_url,
    method="GET",
    headers=None,
    body=None,
    backend_url="https://backend-under-test.example",
    backend_status=200,
    backend_body='{"ok":true}',
    backend_headers=None,
    backend_throws=False,
):
    """Execute worker.js's fetch handler under Node with fetch/ASSETS mocked.

    Returns a dict: {status, headers, body, backendCall, assetsCalls}.
    backendCall is None if the backend fetch mock was never invoked.
    """
    scenario = {
        "requestUrl": request_url,
        "requestMethod": method,
        "requestHeaders": headers or {},
        "requestBody": body,
        "backendApiUrl": backend_url,
        "backendStatus": backend_status,
        "backendBody": backend_body,
        "backendHeaders": backend_headers or {"Content-Type": "application/json"},
        "backendThrows": backend_throws,
    }

    script = f"""
import worker from {json.dumps(WORKER_URI)};

const SCENARIO = {json.dumps(scenario)};

let backendCall = null;

globalThis.fetch = async (url, init) => {{
  let bodyText = null;
  if (init && init.body) {{
    bodyText = await new Response(init.body).text();
  }}
  backendCall = {{
    url: url.toString(),
    method: (init && init.method) || "GET",
    headers: init && init.headers ? Object.fromEntries(init.headers.entries()) : {{}},
    body: bodyText,
  }};
  if (SCENARIO.backendThrows) {{
    throw new Error("simulated network failure");
  }}
  return new Response(SCENARIO.backendBody, {{
    status: SCENARIO.backendStatus,
    headers: SCENARIO.backendHeaders,
  }});
}};

const assetsCalls = [];
const env = {{
  BACKEND_API_URL: SCENARIO.backendApiUrl,
  ASSETS: {{
    fetch: async (req) => {{
      assetsCalls.push(req.url);
      return new Response("STATIC_ASSET_OK", {{ status: 200 }});
    }},
  }},
}};

const reqInit = {{
  method: SCENARIO.requestMethod,
  headers: SCENARIO.requestHeaders,
}};
if (SCENARIO.requestBody !== null && !["GET", "HEAD"].includes(SCENARIO.requestMethod)) {{
  reqInit.body = SCENARIO.requestBody;
}}

const request = new Request(SCENARIO.requestUrl, reqInit);
const response = await worker.fetch(request, env);
const responseBody = await response.text();

console.log(JSON.stringify({{
  status: response.status,
  headers: Object.fromEntries(response.headers.entries()),
  body: responseBody,
  backendCall,
  assetsCalls,
}}));
"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mjs", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["node", temp_path], capture_output=True, text=True, timeout=15
        )
    finally:
        os.unlink(temp_path)

    if result.returncode != 0:
        raise RuntimeError(f"worker.js scenario failed:\n{result.stderr}")

    return json.loads(result.stdout.strip().splitlines()[-1])


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestApiPathsAreProxied(unittest.TestCase):
    """TEST 1: /api/* paths are proxied to the backend."""

    def test_api_v1_searches_is_proxied(self):
        result = _run_worker("https://scout.apexora.workers.dev/api/v1/searches")
        self.assertIsNotNone(result["backendCall"])
        self.assertEqual(result["assetsCalls"], [])

    def test_proxied_path_matches_backend_route_unchanged(self):
        result = _run_worker("https://scout.apexora.workers.dev/api/v1/searches")
        self.assertTrue(result["backendCall"]["url"].endswith("/api/v1/searches"))

    def test_job_detail_path_proxied_unchanged(self):
        result = _run_worker("https://scout.apexora.workers.dev/api/jobs/linkedin/12345")
        self.assertTrue(result["backendCall"]["url"].endswith("/api/jobs/linkedin/12345"))

    def test_healthz_alias_strips_api_prefix(self):
        result = _run_worker("https://scout.apexora.workers.dev/api/healthz")
        self.assertTrue(result["backendCall"]["url"].endswith("/healthz"))
        self.assertNotIn("/api/healthz", result["backendCall"]["url"])

    def test_readyz_alias_strips_api_prefix(self):
        result = _run_worker("https://scout.apexora.workers.dev/api/readyz")
        self.assertTrue(result["backendCall"]["url"].endswith("/readyz"))


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestFrontendPathsServedFromAssets(unittest.TestCase):
    """TEST 2: non-/api/ paths are served as static assets, never proxied."""

    def test_root_served_from_assets(self):
        result = _run_worker("https://scout.apexora.workers.dev/")
        self.assertIsNone(result["backendCall"])
        self.assertEqual(len(result["assetsCalls"]), 1)

    def test_index_html_served_from_assets(self):
        result = _run_worker("https://scout.apexora.workers.dev/index.html")
        self.assertIsNone(result["backendCall"])
        self.assertEqual(len(result["assetsCalls"]), 1)

    def test_preview_html_served_from_assets(self):
        result = _run_worker("https://scout.apexora.workers.dev/preview.html")
        self.assertIsNone(result["backendCall"])
        self.assertEqual(len(result["assetsCalls"]), 1)

    def test_css_served_from_assets(self):
        result = _run_worker("https://scout.apexora.workers.dev/css/styles.css")
        self.assertIsNone(result["backendCall"])
        self.assertEqual(len(result["assetsCalls"]), 1)

    def test_unknown_path_still_goes_to_assets_not_backend(self):
        result = _run_worker("https://scout.apexora.workers.dev/some/unknown/path")
        self.assertIsNone(result["backendCall"])
        self.assertEqual(len(result["assetsCalls"]), 1)


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestBackendUrlFromEnvironment(unittest.TestCase):
    """TEST 3: backend URL comes from env.BACKEND_API_URL, not a constant."""

    def test_proxy_target_uses_configured_backend_url(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/v1/searches",
            backend_url="https://some-other-tunnel.trycloudflare.com",
        )
        self.assertTrue(
            result["backendCall"]["url"].startswith("https://some-other-tunnel.trycloudflare.com")
        )

    def test_missing_backend_url_returns_502_without_calling_fetch(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz", backend_url=""
        )
        self.assertEqual(result["status"], 502)
        self.assertIsNone(result["backendCall"])


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestNoHardcodedTunnelUrl(unittest.TestCase):
    """TEST 4: no hardcoded trycloudflare URL anywhere in the worker."""

    def test_worker_source_has_no_trycloudflare_literal(self):
        content = WORKER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("trycloudflare.com", content)

    def test_worker_source_has_no_https_literal_backend_url(self):
        content = WORKER_PATH.read_text(encoding="utf-8")
        # The only "https://" occurrences allowed are in comments describing
        # the concept, not in code building a request target.
        for line in content.splitlines():
            code = line.split("//", 1)[0]
            self.assertNotIn("https://", code)

    def test_wrangler_toml_has_no_backend_url_value(self):
        wrangler_path = REPO_ROOT / "wrangler.toml"
        content = wrangler_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.strip().startswith("BACKEND_API_URL"):
                self.fail("BACKEND_API_URL must not be set in wrangler.toml")
        self.assertNotIn("trycloudflare.com", content)


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestQueryParametersPreserved(unittest.TestCase):
    """TEST 5: query parameters are preserved on proxied requests."""

    def test_query_string_forwarded(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/v1/searches?limit=10&sort=newest"
        )
        self.assertIn("limit=10", result["backendCall"]["url"])
        self.assertIn("sort=newest", result["backendCall"]["url"])


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestPostBodyPreserved(unittest.TestCase):
    """TEST 6: POST body and method are preserved, JSON payload untouched."""

    def test_post_method_and_body_forwarded(self):
        payload = '{"keywords":"Software Engineer","location":"Remote"}'
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/v1/searches",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=payload,
        )
        self.assertEqual(result["backendCall"]["method"], "POST")
        self.assertEqual(result["backendCall"]["body"], payload)

    def test_put_and_delete_methods_forwarded(self):
        for method in ("PUT", "DELETE"):
            result = _run_worker(
                "https://scout.apexora.workers.dev/api/v1/searches/abc",
                method=method,
            )
            self.assertEqual(result["backendCall"]["method"], method)

    def test_only_whitelisted_headers_forwarded(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/v1/searches",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Custom-Secret": "should-not-be-forwarded",
                "Cookie": "session=should-not-be-forwarded",
            },
            body="{}",
        )
        forwarded = result["backendCall"]["headers"]
        self.assertIn("content-type", {k.lower() for k in forwarded})
        self.assertNotIn("x-custom-secret", {k.lower() for k in forwarded})
        self.assertNotIn("cookie", {k.lower() for k in forwarded})


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestBackendUnavailable(unittest.TestCase):
    """TEST 7-8: backend failure returns 502 with no leaked internal info."""

    def test_backend_failure_returns_502(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz", backend_throws=True
        )
        self.assertEqual(result["status"], 502)

    def test_502_body_is_generic_json(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz", backend_throws=True
        )
        payload = json.loads(result["body"])
        self.assertEqual(payload, {"error": "Backend unavailable"})

    def test_502_never_leaks_backend_url(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz",
            backend_url="https://secret-tunnel-name.trycloudflare.com",
            backend_throws=True,
        )
        self.assertNotIn("secret-tunnel-name", result["body"])
        self.assertNotIn("trycloudflare", result["body"])

    def test_502_never_leaks_stack_trace(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz", backend_throws=True
        )
        self.assertNotIn("Error", result["body"])
        self.assertNotIn(".js:", result["body"])


@unittest.skipUnless(NODE_AVAILABLE, "node is required to execute worker.js")
class TestResponsePassthrough(unittest.TestCase):
    def test_backend_status_and_body_passed_through_unchanged(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/healthz",
            backend_status=200,
            backend_body='{"status":"ok","service":"SCOUTJOBS API"}',
        )
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["body"], '{"status":"ok","service":"SCOUTJOBS API"}')

    def test_backend_error_status_passed_through(self):
        result = _run_worker(
            "https://scout.apexora.workers.dev/api/v1/searches",
            method="POST",
            body="{}",
            backend_status=429,
            backend_body='{"detail":"Rate limit exceeded"}',
        )
        self.assertEqual(result["status"], 429)


# ============================================================
# TEST 9-10: static, non-executed source checks
# ============================================================

class TestConfigNoTunnelUrl(unittest.TestCase):
    def test_config_js_api_base_is_empty(self):
        content = (REPO_ROOT / "frontend" / "config.js").read_text(encoding="utf-8")
        self.assertIn('apiBase: "",', content)

    def test_config_js_has_no_trycloudflare_url(self):
        content = (REPO_ROOT / "frontend" / "config.js").read_text(encoding="utf-8")
        self.assertNotIn("trycloudflare.com", content)


class TestApiJsUsesSameOrigin(unittest.TestCase):
    def test_api_js_calls_are_relative_via_api_base(self):
        content = (REPO_ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertIn("${_apiBase}/api/healthz", content)
        self.assertIn("${_apiBase}/api/v1/searches", content)

    def test_api_js_has_no_hardcoded_absolute_backend_url(self):
        content = (REPO_ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
        for line in content.splitlines():
            code = line.split("//", 1)[0].split("*", 1)[0]
            self.assertNotIn("https://", code)

    def test_api_js_no_longer_calls_bare_healthz(self):
        content = (REPO_ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
        self.assertNotIn("`${_apiBase}/healthz`", content)


class TestWranglerConfigShape(unittest.TestCase):
    def test_wrangler_toml_exists(self):
        self.assertTrue((REPO_ROOT / "wrangler.toml").exists())

    def test_wrangler_declares_worker_entry_and_assets(self):
        content = (REPO_ROOT / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn('main = "frontend/worker.js"', content)
        self.assertIn("[assets]", content)
        self.assertIn('binding = "ASSETS"', content)

    def test_wrangler_declares_compatibility_date(self):
        content = (REPO_ROOT / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn("compatibility_date", content)


class TestBackendUnchanged(unittest.TestCase):
    """This task must not touch FastAPI routes, the connector, or the DB."""

    def test_linkedin_connector_not_modified_by_this_task(self):
        # Sanity: the connector still exposes the same public entry point
        # this proxy design relies on staying stable.
        content = (REPO_ROOT / "linkedin_connector.py").read_text(encoding="utf-8")
        self.assertIn("def fetch_linkedin_jobs", content)

    def test_fastapi_routes_unchanged(self):
        content = (REPO_ROOT / "backend" / "api" / "app.py").read_text(encoding="utf-8")
        for route in ("/healthz", "/readyz", "/api/v1/searches", "/api/jobs/linkedin/"):
            self.assertIn(route, content)


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
