# CLI Branding Guide

The CLI determines its branding dynamically from both the executable name that
launches it and the configuration declared in `BrandConfig`.

## Default behaviour

* Installing the package exposes a single `fenix` entry point.
* Running commands through that binary uses the built-in `fenix` branding
  (config files stored in `~/.fenix`, network name `fenix-network`, plugin entry
  point `fenix.plugins`, etc.).

## Interactive configuration

Run the built-in branding commands to inspect or override the defaults:

```bash
fenix branding show
fenix branding configure
```

The wizard persists your answers to `~/.ff-cli/branding.toml`. Future invocations
of the CLI (regardless of the executable name) will use those values until you
run `fenix branding reset`. On POSIX systems you can also ask the wizard to
create a helper command in `~/.local/bin`.

## Creating a new brand command

1. Define a `BrandConfig` (either interactively as above or by editing
   `src/ff_cli/branding.py` / providing a TOML file) with your brand's CLI name,
   display name, Docker identifiers, and plugin entry-point group.
2. Publish or install a thin package that exposes a console script pointing at
   `ff_cli.main:run` under your command name, for example:

   ```toml
   [project.scripts]
   mybrand = "ff_cli.main:run"
   ```

3. Invoke the CLI via the new command (`mybrand status`). All prompts, config
   directories, plugin scaffolding, and Docker naming will use your brand.

## Plugin authoring

The `fenix plugins create` workflow automatically picks up the active brand when
scaffolding a plugin, so the generated `pyproject.toml`, README, and CLI help use
your command namespace (e.g. `mybrand plugins install`).
