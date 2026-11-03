"""Excel ingestion for new placement opportunities only; never updates workflow rows."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from ..time_utils import business_now_naive

from .smart_placement import (
    PERMISSION_CREATE, SmartPlacementService, SmartPlacementUnavailable,
    _actor, _require_permission, _task_fields,
)

MAX_ROWS = 200
MAX_BYTES = 2 * 1024 * 1024
# Header, create-input key, input guidance. No IDs, owners, status or review fields.
COLUMNS = [
    ('机会名称', 'opportunityName', '必填，最多200字'),
    ('机会来源', 'opportunitySource', '人工发现/会议要求/数据分析规则识别；留空为人工发现'),
    ('分析规则编号', 'analysisRuleCode', '规则识别并提交审核时必填'),
    ('分析开始日期', 'analysisStartDate', '必填，YYYY-MM-DD'),
    ('分析结束日期', 'analysisEndDate', '必填，YYYY-MM-DD'),
    ('平台编码', 'platformCode', '选填，填写业务真实编码'),
    ('平台名称', 'platformName', '必填，与页面单笔录入一致'),
    ('站点编码', 'siteCode', '选填'), ('站点名称', 'siteName', '选填'),
    ('航司', 'airlineCode', '必填，航司编码，例如HO'),
    ('出发类型', 'departureType', '机场/城市/国家，留空为机场'),
    ('出发代码', 'departureCode', '对应类型的代码，留空表示不限'),
    ('到达类型', 'arrivalType', '机场/城市/国家，留空为机场'),
    ('到达代码', 'arrivalCode', '对应类型的代码，留空表示不限'),
    ('航程类型', 'journeyType', '单程/往返/多程，选填'),
    ('航段类型', 'segmentType', '直达/中转，选填'),
    ('航班号', 'flightNos', '多个用英文逗号分隔'),
    ('包含舱位', 'includeCabins', '多个用英文逗号分隔'),
    ('排除舱位', 'excludeCabins', '不得与包含舱位重叠'),
    ('产品类型', 'productType', '选填'),
    ('订单来源', 'orderSource', '平台手工订单/直连订单，可用逗号分隔，留空不限'),
    ('销售开始日期', 'orderStartDate', 'YYYY-MM-DD，选填'),
    ('销售结束日期', 'orderEndDate', 'YYYY-MM-DD，选填'),
    ('提前销售天数', 'advanceSaleDays', '非负整数，选填'),
    ('去程旅行开始日期', 'travelStartDate', 'YYYY-MM-DD，选填'),
    ('去程旅行结束日期', 'travelEndDate', 'YYYY-MM-DD，选填'),
    ('建议投放方式', 'placementMethod', '必填，最多300字'),
    ('亏损阈值下限', 'lossThresholdMin', 'CNY，非负，与上限同时填或同时留空'),
    ('亏损阈值上限', 'lossThresholdMax', 'CNY，非负'),
    ('长期有效', 'longTerm', '是/否，留空为否'),
    ('建议生效时间', 'suggestedEffectiveStart', 'YYYY-MM-DD HH:mm:ss，提交审核必填'),
    ('建议失效时间', 'suggestedEffectiveEnd', '同上，非长期有效且提交审核时必填'),
    ('历史票数', 'historicalTicketCount', '非负整数，提交审核必填'),
    ('历史利润', 'historicalProfitCny', 'CNY数值，提交审核必填'),
    ('预估月票数', 'estimatedMonthTicketCount', '非负整数，提交审核必填'),
    ('预估月利润', 'estimatedMonthProfitCny', 'CNY数值，提交审核必填'),
    ('分析结论', 'analysisConclusion', '必填，最多10000字'),
    ('风险提示', 'riskNote', '选填，最多10000字'),
    ('优先级', 'priority', '高/中/低，留空为中'),
    ('期望完成时间', 'expectedCompleteAt', '必填，YYYY-MM-DD HH:mm:ss'),
]
REQUIRED_HEADERS = {'机会名称', '分析开始日期', '分析结束日期', '平台名称', '航司', '建议投放方式', '分析结论', '期望完成时间'}
INTEGER_FIELDS = {'advanceSaleDays', 'historicalTicketCount', 'estimatedMonthTicketCount'}
MONEY_FIELDS = {'lossThresholdMin', 'lossThresholdMax', 'historicalProfitCny', 'estimatedMonthProfitCny'}
ENUMS = {
    'opportunitySource': {'人工发现': 'MANUAL', '会议要求': 'MEETING', '数据分析规则识别': 'AUTO_ANALYSIS'},
    'priority': {'高': 'HIGH', '中': 'MEDIUM', '低': 'LOW'},
    'departureType': {'机场': 'AIRPORT', '城市': 'CITY', '国家': 'COUNTRY'},
    'arrivalType': {'机场': 'AIRPORT', '城市': 'CITY', '国家': 'COUNTRY'},
}


def require_import(user):
    _require_permission(user, PERMISSION_CREATE, '当前账号没有投放机会录入权限')
    _actor(user)


TEMPLATE_EXAMPLE = [
    '完整填写示例（正式导入前请替换）',
    '数据分析规则识别',
    'DEMO_RULE_001',
    datetime(2026, 10, 1, 0, 0, 0),
    datetime(2026, 10, 31, 0, 0, 0),
    'CTRIP',
    '携程',
    'DEMO_SITE_001',
    '示例站点（请替换）',
    'HO',
    '机场',
    'PVG',
    '机场',
    'BKK',
    '单程',
    '直达',
    'HO1357,HO1359',
    'Y,B,M',
    'X,N',
    '示例产品（请替换）',
    '平台手工订单,直连订单',
    datetime(2026, 11, 3, 0, 0, 0),
    datetime(2026, 11, 30, 0, 0, 0),
    7,
    datetime(2026, 11, 10, 0, 0, 0),
    datetime(2027, 1, 31, 0, 0, 0),
    '小流量测试，具体政策请按真实分析填写',
    0,
    30,
    '否',
    datetime(2026, 11, 5, 0, 0, 0),
    datetime(2026, 11, 12, 23, 59, 59),
    128,
    3660.25,
    40,
    1200,
    '示例数据，请替换为实际分析依据。',
    '示例仅说明填写格式，请核对实际政策和日期。',
    '中',
    datetime(2026, 11, 4, 18, 0, 0),
]


def template_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = '机会导入'
    sheet.append([column[0] for column in COLUMNS])
    sheet.append(TEMPLATE_EXAMPLE)
    sheet.freeze_panes = 'A2'
    sheet.row_dimensions[2].height = 60
    for cell in sheet[2]:
        cell.fill = PatternFill('solid', fgColor='FFF2CC')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        if isinstance(cell.value, datetime):
            key = COLUMNS[cell.column - 1][1]
            cell.number_format = 'yyyy-mm-dd' if key.endswith('Date') else 'yyyy-mm-dd hh:mm:ss'
    for cell in sheet[1]:
        cell.font = Font(color='FFFFFF', bold=True)
        cell.fill = PatternFill('solid', fgColor='2456A6')
        sheet.column_dimensions[cell.column_letter].width = 23
    for index, (_, key, _) in enumerate(COLUMNS, start=1):
        choices = list(ENUMS.get(key, {})) if key in ENUMS else ['是', '否'] if key == 'longTerm' else []
        if choices:
            validation = DataValidation(type='list', formula1='"' + ','.join(choices) + '"', allow_blank=True)
            validation.errorTitle = '请使用支持的选项'
            validation.error = '请选择下拉选项，或按字段说明填写。'
            validation.showErrorMessage = True
            sheet.add_data_validation(validation)
            letter = sheet.cell(1, index).column_letter
            validation.add(f'{letter}2:{letter}{MAX_ROWS + 1}')
    notes = workbook.create_sheet('填写说明')
    notes.append(['批量新建分析机会', '仅填写“机会导入”工作表；第1行表头不可改名；第2行黄色为完整示例，正式导入前必须替换或删除，否则会作为真实机会导入。'])
    notes.append(['多选分隔符', '航班号、包含舱位、排除舱位、订单来源均使用英文逗号（,），例如Y,B,M、平台手工订单,直连订单；不要使用竖线（|）。'])
    notes.append(['单值字段', '平台、航司、出发代码、到达代码每格只填一个值；多个组合请分行填写。示例为虚构数据，需替换为真实业务编码、日期和分析。'])
    notes.append(['操作边界', '仅新建草稿或提交数据审核；不支持导入任务ID、状态、审核、负责人或投放登记。'])
    notes.append(['限制', '每次最多200行、2MB；不接受公式、合并单元格或宏；校验失败整批不写入。'])
    notes.append(['重复确认', '同账号、同内容、同导入方式重复确认返回原任务，不覆盖已有内容。'])
    notes.append(['时间', '按业务时区填写；日期YYYY-MM-DD，时间YYYY-MM-DD HH:mm:ss。'])
    notes.append(['字段', '填写要求'])
    for header, _, guidance in COLUMNS:
        notes.append([header, guidance])
    notes.column_dimensions['A'].width = 26
    notes.column_dimensions['B'].width = 110
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _cell_value(cell, key):
    if cell.data_type in {'f', 'e'}:
        raise ValueError('不接受公式或Excel错误值，请粘贴为值')
    value = cell.value
    if value is None or (isinstance(value, str) and not value.strip()):
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d' if key.endswith('Date') else '%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.isoformat()
    if key in INTEGER_FIELDS | MONEY_FIELDS:
        try:
            number = Decimal(str(value).strip())
            if not number.is_finite():
                raise ValueError('数值必须有限')
            if key in INTEGER_FIELDS and number != number.to_integral_value():
                raise ValueError('票数和天数必须为整数')
            integer_max = 2147483647 if key == 'advanceSaleDays' else 9223372036854775807
            if key in INTEGER_FIELDS and not Decimal(0) <= number <= Decimal(integer_max):
                raise ValueError(f'票数和天数须在0至{integer_max}之间')
            money_limit = Decimal('100000000000000') if key.startswith('lossThreshold') else Decimal('10000000000000000')
            if key in MONEY_FIELDS and abs(number) >= money_limit:
                raise ValueError('金额超出字段范围')
            if key in MONEY_FIELDS and number != number.quantize(Decimal('.0001')):
                raise ValueError('金额最多四位小数')
            return format(number, 'f') if key in MONEY_FIELDS else str(int(number))
        except (InvalidOperation, OverflowError) as error:
            raise ValueError('必须为有效数值') from error
    if key == 'longTerm':
        text = str(value).strip().lower()
        if text not in {'是', '否', 'true', 'false', '1', '0'}:
            raise ValueError('长期有效只能填是或否')
        return text in {'是', 'true', '1'}
    text = str(value).strip()
    return ENUMS.get(key, {}).get(text, text)


def read_rows(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError('请上传不超过2MB的.xlsx文件')
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20 * 1024 * 1024 or len(archive.infolist()) > 100:
                raise ValueError('Excel解压后过大，请拆分文件')
            if any('vbaProject' in item.filename or 'externalLinks/' in item.filename for item in archive.infolist()):
                raise ValueError('不接受宏或外部链接')
        workbook = load_workbook(BytesIO(content), read_only=False, data_only=False, keep_links=False)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('无法读取Excel，请使用下载的.xlsx模板') from error
    try:
        if '机会导入' not in workbook.sheetnames:
            raise ValueError('缺少“机会导入”工作表，请使用模板')
        sheet = workbook['机会导入']
        if sheet.max_row > MAX_ROWS + 1 or sheet.max_column > len(COLUMNS):
            raise ValueError('每次最多200行，且不能增加模板以外的列；请删除多余行列')
        if sheet.merged_cells.ranges:
            raise ValueError('机会导入工作表不能合并单元格')
        headers = [str(cell.value or '').strip() for cell in sheet[1]]
        mapping = {header: key for header, key, _ in COLUMNS}
        if len(set(headers)) != len(headers) or set(headers) - mapping.keys() or REQUIRED_HEADERS - set(headers):
            raise ValueError('表头重复、缺失或含不支持字段；不支持任务ID、状态及修改字段，请使用模板')
        rows, errors = [], []
        for line, cells in enumerate(sheet.iter_rows(min_row=2), start=2):
            if all(cell.value in (None, '') for cell in cells):
                continue
            values = {'opportunitySource': 'MANUAL', 'priority': 'MEDIUM', 'departureType': 'AIRPORT', 'arrivalType': 'AIRPORT', 'longTerm': False}
            try:
                for header, cell in zip(headers, cells):
                    value = _cell_value(cell, mapping[header])
                    if value != '':
                        values[mapping[header]] = value
                rows.append({'line': line, 'values': values})
            except (ValueError, TypeError) as error:
                errors.append({'line': line, 'message': f'{header}：{error}'})
        if not rows and not errors:
            raise ValueError('文件没有待导入的数据，请从第2行开始填写')
        return rows, errors
    finally:
        workbook.close()


class PlacementImportService:
    def __init__(self, config, *, service=None):
        self.config = config
        self.service = service or SmartPlacementService(config)

    def _signer(self):
        secret = self.config.get('SECRET_KEY')
        if not secret:
            raise SmartPlacementUnavailable('缺少导入校验签名配置')
        return URLSafeTimedSerializer(secret, salt='placement-create-import-v1')

    def preview(self, user, content, *, submit=False):
        require_import(user)
        rows, errors = read_rows(content)
        total = len(rows) + len(errors)
        valid = []
        for row in rows:
            try:
                if row['values']['opportunitySource'] not in {'MANUAL', 'MEETING', 'AUTO_ANALYSIS'}:
                    raise ValueError('机会来源不支持')
                _task_fields(row['values'], submit=submit)
                valid.append(row)
            except ValueError as error:
                errors.append({'line': row['line'], 'message': str(error)})
        # No write and no DB connection if file validation already failed.
        if not errors:
            connection = cursor = None
            try:
                connection = self.service.source.connect()
                cursor = connection.cursor()
                for row in valid:
                    try:
                        self.service._validate_locations(cursor, _task_fields(row['values'], submit=submit), business_now_naive())
                    except ValueError as error:
                        errors.append({'line': row['line'], 'message': str(error)})
            except Exception as error:
                raise SmartPlacementUnavailable('导入范围校验暂不可用，请稍后重新预览') from error
            finally:
                if cursor is not None:
                    cursor.close()
                if connection is not None:
                    connection.close()
        payload = {'userId': int(user['id']), 'submit': submit, 'rows': valid}
        digest = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        payload['batchKey'] = digest
        token = self._signer().dumps(payload) if not errors else ''
        return {'total': total, 'validCount': total - len(errors),
                'fields': [{'title': title, 'key': key} for title, key, _ in COLUMNS],
                'errors': sorted(errors, key=lambda item: item['line']), 'token': token, 'submit': submit,
                'rows': [{'line': row['line'], **row['values']} for row in rows]}

    def confirm(self, user, token):
        require_import(user)
        if not isinstance(token, str) or len(token) > 8 * 1024 * 1024:
            raise ValueError('导入凭据无效，请重新预览')
        try:
            payload = self._signer().loads(token, max_age=1800)
        except SignatureExpired as error:
            raise ValueError('预览已超过30分钟，请重新上传校验') from error
        except BadSignature as error:
            raise ValueError('导入凭据无效，请重新预览') from error
        if payload.get('userId') != int(user['id']):
            raise PermissionError('不能确认其他账号的导入')
        return self.service.create_import_tasks(user, payload['rows'], payload['batchKey'], submit=payload['submit'])
