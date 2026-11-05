"""Identify segment threshold values; selecting an applicable rule is separate."""
import json
import re
from decimal import Decimal

LOSS_RULE_TYPE = 'RB01003002'
SEGMENT_KEYS = {1:'paramOne',2:'paramTwo',3:'paramThree',4:'paramFour'}


def identify_thresholds(rule_type, raw):
    result={'status':'not_applicable','values':{},'missing':[],'path':'extValue','usedForCalculation':False}
    if rule_type != LOSS_RULE_TYPE:
        return result
    try:
        value=json.loads(raw,parse_float=Decimal) if isinstance(raw,str) else raw
        fields=value['extValue']
        if not isinstance(fields,dict):raise ValueError()
    except (ValueError,TypeError,KeyError):
        return {**result,'status':'invalid','missing':['extValue']}
    for segments,key in SEGMENT_KEYS.items():
        item=fields.get(key)
        if isinstance(item,bool) or not isinstance(item,(str,int,Decimal)) or not re.fullmatch(r'[0-9]{1,20}(?:\.[0-9]{1,12})?',str(item)):
            result['missing'].append(f'extValue.{key}')
        else:result['values'][str(segments)]=format(Decimal(str(item)),'f')
    result['status']='identified' if not result['missing'] else 'incomplete'
    return result


def ticket_threshold(raw, segments):
    if type(segments) is not int or segments < 1:
        return {'status':'insufficient','reason':'缺少可靠的单票航段数'}
    identified=identify_thresholds(LOSS_RULE_TYPE,raw)
    key=str(min(segments,4))
    if key not in identified['values']:
        return {'status':'insufficient','reason':f'配置缺少{min(segments,4)}段有效阈值'}
    from decimal import localcontext
    with localcontext() as context:
        context.prec=64
        base=Decimal(identified['values'][key])
        extra=max(segments-4,0)*Decimal('25')
        amount=base+extra
    return {'status':'ready','amount':format(amount,'f'),'segments':segments,'baseSegments':min(segments,4),
            'baseAmount':format(base,'f'),'extraSegments':max(segments-4,0),'extraPerSegment':'25',
            'jsonPath':f'extValue.{SEGMENT_KEYS[min(segments,4)]}'}
