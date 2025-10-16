"""Tests for the doctor command auto-fix logic."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ff_cli.commands import doctor as doctor_module


@pytest.fixture(autouse=True)
def stub_brand(monkeypatch):
    """Provide a deterministic brand configuration for doctor tests."""

    brand = SimpleNamespace(
        cli_name="ff",
        cli_display_name="FenixFlow",
        icon="*",
        docker_network="ff-network",
    )
    monkeypatch.setattr(doctor_module, "get_brand", lambda: brand)


@pytest.fixture(autouse=True)
def stub_console(monkeypatch):
    """Silence console output during tests."""

    mock_console = MagicMock()
    monkeypatch.setattr(doctor_module, "console", mock_console)
    return mock_console


def test_needs_registry_cleanup_detects_relevant_issues():
    """The registry cleanup helper should flag missing packages and paths."""

    statuses = [{"issues": ["Package not installed", "Load error"]}]
    assert doctor_module._needs_registry_cleanup(statuses) is True

    statuses = [{"issues": ["Source path missing"]}]
    assert doctor_module._needs_registry_cleanup(statuses) is True

    statuses = [{"issues": ["Load error: boom"]}]
    assert doctor_module._needs_registry_cleanup(statuses) is False


def test_doctor_fix_triggers_registry_cleanup(monkeypatch):
    """Doctor --fix should request registry cleanup when plugin data is stale."""

    monkeypatch.setattr(doctor_module, "check_docker", lambda: (True, "Docker ok", []))
    monkeypatch.setattr(doctor_module, "check_cli_installation", lambda: (True, "CLI ok", []))
    monkeypatch.setattr(doctor_module, "check_python_environment", lambda: (True, "Python ok", []))
    monkeypatch.setattr(doctor_module, "check_network", lambda: (False, "Network missing", []))

    plugin_statuses = [
        {"name": "bad-plugin", "source": "/tmp/missing", "issues": ["Package not installed"]}
    ]
    monkeypatch.setattr(
        doctor_module,
        "check_plugins",
        lambda: (False, plugin_statuses, ["Reinstall bad-plugin"]),
    )

    captured = {}

    def fake_run_auto_fixes(*, fix_network: bool, clean_registry: bool):
        captured["fix_network"] = fix_network
        captured["clean_registry"] = clean_registry
        return ["Removed 1 invalid plugin entry", "Created Docker network: ff-network"]

    monkeypatch.setattr(doctor_module, "run_auto_fixes", fake_run_auto_fixes)

    doctor_module.doctor(json_output=True, auto_fix=True)

    assert captured == {"fix_network": True, "clean_registry": True}


def test_doctor_fix_skips_registry_cleanup_when_not_needed(monkeypatch):
    """Doctor --fix should not attempt cleanup if issues are unrelated."""

    monkeypatch.setattr(doctor_module, "check_docker", lambda: (True, "Docker ok", []))
    monkeypatch.setattr(doctor_module, "check_cli_installation", lambda: (True, "CLI ok", []))
    monkeypatch.setattr(doctor_module, "check_python_environment", lambda: (True, "Python ok", []))
    monkeypatch.setattr(doctor_module, "check_network", lambda: (False, "Network missing", []))

    plugin_statuses = [
        {"name": "bad-plugin", "source": "/tmp/missing", "issues": ["Load error: boom"]}
    ]
    monkeypatch.setattr(
        doctor_module,
        "check_plugins",
        lambda: (False, plugin_statuses, ["Inspect bad-plugin"]),
    )

    captured = {}

    def fake_run_auto_fixes(*, fix_network: bool, clean_registry: bool):
        captured["fix_network"] = fix_network
        captured["clean_registry"] = clean_registry
        return []

    monkeypatch.setattr(doctor_module, "run_auto_fixes", fake_run_auto_fixes)

    doctor_module.doctor(json_output=True, auto_fix=True)

    assert captured == {"fix_network": True, "clean_registry": False}


def test_run_auto_fixes_creates_network(monkeypatch):
    """Auto-fix should attempt to create the brand network when missing."""

    class DummyDocker:
        def __init__(self):
            self.created = False

        def get_network_status(self, name):
            return {"exists": False}

        def create_network(self, name):
            self.created = True
            return True

    dummy = DummyDocker()

    monkeypatch.setattr(doctor_module, "DockerManager", lambda: dummy)
    monkeypatch.setattr(
        doctor_module.plugin_registry,
        "clean_registry",
        lambda: 0,
    )

    actions = doctor_module.run_auto_fixes(fix_network=True)

    assert dummy.created is True
    assert "Created Docker network: ff-network" in actions
