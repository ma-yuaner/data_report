<template>
  <a-empty v-if="!items.length" :description="emptyText" />
  <a-timeline v-else>
    <a-timeline-item v-for="item in [...items].reverse()" :key="item.id">
      <b>{{ eventLabel(item.eventType) }}</b>
      <div>{{ item.operatorName || '系统' }} · {{ formatDateTimeDisplay(item.occurredAt) }}</div>
      <div v-if="item.fromStatus && item.toStatus && item.fromStatus !== item.toStatus">
        {{ label(item.fromStatus) }} → {{ label(item.toStatus) }}
      </div>
      <p v-if="item.operationNote || item.note">{{ item.operationNote || item.note }}</p>
    </a-timeline-item>
  </a-timeline>
</template>

<script setup lang="ts">
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import { label, type Fields } from './api'

defineProps<{ items: Fields[]; emptyText: string }>()

const eventLabel = (value: string) =>
  (
    ({
      MASTER_RECOVERY_SKIP: '无需恢复编码，自动生成明细',
      MASTER_RECOVERY_REQUEST: '提交恢复编码申请',
      MASTER_RECOVERY_START: '负责人标记正在恢复',
      MASTER_RECOVERY_COMPLETED: '48 小时到期，编码已恢复',
      MASTER_LEADER_TRANSFER_REQUESTED: '发起主单组长转派',
      MASTER_LEADER_TRANSFER_ACCEPTED: '接受主单组长转派',
      MASTER_LEADER_TRANSFER_REJECTED: '拒绝主单组长转派',
      CREATE_CASE: '创建主单',
      CREATE_TEST_DATA: '创建测试数据',
      ADD_LINE: '新增订单',
      UPDATE_CASE_BASIC_INFO: '编辑主单基础信息',
      UPDATE_LINE_BASIC_INFO: '编辑订单基础信息',
      UPDATE_OPERATOR_SUPPLEMENT: '补充订单资料',
      UPDATE_INVESTIGATION_NOTE: '更新订单情况说明',
      REBALANCE_LINE_AMOUNT: '调整明细金额',
      PUBLISH_DRAFT: '发布草稿',
      DELETE_DRAFT: '删除草稿',
      ASSIGN_OPERATOR: '分配操作员',
      ACCEPT_LINE: '接单',
      ACCEPT_AND_EXPORT: '接单并导出',
      CHANGE_LEADER: '更换组长',
      REQUEST_TRANSFER: '发起转派',
      TRANSFER_ACCEPTED: '接受转派',
      TRANSFER_REJECTED: '拒绝转派',
      DECIDE_RECOVERY: '判断是否恢复编码',
      RECOVERY_REMINDER_DUE: '恢复编码待查看提醒',
      CONFIRM_RECOVERY: '确认已查看恢复结果',
      START_APPEAL: '开始申诉',
      FINISH_APPEAL: '登记申诉结果',
      RECORD_NO_APPEAL: '登记不申诉',
      SUBMIT_REVIEW: '提交审核',
      REVIEW_APPROVED: '审核通过',
      REVIEW_RETURNED: '审核退回',
      WITHDRAW_REVIEW: '撤回审核',
      CHECK_DIFFERENCE_ORDER: '核验差异单',
      RECORD_COLLECTION: '登记回款',
      VOID_COLLECTION: '作废回款记录',
      CLOSE_CASE: '主单结案',
      VOID_LINE: '作废订单明细',
      VOID_CASE: '作废主单',
      UPLOAD_ATTACHMENT: '上传附件',
      DOWNLOAD_ATTACHMENT: '下载附件',
      VOID_ATTACHMENT: '作废附件',
    }) as Fields
  )[value] || value
</script>
