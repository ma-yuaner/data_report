from __future__ import annotations

import pytest

from data_report_api import hadoop_probe


def test_read_only_rejects_other_nameservice(monkeypatch):
    monkeypatch.setattr(hadoop_probe, "run", lambda *args, **kwargs: None)
    with pytest.raises(hadoop_probe.ProbeError, match="只允许测试"):
        hadoop_probe.check_read_only("hdfs://other/warehouse")


def test_read_only_rejects_hive_wrong_filesystem(monkeypatch):
    monkeypatch.setattr(hadoop_probe, "run", lambda *args, **kwargs: "")
    with pytest.raises(hadoop_probe.ProbeError, match="Hive CLI未确认"):
        hadoop_probe.check_read_only(hadoop_probe.DEFAULT_PATH)


def test_write_probe_uses_unique_table_and_cleans_up(monkeypatch):
    commands = []

    def fake_run(command, label, timeout=180):
        commands.append(command[-1])
        return "1\n" if "COUNT(1)" in command[-1] else ""

    monkeypatch.setattr(hadoop_probe, "run", fake_run)
    hadoop_probe.check_local_load("probe_db")
    assert len(commands) == 4
    assert commands[0].startswith("CREATE TABLE probe_db.tmp_data_report_probe_")
    assert commands[1].startswith("LOAD DATA LOCAL INPATH '")
    assert commands[2].startswith("SELECT COUNT(1) FROM probe_db.tmp_data_report_probe_")
    assert commands[3].startswith("DROP TABLE IF EXISTS probe_db.tmp_data_report_probe_")
    table = commands[0].split(" (")[0].removeprefix("CREATE TABLE ")
    assert all(table in statement for statement in commands)


def test_write_probe_cleans_up_after_load_failure(monkeypatch):
    commands = []

    def fake_run(command, label, timeout=180):
        commands.append(command[-1])
        if "LOAD DATA LOCAL" in command[-1]:
            raise hadoop_probe.ProbeError("load failed")
        return ""

    monkeypatch.setattr(hadoop_probe, "run", fake_run)
    with pytest.raises(hadoop_probe.ProbeError, match="load failed"):
        hadoop_probe.check_local_load("probe_db")
    assert commands[-1].startswith("DROP TABLE IF EXISTS probe_db.tmp_data_report_probe_")


def test_write_probe_rejects_unsafe_database(monkeypatch):
    monkeypatch.setattr(hadoop_probe, "run", lambda *args, **kwargs: None)
    with pytest.raises(hadoop_probe.ProbeError, match="测试库名"):
        hadoop_probe.check_local_load("lywz;drop")
