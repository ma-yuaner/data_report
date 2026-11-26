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
        "rules": [{
            "kind": "tier", "label": "First tier", "concept": "Sales", "operator": "gte",
            "value": "100", "reviewReason": None,
            "tier": {"lower": "100", "upper": None, "currency": "USD", "ratePercent": "4.5",
                     "basis": "Sales", "lowerInclusive": "yes", "upperInclusive": "unknown"},
            "evidence": [{"page": "1", "quote": None, "region": "table"}],
        }],
    }
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

    monkeypatch.setattr(jobs, "fetch_policy_reference", lambda config: {"rows": [{}]})
    monkeypatch.setattr(import_module("data_report_api.api.airline_rebates"), "kick", jobs.drain)
    document = BytesIO()
    writer = PdfWriter()
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
    assert client.post(f"{ROOT}/policies/{policy_id}/confirm").json["data"]["confirmed"] is True

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
    assert version["contract"] == contract
    assert version["rules"]
    assert client.get(f"{ROOT}/policies/{policy_id}/original").status_code == 200
    assert client.post(task_url + "/runs").status_code == 422
    refresh = app.test_cli_runner().invoke(api.cli, ["airline-rebate-refresh", "--interval-minutes", "1"])
    assert refresh.exit_code == 0
    assert "skipped=1 failed=0" in refresh.output
