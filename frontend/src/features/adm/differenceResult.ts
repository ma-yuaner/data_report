import { h } from 'vue'
import { Modal } from 'ant-design-vue'
import { label, type Fields } from './api'

export function showDifferenceResult(result: Fields, lineId: number) {
  const match = result.match || {}
  const status = String(match.resultStatus || '')
  const matched = ['MATCHED', 'MATCHED_OTA_ORDER', 'MATCHED_LEGACY_ADM_NO', 'MATCHED_LINE_INTERNAL_NO'].includes(status)
  const line = result.caseDetail?.lines?.find((item: Fields) => Number(item.id) === lineId)
  const title = matched ? '差异单匹配成功' : ({
    NOT_MATCHED: '未匹配到差异单', QUERY_FAILED: '差异单查询失败', NOT_CONNECTED: '差异单数据源未接通',
  } as Record<string, string>)[status] || '未取得差异单匹配结果'
  const rows = [
    match.matchedKeyValue ? `匹配依据：${match.matchedKeyValue}` : '',
    matched ? `差异单号：${match.summary?.diffNo || '未返回单号'}` : '',
    matched && match.externalRecordId ? `差异记录 ID：${match.externalRecordId}` : '',
    matched && match.summary?.diffDate ? `差异日期：${match.summary.diffDate}` : '',
    line ? `当前状态：${label(line.lineStatus)}` : '',
    status === 'NOT_MATCHED' ? '暂未查到对应差异单，请核对单号及差异单是否已录入，之后可重新匹配。' : '',
    ['QUERY_FAILED', 'NOT_CONNECTED'].includes(status) ? '本次未完成匹配，订单仍待匹配；请检查差异单数据源后重试。' : '',
  ].filter(Boolean)
  const open = matched ? Modal.success : status === 'QUERY_FAILED' ? Modal.error : Modal.warning
  open({ title, width: 560, content: h('div', rows.map(text => h('p', { style: { overflowWrap: 'anywhere' } }, text))), okText: '知道了' })
}
