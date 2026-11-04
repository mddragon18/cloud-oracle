#!/usr/bin/env bash
# Copy /data/metrics.csv out of the app1..3 containers into data/local-metrics/ (ORACLE_SOURCE=local).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/local-metrics
for app in app1 app2 app3; do
  docker compose -f workload/docker-compose.yml cp "$app:/data/metrics.csv" "data/local-metrics/$app.csv"
done
wc -l data/local-metrics/*.csv
