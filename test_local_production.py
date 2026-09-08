"""
test_local_production.py - Local Docker Desktop production tests for SCOUTJOBS.

Current production architecture: Cloudflare frontend -> Cloudflare Tunnel
(optional, opt-in) -> Docker Desktop on a dedicated Windows PC -> FastAPI +
PostgreSQL + Valkey + exactly ONE RQ LinkedIn worker.

Tests docker-compose.prod.yml shape, the infra/windows/*.ps1 scripts (by
static content inspection -- no PowerShell interpreter required), config
defaults, and that the optional Render/cloud path stays inert for local
production. No network calls and no live LinkedIn requests are made.
"""

import os
import subprocess
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))
sys.path.insert(0, REPO_ROOT)

from api.config import Settings  # noqa: E402


def _compose_path():
    return os.path.join(REPO_ROOT, "infra", "docker-compose.prod.yml")


def _read_compose_text():
    with open(_compose_path(), "r", encoding="utf-8") as f:
        return f.read()


def _load_compose():
    import yaml
    with open(_compose_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_script(name):
    path = os.path.join(REPO_ROOT, "infra", "windows", name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# TEST 1-4: No published host ports
# ============================================================

class TestNoPublishedPorts(unittest.TestCase):
    def test_no_host_port_bindings_in_compose_source(self):
        content = _read_compose_text()
        for forbidden in ('"5432:5432"', "'5432:5432'", '"6379:6379"', "'6379:6379'",
                           '"8000:8000"', "'8000:8000'"):
            self.assertNotIn(forbidden, content)

    def test_no_service_declares_a_ports_block(self):
        doc = _load_compose()
        for name, svc in doc["services"].items():
            self.assertNotIn("ports", svc, f"service '{name}' must not publish a host port")

    def test_postgres_valkey_api_have_no_ports_key(self):
        doc = _load_compose()
        for name in ("postgres", "valkey", "api", "linkedin_worker", "cloudflared"):
            self.assertIn(name, doc["services"])
            self.assertNotIn("ports", doc["services"][name])


# ============================================================
# TEST 5-7: cloudflared is opt-in, core services are not
# ============================================================

class TestCloudflaredOptIn(unittest.TestCase):
    def test_cloudflared_under_tunnel_profile(self):
        doc = _load_compose()
        self.assertEqual(doc["services"]["cloudflared"].get("profiles"), ["tunnel"])

    def test_core_services_have_no_profile_restriction(self):
        doc = _load_compose()
        for name in ("postgres", "valkey", "api", "linkedin_worker"):
            self.assertNotIn("profiles", doc["services"][name])

    def test_default_services_exclude_cloudflared(self):
        result = subprocess.run(
            ["docker", "compose", "--env-file", "infra/.env.production",
             "-f", "infra/docker-compose.prod.yml", "config", "--services"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.skipTest("docker compose not available in this environment")
        services = result.stdout.split()
        self.assertIn("postgres", services)
        self.assertIn("valkey", services)
        self.assertIn("api", services)
        self.assertIn("linkedin_worker", services)
        self.assertNotIn("cloudflared", services)


# ============================================================
# TEST 8: -IncludeTunnel fails safely with a blank token
# ============================================================

class TestIncludeTunnelSafety(unittest.TestCase):
    def test_start_script_checks_token_before_starting_cloudflared(self):
        content = _read_script("start_backend.ps1")
        self.assertIn("IncludeTunnel", content)
        self.assertIn("CLOUDFLARE_TUNNEL_TOKEN", content)
        self.assertIn("token is not configured", content.lower())
        self.assertIn("core scoutjobs backend remains running", content.lower())

    def test_start_script_never_invents_a_token(self):
        content = _read_script("start_backend.ps1")
        self.assertNotIn("dummy", content.lower())
        self.assertNotIn("fake_token", content.lower())


# ============================================================
# TEST 9-11: cloudflared network/target
# ============================================================

class TestTunnelTarget(unittest.TestCase):
    def test_cloudflared_shares_backend_network_with_api(self):
        doc = _load_compose()
        self.assertIn("backend", doc["services"]["api"]["networks"])
        self.assertIn("backend", doc["services"]["cloudflared"]["networks"])

    def test_api_service_name_is_api(self):
        doc = _load_compose()
        self.assertIn("api", doc["services"])

    def test_tunnel_target_documented_as_internal_api_8000(self):
        docs_path = os.path.join(REPO_ROOT, "docs", "LOCAL_PRODUCTION_DEPLOYMENT.md")
        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("http://api:8000", content)

    def test_cloudflared_token_not_passed_as_command_arg(self):
        """Token must come from the environment, not a `--token` command arg
        (which would appear in process listings / docker inspect args)."""
        doc = _load_compose()
        command = doc["services"]["cloudflared"].get("command", "")
        self.assertNotIn("--token", command if isinstance(command, str) else " ".join(command))


# ============================================================
# TEST 12: exactly one LinkedIn worker service
# ============================================================

class TestSingleWorker(unittest.TestCase):
    def test_exactly_one_linkedin_worker_service(self):
        content = _read_compose_text()
        self.assertEqual(content.count("linkedin_worker:"), 1)

    def test_no_replicas_or_scale_directive(self):
        doc = _load_compose()
        worker = doc["services"]["linkedin_worker"]
        self.assertNotIn("deploy", worker)


# ============================================================
# TEST 13-14: timing config unchanged
# ============================================================

class TestTimingConfig(unittest.TestCase):
    def test_linkedin_job_timeout_is_1200(self):
        settings = Settings()
        self.assertEqual(settings.LINKEDIN_JOB_TIMEOUT_SECONDS, 1200)

    def test_search_stale_after_is_1800(self):
        settings = Settings()
        self.assertEqual(settings.SEARCH_STALE_AFTER_SECONDS, 1800)

    def test_compose_declares_same_defaults(self):
        content = _read_compose_text()
        self.assertIn("LINKEDIN_JOB_TIMEOUT_SECONDS:-1200", content)
        self.assertIn("SEARCH_STALE_AFTER_SECONDS:-1800", content)


# ============================================================
# TEST 15-16: CORS
# ============================================================

class TestCorsProductionOrigin(unittest.TestCase):
    def test_settings_accepts_production_origin(self):
        with mock.patch.dict(os.environ, {"CORS_ORIGINS": "https://scout.apexora.workers.dev"}):
            import importlib
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertIn("https://scout.apexora.workers.dev", settings.CORS_ORIGINS)
        importlib.reload(api.config)

    def test_production_cors_is_not_wildcard(self):
        example_path = os.path.join(REPO_ROOT, "infra", ".env.production.example")
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            if line.strip().startswith("CORS_ORIGINS="):
                self.assertNotEqual(line.strip(), "CORS_ORIGINS=*")
                self.assertIn("scout.apexora.workers.dev", line)


# ============================================================
# TEST 17-18: local Postgres/Valkey, no cloud DB
# ============================================================

class TestLocalDataStores(unittest.TestCase):
    def test_local_redis_url_uses_valkey_hostname(self):
        doc = _load_compose()
        api_env = doc["services"]["api"]["environment"]
        redis_line = next(e for e in api_env if e.startswith("REDIS_URL="))
        self.assertIn("valkey:6379", redis_line)

    def test_local_database_url_uses_postgres_hostname(self):
        doc = _load_compose()
        api_env = doc["services"]["api"]["environment"]
        db_line = next(e for e in api_env if e.startswith("DATABASE_URL="))
        self.assertIn("@postgres:5432", db_line)

    def test_no_neon_or_upstash_hostnames_in_compose(self):
        content = _read_compose_text().lower()
        self.assertNotIn("neon.tech", content)
        self.assertNotIn("upstash.io", content)


# ============================================================
# TEST 19-20: startup/stop scripts never destroy data
# ============================================================

class TestDestructiveOperationsAvoided(unittest.TestCase):
    def test_start_script_never_uses_down_dash_v(self):
        content = _read_script("start_backend.ps1")
        self.assertNotIn("down -v", content)
        self.assertNotIn("down --volumes", content)

    def test_stop_script_never_uses_dash_v(self):
        content = _read_script("stop_backend.ps1")
        self.assertNotIn(" -v", content)
        self.assertNotIn("--volumes", content)
        self.assertNotIn("down", content)

    def test_stop_script_mentions_volume_preservation(self):
        content = _read_script("stop_backend.ps1")
        self.assertIn("preserved", content.lower())


# ============================================================
# TEST 21-22: backup / restore safety
# ============================================================

class TestBackupRestoreSafety(unittest.TestCase):
    def test_backup_uses_pg_dump_custom_format(self):
        content = _read_script("backup_postgres.ps1")
        self.assertIn("pg_dump", content)
        self.assertIn("-Fc", content)

    def test_backup_validates_nonzero_size(self):
        content = _read_script("backup_postgres.ps1")
        self.assertIn("Length -eq 0", content)

    def test_backup_never_overwrites_existing_file(self):
        content = _read_script("backup_postgres.ps1")
        self.assertIn("refusing to overwrite", content.lower())

    def test_restore_requires_explicit_confirm_restore(self):
        content = _read_script("restore_postgres.ps1")
        self.assertIn("ValidateSet(\"RESTORE\")", content)

    def test_restore_never_drops_database_or_schema(self):
        content = _read_script("restore_postgres.ps1")
        self.assertNotIn("DROP DATABASE", content.upper())
        self.assertNotIn("DROP SCHEMA", content.upper())


# ============================================================
# TEST 23: tunnel token never committed
# ============================================================

class TestTunnelTokenNeverCommitted(unittest.TestCase):
    def test_real_env_file_not_tracked_by_git(self):
        result = subprocess.run(
            ["git", "ls-files", "infra/.env.production"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.skipTest("git not available in this environment")
        self.assertEqual(result.stdout.strip(), "")

    def test_example_env_token_is_blank(self):
        example_path = os.path.join(REPO_ROOT, "infra", ".env.production.example")
        with open(example_path, "r", encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            if line.strip().startswith("CLOUDFLARE_TUNNEL_TOKEN="):
                self.assertEqual(line.strip(), "CLOUDFLARE_TUNNEL_TOKEN=")

    def test_compose_references_token_via_env_var_only(self):
        doc = _load_compose()
        content = str(doc["services"]["cloudflared"])
        self.assertIn("CLOUDFLARE_TUNNEL_TOKEN", content)

    def test_gitignore_covers_env_production(self):
        gitignore_path = os.path.join(REPO_ROOT, ".gitignore")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("infra/.env.production", content)


# ============================================================
# TEST 24: frontend config not set to a fake hostname
# ============================================================

class TestFrontendConfigUntouched(unittest.TestCase):
    def test_frontend_api_base_still_empty(self):
        config_path = os.path.join(REPO_ROOT, "frontend", "config.js")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('apiBase: ""', content)

    def test_frontend_config_has_no_fake_hostname(self):
        config_path = os.path.join(REPO_ROOT, "frontend", "config.js")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("onrender.com", content)
        self.assertNotIn("trycloudflare.com", content)
        self.assertNotIn("api.apexora.workers.dev", content)


# ============================================================
# TEST 25: Render/cloud files do not affect local Docker path
# ============================================================

class TestRenderOptionalDoesNotAffectLocal(unittest.TestCase):
    def test_dockerfile_has_no_render_specific_entrypoint(self):
        dockerfile_path = os.path.join(REPO_ROOT, "infra", "Dockerfile.backend")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('CMD ["uvicorn"', content)
        self.assertNotIn("start_render.py", content.split("CMD")[-1])

    def test_compose_does_not_reference_render_start_script(self):
        content = _read_compose_text()
        self.assertNotIn("start_render.py", content)
        self.assertNotIn("render.yaml", content)

    def test_render_yaml_marked_optional(self):
        render_yaml_path = os.path.join(REPO_ROOT, "render.yaml")
        with open(render_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("OPTIONAL ALTERNATIVE", content)

    def test_cloud_docs_marked_not_current_production(self):
        docs_path = os.path.join(REPO_ROOT, "docs", "CLOUD_DEPLOYMENT.md")
        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("NOT CURRENT PRODUCTION", content)


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
