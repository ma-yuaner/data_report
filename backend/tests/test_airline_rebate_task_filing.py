import json
from importlib import import_module
from io import BytesIO
from unittest.mock import patch

import pytest
from flask import Blueprint, Flask, g
from pypdf import PdfWriter

from data_report_api.api.airline_rebates import ROOT, register_routes
from data_report_api.services.airline_rebates import extraction, jobs
from data_report_api.services.airline_rebates.store import connect


@pytest.mark.parametrize("source, mode, hostname", [
    ("dedicated", "json_schema", "localhost"),
    ("adm", "json_schema", "dashscope.aliyuncs.com"),
    ("adm", "json_object", "localhost"),
])
def test_model_policy_can_be_confirmed_and_filed_without_trial(tmp_path, monkeypatch, source, mode, hostname):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, AIRLINE_REBATE_PILOT_ROOT=tmp_path,
        AIRLINE_REBATE_MODEL_ENABLED=True, AIRLINE_REBATE_MODEL_URL="http://localhost/chat",
        AIRLINE_REBATE_MODEL_NAME="test-qwen", AIRLINE_REBATE_MODEL_KEY="test-only",
    )
    if source == "adm":
        app.config.update(
            AIRLINE_REBATE_MODEL_SOURCE="adm", AIRLINE_REBATE_MODEL_URL="",
            AIRLINE_REBATE_MODEL_NAME="", AIRLINE_REBATE_MODEL_KEY="",
            ADM_PARSING_AI_URL=f"https://{hostname}/chat", ADM_PARSING_AI_KEY="test-adm-only",
            ADM_PARSING_AI_MODEL="qwen3.8-flash", ADM_PARSING_AI_OUTPUT_FORMAT="auto",
        )
    api = Blueprint("rebate", __name__)
    register_routes(api)
    app.register_blueprint(api)

    @app.before_request
    def authorized_user():
        g.current_user = {"is_admin": True, "username": "reviewer"}

    contract = {
        "number": "EXAMPLE-01", "name": "Example", "airline": "XX",
        "start": "2026-01-01", "end": "2026-03-31", "currency": "USD", "scope": "Example routes",
    }
    draft = {
        "schemaVersion": extraction.VERSION, "contract": contract,
        "schemes": [{"id": "S1", "name": "Base", "tablePages": ["1"]},
                    {"id": "S2", "name": "Brand bonus", "tablePages": ["1", "2"]}],
        "rules": [{
            "schemeId": "S1", "kind": "tier", "label": "First tier", "concept": "Sales", "operator": "gte",
            "value": "100", "reviewReason": None,
            "tier": {"lower": "100", "upper": None, "currency": "USD", "ratePercent": "4.5",
                     "basis": "Sales", "lowerInclusive": "yes", "upperInclusive": "unknown"},
            "evidence": [{"page": "1", "quote": None, "region": "table row", "role": "data"}],
        }],
    }
    primary = draft["rules"][0]
    draft["rules"].append({
        **primary, "schemeId": "S2", "label": "Continued brand tier",
        "evidence": [
            {"page": "1", "quote": None, "region": "brand header", "role": "header"},
            {"page": "1", "quote": None, "region": "brand first row", "role": "data"},
            {"page": "2", "quote": None, "region": "brand continued row", "role": "data"},
        ],
    })
    draft["rules"].append({
        **primary, "schemeId": None, "kind": "settlement", "label": "出票日期", "concept": "出票日期", "value": "2026 Q1",
    })
    calls = []

    def reply(request, timeout):
        expected_key = "test-adm-only" if source == "adm" else "test-only"
        assert request.headers["Authorization"] == f"Bearer {expected_key}"
        calls.append(json.loads(request.data))
        response = BytesIO(json.dumps({
            "id": "test-receipt", "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(draft)}}],
        }).encode())
        response.headers = {}
        return response

    monkeypatch.setattr(jobs, "fetch_policy_reference", lambda config: {
        "rows": [{"issue_ticket_time": "2026-02-01"}],
        "columns": [{"name": "issue_ticket_time", "typeMatches": True}],
    })
    monkeypatch.setattr(import_module("data_report_api.api.airline_rebates"), "kick", jobs.drain)
    document = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.add_blank_page(300, 400)
    writer.write(document)
    document.seek(0)

    client = app.test_client()
    with patch.object(extraction, "build_opener") as build_opener:
        build_opener.return_value.open.side_effect = reply
        upload = client.post(ROOT + "/policies", data={"file": (document, "example.pdf")})
    assert upload.status_code == 200
    assert len(calls) == 1
    assert calls[0]["response_format"]["type"] == mode
    if mode == "json_schema":
        assert calls[0]["response_format"]["json_schema"]["strict"] is True
    else:
        assert "schemaVersion" in calls[0]["messages"][0]["content"]
    if hostname == "dashscope.aliyuncs.com":
        assert calls[0]["enable_thinking"] is False
    assert any(part["type"] == "image_url" for part in calls[0]["messages"][1]["content"])
    policy_id = upload.json["data"]["id"]
    policy = client.get(ROOT + "/policies").json["data"][0]
    assert policy["status"] == "ready"
    assert policy["modelReceipt"]["providerRequestId"] == "test-receipt"
    assert policy["trialReady"] is False
    payload = {"policyId": policy_id, "name": "Example task", "owner": "reviewer"}
    assert client.post(ROOT + "/tasks", json=payload).status_code == 409
    policy_url = f"{ROOT}/policies/{policy_id}"
    assert client.post(policy_url + "/confirm").status_code == 409
    cards = client.get(policy_url + "/mapping").json["data"]["rules"]
    first = {"group": cards[0]["id"], "rule": cards[0]["conditions"][0]["id"]}
    assert client.put(policy_url + "/clauses", json={**first, "state": "pending"}).status_code == 422
    assert client.put(policy_url + "/clauses", json={
        **first, "state": "pending", "note": "Check rate against PDF",
    }).status_code == 200
    assert client.post(policy_url + "/confirm").status_code == 409
    for card in cards:
        for condition in card["conditions"]:
            review = {"group": card["id"], "rule": condition["id"], "state": "confirmed"}
            if card is cards[0]:
                review["correction"] = "Verified base rate"
            assert client.put(policy_url + "/clauses", json=review).status_code == 200
    mapping = {"group": cards[-1]["id"], "rule": cards[-1]["conditions"][0]["id"]}
    assert client.post(policy_url + "/confirm").status_code == 409
    assert client.put(policy_url + "/mapping", json={**mapping, "state": "missing"}).status_code == 200
    assert client.post(policy_url + "/confirm").status_code == 409
    field_review = {**mapping, "state": "confirmed", "field": "issue_ticket_time"}
    assert client.put(policy_url + "/mapping", json=field_review).status_code == 200
    assert client.post(policy_url + "/confirm").json["data"]["confirmed"] is True
    assert client.put(policy_url + "/mapping", json=field_review).status_code == 409
    assert client.put(policy_url + "/clauses", json={**first, "state": "confirmed"}).status_code == 409

    created = client.post(ROOT + "/tasks", json=payload)
    assert created.status_code == 200
    task = created.json["data"]
    task_url = f"{ROOT}/tasks/{task['id']}"
    assert task["policyId"] == policy_id
    assert task["currency"] == "USD"
    assert task["trialAvailable"] is False
    assert client.post(ROOT + "/tasks", json=payload).json["data"]["id"] == task["id"]
    assert client.get(ROOT + "/tasks").json["data"] == [task]
    with connect(tmp_path) as db:
        assert db.execute("SELECT COUNT(*) FROM rebate_tasks").fetchone()[0] == 1
    version = client.get(task_url + "/versions").json["data"][0]
    assert version["rules"][0]["conditions"][0]["value"] == "Verified base rate"
    assert version["rules"][-1]["conditions"][0]["dataMapping"]["decision"]["field"] == "issue_ticket_time"
    assert version["contract"] == contract
    assert version["schemes"] == draft["schemes"]
    assert [card["name"] for card in version["rules"]] == [
        "Base · 奖励档位", "Brand bonus · 奖励档位", "合同通用 · 结算条件",
    ]
    assert client.get(f"{ROOT}/policies/{policy_id}/original").status_code == 200
    assert client.post(task_url + "/runs").status_code == 422
    refresh = app.test_cli_runner().invoke(api.cli, ["airline-rebate-refresh", "--interval-minutes", "1"])
    assert refresh.exit_code == 0
    assert "skipped=1 failed=0" in refresh.output


