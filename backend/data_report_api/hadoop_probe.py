"""Standalone, opt-in Hive/HDFS client smoke test for the Docker worker plan."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree


HDFS_COMMAND = Path("/opt/hadoop/bin/hdfs")
HIVE_COMMAND = Path("/opt/hive/bin/hive")
JAVA_COMMAND = Path("/opt/java/bin/java")
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
    print(f"开始：{label}；命令：{' '.join(command)}；超时：{timeout}秒", flush=True)
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
        if error.stdout:
            output = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout
            print(f"超时前stdout（末2000字符）：{output[-2000:]}", flush=True)
        if error.stderr:
            output = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
            print(f"超时前stderr（末2000字符）：{output[-2000:]}", flush=True)
        raise ProbeError(f"{label}超时（{timeout}秒）") from error
    except OSError as error:
        raise ProbeError(f"{label}无法启动：{type(error).__name__}") from error
    if result.returncode:
        details = (result.stderr or result.stdout).strip().splitlines()
        summary = details[-1][:300] if details else "无错误输出"
        raise ProbeError(f"{label}失败，退出码{result.returncode}：{summary}")
    if result.stdout.strip():
        print(f"输出：{result.stdout.strip()[-2000:]}", flush=True)
    print(f"通过：{label}", flush=True)
    return result.stdout


def check_local_clients() -> None:
    for executable in (HDFS_COMMAND, HIVE_COMMAND, JAVA_COMMAND):
        if not executable.is_file():
            raise ProbeError(f"容器内缺少客户端文件：{executable}")
    for config_file in (HADOOP_CONFIG, HDFS_CONFIG, HIVE_CONFIG):
        if not config_file.is_file():
            raise ProbeError(f"容器内缺少配置文件：{config_file}")
    actual_fs = property_value(HADOOP_CONFIG, "fs.defaultFS")
    print(f"配置：{HADOOP_CONFIG} fs.defaultFS={actual_fs or '未配置'}", flush=True)
    if actual_fs != EXPECTED_FS:
        raise ProbeError(
            f"core-site.xml的fs.defaultFS为{actual_fs or '未配置'}，"
            f"不是{EXPECTED_FS}；请核对HADOOP_CLIENT_CONF挂载目录"
        )
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


def main() -> int:
    parser = argparse.ArgumentParser(description="容器内Hive/HDFS客户端探针；默认只读")
    parser.add_argument("--path", default=DEFAULT_PATH, help="只读检查的HDFS目录")
    arguments = parser.parse_args()
    try:
        check_local_clients()
        check_read_only(arguments.path)
        print("只读连通性检查完成；未创建Hive表、未写入HDFS", flush=True)
    except (ProbeError, ElementTree.ParseError) as error:
        print(f"探针未通过：{error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
