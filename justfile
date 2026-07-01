# Task runner for the chemotion-api client. Everything is self-contained:
# `uv` manages Python + dependencies, docker runs the test ELN. Run `just` to list recipes.

# list available recipes
default:
    @just --list

# install/refresh the virtualenv with all dependency groups
sync:
    uv sync --all-groups

# run the offline test suite (no server needed; memory-safe defaults from pytest.ini)
test:
    uv run pytest tests -q

# run the pure-logic unit subset (what CI runs)
test-unit:
    uv run pytest tests/unit -q

# NO_SETUP=0 boots the docker stack and resets the DB from the committed seed, then runs the integration suite
test-integration:
    cd tests && NO_SETUP=0 uv run pytest -m integration -q

# static type checking
mypy:
    uv run mypy chemotion_api

# offline-suite coverage (single process: forked children don't report; gate = fail_under in pyproject)
cov:
    uv run pytest tests -q -o addopts="" -m "not integration" --cov=chemotion_api --cov-report=term-missing --cov-report=xml

# modernization lint (ruff pyupgrade rules, target py314)
lint:
    uv run ruff check chemotion_api tests docs

# apply auto-fixable lint findings
lint-fix:
    uv run ruff check chemotion_api tests docs --fix

# lint + mypy + offline tests — the full local gate
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
    docker compose -f tests/test_config/compose.yml up -d

# stop the dockerized test ELN
stack-down:
    docker compose -f tests/test_config/compose.yml down

# reset the test DB from the committed seed (starts the stack if needed)
stack-reset:
    cd tests/data && bash setup_chemotion_db.sh

# tail the ELN container logs
stack-logs:
    docker compose -f tests/test_config/compose.yml logs -f eln

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
