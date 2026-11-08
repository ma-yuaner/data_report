from __future__ import annotations

from threading import Lock
from time import monotonic, perf_counter

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from .auth_routes import auth_api
from .config import Config
from .routes import api
from .services.auth import AuthError, AuthManager, MySqlAuthStore


PUBLIC_AUTH_ENDPOINTS = {"api.health", "auth.login", "auth.status"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def build_adm_workflow_user_options(users, employees, binding_resolver, departments):
    """Build ADM assignee options with login-account IDs as the authority key.

    ERP roster bindings enrich labels and department metadata only.  An enabled
    account with the ADM menu and required permission remains assignable when it
    has no roster binding.
    """
    purposes = {
        "handle": {"adm.handle"},
        "leader": {"adm.assign_operator"},
        "coordinate": {"adm.create", "adm.review"},
    }
    result = {purpose: [] for purpose in purposes}
    employee_by_id = {int(item["id"]): item for item in employees}
    for user in users:
        if not user.get("is_enabled", True):
            continue
        admin = bool(user.get("is_admin"))
        permissions = set(user.get("permissions") or [])
        if not admin and ("adm.view" not in permissions or "adm.center" not in (user.get("menu_codes") or [])):
            continue
        binding = binding_resolver(int(user["id"]))
        employee = None
        if binding and str(binding.get("status") or "ACTIVE") == "ACTIVE":
            employee = employee_by_id.get(int(binding.get("employee_id") or 0))
        account_name = user.get("display_name") or user.get("username") or str(user["id"])
        person = {
            "id": str(user["id"]),
            "name": employee["name"] if employee else account_name,
            "accountName": account_name,
            "rosterEmployeeId": str(employee["id"]) if employee else "",
            "departmentCode": employee.get("departmentCode", "") if employee else "",
            "departmentName": employee.get("departmentName", "") if employee else "",
        }
        for purpose, required in purposes.items():
            if admin or required <= permissions or (purpose == "leader" and "adm.assign" in permissions):
                result[purpose].append(person)
    result["departments"] = departments
    return result


def required_menu_code(path: str) -> str | None:
    if path.startswith("/api/v1/risk-verification"):
        return "risk.verification"
    if path.startswith("/api/v1/hr-mail"):
        return "hr.mail"
    if path.startswith("/api/v1/adm"):
        return "adm.center"
    if path.startswith("/api/v1/data-workbench"):
        return "data_workbench"
    if path.startswith("/api/v1/resource-governance/gds/routes"):
        return "gds_route.diagnosis"
    if path.startswith("/api/v1/resource-governance/gds"):
        return "governance.gds"
    if path.startswith("/api/v1/resource-governance/ota"):
        return "governance.ota"
    if path.startswith("/api/v1/dashboard/"):
        return "overview"
    if path.startswith("/api/v1/analysis/comprehensive"):
        return "analysis.comprehensive"
    if path.startswith("/api/v1/analysis/issue-profit"):
        return "analysis.issue"
    if path.startswith("/api/v1/analysis/business-profit/refund"):
        return "analysis.refund"
    if path.startswith("/api/v1/analysis/business-profit/change"):
        return "analysis.change"
    if path.startswith("/api/v1/analysis/business-profit/ancillary"):
        return "analysis.ancillary"
    if path.startswith("/api/v1/analysis/risk-monthly") or path.startswith("/api/v1/analysis/risk-daily"):
        return "risk.overview"
    if path.startswith("/api/v1/analysis/risk-business/"):
        return "risk"
    if path.startswith("/api/v1/risk-uploads"):
        return "risk.upload"
    if path.startswith((
        "/api/v1/smart-analysis/comprehensive",
    )):
        return "smart.comprehensive"
    if path.startswith((
        "/api/v1/smart-analysis/overview",
        "/api/v1/smart-analysis/trends",
        "/api/v1/smart-analysis/exports/trend",
    )):
        return "smart.overview"
    if path.startswith((
        "/api/v1/smart-analysis/dimensions",
        "/api/v1/smart-analysis/exports/dimensions",
    )):
        return "smart.dimensions"
    if path.startswith((
        "/api/v1/smart-analysis/details",
        "/api/v1/smart-analysis/tickets/",
        "/api/v1/smart-analysis/exports/details",
    )):
        return "smart.details"
    if path.startswith("/api/v1/smart-analysis/templates"):
        return "smart"
    if path.startswith("/api/v1/smart-analysis/filter-options"):
        return "smart"
    if path.startswith("/api/v1/smart-placement/missed-orders"):
        return "smart.placement.missed"
    if path.startswith("/api/v1/smart-placement/orders"):
        return "smart.placement.orders"
    if path.startswith("/api/v1/smart-placement"):
        return "smart.placement.policies"
    if path.startswith("/api/v1/monitoring"):
        return "monitor.center"
    if path.startswith("/api/v1/business-configuration/target-progress"):
        return "business_config.target_progress"
    if path.startswith("/api/v1/business-configuration/targets"):
        return "business_config.targets"
    if path.startswith("/api/v1/problems/") or path == "/api/v1/issues":
        return "problems"
    if path.startswith("/api/v1/assets/"):
        return "data_assets"
    return None


def create_app(config: type[Config] = Config, auth_store=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(auth_api, url_prefix="/api")

    if app.config["AUTH_ENABLED"]:
        store = auth_store or MySqlAuthStore(app.config)
        manager = AuthManager(store, app.config)
        configured = manager.initialize()
        app.extensions["auth_manager"] = manager
        app.extensions["auth_configured"] = configured
        def resolve_hr_mail_user(user_id):
            return manager.store.get_user_by_id(int(user_id))

        app.config["HR_MAIL_USER_RESOLVER"] = resolve_hr_mail_user
        app.config["MISSED_ORDER_USER_RESOLVER"] = resolve_hr_mail_user
        def resolve_adm_user(user_id):
            return manager.store.get_user_by_id(int(user_id))

        app.config["ADM_USER_RESOLVER"] = resolve_adm_user
        def adm_user_options():
            return [{"id": str(user["id"]), "name": user.get("display_name") or user.get("username") or str(user["id"])}
                    for user in manager.store.list_users()
                    if user.get("is_enabled", True) and (user.get("is_admin") or ({"adm.view", "adm.handle"} <= set(user.get("permissions") or []) and "adm.center" in (user.get("menu_codes") or [])))]
        app.config["ADM_USER_OPTIONS"] = adm_user_options
        adm_options_cache = {"expires_at": 0.0, "value": None}
        adm_options_lock = Lock()
        def adm_workflow_user_options():
            from .services.target_management import TargetManagementService

            now = monotonic()
            if adm_options_cache["value"] is not None and now < adm_options_cache["expires_at"]:
                return adm_options_cache["value"]
            with adm_options_lock:
                now = monotonic()
                if adm_options_cache["value"] is not None and now < adm_options_cache["expires_at"]:
                    return adm_options_cache["value"]
                try:
                    employees, departments = TargetManagementService(app.config)._roster_options()
                except Exception as error:
                    # Account permissions are authoritative for ADM assignment.  A
                    # roster outage may remove optional labels/departments, but must
                    # not make otherwise valid login accounts unassignable.
                    app.logger.warning("ADM roster enrichment unavailable: %s", error)
                    employees, departments = [], []
                database = str(app.config.get("ERP_ROSTER_DATABASE", "sibedb"))
                table = str(app.config.get("ERP_ROSTER_TABLE", "system_user"))
                value = build_adm_workflow_user_options(
                    manager.store.list_users(),
                    employees,
                    lambda user_id: manager.store.get_employee_binding(user_id, database, table),
                    departments,
                )
                ttl = max(0, int(app.config.get("ADM_WORKFLOW_OPTIONS_CACHE_TTL", 300)))
                adm_options_cache.update(value=value, expires_at=monotonic() + ttl)
                return value
        app.config["ADM_WORKFLOW_USER_OPTIONS"] = adm_workflow_user_options
        if not configured:
            app.logger.warning(
                "认证表中没有账号；请配置AUTH_BOOTSTRAP_ADMIN_USERNAME和"
                "AUTH_BOOTSTRAP_ADMIN_PASSWORD后重启一次"
            )

    @app.before_request
    def authenticate_request():
        g.request_started_at = perf_counter()
        g.auth_duration_ms = 0.0
        if request.method == "OPTIONS" or not request.path.startswith("/api"):
            return None
        if not app.config["AUTH_ENABLED"]:
            g.current_user = {
                "id": 0, "username": "development", "display_name": "开发模式",
                "is_admin": True, "is_enabled": True, "must_change_password": False,
            }
            return None
        if request.endpoint in PUBLIC_AUTH_ENDPOINTS:
            return None

        manager: AuthManager = app.extensions["auth_manager"]
        raw_token = request.cookies.get(app.config["AUTH_COOKIE_NAME"])
        auth_started_at = perf_counter()
        authenticated = manager.authenticate(raw_token)
        g.auth_duration_ms = (perf_counter() - auth_started_at) * 1000
        if not authenticated:
            return jsonify({
                "success": False, "message": "登录已过期，请重新登录",
                "data": None, "code": "AUTH_REQUIRED",
            }), 401
        user, session = authenticated
        g.current_user = user
        g.current_session = session
        raw_csrf = request.headers.get("X-CSRF-Token")
        g.current_csrf_token = request.cookies.get(app.config["AUTH_CSRF_COOKIE_NAME"], "")
        if request.method not in SAFE_METHODS and not manager.verify_csrf(session, raw_csrf):
            return jsonify({
                "success": False, "message": "页面验证已失效，请刷新后重试",
                "data": None, "code": "CSRF_INVALID",
            }), 403
        allowed_during_password_change = {"auth.me", "auth.change_password", "auth.logout"}
        if bool(user.get("must_change_password")) and request.endpoint not in allowed_during_password_change:
            return jsonify({
                "success": False, "message": "首次登录必须修改密码",
                "data": None, "code": "PASSWORD_CHANGE_REQUIRED",
            }), 403
        menu_code = required_menu_code(request.path)
        if menu_code and not bool(user.get("is_admin")) and menu_code not in set(user.get("menu_codes") or []):
            return jsonify({
                "success": False, "message": "当前账号没有该模块的菜单权限",
                "data": None, "code": "MENU_FORBIDDEN",
            }), 403
        return None

    @app.after_request
    def report_request_timing(response):
        started_at = getattr(g, "request_started_at", None)
        if started_at is None:
            return response
        total_ms = (perf_counter() - started_at) * 1000
        auth_ms = float(getattr(g, "auth_duration_ms", 0.0))
        response.headers["Server-Timing"] = (
            f"auth;dur={auth_ms:.1f}, app;dur={max(0.0, total_ms - auth_ms):.1f}, total;dur={total_ms:.1f}"
        )
        threshold = int(app.config.get("PERFORMANCE_SLOW_REQUEST_MS", 500))
        if total_ms >= threshold:
            app.logger.warning(
                "Slow request method=%s path=%s status=%s total_ms=%.1f auth_ms=%.1f",
                request.method, request.path, response.status_code, total_ms, auth_ms,
            )
        return response

    @app.errorhandler(AuthError)
    def handle_auth_error(error: AuthError):
        return jsonify({
            "success": False, "message": str(error), "data": None, "code": error.code,
        }), error.status

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"success": False, "message": "接口不存在", "data": None}), 404

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        return jsonify({"success": False, "message": "上传文件超过服务器大小限制", "data": None}), 413

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("Unhandled error", exc_info=error)
        return jsonify({"success": False, "message": "服务暂时不可用", "data": None}), 500

    return app
