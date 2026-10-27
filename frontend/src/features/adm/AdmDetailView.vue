<template>
  <div class="page-wrap adm-center">
    <div class="adm-heading">
      <div>
        <router-link to="/adm/cases">← ADM 台账</router-link>
        <h1>{{ record?.admNo || 'ADM 详情' }}</h1>
        <p v-if="record">
          {{ record.supplierName }} · {{ label(record.status) }} · 版本 {{ record.version
          }}<span v-if="record.partial"> · 仅展示获授权明细</span>
        </p>
      </div>
      <a-space wrap
        ><a-button v-if="permission('export') && record" @click="exportCurrent">导出明细</a-button
        ><a-button :loading="loading" @click="load">刷新已保存记录</a-button
        ><a-button v-if="allowed(record, 'edit')" @click="editCase">编辑主单</a-button
        ><a-button
          v-for="action in caseActions"
          :key="action"
          :danger="['void', 'close'].includes(action)"
          :disabled="busy"
          @click="openAction(action)"
          >{{ actionLabels[action] }}</a-button
        ><a-button
          v-if="record && !record.partial && !record.historicalArchive"
          :loading="checking"
          @click="checkClosure"
          >检查结案条件</a-button
        ></a-space
      >
    </div>
    <a-alert v-if="error" type="error" :message="error" show-icon style="margin-bottom: 12px" />
    <a-alert
      v-if="conflict"
      type="warning"
      message="已发生并发冲突，编辑草稿已保留。刷新详情后请重新打开并核对草稿，不能直接覆盖其他人的修改。"
      show-icon
      style="margin-bottom: 12px"
    />
    <a-spin :spinning="loading">
      <template v-if="record">
        <a-alert
          v-if="record.historicalArchive"
          type="info"
          show-icon
          style="margin-bottom: 12px"
          :message="`历史只读档案 · ERP旧ID ${record.history?.oldId || '—'} · 原处理状态 ${record.history?.originalStatusLabel || record.history?.originalStatus || '未填写'}`"
          description="原系统状态完整保留，不表示中台重新审核、付款或办结。旧锁不继承；需要继续办理请引用新建。附件须另行补传，不自动下载旧URL。"
        />
        <a-alert
          v-if="record.partial"
          type="info"
          message="当前仅可查看获授权明细，主单总金额、私密备注和部分材料已隐藏。"
          show-icon
          style="margin-bottom: 12px"
        />
        <a-alert
          v-if="record.paused"
          type="warning"
          :message="`主单已挂起：${record.pauseReason || record.reason || '查看时间线了解原因'}`"
          show-icon
        />
        <a-alert v-if="record.voided" type="warning" message="主单已作废，保留历史供追溯。" show-icon />
        <a-descriptions bordered size="small" :column="{ xs: 1, sm: 2, lg: 3 }" class="adm-summary">
          <a-descriptions-item label="下发方">{{ record.supplierName }}</a-descriptions-item
          ><a-descriptions-item label="原始金额"
            ><span class="adm-money"
              >{{ record.originalAmount ?? '—' }} {{ record.currency }}</span
            ></a-descriptions-item
          ><a-descriptions-item label="截止日期">{{ record.deadline || '未设置' }}</a-descriptions-item>
          <a-descriptions-item label="下发日期">{{ record.issuedDate || '—' }}</a-descriptions-item
          ><a-descriptions-item label="明细进度"
            >{{ record.completedCount ?? 0 }} / {{ record.lineCount ?? record.lines?.length ?? 0 }}</a-descriptions-item
          ><a-descriptions-item label="最近更新">{{ record.updatedAt || '—' }}</a-descriptions-item>
          <a-descriptions-item label="问题描述" :span="3"
            ><span class="adm-prose">{{ record.description || '尚未填写' }}</span></a-descriptions-item
          ><a-descriptions-item v-if="!record.partial" label="主单备注" :span="3"
            ><span class="adm-prose">{{ record.remark || '—' }}</span></a-descriptions-item
          >
        </a-descriptions>
        <a-descriptions
          v-if="!record.partial"
          bordered
          size="small"
          :column="{ xs: 1, sm: 2, lg: 3 }"
          class="adm-summary"
        >
          <a-descriptions-item label="下发方编码">{{ record.supplierCode || '—' }}</a-descriptions-item>
          <a-descriptions-item label="航司">{{ record.airline || '—' }}</a-descriptions-item>
          <a-descriptions-item label="原票号数量">{{ record.ticketCount ?? '—' }}</a-descriptions-item>
          <a-descriptions-item label="人民币金额">{{ record.originalAmountCny ?? '—' }}</a-descriptions-item>
          <a-descriptions-item label="业务大类">{{
            businessCategoryLabels[String(record.businessCategory)] || '待分类'
          }}</a-descriptions-item>
        </a-descriptions>
        <details v-if="record.history && !record.partial" class="adm-record">
          <summary>历史原始字段（完整保留，未核验）</summary>
          <dl>
            <template v-for="(value, key) in record.history.fields" :key="key"
              ><dt>{{ key }}</dt>
              <dd class="adm-prose">{{ value ?? 'NULL' }}</dd></template
            >
          </dl>
        </details>
        <a-tabs v-model:active-key="tab">
          <a-tab-pane v-if="!record.historicalArchive" key="workflow" tab="责任与流转">
            <a-select
              v-model:value="selectedLineId"
              :options="
                record.lines.map((line) => ({
                  value: line.id,
                  label: `${line.platform || '待核实平台'} · ${line.orderNo || line.id}`,
                }))
              "
              placeholder="选择订单明细查看流转"
              style="width: 100%; max-width: 600px"
              allow-clear
            />
            <WorkflowPanel ref="workflowPanel" :record="record" :line="selectedLine" :config="config" @changed="load" />
            <CollaborationPanel
              ref="collaborationPanel"
              :record="record"
              :line="selectedLine"
              :config="config"
              @changed="load"
              @attachments="showAttachments"
            />
          </a-tab-pane>
          <a-tab-pane v-if="record.source && !record.history && !record.partial" key="source" tab="原始导入字段">
            <p class="adm-muted">原始字段留存，不代表已核实或已完成；处理状态以当前流程为准。</p>
            <dl>
              <template v-for="(value, key) in record.source.fields" :key="key"
                ><dt>{{ key }}</dt>
                <dd class="adm-prose">{{ value ?? 'NULL' }}</dd></template
              >
            </dl>
          </a-tab-pane>
          <a-tab-pane key="lines" tab="订单明细与处理">
            <div class="adm-toolbar">
              <strong>多平台 / 出退改订单明细</strong
              ><a-button v-if="allowed(record, 'addLine')" type="primary" @click="editLine()">添加订单明细</a-button
              ><a-button
                v-if="permission('assign') && !record.historicalArchive"
                :disabled="!selectedOrders.length || busy"
                @click="bulkOpen = true"
                >批量分配 {{ selectedOrders.length || '' }}</a-button
              ><span class="adm-muted">点击订单展开完整描述、分析和处理记录。</span>
            </div>
            <a-table
              row-key="id"
              :columns="lineColumns"
              :data-source="record.lines || []"
              :row-selection="orderSelection"
              :pagination="false"
              :scroll="{ x: 1670, y: 'calc(100vh - 500px)' }"
              size="small"
            >
              <template #bodyCell="{ column, record: line }">
                <template v-if="column.key === 'orderNo'"
                  ><a-button type="link" size="small" @click="selectedLineId = line.id">{{
                    line.orderNo || '待关联订单'
                  }}</a-button></template
                >
                <template v-else-if="column.key === 'businessType'">{{ label(line.businessType) }}</template>
                <template v-else-if="column.key === 'status'"
                  ><a-tag>{{ label(line.status) }}</a-tag></template
                >
                <template v-else-if="column.key === 'amount'"
                  ><span class="adm-money">{{ line.amount ?? '—' }} {{ line.currency }}</span></template
                >
                <template v-else-if="column.key === 'owner'">{{ line.ownerName || line.ownerId || '未分配' }}</template>
                <template v-else-if="column.key === 'actions'"
                  ><a-space
                    ><a-button size="small" @click="selectedLineId = line.id">查看处理</a-button
                    ><a-button v-if="lineAllowed(line, 'edit')" size="small" @click="editLine(line)"
                      >编辑分析</a-button
                    ></a-space
                  ></template
                >
              </template>
              <template #emptyText><a-empty description="尚无订单明细，请先添加或批量导入" /></template>
            </a-table>
            <section v-if="selectedLine" class="adm-line-detail">
              <div class="adm-heading">
                <div>
                  <h2>{{ selectedLine.platform || '待核实平台' }} · {{ selectedLine.orderNo || selectedLine.id }}</h2>
                  <p>
                    {{ label(selectedLine.businessType) }} · {{ label(selectedLine.status) }} ·
                    {{ label(selectedLine.matchStatus) }}
                  </p>
                </div>
                <a-button @click="selectedLineId = ''">收起明细</a-button>
                <a-button v-if="!record.historicalArchive" @click="tab = 'workflow'">责任计划与交接</a-button>
              </div>
              <div class="adm-toolbar">
                <a-button v-if="lineAllowed(selectedLine, 'edit')" @click="editLine(selectedLine)"
                  >编辑描述与分析</a-button
                ><a-button
                  v-for="action in lineActions"
                  :key="action"
                  :disabled="busy"
                  @click="openAction(action, selectedLine)"
                  >{{ actionLabels[action] }}</a-button
                >
              </div>
              <a-descriptions bordered :column="{ xs: 1, sm: 2, lg: 3 }" size="small">
                <a-descriptions-item v-for="field in lineInfo" :key="field[0]" :label="field[1]">{{
                  selectedLine[field[0]] ?? '—'
                }}</a-descriptions-item>
                <a-descriptions-item label="问题描述" :span="3"
                  ><span class="adm-prose">{{ selectedLine.description || '未填写' }}</span></a-descriptions-item
                ><a-descriptions-item label="差异说明" :span="3"
                  ><span class="adm-prose">{{
                    selectedLine.differenceDescription || '未填写'
                  }}</span></a-descriptions-item
                ><a-descriptions-item label="明细备注" :span="3"
                  ><span class="adm-prose">{{ selectedLine.remark || '—' }}</span></a-descriptions-item
                >
                <a-descriptions-item v-for="field in analysisFields" :key="field[0]" :label="field[1]" :span="3"
                  ><span class="adm-prose">{{
                    selectedLine.analysis?.[field[0]] || '待补充'
                  }}</span></a-descriptions-item
                >
              </a-descriptions>
              <div class="adm-record-grid">
                <section>
                  <h3>编码恢复</h3>
                  <a-empty v-if="!selectedLine.recoveries?.length" description="尚无恢复记录" />
                  <div v-for="(item, index) in selectedLine.recoveries" :key="item.id || index" class="adm-record">
                    <a-tag>{{ recoveryStatuses.find((s) => s.value === item.status)?.label || item.status }}</a-tag>
                    <p>{{ item.code }} → {{ item.resultCode || '待恢复' }}</p>
                    <p>{{ item.reason || '—' }}</p>
                    <p class="adm-muted">{{ item.system }} / {{ item.pcc }} · {{ item.updatedAt || item.createdAt }}</p>
                    <a-button v-if="lineAllowed(selectedLine, 'recovery')" size="small" @click="editRecovery(item)"
                      >更新此恢复任务</a-button
                    >
                  </div>
                </section>
                <section>
                  <h3>多对象申诉</h3>
                  <a-empty v-if="!selectedLine.appeals?.length" description="尚无申诉记录" />
                  <div v-for="(item, index) in selectedLine.appeals" :key="item.id || index" class="adm-record">
                    <a-tag
                      >{{ item.targetName }} ·
                      {{ appealTargets.find((t) => t.value === item.targetType)?.label || item.targetType }}</a-tag
                    ><a-tag>{{ appealStatuses.find((s) => s.value === item.status)?.label || item.status }}</a-tag>
                    <p>{{ item.reason }}</p>
                    <p class="adm-money">减免金额：{{ item.waivedAmount ?? '—' }} {{ item.currency }}</p>
                    <p class="adm-muted">第 {{ item.round }} 轮 · {{ item.at }}</p>
                  </div>
                </section>
                <section>
                  <h3>差异登记与核验</h3>
                  <p>
                    登记状态：{{
                      differenceStatuses.find((s) => s.value === selectedLine?.difference?.declaration)?.label ||
                      '未登记'
                    }}
                  </p>
                  <p>
                    系统核验：{{
                      selectedLine.difference?.verification === 'NOT_CONNECTED'
                        ? '未接入'
                        : selectedLine.difference?.verification || '未核验'
                    }}
                  </p>
                  <p>关联编号：{{ selectedLine.difference?.reference || '—' }}</p>
                  <p class="adm-prose">{{ selectedLine.difference?.reason || '尚无登记说明' }}</p>
                  <p>证据附件：{{ selectedLine.difference?.evidence?.length || 0 }} 份（原件与附件页查看）</p>
                </section>
                <section>
                  <h3>财务与结案归因</h3>
                  <p>财务状态：{{ selectedLine.finance?.status || '未确认' }}</p>
                  <p>凭证编号：{{ selectedLine.finance?.reference || '—' }}</p>
                  <p class="adm-money">
                    确认金额：{{ selectedLine.finance?.amount ?? '—' }} {{ selectedLine.finance?.currency }}
                  </p>
                  <p>原因归属：{{ selectedLine.attribution || '待填写' }}</p>
                </section>
              </div>
            </section>
          </a-tab-pane>
          <a-tab-pane v-if="!record.partial" key="analysis" tab="主单描述与分析">
            <a-descriptions bordered size="small" :column="1">
              <a-descriptions-item v-for="field in analysisFields" :key="field[0]" :label="field[1]"
                ><span class="adm-prose">{{ record.analysis?.[field[0]] || '待补充' }}</span></a-descriptions-item
              >
            </a-descriptions>
          </a-tab-pane>
          <a-tab-pane key="attachments" tab="原件与附件"
            ><AttachmentPanel
              :record="record"
              :config="config"
              :can-upload="allowed(record, 'upload') || Boolean(record.lines?.some((line) => allowed(line, 'upload')))"
              @changed="load"
          /></a-tab-pane>
          <a-tab-pane key="closure" tab="结案检查"
            ><a-button :loading="checking" @click="checkClosure">重新检查</a-button
            ><template v-if="closure"
              ><a-alert
                :type="closure.canClose ? 'success' : 'warning'"
                :message="closure.canClose ? '当前满足结案条件，可提交结案' : '尚未满足结案条件，请补充以下事项'"
                show-icon
                style="margin: 12px 0" />
              <p v-if="closure.amounts" class="adm-money">
                {{ closure.amounts.currency }} · 原金额 {{ closure.amounts.originalAmount ?? '—' }} · 已分配
                {{ closure.amounts.allocatedAmount ?? '—' }} · 未核平 {{ closure.amounts.gap ?? '—' }}
              </p>
              <ul>
                <li v-for="check in closure.checks" :key="`${check.code}-${check.lineId || ''}`">
                  {{ check.passed ? '✓ 已满足' : '✕ 待处理' }}：{{ check.label }}
                  <a-button v-if="check.lineId" size="small" type="link" @click="showClosureLine(check.lineId)"
                    >查看明细</a-button
                  >
                </li>
              </ul>
              <a-alert
                v-for="(blocker, i) in closure.blockers"
                :key="i"
                type="warning"
                :message="blocker"
                style="margin: 8px 0"
            /></template>
            <p v-else class="adm-muted">检查原件、必要分析、明细、审核、财务及金额核平状态后再结案。</p></a-tab-pane
          >
          <a-tab-pane key="timeline" tab="完整操作历史"
            ><a-button :loading="historyLoading" @click="loadHistory">刷新历史</a-button
            ><a-empty v-if="!timeline.length" description="暂无可展示历史" />
            <ol class="adm-history">
              <li v-for="(event, i) in timeline" :key="event.id || i">
                <strong>{{ event.label || actionLabels[event.action] || event.action || event.type }}</strong
                ><span class="adm-muted">
                  {{ event.createdAt || event.at }} · {{ event.actorName || event.userName || event.actorId }}</span
                >
                <p class="adm-prose">{{ event.description || event.reason || event.message || '' }}</p>
                <details v-if="event.before || event.after || event.details || event.detail">
                  <summary>查看变更内容</summary>
                  <pre>{{
                    JSON.stringify(
                      { before: event.before, after: event.after, details: event.details || event.detail },
                      null,
                      2,
                    )
                  }}</pre>
                </details>
              </li>
            </ol></a-tab-pane
          >
        </a-tabs>
      </template>
      <a-empty v-else-if="!loading" :description="error ? '详情加载失败，可刷新重试' : '未找到 ADM'" />
    </a-spin>
    <FormDialog
      v-model:open="caseOpen"
      title="编辑主单"
      :busy="busy"
      :dirty="JSON.stringify(caseDraft) !== caseBaseline"
      :error="formError"
      :submit-disabled="conflict"
      @submit="saveCase"
      ><CaseFields v-model="caseDraft" /><DraftComparison :latest="reviewRecord" :draft="caseDraft" /><a-button
        v-if="conflict"
        :loading="loading"
        @click="rebaseDraft"
        >载入最新记录，保留草稿并对照</a-button
      ></FormDialog
    >
    <a-drawer
      v-model:open="lineOpen"
      :title="lineEditId ? '编辑明细及完整分析' : '添加订单明细'"
      width="min(860px, 96vw)"
      :mask-closable="false"
      :destroy-on-close="false"
      ><a-alert v-if="formError" type="error" :message="formError" show-icon style="margin-bottom: 12px" /><LineFields
        v-model="lineDraft"
        :config="config"
      /><DraftComparison :latest="reviewRecord" :draft="lineDraft" /><template #footer
        ><a-space
          ><a-button @click="lineOpen = false">保留草稿并关闭</a-button
          ><a-button type="primary" :loading="busy" :disabled="conflict" @click="saveLine">保存明细</a-button
          ><span v-if="conflict">刷新并重新核对后保存</span></a-space
        ><a-button v-if="conflict" :loading="loading" @click="rebaseDraft"
          >载入最新记录，保留草稿并对照</a-button
        ></template
      ></a-drawer
    >
    <a-modal
      v-model:open="actionOpen"
      :title="actionLabels[currentAction]"
      :confirm-loading="busy"
      :mask-closable="false"
      :width="680"
      @ok="performAction"
    >
      <a-alert v-if="formError" type="error" :message="formError" show-icon style="margin-bottom: 12px" />
      <p>
        目标：{{ actionLine ? `${actionLine.platform || ''} ${actionLine.orderNo || actionLine.id}` : record?.admNo }}
      </p>
      <div class="adm-form-grid">
        <template v-if="currentAction === 'assign'"
          ><label
            >处理人 <span class="required">*</span
            ><AccountSelect
              v-model="actionDraft.ownerId"
              :options="assigneePeople"
              placeholder="选择已获ADM权限的人员" /></label
        ></template>
        <template v-if="currentAction === 'recovery'"
          ><label>恢复状态<a-select v-model:value="actionDraft.status" :options="recoveryStatuses" /></label
          ><label>原编码<a-input v-model:value="actionDraft.code" /></label
          ><label>系统<a-input v-model:value="actionDraft.system" /></label
          ><label>PCC<a-input v-model:value="actionDraft.pcc" /></label
          ><label>恢复后编码<a-input v-model:value="actionDraft.resultCode" /></label
        ></template>
        <template v-if="currentAction === 'appeal'"
          ><label>申诉对象类型<a-select v-model:value="actionDraft.targetType" :options="appealTargets" /></label
          ><label
            >申诉主体名称<a-input
              v-model:value="actionDraft.targetName"
              placeholder="具体平台 / 供应商 / 航司" /></label
          ><label>申诉状态<a-select v-model:value="actionDraft.status" :options="appealStatuses" /></label
          ><label
            >减免金额<a-input
              v-model:value="actionDraft.waivedAmount"
              inputmode="decimal"
              placeholder="成功 / 部分成功时必填" /></label
        ></template>
        <template v-if="currentAction === 'difference'"
          ><label>人工登记状态<a-select v-model:value="actionDraft.declaration" :options="differenceStatuses" /></label
          ><label>差异记录编号<a-input v-model:value="actionDraft.reference" /></label
          ><a-alert class="adm-span" type="info" message="人工登记与系统核验分别保存。已录差异不代表已付款或可结案。"
        /></template>
        <template v-if="currentAction === 'finance_confirm'"
          ><label>凭证编号 <span class="required">*</span><a-input v-model:value="actionDraft.reference" /></label
          ><label>确认金额<a-input v-model:value="actionDraft.amount" inputmode="decimal" /></label
          ><label>币种<a-input v-model:value="actionDraft.currency" :maxlength="3" /></label
          ><a-alert class="adm-span" type="info" message="记录为人工财务确认；未接入外部核验时不能冒充系统核验成功。"
        /></template>
        <label v-if="['recovery', 'appeal', 'difference', 'finance_confirm'].includes(currentAction)" class="adm-span"
          >引用证据附件<a-select
            v-model:value="actionDraft.evidence"
            mode="multiple"
            :options="evidenceOptions"
            placeholder="先在原件与附件页上传，再选择证据"
        /></label>
        <a-button
          v-if="actionLine && ['recovery', 'appeal', 'difference', 'finance_confirm'].includes(currentAction)"
          @click="showActionAttachments"
          >先上传附件</a-button
        >
        <label class="adm-span"
          >{{
            ['pause', 'void', 'return', 'reopen', 'unlock', 'approve', 'appeal', 'difference'].includes(currentAction)
              ? '操作原因 / 审核意见（必填）'
              : '操作说明 / 异常原因'
          }}<a-textarea v-model:value="actionDraft.reason" :rows="3"
        /></label>
      </div>
      <a-alert
        v-if="currentAction === 'close'"
        type="warning"
        message="服务端将再次检查全部结案条件；任一未满足将拒绝结案。"
        show-icon
      />
    </a-modal>
    <a-modal
      v-model:open="bulkOpen"
      title="批量分配订单"
      :confirm-loading="busy"
      :mask-closable="false"
      @ok="saveBulkAssign"
    >
      <p>按明细逐条保存并留痕；已有承办人时发起待确认交接，不立即替换责任。部分失败会显示逐项结果。</p>
      <label>处理人<AccountSelect v-model="bulkOwner" :options="assigneePeople" placeholder="选择处理人" /></label>
      <label>分配 / 转单原因<a-textarea v-model:value="bulkReason" :rows="2" /></label>
      <label>交接摘要（涉及已分配订单时必填）<a-textarea v-model:value="bulkSummary" :rows="3" /></label>
      <a-alert v-if="bulkError" type="error" :message="bulkError" style="margin-top: 12px" />
    </a-modal>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import {
  admApi,
  allowed,
  errorText,
  label,
  type AdmCase,
  type AdmConfig,
  type AdmLine,
  type ClosureCheck,
  type Fields,
} from './api'
import CaseFields from './CaseFields.vue'
import FormDialog from '@/components/FormDialog.vue'
import AccountSelect from '@/components/AccountSelect.vue'
import WorkflowPanel from './WorkflowPanel.vue'
import CollaborationPanel from './CollaborationPanel.vue'
import LineFields from './LineFields.vue'
import AttachmentPanel from './AttachmentPanel.vue'
import DraftComparison from './DraftComparison.vue'
import './adm.css'
const route = useRoute(),
  auth = useAuthStore()
