# Contributing

Thank you for your interest in contributing to netbox-wdm!

## Development Setup

This project uses a Docker devcontainer. Open the repo in VS Code with the Dev Containers extension, or use the CLI:

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash
```

NetBox source is available at `/opt/netbox` inside the container.

## Running Tests

```bash
cd /opt/netbox/netbox
DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest /opt/netbox-wdm/tests/ -v
```

## Linting and Formatting

```bash
ruff check netbox_wdm/
ruff format netbox_wdm/
```

## Building the Frontend

```bash
cd netbox_wdm/static/netbox_wdm
npm install
npm run build        # production build
npm run watch        # dev mode with auto-rebuild
npm run typecheck    # TypeScript type checking
```

## Making Changes

1. Fork the repo and create a branch from `main`.
2. Make your changes. Follow existing code style — ruff enforces it.
3. Add or update tests for any new functionality.
4. Run the full test suite and linter before submitting.
5. Open a pull request against `main`.

## Code Style

- Python: ruff with the project config (line length 120, Python 3.12 target)
- TypeScript: strict mode, one file per component, types in separate `-types.ts` files
- CSS: use `--wdm-*` custom properties, never hardcode colors (see `docs/developer/style-guide.md`)
- Migrations: always generate via `python manage.py makemigrations netbox_wdm`

## Reporting Issues

Open an issue on GitHub with:
- NetBox version
- Plugin version
- Steps to reproduce
- Expected vs actual behavior
