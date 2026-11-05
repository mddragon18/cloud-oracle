# Run from anywhere: make -C service <target>
ROOT := $(CURDIR)/..
PY ?= python3   # activate the repo .venv first

.PHONY: run-api run-dash pipeline-once test test-all

run-api:            # API on http://localhost:8000 (docs at /docs)
	cd "$(ROOT)" && $(PY) -m uvicorn service.oracle_service.api:app --reload --port 8000

run-dash:           # Streamlit dashboard (W3)
	cd "$(ROOT)" && $(PY) -m streamlit run service/dashboard/app.py

pipeline-once:      # one forecast+plan run; ORACLE_SOURCE=sample|local|s3
	cd "$(ROOT)" && $(PY) -m service.oracle_service.pipeline

test:
	cd "$(ROOT)" && $(PY) service/tests/test_api.py && $(PY) -m pytest service/tests -q

test-all: test      # separate pytest runs: service and capacity tests clash when collected together
	cd "$(ROOT)" && $(PY) -m pytest capacity -q && $(PY) -m pytest forecasting -q && $(PY) service/dashboard/check_cloud.py

# ---- AWS (W4). AWS_PROFILE=oracle-m4, ap-south-1; see service/deploy/config.sh ----
.PHONY: build deploy down smoke schedule-on schedule-off invoke

build:              # Lambda image, native arm64
	cd "$(ROOT)" && docker build --platform linux/arm64 --provenance=false -f service/deploy/Dockerfile.lambda -t oracle-service:local .

deploy: test-all    # ALERT_EMAILS="a@x,b@y" make -C service deploy
	"$(ROOT)/service/deploy/up.sh"

down:               # KEEP=--keep-data to keep table + topic
	"$(ROOT)/service/deploy/down.sh" $(KEEP)

smoke:
	"$(ROOT)/service/deploy/smoke.sh"

schedule-on:
	"$(ROOT)/service/deploy/schedule.sh" on

schedule-off:
	"$(ROOT)/service/deploy/schedule.sh" off

invoke:             # EVENT='{"source": "sample"}' make -C service invoke
	cd "$(ROOT)" && . service/deploy/config.sh && aws lambda invoke --function-name $$PIPELINE_FN \
	  --cli-binary-format raw-in-base64-out --payload '$(or $(EVENT),{})' /dev/stdout
