from __future__ import annotations
from flask import Blueprint, current_app, jsonify, request
from ..services.dashboard import DashboardService
from ..services.risk_profit_summary import RISK_FILTER_FIELDS, RiskProfitSummaryService
from .common import ok


def register_routes(api: Blueprint) -> None:
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
