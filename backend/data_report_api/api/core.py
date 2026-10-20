from __future__ import annotations
from flask import Blueprint, current_app
from ..time_utils import business_now
from ..services.dashboard import DashboardService
from ..services.asset_catalog import AssetCatalogService
from ..services.data_source import DataSource, data_mode, is_live_mode
from .common import ok


def register_routes(api: Blueprint) -> None:
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
                "disclaimer": f"当前接入{source.engine_label}实际业务数据，利润为业务估算口径，不代表财务结算。"
                if source
                else "当前为MVP演示数据，不代表正式经营或财务口径。",
            }
        )

    @api.get("/v1/issues")
    def issues():
        return ok(DashboardService().issues())

    @api.get("/v1/assets/coverage")
    def asset_coverage():
        return ok(DashboardService().asset_coverage())

    @api.get("/v1/assets/catalog")
    def asset_catalog():
        return ok(AssetCatalogService(current_app.config).catalog())
