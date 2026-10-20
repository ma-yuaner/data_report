from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request
from ..services.smart_placement import SmartPlacementService, SmartPlacementUnavailable
from ..services.monitoring import MonitoringService, MonitoringUnavailable
from .common import json_body, ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/smart-placement/tasks")
    def smart_placement_tasks():
        try:
            return ok(
                SmartPlacementService(current_app.config).list_tasks(
                    user=g.current_user,
                    status=request.args.get("status", ""),
                    keyword=request.args.get("keyword", ""),
                    platform=request.args.get("platform", ""),
                    airline=request.args.get("airline", ""),
                    owner=request.args.get("owner", ""),
                    scope=request.args.get("scope", ""),
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("pageSize", "30")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/smart-placement/dimensions")
    def smart_placement_dimensions():
        try:
            return ok(SmartPlacementService(current_app.config).dimension_options())
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks")
    def create_smart_placement_task():
        try:
            return ok(
                SmartPlacementService(current_app.config).create_task(g.current_user, json_body()), "投放机会已保存"
            ), 201
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/smart-placement/tasks/<int:task_id>")
    def smart_placement_task_detail(task_id: int):
        try:
            return ok(SmartPlacementService(current_app.config).task_detail(g.current_user, task_id))
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 404
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/smart-placement/tasks/<int:task_id>")
    def update_smart_placement_task(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).update_task(g.current_user, task_id, json_body()),
                "投放机会已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.delete("/v1/smart-placement/tasks/<int:task_id>")
    def delete_smart_placement_task(task_id: int):
        try:
            return ok(SmartPlacementService(current_app.config).delete_task(g.current_user, task_id), "投放任务已删除")
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/withdraw")
    def withdraw_smart_placement_task(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).withdraw_task(g.current_user, task_id), "投放任务已撤回"
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/cancel")
    def cancel_smart_placement_task(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).cancel_task(g.current_user, task_id, json_body()),
                "投放任务已作废",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/reviews")
    def review_smart_placement_task(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).review_task(g.current_user, task_id, json_body()),
                "审核结果已提交",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/reviews/batch")
    def batch_review_smart_placement_tasks():
        try:
            return ok(
                SmartPlacementService(current_app.config).batch_review_tasks(g.current_user, json_body()),
                "批量审核结果已提交",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/claim")
    def claim_smart_placement_task(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).claim_task(g.current_user, task_id, json_body()),
                "任务认领成功",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/executions")
    def register_smart_placement_execution(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).register_execution(g.current_user, task_id, json_body()),
                "投放结果已登记",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/smart-placement/tasks/<int:task_id>/monitoring")
    def smart_placement_task_monitoring(task_id: int):
        try:
            placement = SmartPlacementService(current_app.config)
            placement.task_detail(g.current_user, task_id)
            result = MonitoringService(current_app.config).task_monitoring(g.current_user, task_id)
            result["effectSummary"] = placement.effect_summary(g.current_user, task_id)["summary"]
            return ok(result)
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503
        except MonitoringUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/stop")
    def stop_smart_placement_monitoring(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).stop_monitoring(g.current_user, task_id, json_body()),
                "投放监控已停止",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.post("/v1/smart-placement/tasks/<int:task_id>/effect-reviews")
    def create_smart_placement_effect_review(task_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).create_effect_review(g.current_user, task_id, json_body()),
                "政策效果复盘已保存",
            ), 201
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/smart-placement/orders")
    def smart_placement_orders():
        try:
            return ok(
                SmartPlacementService(current_app.config).list_orders(
                    user=g.current_user,
                    start_date=request.args.get("startDate", ""),
                    end_date=request.args.get("endDate", ""),
                    attention_status=request.args.get("attentionStatus", ""),
                    platform=request.args.get("platform", ""),
                    airline=request.args.get("airline", ""),
                    owner=request.args.get("owner", ""),
                    keyword=request.args.get("keyword", ""),
                    page=int(request.args.get("page", "1")),
                    page_size=int(request.args.get("pageSize", "30")),
                )
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.patch("/v1/smart-placement/orders/<int:match_id>/attention")
    def update_smart_placement_attention(match_id: int):
        try:
            return ok(
                SmartPlacementService(current_app.config).update_attention(g.current_user, match_id, json_body()),
                "订单关注状态已更新",
            )
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except SmartPlacementUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503