const businessCategoryLabels: Record<string, string> = { '0': '票务', '1': '业务', '2': '客服' }
const selectedOrders = ref<string[]>([]),
  bulkOpen = ref(false),
  bulkOwner = ref(''),
  bulkReason = ref(''),
  bulkSummary = ref(''),
  bulkError = ref('')
const orderSelection = computed(() =>
  permission('assign') && record.value && !record.value.historicalArchive
    ? {
        selectedRowKeys: selectedOrders.value,
        onChange: (keys: (string | number)[]) => {
          selectedOrders.value = keys.map(String)
        },
        getCheckboxProps: (line: AdmLine) => ({ disabled: !lineAllowed(line, 'assign') }),
      }
    : undefined,
)
async function saveBulkAssign() {
  if (busy.value || !record.value || !bulkOwner.value.trim()) return
  const caseId = id.value
  busy.value = true
  bulkError.value = ''
  try {
    const result = await admApi.bulkAssign(caseId, {
      version: record.value.version,
      lineIds: selectedOrders.value,
      ownerId: bulkOwner.value.trim(),
      reason: bulkReason.value.trim(),
      summary: bulkSummary.value.trim(),
    })
    if (caseId !== id.value) return
    const failed = (result.items || []).filter((item: Fields) => item.status !== 'SAVED')
    selectedOrders.value = failed.map((item: Fields) => item.lineId)
    if (failed.length)
      bulkError.value =
        `成功${result.successCount}条，失败/未执行${failed.length}条：` +
        failed
          .map((item: Fields) => item.message)
          .slice(0, 5)
          .join('；')
    else {
      bulkOpen.value = false
      message.success(`已保存${result.successCount}条分配/交接请求；已有承办者的订单需接收人确认`)
    }
    await load()
  } catch (cause) {
    bulkError.value = errorText(cause)
  } finally {
    busy.value = false
  }
}
const record = ref<AdmCase | null>(null),
  config = ref<AdmConfig | null>(null),
  loading = ref(false),
  busy = ref(false),
  error = ref(''),
  conflict = ref(false),
  tab = ref('lines')
