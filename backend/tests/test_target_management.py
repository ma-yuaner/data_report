from datetime import date, datetime, timezone
from decimal import Decimal

from data_report_api.services import target_management
from data_report_api.services.target_management import (
    TargetManagementService,
    _boolean_query,
    _change_action,
    _json_ready,
)


def service() -> TargetManagementService:
    return TargetManagementService.__new__(TargetManagementService)


class MainSource:
    database = "sibebid"


def test_roster_can_use_an_independent_mysql_connection():
    instance = TargetManagementService({
        "DATA_MODE": "mysql",
        "MYSQL_HOST": "main.example",
        "MYSQL_PORT": 3306,
        "MYSQL_DATABASE": "sibebid",
        "MYSQL_USER": "main_user",
        "MYSQL_PASSWORD": "main_password",
        "ERP_ROSTER_MYSQL_HOST": "roster.example",
        "ERP_ROSTER_MYSQL_PORT": 63306,
        "ERP_ROSTER_MYSQL_USER": "roster_user",
        "ERP_ROSTER_MYSQL_PASSWORD": "roster_password",
        "ERP_ROSTER_DATABASE": "sibedb",
        "ERP_ROSTER_USER_TABLE": "system_user",
        "ERP_ROSTER_USER_DEPARTMENT_TABLE": "system_user_department",
        "ERP_ROSTER_ORG_TABLE": "base_organization",
    }, source=MainSource())

    assert instance.database == "sibebid"
    assert instance.roster_source.database == "sibedb"
    assert instance.roster_source.config["MYSQL_HOST"] == "roster.example"
    assert instance.roster_source.config["MYSQL_USER"] == "roster_user"
    assert instance._roster_users == "sibedb.system_user"
    assert instance._roster_user_departments == "sibedb.system_user_department"
    assert instance._roster_orgs == "sibedb.base_organization"


def test_metric_value_keeps_missing_distinct_from_real_zero():
    rows = [{"business_date": date(2026, 10, 1), "actual_value": 0}]

    assert service()._metric_value({"LOSS_AMOUNT": rows}, "LOSS_AMOUNT") == 0
    assert service()._metric_value({}, "LOSS_AMOUNT") is None


def test_dashboard_metric_filters_escape_percent_for_pymysql_interpolation():
    class Cursor:
        def execute(self, query, params):
            # PyMySQL applies Python-style percent interpolation when parameters
            # are supplied. Literal LIKE wildcards must therefore be escaped.
            self.rendered_query = query % tuple(repr(value) for value in params)

        def fetchall(self):
            return []

    instance = service()
    instance.database = "sibebid"

    for scene in ("GDS", "POLICY"):
        cursor = Cursor()
        assert instance._dashboard_metric_rows(
            cursor, scene, date(2026, 10, 1), date(2026, 10, 22)
        ) == []
        assert "LIKE" in cursor.rendered_query


def test_include_unconfigured_query_defaults_to_false_and_validates_values():
    assert _boolean_query(None) is False
    assert _boolean_query("false") is False
    assert _boolean_query("true") is True

    try:
        _boolean_query("sometimes")
    except ValueError as error:
        assert "includeUnconfigured" in str(error)
    else:
        raise AssertionError("invalid includeUnconfigured value must fail")


def test_target_change_action_distinguishes_create_update_pause_and_resume():
    assert _change_action(None, "ACTIVE") == "CREATE"
    assert _change_action({"items": [{"enabled": 1}]}, "ACTIVE") == "UPDATE"
    assert _change_action({"items": [{"enabled": 1}]}, "PAUSED") == "PAUSE"
    assert _change_action({"items": [{"enabled": 0}]}, "ACTIVE") == "RESUME"


def test_target_audit_snapshot_is_json_serializable():
    snapshot = _json_ready({
        "target": Decimal("100.0000"),
        "createdAt": datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc),
        "members": (318, 343),
    })

    assert snapshot == {
        "target": "100.0000",
        "createdAt": "2026-10-18T09:00:00+00:00",
        "members": [318, 343],
    }


