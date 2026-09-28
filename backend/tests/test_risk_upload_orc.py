from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from data_report_api.services.risk_upload_orc import (
    orc_schema,
    orc_value,
    parse_host_map,
    rewrite_host,
    upload_orc,
    validate_hdfs_root,
    validate_hdfs_uri,
    write_orc,
)


def test_orc_schema_keeps_hive_order_and_types():
    assert orc_schema(
        [("issue_ticket_no", "STRING"), ("estimated_profit_cny", "DECIMAL(28,4)")]
    ) == "struct<issue_ticket_no:string,estimated_profit_cny:decimal(28,4)>"


@pytest.mark.parametrize(
    ("value", "data_type", "expected"),
    [
        (" 001-2 ", "string", " 001-2 "),
        ("1,234", "bigint", 1234),
        ("-12.3400", "decimal(28,4)", Decimal("-12.3400")),
        ("true", "boolean", True),
        (dt.datetime(2026, 9, 28, 8, 30), "date", dt.date(2026, 9, 28)),
        ("2026-09-28 08:30:00", "timestamp", dt.datetime(2026, 9, 28, 8, 30)),
        ("", "string", None),
    ],
)
def test_orc_value_converts_hive_types(value, data_type, expected):
    assert orc_value(value, data_type) == expected


def test_hdfs_paths_reject_unsafe_values():
    assert validate_hdfs_root("/tmp/data-report/risk-uploads/") == "/tmp/data-report/risk-uploads"
    assert validate_hdfs_uri("hdfs://mycluster/") == "hdfs://mycluster"
    with pytest.raises(ValueError):
        validate_hdfs_root("/tmp/../warehouse")
    with pytest.raises(ValueError):
        validate_hdfs_uri("http://t218:9870")


def test_webhdfs_host_map_rewrites_namenode_and_datanode_urls():
    host_map = parse_host_map(
        "t216=39.108.97.159,t217=120.79.238.200,t218=120.79.241.111"
    )
    assert rewrite_host("http://t217:9870/webhdfs/v1/tmp", host_map) == (
        "http://120.79.238.200:9870/webhdfs/v1/tmp"
    )
    assert rewrite_host(
        "http://t216:9864/webhdfs/v1/tmp/data.orc?op=CREATE", host_map
    ) == "http://39.108.97.159:9864/webhdfs/v1/tmp/data.orc?op=CREATE"


def test_write_orc_creates_readable_file(tmp_path):
    pyorc = pytest.importorskip("pyorc")
    output = tmp_path / "data.orc"
    columns = [
        ("ticket", "string"),
        ("profit", "decimal(28,4)"),
        ("business_date", "date"),
    ]
    rows = [
        ("018-1", Decimal("12.3400"), dt.date(2026, 9, 28)),
        ("018-2", None, None),
    ]

    assert write_orc(output, columns, rows) == 2
    with output.open("rb") as stream:
        reader = pyorc.Reader(stream)
        assert len(reader) == 2
        assert list(reader)[0][0] == "018-1"


class FakeWebHdfsClient:
    def __init__(self, length: int):
        self.length = length
        self.directories: list[tuple[str, str]] = []

    def makedirs(self, path: str, permission: str):
        self.directories.append((path, permission))

    def upload(self, hdfs_path: str, _local_path: str, **_kwargs):
        return hdfs_path

    def status(self, _path: str, strict: bool):
        assert strict is True
        return {"length": self.length}


def test_upload_orc_checks_remote_size(tmp_path):
    local = tmp_path / "data.orc"
    local.write_bytes(b"orc-bytes")
    client = FakeWebHdfsClient(local.stat().st_size)

    remote, size = upload_orc(client, local, "/tmp/data-report/job")

    assert remote == "/tmp/data-report/job/data.orc"
    assert size == local.stat().st_size
    assert client.directories == [("/tmp/data-report/job", "700")]
