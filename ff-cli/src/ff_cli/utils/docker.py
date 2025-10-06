"""Docker utilities for managing containers with OrbStack support."""

import json
import os
import shlex
import socket
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ff_cli.branding import get_brand
from ff_cli.config import get_logger
from ff_cli.utils.common import console

logger = get_logger("docker")


class DockerManager:
    """Manages Docker containers and operations."""

    def __init__(self):
        """Initialize Docker manager."""
        self.docker_available = self.check_docker()
        self.orbstack = self.check_orbstack()

    def _run_docker(
        self,
        args: list[str],
        *,
        capture_output: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a docker CLI command and return the process result."""
        if not self.docker_available:
            raise RuntimeError("Docker is not available on this system")

        cmd = ["docker", *args]
        try:
            return subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
            )
        except subprocess.SubprocessError as exc:
            logger.error(f"Docker command failed ({cmd}): {exc}")
            raise

    @staticmethod
    def _parse_size(size_str: str) -> float:
        """Parse Docker size strings (e.g., '12.3kB') into bytes."""
        size_str = size_str.strip()
        if not size_str or size_str.lower() == "0b":
            return 0.0

        units = {
            "B": 1,
            "kB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "TB": 1024**4,
        }

        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    value = float(size_str[: -len(unit)].strip())
                    return value * multiplier
                except ValueError:
                    return 0.0
        try:
            return float(size_str)
        except ValueError:
            return 0.0

    def check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def check_orbstack(self) -> bool:
        """Check if OrbStack is being used."""
        home = Path.home()
        orbstack_socket = home / ".orbstack" / "run" / "docker.sock"

        # Check for OrbStack socket
        if orbstack_socket.exists():
            return True

        # Check Docker context
        if os.environ.get("DOCKER_CONTEXT"):
            context = os.environ["DOCKER_CONTEXT"].strip()
            return "orbstack" in context.lower()

        # Check docker context show
        try:
            result = subprocess.run(
                ["docker", "context", "show"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return "orbstack" in result.stdout.strip().lower()
        except Exception:
            pass

        return False

    def check_port_conflicts(self, ports: Iterable[str]) -> list[tuple[str, bool]]:
        """Detect whether requested host ports are already in use."""
        conflicts: list[tuple[str, bool]] = []
        for port_spec in ports:
            host_part = port_spec.split(":", 1)[0]
            host_part = host_part.split("/")[0]
            try:
                host_port = int(host_part)
            except ValueError:
                conflicts.append((port_spec, False))
                continue

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                in_use = sock.connect_ex(("127.0.0.1", host_port)) == 0
            conflicts.append((port_spec, in_use))
        return conflicts

    def get_docker_info(self) -> dict[str, Any]:
        """Get Docker daemon information."""
        info = {
            "available": self.docker_available,
            "orbstack": self.orbstack,
            "provider": "orbstack" if self.orbstack else "docker",
            "running": False,
        }

        if self.docker_available:
            try:
                # Get Docker version
                result = subprocess.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    info["version"] = result.stdout.strip()
                    info["status"] = "running"
                    info["running"] = True
                else:
                    info["status"] = "error"
                    info["version"] = "unknown"
            except Exception as e:
                logger.error(f"Error checking Docker status: {e}")
                info["status"] = "error"
                info["error"] = str(e)
        else:
            info["status"] = "not_available"

        return info

    def container_exists(self, name: str) -> bool:
        """Check if a container exists."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "-q", "-f", f"name=^{name}$"],
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except subprocess.SubprocessError:
            return False

    def is_running(self, name: str) -> bool:
        """Check if a container is running."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name=^{name}$"],
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except subprocess.SubprocessError:
            return False

    def start_container(self, name: str) -> bool:
        """Start an existing container."""
        try:
            result = subprocess.run(
                ["docker", "start", name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start container {name}: {e}")
            return False

    def stop_container(self, name: str, timeout: int = 10) -> bool:
        """Stop a running container."""
        try:
            result = subprocess.run(
                ["docker", "stop", "-t", str(timeout), name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to stop container {name}: {e}")
            return False

    def restart_container(self, name: str) -> bool:
        """Restart a container."""
        try:
            result = subprocess.run(
                ["docker", "restart", name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to restart container {name}: {e}")
            return False

    def remove_container(self, name: str, force: bool = False) -> bool:
        """Remove a container."""
        try:
            cmd = ["docker", "rm"]
            if force:
                cmd.append("-f")
            cmd.append(name)

            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to remove container {name}: {e}")
            return False

    def volume_exists(self, name: str) -> bool:
        """Check whether a named Docker volume exists."""
        try:
            result = self._run_docker(
                [
                    "volume",
                    "ls",
                    "--filter",
                    f"name=^{name}$",
                    "--format",
                    "{{.Name}}",
                ]
            )
        except RuntimeError:
            return False

        return name in result.stdout.strip().splitlines()

    def create_volume(self, name: str) -> bool:
        """Create a named Docker volume if it does not already exist."""
        if self.volume_exists(name):
            return True

        try:
            result = self._run_docker(["volume", "create", name])
            return result.returncode == 0
        except RuntimeError:
            return False

    def run_container(
        self,
        image: str,
        name: str | None = None,
        environment: dict[str, str] | None = None,
        volumes: dict[str, str] | None = None,
        ports: dict[str, str] | None = None,
        network: str | None = None,
        detach: bool = True,
        remove: bool = False,
        command: str | None = None,
    ) -> tuple[bool, str]:
        """Run a new container."""
        cmd = ["docker", "run"]

        if detach:
            cmd.append("-d")
        if remove:
            cmd.append("--rm")
        if name:
            cmd.extend(["--name", name])
        if network:
            cmd.extend(["--network", network])

        # Add environment variables
        if environment:
            for key, value in environment.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Add volume mounts
        if volumes:
            for host_path, container_path in volumes.items():
                cmd.extend(["-v", f"{host_path}:{container_path}"])

        # Add port mappings
        if ports:
            for host_port, container_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])

        cmd.append(image)

        if command:
            cmd.extend(command.split())

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr.strip()
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run container: {e}")
            return False, str(e)

    def run_container_from_config(self, config: Any) -> bool:
        """Run a container using a service configuration object."""
        cmd = ["run", "-d", "--name", config.container_name]

        if config.restart:
            cmd.extend(["--restart", config.restart])

        networks = list(config.networks or [])
        if networks:
            cmd.extend(["--network", networks[0]])

        for label, value in (config.labels or {}).items():
            cmd.extend(["--label", f"{label}={value}"])

        for key, value in (config.environment or {}).items():
            cmd.extend(["-e", f"{key}={value}"])

        for port_spec in config.ports or []:
            cmd.extend(["-p", port_spec])

        for volume_spec in config.volumes or []:
            cmd.extend(["-v", volume_spec])

        health = getattr(config, "healthcheck", None)
        if health:
            cmd.extend(["--health-cmd", " ".join(health.test)])
            if getattr(health, "interval", None):
                cmd.extend(["--health-interval", health.interval])
            if getattr(health, "timeout", None):
                cmd.extend(["--health-timeout", health.timeout])
            if getattr(health, "retries", None) is not None:
                cmd.extend(["--health-retries", str(health.retries)])
            if getattr(health, "start_period", None):
                cmd.extend(["--health-start-period", health.start_period])

        cmd.append(config.image)

        if config.command:
            if isinstance(config.command, str):
                cmd.extend(shlex.split(config.command))
            else:
                cmd.extend(list(config.command))

        try:
            result = self._run_docker(cmd)
            if result.returncode != 0:
                logger.error(f"Failed to run container {config.container_name}: {result.stderr}")
            return result.returncode == 0
        except RuntimeError:
            return False

    def exec_in_container(
        self, name: str, command: list[str] | str, interactive: bool = False
    ) -> str:
        """Execute a command in a running container."""
        cmd = ["docker", "exec"]
        if interactive:
            cmd.append("-it")
        cmd.append(name)

        if isinstance(command, str):
            cmd.extend(shlex.split(command))
        else:
            cmd.extend(command)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to exec in container {name}: {result.stderr}")
            return result.stdout if result.returncode == 0 else result.stderr
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to exec in container {name}: {e}")
            return str(e)

    def get_container_logs(
        self, name: str, tail: int | None = None, follow: bool = False
    ) -> Iterable[str]:
        """Stream container logs line by line."""
        cmd = ["docker", "logs"]
        if tail:
            cmd.extend(["--tail", str(tail)])
        if follow:
            cmd.append("-f")
        cmd.append(name)

        if follow:
            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
            except subprocess.SubprocessError as e:
                logger.error(f"Failed to get logs for {name}: {e}")
                return []

            if not process.stdout:
                return []

            def _iterator():
                try:
                    for line in process.stdout:
                        yield line.rstrip("\n")
                finally:
                    process.stdout.close()

            return _iterator()

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to get logs for {name}: {result.stderr}")
                return []
            return result.stdout.splitlines()
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to get logs for {name}: {e}")
            return []

    def network_exists(self, name: str) -> bool:
        """Check if a Docker network exists."""
        try:
            result = subprocess.run(
                ["docker", "network", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
            )
            networks = result.stdout.strip().split("\n")
            return name in networks
        except subprocess.SubprocessError:
            return False

    def create_network(self, name: str) -> bool:
        """Create a Docker network."""
        try:
            if self.network_exists(name):
                return True

            result = subprocess.run(
                ["docker", "network", "create", name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to create network {name}: {e}")
            return False

    def remove_network(self, name: str) -> bool:
        """Remove a Docker network."""
        try:
            result = subprocess.run(
                ["docker", "network", "rm", name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to remove network {name}: {e}")
            return False

    def connect_container_to_network(self, container: str, network: str) -> bool:
        """Connect an existing container to a network."""
        try:
            result = self._run_docker(["network", "connect", network, container])
            return result.returncode == 0
        except RuntimeError:
            return False

    def get_network_status(self, name: str) -> dict[str, Any]:
        """Return basic status information for a Docker network."""
        if not self.docker_available:
            return {"exists": False, "connected_containers": 0}

        try:
            result = self._run_docker(["network", "inspect", name, "--format", "{{json .}}"])
        except RuntimeError:
            return {"exists": False, "connected_containers": 0}

        if result.returncode != 0 or not result.stdout.strip():
            return {"exists": False, "connected_containers": 0}

        info = json.loads(result.stdout.strip())
        containers = info.get("Containers") or {}
        return {
            "exists": True,
            "connected_containers": len(containers),
            "driver": info.get("Driver", "unknown"),
        }

    def list_containers(self, all_containers: bool = False) -> list[dict[str, str]]:
        """List Docker containers."""
        cmd = ["docker", "ps", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"]
        if all_containers:
            cmd.append("-a")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            containers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        containers.append(
                            {
                                "name": parts[0],
                                "status": parts[1],
                                "image": parts[2],
                            }
                        )
            return containers
        except subprocess.SubprocessError:
            return []

    def get_all_brand_status(self) -> list[dict[str, Any]]:
        """Return status information for containers that belong to the current brand."""
        if not self.docker_available:
            return []

        brand = get_brand()
        filter_label = f"ff.brand={brand.cli_name}"

        try:
            base_list = self._run_docker(
                [
                    "ps",
                    "-a",
                    "--filter",
                    f"label={filter_label}",
                    "--format",
                    "{{.ID}}|{{.Names}}|{{.Status}}",
                ]
            )
        except RuntimeError:
            return []

        statuses: list[dict[str, Any]] = []
        for line in base_list.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            container_id, name, status_text = parts

            try:
                inspect_result = self._run_docker(["inspect", container_id])
            except RuntimeError:
                continue

            if inspect_result.returncode != 0 or not inspect_result.stdout.strip():
                continue

            data = json.loads(inspect_result.stdout)[0]
            state = data.get("State", {})
            running = state.get("Running", False)
            health = state.get("Health", {}).get("Status") if state.get("Health") else None
            labels = data.get("Config", {}).get("Labels", {}) or {}
            service_name = labels.get("com.docker.compose.service") or name
            ports: dict[str, str] = {}
            port_settings = data.get("NetworkSettings", {}).get("Ports") or {}
            for container_port, mappings in port_settings.items():
                if not mappings:
                    continue
                host_port = mappings[0].get("HostPort")
                if host_port:
                    ports[container_port] = host_port

            statuses.append(
                {
                    "id": container_id,
                    "name": name,
                    "service": service_name,
                    "status": status_text,
                    "running": running,
                    "health": health or ("healthy" if running else "none"),
                    "ports": ports,
                    "orbstack_domain": labels.get("dev.orbstack.domains", ""),
                    "labels": labels,
                    "exists": True,
                }
            )

        return statuses

    def list_brand_containers(self) -> list[dict[str, Any]]:
        """List containers scoped to the current brand."""
        return self.get_all_brand_status()

    def build_image(
        self, context: str, tag: str, dockerfile: str | None = None
    ) -> tuple[str, list[str]]:
        """Build a Docker image and return its ID alongside build logs."""
        cmd = ["build", "-t", tag]
        if dockerfile:
            cmd.extend(["-f", dockerfile])
        cmd.append(context)

        try:
            result = self._run_docker(cmd)
        except RuntimeError as exc:
            logger.error(f"Failed to build image {tag}: {exc}")
            return "", [str(exc)]

        logs = (result.stdout or "").splitlines()
        if result.stderr:
            logs.extend(result.stderr.splitlines())

        image_id = ""
        for line in reversed(logs):
            if "Successfully built" in line:
                image_id = line.split()[-1]
                break

        return image_id, logs

    def cleanup_unused(self) -> dict[str, float]:
        """Prune unused Docker resources for the current environment."""
        summary = {
            "containers_removed": 0,
            "volumes_removed": 0,
            "networks_removed": 0,
            "space_reclaimed": 0.0,
        }

        if not self.docker_available:
            return summary

        try:
            result = self._run_docker(["system", "prune", "-af", "--volumes"])
        except RuntimeError:
            return summary

        output = result.stdout or ""
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Deleted Containers:"):
                try:
                    summary["containers_removed"] = int(line.split(":", 1)[1].strip() or 0)
                except ValueError:
                    summary["containers_removed"] = 0
            elif line.startswith("Deleted Volumes:"):
                try:
                    summary["volumes_removed"] = int(line.split(":", 1)[1].strip() or 0)
                except ValueError:
                    summary["volumes_removed"] = 0
            elif line.startswith("Deleted Networks:"):
                try:
                    summary["networks_removed"] = int(line.split(":", 1)[1].strip() or 0)
                except ValueError:
                    summary["networks_removed"] = 0
            elif line.startswith("Total reclaimed space:"):
                size_str = line.split(":", 1)[1].strip()
                summary["space_reclaimed"] = self._parse_size(size_str)

        return summary

    def pull_image(self, image: str) -> bool:
        """Pull a Docker image."""
        try:
            console.print(f"[cyan]Pulling image {image}...[/cyan]")
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=False,  # Show progress
                text=True,
            )
            return result.returncode == 0
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to pull image {image}: {e}")
            return False
