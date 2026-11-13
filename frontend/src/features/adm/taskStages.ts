import type { Fields } from './api'

export const taskStages: Record<string, string> = {
  assignLeader: '待分配组长', leaderRecovery: '待恢复判断', ownerRecovery: '待 GDS 操作',
  recovering: '正在恢复', recovered: '已恢复待录入', assign: '待派单操作员',
  accept: '待接单', process: '本人待办理', appeal: '申诉中', review: '待审核',
  diff: '待匹配差异单', collection: '待回款跟进', transferAccept: '待确认转派',
  masterTransferWait: '等待组长确认转派', masterLeaderFollowup: '等待负责人恢复操作',
  leaderFollowup: '组长负责订单', codeReminder: '编码恢复提醒', soon: '即将超时', late: '已超时',
}

export function matchesTaskStage(task: Fields, stage: string, now = Date.now()) {
  if (!stage) return true
  if (stage === 'appeal') return task.kind === 'process' && task.appealStatus === 'IN_PROGRESS'
  if (stage === 'codeReminder') return task.kind === 'process' && task.recoveryStatus === 'REMINDER_DUE'
  if (stage === 'soon' || stage === 'late') {
    if (!task.deadline) return false
    const remaining = new Date(task.deadline).getTime() - now
    return stage === 'late' ? remaining < 0 : remaining >= 0 && remaining < 86400000
  }
  return task.kind === stage
}