const id = computed(() => String(route.params.caseId || ''))
const assigneePeople = computed(() => config.value?.people?.handle || config.value?.assignees || [])
const workflowPanel = ref<InstanceType<typeof WorkflowPanel> | null>(null)
const collaborationPanel = ref<InstanceType<typeof CollaborationPanel> | null>(null)
function showAttachments() {
  tab.value = 'attachments'
}
watch(id, () => {
  selectedOrders.value = []
  bulkOpen.value = false
  bulkError.value = ''
})
const selectedLineId = ref(''),
  selectedLine = computed(() => record.value?.lines?.find((item) => item.id === selectedLineId.value) || null)
const permission = (name: string) => Boolean(auth.user?.isAdmin || auth.user?.permissions.includes(`adm.${name}`))
function showClosureLine(lineId: string) {
  selectedLineId.value = lineId
  tab.value = 'lines'
}

function showActionAttachments() {
  actionOpen.value = false
  tab.value = 'attachments'
}

async function exportCurrent() {
  try {
    await useComprehensiveExportStore().createBackground('adm_lines', { caseId: id.value })
    message.success('已进入页头导出任务')
  } catch (cause) {
    message.error(errorText(cause))
  }
}
const lineAllowed = (line: AdmLine, action: string) => allowed(line, action)
const actionLabels: Record<string, string> = {
  publish: '发布主单',
  pause: '挂起',
  resume: '恢复处理',
  void: '作废',
  close: '结案',
  reopen: '重开',
  assign: '分配 / 转单',
  claim: '接单',
  lock: '重新持锁',
  unlock: '解锁',
  submit: '提交审核',
  approve: '审核通过',
  return: '退回处理',
  finance_confirm: '财务确认',
  recovery: '登记编码恢复',
  appeal: '登记申诉',
  difference: '登记差异',
}
const caseActions = computed(() =>
  ['publish', 'pause', 'resume', 'void', 'close', 'reopen'].filter((action) => allowed(record.value, action)),
)
const lineActions = computed(() =>
  [
    'assign',
    'claim',
    'lock',
    'unlock',
    'recovery',
    'appeal',
    'difference',
    'submit',
    'approve',
    'return',
    'finance_confirm',
  ].filter(
    (action) =>
      selectedLine.value &&
      lineAllowed(selectedLine.value, action) &&
      !(action === 'assign' && selectedLine.value.ownerId),
  ),
)
const lineColumns = [
  { title: '订单号', key: 'orderNo', width: 200, fixed: 'left' as const },
  { title: '业务', key: 'businessType', width: 90 },
  { title: '平台', dataIndex: 'platform', width: 130 },
  { title: '店铺 / 站点', dataIndex: 'shop', width: 150 },
  { title: '票号', dataIndex: 'ticketNo', width: 160 },
  { title: 'PNR', dataIndex: 'pnr', width: 100 },
  { title: '状态', key: 'status', width: 130 },
  { title: '金额', key: 'amount', width: 160, align: 'right' as const },
  { title: '处理人', key: 'owner', width: 120 },
  { title: '备注', dataIndex: 'remark', width: 230, ellipsis: true },
  { title: '操作', key: 'actions', width: 200 },
]
const lineInfo = [
  ['platformCode', '平台编码'],
  ['airline', '航司'],
  ['ticketCount', '票号数量'],
  ['amountCny', '人民币分摊金额'],
  ['actualOwner', '实际责任人'],
  ['actualHandler', '实际处理人'],
  ['recoveryDeadline', '编码恢复时限'],
  ['resolution', '处理结果说明'],
  ['shop', '店铺'],
  ['site', '细分站点'],
  ['ticketNo', '票号'],
  ['pnr', 'PNR'],
  ['system', '系统'],
  ['pcc', 'PCC'],
  ['ownerName', '当前处理人'],
  ['diffType', '差异一级分类'],
  ['diffSecondType', '差异二级分类'],
]
const analysisFields = [
  ['facts', '事实核实'],
  ['dispute', '争议点'],
  ['cause', '原因分析'],
  ['proposal', '处理方案'],
  ['conclusion', '最终结论'],
  ['prevention', '改进及预防措施'],
]
let request = 0
async function load() {
  const seq = ++request,
    caseId = id.value
  loading.value = true
  error.value = ''
  try {
    const result = await admApi.detail(caseId)
    if (seq !== request || id.value !== caseId) return
    record.value = result
    closure.value = result.closureCheck || null
    timeline.value = result.timeline || []
    const linkedLineId = String(route.query.lineId || route.params.lineId || '')
    if (linkedLineId && result.lines.some((line) => line.id === linkedLineId)) selectedLineId.value = linkedLineId
    if (!caseOpen.value && !lineOpen.value && !actionOpen.value) conflict.value = false
  } catch (cause) {
    if (seq === request) error.value = errorText(cause)
  } finally {
    if (seq === request) loading.value = false
  }
}
const closure = ref<ClosureCheck | null>(null),
  checking = ref(false),
  timeline = ref<Fields[]>([]),
  historyLoading = ref(false)