def test_dashboard_roster_uses_user_department_link_table():
    class Cursor:
        query = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query):
            self.query = query

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self, *_args):
            return self.cursor_instance

        def close(self):
            pass

    class Source:
        def __init__(self):
            self.connection = Connection()

        def connect(self):
            return self.connection

    instance = service()
    instance.roster_database = "sibedb"
    instance.roster_user_table = "system_user"
    instance.roster_user_department_table = "system_user_department"
    instance.roster_org_table = "base_organization"
    instance.roster_source = Source()

    assert instance._dashboard_roster() == {}
    query = instance.roster_source.connection.cursor_instance.query
    assert "sibedb.system_user_department" in query
    assert "rud.department_id" in query
    assert "ru.org_id" not in query
    assert "ru.enabled=0" in query
    assert "LEFT JOIN" in query


def test_roster_options_uses_zero_as_enabled_and_keeps_users_without_department():
    class Cursor:
        def __init__(self):
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, *_params):
            self.queries.append(query)

        def fetchall(self):
            if len(self.queries) == 1:
                return [{
                    "id": 318, "username": "", "name": "李清芳", "wechat_id": "",
                    "department_code": "", "department_name": "",
                }]
            return [{"code": "BUSINESS", "name": "业务部"}]

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self, *_args):
            return self.cursor_instance

        def close(self):
            pass

    class Source:
        def __init__(self):
            self.connection = Connection()

        def connect(self):
            return self.connection

    instance = service()
    instance.roster_database = "sibedb"
    instance.roster_user_table = "system_user"
    instance.roster_user_department_table = "system_user_department"
    instance.roster_org_table = "base_organization"
    instance.roster_source = Source()

    employees, departments = instance._roster_options()

    assert employees[0]["name"] == "李清芳"
    assert employees[0]["departmentCode"] == ""
    assert departments == [{"code": "BUSINESS", "name": "业务部"}]
    assert "ru.enabled=0" in instance.roster_source.connection.cursor_instance.queries[0]
    assert "LEFT JOIN" in instance.roster_source.connection.cursor_instance.queries[0]


def test_progress_metrics_derives_remaining_without_inventing_loss(monkeypatch):
    monkeypatch.setattr(
        target_management,
        "business_now",
        lambda: datetime(2026, 10, 16, 8, tzinfo=timezone.utc),
    )
    base = {
        "metricCode": "ISSUED_AIRLIFT_SEGMENT", "target": 100, "actual": None,
        "completionRate": None, "expectedRate": None, "progressGapRate": None,
        "remaining": None, "requiredDaily": None, "profit": None,
        "profitPerSegment": None, "yesterday": None, "dataStatus": "PENDING_ETL",
        "dataThroughDate": None,
    }
    metrics = {
        "ISSUED_AIRLIFT_SEGMENT": [
            {"business_date": date(2026, 10, 14), "actual_value": 30, "ticket_count": 20},
            {"business_date": date(2026, 10, 15), "actual_value": 10, "ticket_count": 8},
        ],
        "ISSUE_PROFIT": [
            {"business_date": date(2026, 10, 15), "actual_value": 80, "ticket_count": None},
        ],
    }

    row = service()._progress_metrics(date(2026, 10, 1), date(2026, 10, 31), metrics, base)

    assert row["actual"] == 40
    assert row["actualThroughYesterday"] == 40
    assert row["todayActual"] is None
    assert row["completionRate"] == 0.4
    assert row["expectedRate"] == 16 / 31
    assert row["remaining"] == 60
    assert row["requiredDaily"] == 3.75
    assert row["yesterday"] == 10
    assert row["dayBefore"] == 30
    assert row["profit"] == 80
    assert row["lossAmount"] is None


