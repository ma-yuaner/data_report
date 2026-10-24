"""Register domain adapters on one blueprint to preserve endpoint names."""
from flask import Blueprint

from .api import adm, adm_exchange, adm_files
from .api import data_workbench

from .api import targets, core, resource_governance, telemetry, dashboard, analysis, smart_analysis, smart_placement, monitoring, risk_upload

api = Blueprint("api", __name__)

adm.register_routes(api)
adm_exchange.register_routes(api)
adm_files.register_routes(api)

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
data_workbench.register_routes(api)

__all__ = ["api"]
