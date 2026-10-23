from __future__ import annotations
from flask import Blueprint, current_app, g, jsonify, request, send_file
from ..services.business_profit_analysis import BusinessProfitAnalysisService
from ..services.comprehensive_analysis import ComprehensiveAnalysisService, DIMENSIONS
from ..services.comprehensive_detail import ComprehensiveDetailService
from ..services.comprehensive_export import (
    ComprehensiveExportConflict,
    ComprehensiveExportService,
    ComprehensiveExportUnavailable,
)
from ..services.risk_monthly_analysis import RiskMonthlyAnalysisService
from ..services.risk_business_analysis import RiskBusinessAnalysisService
from ..services.issue_profit_analysis import IssueProfitAnalysisService
from ..services.profit_problem_center import ProfitProblemCenterService
from .common import json_body, ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/analysis/comprehensive")
    def comprehensive_analysis():
        try:
            return ok(
                ComprehensiveAnalysisService(current_app.config).analysis(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    group=request.args.get("groupBy", "platform"),
                    filters={key: request.args.get(key) for key in DIMENSIONS},
                    sort=request.args.get("sortBy", "segments"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/analysis/comprehensive/diagnosis")
    def comprehensive_diagnosis():
        try:
            return ok(
                ComprehensiveAnalysisService(current_app.config).diagnosis(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    group=request.args.get("groupBy", "platform"),
                    filters={key: request.args.get(key) for key in DIMENSIONS},
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/analysis/comprehensive/details")
    def comprehensive_details():
        try:
            return ok(
                ComprehensiveDetailService(current_app.config).details(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    business=request.args.get("businessType", ""),
                    filters={key: request.args.get(key) for key in DIMENSIONS},
                    page_value=request.args.get("page", "1"),
                    page_size_value=request.args.get("pageSize", "50"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    def _export_error(error: Exception):
        if isinstance(error, PermissionError):
            status = 403
        elif isinstance(error, ComprehensiveExportConflict):
            status = 409
        elif isinstance(error, ValueError):
            status = 400
        else:
            status = 503
        return jsonify({"success": False, "message": str(error), "data": None}), status

    @api.get("/v1/analysis/comprehensive/exports")
    def comprehensive_export_list():
        try:
            return ok(
                ComprehensiveExportService(current_app.config).list(
                    g.current_user, request.args.get("limit", 30)
                )
            )
        except (PermissionError, ValueError, ComprehensiveExportUnavailable) as error:
            return _export_error(error)

    @api.post("/v1/analysis/comprehensive/exports")
    def comprehensive_export_create():
        try:
            task = ComprehensiveExportService(current_app.config).create(g.current_user, json_body())
            message = "相同条件的导出任务正在进行" if task.get("reused") else "导出任务已创建"
            return ok(task, message), (200 if task.get("reused") else 202)
        except (
            PermissionError, ValueError, ComprehensiveExportConflict, ComprehensiveExportUnavailable
        ) as error:
            return _export_error(error)

    @api.post("/v1/analysis/comprehensive/exports/<task_id>/cancel")
    def comprehensive_export_cancel(task_id: str):
        try:
            return ok(
                ComprehensiveExportService(current_app.config).cancel(g.current_user, task_id),
                "取消请求已提交",
            )
        except (
            PermissionError, ValueError, ComprehensiveExportConflict, ComprehensiveExportUnavailable
        ) as error:
            return _export_error(error)

    @api.get("/v1/analysis/comprehensive/exports/<task_id>/download")
    def comprehensive_export_download(task_id: str):
        try:
            path, name = ComprehensiveExportService(current_app.config).download(
                g.current_user, task_id
            )
            return send_file(
                path,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=name,
                max_age=0,
            )
        except (
            PermissionError, ValueError, ComprehensiveExportConflict, ComprehensiveExportUnavailable
        ) as error:
            return _export_error(error)

    @api.get("/v1/analysis/risk-monthly")
    def risk_monthly_analysis():
        try:
            return ok(
                RiskMonthlyAnalysisService(current_app.config).analysis(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    business_type=request.args.get("businessType", "all"),
                    profit_status=request.args.get("profitStatus", "all"),
                    date_basis=request.args.get("dateBasis", "reconcile"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/analysis/risk-daily")
    def risk_daily_analysis():
        try:
            return ok(
                RiskMonthlyAnalysisService(current_app.config).daily(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    business_type=request.args.get("businessType", "all"),
                    profit_status=request.args.get("profitStatus", "all"),
                    date_basis=request.args.get("dateBasis", "reconcile"),
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/analysis/risk-business/<business_type>")
    def risk_business_analysis(business_type: str):
        try:
            return ok(
                RiskBusinessAnalysisService(current_app.config).analysis(
                    business_type=business_type,
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    group=request.args.get("groupBy", "platform"),
                    filters={
                        key: request.args.get(key)
                        for key in (
                            "platform",
                            "site",
                            "department",
                            "airline",
                            "supplier",
                            "policy",
                            "reason",
                            "verifyResult",
                            "profitStatus",
                        )
                    },
                    page_value=request.args.get("page", "1"),
                    page_size_value=request.args.get("pageSize", "30"),
                )
            )
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
