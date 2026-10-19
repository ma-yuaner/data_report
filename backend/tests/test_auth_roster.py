from __future__ import annotations

from data_report_api.services.auth import MySqlAuthStore


def auth_config() -> dict:
    return {
        "DATA_MODE": "mysql",
        "MYSQL_HOST": "primary-db",
        "MYSQL_PORT": 3306,
        "MYSQL_DATABASE": "sibebid",
        "MYSQL_USER": "primary-user",
        "MYSQL_PASSWORD": "primary-password",
        "MYSQL_CHARSET": "utf8mb4",
        "MYSQL_CONNECT_TIMEOUT": 10,
        "MYSQL_READ_TIMEOUT": 60,
        "MYSQL_WRITE_TIMEOUT": 60,
        "MYSQL_POOL_SIZE": 12,
        "MYSQL_POOL_MIN_CACHED": 2,
        "MYSQL_TIME_ZONE": "+08:00",
        "ERP_MYSQL_HOST": "erp-db",
        "ERP_MYSQL_PORT": 63306,
        "ERP_MYSQL_DATABASE": "sibebd",
        "ERP_MYSQL_USER": "erp-reader",
        "ERP_MYSQL_PASSWORD": "erp-password",
        "ERP_MYSQL_POOL_SIZE": 4,
        "ERP_MYSQL_POOL_MIN_CACHED": 1,
        "ERP_ROSTER_DATABASE": "sibebd",
        "ERP_ROSTER_TABLE": "system_user",
    }


def test_mysql_auth_store_has_independent_roster_source():
    store = MySqlAuthStore(auth_config())

    assert store.source.database == "sibebid"
    assert store.source.config["MYSQL_HOST"] == "primary-db"
    assert store.roster_source.database == "sibebd"
    assert store.roster_source.config["MYSQL_HOST"] == "erp-db"
    assert store.roster_source.config["MYSQL_USER"] == "erp-reader"


def test_mysql_auth_store_reuses_primary_connection_when_erp_is_not_configured():
    config = auth_config()
    for key in tuple(config):
        if key.startswith("ERP_MYSQL_"):
            config.pop(key)
    config["MYSQL_PORT"] = 63306

    store = MySqlAuthStore(config)

    assert store.roster_source.database == "sibebd"
    assert store.roster_source.config["MYSQL_HOST"] == "primary-db"
    assert store.roster_source.config["MYSQL_PORT"] == 63306
    assert store.roster_source.config["MYSQL_USER"] == "primary-user"


def test_employee_search_uses_roster_source(monkeypatch):
    store = MySqlAuthStore(auth_config())
    observed = {}

    def fake_fetchall(source, sql, params=()):
        observed.update(source=source, sql=sql, params=params)
        return []

    monkeypatch.setattr(store, "_fetchall_from", fake_fetchall)

    assert store.search_employees("sibebd", "system_user", "皮军平") == []
    assert observed["source"] is store.roster_source
    assert "`sibebd`.`system_user`" in observed["sql"]


def test_employee_binding_falls_back_to_local_snapshot_when_erp_is_unavailable(monkeypatch):
    store = MySqlAuthStore(auth_config())
    monkeypatch.setattr(store, "_fetchone", lambda sql, params=(): {
        "sys_user_id": 7,
        "employee_id": 901,
        "status": "ACTIVE",
        "employee_name_snapshot": "皮军平",
        "work_number_snapshot": "W00901",
        "wechat_id_snapshot": "wecom_pjp",
        "mobile_snapshot": "13800000001",
    })

    def unavailable(*args, **kwargs):
        raise RuntimeError("ERP unavailable")

    monkeypatch.setattr(store, "_fetchone_from", unavailable)

    binding = store.get_employee_binding(7, "sibebd", "system_user")
    assert binding is not None
    assert binding["employee_name_snapshot"] == "皮军平"
    assert binding["wechat_id_snapshot"] == "wecom_pjp"
