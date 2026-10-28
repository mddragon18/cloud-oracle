COMPOSE := docker compose -f workload/docker-compose.yml
PY ?= python3

.PHONY: up down load test

up:                 # full local stack: app x 3 behind nginx at :8080
	$(COMPOSE) up -d --build

down:               # tear everything local down
	$(COMPOSE) down

load:               # PATTERN=steady|cycle|spike|growth  CYCLE_S=600
	cd workload/locust && PATTERN=$${PATTERN:-steady} locust -f locustfile.py -H http://localhost:8090 --headless -t 2m

test:
	$(PY) forecasting/tests/test_forecast.py
	$(PY) capacity/tests/test_plan.py
	$(PY) service/tests/test_api.py
