"""Shim: the old stub's names, now backed by service/oracle_service (HANDOFF §6)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from service.oracle_service.api import (  # noqa: F401
    app,
    health,
    history,
    latest_forecast,
    latest_plan,
    whatif_plan,
)
