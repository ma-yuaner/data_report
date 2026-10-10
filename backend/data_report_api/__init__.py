from __future__ import annotations

from time import perf_counter

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from .auth_routes import auth_api
from .config import Config
from .routes import api
from .services.auth import AuthError, AuthManager, MySqlAuthStore


PUBLIC_AUTH_ENDPOINTS = {"api.health", "auth.login", "auth.status"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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
