"""
考勤周报解析模块 - 读取双文件并合并
- 文件1：考勤周报-YYYYMMDD-YYYYMMDD.xlsx → Sheet「异常排行榜」
- 文件2：考勤周报（部门、负责人、邮箱）.xlsx → Sheet1，列：部门 / 部门负责人 / 邮箱
"""

import re
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path
from datetime import datetime, time, timedelta

import openpyxl
import pandas as pd


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class ValidationError:
    row: int          # Excel 行号（1-based）
    column: str       # 列名
    message: str


@dataclass
class DeptReport:
    row_index: int           # Excel 行号（来源文件1）
    dept_name: str           # 部门名称
    dept_email: str          # 部门负责人邮箱
    dept_leader: str         # 部门负责人姓名（新增）
    dept_cc: str             # 抄送人邮箱（新增）
    report_period: str       # 报表周期（新增，从文件名提取）
    indicators: dict         # { "异常次数": 5, ... }
    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)


# 月度报表数据结构（一人一行）
@dataclass
class PersonMonthly:
    """月报中单个员工的聚合异常数据"""
    name: str                        # 姓名（按表头读取）
    department: str                  # 部门（按表头读取）
    total_work_duration: str = "-"   # 总工作时长（按表头读取）
    average_daily_work_duration: str = "-"  # 平均每日工作时长（按表头读取）
    exception_total: int = 0         # 异常合计（按表头读取）
    late: int = 0                    # 迟到（按表头读取）
    early_leave: int = 0             # 早退（按表头读取）
    makeup: int = 0                  # 补卡（按表头读取）
    missed_card: int = 0             # 缺卡（按表头读取）
    deduction: int | str = 0         # 考勤扣罚（按表头读取）
    absenteeism: int = 0             # 旷工（按表头读取）
    row_index: int = 0               # Excel 行号（考勤总览）


@dataclass
class DeptMonthReport:
    """月报中一个部门的汇总数据"""
    row_index: int                    # 部门在考勤总览出现的首行号
    dept_name: str                    # 部门名称
    dept_email: str                   # 邮箱
    dept_leader: str                  # 负责人
    dept_cc: str                      # 抄送
    report_period: str                # 周期，如「2026年6月」
    # 该部门有异常的人员列表（来自考勤总览）
    persons: List[PersonMonthly] = field(default_factory=list)
    # 该部门是否有任何异常人员（G列>0）
    has_exception: bool = False
    # 该部门是否存在请假/出差/外出明细（即使异常合计=0，仍会发附件）
    has_leave: bool = False
    has_business_trip: bool = False
    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)


EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


# ──────────────────────────────────────────────
# 旧版兼容类（保留，不推荐使用）
# ──────────────────────────────────────────────

@dataclass
class _ValidationError:
    row: int
    column: str
    message: str


@dataclass
class _DeptReport:
    row_index: int
    dept_name: str
    dept_email: str
    report_month: str
    indicators: dict
    valid: bool = True
    errors: List[_ValidationError] = field(default_factory=list)


REQUIRED_COLUMNS = ["部门名称", "部门邮箱", "报表月份"]