async function checkClosure() {
  const caseId = id.value
  checking.value = true
  try {
    const result = await admApi.closure(caseId)
    if (id.value === caseId) {
      closure.value = result
      tab.value = 'closure'
    }
  } catch (cause) {
    error.value = errorText(cause)
  } finally {
    checking.value = false
  }
}
async function loadHistory() {
  const caseId = id.value
  historyLoading.value = true
  try {
    const result = await admApi.timeline(caseId)
    if (id.value === caseId) timeline.value = result
  } catch (cause) {
    error.value = errorText(cause)
  } finally {
    historyLoading.value = false
  }
}
watch(tab, (value) => {
  if (value === 'timeline') void loadHistory()
  if (value === 'closure' && !closure.value) void checkClosure()
})
const caseOpen = ref(false),
  lineOpen = ref(false),
  caseDraft = ref<Fields>({}),
  lineDraft = ref<Fields>({ analysis: {} }),
  formError = ref(''),
  lineEditId = ref('')
let editVersion = 0,
  editCaseId = '',
  lineBaseline = '',
  caseBaseline = ''
const lineDraftCache = new Map<string, { draft: Fields; version: number; baseline: string }>()
const reviewRecord = ref<Fields | null>(null)
function editCase() {
  if (!record.value) return
  caseDraft.value = Object.fromEntries(
    [
      'admNo',
      'supplierName',
      'supplierType',
      'supplierCode',
      'airline',
      'ticketCount',
      'originalAmountCny',
      'businessCategory',
      'currency',
      'originalAmount',
      'issuedDate',
      'deadline',
      'description',
      'remark',
      'analysis',
    ].map((key) => [key, record.value![key]]),
  )
  caseDraft.value.analysis = JSON.parse(JSON.stringify(record.value.analysis || {}))
  editVersion = record.value.version
  editCaseId = record.value.id
  caseBaseline = JSON.stringify(caseDraft.value)
  formError.value = ''
  reviewRecord.value = null
  conflict.value = false
  caseOpen.value = true
}
function editLine(line?: AdmLine) {
  if (!record.value) return
  lineEditId.value = line?.id || ''
  const cached = lineDraftCache.get(lineEditId.value)
  lineDraft.value = cached
    ? structuredClone(cached.draft)
    : JSON.parse(
        JSON.stringify(
          line || {
            businessType: 'ISSUE',
            currency: record.value.currency,
            amount: '',
            matchStatus: 'UNVERIFIED',
            analysis: {},
          },
        ),
      )
  lineDraft.value.analysis ||= {}
  lineDraft.value.finance ||= { required: true, reason: '' }
  lineDraft.value.appealDecision ||= 'UNDECIDED'
  lineDraft.value.recoveryRequired ||= false
  editVersion = record.value.version
  editCaseId = record.value.id
  lineBaseline = cached?.baseline || JSON.stringify(lineDraft.value)
  formError.value =
    cached && cached.version !== record.value.version
      ? '恢复了未保存草稿，记录版本已有变化，请对照最新详情核对后保存。'
      : ''
  conflict.value = false
  lineOpen.value = true
  reviewRecord.value = cached && cached.version !== record.value.version ? line || null : null
}
watch(
  lineOpen,
  (open) => {
    if (!open && lineDraft.value)
      lineDraftCache.set(lineEditId.value, {
        draft: JSON.parse(JSON.stringify(lineDraft.value)),
        version: editVersion,
        baseline: lineBaseline,
      })
  },
  { flush: 'sync' },
)
async function mutate(operation: () => Promise<unknown>, close: () => void) {
  if (busy.value) return
  busy.value = true
  formError.value = ''
  const caseId = id.value
  try {
    await operation()
    if (caseId !== id.value) return
    close()
    message.success('操作已保存')
    await load()
  } catch (cause) {
    if (caseId === id.value) {
      formError.value = errorText(cause)
      if ((cause as { code?: string }).code === 'ADM_VERSION_CONFLICT') conflict.value = true
    }
  } finally {
    busy.value = false
  }
}
function saveCase() {
  if (conflict.value) return
  if (!caseDraft.value.admNo || !caseDraft.value.supplierName) {
    formError.value = 'ADM 单号和下发方必填'
    return
  }
  return mutate(
    () => admApi.update(editCaseId, { ...caseDraft.value, version: editVersion }),
    () => {
      caseBaseline = JSON.stringify(caseDraft.value)
      caseOpen.value = false
    },
  )
}
async function rebaseDraft() {
  if (!record.value) return
  const previousVersion = record.value.version
  await load()
  if (!record.value || record.value.version < previousVersion || error.value) return
  editVersion = record.value.version
  editCaseId = record.value.id
  reviewRecord.value = lineOpen.value
    ? record.value.lines.find((line) => line.id === lineEditId.value) || {}
    : record.value
  conflict.value = false
  formError.value = '已加载最新记录并保留草稿，请核对下方差异后再保存；保存会采用当前草稿内容。'
}
function saveLine() {
  if (conflict.value) return
  return mutate(
    () =>
      lineEditId.value
        ? admApi.updateLine(editCaseId, lineEditId.value, { ...lineDraft.value, version: editVersion })
        : admApi.addLine(editCaseId, { ...lineDraft.value, version: editVersion }),
    () => {
      lineBaseline = JSON.stringify(lineDraft.value)
      lineOpen.value = false
      lineDraftCache.delete(lineEditId.value)
    },
  )
}
const actionOpen = ref(false),
  currentAction = ref(''),
  actionLine = ref<AdmLine | null>(null),
  actionDraft = ref<Fields>({})
