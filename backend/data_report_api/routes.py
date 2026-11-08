"""Register domain adapters on one blueprint to preserve endpoint names."""
from flask import Blueprint

from .api import admwf
from .api import data_workbench
from .api import hr_mail
from .api import risk_verification

from .api import targets, core, resource_governance, telemetry, dashboard, analysis, smart_analysis, smart_placement, monitoring, risk_upload

from .api import missed_orders, placement_import, placement_diagnosis

api = Blueprint("api", __name__)
missed_orders.register_routes(api)
placement_import.register_routes(api)
placement_diagnosis.register_routes(api)

admwf.register_routes(api)

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
hr_mail.register_routes(api)
risk_verification.register_routes(api)

__all__ = ["api"]
