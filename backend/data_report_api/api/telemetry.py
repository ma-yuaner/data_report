from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request
from ..services.telemetry import TelemetryService, TelemetryUnavailable
from .common import json_body, ok


def register_routes(api: Blueprint) -> None:
    @api.post("/v1/telemetry/visits")
    def start_telemetry_visit():
        try:
            return ok(
                TelemetryService(current_app.config).start_visit(
                    g.current_user, getattr(g, "current_session", {}), json_body()
                ),
                "页面访问已记录",
            ), 201
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except TelemetryUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/telemetry/visits/<visit_id>")
    def update_telemetry_visit(visit_id: str):
        try:
            return ok(
                TelemetryService(current_app.config).update_visit(g.current_user, visit_id, json_body()),
                "页面访问已更新",
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except TelemetryUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/telemetry/events")
    def record_telemetry_events():
        try:
            return ok(
                TelemetryService(current_app.config).record_events(
                    g.current_user, getattr(g, "current_session", {}), json_body()
                ),
                "行为事件已记录",
            ), 202
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except TelemetryUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/admin/telemetry/dashboard")
    def telemetry_dashboard():
        try:
            return ok(
                TelemetryService(current_app.config).dashboard(
                    g.current_user,
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
