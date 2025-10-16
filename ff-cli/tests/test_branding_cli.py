"""Tests for branding utilities and commands."""

from pathlib import Path

from typer.testing import CliRunner

from ff_cli import branding
from ff_cli.main import app

runner = CliRunner()


def _setup_brand_path(monkeypatch, tmp_path: Path) -> Path:
    brand_file = tmp_path / "branding.toml"
    monkeypatch.setattr(branding, "USER_STATE_DIR", tmp_path)
    monkeypatch.setattr(branding, "USER_BRAND_PATH", brand_file)
    branding.reset_brand_cache()
    return brand_file


def test_save_and_load_user_brand(monkeypatch, tmp_path):
    brand_file = _setup_brand_path(monkeypatch, tmp_path)

    assert branding.load_user_brand_config() is None

    custom = branding.BrandConfig(cli_name="custom", config_dir_name=".custom")
    branding.save_user_brand_config(custom)

    assert brand_file.exists()

    branding.reset_brand_cache()
    loaded = branding.get_brand()
    assert loaded.cli_name == "custom"
    assert loaded.config_dir_name == ".custom"

    branding.reset_brand_cache()


def test_branding_reset_command(monkeypatch, tmp_path):
    _setup_brand_path(monkeypatch, tmp_path)
    branding.save_user_brand_config(branding.BrandConfig(cli_name="custom"))

    result = runner.invoke(app, ["branding", "reset", "--yes"])
    assert result.exit_code == 0
    assert not branding.user_brand_exists()

    branding.reset_brand_cache()
    assert branding.get_brand().cli_name == "fenix"


def test_branding_configure_command(monkeypatch, tmp_path):
    _setup_brand_path(monkeypatch, tmp_path)

    inputs = "mybrand\n\n\n\nn\n"
    result = runner.invoke(app, ["branding", "configure"], input=inputs)
    assert result.exit_code == 0

    saved = branding.load_user_brand_config()
    assert saved is not None
    assert saved.cli_name == "mybrand"
    assert saved.config_dir_name == ".mybrand"
    assert saved.plugin_entry_point == "mybrand.plugins"
    assert saved.docker_network == "mybrand-network"
    assert saved.container_prefix == "mybrand"
    assert saved.orbstack_domain_suffix == "mybrand.orb.local"

    branding.reset_brand_cache()
