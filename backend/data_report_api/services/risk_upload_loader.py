from __future__ import annotations

import datetime as dt
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .data_source import DataSource
from .risk_upload_definitions import RiskUploadDefinition
from .risk_upload_orc import (
    create_webhdfs_client,
    delete_hdfs_directory,
    normalize_type,
    orc_value,
    upload_orc,
    validate_hdfs_root,
    validate_hdfs_uri,
    write_orc,
)


def trim_headers(values: Iterable[Any]) -> list[str]:
    headers = list(values)
    while headers and (headers[-1] is None or not str(headers[-1]).strip()):
        headers.pop()
    if not headers:
        raise ValueError("Excel首行没有有效表头")
    result: list[str] = []
    for index, value in enumerate(headers, start=1):
        if value is None or not str(value).strip():
            raise ValueError(f"Excel表头第{index}列为空，无法安全匹配字段")
        result.append(str(value).strip())
    duplicates = sorted({name for name in result if result.count(name) > 1})
    if duplicates:
        raise ValueError(f"Excel表头存在重复字段：{duplicates}")
    return result


def describe_target(cursor: Any, target_table: str) -> tuple[list[tuple[str, str]], bool]:
    cursor.execute(f"DESCRIBE {target_table}")
    columns: list[tuple[str, str]] = []
    partitioned = False
    partition_section = False
    for row in cursor.fetchall():
        name = str(row[0]).strip().lower() if row and row[0] is not None else ""
        if name.startswith("# partition"):
            partitioned = True
            partition_section = True
            continue
        if partition_section or not name or name.startswith("#"):
            continue
        columns.append((name, normalize_type(str(row[1]).strip())))
    return columns, partitioned


def repair_refund_row(values: list[Any], header_index: dict[str, int]) -> list[Any]:
    pcc_index = header_index.get("订位PCC")
    ticket_index = header_index.get("票数")
    if pcc_index is None or ticket_index is None:
        return values
    value = values[pcc_index] if pcc_index < len(values) else None
    looks_like_date = isinstance(value, (dt.date, dt.datetime)) or (
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value.strip()) is not None
    )
    if not looks_like_date:
        return values
    repaired = list(values)
    repaired.insert(pcc_index, None)
    if ticket_index >= len(repaired):
        raise ValueError("旧格式退票行缺少票数和月份，无法安全修复")
    repaired.pop(ticket_index)
    return repaired


@dataclass(frozen=True)
class CompositeKeyStats:
    total: int
    valid: int
    distinct: int
    missing: dict[str, int]


KEY_LABELS = {
    "issue_ticket_no": "出票票号",
    "passenger_name": "乘客姓名",
    "change_order_no": "改签单号",
}


def normalized_key_field(alias: str, field: str) -> str:
    prefix = f"{alias}." if alias else ""
    value = f"{prefix}`{field}`"
    normalized = f"TRIM({value})"
    if field == "passenger_name":
        normalized = f"UPPER({normalized})"
    return normalized


def composite_key_label(key_fields: tuple[str, ...]) -> str:
    return "+".join(KEY_LABELS[field] for field in key_fields)


def composite_key_join(
    left_alias: str,
    right_alias: str,
    key_fields: tuple[str, ...] = ("issue_ticket_no", "passenger_name"),
) -> str:
    return " AND ".join(
        f"{normalized_key_field(left_alias, field)}="
        f"{normalized_key_field(right_alias, field)}"
        for field in key_fields
    )


