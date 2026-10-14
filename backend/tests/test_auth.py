from datetime import datetime, timedelta

import pytest

from data_report_api import create_app, required_menu_code
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
    assert created_user["businessRoles"] == []
    assert auth_client.get("/api/admin/users").status_code == 200

    roles = auth_client.get("/api/admin/business-roles")
    assert roles.status_code == 200
    assert {row["code"] for row in roles.get_json()["data"]} == {
        "DATA_ENTRY", "DATA_MANAGER", "POLICY_MANAGER", "POLICY_OPERATOR"
    }
    assigned = auth_client.put(
        f"/api/admin/users/{user_id}/business-roles",
        json={"roleCodes": ["DATA_ENTRY", "POLICY_OPERATOR"]},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert assigned.status_code == 200
    assert {row["code"] for row in assigned.get_json()["data"]["businessRoles"]} == {
        "DATA_ENTRY", "POLICY_OPERATOR"
    }
    assert set(assigned.get_json()["data"]["permissions"]) == {
        "smart_placement.create", "smart_placement.edit", "smart_placement.delete",
        "smart_placement.withdraw",
        "smart_placement.claim", "smart_placement.execute",
        "smart_placement.orders.attention",
    }
    assert assigned.get_json()["data"]["menuCodes"] == [
        "smart", "smart.placement.orders", "smart.placement.policies",
    ]
    menu_catalog = auth_client.get("/api/admin/menu-catalog")
    assert menu_catalog.status_code == 200
    assert "smart.placement.policies" in {row["code"] for row in menu_catalog.get_json()["data"]}
    assert all("groupCode" in row for row in menu_catalog.get_json()["data"])
    menu_assigned = auth_client.put(
        f"/api/admin/users/{user_id}/menus",
        json={"menuCodes": ["smart"]},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert menu_assigned.status_code == 200
    assert menu_assigned.get_json()["data"]["menuCodes"] == [
        "smart", "smart.details", "smart.dimensions", "smart.overview",
        "smart.placement.orders", "smart.placement.policies",
    ]

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
    forbidden_module = ordinary_client.get("/api/v1/dashboard/overview")
    assert forbidden_module.status_code == 403
    assert forbidden_module.get_json()["code"] == "MENU_FORBIDDEN"
    assert ordinary_client.get("/api/admin/users").status_code == 403
    assert ordinary_client.get("/api/v1/admin/telemetry/dashboard").status_code == 403

    disabled = auth_client.patch(
        f"/api/admin/users/{user_id}",
        json={"isEnabled": False},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert disabled.status_code == 200
    assert ordinary_client.get("/api/auth/me").status_code == 401


def test_admin_can_bind_account_to_active_erp_employee(auth_app):
    app, store = auth_app
    store.employees = [{
        "id": 901,
        "user_name": "pjp",
        "cname": "皮军平",
        "work_number": "W00901",
        "wechat_id": "wecom_pjp",
        "mobilephone": "13800000001",
        "status": 1,
        "enabled": 0,
        "update_time": datetime(2026, 10, 13, 9, 0, 0),
    }]
    client = app.test_client()
    changed = change_initial_password(client, login(client))
    admin_csrf = csrf(changed)
    created = client.post(
        "/api/admin/users",
        json={
            "username": "policy01", "displayName": "智能政策员",
            "initialPassword": "Policy123", "isAdmin": False,
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    user_id = created.get_json()["data"]["id"]

    employees = client.get("/api/admin/employees?keyword=皮军平")
    assert employees.status_code == 200
    assert employees.get_json()["data"][0]["wechatId"] == "wecom_pjp"

    bound = client.put(
        f"/api/admin/users/{user_id}/employee-binding",
        json={"employeeId": 901},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert bound.status_code == 200
    assert bound.get_json()["data"]["status"] == "ACTIVE"
    assert bound.get_json()["data"]["employee"]["displayName"] == "皮军平"

    queried = client.get(f"/api/admin/users/{user_id}/employee-binding")
    assert queried.get_json()["data"]["employee"]["hasNotificationIdentity"] is True


def test_admin_configures_role_menus_permissions_and_assigns_role_on_create(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)

    existing = auth_client.get("/api/admin/roles")
    assert existing.status_code == 200
    role_scopes = {row["code"]: row["dataScopes"] for row in existing.get_json()["data"]}
    assert role_scopes["DATA_ENTRY"]["smart_placement.task"] == "SELF"
    assert role_scopes["DATA_MANAGER"]["smart_placement.order"] == "ALL"
    assert role_scopes["POLICY_MANAGER"]["smart_placement.task"] == "MANAGED"
    assert role_scopes["POLICY_OPERATOR"]["smart_placement.order"] == "SELF"
    role_menus = {row["code"]: row["menuCodes"] for row in existing.get_json()["data"]}
    assert role_menus["DATA_ENTRY"] == ["smart.placement.policies"]
    assert role_menus["DATA_MANAGER"] == ["smart.placement.policies"]
    assert role_menus["POLICY_MANAGER"] == ["smart.placement.policies"]
    assert role_menus["POLICY_OPERATOR"] == ["smart.placement.policies", "smart.placement.orders"]

    invalid = auth_client.post(
        "/api/admin/roles",
        json={
            "roleCode": "SMART_CREATOR", "name": "智能录入测试",
            "description": "缺少智能分析菜单", "isActive": True,
            "menuCodes": [], "permissions": ["smart_placement.create"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert invalid.status_code == 400

    created_role = auth_client.post(
        "/api/admin/roles",
        json={
            "roleCode": "RISK_VIEWER", "name": "风控查看员",
            "description": "查看风控分析", "isActive": True,
            "menuCodes": ["risk.overview"], "permissions": [],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created_role.status_code == 201
    assert created_role.get_json()["data"]["menuCodes"] == ["risk.overview"]

    created_user = auth_client.post(
        "/api/admin/users",
        json={
            "username": "riskviewer", "displayName": "风控查看员",
            "email": "riskviewer@example.com", "initialPassword": "Riskview123",
            "isAdmin": False, "roleCodes": ["RISK_VIEWER"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created_user.status_code == 201
    user = created_user.get_json()["data"]
    assert [row["code"] for row in user["businessRoles"]] == ["RISK_VIEWER"]
    assert user["menuCodes"] == ["risk", "risk.overview"]
    assert user["permissions"] == []

    updated_role = auth_client.put(
        "/api/admin/roles/RISK_VIEWER",
        json={
            "name": "风控与智能查看员", "description": "查看风控并录入投放机会",
            "isActive": True, "menuCodes": ["risk.overview", "smart.placement.policies"],
            "permissions": ["smart_placement.create"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert updated_role.status_code == 200
    refreshed_users = auth_client.get("/api/admin/users").get_json()["data"]
    refreshed = next(row for row in refreshed_users if row["id"] == user["id"])
    assert refreshed["menuCodes"] == [
        "risk", "risk.overview", "smart", "smart.placement.policies",
    ]
    assert refreshed["permissions"] == ["smart_placement.create"]


def test_admin_configures_manager_member_relationship(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)
    manager_user = auth_client.post(
        "/api/admin/users",
        json={
            "username": "manager01", "displayName": "业务经理",
            "email": "manager01@example.com", "initialPassword": "Manager123",
            "isAdmin": False, "roleCodes": ["POLICY_MANAGER"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    ).get_json()["data"]
    member_user = auth_client.post(
        "/api/admin/users",
        json={
            "username": "member01", "displayName": "智能业务员",
            "email": "member01@example.com", "initialPassword": "Member123",
            "isAdmin": False, "roleCodes": ["POLICY_OPERATOR"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    ).get_json()["data"]

    saved = auth_client.put(
        f"/api/admin/users/{manager_user['id']}/managed-members",
        json={"resourceCode": "smart_placement", "memberUserIds": [member_user["id"]]},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert saved.status_code == 200
    assert saved.get_json()["data"]["memberUserIds"] == [member_user["id"]]
    loaded = auth_client.get(
        f"/api/admin/users/{manager_user['id']}/managed-members?resourceCode=smart_placement"
    )
    assert loaded.status_code == 200
    assert loaded.get_json()["data"] == {
        "resourceCode": "smart_placement", "memberUserIds": [member_user["id"]],
    }


def test_builtin_role_update_reaches_active_users_and_is_not_reset_on_initialize(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)
    created = auth_client.post(
        "/api/admin/users",
        json={
            "username": "operator01", "displayName": "智能业务执行员",
            "email": "operator01@example.com", "initialPassword": "Operator123",
            "isAdmin": False, "roleCodes": ["POLICY_OPERATOR"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created.status_code == 201

    operator_client = auth_client.application.test_client()
    operator_login = login(operator_client, "operator01", "Operator123")
    operator_changed = change_initial_password(
        operator_client, operator_login, "Operator123", "Operator456"
    )
    assert operator_changed.status_code == 200
    before = operator_client.get("/api/auth/me").get_json()["data"]["user"]
    assert "smart_placement.claim" in before["permissions"]

    updated = auth_client.put(
        "/api/admin/roles/POLICY_OPERATOR",
        json={
            "name": "智能业务执行员", "description": "登记投放并处理收单",
            "isActive": True,
            "menuCodes": ["smart.placement.policies", "smart.placement.orders"],
            "permissions": [
                "smart_placement.execute", "smart_placement.orders.attention",
            ],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert updated.status_code == 200

    after = operator_client.get("/api/auth/me").get_json()["data"]["user"]
    assert "smart_placement.claim" not in after["permissions"]
    denied = operator_client.post(
        "/api/v1/smart-placement/tasks/999/claim",
        json={"plannedCompleteAt": "2026-10-12 12:00:00"},
        headers={"X-CSRF-Token": csrf(operator_changed)},
    )
    assert denied.status_code == 403

    auth_client.application.extensions["auth_manager"].initialize()
    roles = auth_client.get("/api/admin/roles").get_json()["data"]
    operator_role = next(row for row in roles if row["code"] == "POLICY_OPERATOR")
    assert "smart_placement.claim" not in operator_role["permissions"]

    audits = auth_client.get("/api/admin/audits").get_json()["data"]
    audit = next(row for row in audits if row["action"] == "update_role")
    assert audit["detail"]["roleCode"] == "POLICY_OPERATOR"
    assert "smart_placement.claim" in audit["detail"]["before"]["permissions"]
    assert "smart_placement.claim" not in audit["detail"]["after"]["permissions"]


def test_admin_can_apply_personal_permission_overrides(auth_client):
    admin_login = login(auth_client)
    changed = change_initial_password(auth_client, admin_login)
    admin_csrf = csrf(changed)
    created = auth_client.post(
        "/api/admin/users",
        json={
            "username": "business01", "displayName": "业务经理甲",
            "email": "business01@example.com", "initialPassword": "Business123",
            "isAdmin": False, "roleCodes": ["POLICY_MANAGER"],
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created.status_code == 201
    user = created.get_json()["data"]
    assert user["rolePermissions"] == ["smart_placement.review_policy"]
    assert user["permissions"] == ["smart_placement.review_policy"]

    updated = auth_client.put(
        f"/api/admin/users/{user['id']}/permissions",
        json={
            "overrides": {
                "smart_placement.review_policy": "DENY",
                "smart_placement.claim": "ALLOW",
            }
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert updated.status_code == 200
    body = updated.get_json()["data"]
    assert body["rolePermissions"] == ["smart_placement.review_policy"]
    assert body["permissionOverrides"] == {
        "smart_placement.review_policy": "DENY",
        "smart_placement.claim": "ALLOW",
    }
    assert body["permissions"] == ["smart_placement.claim"]
    assert body["menuCodes"] == ["smart", "smart.placement.policies"]

    invalid = auth_client.put(
        f"/api/admin/users/{user['id']}/permissions",
        json={"overrides": {"smart_placement.claim": "MAYBE"}},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert invalid.status_code == 400


def test_page_level_menu_mapping_protects_smart_policy_and_order_pages_separately():
    assert required_menu_code("/api/v1/smart-analysis/overview") == "smart.overview"
    assert required_menu_code("/api/v1/smart-analysis/dimensions") == "smart.dimensions"
    assert required_menu_code("/api/v1/smart-analysis/details") == "smart.details"
    assert required_menu_code("/api/v1/smart-analysis/filter-options") == "smart"
    assert required_menu_code("/api/v1/smart-placement/tasks") == "smart.placement.policies"
    assert required_menu_code("/api/v1/smart-placement/orders") == "smart.placement.orders"
    assert required_menu_code("/api/v1/analysis/comprehensive/details") == "analysis.comprehensive"
    assert required_menu_code("/api/v1/resource-governance/overview") == "governance.gds_ota"
    assert required_menu_code("/api/v1/risk-uploads") == "risk.upload"


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
