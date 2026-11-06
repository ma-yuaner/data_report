"""Permission-controlled risk evidence and review workflow; ERP is read-only."""
import logging
import sqlite3
from flask import current_app, g, jsonify, request

from .common import ok
from ..services.risk_order_evidence import EvidenceError, RiskOrderEvidenceService
from ..services.risk_verification_flow import FlowError, RiskVerificationFlow
from ..services.risk_verification_ai import RiskAI
from ..services.risk_verification_overview import RiskVerificationOverview
from ..services.risk_auto_verification import RiskAutoVerification
from ..services.risk_auto_store import StoreUnavailable
from ..services.risk_commission_rule import RULE_ID
from ..services.risk_child_loss import BET_REASONS
from ..shared.permissions import permission_codes


def required_permission():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return "risk.verification.view"
    path = request.path.rstrip("/")
    if "/followup/policies" in path:
        return "risk.verification.types.manage"
    if "/followup/" in path:
        return "risk.verification.review"
    if path.endswith("/problem-types"):
        return "risk.verification.types.manage"
    if path.endswith("/publish"):
        return "risk.verification.knowledge.publish"
    if path.endswith(("/sample", "/confirm", "/problem-tags", "/knowledge")):
        return "risk.verification.review"
    return "risk.verification.check"


def _call(action):
    user = getattr(g, "current_user", {})
    if not user.get("is_admin"):
        needed = {"risk.verification.view", required_permission()}
        if "risk.verification" not in (user.get("menu_codes") or []) or not needed <= permission_codes(user):
            return jsonify(success=False, message="没有此风控核对功能权限", code="PERMISSION_FORBIDDEN", data=None), 403
    try:
        response = ok(action(str(user["id"])))
        response.headers["Cache-Control"] = "no-store"
        return response
    except (EvidenceError, FlowError) as error:
        payload = {"success": False, "message": str(error), "data": None}
        if getattr(error, "code", None):
            payload["code"] = error.code
        return jsonify(payload), error.status
    except StoreUnavailable as error:
        return jsonify(success=False, message=str(error), data=None), 503
    except Exception:
        logging.getLogger(__name__).exception("Risk verification request failed")
        return jsonify(success=False, message="风控核对暂不可用，请联系管理员核对服务日志", data=None), 503


def _body():
    values = request.get_json(silent=True)
    if not isinstance(values, dict):
        raise EvidenceError("请求内容必须是JSON对象")
    return values


def _flow():
    try:
        return RiskVerificationFlow(current_app.config)
    except (OSError, sqlite3.OperationalError):
        logging.getLogger(__name__).exception("Risk verification storage initialization failed")
        raise FlowError("风控记录存储初始化失败，请检查风控专用数据卷及应用用户写入权限", 503) from None


