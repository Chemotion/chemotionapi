# Seeded integration environment

A local Chemotion ELN (docker compose) plus a seeded database, so the integration test suite
(the tests deselected by default via `-m "not integration"`) can run against a known state.

## Contents

- `compose.yml` — a minimal Chemotion stack, based on the
  [ChemOrc payload compose](https://github.com/Chemotion/ChemOrc/blob/main/payload/docker-compose.yml)
  but trimmed to the essentials: `db` (Postgres, published on host port **54320**) and `eln`
  (published on host port **3579**, running with `CONFIG_ROLE=combine` so the one container serves
  the web app *and* the background worker — its only startup dependency is `db`). The stock image
  only knows the eln/worker roles, so `embed/` mounts the
  [Push2Deploy](https://github.com/Chemotion/Push2Deploy) versions of `run.sh`/`health.sh`, which
  add the combine role.

  Volume names carry a per-line suffix (`CHEMOTION_STACK_SUFFIX`) so one line's volumes — which
  survive `docker compose down` — are never silently reused under another line's Postgres image.
- `../data/test.sql` — the seeded database. All users are fictional:

  | Login | Password | Role |
  | --- | --- | --- |
  | `API` | `1234qewR!` | Person — the account the tests log in with |
  | `ADM` | `PleaseChangeYourPassword` | Admin |
  | `MM` (Max Mustermann) | `thebestpasswordever` | Person |

- `../data/setup_chemotion_db.sh` — dumps the current DB to `../data/dumps/` (gitignored),
  then drops, recreates and reloads it from `test.sql` and runs pending Rails migrations (the seed
  is dumped at the stack's own version, so this is normally a no-op — it only replays
  migrations after a stack upgrade; that is the hook the v3 → v4 seed upgrade goes through.
  Earlier 2.1.1- and 3.1.2-era dumps live in git history).
- `sample_files/` — attachment fixtures used by some tests.


## Scope: ELN v3 and v4

**This stack serves the v3 and v4 release lines. It does not support ELN v2, and the client is not
claimed to work against one.** A 2.x image will start on it — the embed scripts are portable — but
nothing here is seeded, exercised or supported for v2. `main` is where the v2-era client lives;
this layer exists to carry v3 and v4 forward.

## Choosing the server version

`compose.yml` names no images of its own, because the v3 and v4 lines share it and each must run
against the ELN it targets. It reads three variables, and declares no defaults for them — an
unset one makes `docker compose` refuse to start, which is the point: a stack that silently
brings up the wrong server produces failures that look like client bugs.

This branch supplies them from **`images.env`**, next to `compose.yml`:

| variable | this branch (400.x) | the 312.x line |
|---|---|---|
| `CHEMOTION_ELN_IMAGE` | `complat/chemotion_eln_stage:next-release@sha256:3520ac2c…` | `ptrxyz/chemotion:eln-3.1.2` |
| `CHEMOTION_DB_IMAGE` | `complat/dev:postgres16-rdkit@sha256:326d2ef0…` | `ptrxyz/chemotion:db-3.1.2` |
| `CHEMOTION_STACK_SUFFIX` | `v4` | `v3` |

The v4 images are **pinned by digest**: `next-release` is a rolling tag, rebuilt whenever the v4
branch moves, and Docker Hub publishes no immutable v4 tag (its tags jump from `v3.1.1` straight
to `next-release`). Without the digest, two runs a day apart can test different servers. Bumping
a digest is a deliberate, reviewed change — record the new digest together with the `Version:`
string that `/about` then reports. Pinned 2026-08-21 at **v4.0.0-rc-260818**.

Every caller passes the file explicitly (`--env-file`), because `conftest.py` runs
`tests/data/setup_chemotion_db.sh` directly and that script calls `docker compose` itself — so
the values cannot come from the caller's shell. Note that `--env-file` replaces Compose's
automatic `.env` lookup, so a local `.env` here is *not* read. To override an image for one run,
set the variable in your shell: the shell environment still wins over `--env-file`.

```bash
CHEMOTION_ELN_IMAGE=some/other:image just stack-up
```

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
