"""Metadata from used source contracts; registration is not live schema verification."""
CORE_TABLES = [
    {'table': table, 'source': source, 'purpose': purpose, 'grain': grain, 'timeField': clock,
     'verification': '已登记，实际表结构/覆盖及权限待部署环境核验'}
    for table, source, purpose, grain, clock in (
        ('base_issue_match_rule','ERP','出票通用规则及亏损阈值候选；当前配置不代替历史命中','规则ID/版本','start_time/end_time/update_time'),
        ('base_issue_match_log','ERP','规则变更审计；本轮未将日志关联结果当作规则数量','日志ID；business_obj_id关联规则ID','update_time'),
        ('sibe_ota','ERP','平台字典，保留原ota_code','平台编码，唯一性待核验','待核验'),
        ('sibe_ota_site','ERP','平台站点，按平台和站点联合关联','ota_code×ota_site_code，唯一性待核验','待核验'),
        ('system_com_type_det','ERP','亏损原因及规则业务/类型/大类字典','parent_code×det_code，唯一性待核验','待核验'),
        ('order_info','ERP','订单平台与原始亏损原因','内部订单ID','update_time'),
        ('order_info_issue','ERP','出票日期、单票利润、销售佣金','出票明细ID','issue_ticket_time'),
        ('order_info_operator_log','ERP','旧版人工取证历史；V5自动止损不再读取','订单×日志ID','operator_datetime'),
        ('order_info_issue_segment','ERP','单票航段关联，检查重复与无效关联','出票明细ID×航段ID','随明细更新核实'),
        ('order_info_segment','ERP','真实航空航段，以airlift_flag=1核对票段数','航段ID，关联订单ID','随明细更新核实'),
        ('bi_risk_order_day','中台','风控目录及订单去重查询','出票日×订单ID','issue_date/update_time'),
        ('bi_risk_sync_day','中台','目录覆盖和成功同步批次，不是实时数据','出票日','synced_at'),
        ('bi_risk_reason_dict','中台','亏损原因名称映射','parent_code×det_code','etl_run_id'),
        ('bi_risk_auto_results','中台','当前账号自动核实历史结果','账号×订单×结果ID','created/checkedAt'),
        ('bi_risk_auto_samples','中台','个人抽查留痕，不覆盖自动结果','账号×结果×抽查ID','body.at'),
        ('bi_risk_problem_types','中台','管理员共享人工问题分类；新表待部署','类型ID；标准化名称唯一','created_at'),
        ('bi_risk_order_problem_tags','中台','管理员共享订单标签及备注；新表待部署','订单×类型×登记记录','created_at'),
    )
]

RISK_METRICS = [
    {'name': name, 'formula': formula, 'timeField':'所选issue_date；结果须匹配目录批次/源版本及规则版本',
     'stage':'规则核实，非财务利润', 'status':'current', 'businessUse':purpose,
     'source':'bi_risk_order_day + bi_risk_auto_results；抽查另读bi_risk_auto_samples',
     'grain':'所选范围按内部订单ID去重；自动结果按当前账号取最新有效结果', 'unit':unit,
     'deduplication':'跨日保留所选范围内订单最新目录记录，不按票数/日志数累加',
     'nullHandling':'无成功同步批次拒绝汇总；未取得结果不按通过或零问题解释',
     'updateTime':'手动更新并核实成功批次；generatedAt不等于源数据实时更新',
     'permission':'风控核对仅管理员；自动结果/个人抽查按当前账号隔离'}
    for name, formula, unit, purpose in (
        ('待核查订单','COUNT(DISTINCT order_id)，亏损原因有值且目录范围完整','单','确定核查对象数量'),
        ('核实通过订单','最新有效自动结果status=supported的去重订单数','单','展示符合明确规则的订单'),
        ('有问题订单','最新有效自动结果status=problem的去重订单数','单','定位不符合选因条件的订单'),
        ('证据不足订单','最新有效自动结果status=insufficient的去重订单数','单','识别无法下确定性结论的记录'),
        ('执行失败订单','最新有效自动结果status=failed的去重订单数','单','区分技术失败与业务问题'),
        ('已执行核实进度','(supported+problem+insufficient+failed)/total；total=0不适用','%','执行进度，不是通过率或业务闭环'),
        ('人工抽查订单','当前账号每个结果最新抽查的去重结果数','单','观察独立人工抽查，不覆盖自动结论'),
    )
]

RISK_METRICS.append({
    'name':'单票配置止损值','businessUse':'核对RLA013单票选因，非独立点击费计算',
    'formula':'1–4段取extValue.paramOne/Two/Three/Four；超过4段=paramFour+(票段数-4)×25',
    'source':'base_issue_match_rule.ext_json；base_issue_match_log仅还原配置；order_info_issue_segment关联order_info_segment',
    'grain':'出票明细ID（单票）','timeField':'issue_ticket_time时有效配置','unit':'元/CNY',
    'deduplication':'航空航段ID去重数须等于关联行数，重复或无效关联拒绝计算',
    'nullHandling':'段数/阈值缺失、历史断档或匹配不明为证据不足，真实0保留',
    'updateTime':'显式更新并核实的成功批次，配置快照和哈希留痕',
    'permission':'现有管理员；自动结果按当前账号隔离','stage':'规则核实，非财务利润','status':'current'
})
