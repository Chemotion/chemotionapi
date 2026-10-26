# Task runner for the chemotion-api client. Everything is self-contained:
# `uv` manages Python + dependencies, docker runs the test ELN. Run `just` to list recipes.

# Every docker compose call goes through tests/test_config/images.env, which decides which
# server this line tests against. compose.yml itself declares no defaults.
compose := "docker compose --env-file tests/test_config/images.env -f tests/test_config/compose.yml"

# list available recipes
default:
    @just --list

# install/refresh the virtualenv with all dependency groups
sync:
    uv sync --all-groups

# run the offline test suite (no server needed; memory-safe defaults from pytest.ini)
test:
    cd tests && uv run pytest -q

# run the pure-logic unit subset only (CI runs the whole offline suite via `just test`);
# NO_SETUP=1 keeps the test ELN untouched
test-unit:
    cd tests && NO_SETUP=1 uv run pytest unit -q

# NO_SETUP=0 boots the docker stack and resets the DB from the committed seed, then runs the integration suite
test-integration:
    cd tests && NO_SETUP=0 uv run pytest -m integration -q

# offline-suite coverage report, gated at the floor in pyproject.toml.
# addopts is overridden on purpose: pytest.ini defaults to --forked, which runs each test in its
# own subprocess, so coverage would see only import-time execution (it reported 27.7% that way).
cov:
    uv run coverage run -m pytest tests -q -o 'addopts=-m "not integration"'
    uv run coverage report

# static type checking
mypy:
    uv run mypy chemotion_api

# modernization lint (ruff pyupgrade rules, target py314)
lint:
    uv run ruff check chemotion_api tests docs

# apply auto-fixable lint findings
lint-fix:
    uv run ruff check chemotion_api tests docs --fix

# ruff + mypy — the static gate, and exactly what CI enforces on every push and PR
static: lint mypy

# the local gate: lint + types + the offline suite. Needs no server — tests/pytest.ini sets
# `addopts = -m "not integration"` and conftest auto-marks the server-dependent tests.
check: lint mypy test

# build the Sphinx documentation → docs/_build/html/index.html
docs:
    uv run --group docs sphinx-build -b html docs docs/_build/html

# remove the generated documentation
docs-clean:
    rm -rf docs/_build

# build sdist + wheel into dist/
build:
    uv build

# start the dockerized test ELN (db on :54320, eln on :3579)
stack-up:
    {{compose}} up -d

# stop the dockerized test ELN
stack-down:
    {{compose}} down

# reset the test DB from the committed seed (starts the stack if needed)
stack-reset:
    cd tests/data && bash setup_chemotion_db.sh

# tail the ELN container logs
stack-logs:
    {{compose}} logs -f eln

# dump the LabIMotion JSON validation schemas to ./schemas/ (live ELN needed; override ELN_URL/ELN_USER/ELN_PASS)
schemas:
    uv run python -c "\
    import os; \
    from chemotion_api import Instance; \
    url = os.environ.get('ELN_URL', 'http://127.0.0.1:3579'); \
    user = os.environ.get('ELN_USER', 'API'); \
    pw = os.environ.get('ELN_PASS', '1234qewR!'); \
    i = Instance(url).test_connection().login(user, pw); \
    i.generic_manager().write_all_validation_schemas(); \
    print('schemas written to ./schemas/')"
