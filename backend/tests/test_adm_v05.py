from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import io
import sqlite3
import time

import pytest

from data_report_api import build_adm_workflow_user_options
from data_report_api.services.adm.attachments import AdmAttachmentService
from data_report_api.services.adm.exchange import AdmExchangeService, DAILY19, export_workbook, template
from data_report_api.services.adm.operator_exchange import AdmOperatorExchange, LEGACY_OPERATOR34, OPERATOR34
from data_report_api.services.adm.policy import AdmError
from data_report_api.services.adm.service import AdmService
from data_report_api.services.adm.v05 import ORDER_STATUSES
from data_report_api.services.comprehensive_export import ComprehensiveExportService


def user(user_id, *permissions):
    return {
        "id": str(user_id),
        "username": f"user-{user_id}",
        "display_name": f"人员{user_id}",
        "permissions": list(permissions),
        "menu_codes": ["adm.center"],
        "is_enabled": True,
    }


def test_unbound_adm_account_is_assignable_by_system_user_id(tmp_path):
    users = [
        {
            "id": 42,
            "username": "unbound-operator",
            "display_name": "未绑定操作员",
            "permissions": ["adm.view", "adm.handle"],
            "menu_codes": ["adm.center"],
            "is_enabled": True,
        }
    ]
    options = build_adm_workflow_user_options(
        users,
        employees=[{"id": 901, "name": "其他花名册人员", "departmentCode": "D01", "departmentName": "票务部"}],
        binding_resolver=lambda _user_id: None,
        departments=[{"code": "D01", "name": "票务部"}],
    )

    assert options["handle"] == [{
        "id": "42",
        "name": "未绑定操作员",
        "accountName": "未绑定操作员",
        "rosterEmployeeId": "",
        "departmentCode": "",
        "departmentName": "",
    }]
    assert options["coordinate"] == []
    service = AdmService({
        "TESTING": True,
        "ADM_STORAGE_MODE": "sqlite",
        "ADM_SQLITE_PATH": str(tmp_path / "unbound-account.sqlite"),
        "ADM_WORKFLOW_USER_OPTIONS": lambda: options,
        "ADM_USER_RESOLVER": lambda user_id: users[0] if str(user_id) == "42" else None,
    })
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign")
    case = create_case(service, manager)
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    assigned = service.line_action(
        manager,
        case["id"],
        case["lines"][0]["id"],
        {"version": case["version"], "action": "assign_operator", "ownerId": "42"},
    )
    assert assigned["ownerId"] == "42"
    assert assigned["ownerName"] == "未绑定操作员"


@pytest.fixture()
def service(tmp_path):
    return AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "adm.sqlite"),
            "ADM_ATTACHMENT_ROOT": str(tmp_path / "attachments"),
            "ADM_ATTACHMENT_VERIFIER": lambda item: True,
        }
    )


def create_case(service, actor, *, master="100.00", line="100.00"):
    return service.create_case(
        actor,
        {
            "admNo": "ADM-SYNTHETIC-001",
            "supplierName": "合成供应商",
            "currency": "CNY",
            "originalAmount": master,
            "issuedDate": "2026-11-05",
            "deadline": "2026-11-30T18:00:00+08:00",
            "lines": [
                {
                    "departmentCode": "D01",
                    "diffType": "价格差异",
                    "diffSecondType": "合成原因",
                    "amount": line,
                    "orderNo": "SYNTHETIC-ORDER-1",
                }
            ],
        },
    )


def test_internal_adm_number_is_traceable_unique_and_fits_fi_column(tmp_path):
    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "internal-no.sqlite"),
        }
    )
    actor = user("1", "adm.view", "adm.create")
    first = service.create_case(actor, {"admNo": "qw123", "supplierName": "供应商", "currency": "CNY", "lines": [{} for _ in range(10)]})
    second = service.create_case(actor, {"admNo": "qw123", "supplierName": "供应商", "currency": "CNY", "lines": [{}]})
    assert first["internalNo"] == "qw123-01"
    assert second["internalNo"] == "qw123-02"
    assert len(first["internalNo"]) <= 50
    assert first["lines"][0]["lineInternalNo"] == "qw123-01-001"
    assert first["lines"][-1]["lineInternalNo"] == "qw123-01-010"
    assert second["lines"][0]["lineInternalNo"] == "qw123-02-001"


