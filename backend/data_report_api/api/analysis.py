from __future__ import annotations
from flask import Blueprint, current_app, jsonify, request
from ..services.business_profit_analysis import BusinessProfitAnalysisService
from ..services.comprehensive_analysis import ComprehensiveAnalysisService, DIMENSIONS
from ..services.comprehensive_detail import ComprehensiveDetailService
from ..services.risk_monthly_analysis import RiskMonthlyAnalysisService
from ..services.risk_business_analysis import RiskBusinessAnalysisService
from ..services.issue_profit_analysis import IssueProfitAnalysisService
from ..services.profit_problem_center import ProfitProblemCenterService
from .common import ok


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
