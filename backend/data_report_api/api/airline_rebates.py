"""HKG26003 pilot endpoints on the existing authenticated blueprint."""
from datetime import datetime, timezone
from functools import wraps
from hashlib import sha256
from io import BytesIO
import json
import time
from uuid import uuid4

from flask import current_app, g, jsonify, request, send_file
from pypdf.errors import PdfReadError

from .common import json_body, ok
from ..services.airline_rebates.calculation import simulate
from ..services.airline_rebates.policy import parse_policy
from ..services.airline_rebates.store import connect, encode

ROOT = "/v1/airline-rebates"
MAX_FILE = 10 * 1024 * 1024


class PilotError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def endpoint(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            directory = current_app.config.get("AIRLINE_REBATE_PILOT_ROOT")
            if not directory:
                raise PilotError("航司后返试点服务未启用", 503)
            if not g.current_user.get("is_admin"):
                raise PilotError("仅限授权管理员使用航司后返试点", 403)
            return function(directory, *args, **kwargs)
        except PilotError as error:
            return jsonify(success=False, data=None, message=str(error)), error.status
        except (ValueError, TypeError):
            return jsonify(success=False, data=None, message="请求参数无效"), 422
        except Exception as error:
            current_app.logger.error("Airline rebate pilot request failed: %s", type(error).__name__)
            return jsonify(success=False, data=None, message="航司后返试点暂不可用"), 503
    return wrapped


def find(db, table, identifier):
    # Only internal callers supply the table.
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
    if row is None:
        raise PilotError("记录不存在", 404)
    return row


def now():
    return datetime.now(timezone.utc).isoformat()


def user_label():
    return g.current_user.get("display_name") or g.current_user["username"]


def policy_data(row):
    record = json.loads(row["profile"])
    return {key: record[key] for key in ("id", "name", "airline", "period")} | {
        "status": "ready", "confirmed": bool(row["confirmed_at"]),
        "confirmedAt": row["confirmed_at"], "confirmedBy": row["confirmed_by"],
    }


def rule_cards(policy):
    def card(identifier, name, page, conditions):
        return {"id": identifier, "name": name, "sourcePage": f"第 {page} 页", "conditions": [
            {"id": key, "fieldLabel": label, "operator": op, "value": value}
            for key, label, op, value in conditions
        ]}
    return [
        card("eligibility", "适用与计量", 1, [
            ("period", "承运期间", "eq", [policy["flownStart"], policy["flownEnd"]]),
            ("stock", "票证前三位", "eq", policy["ticketPrefix"]),
            ("carrier", "实际承运航司", "in", policy["carriers"]),
            ("exception", "KN 例外", "eq", policy["carrierException"]),
            ("excluded", "不计量不计奖舱位", "not_in", policy["excludedCabins"]),
            ("other_excluded", "其他排除", "not_in", policy["exclude"]),
            ("measure_only", "计量不计奖舱位", "in", policy["measureOnlyCabins"]),
            ("measure_clients", "计量不计奖客户", "in", policy["measureOnly"]),
            ("origin", "换开始发口径", "eq", policy["originBasis"]),
        ]),
        card("routes", "航线及舱位分组", 2, [
            ("long", "远程经停或目的国家", "in", policy["longHaul"]),
            ("short", "非远程经停或目的国家", "in", policy["shortHaul"]),
            ("hkg_non", "香港非指定机场", "in", policy["regionalNonDesignated"]["HKG"]),
            ("mfm_non", "澳门非指定机场", "in", policy["regionalNonDesignated"]["MFM"]),
            ("hkg_designated", "香港指定机场", "in", policy["regionalDesignated"]["HKG"]),
            ("group_a", "费率 A 组舱位", "in", policy["cabinGroups"][0]),
            ("group_b", "费率 B 组舱位", "in", policy["cabinGroups"][1]),
        ]),
        *[card(f"tier-{item['lowerExclusive']}", "承运收入奖励档位 · HKD", 2, [
            ("minimum", "累计收入下限", "gt", item["lowerExclusive"]),
            *([("maximum", "累计收入上限", "lte", item["upperInclusive"])] if item["upperInclusive"] else []),
            ("basis", "列序", "eq", ["远程", "非远程", "非指定", "指定", "异地始发"]),
            ("group_a", "A 组费率（%）", "eq", item["ratesPercent"]["groupA"]),
            ("group_b", "B 组费率（%）", "eq", item["ratesPercent"]["groupB"]),
        ]) for item in reversed(policy["tiers"])],
        card("settlement", "结算与试算边界", 3, [
            ("iata", "代理核定维度", "eq", policy["agencyBasis"]),
            ("revenue", "政策计奖基数", "eq", policy["amountBasis"]),
            ("trial", "宽表试算实际使用", "eq", "首段计划起飞日和 HKD 票面价，真实票联结算待核"),
        ]),
    ]


def task_data(db, row):
    result = json.loads(row["profile"])
    if row["current_run"]:
        summary = json.loads(find(db, "rebate_runs", row["current_run"])["summary"])
        result.update({key: summary[key] for key in ("target", "actual", "completionRate", "dataAsOf")})
    return result


def register_routes(api):
    @api.get(ROOT + "/policies")
    @endpoint
    def rebate_policies(directory):
        with connect(directory) as db:
            return ok([policy_data(row) for row in db.execute("SELECT * FROM rebate_policies ORDER BY rowid DESC")])

    @api.post(ROOT + "/policies")
    @endpoint
    def rebate_upload(directory):
        request.max_content_length = MAX_FILE + 1024 * 32
        file = request.files.get("file")
        if not file or not file.filename or not file.filename.lower().endswith(".pdf"):
            raise PilotError("请选择 HKG26003 PDF")
        raw = file.stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise PilotError("PDF 最大 10 MB", 413)
        if not raw.startswith(b"%PDF-"):
            raise PilotError("请选择有效 PDF")
        try:
            policy = parse_policy(BytesIO(raw))
        except (ValueError, PdfReadError, KeyError, TypeError) as error:
            raise PilotError("PDF 未通过 HKG26003 政策结构校验，请核对原件") from error
        identifier = sha256(raw).hexdigest()
        profile = {"id": identifier, "name": file.filename.replace("\\", "/").rsplit("/", 1)[-1][:200],
                   "airline": "MU/FM", "period": policy["flownStart"] + " 至 " + policy["flownEnd"], "policy": policy}
        with connect(directory) as db:
            db.execute("INSERT OR IGNORE INTO rebate_policies(id, profile, original) VALUES (?, ?, ?)",
                       (identifier, encode(profile), raw))
            return ok(policy_data(find(db, "rebate_policies", identifier)))

    @api.get(ROOT + "/policies/<identifier>")
    @endpoint
    def rebate_policy(directory, identifier):
        with connect(directory) as db:
            record = json.loads(find(db, "rebate_policies", identifier)["profile"])
            return ok(rule_cards(record["policy"]))

    @api.get(ROOT + "/policies/<identifier>/original")
    @endpoint
    def rebate_original(directory, identifier):
        with connect(directory) as db:
            row = find(db, "rebate_policies", identifier)
            return send_file(BytesIO(row["original"]), mimetype="application/pdf", as_attachment=True,
                             download_name=json.loads(row["profile"])["name"], max_age=0)

    @api.post(ROOT + "/policies/<identifier>/confirm")
    @endpoint
    def rebate_confirm(directory, identifier):
        with connect(directory) as db:
            find(db, "rebate_policies", identifier)
            db.execute("UPDATE rebate_policies SET confirmed_by=?, confirmed_at=? WHERE id=? AND confirmed_at IS NULL",
                       (user_label(), now(), identifier))
            return ok(policy_data(find(db, "rebate_policies", identifier)))

    @api.get(ROOT + "/tasks")
    @endpoint
    def rebate_tasks(directory):
        with connect(directory) as db:
            return ok([task_data(db, row) for row in db.execute("SELECT * FROM rebate_tasks ORDER BY rowid DESC")])

    @api.post(ROOT + "/tasks")
    @endpoint
    def rebate_create(directory):
        payload = json_body()
        name, owner = (str(payload.get(key) or "").strip() for key in ("name", "owner"))
        if not name or not owner or len(name) > 200 or len(owner) > 100:
            raise PilotError("请填写有效的任务名称和负责人")
        with connect(directory) as db:
            policy_row = find(db, "rebate_policies", str(payload.get("policyId") or ""))
            if not policy_row["confirmed_at"]:
                raise PilotError("请先核对并确认政策解析结果", 409)
            policy = json.loads(policy_row["profile"])
            item = {"id": uuid4().hex, "name": name, "airline": policy["airline"], "period": policy["period"],
                    "owner": owner, "currency": "HKD", "policyName": policy["name"], "editable": False,
                    "target": None, "actual": None, "completionRate": None, "dataAsOf": None}
            db.execute("INSERT OR IGNORE INTO rebate_tasks(id, policy_id, profile) VALUES (?, ?, ?)",
                       (item["id"], policy["id"], encode(item)))
            row = db.execute("SELECT * FROM rebate_tasks WHERE policy_id = ?", (policy["id"],)).fetchone()
            return ok(task_data(db, row))

    @api.get(ROOT + "/tasks/<identifier>/versions")
    @endpoint
    def rebate_versions(directory, identifier):
        with connect(directory) as db:
            task = find(db, "rebate_tasks", identifier)
            policy = find(db, "rebate_policies", task["policy_id"])
            record = json.loads(policy["profile"])
            return ok([{"version": 1, "reason": "由人工确认的 HKG26003 解析结果建档",
                        "savedAt": policy["confirmed_at"], "rules": rule_cards(record["policy"])}])

    @api.post(ROOT + "/tasks/<identifier>/versions")
    @endpoint
    def rebate_version_unsupported(directory, identifier):
        raise PilotError("HKG26003 试点仅运行已确认的政策版本", 409)

    @api.get(ROOT + "/tasks/<identifier>/progress")
    @endpoint
    def rebate_progress(directory, identifier):
        with connect(directory) as db:
            task = find(db, "rebate_tasks", identifier)
            if task["current_run"]:
                result = json.loads(find(db, "rebate_runs", task["current_run"])["summary"])
            else:
                result = dict(target=None, actual=None, completionRate=None, dataAsOf=None, version=None,
                              status="pending", daily=[], estimatedReward=None)
            if task["run_error"]:
                result.update(status="failed", errorMessage=task["run_error"])
            return ok(result)

    @api.post(ROOT + "/tasks/<identifier>/runs")
    @endpoint
    def rebate_run(directory, identifier):
        token = uuid4().hex
        started = int(time.time())
        with connect(directory) as db:
            task = find(db, "rebate_tasks", identifier)
            updated = db.execute(
                "UPDATE rebate_tasks SET run_token=?, run_at=? WHERE id=? AND (run_token IS NULL OR run_at<?)",
                (token, started, identifier, started - 900),
            ).rowcount
            if not updated:
                raise PilotError("已有试算正在运行", 409)
            policy = json.loads(find(db, "rebate_policies", task["policy_id"])["profile"])["policy"]
        try:
            summary, days = simulate(current_app.config, policy)
            for point in summary["daily"]:
                point["id"] = token + "_" + point["date"]
            with connect(directory) as db:
                updated = db.execute(
                    "UPDATE rebate_tasks SET current_run=?, run_token=NULL, run_at=NULL, run_error=NULL WHERE id=? AND run_token=?",
                    (token, identifier, token),
                ).rowcount
                if not updated:
                    raise PilotError("本次试算已被更新的运行替代", 409)
                db.execute("INSERT INTO rebate_runs(id, task_id, summary) VALUES (?, ?, ?)",
                           (token, identifier, encode(summary)))
                db.executemany("INSERT INTO rebate_days(run_id, day, details) VALUES (?, ?, ?)",
                               ((token, day, encode(rows)) for day, rows in days.items()))
            return ok(summary)
        except PilotError:
            raise
        except Exception as error:
            message = "Hive 试算失败，保留最近成功结果。请核对宽表覆盖或联系数据团队。"
            with connect(directory) as db:
                db.execute("UPDATE rebate_tasks SET run_token=NULL, run_at=NULL, run_error=? WHERE id=? AND run_token=?",
                           (message, identifier, token))
            current_app.logger.warning("HKG26003 trial failed: %s", type(error).__name__)
            raise PilotError(message, 503) from error

    @api.get(ROOT + "/tasks/<identifier>/progress/<daily_id>/details")
    @endpoint
    def rebate_day_details(directory, identifier, daily_id):
        run, separator, day = daily_id.partition("_")
        if not separator:
            raise PilotError("批次明细不存在", 404)
        page = int(request.args.get("page", 1))
        if page < 1 or page > 2000:
            raise PilotError("分页超出试点范围")
        with connect(directory) as db:
            record = db.execute(
                "SELECT details FROM rebate_days JOIN rebate_runs ON rebate_runs.id=rebate_days.run_id "
                "WHERE run_id=? AND day=? AND task_id=?", (run, day, identifier),
            ).fetchone()
            if record is None:
                raise PilotError("批次明细不存在", 404)
            rows = json.loads(record["details"])
            start = (page - 1) * 25
            return ok({"items": rows[start:start + 25], "total": len(rows)})