def test_adding_lines_continues_readable_line_sequence(tmp_path):
    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "line-number.sqlite"),
        }
    )
    actor = user("1", "adm.view", "adm.create", "adm.edit")
    case = service.create_case(
        actor,
        {"admNo": "qw123", "supplierName": "供应商", "currency": "CNY", "lines": [{}, {}]},
    )
    case = service.add_line(actor, case["id"], {"version": case["version"]})
    assert [line["lineInternalNo"] for line in case["lines"]] == [
        "qw123-01-001", "qw123-01-002", "qw123-01-003",
    ]


def test_duplicate_adm_numbers_are_serialized_under_concurrent_creation(tmp_path):
    path = str(tmp_path / "concurrent-number.sqlite")
    config = {"TESTING": True, "ADM_STORAGE_MODE": "sqlite", "ADM_SQLITE_PATH": path}
    AdmService(config).store.check()
    actor = user("1", "adm.view", "adm.create")

    def create_one(_index):
        return AdmService(config).create_case(
            actor,
            {"admNo": "qw-concurrent", "supplierName": "供应商", "currency": "CNY"},
        )["internalNo"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        numbers = sorted(pool.map(create_one, range(6)))
    assert numbers == [f"qw-concurrent-{index:02d}" for index in range(1, 7)]


def test_adm_uses_normalized_tables_and_not_legacy_document_table(tmp_path):
    path = str(tmp_path / "normalized.sqlite")
    service = AdmService({"TESTING": True, "ADM_STORAGE_MODE": "sqlite", "ADM_SQLITE_PATH": path})
    actor = user("1", "adm.view", "adm.create")
    case = service.create_case(
        actor,
        {"admNo": "qw-normalized", "supplierName": "供应商", "currency": "CNY", "lines": [{"orderNo": "OTA-1"}]},
    )
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "adm_case_document" not in tables
        assert {
            "adm_case", "adm_case_line", "adm_case_event", "adm_case_attachment", "adm_case_assignment",
            "adm_case_appeal", "adm_case_recovery", "adm_case_collection", "adm_case_review",
            "adm_case_fx_snapshot",
        }.issubset(tables)
        assert connection.execute("SELECT internal_no FROM adm_case").fetchone()[0] == "qw-normalized-01"
        assert connection.execute("SELECT line_internal_no FROM adm_case_line").fetchone()[0] == "qw-normalized-01-001"
    assert service.case_detail(actor, case["id"])["lines"][0]["orderNo"] == "OTA-1"


def test_normalized_page_query_searches_readable_numbers_and_lines(tmp_path):
    path = str(tmp_path / "normalized-page.sqlite")
    service = AdmService({"TESTING": True, "ADM_STORAGE_MODE": "sqlite", "ADM_SQLITE_PATH": path})
    actor = user("1", "adm.view", "adm.create")
    created = service.create_case(
        actor,
        {"admNo": "qw-search", "supplierName": "供应商", "currency": "CNY", "lines": [{"orderNo": "OTA-SEARCH-1"}]},
    )
    cases, summary = service.store.page_all({"search": created["lines"][0]["lineInternalNo"]}, 1, 20, "2026-11-06T12:00:00+08:00")
    assert [case["id"] for case in cases] == [created["id"]]
    assert summary == {"cases": 1, "lines": 1, "open": 1, "overdue": 0}


def test_difference_entry_match_prefers_ota_then_falls_back_to_internal_number(tmp_path):
    matched = set()
    requested = []

    def lookup(values):
        requested.append(set(values))
        return matched.intersection(values)

    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "difference-match.sqlite"),
            "ADM_DIFFERENCE_MATCH_LOOKUP": lookup,
        }
    )
    actor = user("1", "adm.view", "adm.create")
    case = create_case(service, actor)
    internal_no = case["internalNo"]
    matched.update({"SYNTHETIC-ORDER-1", internal_no})
    detail = service.case_detail(actor, case["id"])
    assert detail["lines"][0]["difference"]["verification"] == "RECORDED"
    assert detail["lines"][0]["difference"]["matchedBy"] == "OTA_ORDER_NO"
    matched.remove("SYNTHETIC-ORDER-1")
    detail = service.case_detail(actor, case["id"])
    assert detail["lines"][0]["difference"]["matchedBy"] == "INTERNAL_ADM_NO"
    assert detail["lines"][0]["difference"]["matchedValue"] == internal_no
    assert {"SYNTHETIC-ORDER-1", internal_no}.issubset(requested[-1])


