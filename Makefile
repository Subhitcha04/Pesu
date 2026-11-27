# Pesu developer commands. Everything except `run` and `docker` needs: pip install -r requirements-dev.txt
PY ?= python3

.PHONY: run docker test e2e lint eval docs verify screenshots coverage backup clean

run:            ## start the app on http://localhost:3000 with demo data
	PESU_DEMO=1 $(PY) -m uvicorn app.main:app --port 3000

docker:         ## build and start with Docker (what reviewers run)
	docker compose up --build

test:           ## unit + API + golden-set tests (no browser needed)
	$(PY) -m pytest -q

e2e:            ## browser tests (needs: python -m playwright install chromium)
	$(PY) -m pytest -q tests/e2e -o addopts=""

lint:           ## ruff lint + format check + front-end static checks
	ruff check app tests scripts
	ruff format --check app tests scripts
	$(PY) scripts/check_static.py

eval:           ## scoring logic regression report (not an accuracy measure)
	$(PY) scripts/eval_scoring.py

coverage:       ## line coverage for app/
	$(PY) -m pytest -q --cov=app --cov-report=term

docs:           ## regenerate the generated README sections
	$(PY) scripts/gen_docs.py

verify:         ## check README links, make targets, env vars and API routes
	$(PY) scripts/verify_readme.py

screenshots:    ## regenerate docs/screenshots with Playwright
	$(PY) scripts/gen_screenshots.py

backup:         ## back up ./data (or PESU_DATA_DIR) to a tar.gz
	sh scripts/backup.sh

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