def test_hkg_rate_table_restores_all_columns_and_normalizes_hkd(monkeypatch):
    quote = "T > 6000 U/F 7 4 5.5 6 1 Q/I 5 2 3 4.5"
    bands = [(60_000_000, None), (30_000_000, 60_000_000),
             (16_000_000, 30_000_000), (6_000_000, 16_000_000)]
    policy = {
        "cabinGroups": [["U", "F"], ["Q", "I"]],
        "tiers": [{"lowerExclusive": low, "upperInclusive": high,
                   "ratesPercent": {"groupA": ["7", "4", "5.5", "6", "1"],
                                    "groupB": ["5", "2", "3", "4.5", "1"]}}
                  for low, high in bands],
        "sourceClauses": {f"tier-{low}": quote for low, _ in bands},
    }
    monkeypatch.setattr(extraction, "parse_policy", lambda source: policy)
    original = {"contract": {"number": "HKG26003"}, "rules": [{"kind": "tier"}, {"kind": "scope"}]}
    result = extraction.verify_hkg_rate_table(original, b"", ["HKG26003", quote, "settlement"])
    rules = result["rules"][1:]
    assert result["rateTableVerification"]["verifiedCells"] == 36
    assert original["rules"] == [{"kind": "tier"}, {"kind": "scope"}]
    assert result["rules"][0] == {"kind": "scope"}
    assert len({rule["id"] for rule in rules}) == 36
    assert all(rule["evidence"][0]["verified"] for rule in rules)
    assert [rule["tier"]["ratePercent"] for rule in rules[:9]] == ["7", "5", "4", "2", "5.5", "3", "6", "4.5", "1"]
    assert rules[0]["tier"]["lower"] == "60000000"
    assert rules[9]["tier"]["upper"] == "60000000"
    assert rules[-1]["tier"]["lower"] == "6000000"
    assert sum(rule["value"] == "异地始发" for rule in rules) == 4