def test_difference_type_must_be_an_enabled_hotel_option(tmp_path):
    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "difference-type.sqlite"),
            "ADM_REFERENCE_OPTIONS": lambda: {
                "platforms": [], "suppliers": [],
                "differenceTypes": [{"code": "ADM-金额差异", "name": "ADM-金额差异", "label": "ADM-金额差异"}],
            },
        }
    )
    actor = user("1", "adm.view", "adm.create")
    with pytest.raises(AdmError, match="差异类型不存在"):
        service.create_case(
            actor,
            {
                "admNo": "ADM-TYPE-1", "supplierName": "供应商", "currency": "CNY",
                "lines": [{"diffType": "人工随意填写"}],
            },
        )
    case = service.create_case(
        actor,
        {
            "admNo": "ADM-TYPE-2", "supplierName": "供应商", "currency": "CNY",
            "lines": [{"diffType": "ADM-金额差异"}],
        },
    )
    assert case["lines"][0]["diffType"] == "ADM-金额差异"


def test_v05_has_exactly_nine_order_states():
    assert len(ORDER_STATUSES) == 9
    assert ORDER_STATUSES[-2:] == ("PENDING_COLLECTION", "COMPLETED")


def test_exchange_rate_snapshot_calculates_cny_without_rounding_loss(tmp_path):
    config = {
        "TESTING": True,
        "ADM_STORAGE_MODE": "sqlite",
        "ADM_SQLITE_PATH": str(tmp_path / "fx.sqlite"),
        "ADM_EXCHANGE_RATE_LOOKUP": lambda currency: {
            "rate": "6.67536500",
            "effectiveAt": "2026-11-05T21:02:01",
            "rowId": "15141911",
            "source": 6,
            "actualSource": 6,
            "baseCurrency": "CNY",
            "exchangeCurrency": currency,
            "rateColumn": "central_parity_rate",
        },
    }
    service = AdmService(config)
    case = service.create_case(
        user("1", "adm.view", "adm.create"),
        {
            "admNo": "ADM-FX-1", "supplierName": "合成供应商", "currency": "USD",
            "originalAmount": "12.34", "lines": [{"amount": "2.50"}],
        },
    )
    assert case["originalAmountCny"] == "82.37400410"
    assert case["fxRate"] == "6.67536500"
    assert case["fxDate"] == "2026-11-05T21:02:01"
    assert case["fxSource"]["rowId"] == "15141911"
    assert case["lines"][0]["amountCny"] == "16.68841250"


def test_imported_exchange_rate_snapshot_does_not_follow_later_rate_changes(tmp_path):
    current = {"rate": "7.00000000", "rowId": "morning", "effectiveAt": "2026-11-06T09:00:00"}
    calls = []

    def lookup(currency):
        calls.append(currency)
        return {
            **current,
            "source": 6,
            "actualSource": 6,
            "baseCurrency": "CNY",
            "exchangeCurrency": currency,
            "rateColumn": "central_parity_rate",
        }

    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "fx-snapshot.sqlite"),
            "ADM_EXCHANGE_RATE_LOOKUP": lookup,
        }
    )
    actor = user("1", "adm.view", "adm.create", "adm.edit")
    case = service.create_case(
        actor,
        {"admNo": "ADM-FX-SNAPSHOT", "supplierName": "合成供应商", "currency": "USD", "originalAmount": "10.00"},
    )
    current.update(rate="8.00000000", rowId="afternoon", effectiveAt="2026-11-06T15:00:00")
    case = service.update_case(actor, case["id"], {"version": case["version"], "originalAmount": "20.00"})
    assert case["fxRate"] == "7.00000000"
    assert case["fxSource"]["rowId"] == "morning"
    assert case["originalAmountCny"] == "140.00000000"
    assert calls == ["USD"]


def test_explicit_cny_amount_is_not_overwritten_by_exchange_rate(tmp_path):
    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "manual-cny.sqlite"),
            "ADM_EXCHANGE_RATE_LOOKUP": lambda currency: pytest.fail("explicit CNY amount must win"),
        }
    )
    case = service.create_case(
        user("1", "adm.view", "adm.create"),
        {
            "admNo": "ADM-FX-2", "supplierName": "合成供应商", "currency": "USD",
            "originalAmount": "12.34", "originalAmountCny": "82.37",
        },
    )
    assert case["originalAmountCny"] == "82.37"
    assert case["fxRate"] is None


