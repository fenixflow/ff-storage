"""Scaffolding utilities for creating project structures from templates."""

import shutil
from pathlib import Path
from typing import Any

from jinja2 import Template
from rich.console import Console

from ff_cli.branding import get_brand
from ff_cli.config import get_logger

console = Console()
logger = get_logger("scaffold")


def render_template(template_str: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 template string with context.

    Args:
        template_str: Template string
        context: Context dictionary for rendering

    Returns:
        Rendered string
    """
    # Add brand context
    brand = get_brand()
    context["brand"] = brand
    context["cli_name"] = brand.cli_name
    context["cli_display_name"] = brand.cli_display_name
    context["company_name"] = brand.company_name
    context["plugin_entry_point"] = brand.plugin_entry_point

    template = Template(template_str)
    return template.render(**context)


def render_template_file(
    template_path: Path,
    context: dict[str, Any],
    output_path: Path | None = None,
) -> str:
    """Render a Jinja2 template file.

    Args:
        template_path: Path to template file
        context: Context dictionary
        output_path: Optional path to write output

    Returns:
        Rendered content
    """
    with open(template_path) as f:
        template_str = f.read()

    rendered = render_template(template_str, context)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(rendered)

    return rendered


def scaffold_directory(
    template_dir: Path,
    output_dir: Path,
    context: dict[str, Any],
    exclude_patterns: list[str] | None = None,
) -> bool:
    """Scaffold a directory structure from templates.

    Args:
        template_dir: Directory containing templates
        output_dir: Directory to create structure in
        context: Context for template rendering
        exclude_patterns: Patterns to exclude from copying

    Returns:
        True if successful
    """
    if not template_dir.exists():
        console.print(f"[red]Template directory not found: {template_dir}[/red]")
        return False

    # Add brand context
    brand = get_brand()
    context["brand"] = brand
    context["cli_name"] = brand.cli_name
    context["cli_display_name"] = brand.cli_display_name
    context["company_name"] = brand.company_name
    context["plugin_entry_point"] = brand.plugin_entry_point

    exclude_patterns = exclude_patterns or []

    try:
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Walk through template directory
        for root, _, files in template_dir.walk():
            # Calculate relative path
            rel_root = root.relative_to(template_dir)

            # Process directory names (might be templates)
            output_root = output_dir / rel_root
            if "__" in str(rel_root):
                # Replace template variables in path
                path_str = str(rel_root)
                for key, value in context.items():
                    path_str = path_str.replace(f"__{key}__", str(value))
                output_root = output_dir / Path(path_str)

            output_root.mkdir(parents=True, exist_ok=True)

            # Process files
            for file in files:
                # Skip excluded patterns
                if any(pattern in file for pattern in exclude_patterns):
                    continue

                template_path = root / file
                output_file = file

                # Handle .j2 template files
                if file.endswith(".j2"):
                    output_file = file[:-3]  # Remove .j2 extension

                    # Replace template variables in filename
                    for key, value in context.items():
                        output_file = output_file.replace(f"__{key}__", str(value))

                    output_path = output_root / output_file

                    # Render template
                    render_template_file(template_path, context, output_path)
                    logger.info(f"Rendered template: {output_path}")

                else:
                    # Replace template variables in filename
                    for key, value in context.items():
                        output_file = output_file.replace(f"__{key}__", str(value))

                    output_path = output_root / output_file

                    # Copy file as-is
                    shutil.copy2(template_path, output_path)
                    logger.info(f"Copied file: {output_path}")

        console.print(f"[green]✅ Scaffolded project in {output_dir}[/green]")
        return True

    except Exception as e:
        logger.error(f"Failed to scaffold directory: {e}")
        console.print(f"[red]Failed to scaffold: {e}[/red]")
        return False


def create_file_from_template(
    template_str: str,
    output_path: Path,
    context: dict[str, Any],
    overwrite: bool = False,
) -> bool:
    """Create a file from a template string.

    Args:
        template_str: Template string
        output_path: Path to output file
        context: Context for rendering
        overwrite: Whether to overwrite existing file

    Returns:
        True if successful
    """
    if output_path.exists() and not overwrite:
        response = console.input(f"[yellow]File {output_path} exists. Overwrite? [y/N]: [/yellow]")
        if response.lower() != "y":
            return False

    try:
        # Render template
        content = render_template(template_str, context)

        # Create parent directories
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(output_path, "w") as f:
            f.write(content)

        console.print(f"[green]Created {output_path}[/green]")
        return True

    except Exception as e:
        logger.error(f"Failed to create file from template: {e}")
        console.print(f"[red]Failed to create file: {e}[/red]")
        return False


def get_templates_dir() -> Path:
    """Get the templates directory path.

    Returns:
        Path to templates directory
    """
    # Look for templates in the package
    import ff_cli

    package_dir = Path(ff_cli.__file__).parent
    return package_dir / "templates"


def list_available_templates() -> list[str]:
    """List available template directories.

    Returns:
        List of template names
    """
    templates_dir = get_templates_dir()
    if not templates_dir.exists():
        return []

    templates = []
    for item in templates_dir.iterdir():
        if item.is_dir() and not item.name.startswith("__"):
            templates.append(item.name)

    return templates


def scaffold_from_template(
    template_name: str,
    output_dir: Path,
    context: dict[str, Any],
) -> bool:
    """Scaffold a project from a named template.

    Args:
        template_name: Name of the template
        output_dir: Output directory
        context: Context for rendering

    Returns:
        True if successful
    """
    templates_dir = get_templates_dir()
    template_dir = templates_dir / template_name

    if not template_dir.exists():
        console.print(f"[red]Template '{template_name}' not found[/red]")
        console.print(f"Available templates: {', '.join(list_available_templates())}")
        return False

    return scaffold_directory(template_dir, output_dir, context)


def create_gitignore(output_dir: Path) -> bool:
    """Create a standard .gitignore file.

    Args:
        output_dir: Directory to create .gitignore in

    Returns:
        True if successful
    """
    gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv
.env
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Testing
.coverage
.pytest_cache/
htmlcov/

# Logs
*.log

# Local config
local_config.yaml
"""

    try:
        gitignore_path = output_dir / ".gitignore"
        with open(gitignore_path, "w") as f:
            f.write(gitignore_content)
        return True
    except Exception as e:
        logger.error(f"Failed to create .gitignore: {e}")
        return False
