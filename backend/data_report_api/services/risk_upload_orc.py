from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


HIVE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HDFS_PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]+$")
HDFS_URI_RE = re.compile(r"^hdfs://[A-Za-z0-9_.-]+(?::[0-9]+)?$")
HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def normalize_type(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def orc_schema(columns: Sequence[tuple[str, str]]) -> str:
    fields: list[str] = []
    for name, data_type in columns:
        if not HIVE_COLUMN_RE.fullmatch(name):
            raise ValueError(f"Hive字段名无法安全写入ORC：{name}")
        normalized = normalize_type(data_type)
        if not normalized:
            raise ValueError(f"Hive字段{name}缺少类型")
        fields.append(f"{name}:{normalized}")
    return "struct<" + ",".join(fields) + ">"


def _decimal(value: Any, data_type: str) -> Decimal:
    stripped = str(value).strip().replace(",", "")
    try:
        number = Decimal(stripped)
        precision, scale = (int(item) for item in re.findall(r"\d+", data_type))
        if not number.is_finite() or abs(number) >= Decimal(10) ** (precision - scale):
            raise ValueError("超出范围")
        exponent = max(0, -number.normalize().as_tuple().exponent)
        if exponent > scale:
            raise ValueError(f"小数位超过{scale}位")
        return number
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"无法将{value!r}转换为{data_type}") from error


def orc_value(value: Any, target_type: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    data_type = normalize_type(target_type)
    if data_type == "string" or data_type.startswith(("varchar(", "char(")):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dt.datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        return str(value)

    stripped = str(value).strip().replace(",", "")
    if data_type in {"tinyint", "smallint", "int", "bigint"}:
        try:
            number = Decimal(stripped)
            if not number.is_finite() or number != number.to_integral_value():
                raise ValueError("非整数")
            return int(number)
        except (InvalidOperation, ValueError, OverflowError) as error:
            raise ValueError(f"无法将{value!r}转换为{data_type}") from error
    if data_type.startswith("decimal("):
        return _decimal(value, data_type)
    if data_type in {"float", "double"}:
        try:
            number = float(stripped)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"无法将{value!r}转换为{data_type}") from error
        if number != number or number in {float("inf"), float("-inf")}:
            raise ValueError(f"无法将{value!r}转换为{data_type}")
        return number
    if data_type == "boolean":
        lowered = stripped.lower()
        if lowered not in {"true", "false", "1", "0"}:
            raise ValueError(f"无法将{value!r}转换为boolean")
        return lowered in {"true", "1"}
    if data_type == "date":
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        try:
            return dt.date.fromisoformat(str(value).strip()[:10])
        except ValueError as error:
            raise ValueError(f"无法将{value!r}转换为date") from error
    if data_type == "timestamp":
        if isinstance(value, dt.datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, dt.date):
            return dt.datetime.combine(value, dt.time())
        text = str(value).strip().replace("T", " ")
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"无法将{value!r}转换为timestamp") from error
        return parsed.replace(tzinfo=None)
    if data_type == "binary":
        return value if isinstance(value, bytes) else str(value).encode("utf-8")
    raise ValueError(f"暂不支持ORC字段类型：{target_type}")


def write_orc(
    output_path: str | Path,
    columns: Sequence[tuple[str, str]],
    rows: Iterable[Sequence[Any]],
    timezone_name: str = "Asia/Shanghai",
) -> int:
    try:
        import pyorc
    except ImportError as error:
        raise RuntimeError("导入Worker缺少pyorc依赖") from error

    path = Path(output_path)
    count = 0
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"ORC时区不存在：{timezone_name}") from error
    try:
        with path.open("wb") as stream:
            with pyorc.Writer(
                stream, orc_schema(columns), timezone=timezone
            ) as writer:
                for row in rows:
                    writer.write(tuple(row))
                    count += 1
    except (OSError, TypeError) as error:
        raise RuntimeError(f"生成ORC失败：{error}") from error
    return count


