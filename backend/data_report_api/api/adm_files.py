"""Authenticated evidence HTTP adapter, separate from lifecycle operations."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..services.adm import AdmError, AdmService
from ..services.adm.attachments import AdmAttachmentService, file_mime
from .common import ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/adm/cases/<case_id>/attachments")
    def adm_attachment_list(case_id: str):
        try:
            detail = AdmService(current_app.config).case_detail(g.current_user, case_id)
            return ok(detail.get("attachments", []))
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status

    @api.post("/v1/adm/cases/<case_id>/attachments")
    def adm_attachment_upload(case_id: str):
        try:
            file = request.files.get("file")
            if file is None:
                raise AdmError("请选择附件", 422, "ADM_FILE_REQUIRED")
            return ok(
                AdmAttachmentService(current_app.config).upload(g.current_user, case_id, file, request.form),
                "附件已上传",
            )
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status

    @api.get("/v1/adm/cases/<case_id>/attachments/<attachment_id>/download")
    def adm_attachment_download(case_id: str, attachment_id: str):
        try:
            path, metadata = AdmAttachmentService(current_app.config).file(g.current_user, case_id, attachment_id)
            response = send_file(
                path, as_attachment=True, download_name=metadata["name"], mimetype=file_mime(metadata), max_age=0
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status

    @api.get("/v1/adm/cases/<case_id>/attachments/<attachment_id>/preview")
    def adm_attachment_preview(case_id: str, attachment_id: str):
        try:
            mode, content, metadata = AdmAttachmentService(current_app.config).preview(
                g.current_user,
                case_id,
                attachment_id,
                request.args.get("sheet", ""),
            )
            if mode == "json":
                return ok(content)
            response = send_file(
                content, as_attachment=False, download_name=metadata["name"], mimetype=file_mime(metadata), max_age=0
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
            return response
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status
