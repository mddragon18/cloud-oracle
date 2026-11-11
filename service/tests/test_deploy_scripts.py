"""Run the deploy scripts against a stub aws that logs its calls: nothing here reaches AWS."""
import json
import os
import stat
import subprocess

from service.oracle_service.config import REPO

STUB = """#!/bin/bash
echo "$*" >> "$AWS_LOG"
case "$*" in
  *get-caller-identity*) echo 149236595048 ;;
  *get-apis*) echo abc123 ;;
  *get-function-configuration*) echo '{"Variables": {"KEEP": "yes", "REPLAY_MODE": "0"}}' ;;
  *"lambda invoke"*) echo '{"ok": true}' > "${@: -1}" ;;
esac
"""


def run(tmp_path, script, *args, **env):
    aws = tmp_path / "aws"
    aws.write_text(STUB)
    aws.chmod(aws.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "aws.log"
    r = subprocess.run([str(REPO / "service/deploy" / script), *args], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "AWS_LOG": str(log), **env})
    return r, log.read_text().splitlines()


def test_down_dry_run_prints_deletes_and_runs_none(tmp_path):
    r, calls = run(tmp_path, "down.sh", DRY_RUN="1")
    assert r.returncode == 0, r.stderr
    assert not [c for c in calls if " delete" in c or " detach" in c]
    for what in ("delete-schedule", "delete-api --api-id abc123", "delete-function --function-name oracle-pipeline",
                 "detach-role-policy", "delete-table", "delete-topic", "delete-repository"):
        assert f"{what}" in r.stdout
    assert "dry run: nothing deleted" in r.stdout


def test_down_without_dry_run_still_deletes(tmp_path):
    r, calls = run(tmp_path, "down.sh", "--keep-data")
    assert r.returncode == 0, r.stderr
    assert any("delete-function" in c for c in calls) and not any("delete-table" in c for c in calls)


def test_replay_keeps_other_env_and_reruns_pipeline(tmp_path):
    r, calls = run(tmp_path, "replay.sh", "on")
    assert r.returncode == 0, r.stderr
    updates = [c for c in calls if "update-function-configuration" in c]
    assert len(updates) == 2
    for u in updates:
        assert json.loads(u.split("--environment ", 1)[1])["Variables"] == {"KEEP": "yes", "REPLAY_MODE": "1"}
    assert "lambda invoke" in calls[-1]


def current_replay(tmp_path, reply, explicit=""):
    aws = tmp_path / "aws"
    aws.write_text(f"#!/bin/bash\n{reply}\n")
    aws.chmod(aws.stat().st_mode | stat.S_IEXEC)
    cmd = f'set -euo pipefail; source service/deploy/config.sh; R="${{REPLAY_MODE:-$(current_replay)}}"; echo "got=$R"'
    return subprocess.run(["bash", "-c", cmd], cwd=REPO, capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "REPLAY_MODE": explicit})


def test_deploy_keeps_replay_unless_passed(tmp_path):
    assert "got=1" in current_replay(tmp_path, "echo 1").stdout
    assert "got=0" in current_replay(tmp_path, "echo 1", explicit="0").stdout
    assert "got=0" in current_replay(tmp_path, "echo None").stdout
    assert "got=0" in current_replay(tmp_path, "echo ResourceNotFoundException; exit 1").stdout


def test_deploy_stops_if_replay_unreadable(tmp_path):
    r = current_replay(tmp_path, "echo AccessDenied; exit 1")
    assert r.returncode != 0 and "got=" not in r.stdout


def test_lambdas_run_math_libraries_single_threaded():
    env_line = next(l for l in (REPO / "service/deploy/up.sh").read_text().splitlines() if l.startswith('ENV_VARS="Variables='))
    assert all(f"{v}=1" in env_line for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"))


def window_for_deploy(tmp_path, reply, explicit=""):
    aws = tmp_path / "aws"
    aws.write_text(f"#!/bin/bash\n{reply}\n")
    aws.chmod(aws.stat().st_mode | stat.S_IEXEC)
    lines = (REPO / "service/deploy/up.sh").read_text().splitlines()
    block = "\n".join(l for l in lines if "FORECAST_WINDOW_HOURS" in l and not l.startswith(("#", "ENV_VARS")))
    return subprocess.run(["bash", "-c", f"set -euo pipefail; source service/deploy/config.sh\n{block}"], cwd=REPO,
                          capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "FORECAST_WINDOW_HOURS": explicit})


def test_deploy_passes_forecast_window_to_lambdas(tmp_path):
    up = (REPO / "service/deploy/up.sh").read_text()
    assert "FORECAST_WINDOW_HOURS=$FORECAST_WINDOW_HOURS," in next(l for l in up.splitlines() if l.startswith("ENV_VARS="))
    assert "72" not in up  # the default lives in service config only
    assert "FORECAST_WINDOW_HOURS=72" in window_for_deploy(tmp_path, "echo None").stdout  # nothing deployed -> default
    assert "FORECAST_WINDOW_HOURS=48" in window_for_deploy(tmp_path, "echo 48").stdout  # keeps the deployed value
    assert "FORECAST_WINDOW_HOURS=24" in window_for_deploy(tmp_path, "echo 48", explicit="24").stdout


def test_forecast_window_default_and_env(monkeypatch):
    from service.oracle_service import config
    monkeypatch.delenv("FORECAST_WINDOW_HOURS", raising=False)
    assert config.load().forecast_window_hours == 72
    monkeypatch.setenv("FORECAST_WINDOW_HOURS", "48")
    assert config.load().forecast_window_hours == 48
