"""Register domain adapters on one blueprint to preserve endpoint names."""
from flask import Blueprint

from .api import targets, core, resource_governance, telemetry, dashboard, analysis, smart_analysis, smart_placement, monitoring, risk_upload

api = Blueprint("api", __name__)

targets.register_routes(api)
core.register_routes(api)
resource_governance.register_routes(api)
telemetry.register_routes(api)
dashboard.register_routes(api)
analysis.register_routes(api)
smart_analysis.register_routes(api)
smart_placement.register_routes(api)
monitoring.register_routes(api)
risk_upload.register_routes(api)

__all__ = ["api"]
