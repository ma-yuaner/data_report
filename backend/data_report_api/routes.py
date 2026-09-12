from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from .services.dashboard import DashboardService
from .services.asset_catalog import AssetCatalogService
from .services.business_profit_analysis import BusinessProfitAnalysisService
from .services.issue_profit_analysis import IssueProfitAnalysisService


api = Blueprint("api", __name__)


def ok(data, message: str = "OK"):
    return jsonify({"success": True, "message": message, "data": data})


@api.get("/health")
def health():
    return ok(
        {
            "status": "UP",
            "service": "data-report-api",
            "dataMode": current_app.config["DATA_MODE"],
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )


@api.get("/v1/meta")
def meta():
    is_live = str(current_app.config["DATA_MODE"]).lower() == "hive"
    return ok(
        {
            "productName": "企业数据中心",
            "businessDomain": "机票业务",
            "version": "0.1.0",
            "environment": current_app.config["APP_ENV"],
            "dataMode": current_app.config["DATA_MODE"],
            "disclaimer": "当前接入Hive实际业务数据，利润为业务估算口径，不代表财务结算。" if is_live else "当前为MVP演示数据，不代表正式经营或财务口径。",
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


@api.get("/v1/issues")
def issues():
    return ok(DashboardService().issues())


@api.get("/v1/assets/coverage")
def asset_coverage():
    return ok(DashboardService().asset_coverage())


@api.get("/v1/assets/catalog")
def asset_catalog():
    return ok(AssetCatalogService(current_app.config).catalog())
