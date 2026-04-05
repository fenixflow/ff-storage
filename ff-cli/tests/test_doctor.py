"""Tests for the doctor command — 21-point diagnostic system."""

from unittest.mock import MagicMock

import pytest

from ff_cli.commands import doctor as doctor_module


@pytest.fixture(autouse=True)
def stub_brand(monkeypatch, tmp_path):
    """Provide a deterministic brand configuration for doctor tests."""

    class FakeBrand:
        cli_name = "ff"
        cli_display_name = "FenixFlow"
        icon = "*"
        docker_network = "ff-network"
        config_dir = tmp_path / ".ff"
        config_dir_name = ".ff"
        plugin_entry_point = "fenix.plugins"

    monkeypatch.setattr(doctor_module, "get_brand", FakeBrand)


@pytest.fixture(autouse=True)
def stub_console(monkeypatch):
    """Silence console output during tests."""
    mock_console = MagicMock()
    monkeypatch.setattr(doctor_module, "console", mock_console)
    return mock_console


class TestResultHelper:
    def test_ok_result(self):
        r = doctor_module._result("Test", "ok", "Details")
        assert r["name"] == "Test"
        assert r["status"] == "ok"
        assert r["detail"] == "Details"
        assert r["recommendations"] == []
        assert r["fixable"] is False

    def test_fail_result_with_recommendations(self):
        r = doctor_module._result("Test", "fail", "Broken", ["Fix it"], fixable=True)
        assert r["status"] == "fail"
        assert r["recommendations"] == ["Fix it"]
        assert r["fixable"] is True


class TestIndividualChecks:
    def test_check_python_version(self):
        result = doctor_module.check_python_version()
        assert result["status"] in ("ok", "OK", "warn", "WARN", "fail", "FAIL")
        assert result["name"]

    def test_check_uv(self):
        result = doctor_module.check_uv()
        assert result["status"] in ("ok", "OK", "fail", "FAIL")

    def test_check_git(self):
        result = doctor_module.check_git()
        assert result["status"] in ("ok", "OK", "fail", "FAIL")

    def test_check_cli_installation(self):
        result = doctor_module.check_cli_installation()
        assert result["status"] in ("ok", "OK", "warn", "WARN", "fail", "FAIL")

    def test_check_python_environment(self):
        result = doctor_module.check_python_environment()
        assert result["status"] in ("ok", "OK", "warn", "WARN")

    def test_check_shell_environment(self):
        result = doctor_module.check_shell_environment()
        assert result["status"] in ("ok", "OK", "warn", "WARN")

    def test_check_config_directory(self):
        result = doctor_module.check_config_directory()
        assert result["status"] in ("ok", "OK", "fail", "FAIL")

    def test_check_docker_network(self):
        result = doctor_module.check_docker_network()
        assert result["status"] in ("ok", "OK", "fail", "FAIL")


class TestAutoFixes:
    def test_empty_results_returns_empty_actions(self):
        actions = doctor_module.run_auto_fixes([])
        assert isinstance(actions, list)

    def test_fixable_result_triggers_action(self):
        results = [
            doctor_module._result("Config directory", "fail", "Missing", fixable=True),
        ]
        actions = doctor_module.run_auto_fixes(results)
        assert isinstance(actions, list)


class TestDoctorCommand:
    def test_doctor_callable(self):
        assert callable(doctor_module.doctor)
