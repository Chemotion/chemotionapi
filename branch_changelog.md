# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-06-09 — Typed fields and a schema validation registry

- `chemotion_api.labImotion.items.{layer, fields, …}` typed; `.value` properties on field types.
- `SchemaRegistry` (jsonschema validator store, singleton) enables runtime property validation before model construction.

## 2026-06-08 — Modernize the core plumbing

- `Instance`, `ElementManager`, `User` strongly typed.
- `Connection` configurable with `verify_ssl`, auto-retrying transient failures (HTTP 502/503/504, idempotent methods only).
- `SchemaManager` decouples version/schema metadata from request logic.

## 2026-06-02 — Migrate to uv + just, target Python 3.14

- `pyproject.toml`: uv-managed deps, Python ≥ 3.14.
- `justfile`: reproducible dev tasks (build, test, lint, coverage).
- Removed the `requirements.txt` files.

## 2026-06-01 — Remove build artifacts, generated dumps and stale configs

- Housekeeping: deleted `.gitlab-ci.yml`, `.readthedocs.yaml`, `.tool-versions`, `chemotionapi.iml`, `config.json.sample` and the `dist/` wheels.
