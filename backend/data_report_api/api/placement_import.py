"""Only batch creation is exposed; import endpoints cannot patch existing opportunities."""
from io import BytesIO

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .common import json_body, ok
from ..services.placement_import import MAX_BYTES, PlacementImportService, require_import, template_bytes
from ..services.smart_placement import SmartPlacementUnavailable


def register_routes(api: Blueprint) -> None:
    def handle(action):
        try:
            require_import(g.current_user)
            return action()
        except PermissionError as error:
            return jsonify(success=False, message=str(error), data=None), 403
        except ValueError as error:
            return jsonify(success=False, message=str(error), data=None), 400
        except SmartPlacementUnavailable as error:
            return jsonify(success=False, message=str(error), data=None), 503

    @api.get('/v1/smart-placement/tasks/import/template')
    def placement_import_template():
        return handle(lambda: send_file(BytesIO(template_bytes()), as_attachment=True,
            download_name='分析机会导入模板.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))

    @api.post('/v1/smart-placement/tasks/import/preview')
    def placement_import_preview():
        def action():
            if set(request.form) - {'submit'} or set(request.files) != {'file'} or len(request.files.getlist('file')) != 1:
                raise ValueError('请上传一个模板文件，仅支持选择新建方式，不接受修改或流程字段')
            upload = request.files.get('file')
            if upload is None or not (upload.filename or '').lower().endswith('.xlsx'):
                raise ValueError('请选择下载模板填写的.xlsx文件')
            if request.form.get('submit', 'false') not in {'true', 'false'}:
                raise ValueError('不支持的导入方式')
            return ok(PlacementImportService(current_app.config).preview(g.current_user,
                upload.stream.read(MAX_BYTES + 1), submit=request.form.get('submit') == 'true'))
        return handle(action)

    @api.post('/v1/smart-placement/tasks/import/confirm')
    def placement_import_confirm():
        def action():
            values = json_body()
            if set(values) != {'token'}:
                raise ValueError('确认导入只接受预览凭据，不支持指定或修改任务ID、状态及流程字段')
            return ok(PlacementImportService(current_app.config).confirm(g.current_user, values['token']), '批量新建已完成')
        return handle(action)
