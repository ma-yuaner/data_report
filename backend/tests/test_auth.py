from datetime import datetime, timedelta

import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services.auth import MemoryAuthStore


class AuthTestConfig(TestConfig):
    AUTH_ENABLED = True
    AUTH_AUTO_CREATE_TABLES = True
    AUTH_COOKIE_SECURE = False
    AUTH_BOOTSTRAP_ADMIN_USERNAME = "admin"
    AUTH_BOOTSTRAP_ADMIN_PASSWORD = "Admin1234"
    AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME = "测试管理员"
    AUTH_IDLE_TIMEOUT_SECONDS = 4 * 60 * 60
    AUTH_ABSOLUTE_TIMEOUT_SECONDS = 24 * 60 * 60
    AUTH_SESSION_TOUCH_SECONDS = 0
    AUTH_MAX_FAILED_ATTEMPTS = 5
    AUTH_LOCK_SECONDS = 15 * 60


@pytest.fixture()
def auth_app():
    store = MemoryAuthStore()
    app = create_app(AuthTestConfig, auth_store=store)
    return app, store


@pytest.fixture()
def auth_client(auth_app):
    return auth_app[0].test_client()


def login(client, username="admin", password="Admin1234"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def csrf(response):
    return response.get_json()["data"]["csrfToken"]


def change_initial_password(client, login_response, current="Admin1234", new="Changed1234"):
    return client.post(
        "/api/auth/change-password",
        json={"currentPassword": current, "newPassword": new},
        headers={"X-CSRF-Token": csrf(login_response)},
    )


def test_health_is_public_but_business_api_requires_login(auth_client):
    health = auth_client.get("/api/health")
    assert health.status_code == 200
    assert "total;dur=" in health.headers["Server-Timing"]
    response = auth_client.get("/api/v1/dashboard/overview")
    assert response.status_code == 401
    assert response.get_json()["code"] == "AUTH_REQUIRED"


def test_auth_status_uses_startup_state_without_querying_users_again(auth_app):
    app, store = auth_app
    store.user_count = lambda: (_ for _ in ()).throw(AssertionError("unexpected query"))
    response = app.test_client().get("/api/auth/status")
    assert response.status_code == 200
    assert response.get_json()["data"] == {"enabled": True, "configured": True}


def test_passwords_are_bcrypt_hashes(auth_app):
    _app, store = auth_app
    user = store.get_user_by_username("admin")
    assert user is not None
    assert user["password_hash"].startswith(("$2a$", "$2b$", "$2y$"))


def test_first_login_requires_password_change_then_allows_business_api(auth_client):
    login_response = login(auth_client)
    assert login_response.status_code == 200
    assert login_response.get_json()["data"]["user"]["mustChangePassword"] is True

    blocked = auth_client.get("/api/v1/dashboard/overview")
    assert blocked.status_code == 403
    assert blocked.get_json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = change_initial_password(auth_client, login_response)
    assert changed.status_code == 200
    assert auth_client.get("/api/v1/dashboard/overview").status_code == 200

    logout_response = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf(changed)},
    )
    assert logout_response.status_code == 200
    assert login(auth_client, password="Admin1234").status_code == 401
    assert login(auth_client, password="Changed1234").status_code == 200


def test_mutating_requests_require_csrf(auth_client):
    response = login(auth_client)
    rejected = auth_client.post("/api/auth/logout")
    assert rejected.status_code == 403
    assert rejected.get_json()["code"] == "CSRF_INVALID"
    accepted = auth_client.post(
        "/api/auth/logout", headers={"X-CSRF-Token": csrf(response)}
    )
    assert accepted.status_code == 200


def test_login_lock_after_five_failures(auth_app):
    app, _store = auth_app
    client = app.test_client()
    clock = [datetime(2026, 10, 8, 9, 0, 0)]
    app.extensions["auth_manager"].now_fn = lambda: clock[0]

    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    assert login(client).status_code == 401

    clock[0] += timedelta(minutes=15, seconds=1)
    assert login(client).status_code == 200


def test_idle_and_absolute_expiry_are_enforced(auth_app):
    app, _store = auth_app
    client = app.test_client()
    clock = [datetime(2026, 10, 8, 9, 0, 0)]
    app.extensions["auth_manager"].now_fn = lambda: clock[0]

    assert login(client).status_code == 200
    clock[0] += timedelta(hours=4, seconds=1)
    assert client.get("/api/auth/me").status_code == 401

    clock[0] = datetime(2026, 10, 9, 9, 0, 0)
    assert login(client).status_code == 200
    for _ in range(7):
        clock[0] += timedelta(hours=3)
        assert client.get("/api/auth/me").status_code == 200
    clock[0] += timedelta(hours=3)
    assert client.get("/api/auth/me").status_code == 401


def test_admin_can_manage_users_and_ordinary_user_cannot(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)

    created = auth_client.post(
        "/api/admin/users",
        json={
            "username": "analyst01", "displayName": "分析员",
            "email": "analyst01@example.com",
            "initialPassword": "Analyst123", "isAdmin": False,
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created.status_code == 201
    created_user = created.get_json()["data"]
    user_id = created_user["id"]
    assert created_user["email"] == "analyst01@example.com"
    assert auth_client.get("/api/admin/users").status_code == 200

    duplicate_email = auth_client.post(
        "/api/admin/users",
        json={"username": "analyst02", "displayName": "分析员2", "email": "analyst01@example.com", "initialPassword": "Analyst234", "isAdmin": False},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert duplicate_email.status_code == 409
    assert duplicate_email.get_json()["code"] == "EMAIL_EXISTS"

    edited = auth_client.patch(
        f"/api/admin/users/{user_id}",
        json={"displayName": "高级分析员", "email": "analyst-new@example.com"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["email"] == "analyst-new@example.com"

    ordinary_client = auth_client.application.test_client()
    ordinary_login = login(ordinary_client, "analyst01", "Analyst123")
    ordinary_changed = change_initial_password(
        ordinary_client, ordinary_login, "Analyst123", "Analyst456"
    )
    assert ordinary_changed.status_code == 200
    assert ordinary_client.get("/api/admin/users").status_code == 403
    assert ordinary_client.get("/api/v1/admin/telemetry/dashboard").status_code == 403

    disabled = auth_client.patch(
        f"/api/admin/users/{user_id}",
        json={"isEnabled": False},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert disabled.status_code == 200
    assert ordinary_client.get("/api/auth/me").status_code == 401


def test_password_reset_revokes_sessions_and_audits_are_available(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)
    created = auth_client.post(
        "/api/admin/users",
        json={"username": "viewer01", "displayName": "查看员", "email": "viewer01@example.com", "initialPassword": "Viewer123", "isAdmin": False},
        headers={"X-CSRF-Token": admin_csrf},
    ).get_json()["data"]

    viewer_client = auth_client.application.test_client()
    assert login(viewer_client, "viewer01", "Viewer123").status_code == 200
    reset = auth_client.post(
        f"/api/admin/users/{created['id']}/reset-password",
        json={"newPassword": "Viewer456"},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert reset.status_code == 200
    assert viewer_client.get("/api/auth/me").status_code == 401

    audits = auth_client.get("/api/admin/audits").get_json()["data"]
    actions = {row["action"] for row in audits}
    assert {"bootstrap_admin", "login", "change_password", "create_user", "reset_password"} <= actions
