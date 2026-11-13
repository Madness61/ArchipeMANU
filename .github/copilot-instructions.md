# Copilot instructions for AP YAML Hub

## Project context

This repository is a Flask-based Archipelago YAML hub: it lets a group manage APWorlds, generated YAML templates, per-user overrides, sessions, and output generation. The app depends on a local Archipelago checkout and populates schema data from installed worlds before it can render forms or generate seeds.

Most work touches the interaction between the Flask app and Archipelago itself, not just the UI templates. If a change affects option parsing, world versions, or seed generation, check both the web layer and the Archipelago bridge code.

## Quick start

Windows setup (from the repo root):

```powershell
.\setup.ps1 -ImportFrom "C:\ProgramData\Archipelago\custom_worlds"
.\start.ps1
```

The Windows launcher binds to `0.0.0.0:8080` by default for LAN/Hamachi access;
http://127.0.0.1:8080 also works on the host. Restrict access to the host with:

```powershell
.\start.ps1 -LocalOnly
```

The default local Archipelago install lives under `%USERPROFILE%\.ap-yaml-hub`; the app reads environment overrides such as `AP_HOME`, `HUB_DATA`, and `HUB_PASSWORD` from `hub/config.py`.

## Build, test, and validation commands

There is no separate lint task in this repository. The project’s validation flow is the `unittest` suite used in CI.

Run the full suite:

```powershell
python -m unittest discover -s tests -v
```

Or, in the project’s configured Archipelago venv:

```powershell
& "$env:USERPROFILE\.ap-yaml-hub\venv\Scripts\python.exe" -m unittest discover tests
```

Run a single test module or case:

```powershell
python -m unittest tests.test_mvp
python -m unittest tests.test_yamlgen.TestYamlGen
```

The GitHub Actions workflow in [.github/workflows/tests.yml](../.github/workflows/tests.yml) confirms this is the expected validation command for PRs and feature branches.

## High-level architecture

- `hub/app.py` is the Flask application. It defines auth, CSRF handling, admin routes, session management, and the page-level orchestration for templates and generation.
- `hub/db.py` is the SQLite layer. It centralizes schema setup and exposes `db.query()` / `db.execute()` for the rest of the app instead of direct database access patterns.
- `hub/config.py` holds the environment-driven configuration and paths: Archipelago source, venv, `data/`, and the generated working directories.
- `hub/yamlgen.py` is the option-logic core. It normalizes AP option values, layers defaults/template/user overrides, sanitizes slot names, and serializes YAML output.
- `hub/ap_bridge.py` is the Archipelago integration boundary. It manages APWorld uploads/activation, verifies trusted custom worlds, extracts option schemas from APWorlds, starts generation, and caches schema files.
- `ap_runner.py` runs inside the Archipelago source tree. It introspects installed APWorlds and writes JSON schema metadata into the hub’s `data/schemas/` folder; it also drives generation for actual seed creation.
- `data/` is runtime state, not source code: SQLite database, APWorld archives, extracted schemas, and generated session output all live there.
- `tests/` contains `unittest` coverage for the core behaviors, especially YAML generation and APWorld metadata handling.

The application treats “current APWorld state” as a first-class concern: if a game isn’t available in the local schema cache or APWorld version registry, the UI can’t render a valid template or generate a result.

## Key conventions in this codebase

- Prefer the project’s config and DB helpers over ad hoc filesystem or SQL code.
  - Use `config.*` paths for data and AP install locations.
  - Use `db.query()` / `db.execute()` rather than creating new SQLite access patterns in route handlers.
- Treat option values as deltas from AP defaults. The layering order is intentionally: AP default < template < personal overrides. See `yamlgen.layer()` and the comment in `hub/yamlgen.py`.
- World extraction and generation are serialized with `ap_bridge.ap_lock` because both operations rewrite Archipelago’s custom world state and must not race each other.
- Custom APWorld execution is explicitly not sandboxed. The code requires trusted local sources and environment opt-in via `HUB_TRUSTED_APWORLDS=1` before injecting uploaded worlds into Archipelago.
- Slot names are normalized and de-duped in the same way as the UI expects: `clean_slot_name()` strips unsafe characters and `assign_slot_names()` appends numbered suffixes when duplicates exist.
- The project is intentionally Windows-first and PowerShell-oriented; repo scripts and default paths are written around Windows install locations, but the Python app itself remains cross-platform where practical.
- When changing APWorld logic, verify the same behavior in both the schema extraction path (`ap_runner.py`) and the YAML/export path (`hub/yamlgen.py`); those two layers must agree on option names, types, and defaults.

## Repository-specific guidance

- Do not assume a simple “web app only” change is isolated to templates or routes; APWorld and schema logic are part of the runtime contract.
- Keep changes compatible with the `data/` runtime layout and the `AP_HOME`/`HUB_DATA` environment variables rather than hard-coding local paths.
- Preserve the project’s existing `unittest` style; new behavior should ideally be covered in the existing tests under `tests/`.
- If you need to inspect or modify APWorld versioning or active-world selection, start in `hub/ap_bridge.py` and the APWorld library helpers before touching routes.
