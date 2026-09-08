"""
test_render_cloud.py - Render/Neon/Upstash cloud deployment tests for SCOUTJOBS.

STATUS: covers an OPTIONAL ALTERNATIVE deployment path, not current
production (current production is the local Docker Desktop stack -- see
test_local_production.py and docs/LOCAL_PRODUCTION_DEPLOYMENT.md). Kept
passing so the Render fallback stays deployable if ever needed.

Tests the Render supervisor (infra/render/start_render.py), DATABASE_URL
normalization for Neon/psycopg3, Upstash rediss:// support, render.yaml
shape, and that the cloud path stays free of cloudflared/local dependencies.

No network calls and no live LinkedIn requests are made.
"""

import importlib
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# Match the sys.path pattern used by the other root-level test modules.
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "infra", "render"))

import start_render as sr  # noqa: E402
from api.config import normalize_database_url, Settings  # noqa: E402


# ============================================================
# TEST 1: Exactly one Uvicorn worker, PORT honored
# ============================================================

class TestApiCommand(unittest.TestCase):
    """Render must run exactly one Uvicorn worker, bound to $PORT."""

    def test_single_uvicorn_worker(self):
        cmd = sr.build_api_command("10000")
        self.assertIn("--workers", cmd)
        self.assertEqual(cmd[cmd.index("--workers") + 1], "1")
        self.assertNotIn("2", cmd[cmd.index("--workers"):cmd.index("--workers") + 2])

    def test_binds_to_given_port(self):
        cmd = sr.build_api_command("54321")
        self.assertIn("--port", cmd)
        self.assertEqual(cmd[cmd.index("--port") + 1], "54321")

    def test_uses_asgi_app_path(self):
        cmd = sr.build_api_command("10000")
        self.assertIn("backend.api.app:app", cmd)

    def test_proxy_headers_enabled(self):
        cmd = sr.build_api_command("10000")
        self.assertIn("--proxy-headers", cmd)
        self.assertIn("--forwarded-allow-ips=*", cmd)

    def test_get_port_reads_env(self):
        with mock.patch.dict(os.environ, {"PORT": "9999"}):
            self.assertEqual(sr.get_port(), "9999")

    def test_get_port_falls_back_when_unset(self):
        env = dict(os.environ)
        env.pop("PORT", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(sr.get_port(), "10000")


# ============================================================
# TEST 2: Exactly one RQ worker command, no duplication
# ============================================================

class TestWorkerCommand(unittest.TestCase):
    """Render must launch exactly one LinkedIn RQ worker process."""

    def test_worker_command_uses_existing_runner(self):
        cmd = sr.build_worker_command()
        self.assertIn("backend.worker.runner", cmd)

    def test_supervisor_starts_exactly_two_children(self):
        """One API process + one worker process, never more."""
        with mock.patch.object(sr.subprocess, "Popen") as mock_popen:
            mock_popen.return_value = mock.Mock()
            supervisor = sr.Supervisor()
            supervisor.start("10000")
            self.assertEqual(mock_popen.call_count, 2)
            worker_calls = [
                c for c in mock_popen.call_args_list
                if "backend.worker.runner" in c.args[0]
            ]
            self.assertEqual(len(worker_calls), 1)


# ============================================================
# TEST 3: Neon / psycopg3 URL normalization
# ============================================================

class TestDatabaseUrlNormalization(unittest.TestCase):
    """postgres(ql):// must become postgresql+psycopg://, nothing else changes."""

    def test_plain_postgresql_scheme_upgraded(self):
        url = "postgresql://user:pass@host.neon.tech/db?sslmode=require"
        result = normalize_database_url(url)
        self.assertEqual(
            result,
            "postgresql+psycopg://user:pass@host.neon.tech/db?sslmode=require",
        )

    def test_legacy_postgres_scheme_upgraded(self):
        url = "postgres://user:pass@host.neon.tech/db?sslmode=require"
        result = normalize_database_url(url)
        self.assertTrue(result.startswith("postgresql+psycopg://"))

    def test_already_psycopg_left_unchanged(self):
        url = "postgresql+psycopg://user:pass@host.neon.tech/db?sslmode=require"
        self.assertEqual(normalize_database_url(url), url)

    def test_query_parameters_preserved(self):
        url = "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
        result = normalize_database_url(url)
        self.assertIn("sslmode=require", result)
        self.assertIn("channel_binding=require", result)

    def test_credentials_and_host_preserved(self):
        url = "postgres://scoutuser:s3cr3t@ep-cool-1234.us-east-2.aws.neon.tech/scoutjobs?sslmode=require"
        result = normalize_database_url(url)
        self.assertIn("scoutuser:s3cr3t@ep-cool-1234.us-east-2.aws.neon.tech", result)
        self.assertIn("/scoutjobs", result)

    def test_empty_url_returned_unchanged(self):
        self.assertEqual(normalize_database_url(""), "")

    def test_settings_database_url_is_normalized(self):
        with mock.patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://u:p@host/db?sslmode=require"},
        ):
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertTrue(settings.DATABASE_URL.startswith("postgresql+psycopg://"))
        importlib.reload(api.config)


