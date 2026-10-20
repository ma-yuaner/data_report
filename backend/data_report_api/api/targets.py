from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request
from ..services.target_management import TargetManagementService, TargetManagementUnavailable
from ..services.target_etl_trigger import TargetEtlTriggerConflict, TargetEtlTriggerService, TargetEtlTriggerUnavailable
from .common import json_body, ok


def register_routes(api: Blueprint) -> None:
    def _target_error(error: Exception):
        if isinstance(error, PermissionError):
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        if isinstance(error, ValueError):
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/business-configuration/targets")
    def target_management_list():
        try:
            return ok(
                TargetManagementService(current_app.config).list_targets(
                    g.current_user,
                    scene_value=request.args.get("scene"),
                    period_value=request.args.get("period"),
                    status_value=request.args.get("status", "ALL"),
                    keyword_value=request.args.get("keyword", ""),
                )
            )
        except (PermissionError, ValueError, TargetManagementUnavailable) as error:
            return _target_error(error)

    @api.get("/v1/business-configuration/target-progress")
    def target_progress_dashboard():
        try:
            return ok(
                TargetManagementService(current_app.config).progress_dashboard(
                    g.current_user,
                    scene_value=request.args.get("scene"),
                    period_value=request.args.get("period"),
                    keyword_value=request.args.get("keyword", ""),
                    include_unconfigured_value=request.args.get("includeUnconfigured"),
                )
            )
        except (PermissionError, ValueError, TargetManagementUnavailable) as error:
            return _target_error(error)

    @api.get("/v1/business-configuration/target-progress/refresh/status")
    def target_progress_refresh_status():
        try:
            return ok(TargetEtlTriggerService(current_app.config).status(g.current_user))
        except (PermissionError, TargetEtlTriggerUnavailable) as error:
            return _target_error(error)

    @api.post("/v1/business-configuration/target-progress/refresh")
    def target_progress_refresh():
        try:
            return ok(TargetEtlTriggerService(current_app.config).trigger(g.current_user), "立即更新任务已提交"), 202
        except TargetEtlTriggerConflict as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 409
        except (PermissionError, TargetEtlTriggerUnavailable) as error:
            return _target_error(error)

    @api.get("/v1/business-configuration/targets/metrics")
    def target_management_metrics():
        try:
            return ok(TargetManagementService(current_app.config).metrics(g.current_user))
        except (PermissionError, TargetManagementUnavailable) as error:
            return _target_error(error)

    @api.get("/v1/business-configuration/targets/options")
    def target_management_options():
        try:
            return ok(TargetManagementService(current_app.config).options(g.current_user))
        except (PermissionError, TargetManagementUnavailable) as error:
            return _target_error(error)

    @api.post("/v1/business-configuration/targets")
    def target_management_save():
        try:
            return ok(TargetManagementService(current_app.config).save(g.current_user, json_body()), "目标已保存"), 201
        except (PermissionError, ValueError, TargetManagementUnavailable) as error:
            return _target_error(error)