def test_progress_metrics_prefers_current_dws_metrics_over_stale_ads_snapshot(monkeypatch):
    monkeypatch.setattr(
        target_management,
        "business_now",
        lambda: datetime(2026, 10, 16, 8, tzinfo=timezone.utc),
    )
    base = {
        "metricCode": "REWARD_SEGMENT", "target": 100, "actual": 0,
        "completionRate": 0, "expectedRate": 0.5, "progressGapRate": -0.5,
        "remaining": 100, "requiredDaily": 10, "profit": None,
        "profitPerSegment": None, "yesterday": 0, "dataStatus": "READY",
        "dataThroughDate": "2026-10-01",
    }
    metrics = {
        "REWARD_SEGMENT": [
            {"business_date": date(2026, 10, 15), "actual_value": 12, "ticket_count": 8},
        ],
    }

    row = service()._progress_metrics(date(2026, 10, 1), date(2026, 10, 31), metrics, base)

    assert row["actual"] == 12
    assert row["actualThroughYesterday"] == 12
    assert row["completionRate"] == 0.12
    assert row["remaining"] == 88
    assert row["dataThroughDate"] == "2026-10-15"


def test_policy_progress_keeps_each_gds_completion_breakdown(monkeypatch):
    monkeypatch.setattr(
        target_management,
        "business_now",
        lambda: datetime(2026, 10, 2, 8, tzinfo=timezone.utc),
    )
    target = {
        "id": "POLICY:1:SD01:PG:318", "policyCode": "PG", "dimensionKey": "",
        "ownerUserId": 318, "metricCode": "REWARD_SEGMENT", "target": 30,
        "actual": 0, "completionRate": 0, "expectedRate": None, "progressGapRate": None,
        "remaining": 30, "requiredDaily": None, "profit": None, "profitPerSegment": None,
        "yesterday": 0, "dataStatus": "READY", "dataThroughDate": "2026-10-01",
        "gdsBreakdown": {
            "1A": {"itemId": 1, "target": 20, "actual": 0, "yesterday": 0, "dataStatus": "READY"},
            "1G": {"itemId": 2, "target": 10, "actual": 0, "yesterday": 0, "dataStatus": "READY"},
        },
    }
    metric_rows = [
        {"scope_code": "PG", "metric_code": "REWARD_SEGMENT", "gds_code": "1A", "business_date": date(2026, 10, 1), "actual_value": 4, "ticket_count": 2, "data_status": "READY"},
        {"scope_code": "PG", "metric_code": "REWARD_SEGMENT", "gds_code": "1A", "business_date": date(2026, 10, 2), "actual_value": 3, "ticket_count": 2, "data_status": "READY"},
        {"scope_code": "PG", "metric_code": "REWARD_SEGMENT", "gds_code": "1G", "business_date": date(2026, 10, 1), "actual_value": 2, "ticket_count": 1, "data_status": "READY"},
        {"scope_code": "PG", "metric_code": "REWARD_SEGMENT", "gds_code": "1G", "business_date": date(2026, 10, 2), "actual_value": 3, "ticket_count": 2, "data_status": "READY"},
    ]

    rows = service()._configured_progress_rows(
        "POLICY", "2026-10", date(2026, 10, 1), date(2026, 10, 31),
        [target], metric_rows, {},
    )

    assert rows[0]["actual"] == 12
    assert rows[0]["gdsBreakdown"]["1A"]["actual"] == 7
    assert rows[0]["gdsBreakdown"]["1A"]["todayActual"] == 3
    assert rows[0]["gdsBreakdown"]["1G"]["actual"] == 5


def test_platform_dashboard_keeps_unconfigured_master_platform_visible():
    masters = [{"code": "OTA-1", "name": "平台一", "full_name": "平台一有限公司"}]

    rows = service()._platform_progress_rows(
        "2026-10", date(2026, 10, 1), date(2026, 10, 31), masters, [], [], {},
    )

    assert len(rows) == 1
    assert rows[0]["platformCode"] == "OTA-1"
    assert rows[0]["configured"] is False
    assert rows[0]["target"] == 0
    assert rows[0]["actual"] is None
    assert rows[0]["lossAmount"] is None


