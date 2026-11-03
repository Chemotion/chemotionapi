# Tests

The suite is split so the offline checks run anywhere, and the server-dependent ones are opt-in.

## Layout

- **`tests/unit/`** — pure logic, offline, fast (445 tests, a few seconds). No live server and no network.
  Covers the collection tree (walk, case-insensitive lookup, element membership), element URLs
  and partial loading, sample and reaction properties, reaction variations and their segment
  columns, generic-element usability and workflow handling, segment fields, the converter, and
  the request-error classes.
- **`tests/*.py`** (top level) — tests that talk to a Chemotion server. These are auto-marked
  `@pytest.mark.integration` by `conftest.py`: any test whose fixtures reach one of the
  `SERVER_FIXTURES` names (`logged_in_instance`, `instance_with_*`, …) gets the marker, directly
  or transitively, so nothing server-dependent can leak into the offline gate by accident.

## Running

The **default** (`addopts` in `pytest.ini`) is `-m "not integration" --forked`: all offline
tests, each in its own subprocess. `--forked` (from `pytest-forked`) runs them *serially*, so
peak memory stays at roughly one test's worth and a runaway test dies alone rather than taking
the run with it.

```bash
# Default: the offline suite. No server needed.
just test                      # or: cd tests && python -m pytest -q

# The unit subset only (fastest).
just test-unit

# Skip the fork overhead — single process, when memory is known-bounded.
cd tests && python -m pytest -p no:forked -q

# Integration suite — self-contained: NO_SETUP=0 boots the docker stack in tests/test_config/,
# resets the DB from the committed seed (tests/data/test.sql) and waits for the ELN.
# Docker is the only requirement; defaults (port 3579, seed users) live in conftest.py.
just test-integration

# Against an already-running or external instance instead, skip the setup and override via env:
ELN_URL=http://... ELN_USER=... ELN_PASS=... NO_SETUP=1 \
  python -m pytest -m integration -q
```

`just check` runs lint, types and the offline suite — no server involved.

See [test_config/README.md](./test_config/README.md) for the stack and seed-user details, and for
which images each release line uses. A fresh seed reset per session matters: the tests mutate the
instance (uploaded generic templates, collections), and some assertions rely on the seed's state.

## Notes

- `conftest.py` imports `chemotion_api` **lazily**, inside the server fixtures, so collecting the
  offline suite stays light. Live-CLI DEBUG logging is off in `pytest.ini`, where it floods memory.
- There is deliberately no session teardown that kills whatever holds port 3579. The stack is
  docker and is meant to outlive a run: `setup_chemotion_db.sh` reseeds it at the start of each
  session, and `just stack-down` is how you stop it.
- `pytest.ini` also declares a `heavy` marker for the memory-heavy offline tests that arrive
  with the FAIR export work — full `.eln` export and SHACL validation. They run in the default
  offline suite; the marker exists so they can be deselected on a constrained machine.
