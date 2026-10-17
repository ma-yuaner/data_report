from datetime import date, datetime, timezone

from data_report_api.services import target_management
from data_report_api.services.target_management import TargetManagementService


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
    }, source=MainSource())

    assert instance.database == "sibebid"
    assert instance.roster_source.database == "sibedb"
    assert instance.roster_source.config["MYSQL_HOST"] == "roster.example"
    assert instance.roster_source.config["MYSQL_USER"] == "roster_user"


def test_metric_value_keeps_missing_distinct_from_real_zero():
    rows = [{"business_date": date(2026, 10, 1), "actual_value": 0}]

    assert service()._metric_value({"LOSS_AMOUNT": rows}, "LOSS_AMOUNT") == 0
    assert service()._metric_value({}, "LOSS_AMOUNT") is None


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
    assert row["completionRate"] == 0.4
    assert row["remaining"] == 60
    assert row["requiredDaily"] == 3.75
    assert row["yesterday"] == 10
    assert row["dayBefore"] == 30
    assert row["profit"] == 80
    assert row["lossAmount"] is None


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
