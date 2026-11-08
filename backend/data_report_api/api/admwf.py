"""HTTP adapter for the rebuilt ADM workflow module."""

from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..services.admwf import AdmError, AdmWorkflowService
from .common import json_body, ok


def admwf_response(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            service = AdmWorkflowService(current_app.config)
            return ok(function(service, g.current_user, *args, **kwargs))
        except AdmError as error:
            return jsonify({"success": False, "message": error.message, "code": error.code, "data": None}), error.status
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "ADM请求参数无效", "code": "ADM_INVALID", "data": None}), 400
    return wrapped


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/adm/config")
    @admwf_response
    def admwf_config(service, user):
        return service.config_payload(user)

    @api.get("/v1/adm/reference-options/<kind>")
    @admwf_response
    def admwf_reference_options(service, user, kind):
        return service.reference_options(user, kind, request.args)

    @api.get("/v1/adm/exchange-rate")
    @admwf_response
    def admwf_exchange_rate(service, user):
        return service.exchange_rate(user, request.args.get("currency"))

    @api.get("/v1/adm/imports/template")
    def admwf_import_template():
        try:
            service = AdmWorkflowService(current_app.config)
            content = service.import_template(g.current_user)
            return send_file(content, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             as_attachment=True, download_name="ADM19列导入模板.xlsx")
        except AdmError as error:
            return jsonify({"success": False, "message": error.message, "code": error.code, "data": None}), error.status
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "ADM请求参数无效", "code": "ADM_INVALID", "data": None}), 400

    @api.post("/v1/adm/imports/preview")
    @admwf_response
    def admwf_import_preview(service, user):
        upload = request.files.get("file")
        if upload is None:
            raise AdmError("请选择19列ADM导入Excel")
        return service.preview_import(user, upload)

    @api.post("/v1/adm/imports/<batch_no>/commit")
    @admwf_response
    def admwf_import_commit(service, user, batch_no):
        return service.commit_import(user, batch_no)

    @api.get("/v1/adm/cases")
    @admwf_response
    def admwf_cases(service, user):
        return service.list_cases(user, request.args)

    @api.post("/v1/adm/cases")
    @admwf_response
    def admwf_create(service, user):
        return service.create_case(
            user, json_body(), idempotency_key=request.headers.get("Idempotency-Key") or None,
        )

    @api.get("/v1/adm/cases/<case_id>")
    @admwf_response
    def admwf_detail(service, user, case_id):
        return service.case_detail(user, case_id)

    @api.patch("/v1/adm/cases/<case_id>")
    @admwf_response
    def admwf_update_case(service, user, case_id):
        return service.update_case(user, case_id, json_body())

    @api.get("/v1/adm/cases/<case_id>/summary")
    @admwf_response
    def admwf_case_summary(service, user, case_id):
        return service.case_summary(user, case_id)

    @api.post("/v1/adm/cases/<case_id>/lines")
    @admwf_response
    def admwf_add_line(service, user, case_id):
        return service.add_line(user, case_id, json_body())

    @api.patch("/v1/adm/cases/<case_id>/lines/<line_id>")
    @admwf_response
    def admwf_update_line(service, user, case_id, line_id):
        return service.update_line(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/publish")
    @admwf_response
    def admwf_publish_draft(service, user, case_id):
        return service.publish_draft(user, case_id)

    @api.post("/v1/adm/cases/<case_id>/delete-draft")
    @admwf_response
    def admwf_delete_draft(service, user, case_id):
        return service.delete_draft(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/assign-operator")
    @admwf_response
    def admwf_assign_operator(service, user, case_id, line_id):
        return service.assign_operator(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/change-leader")
    @admwf_response
    def admwf_change_leader(service, user, case_id, line_id):
        return service.change_leader(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/transfers")
    @admwf_response
    def admwf_request_transfer(service, user, case_id, line_id):
        return service.request_transfer(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/transfers/<transfer_id>/accept")
    @admwf_response
    def admwf_accept_transfer(service, user, case_id, line_id, transfer_id):
        return service.decide_transfer(user, case_id, line_id, transfer_id, "ACCEPTED", json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/transfers/<transfer_id>/reject")
    @admwf_response
    def admwf_reject_transfer(service, user, case_id, line_id, transfer_id):
        return service.decide_transfer(user, case_id, line_id, transfer_id, "REJECTED", json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/accept")
    @admwf_response
    def admwf_accept(service, user, case_id, line_id):
        return service.accept_line(user, case_id, line_id)

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/investigation-note")
    @admwf_response
    def admwf_investigation_note(service, user, case_id, line_id):
        return service.update_investigation_note(user, case_id, line_id, json_body())

    @api.post("/v1/adm/operator-imports")
    @admwf_response
    def admwf_operator_import(service, user):
        upload = request.files.get("file")
        if upload is None:
            raise AdmError("请选择操作员处理结果Excel")
        dry_run = str(request.form.get("dryRun") or "").strip().lower() in {"1", "true", "yes"}
        return service.import_operator_results(user, upload, dry_run=dry_run)

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/recovery-decision")
    @admwf_response
    def admwf_recovery_decision(service, user, case_id, line_id):
        return service.decide_recovery(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/recovery-confirm")
    @admwf_response
    def admwf_recovery_confirm(service, user, case_id, line_id):
        return service.confirm_recovery(user, case_id, line_id)

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/appeals")
    @admwf_response
    def admwf_start_appeal(service, user, case_id, line_id):
        return service.start_appeal(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/appeals/result")
    @admwf_response
    def admwf_finish_appeal(service, user, case_id, line_id):
        return service.finish_appeal(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/no-appeal")
    @admwf_response
    def admwf_no_appeal(service, user, case_id, line_id):
        return service.record_no_appeal(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/submit-review")
    @admwf_response
    def admwf_submit_review(service, user, case_id, line_id):
        return service.submit_review(user, case_id, line_id)

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/review")
    @admwf_response
    def admwf_review(service, user, case_id, line_id):
        return service.decide_review(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/withdraw-review")
    @admwf_response
    def admwf_withdraw_review(service, user, case_id, line_id):
        return service.withdraw_review(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/check-difference-order")
    @admwf_response
    def admwf_check_difference_order(service, user, case_id, line_id):
        return service.check_difference_order(user, case_id, line_id)

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/collections")
    @admwf_response
    def admwf_record_collection(service, user, case_id, line_id):
        return service.record_collection(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/collections/<collection_id>/void")
    @admwf_response
    def admwf_void_collection(service, user, case_id, line_id, collection_id):
        return service.void_collection(user, case_id, line_id, collection_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/lines/<line_id>/void")
    @admwf_response
    def admwf_void_line(service, user, case_id, line_id):
        return service.void_line(user, case_id, line_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/rebalance-lines")
    @admwf_response
    def admwf_rebalance_lines(service, user, case_id):
        return service.rebalance_lines(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/close")
    @admwf_response
    def admwf_close_case(service, user, case_id):
        return service.close_case(user, case_id)

    @api.post("/v1/adm/cases/<case_id>/void")
    @admwf_response
    def admwf_void_case(service, user, case_id):
        return service.void_case(user, case_id, json_body())

    @api.post("/v1/adm/cases/<case_id>/attachments")
    @admwf_response
    def admwf_upload_attachment(service, user, case_id):
        upload = request.files.get("file")
        if upload is None:
            raise AdmError("请选择要上传的附件")
        return service.upload_attachment(user, case_id, upload, request.form.get("category"))

    @api.get("/v1/adm/cases/<case_id>/attachments/<attachment_id>/preview")
    def admwf_preview_attachment(case_id, attachment_id):
        try:
            service = AdmWorkflowService(current_app.config)
            path, metadata = service.attachment_file(g.current_user, case_id, attachment_id)
            response = send_file(path, mimetype=metadata["mime_type"], as_attachment=False,
                                 download_name=metadata["original_file_name"], conditional=True)
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except AdmError as error:
            return jsonify({"success": False, "message": error.message, "code": error.code, "data": None}), error.status
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "ADM请求参数无效", "code": "ADM_INVALID", "data": None}), 400

    @api.post("/v1/adm/cases/<case_id>/attachments/<attachment_id>/void")
    @admwf_response
    def admwf_void_attachment(service, user, case_id, attachment_id):
        return service.void_attachment(user, case_id, attachment_id, json_body())
