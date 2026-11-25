"""HKG26003 pilot endpoints on the existing authenticated blueprint."""
from datetime import datetime, timezone
from functools import wraps
from hashlib import sha256
from io import BytesIO
import json
import time
from uuid import uuid4

import click
from flask import current_app, g, jsonify, request, send_file
from pypdf.errors import PdfReadError

from .common import json_body, ok, smart_excel_response
from ..services.airline_rebates.calculation import CATEGORIES, fetch_facts, fetch_review_details, simulate
from ..services.airline_rebates.mapping import (
    CATALOG_VERSION, MappingValidationError, blocked_trial_rules, review_cards, trial_ready, validate_facts,
)
from ..services.airline_rebates.policy import parse_policy
from ..services.airline_rebates.route_progress import eligible_route_rows, route_days, route_workbook
from ..services.airline_rebates.store import connect, encode

ROOT = "/v1/airline-rebates"
MAX_FILE = 10 * 1024 * 1024
RUN_LEASE_SECONDS = 900


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


def check_category(category):
    if category not in CATEGORIES:
        raise PilotError("航线类型不存在", 404)


def check_snapshot(db, task_id, run_id):
    if db.execute("SELECT 1 FROM rebate_runs WHERE id=? AND task_id=?", (run_id, task_id)).fetchone() is None:
        raise PilotError("批次明细不存在", 404)


def user_label():
    return g.current_user.get("display_name") or g.current_user["username"]


def policy_data(row):
    record = json.loads(row["profile"])
    return {key: record[key] for key in ("id", "name", "airline", "period")} | {
        "status": "ready", "confirmed": bool(row["confirmed_at"]),
        "confirmedAt": row["confirmed_at"], "confirmedBy": row["confirmed_by"],
        "trialReady": trial_ready(record),
    }


def policy_for_review(row):
    stored = json.loads(row["profile"])["policy"]
    return stored if "sourceClauses" in stored else parse_policy(BytesIO(row["original"]))


