from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .time_utils import business_now

from .services.dashboard import DashboardService
from .services.asset_catalog import AssetCatalogService
from .services.business_profit_analysis import BusinessProfitAnalysisService
from .services.comprehensive_analysis import ComprehensiveAnalysisService, DIMENSIONS
from .services.comprehensive_detail import ComprehensiveDetailService
from .services.risk_monthly_analysis import RiskMonthlyAnalysisService
from .services.risk_business_analysis import RiskBusinessAnalysisService
from .services.issue_profit_analysis import IssueProfitAnalysisService
from .services.profit_problem_center import ProfitProblemCenterService
from .services.risk_profit_summary import RISK_FILTER_FIELDS, RiskProfitSummaryService
from .services.risk_upload import RiskUploadService
from .services.data_source import DataSource, data_mode, is_live_mode
from .services.telemetry import TelemetryService, TelemetryUnavailable
from .services.smart_analysis import DIMENSIONS as SMART_DIMENSIONS, SmartAnalysisService
from .services.smart_placement import SmartPlacementService, SmartPlacementUnavailable
from .services.monitoring import MonitoringService, MonitoringUnavailable
from .services.resource_governance import ResourceGovernanceService


api = Blueprint("api", __name__)


def ok(data, message: str = "OK"):
    return jsonify({"success": True, "message": message, "data": data})


def json_body() -> dict:
    values = request.get_json(silent=True)
    if not isinstance(values, dict):
        raise ValueError("请求内容必须为JSON对象")
    return values


@api.get("/health")
def health():
    mode = data_mode(current_app.config)
    return ok(
        {
            "status": "UP",
            "service": "data-report-api",
            "dataMode": mode,
            "time": business_now().isoformat(timespec="seconds"),
        }
    )


@api.get("/v1/meta")
def meta():
    mode = data_mode(current_app.config)
    source = DataSource(current_app.config) if is_live_mode(mode) else None
    return ok(
        {
            "productName": "企业数据中心",
            "businessDomain": "机票业务",
            "version": "0.1.0",
            "environment": current_app.config["APP_ENV"],
            "dataMode": mode,
            "dataSource": source.label if source else "演示数据",
            "disclaimer": f"当前接入{source.engine_label}实际业务数据，利润为业务估算口径，不代表财务结算。" if source else "当前为MVP演示数据，不代表正式经营或财务口径。",
        }
    )


