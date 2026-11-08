# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-11-13 — The chemotion/main milestones M0–M7, ported onto the 401.0 line

The work packages from `MILESTONES.md`, developed on `chemotion/main` against unreleased ELN `main`,
cherry-picked onto the 401.0 line (one commit each, `cherry picked from` in each message) and
tested against the released ELN v4.0.1. See `MISSING_FEATURES.md` for the status per feature.

- **M0** element registry, payload capture tool, deletion. Not ported: the p2d test stack (this
  line tests against tagged releases only).
- **M1** comments, private notes, versions with revert, short-label lookup, user labels on
  wellplates and research plans. Screens and the rest of the label work were already in 401.0.
- **M2** molecules from molfiles, server-side splits, mixture components, structure search, sample
  import, literature, CAS/suggestions/scheme SVG.
- **M3** reports and table exports, inbox assignment, attachment management, analyses-only save,
  collection/research plan metadata, take ownership, wellplate and research plan extras, text
  templates, gate transfer. Collection ZIP export/import was already in 401.0.
- **M4** vessels, safety data sheets and inventory labels; splits of device descriptions and SBMM
  samples. Cell lines, device descriptions, SBMM samples and chemical records keep their 401.0 API.
- **M5** spectra, measurements, image annotation, NMR simulation/prediction/compute tasks, sample tasks.
- **M6** template deletion/revisions/download, element export, LabIMotion Hub, generic splits and
  variations, MTT requests, OLS terms.
- **M7** profile, 2FA status and API tokens, counters, user/group/device/system administration,
  SciFinder-n.

Server issues found on ELN `main` while building these (worked around or guarded in the client): `/public/token`
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
