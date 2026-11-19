"""ERP change SLA dashboard read endpoint."""
from flask import current_app, jsonify, request

from .common import ok
from ..services.change_sla import ChangeSlaQueryError, read_change_sla


def register_routes(api):
    @api.get("/v1/analysis/change-sla")
    def change_sla():
        try:
            response = ok(read_change_sla(current_app.config, request.args.get("from"), request.args.get("to")))
            response.headers["Cache-Control"] = "no-store"
            return response
        except ChangeSlaQueryError as exc:
            return jsonify(success=False, message=str(exc), data=None), 400
        except Exception:
            current_app.logger.exception("ERP change SLA query failed")
            return jsonify(success=False, message="ERP 改签数据暂不可用，请稍后重试", data=None), 503