def composite_key_stats(
    cursor: Any,
    table: str,
    key_fields: tuple[str, ...] = ("issue_ticket_no", "passenger_name"),
) -> CompositeKeyStats:
    """Return completeness and uniqueness for a business merge key."""
    normalized = [normalized_key_field("", field) for field in key_fields]
    valid_condition = " AND ".join(
        f"`{field}` IS NOT NULL AND {value}<>''"
        for field, value in zip(key_fields, normalized)
    )
    missing_expressions = [
        f"SUM(CASE WHEN `{field}` IS NULL OR {value}='' THEN 1 ELSE 0 END)"
        for field, value in zip(key_fields, normalized)
    ]
    encoded_fields = [
        f"CONCAT(LENGTH({value}), ':', {value})" for value in normalized
    ]
    select_items = [
        "COUNT(1)",
        *missing_expressions,
        f"COUNT(CASE WHEN {valid_condition} THEN 1 END)",
        f"COUNT(DISTINCT CASE WHEN {valid_condition} THEN "
        f"CONCAT_WS('#|#', {', '.join(encoded_fields)}) END)",
    ]
    cursor.execute(
        f"SELECT {', '.join(select_items)} FROM {table}"
    )
    result = cursor.fetchone()
    total = result[0]
    missing_values = result[1 : 1 + len(key_fields)]
    valid, distinct_count = result[-2:]
    return CompositeKeyStats(
        total=int(total or 0),
        valid=int(valid or 0),
        distinct=int(distinct_count or 0),
        missing={
            field: int(value or 0)
            for field, value in zip(key_fields, missing_values)
        },
    )


