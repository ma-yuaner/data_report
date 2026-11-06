"""ERP IssueMatchRuleServiceImpl.ruleRank parity; no guessed priority weights."""
import json
from datetime import datetime

TEXT_FIELDS=('ota_code','ota_site_code','product_type','issue_supplier_code','issue_gds','issue_pcc',
 'booking_supplier_code','booking_gds','booking_pcc','airline','airline_except','cabin','cabin_except',
 'cabin_grade','cabin_grade_except','origin','origin_except','destination','destination_except',
 'issue_ticketing_date','travel_date_scope','travel_time_scope')
VALUE_FIELDS=('travel_start_date','travel_end_date','reverse_flag','is_transfer',
 'business_earliest_days','business_latest_days','manual_flag')
EXT_TEXT=('applyRefundReason','auxProductType','saleType','applyChangeReason',
 'paramOne','paramTwo','paramThree','paramFour','paramFive','flightWay')
EXT_VALUE=('receiptAmountMin','receiptAmountMax','isFreeChange','isInvalid','isExemption',
 'invalidTicketFlag','amountMin','amountMax','businessEarliestHours','businessLatestHours')
SORT_BASIS='权重降序 → 配置更新时间降序 → 规则ID降序'
LABELS={'ota_code':'平台','ota_site_code':'站点','product_type':'产品类型','airline':'航司',
 'airline_except':'除外航司','cabin':'子舱位','cabin_except':'除外子舱位','cabin_grade':'舱等',
 'cabin_grade_except':'除外舱等','origin':'主航段出发地','origin_except':'除外出发地',
 'destination':'主航段目的地','destination_except':'除外目的地','flight_number':'航班号',
 'manual_flag':'人工标记','issue_supplier_code':'出票供应商','issue_gds':'出票GDS','issue_pcc':'出票PCC',
 'booking_supplier_code':'订票供应商','booking_gds':'订票GDS','booking_pcc':'订票PCC',
 'issue_way':'出票方式','extFilter.paramOne':'出票方式', 'travel_start_date':'旅行开始日期',
 'travel_end_date':'旅行结束日期','issue_ticketing_date':'出票时间范围'}


def present(value):
    return value is not None and bool(str(value).strip())


def priority(rule):
    raw=rule.get('ext_json')
    ext=json.loads(raw) if isinstance(raw,str) and raw.strip() else (raw or {})
    if not isinstance(ext,dict):raise ValueError('配置扩展JSON不是对象')
    filters=ext.get('extFilter') or {}
    if not isinstance(filters,dict):raise ValueError('配置扩展条件不是对象')
    fields=[key for key in TEXT_FIELDS if present(rule.get(key))]
    fields += [key for key in VALUE_FIELDS if rule.get(key) is not None]
    fields += ['extFilter.'+key for key in EXT_TEXT if present(filters.get(key))]
    fields += ['extFilter.'+key for key in EXT_VALUE if filters.get(key) is not None]
    return {'weight':len(fields),'weightFields':fields,'sortBasis':SORT_BASIS}


def priority_key(rule):
    updated=rule.get('update_time')
    if not isinstance(updated,datetime):updated=datetime.fromisoformat(str(updated).replace(' ','T'))
    return priority(rule)['weight'],updated,int(rule['id'])


def conditions(rule):
    """Display every configured matching field, including fields not contributing to rank."""
    fields=(*TEXT_FIELDS,*VALUE_FIELDS,'flight_number')
    rows=[{'field':key,'label':LABELS.get(key,key),'value':str(rule[key])} for key in fields if present(rule.get(key))]
    raw=rule.get('ext_json')
    ext=json.loads(raw) if isinstance(raw,str) and raw.strip() else (raw or {})
    for key,value in (ext.get('extFilter') or {}).items():
        if present(value):rows.append({'field':'extFilter.'+key,'label':LABELS.get('extFilter.'+key,key),'value':str(value)})
    return rows
