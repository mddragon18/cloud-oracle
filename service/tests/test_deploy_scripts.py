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
