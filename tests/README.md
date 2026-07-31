# Tests

The suite is split by **memory footprint** and **dependencies** so the fast offline checks run
anywhere, while the heavy and server-dependent tests are opt-in.

## Layout

- **`tests/unit/`** — offline, no live server, no pyshacl (~1 s for the whole subset). Mostly
  pure-logic tests (Pydantic models, the ontology registry + `.eln` patch helper, the
  `Affiliation` model, `PropertyDict`, author-node construction), plus a handful of
  `heavy`-marked tests that exercise full `export_eln` RO-Crate serialization
  (offline ingest, `.eln` round-trip, typing enrichment).
- **`tests/*.py`** (top level) — everything else:
  - `@pytest.mark.integration` — needs a live Chemotion server/DB (auto-applied to any test using the
    `logged_in_instance` / `instance_with_*` fixtures).
  - `@pytest.mark.heavy` — memory-heavy *offline* tests: a full `export_eln` (rdflib JSON-LD
    serialization against the 2627-term RO-Crate context) or pyshacl validation over the 262 KB shapes.
    Fine individually (~60 MB each); run them one file at a time rather than all at once.

## Running

The **default** (`addopts` in `pytest.ini`) runs **all offline tests, memory-safe**: `-m "not
integration" --forked`. `--forked` (from `pytest-forked`) runs each test in its own subprocess
*serially*, so peak memory stays at ~one test's worth and a runaway test dies alone instead of
OOM-killing the whole run. Integration (live-server) tests are excluded by default because they need a
server; that combo — heavy export **+** live server in one process — is what OOM-killed past runs.

```bash
# Default: ALL offline tests (incl. heavy export/pyshacl), each isolated → memory-safe. No server:
.venv/bin/python -m pytest tests -q

# Pure-logic unit subset only (fastest; CI runs the full offline suite via `just check`):
.venv/bin/python -m pytest tests/unit -q

# Skip the fork overhead (single process; only when memory is known-bounded).
# addopts must be overridden too, since it carries the --forked flag:
.venv/bin/python -m pytest tests -q -o addopts='-m "not integration"'

# One heavy offline test on its own (CLI -m overrides the default filter):
.venv/bin/python -m pytest tests/test_shacl_conformance.py -m heavy -q

# Integration suite — self-contained: NO_SETUP=0 boots the docker stack in tests/test_config/,
# resets the DB from the committed seed (tests/data/test.sql) and waits for the ELN.
# Docker is the only requirement; defaults (port 3579, seed users) live in conftest.py.
NO_SETUP=0 .venv/bin/python -m pytest tests -m integration -q

# Against an already-running/external instance instead, skip the setup and override via env:
ELN_URL=http://... ELN_USER=... ELN_PASS=... NO_SETUP=1 \
.venv/bin/python -m pytest tests -m integration -q
```

See [test_config/README.md](./test_config/README.md) for the stack and seed-user details.
A fresh seed reset per session matters: the tests mutate the instance (uploaded generic
templates, collections), and some assertions rely on the seed's state.

## Notes on memory (why past runs OOM'd, and what's fixed)

- **Root cause found & fixed:** `test_shacl_conformance.py` passed the 262 KB SHACL shapes *file path*
  to `pyshacl.validate` on every call, which re-parsed and re-processed the shapes each time; that
  memory was retained, so RSS climbed ~8 MB per validation (measured: 42→50→60→68→78 MB) and kept
  growing across SHACL tests. The shapes graph is now parsed **once** and reused → peak RSS is flat
  (~90 MB), measured over repeated validations.
- **Default excludes the OOM combo:** the true blow-up was the heavy export tests running *with* the
  live Chemotion server (Rails+Postgres, ~1–2 GB) in one process on a constrained host. Those tests
  need the server so they carry `integration` and are excluded by default.
- **Heavy offline tests are bounded:** repeated offline `export_eln` peaks flat at ~86 MB (the merged
  LinkML `SchemaView` is cached process-wide in `collection.py`). `tests/unit` (110 tests, incl. the 7
  heavy offline ones) passes under a hard 2.5 GB address-space cap.
- `tests/conftest.py` imports `chemotion_api` **lazily** (inside the server fixtures) so collecting the
  unit suite doesn't pull in rdflib/linkml. Live-CLI DEBUG logging is **off** in `pytest.ini` (it
  floods memory).