def test_hkg_rate_table_does_not_silently_accept_unrecognized_layout(monkeypatch):
    def invalid_policy(source):
        raise ValueError("fixture")
    monkeypatch.setattr(extraction, "parse_policy", invalid_policy)
    with pytest.raises(extraction.ExtractionError, match="无法完整核对"):
        extraction.verify_hkg_rate_table({"contract": {"number": "HKG26003"}}, b"", ["HKG26003"])


@pytest.mark.parametrize("bad_case, message", [
    ("missing_page", "缺少表格页证据"),
    ("header_only", "缺少表格页证据"),
    ("unknown_scheme", "未归属有效奖励方案"),
    ("no_scheme_reward", "缺少带页码证据的奖励规则"),
])
def test_scheme_coverage_rejects_incomplete_tables(bad_case, message):
    draft = {
        "schemaVersion": extraction.VERSION,
        "schemes": [{"id": "S1", "name": "Base", "tablePages": ["1", "2"]}],
        "rules": [{"kind": "tier", "schemeId": "S1", "evidence": [
            {"page": "1", "role": "data", "quote": None, "region": "base row"},
            {"page": "2", "role": "data", "quote": None, "region": "continued row"},
        ]}],
    }
    extraction.validate_scheme_coverage(draft, 2)
    rule = draft["rules"][0]
    if bad_case == "missing_page":
        rule["evidence"].pop()
    elif bad_case == "header_only":
        rule["evidence"][1]["role"] = "header"
    elif bad_case == "unknown_scheme":
        rule["schemeId"] = "S2"
    else:
        rule["kind"] = "scope"
    with pytest.raises(extraction.ExtractionError, match=message):
        extraction.validate_scheme_coverage(draft, 2)


@pytest.mark.parametrize("reason, message", [
    ("length", "达到输出长度上限"),
    ("content_filter", "因内容过滤提前停止"),
    ("tool_calls", "意外的工具调用"),
])
def test_incomplete_model_response_preserves_diagnostics(reason, message):
    response = BytesIO(json.dumps({
        "id": "response-id", "model": "test-qwen",
        "choices": [{"finish_reason": reason, "message": {"content": None}}],
        "usage": {"prompt_tokens": 123, "completion_tokens": 456},
    }).encode())
    response.headers = {}
    config = {"TESTING": True, "AIRLINE_REBATE_MODEL_ENABLED": True,
              "AIRLINE_REBATE_MODEL_URL": "http://localhost/chat",
              "AIRLINE_REBATE_MODEL_NAME": "test-qwen", "AIRLINE_REBATE_MODEL_KEY": "test-only"}
    with patch.object(extraction, "build_opener") as opener:
        opener.return_value.open.return_value = response
        with pytest.raises(extraction.ExtractionError, match=message) as raised:
            extraction.call_model(config, [{"page": 1, "text": "Synthetic", "image": None}])
    assert raised.value.receipt["finishReason"] == reason
    assert raised.value.receipt["providerRequestId"] == "response-id"
    assert raised.value.receipt["outputTokens"] == 456
