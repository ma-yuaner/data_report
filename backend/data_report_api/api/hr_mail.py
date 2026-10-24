"""Authenticated HR-only mail workflow. No credentials accepted or returned."""
from functools import wraps

from flask import current_app, g, jsonify, request, send_file

from ..services.hr_mail.service import Service
from ..services.hr_mail.store import MailError
from .common import json_body, ok


def guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(Service(current_app.config, g.current_user), *args, **kwargs)
        except MailError as error:
            return jsonify(success=False, message=str(error), code=error.code, data=None), error.status
        except (ValueError, TypeError):
            return jsonify(success=False, message="字段或分页参数无效", code="HR_MAIL_INVALID", data=None), 422
        except Exception:
            # Never log raw exceptions that could contain HR content or Secret URLs.
            current_app.logger.error("HR mail request failed endpoint=%s", request.endpoint)
            return jsonify(success=False, message="HR邮件处理失败，未自动发送或重发，请核对批次状态", code="HR_MAIL_INTERNAL", data=None), 500
    return wrapped


def register_routes(api):
    @api.get("/v1/hr-mail/config")
    @guarded
    def hr_mail_config(service):
        return ok(service.config_info())

    @api.post("/v1/hr-mail/uploads")
    @guarded
    def hr_mail_upload(service):
        file = request.files.get("file")
        if not file:
            raise MailError("请选择xlsx文件")
        return ok(service.upload(file, request.form.get("kind")))

    @api.post("/v1/hr-mail/batches")
    @guarded
    def hr_mail_parse(service):
        return ok(service.parse(json_body()))

    @api.get("/v1/hr-mail/batches")
    @guarded
    def hr_mail_history(service):
        return ok(service.list(request.args))

    @api.get("/v1/hr-mail/batches/<batch_id>")
    @guarded
    def hr_mail_detail(service, batch_id):
        return ok(service.public(service.get(batch_id)))

    @api.get("/v1/hr-mail/batches/<batch_id>/items/<item_id>/preview")
    @guarded
    def hr_mail_preview(service, batch_id, item_id):
        response = ok(service.preview(batch_id, item_id))
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.post("/v1/hr-mail/batches/<batch_id>/send")
    @guarded
    def hr_mail_confirm(service, batch_id):
        return ok(service.queue(batch_id, json_body()))

    @api.get("/v1/hr-mail/batches/<batch_id>/files/<file_id>")
    @guarded
    def hr_mail_file(service, batch_id, file_id):
        path, name = service.file(batch_id, file_id)
        response = send_file(path, download_name=name, as_attachment=path.suffix.lower() != ".png", max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
