"""Freeze original desktop outputs, require preview and confirm, persist delivery."""
import hashlib
import hmac
import json
import secrets
import shutil
import threading
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

from ...time_utils import business_now
from .store import MailError, Store
from .transport import secret_config

CHART_LOCK = threading.Lock()


def now():
    return business_now().isoformat(timespec="seconds")


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def permission(user, operation):
    if not user or not user.get("is_enabled", True):
        raise MailError("请先登录", "HR_MAIL_UNAUTHENTICATED", 401)
    if not user.get("is_admin") and ("hr.mail" not in (user.get("menu_codes") or []) or (operation != "view" and "hr.mail." + operation not in (user.get("permissions") or []))):
        raise MailError("没有HR邮件模块的此项权限", "HR_MAIL_FORBIDDEN", 403)


class Service:
    def __init__(self, config, user):
        self.config, self.user = config, user
        permission(user, "view")
        self.owner = str(user["id"])
        self.root = Path(config.get("HR_MAIL_ROOT", "var/hr-mail")).resolve()
        self.store = Store(config)

    def config_info(self):
        value = {"storageReady": True, "secretReady": True, "sendEnabled": bool(self.config.get("HR_MAIL_SEND_ENABLED", False)), "permissions": {}}
        try:
            self.store.check()
        except MailError as error:
            value.update(storageReady=False, error=error.code + "：" + str(error))
        try:
            secret_config(self.config)
        except MailError as error:
            value.update(secretReady=False)
            value["secretError"] = error.code
        for operation in ("upload", "send"):
            try:
                permission(self.user, operation)
                value["permissions"][operation] = True
            except MailError:
                value["permissions"][operation] = False
        return value

    def path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise MailError("文件路径无效", "HR_MAIL_FILE_INVALID")
        return path

    def verify_file(self, metadata):
        path = self.path(metadata["path"])
        if not path.is_file() or digest(path) != metadata["sha256"]:
            raise MailError("报表或附件缺失/已变化，请重新上传解析并预览", "HR_MAIL_FILE_CHANGED", 409)
        return path

    def upload(self, file, kind):
        permission(self.user, "upload")
        name = str(file.filename or "")
        if kind not in {"week", "month", "mapping"} or not name.lower().endswith(".xlsx") or len(name) > 200 or any(c in name for c in '/\\\r\n\x00'):
            raise MailError("请选择有效的xlsx文件和文件类型")
        self.store.check()
        upload_id = uuid.uuid4().hex
        folder = self.path("uploads/" + upload_id)
        folder.mkdir(parents=True, exist_ok=False)
        persisting = False
        try:
            path = folder / name  # Preserve original basename for period extraction.
            count = 0
            with path.open("xb") as target:
                while chunk := file.stream.read(1024 * 1024):
                    count += len(chunk)
                    if count > int(self.config.get("HR_MAIL_UPLOAD_BYTES", 20971520)):
                        raise MailError("上传文件超过允许大小", "HR_MAIL_FILE_TOO_LARGE", 413)
                    target.write(chunk)
            try:
                with zipfile.ZipFile(path) as archive:
                    info = archive.infolist()
                    if len(info) > 5000 or sum(i.file_size for i in info) > 200 * 1024 * 1024 or "xl/workbook.xml" not in archive.namelist():
                        raise ValueError()
            except (zipfile.BadZipFile, ValueError):
                raise MailError("xlsx文件无效或展开后过大", "HR_MAIL_FILE_INVALID") from None
            value = {"id": upload_id, "ownerId": self.owner, "kind": kind, "name": name, "sha256": digest(path), "path": str(path.relative_to(self.root)), "createdAt": now()}
            persisting = True
            self.store.upload(value)
            return {key: value[key] for key in ("id", "name", "kind", "sha256")}
        except Exception:
            # This is only the newly-created private upload, never a user source.
            if not persisting:
                shutil.rmtree(folder)
            raise

    def get(self, batch_id):
        batch = self.store.get(batch_id)
        if batch["ownerId"] != self.owner and not self.user.get("is_admin"):
            raise MailError("批次不存在或无权限", "HR_MAIL_NOT_FOUND", 404)
        return batch

    def public(self, batch, summary=False):
        value = {k: v for k, v in batch.items() if k not in {"files", "requestKey", "sourceIds", "ownerId"}}
        value["items"] = [{k: v for k, v in item.items() if k not in {"html_body", "frozenHash"}} for item in batch["items"]]
        value["success"] = sum(i["status"] == "SUCCESS" for i in batch["items"])
        value["failed"] = sum(i["status"] == "FAILED" for i in batch["items"])
        value["unknown"] = sum(i["status"] == "UNKNOWN" for i in batch["items"])
        if summary:
            value.pop("items", None)
            value.pop("events", None)
            value.pop("charts", None)
        return value

    def list(self, args):
        value = self.store.list(self.user, args)
        value["items"] = [self.public(batch, True) for batch in value["items"]]
        return value

    def register_file(self, batch, path, name=None):
        file_id = uuid.uuid4().hex
        value = {"id": file_id, "path": str(path.relative_to(self.root)), "sha256": digest(path), "name": name or path.name}
        batch["files"][file_id] = value
        return {k: value[k] for k in ("name", "sha256")} | {"url": f"/api/v1/hr-mail/batches/{batch['id']}/files/{file_id}"}

    @staticmethod
    def frozen_hash(item):
        data = {k: item.get(k) for k in ("id", "to", "cc", "subject", "html_body", "attachment")}
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def parse(self, body):
        permission(self.user, "upload")
        kind = body.get("reportType")
        if kind not in {"week", "month"}:
            raise MailError("请选择本次处理周报或月报")
        report = self.store.get_upload(str(body.get("reportId", "")), self.owner)
        mapping = self.store.get_upload(str(body.get("mappingId", "")), self.owner)
        if report["kind"] != kind or mapping["kind"] != "mapping":
            raise MailError("报表类型或部门映射文件不匹配")
        source, contact = self.verify_file(report), self.verify_file(mapping)
        from .legacy import chart_generator as charts, markdown_builder as builder
        from .legacy.excel_parser import AttendanceParser, MonthlyAttendanceParser, generate_dept_attachment, generate_month_dept_attachment
        parser = (AttendanceParser if kind == "week" else MonthlyAttendanceParser)(str(source), str(contact))
        batch_id = uuid.uuid4().hex
        folder = self.path("batches/" + batch_id)
        folder.mkdir(parents=True, exist_ok=False)
        persisting = False
        try:
            parser.load()
            reports = parser.parse()
            if not reports:
                raise MailError("未解析出部门，请核对原报表Sheet与字段", "HR_MAIL_NO_DEPARTMENTS")
            if len(reports) > 2000:
                raise MailError("部门行数过大，请核实模板；未截取部分发送", "HR_MAIL_TOO_MANY_DEPARTMENTS")
            batch = {"id": batch_id, "ownerId": self.owner, "operator": self.user.get("display_name") or self.user.get("username") or self.owner, "version": 1, "status": "PREVIEW", "createdAt": now(), "reportType": kind, "period": parser.report_period, "items": [], "charts": [], "files": {}, "events": [{"action": "parsed", "at": now(), "actor": self.owner}], "sourceIds": [report["id"], mapping["id"]], "warnings": []}
            batch["requestKey"] = kind + ":" + hashlib.sha256((self.owner + ":" + report["id"] + ":" + mapping["id"]).encode()).hexdigest()
            ranking = parser.parse_ranking_sheet() if kind == "week" else []
            for index, result in enumerate(reports):
                item = {"id": uuid.uuid4().hex, "dept_name": result.dept_name, "dept_leader": result.dept_leader, "to": result.dept_email, "cc": result.dept_cc, "valid": result.valid, "errors": [e.message for e in result.errors], "status": "PENDING", "error": ""}
                common = dict(dept_name=result.dept_name, dept_leader=result.dept_leader, dept_email=result.dept_email, report_period=result.report_period)
                out = folder / str(index)
                out.mkdir()
                if kind == "week":
                    item["indicators"] = result.indicators
                    item["detail_data"] = parser.parse_detail_data(result.dept_name)
                    item["flexible_data"] = parser.parse_flexible_sheet(result.dept_name)
                    item["html_body"] = builder.build_email_html(**common, exception_count=result.indicators.get("异常次数", 0), detail_data=item["detail_data"], flexible_data=item["flexible_data"], ranking_data=ranking, has_ranking_version=bool(ranking))
                    item["subject"] = builder.get_email_subject(result.dept_name, result.report_period)
                    attachment = generate_dept_attachment(str(source), result.dept_name, output_dir=str(out))
                else:
                    persons = parser.get_person_exceptions(result.dept_name)
                    item["persons"] = [asdict(person) for person in persons]
                    item["indicators"] = {"异常人员": len(persons), "部门人数": len(result.persons), "有请假": result.has_leave, "有出差或外出": result.has_business_trip}
                    item["html_body"] = builder.build_monthly_email_html(**common, exception_persons=persons, has_leave=result.has_leave, has_business_trip=result.has_business_trip)
                    item["subject"] = builder.get_monthly_email_subject(result.dept_name, result.report_period)
                    attachment = generate_month_dept_attachment(str(source), result.dept_name, leave_rows=parser.get_leave_rows(result.dept_name), trip_rows=parser.get_trip_rows(result.dept_name), exception_rows=parser.get_exception_detail_rows(result.dept_name), overview_rows=parser.get_overview_rows_by_dept(result.dept_name), output_dir=str(out))
                if attachment:
                    item["attachment"] = self.register_file(batch, Path(attachment))
                else:
                    item["valid"] = False
                    item["errors"].append("部门附件生成失败，禁止无附件发送")
                # Preserve recipient rules; only block header control characters.
                if any("\r" in item[k] or "\n" in item[k] for k in ("to", "cc", "subject")):
                    item["valid"] = False
                    item["errors"].append("邮件头含非法换行，不能发送")
                item["frozenHash"] = self.frozen_hash(item)
                batch["items"].append(item)
            if kind == "week":
                with CHART_LOCK:
                    chart_values = []
                    if ranking:
                        chart_values.append(("部门异常排行榜", charts.generate_ranking_chart(ranking)))
                    valid = [r for r in reports if r.valid]
                    if valid:
                        chart_values.append(("异常汇总统计", charts.generate_summary_chart([{"dept_name": r.dept_name, "indicators": r.indicators, "dept_leader": r.dept_leader} for r in valid])))
                for title, content in chart_values:
                    path = folder / (uuid.uuid4().hex + ".png")
                    path.write_bytes(content)
                    batch["charts"].append({"name": title, **self.register_file(batch, path, title + ".png")})
            batch["total"] = len(batch["items"])
            names = parser.get_report_sheet_names() if kind == "week" else parser.get_sheet_names()
            known = {"异常排行榜", "概况统计与打卡明细", "弹性班次踩点关注名单"} if kind == "week" else {"考勤总览", "考勤异常人员明细", "请假明细", "出差或外出明细"}
            if set(names) - known:
                batch["warnings"].append("原拆分函数会保留额外Sheet，请逐部门下载附件核对范围；未擅自删除或改写。")
            persisting = True
            saved = self.store.create(batch)
            if saved["id"] != batch_id:
                shutil.rmtree(folder)
            return self.public(saved)
        except MailError:
            if not persisting and folder.exists():
                shutil.rmtree(folder)
            raise
        except Exception as error:
            if not persisting and folder.exists():
                shutil.rmtree(folder)
            raise MailError("原报表解析或附件生成失败，请检查模板和Sheet；没有发送邮件", "HR_MAIL_PARSE_FAILED") from error
        finally:
            for name in ("_report_wb", "_overview_wb"):
                workbook = getattr(parser, name, None)
                if workbook:
                    workbook.close()

    def file(self, batch_id, file_id):
        batch = self.get(batch_id)
        metadata = batch["files"].get(file_id)
        if not metadata:
            raise MailError("附件不存在", "HR_MAIL_NOT_FOUND", 404)
        return self.verify_file(metadata), metadata["name"]

    def preview(self, batch_id, item_id):
        batch = self.get(batch_id)
        item = next((i for i in batch["items"] if i["id"] == item_id), None)
        if not item:
            raise MailError("部门项不存在", "HR_MAIL_NOT_FOUND", 404)
        token = secrets.token_urlsafe(32)
        stored = self.store.receipt(batch_id, item_id, self.owner)
        if stored:
            token = stored
        else:
            token = self.store.preview(batch_id, item_id, self.owner, token)
        return {k: item.get(k) for k in ("id", "subject", "to", "cc", "html_body", "attachment")} | {"receipt": token}

    def queue(self, batch_id, body):
        permission(self.user, "send")
        batch = self.get(batch_id)
        if batch["status"] != "PREVIEW":
            return self.public(batch)  # Repeated final confirm never resends.
        if not self.config.get("HR_MAIL_SEND_ENABLED", False):
            raise MailError("部署人尚未开启邮件发送开关", "HR_MAIL_SEND_DISABLED", 409)
        secret_config(self.config)
        if body.get("confirmed") is not True or body.get("version") != batch["version"]:
            raise MailError("请预览当前版本并最终确认", "HR_MAIL_CONFIRM_REQUIRED", 409)
        selected, receipts = body.get("selectedIds"), body.get("previewReceipts")
        if not isinstance(selected, list) or not selected or any(not isinstance(i, str) for i in selected) or len(set(selected)) != len(selected) or not isinstance(receipts, dict):
            raise MailError("请选择部门并逐封预览")
        items = {i["id"]: i for i in batch["items"]}
        for item_id in selected:
            item = items.get(item_id)
            if not item or not item["valid"] or not item["to"].strip() or not item.get("attachment"):
                raise MailError("所选部门存在缺少邮箱、无效数据或缺失附件；没有发送", "HR_MAIL_INVALID_RECIPIENT")
            expected = self.store.receipt(batch_id, item_id, self.owner)
            receipt = receipts.get(item_id)
            if not expected or not isinstance(receipt, str) or not hmac.compare_digest(expected, receipt):
                raise MailError("必须逐部门查看当前邮件预览再最终确认", "HR_MAIL_PREVIEW_REQUIRED", 409)
            if self.frozen_hash(item) != item["frozenHash"]:
                raise MailError("邮件内容已变化，请重新解析预览", "HR_MAIL_CONTENT_CHANGED", 409)
            self.file(batch_id, item["attachment"]["url"].rsplit("/", 1)[-1])
        for item in batch["items"]:
            if item["id"] not in selected:
                item.update(status="SKIPPED", error="本次未选择")
        operator = self.user.get("display_name") or self.user.get("username") or self.owner
        batch.update(status="QUEUED", total=len(selected), confirmedAt=now(), confirmedBy=self.owner, uploadedByOperator=batch["operator"], operator=operator)
        batch["events"].append({"action": "confirmed", "at": now(), "actor": self.owner, "selectedIds": selected})
        return self.public(self.store.save(batch, batch["version"]))