def test_excel_export_uses_code_slash_name_for_erp_references():
    content, _ = export_workbook(
        [
            {
                "id": "case-1",
                "admNo": "ADM-1",
                "internalNo": "ADM-1-01",
                "supplierCode": "SUP01",
                "supplierName": "合成供应商",
                "lines": [
                    {
                        "id": "line-1",
                        "lineInternalNo": "ADM-1-01-001",
                        "platformCode": "OTA01",
                        "platform": "合成平台",
                    }
                ],
            }
        ],
        "adm_lines",
    )
    from openpyxl import load_workbook

    sheet = load_workbook(content, read_only=True)["订单明细"]
    rows = sheet.iter_rows()
    headers = [cell.value for cell in next(rows)]
    values = [cell.value for cell in next(rows)]
    row = dict(zip(headers, values))
    assert row["下发方"] == "SUP01/合成供应商"
    assert row["主单内部单号"] == "ADM-1-01"
    assert row["明细内部单号"] == "ADM-1-01-001"
    assert row["平台"] == "OTA01/合成平台"
    assert row["平台编码"] == "OTA01"


def test_daily19_template_has_exact_single_sheet_contract():
    content, filename = template("daily19")
    from openpyxl import load_workbook

    book = load_workbook(content, read_only=True)
    assert filename == "ADM_19列日常建单模板.xlsx"
    assert book.sheetnames == ["ADM导入"]
    assert [cell.value for cell in next(book["ADM导入"].iter_rows())] == [label for _, label in DAILY19]


