"""Tests for the plugin manager."""

from unittest.mock import MagicMock, Mock, patch

import typer
from ff_cli.plugin_manager import Plugin, PluginManager


class TestPlugin:
    """Test the Plugin class."""

    def test_plugin_creation(self):
        """Test creating a plugin instance."""
        plugin = Plugin(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            module_path="test_module:plugin_func",
        )

        assert plugin.name == "test-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Test plugin"
        assert plugin.module_path == "test_module:plugin_func"
        assert plugin.app is None
        assert plugin.source == "unknown"

    def test_plugin_load_success(self):
        """Test successfully loading a plugin."""
        plugin = Plugin(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            module_path="test_module:plugin_func",
        )

        mock_app = typer.Typer()
        mock_func = Mock(return_value=mock_app)

        with patch("builtins.__import__") as mock_import:
            mock_module = MagicMock()
            mock_module.plugin_func = mock_func
            mock_import.return_value = mock_module

            loaded_app = plugin.load()

            assert loaded_app == mock_app
            assert plugin.app == mock_app
            mock_func.assert_called_once()

    def test_plugin_load_cached(self):
        """Test that loading a plugin twice returns cached app."""
        plugin = Plugin(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            module_path="test_module:plugin_func",
        )

        mock_app = typer.Typer()
        plugin.app = mock_app

        loaded_app = plugin.load()
        assert loaded_app == mock_app


class TestPluginManager:
    """Test the PluginManager class."""

    @patch("ff_cli.plugin_manager.PluginManager._discover_plugins")
    def test_manager_creation(self, mock_discover):
        """Test creating a plugin manager."""
        manager = PluginManager()
        mock_discover.assert_called_once()
        assert manager.plugins == {}

    def test_get_plugin(self):
        """Test getting a plugin by name."""
        manager = PluginManager()
        plugin = Plugin(
            name="test-plugin", version="1.0.0", description="Test", module_path="test:plugin"
        )
        manager.plugins["test-plugin"] = plugin

        retrieved = manager.get_plugin("test-plugin")
        assert retrieved == plugin

        none_plugin = manager.get_plugin("nonexistent")
        assert none_plugin is None

    def test_list_plugins(self):
        """Test listing all plugins."""
        manager = PluginManager()
        plugin1 = Plugin("plugin1", "1.0", "First", "mod1:func")
        plugin2 = Plugin("plugin2", "2.0", "Second", "mod2:func")

        manager.plugins = {"plugin1": plugin1, "plugin2": plugin2}

        plugins = manager.list_plugins()
        assert len(plugins) == 2
        assert plugin1 in plugins
        assert plugin2 in plugins

    def test_load_plugin(self):
        """Test loading a specific plugin."""
        manager = PluginManager()
        mock_app = typer.Typer()
        plugin = Plugin("test", "1.0", "Test", "test:plugin")
        plugin.app = mock_app

        manager.plugins["test"] = plugin

        loaded = manager.load_plugin("test")
        assert loaded == mock_app

        none_loaded = manager.load_plugin("nonexistent")
        assert none_loaded is None

    @patch("ff_cli.plugin_manager.console")
    def test_register_plugin_commands(self, mock_console):
        """Test registering plugin commands to main app."""
        manager = PluginManager()
        main_app = typer.Typer()

        # Create mock plugins
        mock_app1 = typer.Typer()
        plugin1 = Plugin("plugin1", "1.0", "First plugin", "mod1:func")
        plugin1.app = mock_app1

        mock_app2 = typer.Typer()
        plugin2 = Plugin("plugin2", "2.0", "Second plugin", "mod2:func")
        plugin2.app = mock_app2

        manager.plugins = {"plugin1": plugin1, "plugin2": plugin2}

        with patch.object(main_app, "add_typer") as mock_add:
            manager.register_plugin_commands(main_app)

            assert mock_add.call_count == 2
            mock_add.assert_any_call(mock_app1, name="plugin1", help="First plugin")
            mock_add.assert_any_call(mock_app2, name="plugin2", help="Second plugin")
