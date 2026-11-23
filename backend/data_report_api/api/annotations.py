"""Authenticated annotation HTTP endpoints."""
from functools import wraps

from flask import current_app, g, jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from ..services.admwf.policy import AdmError
from ..services.annotation_service import AnnotationService
from .common import json_body, ok

def handled(function):
    @wraps(function)
    def route(*args, **kwargs):
        try:
            authority = current_app.extensions.get("auth_manager")
            accounts = authority.store.list_users if authority else None
            service = AnnotationService(current_app.config, g.current_user, accounts)
            if request.method in ("POST", "PATCH", "DELETE"):
                request.max_content_length = 52 * 1024 * 1024 if function.__name__ == "annotation_upload" else 2 * 1024 * 1024
                if request.content_length and request.content_length > request.max_content_length:
                    raise RequestEntityTooLarge()
            response = current_app.make_response(function(service, *args, **kwargs))
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except RequestEntityTooLarge:
            return jsonify(success=False, data=None, message="请求超过标注接口大小限制", code="ANNOTATION_SIZE"), 413
        except AdmError as exc:
            return jsonify(success=False, data=None, message=exc.message, code=exc.code), exc.status
        except (ValueError, TypeError):
            return jsonify(success=False, data=None, message="请求字段无效", code="ANNOTATION_INVALID"), 422
        except Exception as exc:
            current_app.logger.error("Annotation request failed: %s", type(exc).__name__)
            if getattr(exc, "args", ()) and exc.args[0] == 1146:
                return jsonify(success=False, data=None, message="标注库表尚未建立，请联系部署负责人", code="ANNOTATION_SCHEMA"), 503
            return jsonify(success=False, data=None, message="标注存储暂不可用，请稍后重试或联系管理员",
                           code="ANNOTATION_STORAGE"), 503
    return route


def register_routes(api):
    @api.get("/v1/annotations/projects")
    @handled
    def annotation_projects(service):
        return ok(service.projects())

    @api.post("/v1/annotations/projects")
    @handled
    def annotation_create_project(service):
        return ok(service.create_project(json_body()), "项目已创建")

    @api.patch("/v1/annotations/projects/<project_id>")
    @handled
    def annotation_configure(service, project_id):
        return ok(service.configure(project_id, json_body()), "项目配置已保存")

    @api.get("/v1/annotations/accounts")
    @handled
    def annotation_accounts(service):
        return ok(service.account_options(request.args.get("projectId")))

    @api.get("/v1/annotations/projects/<project_id>/samples")
    @handled
    def annotation_samples(service, project_id):
        return ok(service.list_samples(project_id, int(request.args.get("page", 1)),
                                       request.args.get("status", ""), request.args.get("search", "")))

    @api.post("/v1/annotations/projects/<project_id>/samples")
    @handled
    def annotation_upload(service, project_id):
        service.check_import(project_id)
        return ok(service.upload(project_id, request.files.getlist("files"), request.form.get("group") == "true"))

    @api.post("/v1/annotations/projects/<project_id>/import-adm")
    @handled
    def annotation_import_adm(service, project_id):
        return ok(service.import_adm(project_id, json_body().get("taskId")), "ADM 原件已关联标注项目")

    @api.get("/v1/annotations/samples/<sample_id>")
    @handled
    def annotation_detail(service, sample_id):
        return ok(service.detail(sample_id))

    @api.delete("/v1/annotations/samples/<sample_id>")
    @handled
    def annotation_delete(service, sample_id):
        return ok(service.delete_sample(sample_id, json_body()), "样本已从队列删除")

    @api.patch("/v1/annotations/samples/<sample_id>")
    @handled
    def annotation_edit(service, sample_id):
        return ok(service.update_sample(sample_id, json_body()), "草稿已保存")

    @api.post("/v1/annotations/samples/<sample_id>/actions")
    @handled
    def annotation_actions(service, sample_id):
        return ok(service.actions(sample_id, json_body()), "样本已更新")

    @api.get("/v1/annotations/samples/<sample_id>/files/<file_id>")
    @handled
    def annotation_file(service, sample_id, file_id):
        path, name = service.file(sample_id, file_id)
        response = send_file(path, as_attachment=True, download_name=name, max_age=0)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @api.get("/v1/annotations/projects/<project_id>/datasets")
    @handled
    def annotation_datasets(service, project_id):
        return ok(service.datasets(project_id))

    @api.post("/v1/annotations/projects/<project_id>/datasets")
    @handled
    def annotation_publish(service, project_id):
        return ok(service.publish(project_id, json_body()), "已发布固定版本")

    @api.get("/v1/annotations/projects/<project_id>/datasets/<dataset_id>")
    @handled
    def annotation_dataset(service, project_id, dataset_id):
        return ok(service.dataset(project_id, dataset_id))

    @api.get("/v1/annotations/projects/<project_id>/datasets/<dataset_id>/compare-adm")
    @handled
    def annotation_compare_adm(service, project_id, dataset_id):
        return ok(service.compare_adm(project_id, dataset_id))
