"""ERP change SLA dashboard read endpoint."""
from flask import current_app, g, jsonify, request
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from .common import ok
from ..services.change_sla import ChangeSlaQueryError, read_change_sla
from ..services.change_sla_limits import ChangeSlaLimits, FIELDS, InvalidLimit, LimitsChanged, SharedChangeSlaLimits
from ..services.data_source import DataSource
from ..services.change_sla_snapshot import ChangeSlaSnapshotUnavailable, read_reporting_snapshot


def _can_access(user):
    return current_app.config["AUTH_ENABLED"] and (user.get("is_admin") or any(
        role.get("name") == "客服经理" for role in (user.get("business_roles") or [])
    ))


def _read_import(file):
    content = file.stream.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise InvalidLimit("Excel 文件不能超过 2 MB")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 12 * 1024 * 1024:
                raise InvalidLimit("Excel 解压后过大")
        workbook = load_workbook(BytesIO(content), data_only=True, keep_links=False)
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise InvalidLimit("请上传有效的《合作平台与沟通方式》Excel 文件") from exc
    try:
        sheet = workbook.active
        headers = ("负责人", "部门", "OTA平台", "群名称", "沟通方式", "审单", "审核自愿时限",
                   "审核非自愿时限", "操作自愿改期", "操作非自愿改期")
        if sheet is None or tuple(sheet.cell(2, i).value for i in range(1, 11)) != headers or sheet.max_row > 1002:
            raise InvalidLimit("请使用原 Excel 表头，且配置不能超过 1000 行")
        merged = {}
        for span in sheet.merged_cells.ranges:
            if span.min_col == span.max_col <= 10:
                for row in range(max(3, span.min_row), min(sheet.max_row, span.max_row) + 1):
                    merged[(row, span.min_col)] = sheet.cell(span.min_row, span.min_col).value
        columns = ("owner", "department", *FIELDS[:1], *FIELDS[3:])
        result = []
        for row in range(3, sheet.max_row + 1):
            cells = [sheet.cell(row, col).value for col in range(1, 11)]
            if any(value is not None for value in cells):
                values = [merged.get((row, col), value) for col, value in enumerate(cells, 1)]
                result.append({"sourceRow": row, **dict(zip(columns, (str(v) if v is not None else "" for v in values)))})
        return result
    finally:
        workbook.close()


def register_routes(api):
    @api.get("/v1/analysis/change-sla")
    def change_sla():
        user = getattr(g, "current_user", {})
        if not _can_access(user):
            return jsonify(success=False, message="仅系统管理员或客服经理可查看改签 SLA", code="PERMISSION_FORBIDDEN", data=None), 403
        try:
            start, end, node = (request.args.get(key) for key in ("from", "to", "node"))
            result = (
                read_reporting_snapshot(current_app.config, start, end, node)
                if node is not None else read_change_sla(current_app.config, start, end)
            )
            response = ok(result)
            response.headers["Cache-Control"] = "no-store"
            return response
        except ChangeSlaQueryError as exc:
            return jsonify(success=False, message=str(exc), data=None), 400
        except ChangeSlaSnapshotUnavailable as exc:
            return jsonify(success=False, message=str(exc), code="CHANGE_SLA_NOT_SYNCED", data=None), 503
        except Exception:
            current_app.logger.exception("ERP change SLA query failed")
            return jsonify(success=False, message="ERP 改签数据暂不可用，请稍后重试", data=None), 503

    @api.route("/v1/analysis/change-sla/limits", methods=["GET", "POST"])
    def change_sla_limits():
        user = getattr(g, "current_user", {})
        if not _can_access(user):
            return jsonify(success=False, message="仅系统管理员或客服经理可管理改签时限", code="PERMISSION_FORBIDDEN", data=None), 403
        config = current_app.config
        root = config["DATA_WORKBENCH_DIR"]
        store = (
            SharedChangeSlaLimits(root, DataSource({**config, "DATA_MODE": "mysql"}).connect)
            if config.get("CHANGE_SLA_SHARED_RULES") else ChangeSlaLimits(root)
        )
        try:
            if request.method == "POST":
                if request.content_length and request.content_length > 3 * 1024 * 1024:
                    raise InvalidLimit("配置请求过大")
                file = request.files.get("file")
                if file is not None:
                    revision = request.form.get("revision", "")
                    if not revision.isdecimal() or len(revision) > 16:
                        raise InvalidLimit("配置版本无效，请刷新后重新导入")
                    body = {"revision": int(revision), "action": "import", "rows": _read_import(file)}
                else:
                    body = request.get_json(silent=True)
                    if not isinstance(body, dict) or body.get("action") != "upsert":
                        raise InvalidLimit("请提交配置或上传原始 Excel")
                result = store.save(body, user["id"])
            else:
                result = store.export_rule_history() if request.args.get("export") == "216" else store.get()
            response = ok(result)
            response.headers["Cache-Control"] = "no-store"
            return response
        except InvalidLimit as exc:
            return jsonify(success=False, message=str(exc), data=None), 400
        except LimitsChanged as exc:
            return jsonify(success=False, message=str(exc), data=None), 409
        except Exception:
            current_app.logger.exception("Change SLA limits store failed")
            return jsonify(success=False, message="时限配置暂不可用，请稍后重试", data=None), 503