class ExcelParser:
    """解析固定模板 Excel（旧版，保留以兼容旧代码）。"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._wb: Optional[openpyxl.Workbook] = None
        self._ws: Optional[openpyxl.worksheet.worksheet.Worksheet] = None
        self._headers: List[str] = []

    def load(self) -> bool:
        try:
            self._wb = openpyxl.load_workbook(
                self.file_path, data_only=True, read_only=True
            )
            self._ws = self._wb.active
            return True
        except Exception as e:
            raise RuntimeError(f"无法读取 Excel 文件：{e}")

    def parse(self) -> List[_DeptReport]:
        if self._ws is None:
            raise RuntimeError("请先调用 load() 方法")

        rows = list(self._ws.iter_rows(values_only=True))
        if len(rows) < 2:
            raise RuntimeError("Excel 数据行不足（需要至少 1 行表头 + 1 行数据）")

        self._headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        missing = [col for col in REQUIRED_COLUMNS if col not in self._headers]
        if missing:
            raise RuntimeError(f"缺少必需列：{', '.join(missing)}")

        results: List[_DeptReport] = []
        for idx, row in enumerate(rows[1:], start=2):
            report = self._parse_row(row, idx)
            results.append(report)

        return results

    def _parse_row(self, row: tuple, row_num: int) -> _DeptReport:
        dept_name = self._get_cell(row, "部门名称")
        dept_email = self._get_cell(row, "部门邮箱")
        report_month = self._get_cell(row, "报表月份")

        indicators: dict = {}
        for col_name in self._headers:
            if col_name not in REQUIRED_COLUMNS:
                val = self._get_cell(row, col_name)
                indicators[col_name] = val

        errors: List[_ValidationError] = []
        if not dept_name:
            errors.append(_ValidationError(row_num, "部门名称", "部门名称不能为空"))
        if not dept_email:
            errors.append(_ValidationError(row_num, "部门邮箱", "部门邮箱不能为空"))
        elif not EMAIL_REGEX.match(dept_email):
            errors.append(_ValidationError(row_num, "部门邮箱", f"邮箱格式不正确：{dept_email}"))

        for col_name, val in indicators.items():
            if val is None or str(val).strip() == "":
                continue
            try:
                float(val)
            except (ValueError, TypeError):
                errors.append(_ValidationError(row_num, col_name, f"指标列需为数字，当前值：{val}"))

        report = _DeptReport(
            row_index=row_num,
            dept_name=dept_name,
            dept_email=dept_email,
            report_month=report_month,
            indicators=indicators,
            valid=(len(errors) == 0),
            errors=errors,
        )
        return report

    def _get_cell(self, row: tuple, col_name: str) -> str:
        try:
            idx = self._headers.index(col_name)
            val = row[idx]
            if val is None:
                return ""
            return str(val).strip()
        except (ValueError, IndexError):
            return ""

    def get_sheet_names(self) -> List[str]:
        if self._wb is None:
            return []
        return self._wb.sheetnames


# ──────────────────────────────────────────────
# 新版：考勤周报双文件解析
# ──────────────────────────────────────────────

def _extract_period_from_filename(filename: str) -> str:
    """
    从文件名提取报表周期。
    例如："考勤周报-20260511-20260517.xlsx" → "5月11日-5月17日"
    """
    # 匹配 8位数字-8位数字 模式
    m = re.search(r'(\d{8})-(\d{8})', filename)
    if not m:
        return "周报"
    start_str, end_str = m.group(1), m.group(2)
    try:
        start = datetime.strptime(start_str, "%Y%m%d")
        end = datetime.strptime(end_str, "%Y%m%d")
        return f"{start.month}月{start.day}日-{end.month}月{end.day}日"
    except ValueError:
        return "周报"


def _build_dept_mapping(dept_file: str) -> Dict[str, dict]:
    """
    读取文件2，构建 {部门名 → {leader, email}} 的字典。
    """
    mapping: Dict[str, dict] = {}
    wb = openpyxl.load_workbook(dept_file, data_only=True, read_only=True)
    ws = wb.active

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        dept_name = str(row[0]).strip() if row[0] else ""
        leader = str(row[1]).strip() if (len(row) > 1 and row[1]) else ""
        email = str(row[2]).strip() if (len(row) > 2 and row[2]) else ""
        cc = str(row[3]).strip() if (len(row) > 3 and row[3]) else ""
        if dept_name:
            mapping[dept_name] = {"leader": leader, "email": email, "cc": cc}

    wb.close()
    return mapping


class AttendanceParser:
    """
    考勤周报专用解析器。

    合并两个文件：
    - report_file：考勤周报-YYYYMMDD-YYYYMMDD.xlsx（异常数据来源）
    - dept_file：考勤周报（部门、负责人、邮箱）.xlsx（部门-邮箱映射）
    """

    def __init__(self, report_file: str, dept_file: str):
        self.report_file = Path(report_file)
        self.dept_file = Path(dept_file)
        self.report_period = _extract_period_from_filename(self.report_file.name)
        self._dept_mapping: Dict[str, dict] = {}
        self._report_wb: Optional[openpyxl.Workbook] = None
        self._report_ws: Optional[openpyxl.worksheet.worksheet.Worksheet] = None

    def load(self) -> bool:
        """加载两个 Excel 文件"""
        try:
            self._report_wb = openpyxl.load_workbook(
                self.report_file, data_only=True, read_only=True
            )
            # 查找「异常排行榜」Sheet，若不存在则用第一个 Sheet
            if "异常排行榜" in self._report_wb.sheetnames:
                self._report_ws = self._report_wb["异常排行榜"]
            else:
                self._report_ws = self._report_wb.active

            # 加载部门映射
            self._dept_mapping = _build_dept_mapping(str(self.dept_file))
            return True
        except Exception as e:
            raise RuntimeError(f"无法读取 Excel 文件：{e}")

    def parse(self) -> List[DeptReport]:
        """
        解析异常排行榜 Sheet：
        - 第1行（A1）：合并单元格标题，跳过
        - 第2行：表头（异常部门 / 异常次数），跳过
        - 第3行起：数据
        """
        if self._report_ws is None:
            raise RuntimeError("请先调用 load() 方法")

        rows = list(self._report_ws.iter_rows(values_only=True))
        if len(rows) < 3:
            raise RuntimeError("异常排行榜数据行不足")

        # 数据从第2行（index=1）起，第1行（index=0）是合并单元格标题
        results: List[DeptReport] = []
        for excel_row_idx, row in enumerate(rows[1:], start=2):
            if not row or (row[0] is None and row[1] is None):
                continue  # 跳过空行

            dept_name_raw = str(row[0]).strip() if row[0] else ""
            if not dept_name_raw:
                continue

            # 异常次数（指标）
            exception_count = row[1]
            if exception_count is None:
                exception_count = 0
            try:
                exception_count = int(exception_count)
            except (ValueError, TypeError):
                exception_count = 0

            # 查部门映射
            contact = self._dept_mapping.get(dept_name_raw, {})
            dept_leader = contact.get("leader", "")
            dept_email = contact.get("email", "")
            dept_cc = contact.get("cc", "")

            # 校验
            errors: List[ValidationError] = []
            if not dept_email:
                errors.append(ValidationError(
                    excel_row_idx, "邮箱",
                    f"未找到「{dept_name_raw}」的邮箱，请在部门映射表中补充"
                ))

            report = DeptReport(
                row_index=excel_row_idx,
                dept_name=dept_name_raw,
                dept_email=dept_email,
                dept_leader=dept_leader,
                dept_cc=dept_cc,
                report_period=self.report_period,
                indicators={"异常次数": exception_count},
                valid=(len(errors) == 0),
                errors=errors,
            )
            results.append(report)

        return results

    def get_report_sheet_names(self) -> List[str]:
        if self._report_wb is None:
            return []
        return self._report_wb.sheetnames

    def read_report_df(self, sheet_name: str = "异常排行榜") -> pd.DataFrame:
        """读取报表文件指定 Sheet 为 DataFrame"""
        try:
            return pd.read_excel(self.report_file, sheet_name=sheet_name, header=1)
        except Exception:
            return pd.DataFrame()

    def read_all_sheets_df(self) -> Dict[str, pd.DataFrame]:
        """读取报表文件所有 Sheet，返回 {sheet_name: df}"""
        result: Dict[str, pd.DataFrame] = {}
        for sn in self.get_report_sheet_names():
            result[sn] = self.read_report_df(sn)
        return result

    def parse_ranking_sheet(self) -> List[Dict]:
        """
        解析 Sheet1「异常排行榜」。
        返回: [{'department': str, 'count': int}, ...]
        """
        if self._report_ws is None:
            sheet_name = "异常排行榜"
            if "异常排行榜" in (self._report_wb.sheetnames if self._report_wb else []):
                self._report_ws = self._report_wb["异常排行榜"]
            else:
                return []

        rows = list(self._report_ws.iter_rows(values_only=True))
        result = []
        # 数据从第2行（index=1）起，第1行（index=0）是合并单元格标题
        for row in rows[1:]:
            if not row or (row[0] is None and row[1] is None):
                continue
            dept_name = str(row[0]).strip() if row[0] else ""
            if not dept_name:
                continue
            count = row[1]
            if count is None:
                count = 0
            try:
                count = int(count)
            except (ValueError, TypeError):
                count = 0
            result.append({'department': dept_name, 'count': count})
        return result

    def parse_summary_sheet(self, dept_name: str = None) -> tuple:
        """
        解析 Sheet2「概况统计与打卡明细」。
        按部门和姓名汇总异常合计次数。

        参数:
            dept_name: 如果提供，只返回该部门的数据；否则返回全部数据

        返回:
            - person_data: [{'name': str, 'department': str, 'total': int}, ...]
            - dept_data: [{'department': str, 'total': int}, ...]
        """
        try:
            ws = self._report_wb["概况统计与打卡明细"]
        except (KeyError, AttributeError):
            if self._report_wb:
                available = self._report_wb.sheetnames
                return [], []
            return [], []

        person_summary = {}  # name -> {department, total}
        dept_summary = {}    # dept -> total

        rows = list(ws.iter_rows(values_only=True))
        # 第1行是表头：时间=0, 姓名=1, 部门=2, ..., 异常合计(次)=13
        for row in rows[1:]:
            if not row or row[1] is None or row[13] is None:
                continue
            name = str(row[1]).strip() if row[1] else ""
            dept = str(row[2]).strip() if row[2] else ""
            count = row[13]
            try:
                count = int(count) if count else 0
            except (ValueError, TypeError):
                count = 0

            if not name:
                continue

            # 按部门过滤
            if dept_name and dept != dept_name:
                continue

            # 按姓名汇总
            if name not in person_summary:
                person_summary[name] = {'department': dept, 'total': 0}
            person_summary[name]['total'] += count

            # 按部门汇总（只统计过滤后的数据）
            if dept:
                if dept not in dept_summary:
                    dept_summary[dept] = 0
                dept_summary[dept] += count

        person_data = sorted(person_summary.items(), key=lambda x: x[1]['total'], reverse=True)
        person_data = [{'name': k, 'department': v['department'], 'total': v['total']} for k, v in person_data]

        dept_data = sorted(dept_summary.items(), key=lambda x: x[1], reverse=True)
        dept_data = [{'department': k, 'total': v} for k, v in dept_data]

        return person_data, dept_data

    def parse_flexible_sheet(self, dept_name: str = None) -> List[Dict]:
        """
        解析 Sheet3「弹性班次踩点关注名单」。

        参数:
            dept_name: 如果提供，只返回该部门的数据；否则返回全部数据

        返回: [{'name': str, 'department': str, 'count': int}, ...]
        """
        try:
            ws = self._report_wb["弹性班次踩点关注名单"]
        except (KeyError, AttributeError):
            if self._report_wb:
                available = self._report_wb.sheetnames
                return []
            return []

        result = []
        rows = list(ws.iter_rows(values_only=True))
        # 第1行是表头：姓名=A, 部门=B, 次数=C（第3列）
        # 遍历所有数据行，遇到空行或说明行停止
        for row in rows[1:]:
            # 跳过说明行（第18行只有说明文字，无部门）
            if row[0] is not None and isinstance(row[0], str) and "定义：" in row[0]:
                break
            if not row or row[0] is None or row[1] is None:
                continue
            name = str(row[0]).strip() if row[0] else ""
            dept = str(row[1]).strip() if row[1] else ""
            count = row[2]
            try:
                count = int(count) if count else 0
            except (ValueError, TypeError):
                count = 0

            if not name:
                continue

            # 按部门过滤
            if dept_name and dept != dept_name:
                continue

            result.append({'name': name, 'dept': dept, 'count': count})

        return result

    def parse_detail_data(self, dept_name: str = None) -> List[Dict]:
        """
        解析「概况统计与打卡明细」Sheet，返回打卡明细数据。

        参数:
            dept_name: 如果提供，只返回该部门的数据；否则返回全部数据

        返回: [{'time': str, 'name': str, 'dept': str, 'earliest': str, 'latest': str, 'result': str, 'exception': int}, ...]
        """
        try:
            ws = self._report_wb["概况统计与打卡明细"]
        except (KeyError, AttributeError):
            if self._report_wb:
                available = self._report_wb.sheetnames
                return []
            return []

        result = []
        rows = list(ws.iter_rows(values_only=True))

        # 表头: A=时间, B=姓名, C=部门, D=职务, E=工号, F=最早, G=最晚,
        #       H=打卡次数, I=请假, J=迟到, K=考勤结果, L=早退, M=早退状态,
        #       N=异常合计, O=迟到次数, P=迟到时间(分钟), Q=请假次数, R=请假时长,
        #       S=缺勤次数, T=缺勤时长, U=缺卡次数, V=缺卡事件

        for row in rows[1:]:
            if not row or row[1] is None:
                continue

            name = str(row[1]).strip() if row[1] else ""
            dept = str(row[2]).strip() if row[2] else ""

            if not name:
                continue

            # 按部门过滤
            if dept_name and dept != dept_name:
                continue

            # 获取各列数据
            time_val = row[0]
            earliest = row[5]  # F列
            latest = row[6]    # G列
            result_val = row[8]  # I列 考勤结果
            exception = row[13]  # N列

            # 格式化时间
            time_str = ""
            if time_val:
                if isinstance(time_val, str):
                    time_str = time_val[:10]
                else:
                    time_str = str(time_val)[:10]

            # 格式化最早/最晚
            earliest_str = str(earliest).strip() if earliest else "-"
            latest_str = str(latest).strip() if latest else "-"

            # 格式化考勤结果
            result_str = str(result_val).strip() if result_val else "-"

            # 异常次数
            try:
                exception_int = int(exception) if exception else 0
            except (ValueError, TypeError):
                exception_int = 0

            # 只添加有异常的记录
            if exception_int > 0:
                result.append({
                    'time': time_str,
                    'name': name,
                    'dept': dept,
                    'earliest': earliest_str,
                    'latest': latest_str,
                    'result': result_str,
                    'exception': exception_int,
                })

        return result


def _safe_int(v) -> int:
    """安全转换为整数，失败返回 0"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        try:
            return int(v)
        except (ValueError, TypeError, OverflowError):
            return 0
    s = str(v).strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _safe_int_or_text(v) -> int | str:
    """数值保持原有整数格式，非空文本原样保留"""
    if isinstance(v, str):
        text = v.strip()
        if not text:
            return 0
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return text
    return _safe_int(v)