def _resource_governance_overview(data_source: str):
    breach_only = str(request.args.get("breachOnly") or "").strip().lower() in {"1", "true", "yes"}
    try:
        return ok(ResourceGovernanceService(current_app.config).overview(
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
            data_source=data_source,
            group_by=request.args.get("groupBy"),
            filters={
                key: request.args.get(key, "")
                for key in ("platform", "site", "gds", "pcc", "apiGroup")
            },
            breach_only=breach_only,
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/resource-governance/gds/overview")
def gds_resource_governance_overview():
    return _resource_governance_overview("gds")


@api.get("/v1/resource-governance/ota/overview")
def ota_resource_governance_overview():
    return _resource_governance_overview("ota")


@api.post("/v1/telemetry/visits")
def start_telemetry_visit():
    try:
        return ok(TelemetryService(current_app.config).start_visit(
            g.current_user, getattr(g, "current_session", {}), json_body()
        ), "页面访问已记录"), 201
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except TelemetryUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.patch("/v1/telemetry/visits/<visit_id>")
def update_telemetry_visit(visit_id: str):
    try:
        return ok(TelemetryService(current_app.config).update_visit(
            g.current_user, visit_id, json_body()
        ), "页面访问已更新")
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except TelemetryUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/telemetry/events")
def record_telemetry_events():
    try:
        return ok(TelemetryService(current_app.config).record_events(
            g.current_user, getattr(g, "current_session", {}), json_body()
        ), "行为事件已记录"), 202
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except TelemetryUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.get("/v1/admin/telemetry/dashboard")
def telemetry_dashboard():
    try:
        return ok(TelemetryService(current_app.config).dashboard(
            g.current_user,
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
        ))
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/dashboard/overview")
def overview():
    try:
        return ok(
            DashboardService().overview(
                start_date=request.args.get("startDate"),
                end_date=request.args.get("endDate"),
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/dashboard/risk-profit-summary")
def risk_profit_summary():
    try:
        return ok(
            RiskProfitSummaryService(current_app.config).summary(
                start_value=request.args.get("startDate"),
                end_value=request.args.get("endDate"),
                filters={key: request.args.get(key) for key in (*RISK_FILTER_FIELDS, "profitStatus")},
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/dashboard/risk-profit-filter-options")
def risk_profit_filter_options():
    try:
        return ok(
            RiskProfitSummaryService(current_app.config).filter_options(
                start_value=request.args.get("startDate"),
                end_value=request.args.get("endDate"),
                field=request.args.get("field"),
                search=request.args.get("search"),
                filters={key: request.args.get(key) for key in (*RISK_FILTER_FIELDS, "profitStatus")},
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/comprehensive")
def comprehensive_analysis():
    try:
        return ok(ComprehensiveAnalysisService(current_app.config).analysis(
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
            group=request.args.get("groupBy", "platform"),
            filters={key: request.args.get(key) for key in DIMENSIONS},
            sort=request.args.get("sortBy", "segments"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/comprehensive/diagnosis")
def comprehensive_diagnosis():
    try:
        return ok(ComprehensiveAnalysisService(current_app.config).diagnosis(
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
            group=request.args.get("groupBy", "platform"),
            filters={key: request.args.get(key) for key in DIMENSIONS},
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/comprehensive/details")
def comprehensive_details():
    try:
        return ok(ComprehensiveDetailService(current_app.config).details(
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
            business=request.args.get("businessType", ""),
            filters={key: request.args.get(key) for key in DIMENSIONS},
            page_value=request.args.get("page", "1"),
            page_size_value=request.args.get("pageSize", "50"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


def smart_filters() -> dict[str, str | None]:
    return {key: request.args.get(key) for key in SMART_DIMENSIONS}


def smart_period_args() -> dict[str, str | None]:
    return {
        "start_value": request.args.get("startDate"),
        "end_value": request.args.get("endDate"),
        "first_dep_start": request.args.get("firstDepStart"),
        "first_dep_end": request.args.get("firstDepEnd"),
        "order_start": request.args.get("orderStart"),
        "order_end": request.args.get("orderEnd"),
    }


@api.get("/v1/smart-analysis/overview")
def smart_analysis_overview():
    try:
        return ok(SmartAnalysisService(current_app.config).overview(
            **smart_period_args(), filters=smart_filters(),
            trend_date=request.args.get("trendDate", "issue"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/trends")
def smart_analysis_trends():
    try:
        return ok(SmartAnalysisService(current_app.config).trends(
            **smart_period_args(), filters=smart_filters(),
            trend_date=request.args.get("trendDate", "issue"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/dimensions")
def smart_analysis_dimensions():
    try:
        return ok(SmartAnalysisService(current_app.config).dimensions(
            **smart_period_args(), filters=smart_filters(),
            group_by=request.args.get("groupBy", "airline,platform"),
            smart_type=request.args.get("smartType", "all"),
            sort_by=request.args.get("sortBy", "smartProfit"),
            direction=request.args.get("direction", "desc"),
            page_value=request.args.get("page", "1"),
            page_size_value=request.args.get("pageSize", "20"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/details")
def smart_analysis_details():
    try:
        return ok(SmartAnalysisService(current_app.config).details(
            **smart_period_args(), filters=smart_filters(),
            smart_type=request.args.get("smartType", "all"),
            stage=request.args.get("stage", "all"),
            fields_value=request.args.get("fields"),
            page_value=request.args.get("page", "1"),
            page_size_value=request.args.get("pageSize", "20"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/filter-options")
def smart_analysis_filter_options():
    try:
        return ok(SmartAnalysisService(current_app.config).filter_options(
            **smart_period_args(), filters=smart_filters(),
            field=request.args.get("field", ""), search=request.args.get("search"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/tickets/<issue_id>")
def smart_analysis_ticket(issue_id: str):
    try:
        return ok(SmartAnalysisService(current_app.config).ticket(issue_id))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


def smart_excel_response(result):
    content, filename = result
    return send_file(
        content,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@api.get("/v1/smart-analysis/exports/trend")
def smart_analysis_export_trend():
    try:
        return smart_excel_response(SmartAnalysisService(current_app.config).export_trend(
            **smart_period_args(), filters=smart_filters(),
            kind=request.args.get("kind", "daily"),
            smart_type=request.args.get("smartType", "all"),
            trend_date=request.args.get("trendDate", "issue"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/exports/dimensions")
def smart_analysis_export_dimensions():
    try:
        return smart_excel_response(SmartAnalysisService(current_app.config).export_dimensions(
            **smart_period_args(), filters=smart_filters(),
            group_by=request.args.get("groupBy", "airline,platform"),
            metrics_value=request.args.get("metrics", "ticketCount,smartUsed,smartProfit"),
            smart_type=request.args.get("smartType", "all"),
            sort_by=request.args.get("sortBy", "smartProfit"),
            direction=request.args.get("direction", "desc"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-analysis/exports/details")
def smart_analysis_export_details():
    try:
        return smart_excel_response(SmartAnalysisService(current_app.config).export_details(
            **smart_period_args(), filters=smart_filters(),
            smart_type=request.args.get("smartType", "all"),
            stage=request.args.get("stage", "all"),
            fields_value=request.args.get("fields"),
            all_fields=request.args.get("scope", "visible") == "all",
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/smart-placement/tasks")
def smart_placement_tasks():
    try:
        return ok(SmartPlacementService(current_app.config).list_tasks(
            user=g.current_user,
            status=request.args.get("status", ""),
            keyword=request.args.get("keyword", ""),
            platform=request.args.get("platform", ""),
            airline=request.args.get("airline", ""),
            owner=request.args.get("owner", ""),
            scope=request.args.get("scope", ""),
            page=int(request.args.get("page", "1")),
            page_size=int(request.args.get("pageSize", "30")),
        ))
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
        return ok(SmartPlacementService(current_app.config).create_task(g.current_user, json_body()), "投放机会已保存"), 201
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
        return ok(SmartPlacementService(current_app.config).update_task(g.current_user, task_id, json_body()), "投放机会已更新")
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
        return ok(SmartPlacementService(current_app.config).withdraw_task(g.current_user, task_id), "投放任务已撤回")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/smart-placement/tasks/<int:task_id>/cancel")
def cancel_smart_placement_task(task_id: int):
    try:
        return ok(SmartPlacementService(current_app.config).cancel_task(g.current_user, task_id, json_body()), "投放任务已作废")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/smart-placement/tasks/<int:task_id>/reviews")
def review_smart_placement_task(task_id: int):
    try:
        return ok(SmartPlacementService(current_app.config).review_task(g.current_user, task_id, json_body()), "审核结果已提交")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/smart-placement/tasks/<int:task_id>/claim")
def claim_smart_placement_task(task_id: int):
    try:
        return ok(SmartPlacementService(current_app.config).claim_task(g.current_user, task_id, json_body()), "任务认领成功")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/smart-placement/tasks/<int:task_id>/executions")
def register_smart_placement_execution(task_id: int):
    try:
        return ok(SmartPlacementService(current_app.config).register_execution(g.current_user, task_id, json_body()), "投放结果已登记")
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
            SmartPlacementService(current_app.config).stop_monitoring(
                g.current_user, task_id, json_body()
            ),
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
            SmartPlacementService(current_app.config).create_effect_review(
                g.current_user, task_id, json_body()
            ),
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
        return ok(SmartPlacementService(current_app.config).list_orders(
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
        ))
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.patch("/v1/smart-placement/orders/<int:match_id>/attention")
def update_smart_placement_attention(match_id: int):
    try:
        return ok(SmartPlacementService(current_app.config).update_attention(g.current_user, match_id, json_body()), "订单关注状态已更新")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except SmartPlacementUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


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
        return ok(MonitoringService(current_app.config).list_rules(
            g.current_user,
            status=request.args.get("status", ""),
            template=request.args.get("template", ""),
            keyword=request.args.get("keyword", ""),
            page=int(request.args.get("page", "1")),
            page_size=int(request.args.get("pageSize", "30")),
        ))
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
        return ok(MonitoringService(current_app.config).update_rule_status(g.current_user, rule_id, json_body()), "监控规则状态已更新")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except MonitoringUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.get("/v1/monitoring/rules/<int:rule_id>/diagnose")
def diagnose_monitoring_rule(rule_id: int):
    try:
        return ok(MonitoringService(current_app.config).diagnose_rule(
            g.current_user, rule_id, request.args.get("otaOrderNo", ""),
        ))
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except MonitoringUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.get("/v1/monitoring/events")
def monitoring_events():
    try:
        return ok(MonitoringService(current_app.config).list_events(
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
        ))
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
        return ok(MonitoringService(current_app.config).list_runs(
            g.current_user,
            job_type=request.args.get("jobType", ""),
            status=request.args.get("status", ""),
            limit=int(request.args.get("limit", "100")),
        ))
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
        return ok(MonitoringService(current_app.config).save_notify_endpoint(g.current_user, json_body()), "通知群已创建")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except MonitoringUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.put("/v1/monitoring/notify-endpoints/<int:endpoint_id>")
def update_monitoring_notify_endpoint(endpoint_id: int):
    try:
        return ok(MonitoringService(current_app.config).save_notify_endpoint(g.current_user, json_body(), endpoint_id), "通知群已更新")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except MonitoringUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.post("/v1/monitoring/notify-endpoints/<int:endpoint_id>/test")
def test_monitoring_notify_endpoint(endpoint_id: int):
    try:
        return ok(MonitoringService(current_app.config).test_notify_endpoint(g.current_user, endpoint_id), "测试消息发送成功")
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
            MonitoringService(current_app.config).update_message_template(
                g.current_user, template_id, json_body()
            ),
            "消息模板已更新",
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
            MonitoringService(current_app.config).save_notify_route(
                g.current_user, json_body()
            ),
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
            MonitoringService(current_app.config).save_notify_route(
                g.current_user, json_body(), route_id
            ),
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
        return ok(MonitoringService(current_app.config).update_event_status(g.current_user, event_id, json_body()), "监控事件已更新")
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400
    except MonitoringUnavailable as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 503


@api.get("/v1/analysis/risk-monthly")
def risk_monthly_analysis():
    try:
        return ok(RiskMonthlyAnalysisService(current_app.config).analysis(
            start_value=request.args.get("startDate"), end_value=request.args.get("endDate"),
            business_type=request.args.get("businessType", "all"),
            profit_status=request.args.get("profitStatus", "all"),
            date_basis=request.args.get("dateBasis", "reconcile"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/risk-daily")
def risk_daily_analysis():
    try:
        return ok(RiskMonthlyAnalysisService(current_app.config).daily(
            start_value=request.args.get("startDate"), end_value=request.args.get("endDate"),
            business_type=request.args.get("businessType", "all"),
            profit_status=request.args.get("profitStatus", "all"),
            date_basis=request.args.get("dateBasis", "reconcile"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/risk-business/<business_type>")
def risk_business_analysis(business_type: str):
    try:
        return ok(RiskBusinessAnalysisService(current_app.config).analysis(
            business_type=business_type,
            start_value=request.args.get("startDate"),
            end_value=request.args.get("endDate"),
            group=request.args.get("groupBy", "platform"),
            filters={
                key: request.args.get(key)
                for key in (
                    "platform", "site", "department", "airline", "supplier",
                    "policy", "reason", "verifyResult", "profitStatus",
                )
            },
            page_value=request.args.get("page", "1"),
            page_size_value=request.args.get("pageSize", "30"),
        ))
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/risk-uploads")
def risk_upload_status():
    return ok(
        RiskUploadService(current_app.config).status(
            request.headers.get("X-Risk-Upload-Token")
        )
    )


@api.post("/v1/risk-uploads")
def create_risk_upload():
    try:
        job = RiskUploadService(current_app.config).submit(
            business_type=request.form.get("businessType", ""),
            upload=request.files.get("file"),
            sheet_name=request.form.get("sheetName"),
            load_date=request.form.get("loadDate"),
            confirmed=request.form.get("confirmOverwrite", "").lower() == "true",
            token=request.headers.get("X-Risk-Upload-Token"),
        )
        return ok(job, "上传成功，任务已进入Hive导入队列"), 202
    except PermissionError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 403
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/issue-profit")
def issue_profit_analysis():
    try:
        return ok(
            IssueProfitAnalysisService(current_app.config).analysis(
                start_value=request.args.get("startDate"),
                end_value=request.args.get("endDate"),
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/analysis/business-profit/<business_type>")
def business_profit_analysis(business_type: str):
    try:
        return ok(
            BusinessProfitAnalysisService(current_app.config).analysis(
                business_type=business_type,
                start_value=request.args.get("startDate"),
                end_value=request.args.get("endDate"),
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/problems/profit-loss")
def profit_loss_problems():
    try:
        return ok(
            ProfitProblemCenterService(current_app.config).problems(
                start_value=request.args.get("startDate"),
                end_value=request.args.get("endDate"),
            )
        )
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "data": None}), 400


@api.get("/v1/issues")
def issues():
    return ok(DashboardService().issues())


@api.get("/v1/assets/coverage")
def asset_coverage():
    return ok(DashboardService().asset_coverage())


@api.get("/v1/assets/catalog")
def asset_catalog():
    return ok(AssetCatalogService(current_app.config).catalog())
