"""Helpers for managing plugin-provided script definitions."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from ff_cli.config import get_logger, get_settings
from ff_cli.utils.editor import open_in_editor

logger = get_logger("plugin_scripts")


@dataclass
class ScriptDefinition:
    """Declarative description of a plugin script."""

    name: str
    description: str
    command: Sequence[str]
    raw_command: str
    cwd: Path
    env: dict[str, str]
    path: Path


@dataclass
class ScriptStatus:
    """Runtime status for a plugin script."""

    name: str
    running: bool
    pid: int | None
    command: str
    description: str


class ScriptManager:
    """Discover, run, and track scripts distributed by plugins."""

    def __init__(self, plugin_name: str, scripts_dir: Path):
        self.plugin_name = plugin_name
        self.scripts_dir = scripts_dir
        settings = get_settings()
        self.state_dir = settings.config_dir / "scripts" / "plugins" / plugin_name
        self.state_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def list_definitions(self) -> list[ScriptDefinition]:
        """Return all valid script definitions bundled with the plugin."""
        if not self.scripts_dir.exists():
            return []

        definitions: list[ScriptDefinition] = []
        for path in sorted(self.scripts_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Could not load script definition %s: %s", path, exc)
                continue

            name = data.get("name") or path.stem
            raw_command = data.get("command")
            if not raw_command:
                logger.warning("Script %s missing command", path)
                continue

            command = self._normalise_command(raw_command)
            description = data.get("description", name)
            cwd_value = Path(data.get("cwd", "."))
            if not cwd_value.is_absolute():
                cwd = (self.scripts_dir.parent / cwd_value).resolve()
            else:
                cwd = cwd_value
            env = {str(k): str(v) for k, v in (data.get("env") or {}).items()}

            definitions.append(
                ScriptDefinition(
                    name=name,
                    description=description,
                    command=command,
                    raw_command=(
                        raw_command if isinstance(raw_command, str) else " ".join(raw_command)
                    ),
                    cwd=cwd,
                    env=env,
                    path=path,
                )
            )
        return definitions

    def get_definition(self, name: str) -> ScriptDefinition | None:
        for definition in self.list_definitions():
            if definition.name == name:
                return definition
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def run(
        self, name: str, *, detach: bool = True, env: dict[str, str] | None = None
    ) -> int | None:
        """Execute a script definition."""
        definition = self.get_definition(name)
        if not definition:
            raise ValueError(f"Script '{name}' not found")

        combined_env = os.environ.copy()
        combined_env.update(definition.env)
        if env:
            combined_env.update({str(k): str(v) for k, v in env.items()})

        if detach:
            process = subprocess.Popen(
                definition.command,
                cwd=definition.cwd,
                env=combined_env,
            )
            self._write_state(name, process.pid)
            logger.info("Started script %s with PID %s", name, process.pid)
            return process.pid

        result = subprocess.run(
            definition.command,
            cwd=definition.cwd,
            env=combined_env,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, definition.command)
        return None

    def stop(self, name: str, *, force: bool = False) -> bool:
        """Stop a running script if it is tracked."""
        state = self._read_state(name)
        if not state:
            return False

        pid = state.get("pid")
        if not pid:
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            if force:
                time.sleep(0.25)
                if self._is_running(pid):
                    os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            self._delete_state(name)

        return True

    # ------------------------------------------------------------------
    # Status & editing
    # ------------------------------------------------------------------
    def status(self, name: str | None = None) -> list[ScriptStatus]:
        statuses: list[ScriptStatus] = []
        for definition in self.list_definitions():
            if name and definition.name != name:
                continue
            pid = self._state_pid(definition.name)
            running = pid is not None and self._is_running(pid)
            if pid is not None and not running:
                self._delete_state(definition.name)
                pid = None
            statuses.append(
                ScriptStatus(
                    name=definition.name,
                    running=running,
                    pid=pid,
                    command=definition.raw_command,
                    description=definition.description,
                )
            )
        return statuses

    def edit(self, name: str) -> Path:
        """Open (and bootstrap) the script YAML in the configured editor."""
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

        yaml_path = self.scripts_dir / f"{name}.yaml"
        if not yaml_path.exists():
            yaml_path.write_text(
                f"""name: {name}
description: Describe what this script does
command: uv run python scripts/{name}.py
cwd: .
env: {{}}
"""
            )

        script_path = self.scripts_dir / f"{name}.py"
        if not script_path.exists():
            script_path.write_text(
                f"""#!/usr/bin/env python3

def main() -> None:
    print("Hello from {name} script!")


if __name__ == "__main__":
    main()
"""
            )
            script_path.chmod(script_path.stat().st_mode | 0o111)

        open_in_editor(yaml_path)
        return yaml_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _state_path(self, name: str) -> Path:
        return self.state_dir / f"{name}.json"

    def _write_state(self, name: str, pid: int) -> None:
        data = {"pid": pid, "timestamp": time.time()}
        self._state_path(name).write_text(json.dumps(data))

    def _read_state(self, name: str) -> dict[str, int] | None:
        path = self._state_path(name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
            return None

    def _delete_state(self, name: str) -> None:
        self._state_path(name).unlink(missing_ok=True)

    def _state_pid(self, name: str) -> int | None:
        state = self._read_state(name)
        if not state:
            return None
        return state.get("pid")

    def _is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _normalise_command(self, command: object) -> Sequence[str]:
        if isinstance(command, str):
            return shlex.split(command)
        if isinstance(command, list | tuple):
            return [str(part) for part in command]
        raise TypeError("command must be a string or list")
