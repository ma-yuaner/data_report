"""ADM HTTP adapter; rules live in the public application service."""

from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from ..services.adm import AdmError, AdmService
from ..services.adm.workflow import WorkflowService
from .common import json_body, ok


def adm_response(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return ok(function(AdmService(current_app.config), g.current_user, *args, **kwargs))
        except AdmError as error:
            return jsonify({"success": False, "message": error.message, "code": error.code, "data": None}), error.status
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "code": "ADM_INVALID", "data": None}), 400

    return wrapped


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/adm/workflow/overview")
    @adm_response
    def adm_workflow_overview(service, user):
        return WorkflowService(service).overview(user, request.args)

    @api.get("/v1/adm/config")
    @adm_response
    def adm_config(service, user):
        return service.config_info(user)

    @api.get("/v1/adm/cases")
    @adm_response
    def adm_cases(service, user):
        return service.list_cases(user, request.args)

    @api.post("/v1/adm/cases")
    @adm_response
    def adm_create(service, user):
        body = json_body()
        body.pop("source", None)
        if isinstance(body.get("lines"), list):
            for line in body["lines"]:
                if isinstance(line, dict):
                    line.pop("source", None)
        return service.create_case(user, body)

    @api.get("/v1/adm/cases/<case_id>")
    @adm_response
    def adm_detail(service, user, case_id):
        return service.case_detail(user, case_id)

    @api.patch("/v1/adm/cases/<case_id>")
    @adm_response
    def adm_update(service, user, case_id):
        return service.update_case(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/copy")
    @adm_response
    def adm_copy(service, user, case_id):
        return service.copy_case(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines")
    @adm_response
    def adm_add_line(service, user, case_id):
        return service.add_line(user, case_id, json_body())

    @api.patch("/v1/adm/cases/<case_id>/lines/<line_id>")
    @adm_response
    def adm_update_line(service, user, case_id, line_id):
        return service.update_line(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/bulk-assign")
    @adm_response
    def adm_bulk_assign(service, user, case_id):
        return service.bulk_assign(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/actions")
    @adm_response
    def adm_case_action(service, user, case_id):
        return service.case_action(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/actions")
    @adm_response
    def adm_line_action(service, user, case_id, line_id):
        return service.line_action(user, case_id, line_id, json_body())

    @api.get("/v1/adm/cases/<case_id>/closure-check")
    @adm_response
    def adm_closure_check(service, user, case_id):
        return service.closure_check(user, case_id)

    @api.get("/v1/adm/cases/<case_id>/timeline")
    @adm_response
    def adm_timeline(service, user, case_id):
        return service.timeline(user, case_id)
