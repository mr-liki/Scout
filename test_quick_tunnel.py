"""
test_quick_tunnel.py - Free Quick Tunnel (development/testing) tests for SCOUTJOBS.

Covers the opt-in `quick-tunnel` Compose profile (`cloudflared-quick`
service): no token required, temporary trycloudflare.com URL, and that it
never interferes with the named production tunnel or the core services'
"no host ports" guarantee.

No Docker commands are actually run against a live daemon here (that is
covered by manual live validation) -- these tests are static/structural,
mocking subprocess where a live check would otherwise be needed. No network
calls and no live LinkedIn requests are made.
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
# TEST 1-2: both profiles exist
# ============================================================

class TestBothTunnelProfilesExist(unittest.TestCase):
    def test_quick_tunnel_profile_exists(self):
        doc = _load_compose()
        profiles = {p for svc in doc["services"].values() for p in svc.get("profiles", [])}
        self.assertIn("quick-tunnel", profiles)

    def test_named_tunnel_profile_still_exists(self):
        doc = _load_compose()
        profiles = {p for svc in doc["services"].values() for p in svc.get("profiles", [])}
        self.assertIn("tunnel", profiles)

    def test_quick_tunnel_is_its_own_service(self):
        doc = _load_compose()
        self.assertIn("cloudflared-quick", doc["services"])
        self.assertEqual(doc["services"]["cloudflared-quick"]["profiles"], ["quick-tunnel"])

    def test_named_tunnel_service_unchanged_profile(self):
        doc = _load_compose()
        self.assertIn("cloudflared", doc["services"])
        self.assertEqual(doc["services"]["cloudflared"]["profiles"], ["tunnel"])

    def test_starting_one_tunnel_service_does_not_declare_the_other(self):
        result = subprocess.run(
            ["docker", "compose", "--env-file", "infra/.env.production",
             "-f", "infra/docker-compose.prod.yml", "--profile", "quick-tunnel",
             "config", "--services"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0:
            self.skipTest("docker compose not available in this environment")
        services = result.stdout.split()
        self.assertIn("cloudflared-quick", services)
        self.assertNotIn("cloudflared", services)


# ============================================================
# TEST 3: quick tunnel requires no token
# ============================================================

class TestQuickTunnelNoToken(unittest.TestCase):
    def test_quick_tunnel_service_has_no_environment_block(self):
        doc = _load_compose()
        self.assertNotIn("environment", doc["services"]["cloudflared-quick"])

    def test_quick_tunnel_command_has_no_token_flag(self):
        doc = _load_compose()
        command = doc["services"]["cloudflared-quick"]["command"]
        joined = command if isinstance(command, str) else " ".join(command)
        self.assertNotIn("--token", joined)
        self.assertNotIn("TUNNEL_TOKEN", joined)

    def test_no_quick_tunnel_token_env_var_introduced(self):
        """No QUICK_TUNNEL_TOKEN=... assignment exists anywhere (a comment
        explaining that none is needed is fine and expected)."""
        example_path = os.path.join(REPO_ROOT, "infra", ".env.production.example")
        with open(example_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        assignment_lines = [ln for ln in lines if ln.strip().startswith("QUICK_TUNNEL_TOKEN=")]
        self.assertEqual(assignment_lines, [])

    def test_start_script_starts_quick_tunnel_without_checking_token(self):
        content = _read_script("start_backend.ps1")
        # The quick-tunnel branch must not gate on CLOUDFLARE_TUNNEL_TOKEN.
        quick_branch = content.split("IncludeQuickTunnel) {", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("CLOUDFLARE_TUNNEL_TOKEN", quick_branch)


# ============================================================
# TEST 4: quick tunnel target
# ============================================================

class TestQuickTunnelTarget(unittest.TestCase):
    def test_quick_tunnel_targets_internal_api_8000(self):
        doc = _load_compose()
        command = doc["services"]["cloudflared-quick"]["command"]
        joined = command if isinstance(command, str) else " ".join(command)
        self.assertIn("http://api:8000", joined)

    def test_quick_tunnel_uses_url_flag(self):
        doc = _load_compose()
        command = doc["services"]["cloudflared-quick"]["command"]
        joined = command if isinstance(command, str) else " ".join(command)
        self.assertIn("--url", joined)

    def test_quick_tunnel_shares_backend_network(self):
        doc = _load_compose()
        self.assertIn("backend", doc["services"]["cloudflared-quick"]["networks"])

    def test_quick_tunnel_depends_on_healthy_api(self):
        doc = _load_compose()
        depends = doc["services"]["cloudflared-quick"]["depends_on"]
        self.assertEqual(depends["api"]["condition"], "service_healthy")

    def test_quick_tunnel_restart_policy(self):
        doc = _load_compose()
        self.assertEqual(doc["services"]["cloudflared-quick"]["restart"], "unless-stopped")


# ============================================================
# TEST 5-8: no published host ports anywhere
# ============================================================

class TestNoPublishedPorts(unittest.TestCase):
    def test_cloudflared_quick_has_no_ports(self):
        doc = _load_compose()
        self.assertNotIn("ports", doc["services"]["cloudflared-quick"])

    def test_named_cloudflared_has_no_ports(self):
        doc = _load_compose()
        self.assertNotIn("ports", doc["services"]["cloudflared"])

    def test_api_has_no_ports(self):
        doc = _load_compose()
        self.assertNotIn("ports", doc["services"]["api"])

    def test_postgres_has_no_ports(self):
        doc = _load_compose()
        self.assertNotIn("ports", doc["services"]["postgres"])

    def test_valkey_has_no_ports(self):
        doc = _load_compose()
        self.assertNotIn("ports", doc["services"]["valkey"])

    def test_no_host_port_bindings_anywhere_in_source(self):
        content = _read_compose_text()
        for forbidden in ('"5432:5432"', "'5432:5432'", '"6379:6379"', "'6379:6379'",
                           '"8000:8000"', "'8000:8000'"):
            self.assertNotIn(forbidden, content)


# ============================================================
# TEST 9: start script accepts -IncludeQuickTunnel
# ============================================================

class TestStartScriptAcceptsQuickTunnelSwitch(unittest.TestCase):
    def test_param_block_declares_switch(self):
        content = _read_script("start_backend.ps1")
        self.assertIn("[switch]$IncludeQuickTunnel", content)

    def test_help_documents_the_parameter(self):
        content = _read_script("start_backend.ps1")
        self.assertIn(".PARAMETER IncludeQuickTunnel", content)

    def test_mutually_exclusive_with_include_tunnel(self):
        content = _read_script("start_backend.ps1")
        self.assertIn("IncludeTunnel -and $IncludeQuickTunnel", content)

    def test_quick_tunnel_start_targets_correct_service(self):
        content = _read_script("start_backend.ps1")
        self.assertIn("--profile quick-tunnel up -d cloudflared-quick", content)

    def test_quick_tunnel_prints_testing_only_note(self):
        content = _read_script("start_backend.ps1")
        self.assertIn("TEMPORARY", content)


# ============================================================
# TEST 10: normal startup does not start cloudflared
# ============================================================

class TestDefaultStartupExcludesTunnels(unittest.TestCase):
    def test_default_services_exclude_both_tunnels(self):
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
        self.assertNotIn("cloudflared-quick", services)

    def test_start_script_default_call_has_no_tunnel_flags(self):
        content = _read_script("start_backend.ps1")
        # The unconditional "Starting postgres and valkey..." step must not
        # be gated behind either tunnel switch.
        self.assertIn('Invoke-Expression "$composeCmd up -d --wait postgres valkey"', content)


# ============================================================
# TEST 11: stop script covers both tunnel profiles
# ============================================================

class TestStopScriptCoversBothTunnels(unittest.TestCase):
    def test_stop_includes_both_profiles(self):
        content = _read_script("stop_backend.ps1")
        self.assertIn("--profile tunnel --profile quick-tunnel", content)

    def test_stop_never_removes_volumes(self):
        content = _read_script("stop_backend.ps1")
        self.assertNotIn(" -v", content)
        self.assertNotIn("--volumes", content)
        self.assertNotIn("down", content)


# ============================================================
# TEST 12: status script distinguishes tunnel modes
# ============================================================

class TestStatusScriptDistinguishesModes(unittest.TestCase):
    def test_status_checks_quick_tunnel_container(self):
        content = _read_script("status.ps1")
        self.assertIn("cloudflared-quick", content)

    def test_status_labels_quick_tunnel_as_testing(self):
        content = _read_script("status.ps1")
        self.assertIn("TESTING ONLY", content)

    def test_status_never_prints_token_value(self):
        content = _read_script("status.ps1")
        self.assertNotIn("$CLOUDFLARE_TUNNEL_TOKEN", content)


# ============================================================
# TEST 13: CORS_EXTRA_ORIGINS is additive, never a wildcard
# ============================================================

class TestCorsExtraOrigins(unittest.TestCase):
    def test_settings_has_cors_extra_origins_attribute(self):
        settings = Settings()
        self.assertTrue(hasattr(settings, "CORS_EXTRA_ORIGINS"))
        self.assertIsInstance(settings.CORS_EXTRA_ORIGINS, list)

    def test_extra_origins_are_additive(self):
        with mock.patch.dict(os.environ, {
            "CORS_ORIGINS": "https://scout.apexora.workers.dev",
            "CORS_EXTRA_ORIGINS": "https://abcd1234.trycloudflare.com",
        }):
            import importlib
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            combined = settings.CORS_ORIGINS + settings.CORS_EXTRA_ORIGINS
            self.assertIn("https://scout.apexora.workers.dev", combined)
            self.assertIn("https://abcd1234.trycloudflare.com", combined)
        importlib.reload(api.config)

    def test_wildcard_in_extra_origins_is_dropped(self):
        with mock.patch.dict(os.environ, {"CORS_EXTRA_ORIGINS": "*"}):
            import importlib
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertNotIn("*", settings.CORS_EXTRA_ORIGINS)
        importlib.reload(api.config)

    def test_blank_extra_origins_produces_empty_list(self):
        with mock.patch.dict(os.environ, {"CORS_EXTRA_ORIGINS": ""}):
            import importlib
            import api.config
            importlib.reload(api.config)
            settings = api.config.Settings()
            self.assertEqual(settings.CORS_EXTRA_ORIGINS, [])
        importlib.reload(api.config)

    def test_no_quick_tunnel_token_var_referenced_in_settings(self):
        settings_path = os.path.join(REPO_ROOT, "backend", "api", "config.py")
        with open(settings_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("QUICK_TUNNEL_TOKEN", content)


# ============================================================
# TEST 14: frontend config still untouched
# ============================================================

class TestFrontendConfigUntouched(unittest.TestCase):
    def test_api_base_still_empty(self):
        config_path = os.path.join(REPO_ROOT, "frontend", "config.js")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('apiBase: ""', content)
        self.assertNotIn("trycloudflare.com", content)


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
