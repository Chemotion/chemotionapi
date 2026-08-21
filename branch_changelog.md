# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-07-02 — Collection trees for native-ZIP import + producer marker

- `import_export_zip` now rebuilds the exported **collection tree** (bundles supported): one `OfflineCollection` per collection, elements scoped via the `CollectionsSample`/`CollectionsReaction` join tables; several top-level collections group under a synthetic root. Import only — writing the native format stays with the ELN GUI.
- Every exported crate embeds a producer marker: a `SoftwareApplication` node named `chemotion-api` (with version) referenced by the descriptor's `sdPublisher`. Grep: `"name": "chemotion-api"` in `ro-crate-metadata.json`.
- `import_eln` accepts only our own crates by default (foreign `.eln` import is deferred); `allow_foreign=True` opens them best-effort. `ElnCrate.producer` / `.is_chemotion_api` expose the marker.
- Fix: `_OfflineResponse` lacked `close()`, so archived attachment payloads were skipped during offline export.

>>>>>>> e0eb847 (feat: collection trees for native-ZIP import + chemotion-api producer marker in .eln)
## 2026-07-02 — `.eln` importer

- `Instance.import_eln(path)` / `chemotion_api.offline.import_eln` opens a `.eln` (ZIP or extracted crate dir) and exposes it as navigable objects: `ElnCrate` (root, datasets, files, authors, `read_file`) / `ElnDataset` (kind, files, sub-datasets) / `ElnFile` (`read()`/`extract()`).
- Zip-slip-safe payload access; metadata-only File nodes raise `FileNotFoundError` on `read()` instead of failing silently.
- ORCID/ROR authors round-trip back into `Author`/`AuthorAffiliation` objects.
- Round-trip tested against our own exporter output.

## 2026-07-01 — Gated coverage reporting and offline-suite expansion

- Coverage gate via `fail_under` in `pyproject.toml` (54% then; since raised to 55%); CI posts the coverage summary and uploads `coverage.xml` as an artifact.
- New unit tests: `tests/unit/test_pure_helpers.py` and `tests/unit/test_research_plan_body.py`.

## 2026-07-01 — GitHub Actions — offline gate and nightly integration

- New `.github/workflows/ci.yml`: ruff lint, mypy, offline test suite and docs build on pushes to main and PRs.
- New `.github/workflows/integration.yml`: nightly integration run against the seeded docker stack.

=======
>>>>>>> 71940e6 (docs: Sphinx site, user-facing README and CHANGELOG)
## 2026-06-30 — Docs: Sphinx site, user-facing README and CHANGELOG

- `docs/` site: Sphinx build with cross-references and autodoc for main entry points (theme: `sphinx_rtd_theme`).
- User-facing `README.md` and `CHANGELOG.md` (newest-first, dates, summaries).

>>>>>>> 056242d (feat: .eln importer — read RO-Crate archives back into Python objects)
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
