"""ERP change SLA dashboard read endpoint."""
from flask import current_app, g, jsonify, request

from .common import ok
from ..services.change_sla import ChangeSlaQueryError, read_change_sla


def register_routes(api):
    @api.get("/v1/analysis/change-sla")
    def change_sla():
        user = getattr(g, "current_user", {})
        permitted = user.get("is_admin") or any(
            role.get("name") == "客服经理" for role in (user.get("business_roles") or [])
        )
        if not current_app.config["AUTH_ENABLED"] or not permitted:
            return jsonify(success=False, message="仅系统管理员或客服经理可查看改签 SLA", code="PERMISSION_FORBIDDEN", data=None), 403
        try:
            response = ok(read_change_sla(current_app.config, request.args.get("from"), request.args.get("to")))
            response.headers["Cache-Control"] = "no-store"
            return response
        except ChangeSlaQueryError as exc:
            return jsonify(success=False, message=str(exc), data=None), 400
        except Exception:
            current_app.logger.exception("ERP change SLA query failed")
            return jsonify(success=False, message="ERP 改签数据暂不可用，请稍后重试", data=None), 503