def test_daily19_import_assigns_one_case_owner(tmp_path):
    people = {
        "coordinate": [],
        "handle": [{"id": "2", "name": "操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "departments": [{"code": "D01", "name": "票务部", "label": "D01/票务部"}],
    }
    service = AdmService(
        {
            "TESTING": True,
            "ADM_STORAGE_MODE": "sqlite",
            "ADM_SQLITE_PATH": str(tmp_path / "daily19.sqlite"),
            "ADM_WORKFLOW_USER_OPTIONS": lambda: people,
            "ADM_REFERENCE_OPTIONS": lambda: {"platforms": [], "suppliers": []},
        }
    )
    actor = user("1", "adm.view", "adm.create", "adm.import", "adm.assign")
    case = service.import_case(
        actor,
        {
            "admNo": "ADM-DAILY19",
            "supplierName": "航空公司",
            "supplierType": "AIRLINE",
            "currency": "CNY",
            "originalAmount": "100.00",
            "source": {"system": "daily19", "recordId": "ADM-DAILY19"},
            "lines": [
                {
                    "amount": "100.00",
                    "departmentCode": "D01",
                    "diffType": "价格差异",
                    "diffSecondType": "合成原因",
                    "initialOwnerId": "2",
                }
            ],
        },
    )
    assert case["status"] == "IN_PROGRESS"
    assert case["ownerId"] == "2"
    assert case["lines"][0]["status"] == "PENDING_CODE_PROCESSING"
    assert case["lines"][0]["ownerId"] == "2"


def test_operator34_export_preview_and_commit(tmp_path):
    people = {
        "coordinate": [{"id": "2", "name": "组长兼操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "handle": [{"id": "2", "name": "组长兼操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "departments": [{"code": "D01", "name": "票务部", "label": "D01/票务部"}],
    }
    config = {
        "TESTING": True,
        "ADM_STORAGE_MODE": "sqlite",
        "ADM_SQLITE_PATH": str(tmp_path / "operator34.sqlite"),
        "ADM_IMPORT_ROOT": str(tmp_path / "imports"),
        "ADM_WORKFLOW_USER_OPTIONS": lambda: people,
        "ADM_REFERENCE_OPTIONS": lambda: {
            "platforms": [{"code": "OTA01", "name": "合成平台", "label": "OTA01/合成平台"}],
            "suppliers": [{"code": "SUP01", "name": "合成供应商", "label": "SUP01/合成供应商"}],
        },
        "ADM_DIFFERENCE_MATCH_LOOKUP": lambda values: {"SYNTHETIC-ORDER-1"}.intersection(values),
    }
    service = AdmService(config)
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    operator = user("2", "adm.view", "adm.assign", "adm.handle")
    case = create_case(service, manager)
    line_id = case["lines"][0]["id"]
    case = service.update_line(
        manager,
        case["id"],
        line_id,
        {
            "version": case["version"],
            "platformCode": "OTA01",
            "supplierCode": "SUP01",
            "attachmentUrl": "https://prod-tour-oss.ndccloud.com/example/synthetic-attachment.pdf",
        },
    )
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "assign_operator", "ownerId": "2"})

    exchange = AdmOperatorExchange(config)
    content, _ = exchange.export(operator, ["PENDING_CODE_PROCESSING"])
    from openpyxl import load_workbook
    from werkzeug.datastructures import FileStorage

    book = load_workbook(content)
    sheet = book["待处理订单"]
    assert [cell.value for cell in sheet[1]] == OPERATOR34
    assert sheet.cell(2, 1).value == case["internalNo"]
    assert sheet.cell(2, 3).value == case["lines"][0]["lineInternalNo"]
    assert sheet.cell(2, 4).value == "OTA01/合成平台"
    assert sheet.cell(2, 6).value == "SUP01/合成供应商"
    assert sheet.cell(2, 10).value == "https://prod-tour-oss.ndccloud.com/example/synthetic-attachment.pdf"
    assert sheet.cell(2, 10).hyperlink.target == sheet.cell(2, 10).value
    assert sheet.cell(2, 34).value == "已录入（OTA订单号）"
    legacy_book = load_workbook(io.BytesIO(content.getvalue()))
    legacy_sheet = legacy_book["待处理订单"]
    legacy_sheet.delete_cols(10)
    assert [cell.value for cell in legacy_sheet[1]] == LEGACY_OPERATOR34
    legacy_upload = io.BytesIO()
    legacy_book.save(legacy_upload)
    legacy_book.close()
    legacy_upload.seek(0)
    legacy_preview = exchange.preview(operator, FileStorage(stream=legacy_upload, filename="legacy-operator34.xlsx"))
    assert legacy_preview["errorCount"] == 0
    assert legacy_preview["skippedCount"] == 1
    sheet.cell(2, 35).value = "已查看日志，确认为平台重复扣款"
    sheet.cell(2, 25).value = "无需恢复编码"
    sheet.cell(2, 29).value = "提交不申诉"
    sheet.cell(2, 32).value = "业务确认不申诉"
    sheet.cell(2, 33).value = "平台问题"
    upload = io.BytesIO()
    book.save(upload)
    upload.seek(0)
    preview = exchange.preview(operator, FileStorage(stream=upload, filename="operator.xlsx"))
    assert preview["errorCount"] == 0
    assert preview["readyCount"] == 1
    result = exchange.commit(operator, preview["previewId"])
    assert result["successCount"] == 1
    updated = service.case_detail(operator, case["id"])
    assert updated["lines"][0]["status"] == "PENDING_REVIEW"
    assert updated["lines"][0]["investigationNote"] == "已查看日志，确认为平台重复扣款"
    assert updated["lines"][0]["attribution"] == "PLATFORM"


def test_operator34_uses_global_background_export_queue(tmp_path):
    people = {
        "coordinate": [{"id": "2", "name": "操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "handle": [{"id": "2", "name": "操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "departments": [{"code": "D01", "name": "票务部", "label": "D01/票务部"}],
    }
    operator = user("2", "adm.view", "adm.assign", "adm.handle")
    config = {
        "TESTING": True, "MYSQL_DATABASE": "sibebid",
        "ADM_STORAGE_MODE": "sqlite", "ADM_SQLITE_PATH": str(tmp_path / "queued-adm.sqlite"),
        "ADM_IMPORT_ROOT": str(tmp_path / "imports"),
        "COMPREHENSIVE_EXPORT_ROOT": str(tmp_path / "exports"),
        "ADM_WORKFLOW_USER_OPTIONS": lambda: people,
        "ADM_USER_RESOLVER": lambda user_id: operator if int(user_id) == 2 else None,
    }
    service = AdmService(config)
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    case = create_case(service, manager)
    line_id = case["lines"][0]["id"]
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "assign_operator", "ownerId": "2"})

    exports = ComprehensiveExportService(config)
    task = exports.create_background(operator, {"kind": "adm_operator_tasks", "statuses": ["PENDING_CODE_PROCESSING"]})
    for _ in range(100):
        current = next(item for item in exports.list(operator) if item["id"] == task["id"])
        if current["status"] not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
            break
        time.sleep(0.02)
    assert current["status"] == "SUCCEEDED"
    path, name = exports.download(operator, task["id"])
    from openpyxl import load_workbook
    assert name.startswith("ADM_操作人员待处理_")
    assert load_workbook(path, read_only=True).sheetnames == ["待处理订单"]


def test_daily19_workbook_preview_and_commit(tmp_path):
    people = {
        "coordinate": [],
        "handle": [{"id": "2", "name": "操作员", "departmentCode": "D01", "departmentName": "票务部"}],
        "departments": [{"code": "D01", "name": "票务部", "label": "D01/票务部"}],
    }
    config = {
        "TESTING": True,
        "ADM_STORAGE_MODE": "sqlite",
        "ADM_SQLITE_PATH": str(tmp_path / "daily19-workbook.sqlite"),
        "ADM_IMPORT_ROOT": str(tmp_path / "imports"),
        "ADM_WORKFLOW_USER_OPTIONS": lambda: people,
        "ADM_REFERENCE_OPTIONS": lambda: {
            "platforms": [{"code": "OTA01", "name": "合成平台", "label": "OTA01/合成平台"}],
            "suppliers": [{"code": "SUP01", "name": "合成供应商", "label": "SUP01/合成供应商"}],
        },
    }
    actor = user("1", "adm.view", "adm.create", "adm.import", "adm.assign")
    content, _ = template("daily19")
    from openpyxl import load_workbook
    from werkzeug.datastructures import FileStorage

    book = load_workbook(content)
    sheet = book["ADM导入"]
    sheet.append([
        "ADM-XLSX-19", "供应商", "SUP01/合成供应商", "CNY", "100.00", "2026-11-05",
        "2026-11-30", "", "OTA01/合成平台", "ORDER-1", "SUP01/合成供应商", "CA",
        "999-1", "PNR001", "100.00", "D01/票务部", "2/操作员", "价格差异", "合成原因",
    ])
    upload = io.BytesIO(); book.save(upload); upload.seek(0)
    exchange = AdmExchangeService(config)
    preview = exchange.preview(actor, FileStorage(stream=upload, filename="daily19.xlsx"))
    assert preview["format"] == "daily19"
    assert preview["errorCount"] == 0
    result = exchange.commit(actor, preview["previewId"])
    assert result["successCount"] == 1
    case = AdmService(config).case_detail(actor, result["items"][0]["id"])
    assert case["status"] == "IN_PROGRESS"
    assert case["lines"][0]["platformCode"] == "OTA01"
    assert case["ownerId"] == "2"
    assert case["lines"][0]["status"] == "PENDING_CODE_PROCESSING"


def test_amount_mismatch_blocks_publish(service):
    owner = user("1", "adm.view", "adm.create", "adm.edit")
    case = create_case(service, owner, master="100.00", line="99.99")
    with pytest.raises(AdmError) as captured:
        service.case_action(owner, case["id"], {"version": case["version"], "action": "publish"})
    assert captured.value.code == "ADM_AMOUNT_MISMATCH"


def test_manual_recovery_review_and_partial_collection(service):
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review", "adm.close")
    leader_operator = user("2", "adm.view", "adm.assign", "adm.handle")
    case = create_case(service, manager)
    line_id = case["lines"][0]["id"]
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "assign_operator", "ownerId": "2"})
    case = service.line_action(leader_operator, case["id"], line_id, {"version": case["version"], "action": "recovery_decide", "required": True})
    line = case["lines"][0]
    assert line["status"] == "PENDING_CODE_PROCESSING"
    assert line["recovery"]["state"] == "WAITING_MANUAL"
    assert "system" not in line["recovery"]

    case = service.line_action(leader_operator, case["id"], line_id, {"version": case["version"], "action": "recovery_complete"})
    case = service.line_action(
        leader_operator,
        case["id"],
        line_id,
        {"version": case["version"], "action": "decide", "decision": "NO_APPEAL", "reason": "业务确认不申诉", "attribution": "PLATFORM"},
    )
    case = service.line_action(
        manager,
        case["id"],
        line_id,
        {"version": case["version"], "action": "approve", "requiresCollection": True, "collectionExpectedAmount": "100.00", "reason": ""},
    )
    assert case["lines"][0]["status"] == "PENDING_COLLECTION"
    case = service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "record_collection", "amount": "40.00", "receivedDate": "2026-11-05"})
    assert case["lines"][0]["collectionStatus"] == "PARTIAL"
    case = service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "record_collection", "amount": "60.00", "receivedDate": "2026-11-06"})
    assert case["lines"][0]["status"] == "COMPLETED"
    assert case["status"] == "READY_TO_CLOSE"
    assert service.closure_check(manager, case["id"])["canClose"] is True


