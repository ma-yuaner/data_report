from __future__ import annotations
from flask import Blueprint, current_app, jsonify, request
from ..services.risk_upload import RiskUploadService
from .common import ok


def register_routes(api: Blueprint) -> None:
    @api.get("/v1/risk-uploads")
    def risk_upload_status():
        return ok(RiskUploadService(current_app.config).status(request.headers.get("X-Risk-Upload-Token")))

    @api.post("/v1/risk-uploads")
    def create_risk_upload():
        try:
            job = RiskUploadService(current_app.config).submit(
                business_type=request.form.get("businessType", ""),
                upload=request.files.get("file"),
                sheet_name=request.form.get("sheetName"),
                load_date=request.form.get("loadDate"),
                confirmed=request.form.get("confirmOverwrite", "").lower() == "true",
                token=request.headers.get("X-Risk-Upload-Token"),
            )
            return ok(job, "上传成功，任务已进入Hive导入队列"), 202
        except PermissionError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 403
        except ValueError as error:
            return jsonify({"success": False, "message": str(error), "data": None}), 400
