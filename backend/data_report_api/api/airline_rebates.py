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
            {"id": key, "fieldLabel": label, "operator": op, "value": value, "mapping": mapping}
            for key, label, op, value, mapping in conditions
        ]}

    route_points = "试算：segment_airport 与机场字典 airport_code、country_code。"
    regional = "试算：dep_airport、arr_airport 与地区机场名单匹配。待核：联程、来回程、缺口程的逐段匹配。"
    cabin = "试算：segment_real_cabin 按航段顺序对应。待核：票联实际舱位及分段票面价。"
    cumulative = "试算：累计符合计量条件的 issue_ticket_price（issue_currency = HKD）。待核：票联净承运收入。"
    rate = "政策常量。试算按航线类别及 segment_real_cabin 判定费率组，乘相应 HKD 票面价。"
    return [
        card("eligibility", "适用与计量", 1, [
            ("period", "航段实际承运日", "between", [policy["flownStart"], policy["flownEnd"]],
             "试算：segment_dep_time 按航段日期判断，首段日期用于候选取数。待核：票联实际承运日和跨期票分段金额。"),
            ("issue_date", "出票日期", "unrestricted", "原政策未设出票日期窗口",
             "试算按航段日期取数。issue_ticket_time 供回补与追溯。"),
            ("agency", "适用代理人", "in", "香港营业部所辖指定代理人",
             "试算：supplier_code = HK_NGCHOW。待核：指定代理 IATA 名单与东航结算的代理明细。"),
            ("issue_complete", "出票完成", "all", ["订单已出票", "出票已更新"],
             "试算明细入口：order_status = TICKETED、issue_status = I_UPDATED。"),
            ("refund_void", "退票和废票", "not_in", ["已退票", "已作废"],
             "试算明细入口：按 issue_ticket_no_status、flt_status、refund_flag_desc 排除。"),
            ("stock", "票证前三位", "eq", policy["ticketPrefix"],
             "试算及政策匹配：issue_ticket_no 前三位。"),
            ("scope", "适用客票航程", "applies", "含国际或地区航线的单程、来回程、缺口程，可包含票内中国大陆段",
             "试算：segment_airport、dep_airport、arr_airport 与机场国家字典。待核：票联航程和航段顺序。"),
            ("carrier", "实际承运航司", "in", policy["carriers"],
             "试算：segment_marketing_airline 逐段作销售航司参考。待核：运营航司字段需与销售系统或结算样票对照。"),
            ("exception", "KN 例外", "all", ["实际承运分公司归属为 KN", "销售系统显示实际承运方为 MU/FM"],
             "试算未执行。待核：分公司归属字段及销售系统实际承运方字段，须分别取证。"),
            ("excluded", "不计量不计奖舱位", "not_in", policy["excludedCabins"], cabin),
            ("charter", "不计量不计奖航班", "not_in", ["包机", "包收入航班"],
             "试算：issue_price_type_desc 文本包含包机或包收入。待核：业务确认的航班分类。"),
            ("infant", "不计量不计奖旅客", "not_in", "婴儿票",
             "试算：real_age_type_desc 匹配婴儿或 INF。待核：源字段取值覆盖。"),
            ("domestic", "不计量不计奖客票", "not_in", "纯内地客票",
             "试算：dep_airport、segment_airport 与机场国家字典判定。待核：整票完整航程。"),
            ("non_operated", "不计量不计奖航段", "not_in", "共享或外航联运中非东上航实际承运航段",
             "试算未逐段排除。待核：航段明细 operating_airline、code_share 和实际承运票联。"),
            ("measure_only", "计量不计奖舱位", "in", policy["measureOnlyCabins"], cabin),
            ("measure_clients", "计量不计奖客户", "in", policy["measureOnly"],
             "试算：issue_price_type_desc 文本包含集团。待核：集团客户分类及票联收入。"),
            ("origin", "换开始发与销量", "applies",
             "代理人换开追溯旧票始发。东上航直属售票处或客服中心非自愿换开，销量还原并追溯旧票始发",
             "试算：refund_issue_flag 及票号状态识别换开并待核。改签可计入，须核实新旧票联、换开渠道及旧票航程，防止重复。"),
        ]),
        card("routes", "航线及舱位分组", 2, [
            ("long", "港澳始发远程经停或目的国家", "in", policy["longHaul"], route_points),
            ("short", "港澳始发非远程经停或目的国家", "in", policy["shortHaul"],
             route_points + "先判远程。政策要求全航程无远程点。"),
            ("hkg_non", "香港非指定机场", "in", policy["regionalNonDesignated"]["HKG"], regional),
            ("mfm_non", "澳门非指定机场", "in", policy["regionalNonDesignated"]["MFM"], regional),
            ("hkg_designated", "香港指定机场", "in", policy["regionalDesignated"]["HKG"], regional),
            ("other_origin", "异地始发", "applies", "非港澳始发、东上航实际承运的适用航线",
             "试算：dep_airport 判断非港澳始发，符合计奖条件的票面价固定乘 1%。待核：逐段实际承运方。"),
            ("group_a", "费率 A 组舱位", "in", policy["cabinGroups"][0], cabin),
            ("group_b", "费率 B 组舱位", "in", policy["cabinGroups"][1], cabin),
        ]),
        *[card(f"tier-{item['lowerExclusive']}", "承运收入奖励档位 · HKD", 2, [
            ("minimum", "累计收入下限", "gt", item["lowerExclusive"], cumulative),
            *([("maximum", "累计收入上限", "lte", item["upperInclusive"], cumulative)] if item["upperInclusive"] else []),
            ("basis", "费率对应航线列序", "eq", ["远程", "非远程", "非指定", "指定", "异地始发"],
             "政策常量。按此顺序读取 A、B 组费率。"),
            ("group_a", "A 组费率（%）", "eq", item["ratesPercent"]["groupA"], rate),
            ("group_b", "B 组费率（%）", "eq", item["ratesPercent"]["groupB"], rate),
        ]) for item in reversed(policy["tiers"])],
        card("settlement", "计奖、发放与结算", 3, [
            ("iata", "代理核定维度", "eq", "东航代理人明细中的 IATA 号",
             "试算按固定供应商汇总。待核：东航结算 IATA，可与出票航段明细 issuing_iata 对账。"),
            ("revenue", "政策计奖基数", "applies", "不含税费及基础代理费的计奖运输收入净额，分别乘对应费率后求和",
             "试算：issue_ticket_price、issue_currency。待核：东航结算票联净承运收入，票价、税费及佣金列供对账。"),
            ("rounding", "结算资料及取整", "applies", "以东航收入结算部运输收入资料为准，港币四舍五入进整",
             "待核：东航结算数据及取整层级。试算未执行结算取整。"),
            ("payment", "奖励发放", "applies", "东航实际承运的运输收入奖励费按结算周期一并发放",
             "用途：结算发放。待核：航司结算周期和发放记录，试算无对应宽表字段。"),
            ("evaluation", "跨期评估", "applies", "连续两个奖励期未达到阶梯目标，从奖励政策范围中剔除",
             "用途：代理资格管理。待核：代理 IATA、连续奖励期及各期目标达成记录。"),
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
