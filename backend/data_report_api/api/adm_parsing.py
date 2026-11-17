"""ADM parsing HTTP routes; existing task ledger and analysis remain independent."""
from functools import wraps

from flask import current_app, g, jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from ..services.admwf.policy import AdmError
from ..services.adm_parsing.service import ParsingService
from .common import json_body, ok


def response(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            maximum = 51 * 1024 * 1024 if function.__name__ == "adm_parsing_upload" else 16 * 1024
            if request.method == "POST":
                request.max_content_length = maximum
                if request.content_length and request.content_length > maximum:
                    raise AdmError("解析请求超过允许大小，单件文件合计上限50MB", 413, "PARSE_REQUEST_LIMIT")
            return function(ParsingService(current_app.config), g.current_user, *args, **kwargs)
        except RequestEntityTooLarge:
            return jsonify(success=False, data=None, message="解析请求超过大小限制", code="PARSE_REQUEST_LIMIT"), 413
        except AdmError as error:
            if error.code == "ADM_TABLE_MISSING":
                return jsonify(success=False, data=None, message="ADM解析独立表尚未建立，请由部署人执行docs/sql/adm-parsing-v1.sql；原台账和分析表不需要变更", code="PARSE_TABLE_MISSING"), 503
            return jsonify(success=False, data=None, message=error.message, code=error.code), error.status
        except (ValueError, TypeError):
            return jsonify(success=False, data=None, message="解析请求参数无效", code="PARSE_INVALID"), 422
        except Exception as error:
            current_app.logger.error("ADM parsing request failed: %s", type(error).__name__)
            return jsonify(success=False, data=None, message="解析存储暂不可用，请检查数据库、独立解析表及文件目录", code="PARSE_STORAGE_UNAVAILABLE"), 503
    return wrapped


def register_routes(api):
    @api.get("/v1/adm/parsing/status")
    @response
    def adm_parsing_status(service, user):
        return ok(service.status(user))

    @api.get("/v1/adm/parsing/tasks")
    @response
    def adm_parsing_list(service, user):
        return ok(service.list(user, int(request.args.get("page", 1)), int(request.args.get("pageSize", 20)), request.args.get("state", "")))

    @api.post("/v1/adm/parsing/tasks")
    @response
    def adm_parsing_upload(service, user):
        return ok(service.upload(user, request.files.getlist("files"), request.headers.get("Idempotency-Key")), "材料已上传并保存")

    @api.get("/v1/adm/parsing/tasks/<task_id>")
    @response
    def adm_parsing_detail(service, user, task_id):
        return ok(service.detail(user, task_id))

    @api.post("/v1/adm/parsing/tasks/<task_id>/parse")
    @response
    def adm_parsing_start(service, user, task_id):
        return ok(service.enqueue(user, task_id, json_body().get("version")), "已加入解析队列")

    @api.post("/v1/adm/parsing/tasks/<task_id>/retry-save")
    @response
    def adm_parsing_retry_save(service, user, task_id):
        return ok(service.retry_save(user, task_id, json_body().get("version")), "保存状态已核对")

    @api.get("/v1/adm/parsing/tasks/<task_id>/files/<file_id>")
    @response
    def adm_parsing_file(service, user, task_id, file_id):
        path, name = service.file(user, task_id, file_id)
        result = send_file(path, as_attachment=True, download_name=name, max_age=0)
        result.headers["Cache-Control"] = "private, no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        return result
