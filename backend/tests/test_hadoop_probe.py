from __future__ import annotations

import pytest

from data_report_api import hadoop_probe


def test_client_config_mismatch_reports_actual_value(monkeypatch, tmp_path):
    for name in ("hdfs", "hive", "java", "hdfs-site.xml", "hive-site.xml"):
        (tmp_path / name).touch()
    core = tmp_path / "core-site.xml"
    core.write_text(
        "<configuration><property><name>fs.defaultFS</name>"
        "<value>hdfs://other</value></property></configuration>",
        encoding="utf-8",
    )
    monkeypatch.setattr(hadoop_probe, "HDFS_COMMAND", tmp_path / "hdfs")
    monkeypatch.setattr(hadoop_probe, "HIVE_COMMAND", tmp_path / "hive")
    monkeypatch.setattr(hadoop_probe, "JAVA_COMMAND", tmp_path / "java")
    monkeypatch.setattr(hadoop_probe, "HADOOP_CONFIG", core)
    monkeypatch.setattr(hadoop_probe, "HDFS_CONFIG", tmp_path / "hdfs-site.xml")
    monkeypatch.setattr(hadoop_probe, "HIVE_CONFIG", tmp_path / "hive-site.xml")
    with pytest.raises(hadoop_probe.ProbeError, match="hdfs://other"):
        hadoop_probe.check_local_clients()


def test_read_only_rejects_other_nameservice(monkeypatch):
    monkeypatch.setattr(hadoop_probe, "run", lambda *args, **kwargs: None)
    with pytest.raises(hadoop_probe.ProbeError, match="只允许测试"):
        hadoop_probe.check_read_only("hdfs://other/warehouse")


def test_read_only_rejects_hive_wrong_filesystem(monkeypatch):
    monkeypatch.setattr(hadoop_probe, "run", lambda *args, **kwargs: "")
    with pytest.raises(hadoop_probe.ProbeError, match="Hive CLI未确认"):
        hadoop_probe.check_read_only(hadoop_probe.DEFAULT_PATH)