def test_only_adm_coordinator_can_review_even_with_all_scope(service):
    coordinator = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    operator = user("2", "adm.view", "adm.assign", "adm.handle")
    outsider = user("3", "adm.view", "adm.review", "adm.scope.all")
    case = create_case(service, coordinator)
    line_id = case["lines"][0]["id"]
    case = service.case_action(coordinator, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(coordinator, case["id"], line_id, {"version": case["version"], "action": "assign_operator", "ownerId": "2"})
    case = service.line_action(operator, case["id"], line_id, {"version": case["version"], "action": "recovery_decide", "required": False})
    case = service.line_action(operator, case["id"], line_id, {"version": case["version"], "action": "decide", "decision": "NO_APPEAL", "reason": "无需申诉", "attribution": "PLATFORM"})
    with pytest.raises(AdmError) as captured:
        service.line_action(outsider, case["id"], line_id, {"version": case["version"], "action": "approve", "requiresCollection": False})
    assert captured.value.code == "ADM_FORBIDDEN"
    reviewed = service.line_action(coordinator, case["id"], line_id, {"version": case["version"], "action": "approve", "requiresCollection": False})
    assert reviewed["lines"][0]["status"] == "COMPLETED"
    assert reviewed["status"] == "READY_TO_CLOSE"


def test_unassigned_operator_can_view_all_but_cannot_handle_other_owners_case(service):
    coordinator = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    assigned = user("2", "adm.view", "adm.handle")
    outsider = user("3", "adm.view", "adm.handle")
    case = create_case(service, coordinator)
    line_id = case["lines"][0]["id"]
    case = service.case_action(coordinator, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(
        coordinator,
        case["id"],
        line_id,
        {"version": case["version"], "action": "assign_operator", "ownerId": assigned["id"]},
    )

    ledger = service.list_cases(outsider, {"scope": "all", "page": 1, "pageSize": 20})
    assert ledger["pagination"]["total"] == 1
    detail = service.case_detail(outsider, case["id"])
    assert detail["partial"] is False
    assert len(detail["lines"]) == 1
    assert detail["allowedActions"] == []
    assert detail["lines"][0]["allowedActions"] == []

    with pytest.raises(AdmError) as captured:
        service.line_action(
            outsider,
            case["id"],
            line_id,
            {"version": case["version"], "action": "recovery_decide", "required": False},
        )
    assert captured.value.status == 403


def test_ledger_viewer_can_preview_but_cannot_download_attachment(service):
    coordinator = user("1", "adm.view", "adm.create", "adm.edit")
    viewer = user("3", "adm.view")
    case = create_case(service, coordinator)
    case = service.add_attachment(
        coordinator,
        case["id"],
        {
            "version": case["version"],
            "attachment": {
                "id": "preview-only-file",
                "name": "supplier.pdf",
                "category": "ORIGINAL",
                "storageKey": "b" * 32 + ".pdf",
                "sha256": "synthetic",
                "size": 9,
            },
        },
    )

    detail = service.case_detail(viewer, case["id"])
    assert detail["attachments"][0]["canDownload"] is False
    assert service.attachment_preview(viewer, case["id"], "preview-only-file")["name"] == "supplier.pdf"
    with pytest.raises(AdmError) as captured:
        service.attachment(viewer, case["id"], "preview-only-file")
    assert captured.value.code == "ADM_FORBIDDEN"


def test_admin_can_review_any_case_as_audited_override(service):
    coordinator = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    operator = user("2", "adm.view", "adm.handle")
    admin = user("99")
    admin["is_admin"] = True
    case = create_case(service, coordinator)
    line_id = case["lines"][0]["id"]
    case = service.case_action(coordinator, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(
        coordinator,
        case["id"],
        line_id,
        {"version": case["version"], "action": "assign_operator", "ownerId": operator["id"]},
    )
    case = service.line_action(operator, case["id"], line_id, {"version": case["version"], "action": "recovery_decide", "required": False})
    case = service.line_action(
        operator,
        case["id"],
        line_id,
        {"version": case["version"], "action": "decide", "decision": "NO_APPEAL", "reason": "无需申诉", "attribution": "PLATFORM"},
    )
    reviewed = service.line_action(
        admin,
        case["id"],
        line_id,
        {"version": case["version"], "action": "approve", "requiresCollection": False},
    )
    assert reviewed["lines"][0]["status"] == "COMPLETED"
    assert reviewed["timeline"][-1]["actorId"] == "99"


def test_case_has_one_owner_and_transfer_moves_every_line(service):
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review")
    first_owner = user("2", "adm.view", "adm.handle")
    next_owner = user("3", "adm.view", "adm.handle")
    case = service.create_case(
        manager,
        {
            "admNo": "ADM-ONE-OWNER",
            "supplierName": "合成供应商",
            "currency": "CNY",
            "originalAmount": "100.00",
            "lines": [
                {"departmentCode": "D01", "diffType": "价格差异", "diffSecondType": "原因1", "amount": "40.00"},
                {"departmentCode": "D02", "diffType": "价格差异", "diffSecondType": "原因2", "amount": "60.00"},
            ],
        },
    )
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(
        manager,
        case["id"],
        case["lines"][0]["id"],
        {"version": case["version"], "action": "assign_operator", "ownerId": "2"},
    )
    assert case["ownerId"] == "2"
    assert {line["ownerId"] for line in case["lines"]} == {"2"}

    case = service.line_action(
        first_owner,
        case["id"],
        case["lines"][1]["id"],
        {"version": case["version"], "action": "transfer_request", "ownerId": "3", "reason": "补充资料", "summary": "请补充两笔订单资料"},
    )
    assert case["ownerId"] == "2"
    assert case["handover"]["status"] == "PENDING"

    case = service.line_action(
        next_owner,
        case["id"],
        case["lines"][0]["id"],
        {"version": case["version"], "action": "transfer_accept", "reason": "已接收"},
    )
    assert case["ownerId"] == "3"
    assert {line["ownerId"] for line in case["lines"]} == {"3"}
    assert case["handoverHistory"][-1]["status"] == "ACCEPTED"
    assert case["assignmentSegments"][-1]["ownerId"] == "3"

    with pytest.raises(AdmError):
        service.line_action(
            next_owner,
            case["id"],
            case["lines"][0]["id"],
            {"version": case["version"], "action": "collaboration_create", "ownerId": "2"},
        )


def test_closed_attachment_is_purged_after_due_date(service, tmp_path):
    manager = user("1", "adm.view", "adm.create", "adm.edit", "adm.assign", "adm.review", "adm.close")
    operator = user("2", "adm.view", "adm.assign", "adm.handle")
    case = create_case(service, manager)
    line_id = case["lines"][0]["id"]
    root = Path(service.config["ADM_ATTACHMENT_ROOT"])
    root.mkdir(parents=True)
    key = "a" * 32 + ".txt"
    (root / key).write_text("synthetic", encoding="utf-8")
    case = service.add_attachment(
        manager,
        case["id"],
        {"version": case["version"], "attachment": {"id": "file-1", "name": "synthetic.txt", "category": "ORIGINAL", "storageKey": key, "sha256": "synthetic", "size": 9}},
    )
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "publish"})
    case = service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "assign_operator", "ownerId": "2"})
    case = service.line_action(operator, case["id"], line_id, {"version": case["version"], "action": "recovery_decide", "required": False})
    case = service.line_action(operator, case["id"], line_id, {"version": case["version"], "action": "decide", "decision": "NO_APPEAL", "reason": "不申诉", "attribution": "HUMAN"})
    case = service.line_action(manager, case["id"], line_id, {"version": case["version"], "action": "approve", "requiresCollection": False})
    case = service.case_action(manager, case["id"], {"version": case["version"], "action": "close"})
    raw = service._get(case["id"])
    raw["attachmentCleanupDueAt"] = "2000-01-01T00:00:00+08:00"
    service._save(manager, raw, "test_make_cleanup_due")

    result = AdmAttachmentService(service.config, service).cleanup_due()
    assert result == {"scanned": 1, "cleanedCases": 1, "cleanedFiles": 1, "failedCases": 0}
    assert not (root / key).exists()
    cleaned = service._get(case["id"])
    assert cleaned["attachments"][0]["deletedAt"]
    assert cleaned["attachmentCleanupState"] == "COMPLETED"