def test_platform_dashboard_defaults_to_configured_and_searches_current_scope(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            pass

        def fetchall(self):
            return [
                {"code": "OTA-1", "name": "平台一", "full_name": "平台一有限公司"},
                {"code": "OTA-2", "name": "平台二", "full_name": "平台二有限公司"},
            ]

    class Connection:
        def cursor(self, *_args):
            return Cursor()

        def close(self):
            pass

    class Source:
        def connect(self):
            return Connection()

    instance = service()
    instance.source = Source()
    instance.platform_database = "sibelog"
    instance.platform_table = "sibe_ota"
    monkeypatch.setattr(instance, "_dashboard_target_rows", lambda *_args: [])
    monkeypatch.setattr(instance, "_public_rows", lambda *_args: [])
    monkeypatch.setattr(instance, "_dashboard_metric_rows", lambda *_args: [])
    monkeypatch.setattr(instance, "_dashboard_roster", lambda: {})
    dashboard_rows = [
        {
            "id": "PLATFORM:OTA-1", "configured": True, "platformCode": "OTA-1", "platform": "平台一",
            "gds": None, "policyCode": "", "policy": None, "policyLeaderName": "", "policyMemberNames": [],
            "department": "业务部", "owner": "张三", "target": 100.0, "actual": 40.0,
            "actualThroughYesterday": 30.0, "todayActual": 10.0,
            "todayRequired": 12.0, "todayRemaining": 2.0,
            "expectedRate": 0.5, "remaining": 60.0, "requiredDaily": 3.75,
            "profit": 80.0, "lossAmount": None, "dataThroughDate": "2026-10-19",
        },
        {
            "id": "PLATFORM:OTA-2", "configured": False, "platformCode": "OTA-2", "platform": "平台二",
            "gds": None, "policyCode": "", "policy": None, "policyLeaderName": "", "policyMemberNames": [],
            "department": "", "owner": "", "target": 0.0, "actual": None,
            "actualThroughYesterday": None, "todayActual": None,
            "todayRequired": None, "todayRemaining": None,
            "expectedRate": None, "remaining": None, "requiredDaily": None,
            "profit": None, "lossAmount": None, "dataThroughDate": None,
        },
    ]
    monkeypatch.setattr(instance, "_platform_progress_rows", lambda *_args: list(dashboard_rows))
    user = {"permissions": ["business_config.target_progress.view"]}

    default_result = instance.progress_dashboard(
        user, scene_value="PLATFORM", period_value="2026-10",
    )
    expanded_result = instance.progress_dashboard(
        user, scene_value="PLATFORM", period_value="2026-10",
        include_unconfigured_value="true", keyword_value="平台二",
    )

    assert [row["platformCode"] for row in default_result["rows"]] == ["OTA-1"]
    assert default_result["summary"] == {
        "scopeCount": 2, "visibleCount": 1, "configuredCount": 1, "progressReadyCount": 1,
        "target": 100.0, "actual": 40.0, "completionRate": 0.4,
        "actualThroughYesterday": 30.0, "todayActual": 10.0,
        "todayRequired": 12.0, "todayRemaining": 2.0,
        "expectedRate": 0.5, "progressGapRate": -0.1,
        "remaining": 60.0, "requiredDaily": 3.75,
        "profit": 80.0, "lossAmount": None,
    }
    assert [row["platformCode"] for row in expanded_result["rows"]] == ["OTA-2"]
    assert expanded_result["summary"]["scopeCount"] == 2
    assert expanded_result["summary"]["configuredCount"] == 1
    assert expanded_result["summary"]["visibleCount"] == 1
    assert expanded_result["includeUnconfigured"] is True
