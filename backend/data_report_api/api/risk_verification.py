"""Administrator-only risk evidence and review workflow; ERP is read-only."""
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


def _call(action):
    user = getattr(g, "current_user", {})
    if not user.get("is_admin"):
        return jsonify(success=False, message="首版风控核对仅限管理员", data=None), 403
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
        return _call(lambda owner: RiskAutoVerification(current_app.config).result(owner, identifier))

    @api.post("/v1/risk-verification/automatic/orders/<identifier>/sample")
    def risk_automatic_sample(identifier):
        def sample(owner):
            values = _body()
            return RiskAutoVerification(current_app.config).sample(owner, identifier, values.get("resultId"), values.get("outcome"), values.get("reason"))
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
        return _call(lambda owner: {"ai": RiskAI(current_app.config).status(), "access": "admin_owner_only",
                                   "formulaStatus": "partially_confirmed", "source": "ERP_MYSQL",
                                   "rules": [{"id": RULE_ID, "label": "佣金、点击费亏损（去哪儿且有销售佣金）",
                                              "formula": "调整后利润＝出票利润＋销售佣金；调整后利润≥－日志止损值时核实通过（含等号）",
                                              "status": "自动规则已接入；必要字段缺失或止损值冲突时证据不足"}],
                                   "sourceConfigured": current_app.config.get("RISK_VERIFICATION_ERP_EXPLICIT") is True and all(bool(current_app.config.get(f"ERP_MYSQL_{key}")) for key in ("HOST", "DATABASE", "USER", "PASSWORD"))})

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
