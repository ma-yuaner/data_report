from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request
from ..services.smart_analysis import DIMENSIONS as SMART_DIMENSIONS, SmartAnalysisService
from ..services.smart_view_template import SmartViewTemplateService
from ..services.smart_placement import SmartPlacementService, SmartPlacementUnavailable
from .common import ok, smart_excel_response


def register_routes(api: Blueprint) -> None:
    def smart_filters() -> dict[str, str | None]:
        return {key: request.args.get(key) for key in (*SMART_DIMENSIONS, "otaOrderNo")}

    def smart_period_args() -> dict[str, str | None]:
        return {
            "start_value": request.args.get("startDate"),
            "end_value": request.args.get("endDate"),
            "first_dep_start": request.args.get("firstDepStart"),
            "first_dep_end": request.args.get("firstDepEnd"),
            "order_start": request.args.get("orderStart"),
            "order_end": request.args.get("orderEnd"),
        }

    @api.get("/v1/smart-analysis/templates")
    def smart_analysis_templates():
        try:
            return ok(SmartViewTemplateService(current_app.config).list(g.current_user, request.args.get("scope")))
        except (ValueError, PermissionError) as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400 if isinstance(
                error, ValueError
            ) else 403

    @api.post("/v1/smart-analysis/templates")
    def save_smart_analysis_template():
        try:
            return ok(
                SmartViewTemplateService(current_app.config).save(g.current_user, request.get_json(silent=True) or {})
            )
        except (ValueError, PermissionError) as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400 if isinstance(
                error, ValueError
            ) else 403

    @api.delete("/v1/smart-analysis/templates/<int:template_id>")
    def delete_smart_analysis_template(template_id: int):
        try:
            return ok(SmartViewTemplateService(current_app.config).delete(g.current_user, template_id))
        except (ValueError, PermissionError) as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400 if isinstance(
                error, ValueError
            ) else 403

    @api.get("/v1/smart-analysis/comprehensive")
    def smart_analysis_comprehensive():
        try:
            period_args = smart_period_args()
            filters = smart_filters()
            analysis = SmartAnalysisService(current_app.config)
            overview = analysis.overview(**period_args, filters=filters, trend_date="issue")
            dimensions = analysis.dimensions(
                **period_args,
                filters=filters,
                group_by=request.args.get("groupBy", "platform"),
                smart_type=request.args.get("smartType", "all"),
                sort_by=request.args.get("sortBy", "smartProfit"),
                direction=request.args.get("direction", "desc"),
                page_value=request.args.get("page", "1"),
                page_size_value=request.args.get("pageSize", "20"),
            )
            coverage_start = period_args["start_value"] or period_args["order_start"] or period_args["first_dep_start"]
            coverage_end = period_args["end_value"] or period_args["order_end"] or period_args["first_dep_end"]
            try:
                placement = SmartPlacementService(current_app.config).analysis_coverage(
                    user=g.current_user,
                    start_value=coverage_start,
                    end_value=coverage_end,
                    filters=filters,
                )
            except (SmartPlacementUnavailable, PermissionError) as error:
                placement = {
                    "available": False,
                    "error": str(error),
                    "truncated": False,
                    "period": {"startDate": coverage_start or "", "endDate": coverage_end or ""},
                    "summary": {
                        "taskCount": 0,
                        "monitoringTaskCount": 0,
                        "workflowTaskCount": 0,
                        "matchedOrderCount": 0,
                        "statusCounts": {},
                    },
                    "rows": [],
                }
            return ok({"overview": overview, "dimensions": dimensions, "placement": placement})
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/overview")
    def smart_analysis_overview():
        try:
            return ok(
                SmartAnalysisService(current_app.config).overview(
                    **smart_period_args(),
                    filters=smart_filters(),
                    trend_date=request.args.get("trendDate", "issue"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/trends")
    def smart_analysis_trends():
        try:
            return ok(
                SmartAnalysisService(current_app.config).trends(
                    **smart_period_args(),
                    filters=smart_filters(),
                    trend_date=request.args.get("trendDate", "issue"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/dimensions")
    def smart_analysis_dimensions():
        try:
            return ok(
                SmartAnalysisService(current_app.config).dimensions(
                    **smart_period_args(),
                    filters=smart_filters(),
                    group_by=request.args.get("groupBy", "airline,platform"),
                    smart_type=request.args.get("smartType", "all"),
                    sort_by=request.args.get("sortBy", "smartProfit"),
                    direction=request.args.get("direction", "desc"),
                    page_value=request.args.get("page", "1"),
                    page_size_value=request.args.get("pageSize", "20"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/details")
    def smart_analysis_details():
        try:
            return ok(
                SmartAnalysisService(current_app.config).details(
                    **smart_period_args(),
                    filters=smart_filters(),
                    smart_type=request.args.get("smartType", "all"),
                    stage=request.args.get("stage", "all"),
                    fields_value=request.args.get("fields"),
                    page_value=request.args.get("page", "1"),
                    page_size_value=request.args.get("pageSize", "20"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/filter-options")
    def smart_analysis_filter_options():
        try:
            return ok(
                SmartAnalysisService(current_app.config).filter_options(
                    **smart_period_args(),
                    filters=smart_filters(),
                    field=request.args.get("field", ""),
                    search=request.args.get("search"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/tickets/<issue_id>")
    def smart_analysis_ticket(issue_id: str):
        try:
            return ok(SmartAnalysisService(current_app.config).ticket(issue_id))
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/exports/trend")
    def smart_analysis_export_trend():
        try:
            return smart_excel_response(
                SmartAnalysisService(current_app.config).export_trend(
                    **smart_period_args(),
                    filters=smart_filters(),
                    kind=request.args.get("kind", "daily"),
                    smart_type=request.args.get("smartType", "all"),
                    trend_date=request.args.get("trendDate", "issue"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/exports/dimensions")
    def smart_analysis_export_dimensions():
        try:
            return smart_excel_response(
                SmartAnalysisService(current_app.config).export_dimensions(
                    **smart_period_args(),
                    filters=smart_filters(),
                    group_by=request.args.get("groupBy", "airline,platform"),
                    metrics_value=request.args.get("metrics", "ticketCount,smartUsed,smartProfit"),
                    smart_type=request.args.get("smartType", "all"),
                    sort_by=request.args.get("sortBy", "smartProfit"),
                    direction=request.args.get("direction", "desc"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/smart-analysis/exports/details")
    def smart_analysis_export_details():
        try:
            return smart_excel_response(
                SmartAnalysisService(current_app.config).export_details(
                    **smart_period_args(),
                    filters=smart_filters(),
                    smart_type=request.args.get("smartType", "all"),
                    stage=request.args.get("stage", "all"),
                    fields_value=request.args.get("fields"),
                    all_fields=request.args.get("scope", "visible") == "all",
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
