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

## Testing against an unreleased ELN (p2d)

`images.env` pins a released server. To run the suite against a branch, tag or commit of
[chemotion_ELN](https://github.com/ComPlat/chemotion_ELN) that has no image yet, build it with
the ELN's own Push2Deploy files (`Dockerfile.p2d`, present from v3.1.0-rc on):

```bash
just stack-p2d-build                 # the tested ELN from eln-ref.env (see below)
just stack-p2d                       # reset the p2d stack from the seed, run every test
just stack-p2d -m integration -q     # or pass your own pytest arguments
just stack-p2d-build main            # or any branch, tag (v4.0.0) or full commit sha
just stack-p2d main
just stack-p2d-down
```

### The tested ELN: `eln-ref.env`

[`eln-ref.env`](eln-ref.env) records the chemotion_ELN source the suite was last run green
against, with three fields:

| field | meaning |
|---|---|
| `ELN_BRANCH` | the branch the commit was taken from; names the image |
| `ELN_TAG` | a tag at that commit, if any |
| `ELN_COMMIT` | the full sha — when set, this is what gets built |

When the file exists, `build`, `test` and `image` without a ref (for `test`: no ref, or a first
argument starting with `-`) use it, building `ELN_COMMIT`, else `ELN_TAG`, else the tip of
`ELN_BRANCH`. The image is `chemotion-eln-p2d:<branch, else tag>-<short sha>`, so a branch that
moves on cannot change the server under the suite. An explicit ref on the command line still wins;
without the file the default ref is `main`.

Setting just one field is enough: the empty ones are looked up with `git ls-remote` and written
back into the file (a short sha is expanded too). A branch or tag is only filled in when its tip
is exactly the commit, since `ls-remote` cannot tell which branch merely contains it; otherwise it
stays empty. If the remote is unreachable and the commit is already a full sha, the fill-in is
skipped with a warning. Bump the file after a green run against a new commit, and commit it.

All of it goes through [`p2d.sh`](p2d.sh), which can also be run directly with `bash`.

- The image is tagged `chemotion-eln-p2d:<ref>` and `chemotion-eln-p2d:<ref>-<sha>`.
- It runs as compose project `chemotion-test-p2d` with its own volumes (`*_p2d`), so the pinned
  stack and its data are untouched. It keeps the pinned db image from `images.env`.
- Both stacks publish ports 3579 and 54320, so only one can run at a time. `stack-p2d` refuses
  to start while another container holds 3579.
- The first build takes about 45 minutes, because it reinstalls Ruby, Node and every gem. Later
  builds reuse most of it from the BuildKit cache.
- Near the end the build downloads Ketcher from GitHub. A network timeout there is not a code
  problem: rerun, and the cached layers make it quick.
- Migrations newer than the seed are applied by the reset, as for any upgrade.
