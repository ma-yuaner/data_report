"""Immutable current-time reports. No reconstruction from today's owner or legacy profit."""
from datetime import date
from decimal import Decimal

from .operations import OperationsService, digest
from .policy import AdmError, identity, now, require, uid


class ReportService(OperationsService):
    def listing(self, user, day):
        require(user, "adm.view")
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
        except (ValueError, TypeError):
            raise AdmError("请选择有效业务日期") from None
        keys = ("id", "version", "businessDate", "generatedAt", "revision", "published", "ruleVersion", "quality")
        return {"items": [{key: row.get(key) for key in keys} for row in self.store.list("SNAPSHOT", 20, date=day) if row.get("published") or user.get("is_admin")], "limit": 20}

    def capture(self, user, body):
        self.admin(user)
        reason = str(body.get("reason") or "").strip()
        if not reason or len(reason) > 4000:
            raise AdmError("生成快照须说明原因，最多4000字")
        if set(body) - {"reason"}:
            raise AdmError("只允许当前时点捕获，不能指定过去日期")
        stamp, policy = now(), self.policy()
        maximum = int(self.service.config.get("ADM_WORKFLOW_MAX_CASES", 5000))
        cases = self.service.store.report_cases(maximum)
        if len(cases) > maximum:
            raise AdmError("快照来源超过容量，拒绝截断生成", 422)
        tasks = self.tasks(user, cases)
        people = {}

        def person(owner, name, role, business):
            key = (str(owner), role, business)
            if key not in people:
                people[key] = dict(ownerId=str(owner), ownerName=name or str(owner), role=role, businessType=business,
                                   openTasks=0, overdue=0, missingDeadline=0, firstReviewed=0, firstPassed=0,
                                   firstPassRate=None, completedTasks=0, eligible=False, rank=None)
            return people[key]

        roles = {"PROCESS": "HANDLER", "ACCEPT": "HANDLER", "FOLLOW_UP": "HANDLER", "REVIEW": "REVIEWER", "FINANCE": "FINANCE", "ASSIGN": "COORDINATOR", "TRANSFER": "HANDLER", "COLLABORATION": "COLLABORATOR", "REMEDIATION": "REMEDIATOR"}
        for task in tasks:
            if not task["ownerId"]:
                continue
            row = person(task["ownerId"], task["ownerName"], roles[task["kind"]], task["businessType"])
            row["openTasks"] += 1
            row["overdue"] += int(task["overdue"])
            row["missingDeadline"] += int(not task["dueAt"])
        missing, reviewed, completed = 0, set(), set()
        for case in cases:
            for event in case["timeline"]:
                action = event["action"]
                if action not in {"approve", "return", "finance_confirm"} or not event.get("lineId"):
                    continue
                measurement = event.get("detail", {}).get("measurement") or {}
                old = event.get("detail", {}).get("responsibility") or {}
                event_round = measurement.get("round", old.get("round"))
                key = (case["id"], event["lineId"], event_round)
                first = action in {"approve", "return"} and key not in reviewed
                if action in {"approve", "return"}:
                    reviewed.add(key)
                trusted = measurement.get("ownerId") and measurement.get("businessType") in {"ISSUE", "REFUND", "CHANGE"} and measurement.get("lineStatus") and type(measurement.get("round")) is int
                if not trusted:
                    if event["at"][:10] == stamp[:10]:
                        missing += 1
                    continue
                if event["at"][:10] != stamp[:10]:
                    continue
                row = person(measurement["ownerId"], measurement.get("ownerName"), "HANDLER", measurement["businessType"])
                if first:
                    row["firstReviewed"] += 1
                    row["firstPassed"] += int(action == "approve")
                if measurement["lineStatus"] == "COMPLETED" and action in {"approve", "finance_confirm"} and key not in completed:
                    row["completedTasks"] += 1
                    completed.add(key)
        for row in people.values():
            samples = row["firstReviewed"]
            if samples:
                row["firstPassRate"] = str((Decimal(row["firstPassed"]) * 100 / samples).quantize(Decimal("0.01")))
            row["eligible"] = bool(policy["rankingEnabled"] and policy["minimumSamples"] and samples >= policy["minimumSamples"] and row["role"] == "HANDLER")
        for business in ("ISSUE", "REFUND", "CHANGE"):
            rows = sorted([row for row in people.values() if row["eligible"] and row["businessType"] == business], key=lambda row: -Decimal(row["firstPassed"]) / row["firstReviewed"])
            previous, rank = None, None
            for index, row in enumerate(rows, 1):
                value = Decimal(row["firstPassed"]) / row["firstReviewed"]
                if value != previous:
                    rank = index
                row["rank"], previous = rank, value
        report = dict(id=uid(), kind="SNAPSHOT", businessDate=stamp[:10], generatedAt=stamp, revision=stamp,
                      published=False, capturedBy=identity(user), reason=reason, ruleVersion=digest({key: policy[key] for key in ("version", "rankingEnabled", "minimumSamples", "approvalNote")}),
                      quality={"missingTrustedEvents": missing, "sourceCases": len(cases), "rankingEnabled": policy["rankingEnabled"], "minimumSamples": policy["minimumSamples"]},
                      summary={"tasks": len(tasks), "overdue": sum(item["overdue"] for item in tasks), "missingDeadline": sum(not item["dueAt"] for item in tasks)},
                      people=list(people.values()), sources=[{"id": case["id"], "version": case["version"]} for case in cases],
                      limitations=["当前时点风险快照，不代表完整全天；业务日期按北京时间", "完成/首审只统计新增可信事件，旧日志缺少当时责任和业务类型不补零", "试运行分项榜仅同业务类型首次审核通过率；非正式绩效、无综合分与处罚", "任务数不等于订单数，不计算旧看板所谓追回利润", "排名保留该快照批准口径及样本范围；个人/团队视图仅展示授权人员"])
        return self.store.save(report)

    def detail(self, user, report_id, scope="mine"):
        require(user, "adm.view")
        if scope not in {"mine", "team", "all"}:
            raise AdmError("报告范围无效")
        if scope == "all":
            require(user, "adm.scope.all")
        row = self.store.get(report_id)
        if not row or row["kind"] != "SNAPSHOT" or (not row["published"] and not user.get("is_admin")):
            raise AdmError("报告不存在或尚未发布", 404)
        if scope != "all":
            ids = self.service._ids(user, scope)
            row["people"] = [item for item in row["people"] if item["ownerId"] in ids]
            row.pop("sources", None)
            row["summary"] = {key: sum(item[key] for item in row["people"]) for key in ("openTasks", "overdue", "missingDeadline", "firstReviewed", "firstPassed", "completedTasks")}
            row["quality"] = {key: row["quality"][key] for key in ("rankingEnabled", "minimumSamples")}
        return row

    def publish(self, user, report_id, body):
        self.admin(user)
        row = self.detail(user, report_id, "all")
        if type(body.get("version")) is not int or body["version"] != row["version"]:
            raise AdmError("报告版本冲突", 409, "ADM_VERSION_CONFLICT")
        reason = str(body.get("reason") or "").strip()
        if not reason or len(reason) > 4000 or row["published"]:
            raise AdmError("发布须填写核对依据；已发布内容不可变，更正请生成新修订", 409)
        row.update(published=True, publishedAt=now(), publishedBy=identity(user), publishReason=reason)
        return self.store.save(row, row["version"])