def validate_hdfs_root(value: str) -> str:
    root = str(PurePosixPath("/" + value.strip().lstrip("/")))
    if root in {"/", "."} or not HDFS_PATH_RE.fullmatch(root) or ".." in root.split("/"):
        raise ValueError("RISK_UPLOAD_HDFS_ROOT不是安全的HDFS绝对目录")
    return root.rstrip("/")


def validate_hdfs_uri(value: str) -> str:
    uri = value.strip().rstrip("/")
    if not HDFS_URI_RE.fullmatch(uri):
        raise ValueError("RISK_UPLOAD_HDFS_URI必须是hdfs://名称服务或主机")
    return uri


def parse_host_map(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        source, separator, destination = item.partition("=")
        source = source.strip().lower()
        destination = destination.strip()
        if (
            not separator
            or not HOST_RE.fullmatch(source)
            or not HOST_RE.fullmatch(destination)
        ):
            raise ValueError(
                "RISK_UPLOAD_WEBHDFS_HOST_MAP格式应为t216=IP,t217=IP"
            )
        result[source] = destination
    return result


def rewrite_host(url: str, host_map: dict[str, str]) -> str:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    destination = host_map.get(hostname)
    if not destination:
        return url
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (parsed.scheme, f"{destination}{port}", parsed.path, parsed.query, parsed.fragment)
    )


def create_webhdfs_client(config: dict[str, Any]):
    urls = str(config.get("RISK_UPLOAD_WEBHDFS_URL", "")).strip()
    user = str(config.get("RISK_UPLOAD_WEBHDFS_USER", "")).strip()
    if not urls or not user:
        raise RuntimeError("WebHDFS配置不完整，请设置URL和用户")
    if any(not item.strip().startswith(("http://", "https://")) for item in urls.split(";")):
        raise ValueError("RISK_UPLOAD_WEBHDFS_URL必须是HTTP地址，HA地址用分号分隔")
    try:
        from hdfs import InsecureClient
        import requests
    except ImportError as error:
        raise RuntimeError("导入Worker缺少hdfs依赖") from error
    host_map = parse_host_map(
        str(config.get("RISK_UPLOAD_WEBHDFS_HOST_MAP", ""))
    )
    urls = ";".join(rewrite_host(item.strip(), host_map) for item in urls.split(";"))
    session = requests.Session()

    def rewrite_redirect(response, *_args, **_kwargs):
        location = response.headers.get("Location")
        if location:
            response.headers["Location"] = rewrite_host(location, host_map)
        return response

    session.hooks["response"].append(rewrite_redirect)
    connect_timeout = max(1, int(config.get("RISK_UPLOAD_WEBHDFS_CONNECT_TIMEOUT", 10)))
    read_timeout = max(1, int(config.get("RISK_UPLOAD_WEBHDFS_READ_TIMEOUT", 300)))
    return InsecureClient(
        urls,
        user=user,
        timeout=(connect_timeout, read_timeout),
        session=session,
    )


def upload_orc(
    client: Any,
    local_path: str | Path,
    remote_dir: str,
) -> tuple[str, int]:
    local = Path(local_path)
    remote_file = f"{remote_dir.rstrip('/')}/data.orc"
    try:
        client.makedirs(remote_dir, permission="700")
        uploaded = client.upload(
            remote_file,
            str(local),
            overwrite=True,
            n_threads=1,
            cleanup=True,
        )
        status = client.status(uploaded, strict=True)
    except Exception as error:
        raise RuntimeError(
            f"WebHDFS上传ORC失败：{type(error).__name__}：{str(error)[:300]}"
        ) from error
    remote_size = int(status.get("length", -1))
    local_size = local.stat().st_size
    if remote_size != local_size:
        raise RuntimeError(
            f"WebHDFS文件大小校验失败：本地{local_size}字节，HDFS {remote_size}字节"
        )
    return str(uploaded), remote_size


def delete_hdfs_directory(client: Any, remote_dir: str) -> None:
    try:
        client.delete(remote_dir, recursive=True)
    except Exception:
        pass
