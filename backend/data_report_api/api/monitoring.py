from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request
from ..services.monitoring import MonitoringService, MonitoringUnavailable
from .common import json_body, ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/monitoring/overview")
    def monitoring_overview():
        try:
            return ok(MonitoringService(current_app.config).overview(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/templates")
    def monitoring_templates():
        try:
            return ok(MonitoringService(current_app.config).templates(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/rules")
    def monitoring_rules():
        try:
            return ok(
                MonitoringService(current_app.config).list_rules(
                    g.current_user,
                    status=request.args.get("status", ""),
                    template=request.args.get("template", ""),
                    keyword=request.args.get("keyword", ""),
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("pageSize", "30")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/rules")
    def create_monitoring_rule():
        try:
            return ok(MonitoringService(current_app.config).create_rule(g.current_user, json_body()), "监控规则已创建")
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/rules/<int:rule_id>")
    def monitoring_rule_detail(rule_id: int):
        try:
            return ok(MonitoringService(current_app.config).rule_detail(g.current_user, rule_id))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 404
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/monitoring/rules/<int:rule_id>/status")
    def update_monitoring_rule_status(rule_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).update_rule_status(g.current_user, rule_id, json_body()),
                "监控规则状态已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/rules/<int:rule_id>/diagnose")
    def diagnose_monitoring_rule(rule_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).diagnose_rule(
                    g.current_user,
                    rule_id,
                    request.args.get("otaOrderNo", ""),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/events")
    def monitoring_events():
        try:
            return ok(
                MonitoringService(current_app.config).list_events(
                    g.current_user,
                    status=request.args.get("status", ""),
                    template=request.args.get("template", ""),
                    start_date=request.args.get("startDate", ""),
                    end_date=request.args.get("endDate", ""),
                    keyword=request.args.get("keyword", ""),
                    assignee_user_id=int(request.args.get("assigneeUserId", "0") or 0) or None,
                    only_mine=str(request.args.get("onlyMine") or "").strip().lower() in {"1", "true", "yes"},
                    overdue_only=str(request.args.get("overdueOnly") or "").strip().lower() in {"1", "true", "yes"},
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("pageSize", "30")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/event-assignees")
    def monitoring_event_assignees():
        try:
            return ok(MonitoringService(current_app.config).list_event_assignees(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/action-orders")
    def monitoring_action_orders():
        try:
            return ok(
                MonitoringService(current_app.config).list_action_orders(
                    g.current_user,
                    status=request.args.get("status", ""),
                    action_type=request.args.get("actionType", ""),
                    assignee_user_id=int(request.args.get("assigneeUserId", "0") or 0) or None,
                    only_mine=str(request.args.get("onlyMine") or "").strip().lower() in {"1", "true", "yes"},
                    keyword=request.args.get("keyword", ""),
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("pageSize", "30")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/action-orders/<int:action_order_id>")
    def monitoring_action_order_detail(action_order_id: int):
        try:
            return ok(MonitoringService(current_app.config).action_order_detail(g.current_user, action_order_id))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 404
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/events/<int:event_id>/action-orders")
    def create_monitoring_action_order(event_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).create_action_order(g.current_user, event_id, json_body()),
                "技术执行工单已创建",
            ), 201
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/monitoring/action-orders/<int:action_order_id>/status")
    def update_monitoring_action_order(action_order_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).update_action_order(g.current_user, action_order_id, json_body()),
                "技术工单状态已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/events/<int:event_id>")
    def monitoring_event_detail(event_id: int):
        try:
            return ok(MonitoringService(current_app.config).event_detail(g.current_user, event_id))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 404
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/runs")
    def monitoring_runs():
        try:
            return ok(
                MonitoringService(current_app.config).list_runs(
                    g.current_user,
                    job_type=request.args.get("jobType", ""),
                    status=request.args.get("status", ""),
                    limit=int(request.args.get("limit", "100")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/notify-endpoints")
    def monitoring_notify_endpoints():
        try:
            return ok(MonitoringService(current_app.config).list_notify_endpoints(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/notify-endpoints")
    def create_monitoring_notify_endpoint():
        try:
            return ok(
                MonitoringService(current_app.config).save_notify_endpoint(g.current_user, json_body()), "通知群已创建"
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.put("/v1/monitoring/notify-endpoints/<int:endpoint_id>")
    def update_monitoring_notify_endpoint(endpoint_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).save_notify_endpoint(g.current_user, json_body(), endpoint_id),
                "通知群已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/notify-endpoints/<int:endpoint_id>/test")
    def test_monitoring_notify_endpoint(endpoint_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).test_notify_endpoint(g.current_user, endpoint_id),
                "测试消息发送成功",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/message-templates")
    def monitoring_message_templates():
        try:
            return ok(MonitoringService(current_app.config).list_message_templates(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.put("/v1/monitoring/message-templates/<int:template_id>")
    def update_monitoring_message_template(template_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).update_message_template(g.current_user, template_id, json_body()),
                "消息模板已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/message-templates")
    def create_monitoring_message_template():
        try:
            return ok(
                MonitoringService(current_app.config).create_message_template(g.current_user, json_body()),
                "消息模板已创建",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/monitoring/notify-routes")
    def monitoring_notify_routes():
        try:
            return ok(MonitoringService(current_app.config).list_notify_routes(g.current_user))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/monitoring/notify-routes")
    def create_monitoring_notify_route():
        try:
            return ok(
                MonitoringService(current_app.config).save_notify_route(g.current_user, json_body()),
                "通知路由已创建",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.put("/v1/monitoring/notify-routes/<int:route_id>")
    def update_monitoring_notify_route(route_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).save_notify_route(g.current_user, json_body(), route_id),
                "通知路由已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/monitoring/events/<int:event_id>/status")
    def update_monitoring_event_status(event_id: int):
        try:
            return ok(
                MonitoringService(current_app.config).update_event_status(g.current_user, event_id, json_body()),
                "监控事件已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503
