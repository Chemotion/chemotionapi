# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-11-07 – 2026-11-08 — Milestones M0–M7: the web UI's features in the client

Work packages from `MILESTONES.md`, one commit each (see `MISSING_FEATURES.md` for the status per
feature):

- **M0** element registry, payload capture tool, p2d test stack (`tests/test_config/p2d.sh`), deletion.
- **M1** screens, comments, private notes, versions with revert, user labels, short-label lookup.
- **M2** molecules from molfiles, server-side splits, mixture components, structure search (and a
  fix for the broken advanced search), sample import, literature, CAS/suggestions/scheme SVG.
- **M3** collection export/import, reports and table exports, inbox assignment, attachment
  management, analyses-only save, collection/research plan metadata, take ownership, wellplate
  and research plan extras, text templates, gate transfer.
- **M4** cell lines, vessels, device descriptions, SBMM samples, chemicals and inventory.
- **M5** spectra, measurements, image annotation, NMR simulation/prediction/compute tasks, sample tasks.
- **M6** template deletion/revisions/download, element export, LabIMotion Hub, generic splits and
  variations, MTT requests, OLS terms.
- **M7** profile, 2FA status and API tokens, counters, user/group/device/system administration,
  SciFinder-n.

Server issues found on ELN `main` along the way (worked around or guarded in the client): `/public/token`
ignores 2FA; `DELETE /profiles` deletes any path; vessel updates, measurement deletion and MTT wellplate
lookups lack permission checks; `research_plans/linked` leaks names; `DELETE`/`PUT /containers/:id`
refuse owners; prediction routes always 500; `olsEnableDisable` empties term lists without imported terms.

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
