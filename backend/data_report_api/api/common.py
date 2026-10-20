from __future__ import annotations
from flask import jsonify, request, send_file


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