# ============================================================
# TEST 4: Upstash rediss:// support
# ============================================================

class TestUpstashRedisSupport(unittest.TestCase):
    """rediss:// (TLS) must never be downgraded or rejected."""

    def test_rediss_scheme_preserved_in_settings(self):
        with mock.patch.dict(
            os.environ,
            {"REDIS_URL": "rediss://default:pw@usw1-abc.upstash.io:6379"},
        ):
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertTrue(settings.REDIS_URL.startswith("rediss://"))
        importlib.reload(api.config)

    def test_cache_manager_uses_redis_from_url(self):
        """CacheManager must hand REDIS_URL to redis.from_url unmodified."""
        from db import cache as cache_module

        fake_settings = mock.Mock()
        fake_settings.REDIS_URL = "rediss://default:pw@usw1-abc.upstash.io:6379"
        fake_settings.SEARCH_CACHE_TTL_SECONDS = 90
        fake_settings.DETAIL_CACHE_TTL_SECONDS = 1800

        with mock.patch("redis.from_url") as mock_from_url, \
                mock.patch.object(cache_module, "get_settings", return_value=fake_settings):
            cache_module.CacheManager()
            called_url = mock_from_url.call_args.args[0]
            self.assertTrue(called_url.startswith("rediss://"))


# ============================================================
# TEST 5: CORS
# ============================================================

class TestCorsConfiguration(unittest.TestCase):
    """Production CORS must allow exactly the Cloudflare frontend origin."""

    def test_cors_origins_include_production_frontend(self):
        with mock.patch.dict(
            os.environ, {"CORS_ORIGINS": "https://scout.apexora.workers.dev"}
        ):
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertIn("https://scout.apexora.workers.dev", settings.CORS_ORIGINS)
        importlib.reload(api.config)

    def test_render_yaml_declares_production_origin(self):
        content = _read_render_yaml_text()
        self.assertIn("https://scout.apexora.workers.dev", content)


# ============================================================
# TEST 6: Worker/search timing config unchanged
# ============================================================

class TestTimingConfigUnchanged(unittest.TestCase):
    def test_linkedin_job_timeout_still_1200(self):
        settings = Settings()
        self.assertEqual(settings.LINKEDIN_JOB_TIMEOUT_SECONDS, 1200)

    def test_search_stale_after_still_1800(self):
        settings = Settings()
        self.assertEqual(settings.SEARCH_STALE_AFTER_SECONDS, 1800)


# ============================================================
# TEST 7: render.yaml shape
# ============================================================

def _render_yaml_path():
    return os.path.join(REPO_ROOT, "render.yaml")


def _read_render_yaml_text():
    with open(_render_yaml_path(), "r", encoding="utf-8") as f:
        return f.read()


