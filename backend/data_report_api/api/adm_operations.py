"""HTTP adapter for approved operations and immutable reporting."""
from functools import wraps

from flask import request

from ..services.adm.operations import OperationsService, unavailable
from ..services.adm.reports import ReportService
from ..services.adm.store import Conflict, StoreUnavailable
from .adm import adm_response
from .common import json_body


def operational(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (Conflict, StoreUnavailable) as error:
            raise unavailable(error) from error
    return adm_response(wrapped)


def register_routes(api):
    @api.get("/v1/adm/operations/config")
    @operational
    def adm_operation_config(service, user):
        return OperationsService(service).config(user)

    @api.put("/v1/adm/operations/config")
    @operational
    def adm_operation_config_save(service, user):
        return OperationsService(service).configure(user, json_body())

    @api.post("/v1/adm/operations/preview")
    @operational
    def adm_operation_preview(service, user):
        return OperationsService(service).preview(user)

    @api.get("/v1/adm/operations/inbox")
    @operational
    def adm_operation_inbox(service, user):
        return OperationsService(service).inbox(user)

    @api.post("/v1/adm/operations/inbox/<record_id>/read")
    @operational
    def adm_operation_read(service, user, record_id):
        return OperationsService(service).read(user, record_id, json_body())

    @api.get("/v1/adm/operations/deliveries")
    @operational
    def adm_operation_deliveries(service, user):
        return OperationsService(service).deliveries(user)

    @api.get("/v1/adm/reports")
    @operational
    def adm_reports(service, user):
        return ReportService(service).listing(user, request.args.get("date", ""))

    @api.post("/v1/adm/reports/capture")
    @operational
    def adm_report_capture(service, user):
        return ReportService(service).capture(user, json_body())

    @api.get("/v1/adm/reports/<record_id>")
    @operational
    def adm_report_detail(service, user, record_id):
        return ReportService(service).detail(user, record_id, request.args.get("scope", "mine"))

    @api.post("/v1/adm/reports/<record_id>/publish")
    @operational
    def adm_report_publish(service, user, record_id):
        return ReportService(service).publish(user, record_id, json_body())
