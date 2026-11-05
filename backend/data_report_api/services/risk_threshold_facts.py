"""Read minimal segment/airport facts; ambiguous main-segment selection stays unknown."""
from .risk_order_evidence import _rows

SEGMENTS_SQL = """SELECT s.id,s.order_id,s.cabin,s.cabin_grade,s.flight_number,s.dep_airport,s.arr_airport,
 s.journey_sequence,s.segment_sequence
 FROM order_info_issue_segment i JOIN order_info_segment s ON s.id=i.segment_id
 WHERE i.issue_id=%s AND s.order_id=%s AND s.airlift_flag=1
 ORDER BY s.journey_sequence,s.segment_sequence,s.id LIMIT 201"""
AIRPORT_SQL = """SELECT airport_code,city_code,country_code,zone_code,area_code,update_time
 FROM base_airport WHERE airport_code=%s AND status=1 LIMIT 2"""


def enrich_matching_facts(cursor, issue, order, cache):
    cursor.execute(SEGMENTS_SQL,(issue['id'],order['id']))
    rows=_rows(cursor)
    facts={};problems={}
    fields={'cabin':'cabin','cabin_grade':'cabin_grade','flight_number':'flight_number',
            'origin':'dep_airport','destination':'arr_airport'}
    complete=bool(rows) and len(rows)<=200 and len(rows)==issue.get('segmentCount') and len({str(row['id']) for row in rows})==len(rows)
    for target,source in fields.items():
        if target in ('origin','destination'):
            # User-confirmed legacy names: these order fields contain main-segment airports.
            source='dep_city' if target=='origin' else 'arr_city'
            values={str(order.get(source) or '')}
            available='' not in values
        else:
            values={str(row.get(source) or '') for row in rows}
            available=complete and '' not in values
        if not available:
            problems[target]=('订单主航段机场缺失：order_info.'+source if target in ('origin','destination') else '单票航段关联不完整或对应字段缺失')
            continue
        if len(values)!=1:
            problems[target]='多航段字段不一致，尚缺原出票调用方选择主航段的可靠依据'
            continue
        value=values.pop()
        if target not in ('origin','destination'):
            facts[target]=value
            continue
        airports=cache.setdefault('airports',{})
        if value not in airports:
            cursor.execute(AIRPORT_SQL,(value,));airports[value]=_rows(cursor)
        mapped=airports[value]
        if len(mapped)!=1:
            problems[target]='机场字典缺失或重复：'+value
            continue
        airport=mapped[0]
        codes=[airport.get(key) for key in ('city_code','country_code','zone_code','area_code')]
        if any(not code for code in codes):
            problems[target]='机场地域层级不完整：'+value
            continue
        facts[target]=','.join(['#'+value,*codes])
    issue['matchingFacts']=facts
    issue['matchingFactProblems']=problems
