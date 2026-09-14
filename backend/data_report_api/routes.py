from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from .services.dashboard import DashboardService
from .services.asset_catalog import AssetCatalogService
from .services.business_profit_analysis import BusinessProfitAnalysisService
from .services.issue_profit_analysis import IssueProfitAnalysisService
from .services.profit_problem_center import ProfitProblemCenterService
from .services.data_source import DataSource, data_mode, is_live_mode


api = Blueprint("api", __name__)


def ok(data, message: str = "OK"):
    return jsonify({"success": True, "message": message, "data": data})


@api.get("/health")
def health():
    mode = data_mode(current_app.config)
    return ok(
        {
            "status": "UP",
            "service": "data-report-api",
            "dataMode": mode,
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
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
