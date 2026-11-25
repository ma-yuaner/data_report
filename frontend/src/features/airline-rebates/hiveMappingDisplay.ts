// These labels describe the fields used in the HKG26003 policy review.
const fieldLabels: Record<string, string> = {
  segment_dep_time: '航段计划起飞时间',
  issue_ticket_time: '出票时间',
  supplier_code: '供应商',
  issue_ticket_no: '票号',
  segment_airport: '各航段起降机场',
  dep_airport: '始发机场',
  arr_airport: '到达机场',
  segment_marketing_airline: '航段销售航司',
  segment_real_cabin: '航段实际舱位',
  issue_price_type_desc: '出票价格类型说明',
  real_age_type_desc: '旅客年龄类型说明',
  operating_airline: '实际承运航司',
  code_share: '代码共享标记',
  refund_issue_flag: '退改重出标记',
  order_status: '订单状态',
  issue_status: '出票状态',
  issue_ticket_no_status: '票号状态',
  flt_status: '航段状态',
  refund_flag_desc: '退票标记说明',
  issue_ticket_price: '出票票面价',
  issue_currency: '出票币种',
  airport_code: '机场代码',
  country_code: '国家或地区代码',
  issuing_iata: '出票代理 IATA 号',
}

export function hiveFieldLabel(field: string): string {
  return fieldLabels[field] ?? field
}

const conditionLabels: Record<string, string> = {
  'supplier_code = HK_NGCHOW': '按试点指定供应商筛选（HK_NGCHOW）',
  'order_status = TICKETED': '订单状态为已出票',
  'issue_status = I_UPDATED': '出票状态为已更新',
  'issue_currency = HKD': '出票币种为港币',
}

export function formatHiveMapping(mapping?: string): string {
  if (!mapping) return '—'
  return mapping
    .replace(/\b[a-z][a-z_]*\s*=\s*[A-Z_]+\b/g, condition => conditionLabels[condition] ?? condition)
    .replace(/\b[a-z]+(?:_[a-z]+)+\b/g, field => fieldLabels[field] ?? field)
}
