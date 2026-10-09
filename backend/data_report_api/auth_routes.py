from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from .services.auth import AuthError, AuthManager


auth_api = Blueprint("auth", __name__)


def ok(data=None, message: str = "OK"):
    return jsonify({"success": True, "message": message, "data": data})


def manager() -> AuthManager:
    return current_app.extensions["auth_manager"]


def request_context() -> tuple[str, str]:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded or request.remote_addr or "", request.headers.get("User-Agent", "")[:500]


def body() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise AuthError("请求内容必须是JSON对象")
    return value


def set_session_cookie(response, raw_token: str) -> None:
    response.set_cookie(
        current_app.config["AUTH_COOKIE_NAME"],
        raw_token,
        max_age=int(current_app.config["AUTH_ABSOLUTE_TIMEOUT_SECONDS"]),
        httponly=True,
        secure=bool(current_app.config["AUTH_COOKIE_SECURE"]),
        samesite="Lax",
        path="/",
    )


def set_csrf_cookie(response, raw_csrf: str) -> None:
    response.set_cookie(
        current_app.config["AUTH_CSRF_COOKIE_NAME"],
        raw_csrf,
        max_age=int(current_app.config["AUTH_ABSOLUTE_TIMEOUT_SECONDS"]),
        httponly=False,
        secure=bool(current_app.config["AUTH_COOKIE_SECURE"]),
        samesite="Lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        current_app.config["AUTH_COOKIE_NAME"],
        httponly=True,
        secure=bool(current_app.config["AUTH_COOKIE_SECURE"]),
        samesite="Lax",
        path="/",
    )
    response.delete_cookie(
        current_app.config["AUTH_CSRF_COOKIE_NAME"],
        httponly=False,
        secure=bool(current_app.config["AUTH_COOKIE_SECURE"]),
        samesite="Lax",
        path="/",
    )


@auth_api.errorhandler(AuthError)
def auth_error(error: AuthError):
    return jsonify({"success": False, "message": str(error), "data": None, "code": error.code}), error.status


@auth_api.get("/auth/status")
def status():
    if not current_app.config["AUTH_ENABLED"]:
        return ok({"enabled": False, "configured": True})
    return ok({"enabled": True, "configured": manager().store.user_count() > 0})


@auth_api.post("/auth/login")
def login():
    values = body()
    ip_address, user_agent = request_context()
    result = manager().login(
        str(values.get("username", "")), str(values.get("password", "")),
        ip_address, user_agent,
    )
    response = ok(
        {"user": result["user"], "csrfToken": result["csrfToken"]},
        "登录成功",
    )
    set_session_cookie(response, result["sessionToken"])
    set_csrf_cookie(response, result["csrfToken"])
    return response


@auth_api.get("/auth/me")
def me():
    if not current_app.config["AUTH_ENABLED"]:
        return ok({
            "user": {"id": 0, "username": "development", "email": "development@local", "displayName": "开发模式", "isAdmin": True, "isEnabled": True, "mustChangePassword": False},
            "csrfToken": "development",
        })
    return ok({"user": manager().public_user(g.current_user), "csrfToken": g.current_csrf_token})


@auth_api.post("/auth/logout")
def logout():
    ip_address, user_agent = request_context()
    if current_app.config["AUTH_ENABLED"]:
        manager().logout(g.current_user, g.current_session, ip_address, user_agent)
    response = ok(None, "已退出登录")
    clear_session_cookie(response)
    return response


@auth_api.post("/auth/change-password")
def change_password():
    values = body()
    ip_address, user_agent = request_context()
    result = manager().change_password(
        g.current_user,
        str(values.get("currentPassword", "")),
        str(values.get("newPassword", "")),
        ip_address,
        user_agent,
    )
    response = ok({"csrfToken": result["csrfToken"]}, "密码修改成功")
    set_session_cookie(response, result["sessionToken"])
    set_csrf_cookie(response, result["csrfToken"])
    return response


@auth_api.get("/admin/users")
def list_users():
    return ok(manager().users(g.current_user))


@auth_api.post("/admin/users")
def create_user():
    values = body()
    ip_address, user_agent = request_context()
    user = manager().create_user(
        g.current_user,
        username=str(values.get("username", "")),
        display_name=str(values.get("displayName", "")),
        email=str(values.get("email", "")) or None,
        password=str(values.get("initialPassword", "")),
        is_admin=values.get("isAdmin") is True,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ok(user, "账号创建成功"), 201


@auth_api.patch("/admin/users/<int:user_id>")
def update_user(user_id: int):
    values = body()
    ip_address, user_agent = request_context()
    changes = {}
    for api_key, store_key in (
        ("displayName", "display_name"),
        ("email", "email"),
        ("isAdmin", "is_admin"),
        ("isEnabled", "is_enabled"),
    ):
        if api_key in values:
            changes[store_key] = values[api_key]
    user = manager().update_user(
        g.current_user, user_id, changes, ip_address, user_agent
    )
    return ok(user, "账号已更新")


@auth_api.post("/admin/users/<int:user_id>/reset-password")
def reset_password(user_id: int):
    values = body()
    ip_address, user_agent = request_context()
    manager().reset_password(
        g.current_user, user_id, str(values.get("newPassword", "")),
        ip_address, user_agent,
    )
    return ok(None, "密码已重置，用户下次登录必须修改密码")


@auth_api.get("/admin/audits")
def list_audits():
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError as error:
        raise AuthError("limit必须为整数") from error
    return ok(manager().audits(g.current_user, limit))
