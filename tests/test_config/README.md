# Seeded integration environment

A local Chemotion ELN (docker compose) plus a seeded database, so the integration test suite
(the tests deselected by default via `-m "not integration"`) can run against a known state.

## Contents

- `compose.yml` — a minimal Chemotion 3.1.2 stack, based on the
  [ChemOrc payload compose](https://github.com/Chemotion/ChemOrc/blob/main/payload/docker-compose.yml)
  but trimmed to the essentials: `db` (Postgres, published on host port **54320**) and `eln`
  (published on host port **3579**, running with `CONFIG_ROLE=combine` so the one container serves
  the web app *and* the background worker — its only startup dependency is `db`). The stock image
  only knows the eln/worker roles, so `embed/` mounts the
  [Push2Deploy](https://github.com/Chemotion/Push2Deploy) versions of `run.sh`/`health.sh`, which
  add the combine role.
- `../data/test.sql` — the seeded database. All users are fictional:

  | Login | Password | Role |
  | --- | --- | --- |
  | `API` | `1234qewR!` | Person — the account the tests log in with |
  | `ADM` | `PleaseChangeYourPassword` | Admin |
  | `MM` (Max Mustermann) | `thebestpasswordever` | Person |

- `../data/setup_chemotion_db.sh` — dumps the current DB to `../data/dumps/` (gitignored),
  then drops, recreates and reloads it from `test.sql` and runs pending Rails migrations (the seed
  is dumped at the stack's own version, so this is normally a no-op — it only replays
  migrations after a stack upgrade. The original 2.1.1-era dump lives in git history).
- `sample_files/` — attachment fixtures used by some tests.

## Usage

```bash
cd tests/test_config
docker compose up -d       # first start initializes the instance (takes a few minutes)
```

Then run the integration suite from `tests/` — the conftest resets the DB from the seed
automatically unless `NO_SETUP=1`:

```bash
cd ..
NO_SETUP=0 ../.venv/bin/python -m pytest -m integration
```

Connection defaults (URL `http://127.0.0.1:3579`, users above) live in `tests/conftest.py
DEFAULT_CONFIG`; override any of them via environment variables or a gitignored `config.json`
(template: [`../config.json.sample`](../config.json.sample); `conftest.py` reads `config.json`
from the working directory, i.e. `tests/` in the `just test-integration` workflow).

Note: the DB reset uses the host Postgres client tools (`psql`, `pg_dump`) against port 54320
when available, and falls back to `docker compose exec db` otherwise — docker is the only hard
requirement.
