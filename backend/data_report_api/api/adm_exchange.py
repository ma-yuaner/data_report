"""Intake and template HTTP adapter; data export goes through the global queue."""

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..services.adm import AdmError
from ..services.adm.exchange import AdmExchangeService, check_permission, template
from .common import ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/adm/templates")
    def adm_template_download():
        try:
            check_permission(g.current_user, "adm.import")
            content, filename = template(request.args.get("format", "center"))
            return send_file(
                content,
                as_attachment=True,
                download_name=filename,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                max_age=0,
            )
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status

    @api.post("/v1/adm/imports/preview")
    def adm_import_preview():
        try:
            file = request.files.get("file")
            if file is None:
                raise AdmError("请上传工作簿", 422, "ADM_FILE_REQUIRED")
            return ok(AdmExchangeService(current_app.config).preview(g.current_user, file))
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status
        except (ValueError, OSError) as error:
            current_app.logger.warning("ADM import preview failed: %s", type(error).__name__)
            return jsonify({"success": False, "message": "文件无法读取，请核查模板与存储", "data": None}), 422

    @api.post("/v1/adm/imports/<preview_id>/commit")
    def adm_import_commit(preview_id: str):
        try:
            return ok(AdmExchangeService(current_app.config).commit(g.current_user, preview_id))
        except AdmError as error:
            return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status
