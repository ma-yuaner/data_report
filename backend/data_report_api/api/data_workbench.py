from __future__ import annotations

from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context

from ..services.workbench_service import WorkbenchService
from ..services.workbench_store import WorkbenchError
from .common import ok


def service():
    user = getattr(g, "current_user", None)
    owner = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
    if owner is None:
        if current_app.config.get("AUTH_ENABLED", True):
            raise WorkbenchError("请先登录", "UNAUTHENTICATED", 401)
        owner = 0
    return WorkbenchService(current_app.config, int(owner), current_app.instance_path)


def guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except WorkbenchError as error:
            return jsonify(success=False, message=str(error), code=error.code, data={"report": error.report} if error.report else None), error.status
        except ValueError:
            return jsonify(success=False, message="字段、分页或数据格式无效，请检查输入", code="INVALID_REQUEST", data=None), 400
        except Exception:
            current_app.logger.exception("Workbench request failed")
            return jsonify(success=False, message="处理失败，请检查输入或稍后重试", code="WORKBENCH_ERROR", data=None), 500
    return wrapped


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise WorkbenchError("请求内容必须为JSON对象")
    return value


def register_routes(api: Blueprint):
    @api.post("/v1/data-workbench/cleanup")
    @guarded
    def workbench_cleanup():
        values = body()
        instance = service()
        ids = values.get("ids")
        if not isinstance(ids, list):
            raise WorkbenchError("请选择需要删除的对象")
        for resource_id in ids:
            instance.identifier(resource_id)
        return ok(instance.store.cleanup(values.get("kind"), ids, instance.owner))

    @api.get("/v1/data-workbench/catalog")
    @guarded
    def workbench_catalog():
        return ok(service().catalog())

    @api.post("/v1/data-workbench/datasets")
    @guarded
    def workbench_upload():
        return ok(service().upload(request.files.get("file"), request.form.get("name"), request.form.get("sheetName"))), 201

    @api.get("/v1/data-workbench/datasets/<dataset_id>/preview")
    @guarded
    def workbench_dataset_preview(dataset_id):
        return ok(service().dataset_preview(dataset_id, request.args.get("offset", 0), request.args.get("limit", 100)))

    @api.post("/v1/data-workbench/recipes")
    @guarded
    def workbench_create_recipe():
        return ok(service().save_recipe(body())), 201

    @api.put("/v1/data-workbench/recipes/<recipe_id>")
    @guarded
    def workbench_update_recipe(recipe_id):
        return ok(service().save_recipe(body(), recipe_id))

    @api.post("/v1/data-workbench/recipes/<recipe_id>/copy")
    @guarded
    def workbench_copy_recipe(recipe_id):
        return ok(service().copy_recipe(recipe_id, body().get("name"))), 201

    @api.post("/v1/data-workbench/jobs")
    @guarded
    def workbench_create_job():
        return ok(service().submit(body())), 202

    @api.get("/v1/data-workbench/jobs/<job_id>")
    @guarded
    def workbench_get_job(job_id):
        return ok(service().job(job_id))

    @api.post("/v1/data-workbench/jobs/<job_id>/cancel")
    @guarded
    def workbench_cancel_job(job_id):
        instance = service()
        return ok({k: v for k, v in instance.store.cancel(instance.identifier(job_id), instance.owner).items() if not k.startswith("_")})

    @api.get("/v1/data-workbench/jobs/<job_id>/preview")
    @guarded
    def workbench_job_preview(job_id):
        return ok(service().job_preview(job_id, request.args.get("offset", 0), request.args.get("limit", 100)))

    @api.get("/v1/data-workbench/jobs/<job_id>/download")
    @guarded
    def workbench_download(job_id):
        output = service().download(job_id)
        return Response(stream_with_context(output), mimetype="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="workbench-{job_id}.csv"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @api.post("/v1/data-workbench/jobs/<job_id>/publish")
    @guarded
    def workbench_publish(job_id):
        return ok(service().publish(job_id, body().get("name"))), 201
