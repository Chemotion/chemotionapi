# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-06-30 — Self-contained seeded integration environment

- `tests/test_config/compose.yml` boots a live ELN + Postgres on port 3579.
- Pre-seeded DB (`tests/data/test.sql`): API/ADM/MM users plus sample data.
- `conftest.py` runs `tests/data/setup_chemotion_db.sh` when `NO_SETUP=0`: boots the stack, resets the DB from the seed, waits for the `**SUCCESS**` marker.
- Replaces the old root `test_config/` (manual `.env`, no committed seed), which is deleted.

## 2026-06-02 — Migrate to uv + just, target Python 3.14

- `pyproject.toml`: uv-managed deps, Python ≥ 3.14.
- `justfile`: reproducible dev tasks (build, test, lint, coverage).
- Removed the `requirements.txt` files.

## 2026-06-01 — Remove build artifacts, generated dumps and stale configs

- Housekeeping: deleted `.gitlab-ci.yml`, `.readthedocs.yaml`, `.tool-versions`, `chemotionapi.iml`, `config.json.sample` and the `dist/` wheels.
