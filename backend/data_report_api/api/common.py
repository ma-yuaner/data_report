from __future__ import annotations
from functools import wraps

from flask import current_app, g, jsonify, request, send_file

from ..services.adm import AdmError, AdmService


def ok(data, message: str = "OK"):
    return jsonify({"success": True, "message": message, "data": data})


def json_body() -> dict:
    values = request.get_json(silent=True)
    if not isinstance(values, dict):
        raise ValueError("请求内容必须为JSON对象")
    return values


def smart_excel_response(result):
    content, filename = result
    return send_file(
        content,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


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