def load_excel_to_hive(
    *,
    definition: RiskUploadDefinition,
    excel_path: str | Path,
    sheet_name: str,
    load_date: str | None,
    config: dict[str, Any],
    log: Callable[[str], None],
) -> tuple[int, int]:
    try:
        import openpyxl
    except ImportError as error:
        raise RuntimeError("导入Worker缺少openpyxl依赖") from error

    path = Path(excel_path).resolve()
    if not path.is_file() or path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("上传文件不存在或格式不是.xlsx/.xlsm")
    workbook = openpyxl.load_workbook(
        path, read_only=True, data_only=True, keep_links=False
    )
    connection = None
    cursor = None
    raw_staging_table = ""
    staging_table = ""
    merge_table = ""
    local_orc_path: Path | None = None
    webhdfs_client = None
    remote_dir = ""
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(
                f"工作表不存在：{sheet_name}；可选工作表={workbook.sheetnames}"
            )
        worksheet = workbook[sheet_name]
        header_rows = worksheet.iter_rows(min_row=1, max_row=1, values_only=True)
        try:
            headers = trim_headers(next(header_rows))
        except StopIteration as error:
            raise ValueError("Excel工作表为空") from error
        header_index = {name: index for index, name in enumerate(headers)}
        required_headers = [source for source, _ in definition.source_to_target]
        missing = [name for name in required_headers if name not in header_index]
        if missing:
            raise ValueError(f"Excel缺少目标表所需字段：{missing}")
        ignored = [name for name in headers if name not in required_headers]
        if ignored:
            log(f"忽略{len(ignored)}个非目标字段")

        source_indexes = [header_index[name] for name in required_headers]
        expected_columns = [target for _, target in definition.source_to_target]
        source = DataSource({**config, "DATA_MODE": "hive"})
        connection = source.connect()
        cursor = connection.cursor()
        actual_schema, partitioned = describe_target(cursor, definition.target_table)
        actual_columns = [name for name, _ in actual_schema]
        if actual_columns != expected_columns:
            first = next(
                (
                    index
                    for index, (actual, expected) in enumerate(
                        zip(actual_columns, expected_columns), start=1
                    )
                    if actual != expected
                ),
                min(len(actual_columns), len(expected_columns)) + 1,
            )
            raise RuntimeError(
                f"Hive目标表字段不一致：期望{len(expected_columns)}列，"
                f"实际{len(actual_columns)}列，首个差异在第{first}列"
            )
        if partitioned and not definition.partition_date_required:
            raise RuntimeError("目标表意外成为分区表，当前上传口径按非分区整表设计，已停止覆盖")
        if partitioned and not load_date:
            raise ValueError("分区表导入必须提供dt日期")
        log(f"Excel表头与Hive目标表{len(actual_schema)}列校验通过")

        # Excel转ORC和WebHDFS上传可能耗时较长，不能一直占用最初的
        # HiveServer2 Thrift会话，否则大文件上传后该空闲连接容易失效。
        cursor.close()
        cursor = None
        connection.close()
        connection = None

        database = definition.target_table.split(".", 1)[0]
        upload_id = uuid.uuid4().hex
        raw_staging_table = f"{database}.tmp_risk_upload_{upload_id}"
        column_ddl = ",\n".join(
            f"  `{name}` {data_type.upper()}" for name, data_type in actual_schema
        )

        def iter_orc_rows():
            for row_number, values in enumerate(
                worksheet.iter_rows(
                    min_row=2, max_col=len(headers), values_only=True
                ),
                start=2,
            ):
                row_values = list(values)
                if definition.key == "refund":
                    row_values = repair_refund_row(row_values, header_index)
                selected = [
                    row_values[index] if index < len(row_values) else None
                    for index in source_indexes
                ]
                if all(
                    value is None
                    or (isinstance(value, str) and not value.strip())
                    for value in selected
                ):
                    continue
                try:
                    yield tuple(
                        orc_value(value, data_type)
                        for value, (_, data_type) in zip(selected, actual_schema)
                    )
                except ValueError as error:
                    raise ValueError(f"Excel第{row_number}行：{error}") from error

        with tempfile.NamedTemporaryFile(
            prefix=f"risk-upload-{upload_id}-",
            suffix=".orc",
            dir=path.parent,
            delete=False,
        ) as temporary_file:
            local_orc_path = Path(temporary_file.name)
        total = write_orc(
            local_orc_path,
            actual_schema,
            iter_orc_rows(),
            str(config.get("RISK_UPLOAD_ORC_TIMEZONE", "Asia/Shanghai")),
        )
        if total <= 0:
            raise ValueError("Excel没有有效数据行，禁止覆盖Hive目标表")
        local_orc_size = local_orc_path.stat().st_size
        log(
            f"Excel校验及ORC转换完成：{total:,}行，"
            f"{local_orc_size / 1024 / 1024:.2f} MB"
        )

        remote_root = validate_hdfs_root(
            str(config.get("RISK_UPLOAD_HDFS_ROOT", "/tmp/data-report/risk-uploads"))
        )
        hdfs_uri = validate_hdfs_uri(
            str(config.get("RISK_UPLOAD_HDFS_URI", "hdfs://mycluster"))
        )
        remote_dir = f"{remote_root}/{upload_id}"
        webhdfs_client = create_webhdfs_client(config)
        remote_file, remote_size = upload_orc(
            webhdfs_client, local_orc_path, remote_dir
        )
        log(f"ORC已通过WebHDFS上传：{remote_size / 1024 / 1024:.2f} MB")

        connection = source.connect()
        cursor = connection.cursor()
        log("Hive连接已刷新，开始校验并合并数据")
        hdfs_location = f"{hdfs_uri}{remote_dir}"
        cursor.execute(
            f"CREATE EXTERNAL TABLE {raw_staging_table} (\n{column_ddl}\n) "
            f"STORED AS ORC LOCATION '{hdfs_location}'"
        )
        log(f"Hive ORC临时表已就绪：{Path(remote_file).name}")

        cursor.execute(f"SELECT COUNT(1) FROM {raw_staging_table}")
        staging_rows = int(cursor.fetchone()[0])
        if staging_rows != total:
            raise RuntimeError(
                f"Hive临时表行数不一致：Excel {total}行，临时表{staging_rows}行"
            )
        selected_columns = ", ".join(f"`{name}`" for name in expected_columns)
        key_fields = definition.merge_key_fields
        key_label = composite_key_label(key_fields)
        stage_stats = composite_key_stats(cursor, raw_staging_table, key_fields)
        if stage_stats.valid != stage_stats.total:
            missing_detail = "、".join(
                f"{stage_stats.missing[field]:,}行空{KEY_LABELS[field]}"
                for field in key_fields
                if stage_stats.missing[field]
            )
            raise ValueError(
                f"{definition.label}增量存在{missing_detail}，组合键不完整，禁止合并"
            )
        staging_table = raw_staging_table
        if stage_stats.distinct != stage_stats.total:
            staging_table = f"{database}.tmp_risk_unique_{upload_id}"
            cursor.execute(
                f"CREATE TEMPORARY TABLE {staging_table} (\n{column_ddl}\n) "
                "STORED AS ORC"
            )
            raw_columns = ", ".join(
                f"raw_rows.`{name}`" for name in expected_columns
            )
            unique_key_select = ",\n         ".join(
                f"{normalized_key_field('', field)} AS key_{index}"
                for index, field in enumerate(key_fields)
            )
            unique_key_group = ", ".join(
                normalized_key_field("", field) for field in key_fields
            )
            unique_key_join = " AND ".join(
                f"{normalized_key_field('raw_rows', field)}=unique_keys.key_{index}"
                for index, field in enumerate(key_fields)
            )
            cursor.execute(
                f"INSERT OVERWRITE TABLE {staging_table}\n"
                f"SELECT {raw_columns}\n"
                f"FROM {raw_staging_table} raw_rows\n"
                "JOIN (\n"
                f"  SELECT {unique_key_select}\n"
                f"  FROM {raw_staging_table}\n"
                f"  GROUP BY {unique_key_group}\n"
                "  HAVING COUNT(1)=1\n"
                ") unique_keys\n"
                f"ON {unique_key_join}"
            )
            connection.commit()
            filtered_stats = composite_key_stats(cursor, staging_table, key_fields)
            if (
                filtered_stats.total != filtered_stats.valid
                or filtered_stats.total != filtered_stats.distinct
            ):
                raise RuntimeError(f"{definition.label}重复组合键过滤结果校验失败")
            duplicate_rows = stage_stats.total - filtered_stats.total
            duplicate_key_count = stage_stats.distinct - filtered_stats.distinct
            log(
                f"{definition.label}增量已忽略{duplicate_key_count:,}个重复组合键"
                f"对应的{duplicate_rows:,}行；保留{filtered_stats.total:,}行"
                f"唯一{key_label}数据"
            )

        target_stats = composite_key_stats(
            cursor, definition.target_table, key_fields
        )
        if target_stats.valid != target_stats.total:
            missing_detail = "、".join(
                f"{target_stats.missing[field]:,}行空{KEY_LABELS[field]}"
                for field in key_fields
                if target_stats.missing[field]
            )
            raise RuntimeError(
                f"Hive{definition.label}原表存在{missing_detail}，"
                "请先清理原表后再增量导入"
            )
        if target_stats.distinct != target_stats.valid:
            raise RuntimeError(
                f"Hive{definition.label}原表存在"
                f"{target_stats.valid - target_stats.distinct:,}行重复组合键记录，"
                "请先清理原表后再增量导入"
            )

        cursor.execute(
            "SELECT "
            "SUM(CASE WHEN `estimated_profit_cny`=0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN `estimated_profit_cny` IS NULL "
            "OR `estimated_profit_cny`<>0 THEN 1 ELSE 0 END) "
            f"FROM {staging_table}"
        )
        delete_requests_raw, upsert_rows_raw = cursor.fetchone()
        delete_requests = int(delete_requests_raw or 0)
        upsert_rows = int(upsert_rows_raw or 0)

        cursor.execute(
            "SELECT "
            "SUM(CASE WHEN new_rows.`estimated_profit_cny`=0 THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN new_rows.`estimated_profit_cny` IS NULL "
            "OR new_rows.`estimated_profit_cny`<>0 THEN 1 ELSE 0 END) "
            f"FROM {definition.target_table} old_rows "
            f"JOIN {staging_table} new_rows "
            f"ON {composite_key_join('old_rows', 'new_rows', key_fields)}"
        )
        deleted_rows_raw, replaced_rows_raw = cursor.fetchone()
        deleted_rows = int(deleted_rows_raw or 0)
        replaced_rows = int(replaced_rows_raw or 0)
        added_rows = upsert_rows - replaced_rows
        unmatched_delete_rows = delete_requests - deleted_rows
        expected_rows = (
            target_stats.total - deleted_rows
            - replaced_rows + upsert_rows
        )
        log(
            f"{definition.label}复合键校验通过：原表{target_stats.total:,}行，"
            f"新增{added_rows:,}行，整行替换{replaced_rows:,}行，"
            f"删除{deleted_rows:,}行，"
            f"未命中删除指令{unmatched_delete_rows:,}行"
        )

        merge_table = f"{database}.tmp_risk_merge_{uuid.uuid4().hex}"
        cursor.execute(
            f"CREATE TEMPORARY TABLE {merge_table} (\n{column_ddl}\n) STORED AS ORC"
        )
        old_columns = ", ".join(
            f"old_rows.`{name}`" for name in expected_columns
        )
        new_columns = ", ".join(
            f"new_rows.`{name}`" for name in expected_columns
        )
        cursor.execute(
            f"INSERT OVERWRITE TABLE {merge_table}\n"
            f"SELECT {old_columns}\n"
            f"FROM {definition.target_table} old_rows\n"
            f"LEFT JOIN {staging_table} new_keys\n"
            f"ON {composite_key_join('old_rows', 'new_keys', key_fields)}\n"
            "WHERE new_keys.`issue_ticket_no` IS NULL\n"
            "UNION ALL\n"
            f"SELECT {new_columns}\nFROM {staging_table} new_rows\n"
            "WHERE new_rows.`estimated_profit_cny` IS NULL "
            "OR new_rows.`estimated_profit_cny`<>0"
        )
        connection.commit()
        merged_stats = composite_key_stats(cursor, merge_table, key_fields)
        if (
            merged_stats.total != expected_rows
            or merged_stats.valid != merged_stats.total
            or merged_stats.distinct != merged_stats.total
        ):
            raise RuntimeError(
                f"{definition.label}合并临时表校验失败："
                f"计划{expected_rows:,}行，实际{merged_stats.total:,}行，"
                f"唯一复合键{merged_stats.distinct:,}个"
            )
        log(
            f"{definition.label}合并临时表校验通过，共{merged_stats.total:,}行，"
            "开始重写正式表"
        )
        cursor.execute(
            f"INSERT OVERWRITE TABLE {definition.target_table}\n"
            f"SELECT {selected_columns}\nFROM {merge_table}"
        )
        connection.commit()
        final_stats = composite_key_stats(
            cursor, definition.target_table, key_fields
        )
        if (
            final_stats.total != expected_rows
            or final_stats.valid != final_stats.total
            or final_stats.distinct != final_stats.total
        ):
            raise RuntimeError(
                f"{definition.label}正式表校验失败："
                f"计划{expected_rows:,}行，实际{final_stats.total:,}行，"
                f"唯一复合键{final_stats.distinct:,}个"
            )
        log(
            f"{definition.label}增量导入完成：新增{added_rows:,}行，"
            f"替换{replaced_rows:,}行，删除{deleted_rows:,}行，"
            f"正式表共{final_stats.total:,}行"
        )
        return total, final_stats.total
    finally:
        if cursor is not None:
            cleanup_tables = dict.fromkeys(
                (merge_table, staging_table, raw_staging_table)
            )
            for temporary_table in cleanup_tables:
                if not temporary_table:
                    continue
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {temporary_table}")
                except Exception:
                    pass
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if webhdfs_client is not None and remote_dir:
            delete_hdfs_directory(webhdfs_client, remote_dir)
        if local_orc_path is not None:
            try:
                local_orc_path.unlink(missing_ok=True)
            except OSError:
                pass
        workbook.close()
