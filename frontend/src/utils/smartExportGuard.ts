import { Modal } from 'ant-design-vue'

export const SMART_EXPORT_WARNING_ROWS = 300_000
export const SMART_EXPORT_MAX_ROWS = 900_000

const integer = new Intl.NumberFormat('zh-CN')

export function guardSmartExport(totalRows: number, exportAction: () => Promise<void>) {
  const total = Math.max(0, Number.isFinite(totalRows) ? totalRows : 0)
  if (total > SMART_EXPORT_MAX_ROWS) {
    Modal.warning({
      title: '禁止导出',
      content: `当前匹配 ${integer.format(total)} 条，单次导出上限为 900,000 条。请缩小日期或筛选范围后再导出。`,
      okText: '我知道了',
    })
    return
  }
  if (total > SMART_EXPORT_WARNING_ROWS) {
    Modal.confirm({
      title: '大数据量导出提醒',
      content: `当前将导出 ${integer.format(total)} 条数据，处理时间可能较长，且可能因网络或资源限制导出失败。建议先缩小日期或筛选范围。`,
      okText: '仍然导出',
      cancelText: '缩小范围',
      onOk: exportAction,
    })
    return
  }
  void exportAction()
}
