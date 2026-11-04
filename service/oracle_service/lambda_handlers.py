"""Lambda entry points: API Gateway -> api_handler; EventBridge Scheduler -> pipeline_handler."""
import logging

from mangum import Mangum

from .api import app
from .pipeline import run_once

logging.getLogger().setLevel(logging.INFO)
api_handler = Mangum(app, lifespan="off")


def pipeline_handler(event, context):
    """Test event {"force_alert": true} sends an alert regardless of window/dedupe."""
    return run_once(force_alert=bool((event or {}).get("force_alert")))