def register_routes(api):
    from ..services.risk_followup import RiskFollowup

    @api.get("/v1/risk-verification/followup/reviews")
    def risk_followup_summaries():
        def read(actor):
            import re
            try:
                raw = request.args.get('orders', '')
                if len(raw) > 4000:
                    raise ValueError('too many orders')
                pairs = raw.split(',') if raw else []
                if any(not re.fullmatch(r'[1-9][0-9]{0,18}:\d{4}-\d{2}-\d{2}', pair) for pair in pairs):
                    raise ValueError('invalid scope')
                items = [dict(zip(('orderId', 'issueDate'), pair.split(':'))) for pair in pairs]
            except (ValueError, TypeError):
                raise FlowError('订单范围格式无效') from None
            return RiskFollowup(current_app.config).summaries(items)
        return _call(read)

    @api.get("/v1/risk-verification/followup/cases")
    def risk_followup_cases():
        return _call(lambda actor: RiskFollowup(current_app.config).listing(request.args, actor))

    @api.get("/v1/risk-verification/followup/cases/<case_id>")
    def risk_followup_case(case_id):
        return _call(lambda actor: RiskFollowup(current_app.config).detail(case_id))

    @api.post("/v1/risk-verification/followup/cases/<case_id>")
    def risk_followup_update(case_id):
        return _call(lambda actor: RiskFollowup(current_app.config).update(actor, case_id, _body()))

    @api.get("/v1/risk-verification/followup/orders/<identifier>")
    def risk_followup_order(identifier):
        return _call(lambda actor: RiskFollowup(current_app.config).order(identifier, request.args.get('issueDate')))

    @api.post("/v1/risk-verification/followup/reviews")
    def risk_followup_review():
        return _call(lambda actor: RiskFollowup(current_app.config).review(actor, _body()))

    @api.get("/v1/risk-verification/followup/policies")
    def risk_followup_policies():
        return _call(lambda actor: RiskFollowup(current_app.config).policies())

    @api.post("/v1/risk-verification/followup/policies")
    def risk_followup_policy_create():
        return _call(lambda actor: RiskFollowup(current_app.config).policy_create(actor, _body()))

    @api.get("/v1/risk-verification/problem-types")
    def risk_problem_types():
        from ..services.risk_problem_tags import RiskProblemTags
        return _call(lambda owner: RiskProblemTags(current_app.config).types())

    @api.post("/v1/risk-verification/problem-types")
    def risk_problem_type_create():
        from ..services.risk_problem_tags import RiskProblemTags
        return _call(lambda owner: RiskProblemTags(current_app.config).create(owner,_body().get('name')))

    @api.get("/v1/risk-verification/orders/<identifier>/problem-tags")
    def risk_problem_tag_list(identifier):
        from ..services.risk_problem_tags import RiskProblemTags
        return _call(lambda owner: RiskProblemTags(current_app.config).list(identifier))

    @api.post("/v1/risk-verification/orders/<identifier>/problem-tags")
    def risk_problem_tag_save(identifier):
        from ..services.risk_problem_tags import RiskProblemTags
        def save(owner):
            values=_body()
            return RiskProblemTags(current_app.config).save(owner,identifier,values.get('typeIds'),values.get('reason'))
        return _call(save)

    @api.get("/v1/risk-verification/rule-configs")
    def risk_issue_rule_configs():
        from ..services.risk_issue_rule_configs import RiskIssueRuleConfigs
        return _call(lambda owner: RiskIssueRuleConfigs(current_app.config).read(request.args.get('platform'), request.args.get('group')))

    @api.post("/v1/risk-verification/automatic/jobs")
    def risk_automatic_submit():
        def submit(owner):
            values = _body()
            if values.get("mode") != "refresh_verify":
                raise EvidenceError("请更新页面后使用‘更新并核实’按钮；查询不会启动任务")
            return RiskAutoVerification(dict(current_app.config)).submit(owner, values.get("startDate"), values.get("endDate"), values.get("reason"), values.get("force", False))
        return _call(submit)

    @api.get("/v1/risk-verification/automatic/job")
    def risk_automatic_job():
        return _call(lambda owner: RiskAutoVerification(current_app.config).active(owner))

    @api.get("/v1/risk-verification/automatic/orders/<identifier>")
    def risk_automatic_result(identifier):
        return _call(lambda owner: RiskAutoVerification(current_app.config).result(owner, identifier,request.args.get('issueDate')))

    @api.post("/v1/risk-verification/automatic/orders/<identifier>/sample")
    def risk_automatic_sample(identifier):
        def sample(owner):
            values = _body()
            return RiskAutoVerification(current_app.config).sample(owner, identifier, values.get("resultId"), values.get("outcome"), values.get("reason"),values.get('issueDate'))
        return _call(sample)

    @api.get("/v1/risk-verification/overview")
    def risk_verification_overview():
        return _call(lambda owner: RiskVerificationOverview(current_app.config).summary(
            owner, request.args.get("startDate"), request.args.get("endDate")))

    @api.get("/v1/risk-verification/orders")
    def risk_verification_order_list():
        return _call(lambda owner: RiskVerificationOverview(current_app.config).orders(
            owner, request.args.get("startDate"), request.args.get("endDate"),
            request.args.get("reason"), request.args.get("status", "all"),
            request.args.get("page", "1"), request.args.get("pageSize", "20")))

    @api.get("/v1/risk-verification/status")
    def risk_verification_status():
        return _call(lambda owner: {"ai": RiskAI(current_app.config).status(), "access": "permission_owner_scoped",
                                   "formulaStatus": "partially_confirmed", "source": "sibebid_prepared",
                                   "rules": [{"id": RULE_ID, "label": "佣金、点击费亏损（去哪儿且有销售佣金）",
                                              "formula": "非去哪儿优先判有问题；去哪儿正佣金单票：出票利润＋销售佣金≥－出票时配置止损值（含等号）；超过4段按4段配置＋超出段数×25元",
                                              "status": "自动规则已接入；历史配置、段数或必要字段不能可靠还原时证据不足"},
                                             {"id": RULE_ID+":RLA040", "label": "综合无亏损－儿童/婴儿",
                                              "formula": "必须有儿童或婴儿；携程OTA及关联拆单出票利润合计÷总票数≥－当前单出票时配置止损值，不加佣金",
                                              "status": "自动规则已接入；全成人直接有问题，关联范围/利润/阈值不完整时证据不足"},
                                             *[{"id": RULE_ID+":"+code, "label": label,
                                                "formula": "逐票出票利润≥－出票时单票止损值（含等号），不加佣金或预期收益；任一票突破即有问题",
                                                "status": "自动规则已接入；利润、历史阈值或出票范围不完整时保留证据不足"}
                                               for code,label in BET_REASONS.items()]],
                                   "sourceConfigured": all(bool(current_app.config.get(f"MYSQL_{key}")) for key in ("HOST", "DATABASE", "USER", "PASSWORD")),
                                   "erpEvidenceConfigured": current_app.config.get("RISK_VERIFICATION_ERP_EXPLICIT") is True and all(bool(current_app.config.get(f"ERP_MYSQL_{key}")) for key in ("HOST", "DATABASE", "USER", "PASSWORD"))})

    @api.get("/v1/risk-verification/candidates")
    def risk_verification_candidates():
        return _call(lambda owner: RiskOrderEvidenceService(current_app.config).candidates(
            request.args.get("startDate"), request.args.get("endDate"), request.args.get("before")))

    @api.get("/v1/risk-verification/orders/<value>/evidence")
    def risk_verification_evidence(value):
        def read(owner):
            sections = request.args.get("sections")
            return RiskOrderEvidenceService(current_app.config).evidence(value, sections.split(",") if sections else None, request.args.get("identifierType", "auto"))
        return _call(read)

    @api.get("/v1/risk-verification/cases")
    def risk_verification_cases():
        return _call(lambda owner: _flow().list_cases(owner))

    @api.post("/v1/risk-verification/cases")
    def risk_verification_create():
        def create(owner):
            values = _body()
            sections = values.get("sections")
            if sections is not None and (not isinstance(sections, list) or not all(isinstance(item, str) for item in sections)):
                raise EvidenceError("证据类型须为字符串列表")
            evidence = RiskOrderEvidenceService(current_app.config).evidence(values.get("orderId"), sections, values.get("identifierType", "auto"))
            if not evidence["candidate"]:
                raise EvidenceError("该订单未命中盈亏原因分类有值规则")
            return _flow().create(owner, evidence)
        return _call(create)

    @api.get("/v1/risk-verification/cases/<case_id>")
    def risk_verification_case(case_id):
        return _call(lambda owner: _flow().get(owner, case_id))

    @api.get("/v1/risk-verification/cases/<case_id>/preview")
    def risk_verification_preview(case_id):
        return _call(lambda owner: _flow().preview(owner, case_id))

    @api.post("/v1/risk-verification/cases/<case_id>/review")
    def risk_verification_review(case_id):
        return _call(lambda owner: _flow().review(owner, case_id, _body().get("version")))

    @api.post("/v1/risk-verification/cases/<case_id>/confirm")
    def risk_verification_confirm(case_id):
        def confirm(owner):
            values = _body()
            return _flow().confirm(owner, case_id, values.get("version"), values.get("conclusion"), values.get("reason"))
        return _call(confirm)

    @api.post("/v1/risk-verification/cases/<case_id>/analyze")
    def risk_verification_analyze(case_id):
        return _call(lambda owner: _flow().analyze(owner, case_id, _body().get("version")))

    @api.post("/v1/risk-verification/cases/<case_id>/recover")
    def risk_verification_recover(case_id):
        return _call(lambda owner: _flow().recover(owner, case_id, _body().get("version")))

    @api.post("/v1/risk-verification/cases/<case_id>/knowledge")
    def risk_verification_draft(case_id):
        def draft(owner):
            values = _body()
            return _flow().draft_knowledge(owner, case_id, values.get("version"), values.get("title"),
                                          values.get("content"), values.get("scope"), values.get("source"))
        return _call(draft)

    @api.get("/v1/risk-verification/knowledge")
    def risk_verification_knowledge():
        return _call(lambda owner: _flow().list_knowledge(owner))

    @api.post("/v1/risk-verification/knowledge/<knowledge_id>/publish")
    def risk_verification_publish(knowledge_id):
        return _call(lambda owner: _flow().publish_knowledge(owner, knowledge_id, _body().get("version")))
