"""Standalone, opt-in Hive/HDFS client smoke test for the Docker worker plan."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from xml.etree import ElementTree


HDFS_COMMAND = Path("/opt/hadoop/bin/hdfs")
HIVE_COMMAND = Path("/opt/hive/bin/hive")
HADOOP_CONFIG = Path("/etc/hadoop/conf/core-site.xml")
HDFS_CONFIG = Path("/etc/hadoop/conf/hdfs-site.xml")
HIVE_CONFIG = Path("/etc/hive/conf/hive-site.xml")
EXPECTED_FS = "hdfs://mycluster"
DEFAULT_PATH = EXPECTED_FS + "/warehouse/lywz/ads/ads_gds_achievement_rate_day"


class ProbeError(RuntimeError):
    pass


def property_value(file_path: Path, key: str) -> str | None:
    root = ElementTree.parse(file_path).getroot()
    for prop in root.findall("property"):
        if prop.findtext("name", "").strip() == key:
            return prop.findtext("value", "").strip()
    return None


def run(command: list[str], label: str, timeout: int = 180) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ProbeError(f"{label}超时（{timeout}秒）") from error
    except OSError as error:
        raise ProbeError(f"{label}无法启动：{type(error).__name__}") from error
    if result.returncode:
        details = (result.stderr or result.stdout).strip().splitlines()
        summary = details[-1][:300] if details else "无错误输出"
        raise ProbeError(f"{label}失败，退出码{result.returncode}：{summary}")
    print(f"通过：{label}", flush=True)
    return result.stdout


def check_local_clients() -> None:
    for executable in (HDFS_COMMAND, HIVE_COMMAND, Path("/opt/java/bin/java")):
        if not executable.is_file():
            raise ProbeError(f"容器内缺少客户端文件：{executable}")
    for config_file in (HADOOP_CONFIG, HDFS_CONFIG, HIVE_CONFIG):
        if not config_file.is_file():
            raise ProbeError(f"容器内缺少配置文件：{config_file}")
    actual_fs = property_value(HADOOP_CONFIG, "fs.defaultFS")
    if actual_fs != EXPECTED_FS:
        raise ProbeError(f"core-site.xml的fs.defaultFS不是{EXPECTED_FS}，已停止测试")
    print("通过：容器内客户端及mycluster配置文件存在", flush=True)


def check_read_only(path: str) -> None:
    if not path.startswith(EXPECTED_FS + "/"):
        raise ProbeError(f"只允许测试{EXPECTED_FS}下的HDFS路径")
    run([str(HDFS_COMMAND), "dfs", "-stat", "%F", path], "HDFS目录状态读取", 90)
    hive_output = run(
        [str(HIVE_COMMAND), "-e", "SET fs.defaultFS; SELECT 1;"],
        "hive -e只读查询",
        180,
    )
    if f"fs.defaultFS={EXPECTED_FS}" not in hive_output:
        raise ProbeError("Hive CLI未确认fs.defaultFS=hdfs://mycluster，禁止继续写入测试")


def check_local_load(database: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise ProbeError("测试库名只能包含字母、数字和下划线")
    table = f"{database}.tmp_data_report_probe_{uuid.uuid4().hex}"
    print(f"本次唯一测试表：{table}", flush=True)
    with tempfile.TemporaryDirectory(prefix="data_report_hive_probe_") as temporary:
        file_path = Path(temporary) / "part-00000"
        file_path.write_text("probe\n", encoding="utf-8")
        created = False
        try:
            run(
                [str(HIVE_COMMAND), "-e", f"CREATE TABLE {table} (probe_value STRING) STORED AS TEXTFILE"],
                "创建唯一命名的测试暂存表",
                300,
            )
            created = True
            run(
                [str(HIVE_COMMAND), "-e", f"LOAD DATA LOCAL INPATH '{file_path}' INTO TABLE {table}"],
                "LOAD DATA LOCAL单行写入",
                300,
            )
            output = run(
                [str(HIVE_COMMAND), "-e", f"SELECT COUNT(1) FROM {table}"],
                "测试暂存表行数查询",
                300,
            )
            if "1" not in {line.strip() for line in output.splitlines()}:
                raise ProbeError("测试暂存表行数不是1，必须人工核查")
            print("通过：单行文件导入及行数校验", flush=True)
        finally:
            if created:
                run(
                    [str(HIVE_COMMAND), "-e", f"DROP TABLE IF EXISTS {table}"],
                    "清理本次唯一命名的测试暂存表",
                    300,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="容器内Hive/HDFS客户端探针；默认只读")
    parser.add_argument("--path", default=DEFAULT_PATH, help="只读检查的HDFS目录")
    parser.add_argument("--write-db", help="显式指定已授权测试库，创建并删除一张单行测试表")
    arguments = parser.parse_args()
    try:
        check_local_clients()
        check_read_only(arguments.path)
        if arguments.write_db:
            check_local_load(arguments.write_db)
        else:
            print("只读检查完成；未创建Hive表、未写入HDFS", flush=True)
    except (ProbeError, ElementTree.ParseError) as error:
        print(f"探针未通过：{error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