def _duration_text(value) -> str:
    """保留月报时长文本；兼容Excel时长/时间单元格。"""
    if value is None:
        return "-"
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        sign = "-" if total_seconds < 0 else ""
        seconds = abs(total_seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if seconds:
            return f"{sign}{hours}:{minutes:02d}:{seconds:02d}"
        return f"{sign}{hours}:{minutes:02d}"
    if isinstance(value, time):
        return value.strftime("%H:%M:%S" if value.second or value.microsecond else "%H:%M")
    text = str(value).strip()
    return text or "-"


def _header_indexes(header) -> Dict[str, int]:
    """按去除空白后的表头定位列，避免新增列导致固定索引错位。"""
    return {
        re.sub(r"\s+", "", str(value)).strip(): index
        for index, value in enumerate(header or ())
        if value is not None and str(value).strip()
    }


def _header_value(row, indexes: Dict[str, int], *names):
    for name in names:
        index = indexes.get(re.sub(r"\s+", "", name))
        if index is not None and index < len(row):
            return row[index]
    return None


def _extract_period_from_month_filename(filename: str) -> str:
    """
    从月报文件名提取月度周期。
    例如："考勤月报-20260601-20260630.xlsx" → "2026年6月"
    """
    m = re.search(r'(\d{8})-(\d{8})', filename)
    if not m:
        return "月报"
    start_str = m.group(1)
    try:
        start = datetime.strptime(start_str, "%Y%m%d")
        return f"{start.year}年{start.month}月"
    except ValueError:
        return "月报"


# ──────────────────────────────────────────────
# 月报 Sheet 名匹配（带模糊匹配）
# ──────────────────────────────────────────────

def _find_sheet(wb: openpyxl.Workbook, candidates: List[str]) -> Optional[str]:
    """在 wb.sheetnames 中模糊匹配候选 sheet 名，返回匹配到的 sheet 名或 None"""
    if wb is None:
        return None
    names = wb.sheetnames
    for c in candidates:
        for n in names:
            if c == n:
                return n
    for c in candidates:
        for n in names:
            if c in n or n in c:
                return n
    return None


# ──────────────────────────────────────────────
# 月报解析器
# ──────────────────────────────────────────────

class MonthlyAttendanceParser:
    """
    考勤月报专用解析器。

    文件结构（4 个 Sheet 页）：
    - 考勤总览           : 按表头读取姓名、部门、总/日均工作时长及各异常字段
    - 考勤异常人员明细   : B姓名 / C部门
    - 请假明细           : B姓名 / C部门
    - 出差或外出明细     : B姓名 / C部门

    部门邮箱通过外部部门映射表（与周报共用）查找。
    """

    SHEET_OVERVIEW = "考勤总览"
    SHEET_EXCEPTION_DETAIL = "考勤异常人员明细"
    SHEET_LEAVE_DETAIL = "请假明细"
    SHEET_TRIP_DETAIL = "出差或外出明细"

    def __init__(self, report_file: str, dept_file: str):
        self.report_file = Path(report_file)
        self.dept_file = Path(dept_file)
        self.report_period = _extract_period_from_month_filename(self.report_file.name)
        self._dept_mapping: Dict[str, dict] = {}
        self._overview_wb: Optional[openpyxl.Workbook] = None
        # 以下为按部门聚合后的数据
        self._overview_by_dept: Dict[str, List[PersonMonthly]] = {}
        self._overview_dept_order: List[str] = []  # 考勤总览中部门首次出现顺序
        self._exception_detail_depts: set = set()
        self._leave_depts: set = set()
        self._trip_depts: set = set()
        self._sheet_rows_cache = {}

    def _sheet_rows(self, ws):
        # Preserve full-width tuples, including blank columns; only avoid rereads.
        if ws.title not in self._sheet_rows_cache:
            self._sheet_rows_cache[ws.title] = list(ws.iter_rows(values_only=True))
        return self._sheet_rows_cache[ws.title]

    def load(self) -> bool:
        try:
            self._overview_wb = openpyxl.load_workbook(
                self.report_file, data_only=True, read_only=True
            )
            self._dept_mapping = _build_dept_mapping(str(self.dept_file))
            return True
        except Exception as e:
            raise RuntimeError(f"无法读取月报 Excel 文件：{e}")

    # ── Sheet 解析辅助 ──

    def _parse_overview(self) -> None:
        """解析「考勤总览」Sheet，按部门聚合异常数据"""
        sheet_name = _find_sheet(
            self._overview_wb, [self.SHEET_OVERVIEW]
        )
        if not sheet_name:
            return
        ws = self._overview_wb[sheet_name]

        rows = self._sheet_rows(ws)
        if len(rows) < 2:
            return
        indexes = _header_indexes(rows[0])

        # 第1行是表头，从第2行开始
        for excel_row_idx, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            name_value = _header_value(row, indexes, "姓名")
            dept_value = _header_value(row, indexes, "部门")
            name = str(name_value).strip() if name_value else ""
            dept = str(dept_value).strip() if dept_value else ""
            if not name or not dept:
                continue

            person = PersonMonthly(
                name=name,
                department=dept,
                total_work_duration=_duration_text(
                    _header_value(row, indexes, "总工作时长")
                ),
                average_daily_work_duration=_duration_text(
                    _header_value(row, indexes, "平均每日工作时长")
                ),
                exception_total=_safe_int(
                    _header_value(row, indexes, "异常合计", "异常合计（次）", "异常合计(次)")
                ),
                absenteeism=_safe_int(
                    _header_value(row, indexes, "旷工", "旷工（次）", "旷工(次)")
                ),
                late=_safe_int(
                    _header_value(row, indexes, "迟到", "迟到（次）", "迟到(次)")
                ),
                early_leave=_safe_int(
                    _header_value(row, indexes, "早退", "早退（次）", "早退(次)")
                ),
                makeup=_safe_int(
                    _header_value(row, indexes, "补卡", "补卡（次）", "补卡(次)")
                ),
                missed_card=_safe_int(
                    _header_value(row, indexes, "缺卡", "缺卡（次）", "缺卡(次)")
                ),
                deduction=_safe_int_or_text(
                    _header_value(row, indexes, "考勤罚扣", "考勤扣罚")
                ),
                row_index=excel_row_idx,
            )

            if dept not in self._overview_by_dept:
                self._overview_by_dept[dept] = []
                self._overview_dept_order.append(dept)
            self._overview_by_dept[dept].append(person)

    def _parse_name_dept_sheet(self, candidates: List[str]) -> set:
        """
        通用解析器：从 Sheet 中读取 B列姓名、C列部门，把涉及的部门收集到集合中返回。
        """
        depts: set = set()
        sheet_name = _find_sheet(self._overview_wb, candidates)
        if not sheet_name:
            return depts
        ws = self._overview_wb[sheet_name]

        rows = self._sheet_rows(ws)
        if len(rows) < 2:
            return depts

        for row in rows[1:]:
            if not row:
                continue
            name = str(row[1]).strip() if len(row) > 1 and row[1] else ""
            dept = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            if not name or not dept:
                continue
            depts.add(dept)
        return depts

    # ── 主入口 ──

    def parse(self) -> List[DeptMonthReport]:
        """
        解析整个月报，返回部门级汇总列表。
        部门列表来源于：考勤总览 + 异常明细 + 请假明细 + 出差或外出明细 的并集。
        """
        if self._overview_wb is None:
            raise RuntimeError("请先调用 load() 方法")

        self._parse_overview()
        self._exception_detail_depts = self._parse_name_dept_sheet(
            [self.SHEET_EXCEPTION_DETAIL]
        )
        self._leave_depts = self._parse_name_dept_sheet(
            [self.SHEET_LEAVE_DETAIL]
        )
        self._trip_depts = self._parse_name_dept_sheet(
            [self.SHEET_TRIP_DETAIL]
        )

        # 部门并集
        all_depts: List[str] = []
        seen: set = set()
        for d in self._overview_dept_order:
            if d not in seen:
                all_depts.append(d)
                seen.add(d)
        for d in list(self._exception_detail_depts) + list(self._leave_depts) + list(self._trip_depts):
            if d not in seen:
                all_depts.append(d)
                seen.add(d)

        results: List[DeptMonthReport] = []
        for idx, dept_name in enumerate(all_depts, start=1):
            persons = self._overview_by_dept.get(dept_name, [])
            # 是否有任何异常（G列>0）
            has_exc = any(p.exception_total and p.exception_total > 0 for p in persons)

            contact = self._dept_mapping.get(dept_name, {})
            dept_email = contact.get("email", "")
            dept_leader = contact.get("leader", "")
            dept_cc = contact.get("cc", "")

            errors: List[ValidationError] = []
            if not dept_email:
                errors.append(ValidationError(
                    idx, "邮箱",
                    f"未找到「{dept_name}」的邮箱，请在部门映射表中补充"
                ))

            report = DeptMonthReport(
                row_index=idx,
                dept_name=dept_name,
                dept_email=dept_email,
                dept_leader=dept_leader,
                dept_cc=dept_cc,
                report_period=self.report_period,
                persons=persons,
                has_exception=has_exc,
                has_leave=(dept_name in self._leave_depts),
                has_business_trip=(dept_name in self._trip_depts),
                valid=(len(errors) == 0),
                errors=errors,
            )
            results.append(report)
        return results

    # ── 部门级别数据查询 ──

    def get_person_exceptions(self, dept_name: str) -> List[PersonMonthly]:
        """获取某部门的「异常合计>0」的人员列表（按异常次数降序）"""
        persons = self._overview_by_dept.get(dept_name, [])
        result = [p for p in persons if p.exception_total and p.exception_total > 0]
        result.sort(key=lambda p: (-p.exception_total, p.name))
        return result

    def get_exception_detail_rows(self, dept_name: str) -> List[dict]:
        """获取某部门在「考勤异常人员明细」Sheet 的所有原始行"""
        return self._read_name_dept_rows([self.SHEET_EXCEPTION_DETAIL], dept_name)

    def get_leave_rows(self, dept_name: str) -> List[dict]:
        return self._read_name_dept_rows([self.SHEET_LEAVE_DETAIL], dept_name)

    def get_trip_rows(self, dept_name: str) -> List[dict]:
        return self._read_name_dept_rows([self.SHEET_TRIP_DETAIL], dept_name)

    def _read_name_dept_rows(self, candidates: List[str], dept_name: str) -> List[tuple]:
        """
        读取某 sheet 中 C列匹配部门的所有行。
        返回: [(col1_val, col2_val, ...), ...]  — 直接按列索引取值，无列名冲突问题
        """
        sheet_name = _find_sheet(self._overview_wb, candidates)
        if not sheet_name:
            return []
        ws = self._overview_wb[sheet_name]
        rows = self._sheet_rows(ws)
        if len(rows) < 2:
            return []
        result = []
        for row in rows[1:]:
            if not row:
                continue
            d = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            if d != dept_name:
                continue
            result.append(tuple(row))
        return result

    def get_overview_rows_by_dept(self, dept_name: str) -> List[tuple]:
        """
        获取某部门在「考勤总览」Sheet 的所有原始行（保留本部门全部人员）。
        返回: [(col1_val, col2_val, ...), ...]
        """
        sheet_name = _find_sheet(self._overview_wb, [self.SHEET_OVERVIEW])
        if not sheet_name:
            return []
        ws = self._overview_wb[sheet_name]
        rows = self._sheet_rows(ws)
        if len(rows) < 2:
            return []
        result = []
        for row in rows[1:]:
            if not row:
                continue
            d = str(row[2]).strip() if len(row) > 2 and row[2] else ""
            if d != dept_name:
                continue
            result.append(tuple(row))
        return result

    def get_sheet_names(self) -> List[str]:
        if self._overview_wb is None:
            return []
        return self._overview_wb.sheetnames


# ──────────────────────────────────────────────
# 月报附件生成（按部门拆分）
# ──────────────────────────────────────────────

def generate_month_dept_attachment(
    report_file: str,
    dept_name: str,
    leave_rows: List[tuple],
    trip_rows: List[tuple],
    exception_rows: List[tuple],
    overview_rows: List[tuple],
    output_dir: Optional[str] = None,
) -> Optional[str]:
    """
    根据月报原始 Excel，按部门过滤各 Sheet，生成只含该部门数据的临时附件。

    拆分规则：
    - 考勤总览：保留该部门所有人员；无则删除整 Sheet
    - 考勤异常人员明细：保留该部门所有明细行；无则删除整 Sheet
    - 请假明细：保留该部门所有明细行；无则删除整 Sheet
    - 出差或外出明细：保留该部门所有明细行；无则删除整 Sheet

    若四个 Sheet 全部被删除（无任何数据），返回 None。
    """
    try:
        wb = openpyxl.load_workbook(report_file, data_only=True)
    except Exception:
        return None

    # 先收集各 Sheet 的原始 header，再决定删除哪些
    sheet_headers: dict = {}
    for sn in wb.sheetnames:
        ws = wb[sn]
        # The old code materialized every formatted cell just to take rows[0].
        header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if header is not None:
            sheet_headers[sn] = [str(h).strip() if h is not None else "" for h in header]

    # 先写入有数据的 Sheet（避免先删除 Sheet 导致数据丢失）
    sheets_to_delete: set = set()
    for sn in wb.sheetnames:
        if sn not in sheet_headers:
            continue

        header = sheet_headers[sn]
        rows: List[dict] = []
        if sn == "考勤总览":
            rows = overview_rows
        elif sn == "考勤异常人员明细":
            rows = exception_rows
        elif sn == "请假明细":
            rows = leave_rows
        elif sn == "出差或外出明细":
            rows = trip_rows
        else:
            # 非目标 Sheet，先保留（下次再处理）
            continue

        if not rows:
            sheets_to_delete.add(sn)
            continue

        ws = wb[sn]
        ws.delete_rows(1, ws.max_row)
        ws.append(header)
        for row_tuple in rows:
            # row_tuple 是列值元组，直接追加
            # Openpyxl does not serialize unstyled trailing None cells. Avoid
            # allocating millions of these cells; retain full header/dimensions.
            last = len(row_tuple)
            while last and row_tuple[last - 1] is None:
                last -= 1
            ws.append(list(row_tuple[:last]))
        # 禁用冻结窗格
        ws.freeze_panes = None

    # 再删除空 Sheet
    for sn in sheets_to_delete:
        del wb[sn]

    # 四个 Sheet 都被删光，返回 None
    if not wb.sheetnames:
        wb.close()
        return None

    temp_dir = output_dir or tempfile.gettempdir()
    safe_dept = dept_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    period_tag = _extract_period_from_month_filename(os.path.basename(report_file))
    temp_path = os.path.join(
        temp_dir, f"考勤月报_{safe_dept}_{period_tag}.xlsx"
    )
    try:
        wb.save(temp_path)
    except Exception:
        wb.close()
        return None
    wb.close()
    return temp_path
def generate_dept_attachment(report_file: str, dept_name: str, output_dir: Optional[str] = None) -> Optional[str]:
    """
    根据原始考勤周报 Excel，按部门过滤数据，生成只含该部门数据的临时文件。
    返回临时文件路径（调用方负责清理）。
    若无可过滤数据或出错，返回 None。
    """
    try:
        wb = openpyxl.load_workbook(report_file, data_only=True)
    except Exception:
        return None

    temp_dir = output_dir or tempfile.gettempdir()
    safe_dept = dept_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    temp_path = os.path.join(temp_dir, f"考勤周报_{safe_dept}.xlsx")

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            wb.close()
            return None

        header = list(rows[0])

        if sheet_name == "弹性班次踩点关注名单":
            new_rows = [header]
            for row in rows[1:]:
                if row[0] is not None and isinstance(row[0], str) and "定义：" in row[0]:
                    break
                if not row or row[0] is None or row[1] is None:
                    continue
                if str(row[1]).strip() == dept_name:
                    new_rows.append(list(row))
            if len(new_rows) > 1:
                ws.delete_rows(1, ws.max_row)
                for r in new_rows:
                    ws.append(r)
            else:
                ws.delete_rows(1, ws.max_row)

        elif sheet_name == "概况统计与打卡明细":
            new_rows = [header]
            for row in rows[1:]:
                if not row or row[1] is None:
                    continue
                if str(row[2]).strip() == dept_name:
                    new_rows.append(list(row))
            ws.delete_rows(1, ws.max_row)
            for r in new_rows:
                ws.append(r)

        else:
            pass

    try:
        wb.save(temp_path)
    except Exception:
        wb.close()
        return None
    wb.close()
    return temp_path
