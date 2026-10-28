import { cents, cash, id, lineSeed, type Case, type Line } from './model'
export const specificTypes = [
  '重复预定',
  '虚假定位',
  '违规定位',
  '退票费用差异',
  '改签费用差异',
  '返点费用差异',
  '其他待核实',
]
export interface IntakeRow {
  orderNo: string
  platform: string
  business: string
  amount: string
  pnr: string
  ticketNo: string
}
export const rowsFromText = (value: string): IntakeRow[] =>
  value
    .split('\n')
    .filter((row) => row.trim())
    .map((row) => {
      const [orderNo = '', platform = '平台A', business = '出票', amount = '', pnr = '', ticketNo = ''] = row.split(',')
      return { orderNo, platform, business, amount, pnr, ticketNo }
    })
export const rowsToText = (rows: IntakeRow[]) =>
  rows.map((row) => [row.orderNo, row.platform, row.business, row.amount, row.pnr, row.ticketNo].join(',')).join('\n')
export function referenceAmount(amount: string, currency: string, rate: string) {
  if (currency === 'CNY') return amount
  if (!/^\d{1,5}(\.\d{1,6})?$/.test(rate) || Number(rate) <= 0) return ''
  const [whole, decimal = ''] = rate.split('.')
  const numerator = BigInt(whole!) * 1000000n + BigInt(decimal.padEnd(6, '0'))
  const value = (BigInt(cents(amount)) * numerator + 500000n) / 1000000n
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw Error('换算超出原型范围')
  return cash(Number(value))
}
export function prepareIntake(value: Record<string, any>, types = specificTypes): Case {
  if ((!value.preliminary && !value.admNo?.trim()) || !value.supplier?.trim() || !value.description?.trim())
    throw Error('正式ADM号、供应商和ADM内容必填')
  if (!['航司', '供应商', '平台'].includes(value.sourceType)) throw Error('请选择来源主体')
  if (!['CNY', 'HKD', 'JPY', 'USD', 'EUR'].includes(value.currency)) throw Error('请选择原币')
  if (
    (!value.preliminary && !value.airline?.trim()) ||
    !/^\d{4}-\d\d-\d\d$/.test(value.issuedOn) ||
    !/^\d{4}-\d\d-\d\d$/.test(value.replyDue)
  )
    throw Error('正式单航司、下发日期和回复截止必填')
  if (value.replyDue < value.issuedOn) throw Error('回复截止不能早于下发日期')
  if (!types.includes(value.diffType)) throw Error('请选择具体错误类型（演练字典）')
  const rows = rowsFromText(value.rows || '')
  if (
    String(value.rows)
      .split('\n')
      .some((row) => row.split(',').length > 6)
  )
    throw Error('子项字段请勿使用英文逗号；多票号请用分号')
  if ((!value.preliminary && !rows.length) || rows.length > 20) throw Error('正式单请录入1–20条订单子项')
  const seen = new Set<string>()
  const parent: Case = {
    id: id(),
    admNo: value.admNo?.trim() || `PRE-${id()}`,
    supplier: value.supplier.trim(),
    amount: value.amount,
    description: value.description.trim(),
    remark: value.remark || '',
    currency: value.currency,
    sourceType: value.sourceType,
    airline: value.airline,
    issuedOn: value.issuedOn,
    replyDue: value.replyDue,
    referenceCny: referenceAmount(value.amount, value.currency, value.rate || ''),
    preliminary: value.preliminary === true,
    status: 'ACTIVE',
    paused: false,
    lines: [],
    files: [],
    source: '单条录入（合成演练）',
    remediation: { owner: 'handlerB', status: '未开始', result: '' },
  }
  if (value.preliminary && !rows.length)
    rows.push({ orderNo: '', platform: '平台A', business: '出票', amount: value.amount, pnr: '', ticketNo: '' })
  if (value.currency !== 'CNY' && value.rate && !parent.referenceCny)
    throw Error('参考汇率格式无效，请填写正数、最多6位小数，或留空')
  parent.lines = rows.map((row, index) => {
    if (!['平台A', '平台B'].includes(row.platform) || !['出票', '退票', '改签'].includes(row.business))
      throw Error(`第${index + 1}项平台或业务无效`)
    if (!row.orderNo.trim() && !value.preliminary) throw Error(`第${index + 1}项缺订单号，请先核实；无票号可留空`)
    if (Object.values(row).some((text) => /[\r\n,]/.test(text))) throw Error('子项字段不能包含逗号或换行')
    const tickets = row.ticketNo.split(/[;；、\s]+/).filter(Boolean)
    for (const ticket of tickets) {
      if (seen.has(`ticket:${ticket}`)) throw Error('存在重复票号，请核对子项')
      seen.add(`ticket:${ticket}`)
    }
    const key = `${row.orderNo}|${row.platform}|${row.business}`
    if (seen.has(key)) throw Error('订单/平台/业务子项重复')
    seen.add(key)
    cents(row.amount)
    const line: Line = {
      ...lineSeed(index + 1),
      ...row,
      id: id(),
      stage: 'ACCEPT',
      owner: 'lead',
      supervisor: 'lead',
      evidence: [] as string[],
      description: parent.description,
      diffType: value.diffType,
      diffSecond: '',
      dueAt: `${value.replyDue}T18:00`,
      financeReason: '不涉及回款，需由审核人员核对',
    }
    const fileId = id()
    if (!row.orderNo.trim()) {
      line.stage = 'MATCH'
      line.owner = 'coordinator'
      line.matchReason = '预罚暂未关联订单，待人工核实'
    }
    line.evidence.push(fileId)
    parent.files.push({
      id: fileId,
      name: `子项${index + 1}-录入摘要.txt`,
      category: '录入摘要',
      lineId: line.id,
      shared: [],
      content: `仅合成录入摘要，正式办理须补真实证据。\n${parent.description}\n${row.orderNo} / ${row.ticketNo || '无票号'}`,
    })
    return line
  })
  if (parent.lines.reduce((total, line) => total + cents(line.amount), 0) !== cents(parent.amount))
    throw Error('子项合计与主单原币金额不一致，请核对，不自动平摊')
  parent.files.push({
    id: id(),
    name: 'ADM内容-演练.txt',
    category: '下发原件',
    lineId: '',
    shared: [],
    content: `仅合成原件占位，非真实上传。\n${parent.description}`,
  })
  return parent
}
