from __future__ import annotations
from flask import Blueprint, current_app, jsonify, request
from ..services.resource_governance import ResourceGovernanceService
from ..services.gds_route_analysis import GdsRouteAnalysisService, GdsRouteAnalysisUnavailable
from .common import ok, smart_excel_response


def register_routes(api: Blueprint) -> None:
    def _resource_governance_overview(data_source: str):
        breach_only = str(request.args.get("breachOnly") or "").strip().lower() in {"1", "true", "yes"}
        try:
            return ok(
                ResourceGovernanceService(current_app.config).overview(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    data_source=data_source,
                    group_by=request.args.get("groupBy"),
                    filters={
                        key: request.args.get(key, "")
                        for key in ("platform", "site", "gds", "resourceChannel", "pcc", "apiGroup")
                    },
                    breach_only=breach_only,
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/resource-governance/gds/overview")
    def gds_resource_governance_overview():
        return _resource_governance_overview("gds")

    @api.get("/v1/resource-governance/gds/routes")
    def gds_route_analysis():
        try:
            return ok(
                GdsRouteAnalysisService(current_app.config).overview(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    filters={
                        key: request.args.get(key, "")
                        for key in (
                            "platform",
                            "site",
                            "gds",
                            "pcc",
                            "resourceChannel",
                            "apiGroup",
                            "route",
                            "keyword",
                        )
                    },
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
        except GdsRouteAnalysisUnavailable as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 503

    @api.get("/v1/resource-governance/ota/overview")
    def ota_resource_governance_overview():
        return _resource_governance_overview("ota")

    def _resource_governance_export(data_source: str):
        breach_only = str(request.args.get("breachOnly") or "").strip().lower() in {"1", "true", "yes"}
        try:
            return smart_excel_response(
                ResourceGovernanceService(current_app.config).export_report(
                    start_value=request.args.get("startDate"),
                    end_value=request.args.get("endDate"),
                    data_source=data_source,
                    group_by=request.args.get("groupBy"),
                    filters={
                        key: request.args.get(key, "")
                        for key in ("platform", "site", "gds", "resourceChannel", "pcc", "apiGroup")
                    },
                    breach_only=breach_only,
                )
            )
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400

    @api.get("/v1/resource-governance/gds/export")
    def gds_resource_governance_export():
        return _resource_governance_export("gds")

    @api.get("/v1/resource-governance/ota/export")
    def ota_resource_governance_export():
        return _resource_governance_export("ota")