def rule_cards(policy):
    clauses = dict(policy["sourceClauses"])
    clauses["carrier"] += "。" + clauses["exception"]
    def card(identifier, name, page, conditions):
        return {"id": identifier, "name": name, "sourcePage": f"第 {page} 页" if isinstance(page, int) else None, "conditions": [
            {"id": key, "fieldLabel": label, "operator": op, "value": value, "mapping": mapping,
             "sourceText": clauses.get(key) or clauses.get(identifier) or (
                 clauses[f"tier-{policy['tiers'][0]['lowerExclusive']}"]
                 if identifier == "routes" and key in ("group_a", "group_b") else None
             )}
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
            ("stock", "票证前三位", "eq", policy["ticketPrefix"],
             "试算及政策匹配：issue_ticket_no 前三位。"),
            ("scope", "适用客票航程", "applies", "含国际或地区航线的单程、来回程、缺口程，可包含票内中国大陆段",
             "试算：segment_airport、dep_airport、arr_airport 与机场国家字典。待核：票联航程和航段顺序。"),
            ("carrier", "实际承运航司", "in", policy["carriers"],
             "试算：segment_marketing_airline 逐段作销售航司参考。待核：运营航司字段需与销售系统或结算样票对照。"),
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
        card("trial_filters", "业务确认的试算过滤条件", "—", [
            ("issue_complete", "出票完成", "all", ["订单已出票", "出票已更新"],
             "试算明细入口：order_status = TICKETED、issue_status = I_UPDATED。"),
            ("refund_void", "退票和废票", "not_in", ["已退票", "已作废"],
             "试算明细入口：按 issue_ticket_no_status、flt_status、refund_flag_desc 排除。"),
        ]),
        card("routes", "航线及舱位分组", 2, [
            ("regional_scope", "地区航线前提", "all", ["港澳始发至中国大陆", "不经过国际航线"], regional),
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


def mapping_review(row):
    profile = json.loads(row["profile"])
    return {
        "policy": policy_data(row),
        "rules": review_cards(rule_cards(policy_for_review(row)), profile),
        "validation": profile.get("mappingValidation"),
    }


def save_mapping_profile(db, row, profile):
    if not db.execute(
        "UPDATE rebate_policies SET profile=? WHERE id=? AND profile=?",
        (encode(profile), row["id"], row["profile"]),
    ).rowcount:
        raise PilotError("校验期间有其他人修改了数据映射，请刷新后重试", 409)
    return mapping_review(find(db, "rebate_policies", row["id"]))


def task_data(db, row):
    result = json.loads(row["profile"])
    if row["current_run"]:
        summary = json.loads(find(db, "rebate_runs", row["current_run"])["summary"])
        result.update({key: summary[key] for key in ("target", "actual", "completionRate", "dataAsOf")})
        result.update({key: summary.get(key) for key in ("tier", "refreshedAt", "refreshMode", "pendingCount", "estimatedReward")})
    result["refreshStatus"] = "failed" if row["run_error"] else "ready" if row["current_run"] else "pending"
    return result


def run_trial(directory, identifier, refresh_interval=0):
    token = uuid4().hex
    started = int(time.time())
    with connect(directory) as db:
        task = find(db, "rebate_tasks", identifier)
        policy_row = find(db, "rebate_policies", task["policy_id"])
        profile = json.loads(policy_row["profile"])
        if blocked_trial_rules(profile):
            raise PilotError("试算依赖的字段待核实，请在政策审阅中处理", 422)
        if refresh_interval and task["current_run"]:
            previous = json.loads(find(db, "rebate_runs", task["current_run"])["summary"])
            last = previous.get("refreshedAt")
            if last and started - datetime.fromisoformat(last).timestamp() < refresh_interval:
                return None
        updated = db.execute(
            "UPDATE rebate_tasks SET run_token=?, run_at=? WHERE id=? AND current_run IS ? AND (run_token IS NULL OR run_at<?)",
            (token, started, identifier, task["current_run"], started - RUN_LEASE_SECONDS),
        ).rowcount
        if not updated:
            raise PilotError("已有试算正在运行", 409)
        policy = profile["policy"]
    try:
        summary, days = simulate(current_app.config, policy)
        summary.update(runId=token, refreshedAt=now(), refreshMode="scheduled" if refresh_interval else "manual")
        for point in summary["daily"]:
            point["id"] = token + "_" + point["date"]
        with connect(directory) as db:
            latest_policy = find(db, "rebate_policies", task["policy_id"])
            if json.loads(latest_policy["profile"]).get("mappingReview") != profile.get("mappingReview"):
                raise ValueError("试算期间政策数据映射已变更")
            updated = db.execute(
                "UPDATE rebate_tasks SET current_run=?, run_token=NULL, run_at=NULL, run_error=NULL "
                "WHERE id=? AND run_token=? AND EXISTS ("
                "SELECT 1 FROM rebate_policies p WHERE p.id=rebate_tasks.policy_id AND p.profile=?)",
                (token, identifier, token, latest_policy["profile"]),
            ).rowcount
            if not updated:
                raise ValueError("本次试算已被替代或数据映射已更新")
            db.execute("INSERT INTO rebate_runs(id, task_id, summary) VALUES (?, ?, ?)",
                       (token, identifier, encode(summary)))
            db.executemany("INSERT INTO rebate_days(run_id, day, details) VALUES (?, ?, ?)",
                           ((token, day, encode(rows)) for day, rows in days.items()))
        return summary
    except PilotError:
        raise
    except Exception as error:
        message = (
            f"{error}。如有历史结果，仍可查看。"
            if isinstance(error, MappingValidationError)
            else "Hive 试算失败，保留最近成功结果。请核对宽表覆盖或联系数据团队。"
        )
        with connect(directory) as db:
            db.execute("UPDATE rebate_tasks SET run_token=NULL, run_at=NULL, run_error=? WHERE id=? AND run_token=?",
                       (message, identifier, token))
        current_app.logger.warning("HKG26003 trial failed: %s", type(error).__name__)
        raise PilotError(message, 503) from error


def register_routes(api):
    @api.cli.command("airline-rebate-refresh")
    @click.option("--interval-minutes", type=click.IntRange(min=1), required=True, help="Minimum time between successful runs per task.")
    def refresh_due_tasks(interval_minutes):
        """Refresh confirmed rebate tasks due since their last successful run."""
        directory = current_app.config.get("AIRLINE_REBATE_PILOT_ROOT")
        if not directory:
            raise click.ClickException("航司后返试点未配置")
        with connect(directory) as db:
            identifiers = [row["id"] for row in db.execute(
                "SELECT t.id FROM rebate_tasks t JOIN rebate_policies p ON p.id=t.policy_id "
                "WHERE p.confirmed_at IS NOT NULL ORDER BY t.rowid"
            )]
        refreshed = skipped = failed = 0
        for identifier in identifiers:
            try:
                result = run_trial(directory, identifier, refresh_interval=interval_minutes * 60)
                if result is None:
                    skipped += 1
                else:
                    refreshed += 1
            except PilotError as error:
                if error.status == 409:
                    skipped += 1
                else:
                    failed += 1
                    click.echo(f"{identifier}: {error}", err=True)
        click.echo(f"refreshed={refreshed} skipped={skipped} failed={failed}")
        if failed:
            raise click.ClickException("部分任务刷新失败，保留最近成功结果")

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
                   "airline": "MU/FM", "period": policy["flownStart"] + " 至 " + policy["flownEnd"], "policy": policy,
                   "uploadRevision": uuid4().hex}
        with connect(directory) as db:
            db.execute("INSERT OR IGNORE INTO rebate_policies(id, profile, original) VALUES (?, ?, ?)",
                       (identifier, encode(profile), raw))
            return ok(policy_data(find(db, "rebate_policies", identifier)))

    @api.get(ROOT + "/policies/<identifier>")
    @endpoint
    def rebate_policy(directory, identifier):
        with connect(directory) as db:
            return ok(rule_cards(policy_for_review(find(db, "rebate_policies", identifier))))

    @api.get(ROOT + "/policies/<identifier>/mapping")
    @endpoint
    def rebate_mapping(directory, identifier):
        with connect(directory) as db:
            return ok(mapping_review(find(db, "rebate_policies", identifier)))

    @api.get(ROOT + "/policies/<identifier>/mapping/details")
    @endpoint
    def rebate_mapping_details(directory, identifier):
        page = int(request.args.get("page", "1"))
        if not 1 <= page <= 2500:
            raise PilotError("明细页码无效")
        with connect(directory) as db:
            profile = json.loads(find(db, "rebate_policies", identifier)["profile"])
        reference = profile.get("mappingReference") or {"columns": [], "rows": []}
        return ok({**reference, "page": 1, "hasNext": False})

    @api.put(ROOT + "/policies/<identifier>/mapping")
    @endpoint
    def rebate_review_mapping(directory, identifier):
        payload = json_body()
        group, rule, state = (payload.get(key) for key in ("group", "rule", "state"))
        note = str(payload.get("note") or "").strip()
        field = payload.get("field")
        if state not in ("confirmed", "missing", "removed", "reset") or len(note) > 500:
            raise PilotError("核实结论无效，说明最多 500 字")
        if state == "confirmed" and (not isinstance(field, str) or not field or len(field) > 128):
            raise PilotError("请选择 Hive 明细字段")
        with connect(directory) as db:
            row = find(db, "rebate_policies", identifier)
            cards = mapping_review(row)["rules"]
            selected = next((
                condition["dataMapping"] for card in cards if card["id"] == group
                for condition in card["conditions"] if condition["id"] == rule
            ), None)
            if not selected or selected["kind"] == "constant":
                raise PilotError("该规则无需字段核实")
            if state == "removed" and not selected["removable"]:
                raise PilotError("该政策项属于必核项")
            profile = json.loads(row["profile"])
            if state == "confirmed":
                reference = profile.get("mappingReference", {})
                if not any(item["name"] == field for item in reference.get("columns", [])):
                    raise PilotError("该字段不在已准备的参考记录中，请先校验 Hive 明细")
            review = profile.setdefault("mappingReview", {})
            key = f"{group}/{rule}"
            if state == "reset":
                review.pop(key, None)
            else:
                review[key] = {"state": state, "note": note, "by": user_label(), "at": now()}
                if state == "confirmed":
                    review[key]["field"] = field
            return ok(save_mapping_profile(db, row, profile))

    @api.post(ROOT + "/policies/<identifier>/mapping/validate")
    @endpoint
    def rebate_validate_mapping(directory, identifier):
        with connect(directory) as db:
            row = find(db, "rebate_policies", identifier)
        profile = json.loads(row["profile"])
        try:
            records, airports = fetch_facts(current_app.config, profile["policy"])
            validation = validate_facts(records, airports)
        except MappingValidationError as error:
            validation = {"rows": 0, "fields": {}, "error": str(error)}
        except Exception as error:
            current_app.logger.warning("Rebate mapping validation failed: %s", type(error).__name__)
            validation = {"rows": 0, "fields": {}, "error": "Hive 校验失败，请核对连接、字段和政策期间覆盖"}
        checked_at = now()
        if validation.get("rows"):
            try:
                reference = fetch_review_details(current_app.config, profile["policy"], 1, 1)
                if reference["rows"]:
                    profile["mappingReference"] = {
                        "columns": reference["columns"], "rows": reference["rows"][:1], "preparedAt": checked_at,
                    }
                else:
                    validation["referenceError"] = "本次未取得参考记录"
            except Exception as error:
                current_app.logger.warning("Rebate reference preparation failed: %s", type(error).__name__)
                validation["referenceError"] = "本次未能准备参考记录"
        profile["mappingValidation"] = {**validation, "catalogVersion": CATALOG_VERSION, "at": checked_at}
        with connect(directory) as db:
            return ok(save_mapping_profile(db, row, profile))

    @api.delete(ROOT + "/policies/<identifier>")
    @endpoint
    def rebate_delete_policy(directory, identifier):
        with connect(directory) as db:
            db.execute("BEGIN IMMEDIATE")
            find(db, "rebate_policies", identifier)
            if db.execute("SELECT 1 FROM rebate_tasks WHERE policy_id=?", (identifier,)).fetchone():
                raise PilotError("请先删除该政策对应的试算任务", 409)
            db.execute("DELETE FROM rebate_policies WHERE id=?", (identifier,))
        current_app.logger.info("Rebate policy deleted by %s: %s", user_label(), identifier)
        return ok(None)

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
            existing = db.execute("SELECT * FROM rebate_tasks WHERE policy_id=?", (policy["id"],)).fetchone()
            if existing:
                return ok(task_data(db, existing))
            if not trial_ready(policy):
                raise PilotError("请先核实试算字段并通过 Hive 明细校验", 422)
            item = {"id": uuid4().hex, "name": name, "airline": policy["airline"], "period": policy["period"],
                    "owner": owner, "currency": "HKD", "policyName": policy["name"], "editable": False,
                    "target": None, "actual": None, "completionRate": None, "dataAsOf": None}
            db.execute(
                "INSERT OR IGNORE INTO rebate_tasks(id, policy_id, profile) "
                "SELECT ?, id, ? FROM rebate_policies WHERE id=? AND profile=?",
                (item["id"], encode(item), policy["id"], policy_row["profile"]),
            )
            row = db.execute("SELECT * FROM rebate_tasks WHERE policy_id = ?", (policy["id"],)).fetchone()
            if not row:
                raise PilotError("字段校验状态已更新，请刷新政策后重试", 409)
            return ok(task_data(db, row))

    @api.delete(ROOT + "/tasks/<identifier>")
    @endpoint
    def rebate_delete_task(directory, identifier):
        with connect(directory) as db:
            db.execute("BEGIN IMMEDIATE")
            task = find(db, "rebate_tasks", identifier)
            if task["run_token"] and task["run_at"] >= int(time.time()) - RUN_LEASE_SECONDS:
                raise PilotError("试算正在运行，请在本次运行结束后删除", 409)
            db.execute("DELETE FROM rebate_days WHERE run_id IN (SELECT id FROM rebate_runs WHERE task_id=?)",
                       (identifier,))
            db.execute("DELETE FROM rebate_runs WHERE task_id=?", (identifier,))
            db.execute("DELETE FROM rebate_tasks WHERE id=?", (identifier,))
        current_app.logger.info("Rebate task deleted by %s: %s", user_label(), identifier)
        return ok(None)

    @api.get(ROOT + "/tasks/<identifier>/versions")
    @endpoint
    def rebate_versions(directory, identifier):
        with connect(directory) as db:
            task = find(db, "rebate_tasks", identifier)
            policy = find(db, "rebate_policies", task["policy_id"])
            return ok([{"version": 1, "reason": "由人工确认的 HKG26003 解析结果建档",
                        "savedAt": policy["confirmed_at"], "rules": rule_cards(policy_for_review(policy))}])

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
                result["runId"] = task["current_run"]
            else:
                result = dict(target=None, actual=None, completionRate=None, dataAsOf=None, version=None,
                              status="pending", daily=[], estimatedReward=None)
            if task["run_error"]:
                result.update(status="failed", errorMessage=task["run_error"])
            return ok(result)

    @api.post(ROOT + "/tasks/<identifier>/runs")
    @endpoint
    def rebate_run(directory, identifier):
        return ok(run_trial(directory, identifier))

    @api.get(ROOT + "/tasks/<identifier>/runs/<run_id>/routes/<category>/days")
    @endpoint
    def rebate_route_progress(directory, identifier, run_id, category):
        check_category(category)
        with connect(directory) as db:
            check_snapshot(db, identifier, run_id)
            return ok([point for point, _ in route_days(db, run_id, category)])

    @api.get(ROOT + "/tasks/<identifier>/runs/<run_id>/routes/<category>/export")
    @endpoint
    def rebate_route_export(directory, identifier, run_id, category):
        check_category(category)
        day = request.args.get("day")
        with connect(directory) as db:
            check_snapshot(db, identifier, run_id)
            if day is not None and db.execute(
                "SELECT 1 FROM rebate_days WHERE run_id=? AND day=?", (run_id, day),
            ).fetchone() is None:
                raise PilotError("批次当日明细不存在", 404)
            currency = json.loads(find(db, "rebate_tasks", identifier)["profile"])["currency"]
            label = CATEGORIES[category]
            content = route_workbook(route_days(db, run_id, category, day), label, currency)
        return smart_excel_response((content, f"后返-{label}-{day or '全期'}.xlsx"))

    @api.get(ROOT + "/tasks/<identifier>/progress/<daily_id>/details")
    @endpoint
    def rebate_day_details(directory, identifier, daily_id):
        run, separator, day = daily_id.partition("_")
        if not separator:
            raise PilotError("批次明细不存在", 404)
        page = int(request.args.get("page", 1))
        query = request.args.get("q", "").strip()
        category = request.args.get("category")
        if category is not None:
            check_category(category)
        if len(query) > 80:
            raise PilotError("订单号或票号筛选值过长")
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
            if category is not None:
                rows = eligible_route_rows(rows, category)
            if query:
                rows = [row for row in rows if query in (row.get("orderNo"), row.get("ticketNo"))]
            start = (page - 1) * 25
            return ok({"items": rows[start:start + 25], "total": len(rows)})