const recoveryStatuses = ['PENDING', 'PROCESSING', 'COMPLETED', 'EXCEPTION'].map((value, index) => ({
  value,
  label: ['待恢复', '恢复中', '恢复完成', '恢复异常'][index],
}))
const appealTargets = ['PLATFORM', 'SUPPLIER', 'AIRLINE'].map((value, index) => ({
  value,
  label: ['平台', '供应商', '航司'][index],
}))
const appealStatuses = ['DRAFT', 'SUBMITTED', 'NEED_INFO', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED', 'WITHDRAWN'].map(
  (value, index) => ({
    value,
    label: ['待申诉', '已提交', '待补材料', '申诉成功', '部分成功', '申诉失败', '已撤销'][index],
  }),
)
const differenceStatuses = ['UNDECLARED', 'MANUAL_DECLARED', 'NOT_REQUIRED'].map((value, index) => ({
  value,
  label: ['未录差异', '已录差异', '无需录入'][index],
}))
function openAction(action: string, line?: AdmLine) {
  if (!record.value) return
  currentAction.value = action
  actionLine.value = line || null
  actionDraft.value = {
    reason: '',
    status: action === 'appeal' ? 'SUBMITTED' : 'COMPLETED',
    targetType: 'PLATFORM',
    targetName: '',
    code: line?.pnr || '',
    system: line?.system || '',
    pcc: line?.pcc || '',
    evidence: [],
    declaration: 'MANUAL_DECLARED',
    currency: line?.currency || record.value.currency,
    amount: line?.amount || '',
  }
  editVersion = record.value.version
  editCaseId = record.value.id
  formError.value = ''
  actionOpen.value = true
}
const evidenceOptions = computed(() =>
  (record.value?.attachments || [])
    .filter((file) => !file.lineId || file.lineId === actionLine.value?.id)
    .map((file) => ({ value: file.id, label: `${file.name} · ${file.lineId ? '明细材料' : '主单材料'}` })),
)
function editRecovery(recovery: Fields) {
  if (!selectedLine.value) return
  openAction('recovery', selectedLine.value)
  actionDraft.value = { ...actionDraft.value, ...JSON.parse(JSON.stringify(recovery)), recoveryId: recovery.id }
}
function performAction() {
  if (
    ['pause', 'void', 'return', 'reopen', 'unlock', 'approve', 'appeal', 'difference'].includes(currentAction.value) &&
    !actionDraft.value.reason?.trim()
  ) {
    formError.value = '请填写操作原因'
    return
  }
  if (currentAction.value === 'assign' && !actionDraft.value.ownerId) {
    formError.value = '请选择处理人；名单为空时请先配置ADM账号权限'
    return
  }
  const body = { ...actionDraft.value, version: editVersion, action: currentAction.value }
  return mutate(
    () =>
      actionLine.value ? admApi.lineAction(editCaseId, actionLine.value.id, body) : admApi.action(editCaseId, body),
    () => {
      actionOpen.value = false
    },
  )
}
function clearScope() {
  request++
  record.value = null
  timeline.value = []
  closure.value = null
  selectedLineId.value = ''
  caseOpen.value = false
  lineOpen.value = false
  lineDraftCache.clear()
  actionOpen.value = false
  conflict.value = false
  error.value = ''
  reviewRecord.value = null
}
watch(
  id,
  () => {
    clearScope()
    void load()
  },
  { immediate: true },
)
watch(
  () => auth.user?.id,
  () => {
    clearScope()
    config.value = null
    void loadConfig()
    void load()
  },
)
let configRequest = 0
async function loadConfig() {
  const seq = ++configRequest
  try {
    const result = await admApi.config()
    if (seq === configRequest) config.value = result
  } catch (cause) {
    if (seq === configRequest) error.value = `人员与配置加载失败：${errorText(cause)}`
  }
}
void loadConfig()
function hasUnsavedDraft() {
  return (
    Boolean(workflowPanel.value?.hasUnsavedDraft()) ||
    Boolean(collaborationPanel.value?.hasUnsavedDraft()) ||
    (lineOpen.value && JSON.stringify(lineDraft.value) !== lineBaseline) ||
    (caseOpen.value && JSON.stringify(caseDraft.value) !== caseBaseline) ||
    [...lineDraftCache.values()].some((item) => JSON.stringify(item.draft) !== item.baseline)
  )
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (hasUnsavedDraft()) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeRouteLeave(() => !hasUnsavedDraft() || window.confirm('存在未保存草稿，离开此页将丢失。是否继续？'))
onBeforeRouteUpdate(() => !hasUnsavedDraft() || window.confirm('存在未保存草稿，切换 ADM 将丢失。是否继续？'))
onBeforeUnmount(() => {
  request++
  configRequest++
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>
