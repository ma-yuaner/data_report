from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from data_report_api import create_app
from data_report_api.config import TestConfig
from data_report_api.services import risk_business_analysis as module


def metric_row(
    rows=2,
    tickets=3,
    profit=Decimal("-90.12345678"),
    ticket_missing=0,
    profit_missing=0,
    loss_tickets=2,
    loss_profit=Decimal("-100.12345678"),
    loss_ticket_missing=0,
    profit_tickets=1,
    zero_tickets=0,
):
    return (
        rows, tickets, profit, ticket_missing, profit_missing, loss_tickets,
        loss_profit, loss_ticket_missing, profit_tickets, zero_tickets,
    )


def service_with_rows():
    source = MagicMock()
    source.database = "sibebid"
    connection = source.connect.return_value
    summary, trend, dimension, count, orders = [MagicMock() for _ in range(5)]
    connection.cursor.side_effect = [summary, trend, dimension, count, orders]
    summary.fetchone.return_value = metric_row()
    trend.fetchall.return_value = [("2026-09", *metric_row())]
    dimension.fetchall.return_value = [("携程", *metric_row())]
    count.fetchone.return_value = (1,)
    orders.fetchall.return_value = [(
        "2026-09-30", "OTA-1", "REL-1", "781-1", "BIZ-1", "张三",
        "携程", "携程一部", "机票业务1部", "MU", "SHA-PEK", "供应商A",
        "政策员A", "出票员A", "对赌亏损", "利润说明", "已核实", 1,
        Decimal("-50.12345678"), Decimal("-49.00000000"),
    )]
    return source, connection, (summary, trend, dimension, count, orders)


def test_issue_analysis_uses_real_reconcile_fields_and_returns_drilldown():
    source, connection, cursors = service_with_rows()
    with patch.object(module, "DataSource", return_value=source):
        result = module.RiskBusinessAnalysisService({"DATA_MODE": "hive"}).analysis(
            business_type="issue",
            start_value="2026-09-01",
            end_value="2026-09-30",
            group="platform",
            filters={"platform": "携程", "profitStatus": "loss"},
        )

    assert result["available"] is True
    assert result["source"] == "MySQL · sibebid.bi_order_issue_profit_reconcile_year"
    assert result["summary"]["ticketCount"] == 3
    assert result["summary"]["estimatedProfit"] == "-90.12345678"
    assert result["summary"]["averageLossPerTicket"] == "50.06172839"
    assert result["trend"][0]["period"] == "2026-09"
    assert result["dimensions"][0]["name"] == "携程"
    assert result["orders"]["rows"][0]["issueTicketNo"] == "781-1"
    assert result["orders"]["rows"][0]["reason"] == "对赌亏损"

    summary_sql, summary_params = cursors[0].execute.call_args.args
    assert "SUM(ticket_num)" in summary_sql
    assert "SUM(estimated_profit_cny)" in summary_sql
    assert "business_date >= %s" in summary_sql
    assert "NULLIF(TRIM(ota_cname),'') = %s" in summary_sql
    assert "estimated_profit_cny < 0" in summary_sql
    assert summary_params == ["2026-09-01", "2026-10-01", "携程"]
    assert connection.close.call_count == 1
    assert all(cursor.close.call_count == 1 for cursor in cursors)


def test_missing_values_are_not_published_as_zero():
    source, _, cursors = service_with_rows()
    cursors[0].fetchone.return_value = metric_row(
        rows=2, tickets=1, profit=Decimal("-10"), ticket_missing=1,
        profit_missing=1, loss_tickets=1, loss_profit=Decimal("-10"),
    )
    with patch.object(module, "DataSource", return_value=source):
        result = module.RiskBusinessAnalysisService({}).analysis(
            business_type="issue", start_value="2026-09-01", end_value="2026-09-30"
        )
    assert result["summary"]["status"] == "incomplete"
    assert result["summary"]["ticketCount"] is None
    assert result["summary"]["estimatedProfit"] is None
    assert result["summary"]["knownProfit"] == "-10"
    assert result["summary"]["lossTicketCount"] is None


def test_refund_and_change_do_not_fabricate_reason_dimension():
    source = MagicMock()
    with patch.object(module, "DataSource", return_value=source):
        service = module.RiskBusinessAnalysisService({})
        with pytest.raises(ValueError, match="不支持当前分析维度"):
            service.analysis(business_type="refund", group="reason")
        with pytest.raises(ValueError, match="尚无标准盈亏原因字段"):
            service.analysis(business_type="change", filters={"reason": "原因A"})
    source.connect.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"business_type": "ancillary"},
        {"business_type": "issue", "group": "raw_sql"},
        {"business_type": "issue", "filters": {"profitStatus": "bad"}},
        {"business_type": "issue", "filters": {"platform": "a" * 151}},
        {"business_type": "issue", "page_value": "0"},
        {"business_type": "issue", "page_size_value": "101"},
    ],
)
def test_invalid_inputs_fail_before_mysql(kwargs):
    source = MagicMock()
    with patch.object(module, "DataSource", return_value=source):
        with pytest.raises(ValueError):
            module.RiskBusinessAnalysisService({}).analysis(**kwargs)
    source.connect.assert_not_called()


def test_mysql_failure_returns_empty_real_data_state():
    source = MagicMock()
    source.database = "sibebid"
    source.connect.side_effect = RuntimeError("private password detail")
    with patch.object(module, "DataSource", return_value=source):
        result = module.RiskBusinessAnalysisService({}).analysis(business_type="issue")
    assert result["available"] is False
    assert "private" not in result["error"]
    assert result["orders"]["rows"] == []
    assert result["trend"] == []


def test_route_and_input_validation():
    client = create_app(TestConfig).test_client()
    response = client.get("/api/v1/analysis/risk-business/issue")
    assert response.status_code == 200
    assert response.json["data"]["available"] is False
    assert client.get("/api/v1/analysis/risk-business/bad").status_code == 400
    assert client.get("/api/v1/analysis/risk-business/refund?groupBy=reason").status_code == 400
