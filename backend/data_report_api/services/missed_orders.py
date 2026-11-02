"""Read-only access to the migrated downgrade missed-order result table."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from .data_source import DataSource
from ..shared.permissions import permission_codes
from ..time_utils import business_now_naive

TABLE = 'bi_downgrade_missed_order_day'
MENU = 'smart.placement.missed'
EXPORT_PERMISSION = 'smart_placement.missed.export'
MAX_EXPORT = 500_000
PLATFORMS = dict(zip(
    'CTRIP FLIGGY QUNAR LY TUNIU MEITUAN JD JINRI 517NA LVMAMA 8000YI TRAFREE OWT MAFENGWO INDIVIDUAL HNCZ HYZH FR LYB2B PKFARE UNIFIFI DD LF OWTHK AGODA ORBIS LYWZ TM HBGJ JG'.split(),
    ['携程','飞猪','去哪儿','同程','途牛','美团','京东','今通','我要去哪','驴妈妈旅游','八千翼','自由飞越','乐游五洲','马蜂窝','散客','湖南晨舟','寰宇纵横','航路','易旅行','PKFARE','由你飞飞','道旅','乐飞天下','香港五洲线下','安可达(Agoda)','奥比斯','核价平台','途灵','航班管家','说走就走'],
))
JOBS = {'H01':'智能定位','H02':'智能降舱','H03':'智能废票'}
BUSINESSES = dict(zip(
    [f'HB{n:02d}' for n in range(1,11)],
    ['占位提醒','提醒不占位','比价测试','取消编码占位','HX编码补位','改签占位','升舱降价','智能占位','未来运价','未来运价(批量任务)'],
))
FIELDS = ['id','company_code','business_date','analysis_code','ota_code','ota_order_no','airline','dep_city','arr_city','order_smart_confirm_flag','job_type','hpr_job_business_type','cabin','hpr_cabin','policy_operator_group_name','policy_operator','remark','issue_ticket_time','sale_diff_price','create_time','update_time']
FILTER_FIELDS = {'platform':'ota_code','airline':'airline','operator':'policy_operator','group':'policy_operator_group_name','depCity':'dep_city','arrCity':'arr_city','jobType':'job_type','businessType':'hpr_job_business_type'}
SORTS = {'issueTicketTime':'issue_ticket_time','saleDiffPrice':'sale_diff_price','createdAt':'create_time','id':'id'}
EXPORT_COLUMNS = [
    ('platformName','平台'),('otaCode','平台代码'),('otaOrderNo','OTA订单号'),('airline','航司'),
    ('saleDiffPrice','比价差（原值）'),('depCity','出发城市'),('arrCity','到达城市'),
    ('cabin','降前舱位'),('hprCabin','降后舱位'),('policyOperator','政策员'),
    ('policyOperatorGroupName','组别'),('remark','备注'),('issueTicketTime','出票时间'),
    ('jobTypeName','任务类型'),('businessTypeName','业务类型'),('id','原记录ID'),
    ('businessDate','原业务日期'),('createTime','创建时间'),('updateTime','更新时间'),
    ('companyCode','业务公司代码'),('analysisCode','分析代码'),('jobType','任务类型代码'),
    ('hprJobBusinessType','业务类型代码'),('orderSmartConfirmFlag','原智能确认标记'),
]


class MissedOrdersUnavailable(RuntimeError):
    pass


class MissedOrdersCancelled(RuntimeError):
    pass


class MissedOrderNotFound(ValueError):
    pass


def require_menu(user: dict[str, Any]) -> None:
    if not user.get('id'):
        raise PermissionError('登录用户信息不完整')
    if not (user.get('is_admin') or user.get('isAdmin') or MENU in (user.get('menu_codes') or user.get('menuCodes') or [])):
        raise PermissionError('当前账号没有漏处理订单菜单权限')


def text(value: Any, name: str, maximum: int = 100) -> str:
    value = '' if value is None else str(value).strip()
    if len(value) > maximum:
        raise ValueError(f'{name}不能超过{maximum}个字符')
    return value


def normalize(values: dict[str, Any]) -> dict[str, str]:
    result = {key: text(values.get(key), key, 100) for key in FILTER_FIELDS}
    result['otaOrderNo'] = text(values.get('otaOrderNo'), 'OTA订单号', 50)
    for key in ('minPrice','maxPrice'):
        raw = text(values.get(key), '比价差', 32)
        if raw:
            try:
                value = Decimal(raw)
            except InvalidOperation as error:
                raise ValueError('比价差必须为有效数值') from error
            if not value.is_finite() or value.copy_abs() >= Decimal('100000000000000') or value != value.quantize(Decimal('.01')):
                raise ValueError('比价差最多两位小数且须在字段范围内')
            raw = format(value, 'f')
        result[key] = raw
    if result['minPrice'] and result['maxPrice'] and Decimal(result['minPrice']) > Decimal(result['maxPrice']):
        raise ValueError('比价差下限不能大于上限')
    if result['otaOrderNo']:
        result.update(startDate='', endDate='')
    else:
        start, end = values.get('startDate'), values.get('endDate')
        if not start and not end:
            first = business_now_naive().date().replace(day=1)
            next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            start, end = (first-timedelta(days=7)).isoformat(), (next_month-timedelta(days=1)).isoformat()
        try:
            first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        except ValueError as error:
            raise ValueError('请填写完整、有效的出票开始和结束日期') from error
        if last < first or (last-first).days >= 366 or last.year==9999:
            raise ValueError('出票日期须正序且单次最多366天')
        result.update(startDate=first.isoformat(), endDate=last.isoformat())
    result['sortBy'] = text(values.get('sortBy') or 'issueTicketTime', '排序字段', 30)
    result['direction'] = text(values.get('direction') or 'desc', '排序方向', 4).lower()
    if result['sortBy'] not in SORTS or result['direction'] not in {'asc','desc'}:
        raise ValueError('排序条件不支持')
    return result


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    def camel(key):
        head, *tail = key.split('_')
        return head + ''.join(part.title() for part in tail)
    result = {camel(k): v.isoformat(sep=' ') if isinstance(v, datetime) else v.isoformat() if isinstance(v, date) else format(v, 'f') if isinstance(v, Decimal) else v for k,v in row.items()}
    if 'ota_code' in row: result['platformName'] = PLATFORMS.get(row['ota_code'],row['ota_code'])
    if 'job_type' in row: result['jobTypeName'] = JOBS.get(row['job_type'],row['job_type'])
    if 'hpr_job_business_type' in row: result['businessTypeName'] = BUSINESSES.get(row['hpr_job_business_type'],row['hpr_job_business_type'])
    return result


def dict_rows(cursor, rows):
    columns = [column[0] for column in (cursor.description or [])]
    return [dict(row) if isinstance(row, dict) else dict(zip(columns,row)) for row in rows]


class MissedOrdersService:
    def __init__(self, config, source=None):
        self.source = source or DataSource({**config,'DATA_MODE':'mysql','MYSQL_DATABASE':'sibebid'})

    @property
    def table(self):
        return f'{self.source.database}.{TABLE}'

    def scope(self, cursor, user):
        require_menu(user)
        scope = (user.get('data_scopes') or user.get('dataScopes') or {}).get('smart_placement.order','SELF')
        if user.get('is_admin') or user.get('isAdmin') or scope == 'ALL':
            return {'mode':'ALL','names':[]}
        # Reuse the existing active employee binding and explicit manager-member relation.
        # Display names are not trusted as identities. Ambiguous bound names fail closed.
        database = self.source.database
        eligibility = 'b.sys_user_id=%s'
        params = [int(user['id'])]
        if scope == 'MANAGED':
            eligibility += f" OR EXISTS (SELECT 1 FROM {database}.sys_user_manager_relation mr WHERE mr.manager_user_id=%s AND mr.member_user_id=b.sys_user_id AND mr.resource_code='smart_placement' AND mr.is_active=1)"
            params.append(int(user['id']))
        cursor.execute(f"""SELECT DISTINCT b.employee_name_snapshot AS name
            FROM {database}.sys_user_employee_binding b
            WHERE b.status='ACTIVE' AND ({eligibility})
              AND NULLIF(TRIM(b.employee_name_snapshot),'') IS NOT NULL
              AND (SELECT COUNT(*) FROM {database}.sys_user_employee_binding same_name
                   WHERE same_name.status='ACTIVE' AND same_name.employee_name_snapshot=b.employee_name_snapshot)=1""", tuple(params))
        names = sorted({row['name'] for row in dict_rows(cursor, list(cursor.fetchall()))})
        return {'mode':'MANAGED' if scope == 'MANAGED' else 'SELF','names':names}

    def scope_signature(self, user):
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            scope = self.scope(cursor,user)
            return hashlib.sha256(json.dumps(scope,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        except (ValueError,PermissionError):
            raise
        except Exception as error:
            raise self.unavailable(error) from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def where(self, cursor, user, values, record_id=None):
        scope = self.scope(cursor,user)
        clauses = ["company_code=%s","analysis_code=%s"]
        params: list[Any] = ['1020','DOWNGRADE_MISSED']
        if scope['mode'] != 'ALL':
            if scope['names']:
                clauses.append(f"policy_operator IN ({','.join(['%s']*len(scope['names']))})")
                params.extend(scope['names'])
            else:
                clauses.append('1=0')
        if record_id is not None:
            clauses.append('id=%s'); params.append(int(record_id))
        elif values['otaOrderNo']:
            clauses.append('ota_order_no=%s'); params.append(values['otaOrderNo'])
        else:
            clauses.extend(['issue_ticket_time >= %s','issue_ticket_time < %s'])
            params.extend([values['startDate'],(date.fromisoformat(values['endDate'])+timedelta(days=1)).isoformat()])
        for key,column in FILTER_FIELDS.items():
            value = values[key]
            if value == '__NULL__':
                clauses.append(f"NULLIF(TRIM({column}),'') IS NULL")
            elif value:
                clauses.append(f'{column}=%s'); params.append(value)
        for key,operator in [('minPrice','>='),('maxPrice','<=')]:
            if values[key]:
                clauses.append(f'sale_diff_price{operator}%s'); params.append(Decimal(values[key]))
        return ' AND '.join(clauses), params, scope

    @staticmethod
    def unavailable(error):
        if getattr(error,'args',()) and error.args[0] == 1146:
            return MissedOrdersUnavailable('漏处理结果表或人员绑定表尚未就绪，请核对sibebid迁移及原有权限配套表')
        return MissedOrdersUnavailable('漏处理订单查询失败，请稍后重试')

    def list(self, user, values):
        require_menu(user)
        filters = normalize(values)
        try:
            page, size = max(1,int(values.get('page') or 1)), max(1,min(100,int(values.get('pageSize') or 30)))
        except (ValueError,TypeError) as error:
            raise ValueError('分页参数无效') from error
        connection = cursor = None
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            where, params, scope = self.where(cursor,user,filters)
            cursor.execute(f"""SELECT COUNT(*) AS record_count,
                COUNT(DISTINCT ota_code,ota_order_no) AS order_count,
                COUNT(DISTINCT NULLIF(policy_operator,'')) AS operator_count,
                COUNT(DISTINCT dep_city,arr_city) AS route_count,
                MAX(update_time) AS latest_row_updated_at
                FROM {self.table} WHERE {where}""",tuple(params))
            summary = dict_rows(cursor,[cursor.fetchone()])[0]
            sort = SORTS[filters['sortBy']]; direction = filters['direction'].upper()
            cursor.execute(f"SELECT {','.join(FIELDS)} FROM {self.table} WHERE {where} ORDER BY {sort} {direction},id {direction} LIMIT %s OFFSET %s", tuple([*params,size,(page-1)*size]))
            rows = [public_row(row) for row in dict_rows(cursor,list(cursor.fetchall()))]
            return {'available':True,'source':self.table,'filters':filters,'scope':scope['mode'],
                    'scopeEmpty':scope['mode']!='ALL' and not scope['names'],
                    'summary':public_row(summary),'rows':rows,'total':int(summary['record_count']),'page':page,'pageSize':size}
        except (ValueError,PermissionError):
            raise
        except Exception as error:
            raise self.unavailable(error) from error
        finally:
            if connection is not None: connection.rollback()
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def options(self,user,values):
        filters = normalize(values)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            where,params,_ = self.where(cursor,user,filters)
            result = {}
            for key in ('platform','airline','operator','group','jobType','businessType'):
                column = FILTER_FIELDS[key]
                cursor.execute(f"SELECT DISTINCT {column} AS value FROM {self.table} WHERE {where} ORDER BY {column} LIMIT 251",tuple(params))
                rows = dict_rows(cursor,list(cursor.fetchall()))
                labels = PLATFORMS if key=='platform' else JOBS if key=='jobType' else BUSINESSES if key=='businessType' else {}
                choices = {r['value'] if r['value'] not in (None,'') else '__NULL__': labels.get(r['value'],r['value']) or '未填写' for r in rows[:250]}
                result[key] = {'truncated':len(rows)>250,'rows':[{'value':value,'label':label} for value,label in choices.items()]}
            return result
        except (ValueError,PermissionError):
            raise
        except Exception as error:
            raise self.unavailable(error) from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def detail(self,user,record_id):
        require_menu(user)
        connection = cursor = None
        try:
            connection = self.source.connect(); cursor = connection.cursor()
            filters = normalize({'otaOrderNo':'__detail__'})
            where,params,scope = self.where(cursor,user,filters,record_id=record_id)
            cursor.execute(f"SELECT {','.join(FIELDS)} FROM {self.table} WHERE {where}",tuple(params))
            raw = cursor.fetchone()
            if raw is None: raise MissedOrderNotFound('记录不存在或不在当前可见范围')
            row = dict_rows(cursor,[raw])[0]
            same = normalize({'otaOrderNo':row['ota_order_no'],'platform':row['ota_code']})
            same_where,same_params,_ = self.where(cursor,user,same)
            cursor.execute(f"SELECT {','.join(FIELDS)} FROM {self.table} WHERE {same_where} ORDER BY update_time DESC,id DESC LIMIT 21",tuple(same_params))
            history = dict_rows(cursor,list(cursor.fetchall()))
            return {'row':public_row(row),'history':[public_row(r) for r in history[:20]],'historyTruncated':len(history)>20,'scope':scope['mode']}
        except (ValueError,PermissionError):
            raise
        except Exception as error:
            raise self.unavailable(error) from error
        finally:
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()

    def export(self,user,values,on_total=None,cancelled=None):
        require_menu(user)
        if not (user.get('is_admin') or user.get('isAdmin') or EXPORT_PERMISSION in permission_codes(user)):
            raise PermissionError('当前账号没有漏处理订单导出权限')
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.utils import get_column_letter
        filters = normalize(values)
        connection = cursor = None
        workbook = Workbook(write_only=True)
        output = BytesIO()
        try:
            connection = self.source.connect(); connection.begin(); cursor = connection.cursor()
            where,params,_ = self.where(cursor,user,filters)
            cursor.execute(f'SELECT COUNT(*) FROM {self.table} WHERE {where}',tuple(params))
            raw = cursor.fetchone(); total = int(next(iter(raw.values())) if isinstance(raw,dict) else raw[0])
            if total>MAX_EXPORT: raise ValueError('漏处理明细导出单次最多500000条，请缩小范围')
            if on_total: on_total(total)
            if cancelled and cancelled(): raise MissedOrdersCancelled()
            sheet = workbook.create_sheet('漏处理订单')
            sheet.freeze_panes='A2'
            sheet.auto_filter.ref=f'A1:{get_column_letter(len(EXPORT_COLUMNS))}{total+1}'
            for index,(_,label) in enumerate(EXPORT_COLUMNS,1):
                sheet.column_dimensions[get_column_letter(index)].width = 38 if label=='备注' else 24 if '时间' in label or '订单号' in label else 16
            sheet.append([label for _,label in EXPORT_COLUMNS])
            sort = SORTS[filters['sortBy']]; direction=filters['direction'].upper()
            import pymysql
            cursor.close(); cursor = connection.cursor(pymysql.cursors.SSCursor)
            cursor.execute(f"SELECT {','.join(FIELDS)} FROM {self.table} WHERE {where} ORDER BY {sort} {direction},id {direction}",tuple(params))
            while True:
                if cancelled and cancelled(): raise MissedOrdersCancelled()
                batch = cursor.fetchmany(2000)
                if not batch: break
                for raw in dict_rows(cursor,list(batch)):
                    row = public_row(raw); cells=[]
                    for key,_ in EXPORT_COLUMNS:
                        value = Decimal(row[key]) if key=='saleDiffPrice' and row[key] is not None else row.get(key)
                        date_field = {'issueTicketTime':'issue_ticket_time','createTime':'create_time','updateTime':'update_time','businessDate':'business_date'}.get(key)
                        if date_field:
                            value = raw.get(date_field)
                            if isinstance(value,str): value = date.fromisoformat(value) if key=='businessDate' else datetime.fromisoformat(value)
                        if key=='id' and value is not None: value = str(value)
                        cell=WriteOnlyCell(sheet,value=value)
                        if isinstance(value,str): cell.data_type='s'; cell.number_format='@'
                        elif date_field: cell.number_format='yyyy-mm-dd' if key=='businessDate' else 'yyyy-mm-dd hh:mm:ss'
                        elif key=='saleDiffPrice': cell.number_format='#,##0.00'
                        cells.append(cell)
                    sheet.append(cells)
            workbook.save(output); output.seek(0)
            return output,'漏处理订单.xlsx'
        except (PermissionError,ValueError,MissedOrdersCancelled):
            output.close(); raise
        except Exception as error:
            output.close(); raise self.unavailable(error) from error
        finally:
            workbook.close()
            if connection is not None: connection.rollback()
            if cursor is not None: cursor.close()
            if connection is not None: connection.close()
