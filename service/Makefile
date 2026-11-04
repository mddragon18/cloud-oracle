# Run from anywhere: make -C service <target>
ROOT := $(CURDIR)/..
PY ?= python3   # activate the repo .venv first

.PHONY: run-api run-dash pipeline-once test

run-api:            # API on http://localhost:8000 (docs at /docs)
	cd "$(ROOT)" && $(PY) -m uvicorn service.oracle_service.api:app --reload --port 8000

run-dash:           # Streamlit dashboard (W3)
	cd "$(ROOT)" && $(PY) -m streamlit run service/dashboard/app.py

pipeline-once:      # one forecast+plan run; ORACLE_SOURCE=sample|local|s3
	cd "$(ROOT)" && $(PY) -m service.oracle_service.pipeline

test:
	cd "$(ROOT)" && $(PY) service/tests/test_api.py && $(PY) -m pytest service/tests -q
