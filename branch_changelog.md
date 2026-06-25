# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-06-25 — Explicit ORCID + ROR authorship replaces the logged-in-user default

- `Author` and `AuthorAffiliation` capture full identity (ORCID, name) and org identity (ROR, name) respectively.
- Export no longer defaults to the logged-in user; `export_eln` raises `ValueError` unless authors with ORCID + ROR affiliations are supplied (`validate_authors`).

## 2026-06-22 — RO-Crate 1.1 .eln exporter (logged-in user as author)

- `Collection.export_eln(...)` bundles a collection + its elements as a ZIP containing RO-Crate 1.1 metadata (crate descriptor, datasets per element type, file payloads).
- Offline-capable: the RO-Crate JSON-LD context is vendored (`chemotion_api/data/ro-crate-context.jsonld`), so serialization needs no network access.

## 2026-06-18 — Typed element layer with chem-dcat-ap mapping

- `Sample.to_dcat_ap()` / `Reaction.to_dcat_ap()` map element JSON to chem-dcat-ap objects.
- Reaction: starting materials/reactants/products/solvents with roles and quantities; conditions (temperature, duration) as typed properties.
- Sample: molecule identifiers (SMILES/InChI) and quantities (mass, volume, amount, density, molarity) as QUDT-typed values.

## 2026-06-15 — CHMO term resolution via embedded codes and cached OLS lookup

- `chemotion_api/ontology/ols_lookup.py` + `OntologyRegistry` resolve CHMO terms from the code embedded in an analysis' `extended_metadata.kind`, hitting the OLS API on first use with caching; an embedded fallback mapping covers offline use.

## 2026-06-11 — Pydantic v2 data models for samples, reactions and molecules

- `chemotion_api/models.py` with Pydantic v2 models (`ConfigDict(extra='allow')` so unknown server fields pass through) for chem-dcat-ap aware fields (SMILES, InChI, density, stoichiometry).
- Replaces inline dict-based schema handling; proper IDE autocomplete.

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
