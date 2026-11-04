"""Lambda entry points: API Gateway -> api_handler; EventBridge Scheduler -> pipeline_handler."""
import json
import logging
from dataclasses import replace

from mangum import Mangum

from . import config
from .api import app
from .pipeline import run_once
from .sources import NoMetricsError

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)
api_handler = Mangum(app, lifespan="off")


def pipeline_handler(event, context):
    """Test events: {"force_alert": true} alerts regardless of window/dedupe;
    {"source": "sample"} uses the contract sample instead of S3 (smoke test before real metrics exist).
    No metrics -> returns {"ok": false, ...} instead of failing the invocation; other errors re-raise."""
    event = event or {}
    cfg = config.load()
    if event.get("source"):
        cfg = replace(cfg, source=event["source"])
    try:
        return {"ok": True, **run_once(cfg, force_alert=bool(event.get("force_alert")))}
    except NoMetricsError as e:
        log.warning(json.dumps({"event": "pipeline_no_data", "source": cfg.source, "error": str(e)}))
        return {"ok": False, "event": "pipeline_no_data", "source": cfg.source, "error": str(e)}
