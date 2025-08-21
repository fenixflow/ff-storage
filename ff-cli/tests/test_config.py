"""Tests for configuration management."""

import tempfile
from pathlib import Path

from ff_cli.config import ConfigManager, FenixConfig, PluginConfig


class TestPluginConfig:
    """Test the PluginConfig class."""

    def test_plugin_config_creation(self):
        """Test creating a plugin config."""
        config = PluginConfig(
            version="1.0.0",
            source="git+https://example.com/plugin.git",
            installed_at="2025-01-01T00:00:00",
        )

        assert config.version == "1.0.0"
        assert config.source == "git+https://example.com/plugin.git"
        assert config.installed_at == "2025-01-01T00:00:00"

    def test_plugin_config_to_dict(self):
        """Test converting plugin config to dict."""
        config = PluginConfig(version="1.0.0", source="pypi")

        data = config.to_dict()
        assert data == {"version": "1.0.0", "source": "pypi", "installed_at": ""}


class TestFenixConfig:
    """Test the FenixConfig class."""

    def test_fenix_config_creation(self):
        """Test creating a Fenix config."""
        config = FenixConfig()
        assert config.plugins == {}
        assert config.settings == {}

    def test_fenix_config_with_data(self):
        """Test creating config with data."""
        plugin = PluginConfig("1.0", "pypi")
        config = FenixConfig(plugins={"test": plugin}, settings={"key": "value"})

        assert "test" in config.plugins
        assert config.plugins["test"] == plugin
        assert config.settings["key"] == "value"

    def test_fenix_config_to_dict(self):
        """Test converting config to dict."""
        plugin = PluginConfig("1.0", "pypi", "2025-01-01")
        config = FenixConfig(plugins={"test": plugin}, settings={"key": "value"})

        data = config.to_dict()
        assert "plugins" in data
        assert "test" in data["plugins"]
        assert data["plugins"]["test"]["version"] == "1.0"
        assert data["settings"]["key"] == "value"

    def test_fenix_config_from_dict(self):
        """Test creating config from dict."""
        data = {
            "plugins": {"test": {"version": "1.0", "source": "pypi", "installed_at": "2025-01-01"}},
            "settings": {"key": "value"},
        }

        config = FenixConfig.from_dict(data)
        assert "test" in config.plugins
        assert config.plugins["test"].version == "1.0"
        assert config.settings["key"] == "value"


class TestConfigManager:
    """Test the ConfigManager class."""

    def test_config_manager_creation(self):
        """Test creating a config manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "test_config"
            manager = ConfigManager(config_dir=config_dir)

            assert manager.config_dir == config_dir
            assert manager.config_file == config_dir / "config.toml"
            assert config_dir.exists()

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "test_config"
            manager = ConfigManager(config_dir=config_dir)

            # Add a plugin
            manager.add_plugin("test-plugin", "1.0.0", "pypi")

            # Set a setting
            manager.set_setting("test.key", "value")

            # Create new manager to test loading
            manager2 = ConfigManager(config_dir=config_dir)

            # Check plugin was loaded
            plugin = manager2.get_plugin_config("test-plugin")
            assert plugin is not None
            assert plugin.version == "1.0.0"
            assert plugin.source == "pypi"

            # Check setting was loaded
            assert manager2.get_setting("test.key") == "value"

    def test_add_and_remove_plugin(self):
        """Test adding and removing plugins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "test_config"
            manager = ConfigManager(config_dir=config_dir)

            # Add plugin
            manager.add_plugin("test", "1.0", "pypi")
            assert "test" in manager.list_plugins()

            # Remove plugin
            result = manager.remove_plugin("test")
            assert result is True
            assert "test" not in manager.list_plugins()

            # Remove non-existent plugin
            result = manager.remove_plugin("nonexistent")
            assert result is False

    def test_get_and_set_settings(self):
        """Test getting and setting configuration values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "test_config"
            manager = ConfigManager(config_dir=config_dir)

            # Set simple value
            manager.set_setting("key", "value")
            assert manager.get_setting("key") == "value"

            # Set nested value
            manager.set_setting("nested.key", "nested_value")
            assert manager.get_setting("nested.key") == "nested_value"

            # Get with default
            assert manager.get_setting("nonexistent", "default") == "default"

            # Set deeply nested
            manager.set_setting("a.b.c.d", "deep")
            assert manager.get_setting("a.b.c.d") == "deep"