def _read_render_yaml_code_lines():
    """Lines of render.yaml with full-line/leading comments stripped."""
    lines = []
    for line in _read_render_yaml_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _load_render_yaml():
    import yaml
    with open(_render_yaml_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestRenderYamlShape(unittest.TestCase):
    def test_render_yaml_exists(self):
        self.assertTrue(os.path.exists(_render_yaml_path()))

    def test_render_yaml_is_valid_yaml(self):
        doc = _load_render_yaml()
        self.assertIsInstance(doc, dict)
        self.assertIn("services", doc)

    def test_exactly_one_service(self):
        doc = _load_render_yaml()
        self.assertEqual(len(doc["services"]), 1)

    def test_service_is_free_docker_web_service(self):
        service = _load_render_yaml()["services"][0]
        self.assertEqual(service["name"], "scoutjobs-api")
        self.assertEqual(service["type"], "web")
        self.assertEqual(service["runtime"], "docker")
        self.assertEqual(service["plan"], "free")

    def test_no_render_postgres_or_redis_service(self):
        content = _read_render_yaml_text()
        self.assertNotIn("type: pserv", content)
        self.assertNotIn("type: redis", content)

    def test_no_second_worker_or_cron_service(self):
        doc = _load_render_yaml()
        self.assertEqual(len(doc["services"]), 1)
        content = _read_render_yaml_code_lines().lower()
        self.assertNotIn("cron", content)

    def test_no_cloudflared_in_render_yaml(self):
        content = _read_render_yaml_code_lines().lower()
        self.assertNotIn("cloudflared", content)

    def test_health_check_is_healthz_not_readyz(self):
        service = _load_render_yaml()["services"][0]
        self.assertEqual(service["healthCheckPath"], "/healthz")

    def test_start_command_uses_supervisor(self):
        service = _load_render_yaml()["services"][0]
        self.assertIn("infra/render/start_render.py", service["dockerCommand"])

    def test_database_and_redis_url_are_secrets_not_values(self):
        service = _load_render_yaml()["services"][0]
        env_by_key = {e["key"]: e for e in service["envVars"]}
        for key in ("DATABASE_URL", "REDIS_URL"):
            self.assertIn(key, env_by_key)
            self.assertEqual(env_by_key[key].get("sync"), False)
            self.assertNotIn("value", env_by_key[key])

    def test_no_real_secret_committed(self):
        """No password-shaped literal value anywhere in the blueprint."""
        content = _read_render_yaml_text()
        # Only URLs that may appear are the CORS origin (https, no credentials).
        for line in content.splitlines():
            if "://" in line:
                self.assertIn("scout.apexora.workers.dev", line)


# ============================================================
# TEST 8: Frontend config untouched (no fake Render URL)
# ============================================================

class TestFrontendConfigUntouched(unittest.TestCase):
    def test_api_base_still_empty(self):
        config_path = os.path.join(REPO_ROOT, "frontend", "config.js")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('apiBase: ""', content)
        self.assertNotIn("onrender.com", content)


# ============================================================
# TEST 9: Cloud path has no cloudflared / local dependency
# ============================================================

class TestNoLocalDependencyInCloudPath(unittest.TestCase):
    def test_start_render_has_no_cloudflared_reference(self):
        path = os.path.join(REPO_ROOT, "infra", "render", "start_render.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        self.assertNotIn("cloudflared", content)
        self.assertNotIn("tunnel_token", content)

    def test_selfhost_compose_untouched_by_cloud_path(self):
        """Local self-host cloudflared usage is unrelated to the Render path."""
        compose_path = os.path.join(REPO_ROOT, "infra", "docker-compose.prod.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Self-host compose keeps cloudflared as its own optional profile.
        self.assertIn("cloudflared", content)


# ============================================================
# TEST 10: Supervisor child-process monitoring and shutdown
# ============================================================

class TestSupervisorLifecycle(unittest.TestCase):
    def _make_mock_proc(self, poll_sequence):
        import itertools
        proc = mock.Mock()
        proc.poll.side_effect = itertools.chain(poll_sequence, itertools.repeat(poll_sequence[-1]))
        proc.pid = 1234
        return proc

    def test_monitor_exits_nonzero_if_api_dies(self):
        supervisor = sr.Supervisor()
        supervisor.api_proc = self._make_mock_proc([1])  # dies immediately, code 1
        supervisor.worker_proc = self._make_mock_proc([None] * 50)
        with mock.patch.object(sr.time, "sleep"):
            code = supervisor.monitor()
        self.assertEqual(code, 1)
        supervisor.worker_proc.terminate.assert_called_once()

    def test_monitor_exits_nonzero_if_worker_dies(self):
        supervisor = sr.Supervisor()
        supervisor.api_proc = self._make_mock_proc([None] * 50)
        supervisor.worker_proc = self._make_mock_proc([1])
        with mock.patch.object(sr.time, "sleep"):
            code = supervisor.monitor()
        self.assertEqual(code, 1)
        supervisor.api_proc.terminate.assert_called_once()

    def test_shutdown_forwards_to_both_children(self):
        supervisor = sr.Supervisor()
        supervisor.api_proc = self._make_mock_proc([None, 0])
        supervisor.worker_proc = self._make_mock_proc([None, 0])
        supervisor.shutdown(grace_seconds=0)
        supervisor.api_proc.terminate.assert_called_once()
        supervisor.worker_proc.terminate.assert_called_once()

    def test_shutdown_is_idempotent(self):
        supervisor = sr.Supervisor()
        supervisor.api_proc = self._make_mock_proc([None, 0])
        supervisor.worker_proc = self._make_mock_proc([None, 0])
        supervisor.shutdown(grace_seconds=0)
        supervisor.shutdown(grace_seconds=0)
        supervisor.api_proc.terminate.assert_called_once()

    def test_monitor_returns_zero_on_requested_shutdown(self):
        supervisor = sr.Supervisor()
        supervisor.api_proc = self._make_mock_proc([None] * 50)
        supervisor.worker_proc = self._make_mock_proc([None] * 50)
        supervisor._shutting_down = True
        code = supervisor.monitor()
        self.assertEqual(code, 0)


# ============================================================
# TEST 11: Migration retry behavior
# ============================================================

class TestMigrationRetry(unittest.TestCase):
    def test_migration_succeeds_first_try(self):
        with mock.patch.object(sr.subprocess, "run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            sr.run_migrations_with_retry(max_attempts=8)
        self.assertEqual(mock_run.call_count, 1)

    def test_migration_retries_then_succeeds(self):
        with mock.patch.object(sr.subprocess, "run") as mock_run, \
                mock.patch.object(sr.time, "sleep"):
            mock_run.side_effect = [mock.Mock(returncode=1), mock.Mock(returncode=0)]
            sr.run_migrations_with_retry(max_attempts=8)
        self.assertEqual(mock_run.call_count, 2)

    def test_migration_gives_up_after_max_attempts(self):
        with mock.patch.object(sr.subprocess, "run") as mock_run, \
                mock.patch.object(sr.time, "sleep"):
            mock_run.return_value = mock.Mock(returncode=1)
            with self.assertRaises(SystemExit):
                sr.run_migrations_with_retry(max_attempts=3)
        self.assertEqual(mock_run.call_count, 3)


# ============================================================
# TEST 12: Required secrets enforced at startup
# ============================================================

class TestRequiredEnvEnforced(unittest.TestCase):
    def test_missing_database_url_fails_fast(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                sr.require_env("DATABASE_URL")

    def test_present_env_returned(self):
        with mock.patch.dict(os.environ, {"REDIS_URL": "rediss://x"}):
            self.assertEqual(sr.require_env("REDIS_URL"), "rediss://x")


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
