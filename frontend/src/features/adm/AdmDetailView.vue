<template>
  <div class="v05-app embedded">
    <main class="v05-main">
      <section class="v05-page v05-detail">
        <div class="detail-back-actions">
          <button class="back" @click="router.push('/adm/cases')">← 返回台账</button>
          <button class="back" @click="returnWorkbench">← 返回工作台</button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-bottom: 16px" />
        <a-alert v-if="configError" type="warning" show-icon :message="configError" />
        <a-alert
          v-if="loading && !hasRecord"
          type="info"
          show-icon
          message="正在读取 ADM 主单详情…"
          style="margin-bottom: 16px"
        />
        <div v-if="!caseId" class="v05-card v05-empty">
          <h1>ADM 详情</h1>
          <p>请从 ADM 台账或我的工作台选择要查看的单据。</p>
        </div>
        <button v-else-if="!loading && !hasRecord" @click="() => load()">重试读取详情</button>
        <template v-if="hasRecord">
          <a-alert v-if="record.case.masterRecoveryStatus" type="info" show-icon class="block"
            :message="masterRecoveryText[record.case.masterRecoveryStatus]"
            :description="[record.case.recoveryLocators, record.case.masterRecoveryDueAt].filter(Boolean).join(' · ')" />
          <div v-if="!isLegacyReadOnly" class="detail-page-actions">
            <button :disabled="!canAddLine" class="primary" @click="openAddLine">＋ 新增订单明细</button>
          </div>
          <div class="v05-summary">
            <div>
              <span :class="['pill', statusTone]">● {{ hasRecord ? label(record.case.caseStatus) : '暂无数据' }}</span>
              <span :class="['source-badge', sourceTone(record.case.sourceType)]">{{ sourceText(record.case.sourceType) }}</span>
              <h1>{{ record.case.admNo }}</h1>
              <p>
                <i>{{ label(record.case.issuerType) }}</i> {{ record.case.issuerName }} · 下发于
                {{ record.case.issuedDate || '—' }}
              </p>
              <small>系统记录：{{ record.case.internalNo }} · ADM负责人：{{ record.case.coordinatorName }}</small>
            </div>
            <dl>
              <div>
                <dt>原币总金额</dt>
                <dd>
                  {{ record.case.currency }} {{ record.case.originalAmount
                  }}<small
                    >汇率 {{ record.fxSnapshot?.rateValue || '—' }} · {{ record.fxSnapshot?.rateDate || '—' }}</small
                  >
                </dd>
              </div>
              <div>
                <dt>人民币总金额</dt>
                <dd>{{ hasRecord ? '¥ ' + record.case.cnyAmount : '—' }}</dd>
              </div>
              <div>
                <dt>处理截止</dt>
                <dd>{{ record.case.replyDeadline || '—' }}</dd>
              </div>
              <div>
                <dt>订单完成</dt>
                <dd>{{ completedCount }} / {{ activeLines.length }}</dd>
              </div>
            </dl>
            <div class="summary-actions">
              <a-button @click="openMasterBasicInfo">{{ canEditMasterBasic ? '编辑基础信息' : '查看基础信息' }}</a-button>
              <a-button :loading="loading" @click="openMasterOperations">操作记录</a-button><a-button :disabled="loading" @click="() => load()">刷新</a-button
              ><a-button v-if="isCaseOwner && canCreate && record.case.caseStatus === 'DRAFT'" type="primary" @click="publishDraft">
                发布草稿</a-button
              ><a-button
                v-if="isCaseOwner && (canCreate || canManage) && record.case.caseStatus === 'DRAFT'"
                danger
                @click="openAction('deleteDraft')"
              >
                删除草稿</a-button
              ><a-button v-if="isCaseOwner && canClose && record.case.caseStatus === 'ACTIVE'"
                :disabled="saving || !canCloseCurrentCase" @click="runSimple('close')">
                主单结案</a-button
              ><a-button
                v-if="isCaseOwner && canManage && record.case.caseStatus === 'ACTIVE'"
                danger
                @click="openAction('voidCase')"
              >
                作废主单
              </a-button>
            </div>
          </div>
          <section v-if="isLegacyReadOnly" class="legacy-source-card">
            <header><div><h2>旧系统数据</h2><p>历史只读。以下内容直接来自迁移时封存的原始记录，不使用当前目录或汇率重算。</p></div><span class="pill amber">不进入新系统流程</span></header>
            <details>
              <summary>查看旧系统原始信息</summary>
              <div v-if="record.legacySource" class="legacy-source-body">
                <dl class="legacy-metadata">
                  <div><dt>来源系统 / 表</dt><dd>{{ record.legacySource.sourceSystem || '—' }} / {{ record.legacySource.sourceTable || '—' }}</dd></div>
                  <div><dt>源记录ID</dt><dd>{{ record.legacySource.sourceRecordId ?? '—' }}</dd></div>
                  <div><dt>迁移批次</dt><dd>{{ record.legacySource.migrationBatchNo || '—' }}</dd></div>
                  <div><dt>迁移模式 / 映射状态</dt><dd>{{ record.legacySource.migrationMode || '—' }} / {{ record.legacySource.mappingStatus || '—' }}</dd></div>
                  <div><dt>源负责人 / 处理人</dt><dd>{{ record.legacySource.sourceOwnerText || '—' }} / {{ record.legacySource.sourceHandlerText || '—' }}</dd></div>
                  <div><dt>迁移时间</dt><dd>{{ record.legacySource.migratedAt || '—' }}</dd></div>
                  <div class="wide"><dt>质量说明</dt><dd>{{ record.legacySource.qualityNote || '—' }}</dd></div>
                </dl>
                <section v-for="group in legacyFieldGroups" :key="group.title" class="legacy-field-group">
                  <h3>{{ group.title }}</h3>
                  <dl><div v-for="field in group.fields" :key="field[0]"><dt>{{ field[1] }}</dt><dd>{{ legacyValue(field[0]) }}</dd></div></dl>
                </section>
              </div>
              <a-alert v-else type="warning" show-icon message="未找到该历史主单的旧新映射记录，请联系管理员核对迁移批次。" />
            </details>
          </section>
          <a-alert
            v-if="!hasRecord"
            type="info"
            show-icon
            message="当前新ADM表中还没有主单。请返回ADM台账新建主单并录入第一笔订单；进入已有主单详情后才会显示“新增订单”。"
            style="margin-bottom: 16px"
          />
          <div class="v05-blocker">
            <b>结案阻断</b><span>{{ blockerSummary }}</span
            ><button @click="selectFirstBlocker">查看阻断订单</button>
          </div>
          <div class="v05-metrics compact">
            <button
              v-for="item in stageMetrics"
              :key="item.key"
              :class="{ selected: selectedStage === item.key }"
              @click="selectDetailStage(item.key)"
            >
              <span>{{ item.title }}</span
              ><strong>{{ item.value }}</strong>
            </button>
          </div>
          <div class="v05-detail-grid" style="grid-template-columns: minmax(0, 1fr)">
            <div class="v05-card v05-orders">
              <div class="detail-card-head">
                <div>
                  <h2>{{ record.case.admNo }} · 订单明细（{{ visibleLines.length }}/{{ record.lines.length }}）</h2>
                  <small>清除筛选后显示当前 ADM 下全部订单</small>
                </div>
                <div class="v05-actions">
                  <button v-if="record.case.caseStatus === 'ACTIVE' && selectedIds.length" @click="exportSelected">
                    接单并导出（{{ selectedIds.length }}）
                  </button>
                </div>
              </div>
              <div class="order-filters">
                <a-input v-model:value="lineFilter.q" allow-clear aria-label="搜索订单明细"
                  placeholder="订单号、票号、PNR" style="min-width: 180px; flex: 1" />
                <a-select v-model:value="lineFilter.status" aria-label="明细状态" style="width: 155px"
                  :options="[{ value: '', label: '全部状态' }, ...(config?.lineStatuses || []).map((status) => ({ value: status, label: label(status) }))]"
                  @change="selectedStage = ''" />
                <a-select v-model:value="lineFilter.dept" aria-label="归属部门" style="width: 155px"
                  :options="[{ value: '', label: '全部部门' }, ...departmentNames.map((name) => ({ value: name, label: name }))]" />
                <a-select v-model:value="lineFilter.leader" aria-label="负责组长" style="width: 155px"
                  :options="[{ value: '', label: '全部组长' }, ...leaderNames.map((name) => ({ value: name, label: name }))]" />
                <a-button @click="clearLineFilters">清除筛选</a-button>
              </div>
              <div class="v05-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th></th>
                      <th>票号 / OTA订单号 / 内部明细</th>
                      <th>业务归属 / 组长</th>
                      <th>操作人员</th>
                      <th>主状态 / 结果</th>
                      <th>截止 / 风险</th>
                      <th>当前任务</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="line in visibleLines"
                      :key="line.id"
                      :class="{ active: selectedLineId === line.id }"
                      @click="selectedLineId = line.id"
                    >
                      <td>
                        <input
                          v-if="canExportLine(line)"
                          type="checkbox"
                          :checked="selectedIds.includes(line.id)"
                          @click.stop
                          @change="toggleSelected(line.id)"
                        />
                      </td>
                      <td>
                        <button class="link" @click.stop="openBasicInfo(line)">
                          {{ line.ticketNo || '未填写票号' }}</button
                        ><small>OTA：{{ line.otaOrderNo || '未填写' }} · PNR：{{ line.pnr || '未填写' }}</small
                        ><small>内部明细：{{ line.lineInternalNo }}</small>
                      </td>
                      <td>
                        {{ line.departmentName }}<small>组长：{{ line.leaderName || '未分配' }}</small>
                      </td>
                      <td>{{ line.operatorName || '未分配' }}</td>
                      <td>
                        <span :class="['pill', lineTone(line.lineStatus)]">● {{ label(line.lineStatus) }}</span>
                        <div class="order-tags">
                          <span class="pill blue"
                            >恢复：{{ label(line.recoveryStatus) }}</span
                          ><span
                            :class="['pill', lineDiffMatchTone(line)]"
                            >差异单：{{ lineDiffMatchLabel(line) }}</span
                          >
                        </div>
                      </td>
                      <td>
                        {{ record.case.replyDeadline || '—'
                        }}<small :class="{ danger: lineRisk !== '正常' }">{{ lineRisk }}</small>
                      </td>
                      <td>
                      {{ nextTask(line) }}
                      <a-tag v-if="line.leaderOverdueAt" color="red">组长分派超 3 天</a-tag>
                <a-tag v-if="line.operatorOverdueAt" color="red">操作员分派超 3 天</a-tag>
                    </td>
                      <td>
                        <div class="record-actions order-record-actions">
                          <a-button type="primary" @click.stop="openLineDrawer(line)">订单处理详情</a-button
                          ><a-button v-if="isCaseOwner && canAssignLeader && record.case.caseStatus === 'ACTIVE' && canChangeAdmLeader(line)" @click.stop="openLineTask(line, 'leader')">{{ line.lineStatus === 'PENDING_LEADER' ? '分配组长' : '更换组长' }}</a-button
                          ><a-button v-if="canAssignOperator && Number(line.leaderId) === myId && line.lineStatus === 'PENDING_OPERATOR'" @click.stop="openLineTask(line, 'assign')">分配操作员</a-button
                          ><a-button v-if="canTransferOrder(line)" @click.stop="openLineTask(line, 'transfer')">转派</a-button>
                        </div>
                      </td>
                    </tr>
                    <tr v-if="!visibleLines.length">
                      <td colspan="8" class="empty">{{ record.lines.length ? '当前筛选下没有订单明细' : '暂无订单明细' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <a-drawer
            v-if="selectedLine"
            v-model:open="drawerOpen"
            title="订单处理详情"
            width="940"
            ><div class="drawer-line-head">
              <div>
                <h2>{{ selectedLine.ticketNo || '未填写票号' }} · 订单处理</h2>
                <p>OTA {{ selectedLine.otaOrderNo || '未填写' }} · PNR {{ selectedLine.pnr || '未填写' }} · 内部明细 {{ selectedLine.lineInternalNo }}</p>
                <small>{{ selectedLine.departmentName }} · {{ selectedLine.leaderName || '未分配组长' }} · {{ selectedLine.operatorName || '未分配操作员' }} · 当前任务：{{ nextTask(selectedLine) }}</small>
              </div>
              <div class="drawer-head-actions"><button @click="openBasicInfo(selectedLine)">{{ canEditLineBasic(selectedLine) ? '编辑基础信息' : '查看基础信息' }}</button><span :class="['pill', lineTone(selectedLine.lineStatus)]">{{ label(selectedLine.lineStatus) }}</span></div>
            </div>
            <a-alert
              v-if="record.case.caseStatus === 'DRAFT'"
              type="info"
              show-icon
              message="草稿尚未进入办理流程；发布后才可分配、接单和处理明细。"
              style="margin-bottom: 14px"
            />
            <div class="drawer-tabs">
              <button
                v-for="tab in drawerTabs"
                :key="tab"
                :class="{ active: drawerTab === tab }"
                @click="drawerTab = tab"
              >
                {{ tab }}
              </button>
            </div>
            <div class="drawer-body">
              <section v-if="drawerTab === '处理决定与结果'">
                <p class="permission">当前为{{ canEditLineRecord(selectedLine) ? '可编辑' : '只读查看' }}模式；只显示当前角色和订单状态允许的操作，所有提交均写入操作记录。</p>
                <section v-if="!canProcessSelected || selectedLine.lineStatus !== 'PROCESSING'" class="saved-process-section">
                  <h3>处理进度与已保存内容</h3>
                  <p>当前状态：{{ label(selectedLine.lineStatus) }} · {{ nextTask(selectedLine) }}</p>
                  <p>编码恢复：{{ recoveryTitle }}<span v-if="latestRecovery?.decidedAt"> · 决定于 {{ latestRecovery.decidedAt }}</span><span v-if="latestRecovery?.confirmedAt"> · {{ latestRecovery.confirmedByName || selectedLine.operatorName }} 于 {{ latestRecovery.confirmedAt }} 确认已恢复并处理</span></p>
                  <p>处理决定：{{ appealTitle }} · 结果：{{ appealCopy }}</p>
                  <p v-if="selectedLine.investigationNote">订单情况说明：{{ selectedLine.investigationNote }}</p>
                  <p v-if="selectedLine.problemAttribution">问题归因：{{ label(selectedLine.problemAttribution) }}</p>
                  <p>是否匹配到差异单：{{ lineDiffMatchLabel(selectedLine) }} · {{ selectedLine.otaOrderNo || selectedLine.lineInternalNo }}</p>
                  <p>本单可用附件：{{ currentAvailableAttachments.length }} 份（主单公共附件 {{ masterAttachments.length }} 份，当前明细附件 {{ selectedLineAttachments.length }} 份）</p>
                </section>

                <section v-else class="prototype-process-form">
                  <a-alert
                    v-if="selectedReturnMode === 'SUPPLEMENT'"
                    type="warning"
                    show-icon
                    message="审核已驳回：请补充材料后重新提交"
                    :description="cleanReturnReason(latestReview?.returnReason) || '请按审核意见补充订单资料、问题说明或附件。原处理决定保持不变。'"
                    class="block"
                  />
                  <a-alert
                    v-else-if="selectedReturnMode === 'REAPPEAL'"
                    type="warning"
                    show-icon
                    message="审核已驳回：需要重新申诉"
                    :description="cleanReturnReason(latestReview?.returnReason) || '原处理决定已退回，请重新填写申诉决定和实际结果。'"
                    class="block"
                  />
                  <a-alert
                    v-else-if="selectedReturnMode === 'WITHDRAWN'"
                    type="warning"
                    show-icon
                    message="审核已撤回：请更正后重新提交"
                    description="该订单曾审核通过，ADM负责人已撤回审核。请按撤回原因更正资料或说明，原处理决定暂时保留。"
                    class="block"
                  />
                  <section class="supplement-order-section">
                    <h3>补充订单资料（均选填）</h3>
                    <div class="prototype-process-grid">
                      <label>OTA订单号<a-input :value="selectedLine.otaOrderNo || ''" readonly /></label>
                      <label>OTA平台<a-input :value="selectedLine.otaName || ''" readonly /></label>
                      <label>供应商<a-input :value="selectedLine.supplierName || ''" readonly /></label>
                      <label>航司<a-input :value="selectedLine.airlineName || ''" readonly /></label>
                      <label>票号<a-input :value="selectedLine.ticketNo || ''" readonly /></label>
                      <label>PNR编码<a-input :value="selectedLine.pnr || ''" readonly /></label>
                    </div>
                  </section>

                  <h3>1. 判断是否恢复编码</h3>
                  <p>按当前阶段完成一项操作。系统只记录决定、人员和时间；实际恢复在线下完成，不等待外部接口回写。</p>
                  <div class="recovery-stage">
                    <template v-if="selectedLine.recoveryStatus === 'UNDECIDED'">
                      <div><span class="pill blue">待判断</span><b>本笔订单是否需要恢复编码？</b><small>完成判断后才能继续提交处理结果。</small></div>
                      <div class="task-buttons"><a-button type="primary" @click="openRecoveryAction('NEEDED')">需要恢复编码</a-button><a-button @click="openRecoveryAction('NOT_NEEDED')">无需恢复编码</a-button></div>
                    </template>
                    <template v-else-if="selectedLine.recoveryStatus === 'NOT_REQUIRED'">
                      <div><span class="pill blue">无需恢复</span><b>本笔订单无需恢复编码</b><small>可以继续填写申诉决定和处理结果。</small></div>
                    </template>
                    <template v-else-if="['WAITING', 'REMINDER_DUE'].includes(selectedLine.recoveryStatus)">
                      <div><span class="pill amber">等待人工恢复</span><b>已记录需要恢复编码</b><small>决定时间：{{ latestRecovery?.decidedAt || '未记录' }}</small><small v-if="selectedLine.recoveryStatus === 'REMINDER_DUE'" class="danger">恢复结果已到提醒时间，请确认线下处理结果。</small></div>
                      <a-button type="primary" @click="runSimple('recoveryConfirm')">确认已查看并处理</a-button>
                    </template>
                    <template v-else>
                      <div><span class="pill green">已处理</span><b>恢复编码已经人工完成并处理</b><small>{{ latestRecovery?.confirmedByName || selectedLine.operatorName }} 于 {{ latestRecovery?.confirmedAt || '未记录时间' }} 确认</small></div>
                    </template>
                  </div>

                  <section>
                    <h3>2. 是否申诉与最终结果</h3>
                    <p>申诉在系统外办理，无需登记具体跟进过程；允许一次填写实际最终结果。</p>
                    <label>处理决定<div class="task-buttons process-choice-buttons"><a-button :aria-pressed="selectedLine.appealStatus === 'IN_PROGRESS'" :disabled="selectedLine.appealStatus !== 'UNDECIDED'" @click="openAction('appeal')">{{ selectedReturnMode === 'REAPPEAL' ? '重新申诉' : '提交申诉' }}</a-button><a-button :aria-pressed="selectedLine.appealStatus === 'NO_APPEAL'" :disabled="selectedLine.appealStatus !== 'UNDECIDED'" @click="openAction('noAppeal')">不申诉</a-button></div></label>
                    <template v-if="activeAppeal"><p>申诉原因：{{ activeAppeal.appealReason || '未填写' }}</p><p>申诉对象：{{ activeAppeal.appealTarget || '未填写' }}</p><a-button @click="openAction('appealResult')">申诉结果</a-button></template>
                    <div v-if="['NO_APPEAL', 'FAILED'].includes(selectedLine.appealStatus)"><p>问题归因（必填，三选一）</p><div class="task-buttons process-choice-buttons"><a-button v-for="cause in ['人为问题', '平台问题', '系统问题']" :key="cause" :aria-pressed="label(selectedLine.problemAttribution) === cause">{{ cause }}</a-button></div><p>差异订单匹配状态：{{ label(selectedLine.diffMatchStatus) }}</p><small>{{ selectedLine.otaOrderNo || selectedLine.lineInternalNo }} · 审核通过后由 ADM 负责人核验。</small></div>
                    <label v-if="selectedLine.appealStatus !== 'UNDECIDED'">处理依据附件（选填）<a-button @click="openLineAttachments('APPEAL')">上传或查看当前明细附件（{{ selectedLineAttachments.length }}）</a-button></label>
                    <div v-if="['SUPPLEMENT', 'WITHDRAWN'].includes(selectedReturnMode)" class="task-buttons"><a-button @click="openBasicInfo(selectedLine)">{{ selectedReturnMode === 'WITHDRAWN' ? '更正订单基础信息' : '补充订单基础信息' }}</a-button><a-button @click="openLineAttachments('APPEAL')">补充附件材料</a-button><a-button type="primary" @click="runSimple('submitReview')">{{ selectedReturnMode === 'WITHDRAWN' ? '更正完成，重新提交审核' : '补充完成，重新提交审核' }}</a-button></div>
                    <div v-else-if="selectedLine.appealStatus !== 'UNDECIDED'" class="task-buttons"><a-button @click="openAction('note')">保存处理决定</a-button><a-button type="primary" @click="runSimple('submitReview')">提交ADM负责人审核</a-button></div>
                  </section>
                </section>

                <div v-if="record.case.caseStatus === 'ACTIVE'" class="process-overview-actions process-support-actions">
                  <a-button v-if="isCurrentOperator && selectedLine.lineStatus === 'PENDING_ACCEPT'" type="primary" @click="runSimple('accept')">接单</a-button><a-button v-if="pendingTargetTransfer" type="primary" @click="decidePendingTransfer(true)">接受转派</a-button><a-button v-if="pendingTargetTransfer" danger @click="openAction('transferReject')">拒绝转派</a-button><a-button v-if="isCaseOwner && canReview && selectedLine.lineStatus === 'PENDING_REVIEW'" type="primary" @click="openAction('review')">ADM负责人审核</a-button><a-button v-if="canWithdrawReview" @click="openAction('withdrawReview')">撤回审核</a-button><a-button v-if="isCaseOwner && canDiffMatch && selectedLine.lineStatus === 'WAITING_DIFF'" type="primary" @click="runSimple('checkDifference')">匹配差异单</a-button><a-button v-if="isCaseOwner && canCollection && selectedLine.lineStatus === 'WAITING_COLLECTION'" type="primary" @click="openAction('collection')">登记回款</a-button>
                </div>

                <div v-if="isCaseOwner && canManage && record.case.caseStatus === 'ACTIVE'" class="process-danger-zone"><b>管理操作</b><div><a-button v-if="!record.lines.some((item) => ['PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION', 'COMPLETED', 'HISTORICAL'].includes(item.lineStatus))" @click="openAction('rebalance')">调整明细金额</a-button><a-button v-if="selectedLine.reviewStatus !== 'APPROVED' && !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(selectedLine.lineStatus)" danger @click="openAction('voidLine')">作废明细</a-button></div></div>
              </section>
              <section v-else-if="drawerTab === '附件'">
                <h3>主单公共附件</h3>
                <p class="info">
                  当前 ADM 主单下所有明细都可以查看这里的附件。适合存放 ADM 原始文件等整单共用资料。
                </p>
                <a-alert v-if="!canUploadAttachment" type="info" show-icon :message="`当前账号只能查看附件；如需上传，请联系ADM负责人${record.case.coordinatorName ? `“${record.case.coordinatorName}”` : ''}或当前负责人员。`" />
                <div class="upload attachment-upload-box">
                  <div class="attachment-upload-row">
                    <a-select v-model:value="masterAttachmentCategory" :options="masterAttachmentOptions" :disabled="!canUploadAttachment" />
                    <a-button @click="canUploadAttachment ? masterAttachmentInput?.click() : readOnlyNotice('附件')">选择文件</a-button>
                    <span class="attachment-file-name">{{ masterAttachmentFile?.name || '尚未选择文件' }}</span>
                    <a-button type="primary" :disabled="!canUploadAttachment || !masterAttachmentFile" :loading="saving" @click="canUploadAttachment ? uploadScopedAttachment('CASE') : readOnlyNotice('附件')">上传到主单</a-button>
                  </div>
                  <input ref="masterAttachmentInput" class="attachment-file-input" type="file" @change="pickMasterAttachment" />
                </div>
                <p v-if="!masterAttachments.length" class="attachment-empty">暂无主单公共附件</p>
                <a-list v-else :data-source="masterAttachments" size="small"
                  ><template #renderItem="{ item }"
                    ><a-list-item
                      ><a-list-item-meta
                        :title="item.originalFileName"
                        :description="`${attachmentCategoryLabel(item.category)} · ${item.uploadedByName} · ${item.uploadedAt}`"
                      /><a-space
                        ><a-button size="small" @click="previewFile(item)">预览</a-button
                        ><a-button size="small" @click="queueAttachmentExport(item)">加入导出任务</a-button
                        ><a-button v-if="isCaseOwner && canManage" size="small" danger @click="voidAttachment(item)"
                          >作废</a-button
                        ></a-space
                      ></a-list-item
                    ></template
                  ></a-list
                >
                <div ref="lineAttachmentSection" class="attachment-scope-section">
                  <h3>当前明细附件</h3>
                  <p class="info">
                    仅属于明细“{{ selectedLine.lineInternalNo }}”，不会显示在同一主单的其他明细中。适合存放申诉依据、处理证明、审核材料和回款凭证。
                  </p>
                  <div class="upload attachment-upload-box">
                    <div class="attachment-upload-row">
                      <a-select v-model:value="lineAttachmentCategory" :options="lineAttachmentOptions" :disabled="!canUploadSelectedLineAttachment" />
                      <a-button @click="canUploadSelectedLineAttachment ? lineAttachmentInput?.click() : readOnlyNotice('附件')">选择文件</a-button>
                      <span class="attachment-file-name">{{ lineAttachmentFile?.name || '尚未选择文件' }}</span>
                      <a-button type="primary" :disabled="!canUploadSelectedLineAttachment || !lineAttachmentFile" :loading="saving" @click="canUploadSelectedLineAttachment ? uploadScopedAttachment('LINE') : readOnlyNotice('附件')">上传到当前明细</a-button>
                    </div>
                    <input ref="lineAttachmentInput" class="attachment-file-input" type="file" @change="pickLineAttachment" />
                  </div>
                  <p v-if="!selectedLineAttachments.length" class="attachment-empty">暂无当前明细附件</p>
                  <a-list v-else :data-source="selectedLineAttachments" size="small"
                    ><template #renderItem="{ item }"
                      ><a-list-item
                        ><a-list-item-meta
                          :title="item.originalFileName"
                          :description="`${attachmentCategoryLabel(item.category)} · ${item.uploadedByName} · ${item.uploadedAt}`"
                        /><a-space
                          ><a-button size="small" @click="previewFile(item)">预览</a-button
                          ><a-button size="small" @click="queueAttachmentExport(item)">加入导出任务</a-button
                          ><a-button v-if="isCaseOwner && canManage" size="small" danger @click="voidAttachment(item)"
                            >作废</a-button
                          ></a-space
                        ></a-list-item
                      ></template
                    ></a-list
                  >
                </div>
              </section>
              <section v-else-if="drawerTab === '审核处理'">
                <h3>审核记录</h3>
                <a-button v-if="isCaseOwner && canReview && selectedLine.lineStatus === 'PENDING_REVIEW'"
                  type="primary" :disabled="saving" @click="openAction('review')">ADM负责人审核</a-button>
                <a-button v-if="canWithdrawReview" :disabled="saving" @click="openAction('withdrawReview')">撤回审核</a-button>
                <a-timeline v-if="lineRecords('reviews').length"
                  ><a-timeline-item v-for="item in lineRecords('reviews').slice().reverse()" :key="item.id"
                    ><b>{{ label(item.result) }}</b>
                    <div>{{ item.reviewerName }} · {{ item.reviewedAt }}</div>
                    <p v-if="item.returnReason"><b>{{ item.returnReason.startsWith('【驳回补充材料】') ? '驳回补充材料' : item.returnReason.startsWith('【驳回重新申诉】') ? '驳回重新申诉' : '审核退回' }}：</b>{{ cleanReturnReason(item.returnReason) }}</p>
                    <p v-else>{{ item.reviewNote || '无补充说明' }}</p></a-timeline-item
                  ></a-timeline
                >
                <p v-else class="empty">当前暂无审核记录</p>
              </section>
              <section v-else-if="drawerTab === '转派记录'">
                <h3>转派记录</h3>
                <a-space v-if="pendingTargetTransfer">
                  <a-button type="primary" :loading="saving" @click="decidePendingTransfer(true)">接受转派</a-button>
                  <a-button danger :disabled="saving" @click="openAction('transferReject')">拒绝转派</a-button>
                </a-space>
                <a-timeline v-if="visibleTransfers.length">
                  <a-timeline-item v-for="item in visibleTransfers" :key="item.id">
                    <a-tag color="blue">{{ item.targetRole === 'LEADER' ? '组长转派' : '操作员转派' }}</a-tag>
                    <b>{{ item.fromOperatorName }} → {{ item.toOperatorName }}</b>
                    <div>{{ transferResultText(item) }} · {{ item.requestedByName }} · {{ item.requestedAt }}</div>
                    <p v-if="item.transferReason">{{ item.transferReason }}</p>
                    <p v-if="item.decidedAt">{{ item.decidedByName }} · {{ item.decidedAt }} {{ item.decisionReason }}</p>
                  </a-timeline-item>
                </a-timeline>
                <p v-else class="empty">当前暂无可查看的转派记录</p>
              </section>
              <section v-else-if="drawerTab === '负责人跟进'">
                <h3>差异单核验</h3>
                <p>当前结果：{{ lineDiffMatchLabel(selectedLine) }}</p>
                <a-button v-if="isCaseOwner && canDiffMatch && selectedLine.lineStatus === 'WAITING_DIFF'" :loading="saving"
                  @click="runSimple('checkDifference')">核验差异单</a-button>
                <a-timeline v-if="lineRecords('diffMatches').length">
                  <a-timeline-item v-for="item in lineRecords('diffMatches').slice().reverse()" :key="item.id">
                    <b>{{ diffMatchLabel(item.resultStatus) }}</b>
                    <div>{{ item.checkedByName }} · {{ item.checkedAt }}</div>
                    <div v-if="item.matchedKeyValue">核验值 {{ item.matchedKeyValue }}</div>
                  </a-timeline-item>
                </a-timeline>
                <h3>回款</h3>
                <p v-if="selectedLine.collectionRequired">
                  应回款 {{ selectedLine.currency }} {{ selectedLine.expectedCollectionAmount }} ·
                  已登记 {{ selectedLine.currency }} {{ selectedLine.collectedAmount }} ·
                  未回款 {{ selectedLine.currency }} {{ collectionBalance.current }}
                </p>
                <a-button v-if="isCaseOwner && canCollection && selectedLine.lineStatus === 'WAITING_COLLECTION'"
                  :disabled="saving" @click="openAction('collection')">登记回款</a-button>
                <a-timeline v-if="lineRecords('collections').length"
                  ><a-timeline-item v-for="item in lineRecords('collections').slice().reverse()" :key="item.id"
                    ><b>{{ item.currency }} {{ item.amount }}</b>
                    <div>{{ item.receivedDate }} · {{ item.recordedByName }}</div>
                    <p>{{ item.description || item.voucherNo || '无补充说明' }}</p></a-timeline-item
                  ></a-timeline
                >
                <p v-else class="empty">当前暂无负责人跟进记录</p>
              </section>
              <section v-else>
                <h3>订单操作记录</h3>
                <a-button type="link" @click="openMasterOperations">查看主单操作记录</a-button>
                <AdmOperationTimeline :items="lineRecords('operationLogs')" empty-text="当前订单暂无操作记录" />
              </section>
            </div></a-drawer
          >
        </template>
      </section>
    </main>

    <a-modal v-model:open="masterOperationsOpen" title="ADM 主单操作记录" :footer="null" :width="720">
      <AdmOperationTimeline :items="caseOperationLogs" empty-text="当前主单暂无操作记录" />
    </a-modal>
    <AdmMasterBasicModal :open="masterInfoOpen" :detail="record" :editable="canEditMasterBasic" @close="masterInfoOpen = false" @saved="basicInfoSaved" />
    <AdmLineBasicModal :open="basicInfoOpen" :detail="record" :line="selectedLine" :editable="!!selectedLine && canEditLineBasic(selectedLine)" :config="config" @close="basicInfoOpen = false" @saved="basicInfoSaved" />

    <a-modal v-model:open="addLineOpen" :title="isRecoveryAllocation && addAmountStep ? '订单金额分摊' : '新增订单明细'" width="1080px" :footer="null" wrap-class-name="v05-modal"
      ><p class="context">
        <b>{{ addTarget.case.admNo }}</b
        > 系统记录 {{ addTarget.case.internalNo }} {{ addTarget.case.issuerName }} 原币总金额 {{ addTarget.case.currency }}
        {{ addTarget.case.originalAmount }} 处理截止 {{ addTarget.case.replyDeadline || '未设置' }}
      </p>
      <a-alert
        type="info"
        show-icon
        :message="addActiveLines.length
          ? '主单总金额固定，新增后全部有效明细金额合计须与主单金额一致。'
          : '首笔订单金额沿用主单总金额。' "
        class="block"
      />
      <a-alert v-if="!isRecoveryAllocation"
        type="warning"
        show-icon
        message="先选择订单所属的 ADM 主单；币种、截止时间和冻结汇率均继承所选主单。"
        class="block"
      />
      <a-alert v-if="addTarget.case.lineDefaults" type="info" show-icon class="block"
        :message="`继承主单：${addTarget.case.lineDefaults.departmentName} · ${addTarget.case.lineDefaults.leaderName} · ${addTarget.case.lineDefaults.diffTypeName}`" />
      <div v-if="!isRecoveryAllocation || !addAmountStep" class="v05-form-grid">
        <label v-if="!isRecoveryAllocation" class="wide"
          ><span class="form-field-label">所属 ADM 主单 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
            v-model:value="addTargetCaseId"
            show-search
            :filter-option="filterOption"
            :options="addCaseOptions" :loading="addTargetLoading"
            @change="selectAddCase" /></label
        >
        <label>OTA订单号（选填）<a-input v-model:value="addLineForm.otaOrderNo" /></label
        ><label>票号（选填）<a-input v-model:value="addLineForm.ticketNo" /></label
        ><label v-if="!isRecoveryAllocation">PNR编码（选填）<a-input v-model:value="addLineForm.pnr" /></label
        ><label
          >OTA平台（选填）<a-select
            v-model:value="addLineForm.otaCode"
            allow-clear
            :options="addOtaOptions"
            @change="(v?: string) => selectAddOption('ota', v)" /></label
        ><label v-if="!addTarget.case.lineDefaults"
          ><span class="form-field-label">业务归属部门 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
            v-model:value="addLineForm.departmentCode"
            show-search
            :options="addDepartmentOptions"
            @change="(v: string) => selectAddOption('department', v)" /></label
        ><label v-if="!addTarget.case.lineDefaults || isRecoveryAllocation"
          ><span class="form-field-label">负责组长 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
            v-model:value="addLineForm.leaderId"
            :options="addLeaderOptions"
            @change="selectAddLeader" /></label
        ><label v-if="!isRecoveryAllocation">截止时间（继承主单）<a-input :value="addTarget.case.replyDeadline" readonly /></label
        ><label v-if="!isRecoveryAllocation"
          >供应商（选填）<a-select
            v-model:value="addLineForm.supplierCode"
            allow-clear
            :options="addSupplierOptions"
            @change="(v?: string) => selectAddOption('supplier', v)" /></label
        ><label v-if="!isRecoveryAllocation">航司（选填）<a-input v-model:value="addLineForm.airlineName" /></label
        ><label v-if="!isRecoveryAllocation"><span class="form-field-label">ADM金额（原币） <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="addLineForm.originalAmount" /></label
        ><label v-if="!isRecoveryAllocation">币种（继承主单）<a-input :value="addTarget.case.currency" readonly /></label
        ><label v-if="!isRecoveryAllocation">ADM金额（人民币，系统换算）<a-input :value="`¥ ${addLineCnyAmount}`" readonly /></label
        ><label class="wide"
          >订单情况说明（选填）<a-textarea
            v-model:value="addLineForm.investigationNote"
            :rows="2"
            placeholder="填写当前已知的订单情况，操作员办理时可继续更新" /></label
        ><label v-if="!addTarget.case.lineDefaults"
          ><span class="form-field-label">差异类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
            v-model:value="addLineForm.diffTypeCode"
            show-search
            :options="addDiffTypeOptions"
            @change="(v: string) => selectAddOption('diffType', v)" /></label
        ><label v-if="!addTarget.case.lineDefaults" class="wide"><span class="form-field-label">细分差异原因 <span class="form-required-mark" aria-hidden="true">*</span></span><a-textarea aria-required="true" v-model:value="addLineForm.differenceReason" :rows="3" /></label
        ><label v-if="!isRecoveryAllocation && needsAddLineReason" class="wide"><span class="form-field-label">新增及金额调整说明 <span class="form-required-mark" aria-hidden="true">*</span></span><a-textarea aria-required="true" v-model:value="addLineForm.reason" :rows="2" /></label>
      </div>
      <template v-if="!isRecoveryAllocation || addAmountStep">
      <a-form v-if="isRecoveryAllocation" layout="vertical">
        <a-form-item label="本笔订单原币金额" required>
          <a-input v-model:value="addLineForm.originalAmount" :addon-before="addTarget.case.currency" />
        </a-form-item>
        <a-form-item v-if="needsAddLineReason" label="金额调整说明" required>
          <a-textarea v-model:value="addLineForm.reason" :rows="2" />
        </a-form-item>
      </a-form>
      <h3>现有有效明细调整后金额</h3>
      <div class="amount-adjustments">
        <label v-for="line in addActiveLines" :key="line.id"
          >{{ line.lineInternalNo
          }}<a-input v-model:value="addLineAmounts[line.id]" :addon-before="addTarget.case.currency"
        /></label>
      </div>
      <a-alert
        :type="addLineBalanced ? 'success' : 'warning'"
        show-icon
        :message="`调整后合计 ${addTarget.case.currency} ${addLineTotal.toFixed(2)}；主单金额 ${addTarget.case.originalAmount}`"
        class="block"
      />
      <section class="entry-extra">
        <h3>当前已录入 {{ addActiveLines.length }} 笔</h3>
        <div class="v05-table-wrap">
          <table>
            <thead>
              <tr>
                <th>内部明细</th>
                <th>OTA订单号 / 票号 / PNR</th>
                <th>部门 / 组长</th>
                <th>调整后金额</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in addActiveLines" :key="`saved-${line.id}`">
                <td>{{ line.lineInternalNo }}</td>
                <td>
                  {{ line.otaOrderNo || '未填写' }} / {{ line.ticketNo || '未填写' }} / {{ line.pnr || '未填写' }}
                </td>
                <td>{{ line.departmentName }} / {{ line.leaderName || '未分配' }}</td>
                <td>{{ addTarget.case.currency }} {{ addLineAmounts[line.id] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      </template>
      <a-alert v-if="addLineError" type="error" show-icon :message="addLineError" class="block" />
      <div class="v05-modal-actions">
        <button @click="addLineOpen = false">取消</button
        ><a-button v-if="isRecoveryAllocation && addAmountStep" @click="addAmountStep = false">返回订单信息</a-button>
        <a-button v-if="isRecoveryAllocation && !addAmountStep" type="primary"
          :disabled="!addLineForm.leaderId" @click="addAmountStep = true">下一步：金额分摊</a-button>
        <a-button v-else type="primary" :loading="saving" :disabled="!addLineReady" @click="submitAddLine">保存新增订单</a-button>
      </div></a-modal
    >

    <a-modal
      v-model:open="actionOpen"
      :title="actionTitles[actionName] || '办理操作'"
      :confirm-loading="saving"
      ok-text="确定"
      cancel-text="取消"
      wrap-class-name="v05-modal"
      @ok="submitAction"
    >
      <a-form layout="vertical">
        <a-alert v-if="assignmentAction && (configError || config?.people.rosterAvailable === false)" type="warning" show-icon
          :message="configError || '花名册暂不可用，当前显示具备 ADM 权限的中台账号。'" />
        <a-button v-if="assignmentAction" type="link" :loading="peopleLoading" @click="loadPeople">刷新人员名单</a-button>
        <a-form-item v-if="actionName === 'assign'" label="操作员" required
          ><a-select v-model:value="actionForm.operatorId" :options="operatorOptions"
            show-search option-filter-prop="label" placeholder="搜索姓名、部门或账号" :loading="peopleLoading"
        /></a-form-item>
        <a-form-item v-if="actionName === 'leader'" label="新组长" required
          ><a-select v-model:value="actionForm.leaderId" :options="leaderOptions"
            show-search option-filter-prop="label" placeholder="搜索姓名、部门或账号" :loading="peopleLoading"
        /></a-form-item>
        <a-form-item v-if="actionName === 'transfer'" label="转派岗位" required>
          <a-radio-group v-model:value="actionForm.targetRole" @change="actionForm.targetUserId = undefined">
            <a-radio-button v-if="canAssignOperator && Number(selectedLine?.leaderId) === myId" value="LEADER">组长</a-radio-button>
            <a-radio-button :disabled="!selectedLine?.operatorId" value="OPERATOR">操作员</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="actionName === 'transfer'" label="目标人员" required
          ><a-select v-model:value="actionForm.targetUserId" :options="actionForm.targetRole === 'LEADER' ? leaderOptions : operatorOptions"
            show-search option-filter-prop="label" placeholder="搜索姓名、部门或账号" :loading="peopleLoading"
        /></a-form-item>
        <a-form-item v-if="actionName === 'note'" label="订单情况说明" required
          ><a-textarea v-model:value="actionForm.investigationNote" :rows="5"
        /></a-form-item>
        <a-form-item v-if="actionName === 'recovery'" label="是否需要恢复" required
          ><a-radio-group v-model:value="actionForm.decision"
            ><a-radio value="NEEDED">需要恢复</a-radio><a-radio value="NOT_NEEDED">无需恢复</a-radio></a-radio-group
          ></a-form-item
        >
        <a-form-item v-if="actionName === 'appeal'" label="申诉原因" required
          ><a-textarea v-model:value="actionForm.appealReason"
        /></a-form-item>
        <a-form-item v-if="actionName === 'appeal'" label="申诉对象" required>
          <a-select v-model:value="actionForm.appealTarget" :options="config?.appealTargets || []" placeholder="请选择申诉对象" />
          <div v-if="actionForm.appealTarget" class="form-help">
            {{ appealPartyName || '当前订单未登记该类型的对象名称' }}
          </div>
        </a-form-item>
        <a-form-item v-if="actionName === 'appealResult'" label="申诉结果" required
          ><a-select v-model:value="actionForm.result" :options="appealResultOptions" placeholder="请选择申诉结果"
        /></a-form-item>
        <a-form-item v-if="['appealResult', 'noAppeal'].includes(actionName)" label="问题归属" :required="actionName === 'noAppeal' || actionForm.result === 'FAILED'"
          ><a-select v-model:value="actionForm.problemAttribution" :options="attributionOptions"
        /></a-form-item>
        <a-form-item v-if="actionName === 'review'" label="审核结果" required
          ><a-radio-group v-model:value="actionForm.result"
            ><a-radio value="APPROVED">通过</a-radio><a-radio value="RETURNED">退回</a-radio></a-radio-group
          ></a-form-item
        >
        <a-form-item v-if="actionName === 'review' && actionForm.result === 'RETURNED'" label="驳回类型" required
          ><a-radio-group v-model:value="actionForm.returnType"
            ><a-radio value="SUPPLEMENT">驳回补充材料</a-radio><a-radio value="REAPPEAL">驳回重新申诉</a-radio></a-radio-group
          ><div class="form-help">补充材料保留原处理决定；重新申诉会把当前处理决定退回，由操作员重新选择申诉或不申诉。</div></a-form-item
        >
        <a-form-item v-if="actionName === 'review' && actionForm.result === 'APPROVED' && selectedLine?.appealStatus === 'SUCCEEDED'" label="是否需要回款" required
          ><a-radio-group v-model:value="actionForm.collectionRequired"
            ><a-radio :value="true">需要</a-radio><a-radio :value="false">不需要</a-radio></a-radio-group
          ></a-form-item
        >
        <a-form-item v-if="actionName === 'review' && actionForm.result === 'APPROVED' && selectedLine?.appealStatus === 'SUCCEEDED' && actionForm.collectionRequired === true" label="应回款金额" required
          ><a-input v-model:value="actionForm.expectedCollectionAmount"
        /></a-form-item>
        <template v-if="actionName === 'collection'">
          <a-alert show-icon :type="collectionBalance.over ? 'warning' : 'info'" class="block">
            <template #message>
              应回款 {{ selectedLine?.currency }} {{ selectedLine?.expectedCollectionAmount }}，
              已登记 {{ selectedLine?.currency }} {{ selectedLine?.collectedAmount }}，
              未回款 {{ selectedLine?.currency }} {{ collectionBalance.current }}
            </template>
            <template #description>
              <span v-if="collectionBalance.over">本次金额超过当前未回款金额，请核对凭证。</span>
              <span v-else-if="collectionBalance.projected !== null">登记后预计未回款 {{ selectedLine?.currency }} {{ collectionBalance.projected }}</span>
              <span v-else>可按实际到账金额分次登记。</span>
            </template>
          </a-alert>
          <a-form-item label="回款日期" required><a-input v-model:value="actionForm.receivedDate" type="date" /></a-form-item
          ><a-form-item label="回款金额" required><a-input v-model:value="actionForm.amount" /></a-form-item
          ><a-form-item label="凭证号（银行流水号、收款单号或财务凭证号）"
            ><a-input v-model:value="actionForm.voucherNo" placeholder="有凭证号时填写真实编号，不要随意编写" /></a-form-item
          ><a-form-item label="回款凭证附件"
            ><div class="collection-attachment-field">
              <a-checkbox-group v-model:value="actionForm.attachmentIds">
                <a-checkbox v-for="item in currentAvailableAttachments" :key="item.id" :value="item.id">
                  {{ item.originalFileName }}（{{ attachmentCategoryLabel(item.category) }}）
                </a-checkbox>
              </a-checkbox-group>
              <input type="file" @change="pickCollectionFile" />
              <span>{{ collectionFile ? `已选择：${collectionFile.name}` : '尚未选择新的回款凭证文件' }}</span>
              <small>没有凭证号时必须选择已有附件或上传新的回款凭证；点击“确定”后，新文件会先上传并与本次回款记录关联。</small>
            </div></a-form-item
          ><a-form-item label="回款说明"><a-textarea v-model:value="actionForm.description" /></a-form-item
        ></template>
        <template v-if="actionName === 'rebalance'"
          ><a-alert
            type="warning"
            show-icon
            message="必须一次填写全部有效明细，合计仍须等于主单金额。"
            class="block" /><a-form-item v-for="line in activeLines" :key="line.id" :label="line.lineInternalNo"
            ><a-input v-model:value="actionForm.amounts[line.id]" :addon-before="record?.case.currency" /></a-form-item
        ></template>
        <a-form-item v-if="needsReason" :label="reasonLabel" :required="reasonRequired"
          ><a-textarea v-model:value="actionForm.reason"
        /></a-form-item>
        <a-form-item v-if="actionName === 'appealResult'" label="结果说明"
          ><a-textarea v-model:value="actionForm.resultNote"
        /></a-form-item>
        <a-form-item v-if="actionName === 'review' && actionForm.result === 'RETURNED'" label="驳回原因"
          ><a-textarea v-model:value="actionForm.returnReason"
        /></a-form-item>
      </a-form>
      <a-alert v-if="actionError" type="error" show-icon :message="actionError" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { Modal, message } from 'ant-design-vue'
import AdmOperationTimeline from './AdmOperationTimeline.vue'
import AdmLineBasicModal from './AdmLineBasicModal.vue'
import AdmMasterBasicModal from './AdmMasterBasicModal.vue'
import {
  admApi,
  admPersonOptions,
  canChangeAdmLeader,
  diffMatchLabel,
  errorText,
  label,
  type AdmCaseDetail,
  type AdmCaseRow,
  type AdmConfig,
  type AdmLine,
  type Fields,
  type Option,
} from './api'
import './adm-v05.css'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore(),
  exportTasks = useComprehensiveExportStore()
const caseId = Number(route.params.caseId || route.query.admId || 0)
const emptyRecord = (): AdmCaseDetail => ({
  case: {
    id: 0,
    admNo: '暂无ADM主单',
    internalNo: '—',
    issuerType: '—',
    issuerName: '—',
    issuedDate: null,
    coordinatorName: '—',
    currency: '—',
    originalAmount: '—',
    cnyAmount: '—',
    replyDeadline: null,
    caseStatus: 'EMPTY',
    lineCount: 0,
    completedLineCount: 0,
    voidedLineCount: 0,
  },
  fxSnapshot: null,
  lines: [],
  attachments: [],
  assignments: [],
  transfers: [],
  responsibilitySegments: [],
  recoveries: [],
  appeals: [],
  reviews: [],
  diffMatches: [],
  collections: [],
  operationLogs: [],
  legacySource: null,
})
const record = ref<AdmCaseDetail>(emptyRecord()),
  config = ref<AdmConfig | null>(null),
  loading = ref(false),
  saving = ref(false),
  error = ref(''),
  configError = ref('')
const hasRecord = computed(() => Number(record.value.case.id) > 0)
const isLegacyReadOnly = computed(
  () => record.value.case.sourceType === 'LEGACY' || record.value.case.caseStatus === 'HISTORICAL',
)
const selectedLineId = ref<number | null>(Number(route.query.lineId) || null),
  selectedIds = ref<number[]>([]),
  selectedStage = ref(''),
  drawerOpen = ref(false),
  drawerTab = ref('处理决定与结果'),
  basicInfoOpen = ref(false),
  masterInfoOpen = ref(false)
const drawerTabs = ['处理决定与结果', '附件', '审核处理', '负责人跟进', '转派记录', '操作记录']
const selectedLine = computed(() => record.value?.lines.find((line) => Number(line.id) === Number(selectedLineId.value)) || null)
const activeLines = computed(() => record.value?.lines.filter((line) => line.lineStatus !== 'VOIDED') || [])
const isAdmin = computed(() => !!auth.user?.isAdmin)
const myId = computed(() => Number(auth.user?.id))
const canCreate = computed(() => isAdmin.value || !!config.value?.permissions.create),
  canAssignOperator = computed(
    () => isAdmin.value || !!(config.value?.permissions.assignOperator || config.value?.permissions.assign),
  ),
  canAssignLeader = computed(() => isAdmin.value || !!config.value?.permissions.assignLeader),
  canHandle = computed(() => isAdmin.value || !!config.value?.permissions.handle),
  canReview = computed(() => isAdmin.value || !!config.value?.permissions.review),
  canDiffMatch = computed(() => isAdmin.value || !!config.value?.permissions.diffMatch),
  canCollection = computed(() => isAdmin.value || !!config.value?.permissions.collection),
  canClose = computed(() => isAdmin.value || !!config.value?.permissions.close),
  canManage = computed(() => isAdmin.value || !!config.value?.permissions.manage)
const isCaseOwner = computed(() => Number(record.value.case.coordinatorId) === myId.value)
const masterRecoveryText: Record<string, string> = {
  LEADER_DECISION: '待组长判断是否恢复编码',
  OWNER_RECOVERY: '待 ADM 负责人在 GDS 操作',
  RECOVERING: '正在恢复编码',
  RECOVERED: '编码已恢复，组长可录入订单',
  NOT_REQUIRED: '无需恢复编码',
}
const canAddLine = computed(() => {
  const master = record.value.case
  if (!hasRecord.value || isLegacyReadOnly.value || !['DRAFT', 'ACTIVE'].includes(master.caseStatus)) return false
  if (master.masterRecoveryStatus === 'RECOVERED')
    return canAssignOperator.value && Number(master.lineDefaults?.leaderId) === myId.value
  if (master.masterRecoveryStatus && master.masterRecoveryStatus !== 'NOT_REQUIRED') return false
  return isCaseOwner.value && (canCreate.value || canManage.value)
})
const canEditMasterBasic = computed(
  () => isCaseOwner.value && (canCreate.value || canManage.value || canReview.value) &&
    ['DRAFT', 'ACTIVE'].includes(record.value.case.caseStatus) &&
    !activeLines.value.some((line) => line.reviewStatus === 'APPROVED' || line.lineStatus === 'COMPLETED'),
)
function canEditLineBasic(line: AdmLine) {
  return canEditMasterBasic.value && line.reviewStatus !== 'APPROVED' &&
    !['COMPLETED', 'HISTORICAL', 'VOIDED'].includes(line.lineStatus)
}
function canEditLineRecord(line: AdmLine) {
  if (record.value.case.caseStatus !== 'ACTIVE') return false
  return canEditLineBasic(line) ||
    (canHandle.value && Number(line.operatorId) === myId.value && ['PENDING_ACCEPT', 'PROCESSING'].includes(line.lineStatus)) ||
    (canAssignOperator.value && Number(line.leaderId) === myId.value && ['PENDING_OPERATOR', 'PENDING_ACCEPT', 'PROCESSING'].includes(line.lineStatus))
}
const isCurrentOperator = computed(
  () => !!selectedLine.value && canHandle.value && Number(selectedLine.value.operatorId) === myId.value,
)
const canProcessSelected = computed(() => isCurrentOperator.value)
const isCurrentLeader = computed(
  () => !!selectedLine.value && canAssignOperator.value && Number(selectedLine.value.leaderId) === myId.value,
)
const completedCount = computed(() => activeLines.value.filter((line) => line.lineStatus === 'COMPLETED').length)
const statusTone = computed(() =>
  record.value?.case.caseStatus === 'CLOSED'
    ? 'green'
    : record.value?.case.caseStatus === 'DRAFT'
      ? 'amber'
      : record.value?.case.caseStatus === 'HISTORICAL'
        ? 'amber'
      : record.value?.case.caseStatus === 'VOIDED'
        ? 'red'
        : 'blue',
)
const sourceText = (value: unknown) => ({
    TEST: '测试数据', LEGACY: '旧系统数据 / 历史只读',
    MANUAL: '新系统人工数据', EXCEL: '新系统导入数据',
  } as Fields)[String(value || '')] || '来源未标记',
  sourceTone = (value: unknown) => String(value || '').toLowerCase()
const legacyFieldGroups = [
  { title: '来源与标识', fields: [['id', '原记录ID'], ['adm_no', 'ADM单号'], ['status', '记录状态'], ['adm_status', 'ADM状态'], ['create_time', '创建时间'], ['update_time', '更新时间'], ['create_user_name', '创建人'], ['update_user_name', '更新人']] },
  { title: '订单与供应信息', fields: [['supplier_type', '供应方类型'], ['supplier_code', '供应商编码'], ['airline', '航司编码'], ['ota_code', 'OTA编码'], ['ota_order_no', 'OTA订单号'], ['pnr_no', 'PNR'], ['pnr_recover_time', 'PNR恢复时间'], ['ticket_no', '票号'], ['ticket_count', '票数']] },
  { title: '金额与日期', fields: [['currency', '币种'], ['total_amount', '原币总金额'], ['total_amount_cny', '人民币总金额'], ['supply_issue_date', '下发日期'], ['adm_deadline', 'ADM截止时间']] },
  { title: '差异与处理', fields: [['category', '类别'], ['diff_type', '差异类型'], ['diff_second_type', '二级差异类型'], ['diff_detail_reason', '差异原因'], ['appeal_status', '申诉决定'], ['appeal_result', '申诉结果'], ['appeal_reason', '申诉原因'], ['appeal_target', '申诉对象'], ['resolution', '处理结果'], ['handle_time', '处理时间']] },
  { title: '人员与审核', fields: [['owner', '负责人'], ['actual_owner', '实际负责人'], ['actual_handler', '实际处理人'], ['auditor_name', '审核人'], ['auditor_time', '审核时间'], ['auditor_remark', '审核备注'], ['lock_flag', '锁定标记'], ['lock_operator_id', '锁定操作员ID'], ['lock_operator', '锁定操作员']] },
  { title: '其他原始信息', fields: [['file_url', '旧附件地址（原始文本）'], ['remark', '备注']] },
] as const
const legacyEnumLabels: Record<string, Record<string, string>> = {
  adm_status: { '0': '待申诉', '1': '申诉中', '2': '待审核', '3': '已结案' },
  status: { '0': '无效', '1': '有效', '2': '暂停' },
  supplier_type: { '1': '平台', '2': '航司', '3': '供应商' },
  appeal_status: { '0': '申诉', '1': '不申诉' },
  appeal_result: { '0': '申诉成功', '1': '申诉失败' },
}
function legacyValue(field: string) {
  const value = record.value.legacySource?.sourcePayload?.[field]
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number' && ['total_amount', 'total_amount_cny'].includes(field)) return value.toFixed(2)
  const raw = String(value)
  return legacyEnumLabels[field]?.[raw] ? `${raw}（${legacyEnumLabels[field][raw]}）` : raw
}
const stageGroups: Record<string, string[]> = {
  todo: ['PENDING_LEADER', 'PENDING_OPERATOR', 'PENDING_ACCEPT'],
  processing: ['PROCESSING'],
  review: ['PENDING_REVIEW'],
  difference: ['WAITING_DIFF'],
  collection: ['WAITING_COLLECTION'],
  completed: ['COMPLETED'],
}
const stageMetrics = computed(() => [
  {
    key: 'todo',
    title: '待办',
    value: activeLines.value.filter((l) => stageGroups.todo.includes(l.lineStatus)).length,
  },
  {
    key: 'processing',
    title: '处理中',
    value: activeLines.value.filter((l) => stageGroups.processing.includes(l.lineStatus)).length,
  },
  {
    key: 'review',
    title: '待审核',
    value: activeLines.value.filter((l) => stageGroups.review.includes(l.lineStatus)).length,
  },
  {
    key: 'difference',
    title: '待匹配差异单',
    value: activeLines.value.filter((l) => stageGroups.difference.includes(l.lineStatus)).length,
  },
  {
    key: 'collection',
    title: '待回款',
    value: activeLines.value.filter((l) => stageGroups.collection.includes(l.lineStatus)).length,
  },
  { key: 'completed', title: '已完成', value: completedCount.value },
])
const lineFilter = reactive({ q: '', status: '', dept: '', leader: '' }),
  departmentNames = computed(() => [
    ...new Set((record.value?.lines || []).map((l) => String(l.departmentName || '')).filter(Boolean)),
  ]),
  leaderNames = computed(() => [
    ...new Set((record.value?.lines || []).map((l) => String(l.leaderName || '')).filter(Boolean)),
  ])
const visibleLines = computed(() =>
  (record.value?.lines || []).filter(
    (line) =>
      (!selectedStage.value || stageGroups[selectedStage.value]?.includes(line.lineStatus)) &&
      (!lineFilter.q ||
        `${line.lineInternalNo}${line.ticketNo || ''}${line.otaOrderNo || ''}${line.pnr || ''}`
          .toLowerCase()
          .includes(lineFilter.q.toLowerCase())) &&
      (!lineFilter.status || line.lineStatus === lineFilter.status) &&
      (!lineFilter.dept || line.departmentName === lineFilter.dept) &&
      (!lineFilter.leader || line.leaderName === lineFilter.leader),
  ),
)
function selectDetailStage(key: string) {
  lineFilter.status = ''
  selectedStage.value = selectedStage.value === key ? '' : key
}
function clearLineFilters() {
  Object.assign(lineFilter, { q: '', status: '', dept: '', leader: '' })
  selectedStage.value = ''
}
const blockingLines = computed(() => record.value.lines.filter(
  (line) => !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus),
))
const canCloseCurrentCase = computed(() => !!record.value.lines.length && !blockingLines.value.length)
const blockerSummary = computed(() => {
  if (!hasRecord.value) return '暂无主单数据，选择或新建ADM主单后显示结案阻断'
  if (isLegacyReadOnly.value) return '旧系统历史记录只读，不进入新系统任务、审核、回款或结案流程'
  if (record.value.case.caseStatus === 'CLOSED') return '主单已结案'
  if (record.value.case.caseStatus === 'VOIDED') return '主单已作废'
  if (record.value.case.caseStatus === 'DRAFT') return '发布草稿后进入处理流程'
  if (!record.value.lines.length) return '暂无订单明细'
  const pending = blockingLines.value
  if (!pending.length) return '全部有效订单及前置事项均已完成，可以结案'
  const counts = new Map<string, number>()
  pending.forEach((line) => counts.set(label(line.lineStatus), (counts.get(label(line.lineStatus)) || 0) + 1))
  return [...counts].map(([name, count]) => `${count}笔${name}`).join('；')
})
const lineRisk = computed(() => {
  const deadline = record.value?.case.replyDeadline
  if (!deadline) return '未设期限'
  const diff = new Date(deadline).getTime() - Date.now()
  return diff < 0 ? '已超时' : diff < 86400000 ? '即将超时' : '正常'
})
function lineTone(status: string) {
  return status === 'COMPLETED'
    ? 'green'
    : status === 'VOIDED'
      ? 'red'
      : ['PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(status)
        ? 'amber'
        : 'blue'
}
function nextTask(line: AdmLine) {
  const returnMode = returnModeFor(line.id)
  if (line.lineStatus === 'PROCESSING' && returnMode === 'SUPPLEMENT') return '补充材料并重新提交审核'
  if (line.lineStatus === 'PROCESSING' && returnMode === 'REAPPEAL') return '重新申诉并提交新的处理结果'
  if (line.lineStatus === 'PROCESSING' && returnMode === 'WITHDRAWN') return '按撤回原因更正后重新提交审核'
  return (
    (
      {
        PENDING_OPERATOR: '组长分配操作人员',
        PENDING_ACCEPT: '操作人员确认接单',
        PROCESSING: '完成恢复、申诉或不申诉并提交审核',
        PENDING_REVIEW: 'ADM负责人审核',
        WAITING_DIFF: '匹配差异单',
        WAITING_COLLECTION: 'ADM负责人登记回款',
        COMPLETED: '已完成',
      } as Fields
    )[line.lineStatus] || '查看处理记录'
  )
}
function readOnlyNotice(scope = '该内容') {
  const isLineScope = scope.includes('订单') || scope.includes('明细') || scope.includes('处理记录')
  if (isLineScope && selectedLine.value?.lineStatus === 'COMPLETED') {
    void message.warning('该订单已完结，不能直接修改。特殊情况请联系ADM负责人发起受控更正。')
    return
  }
  if (isLineScope && selectedLine.value?.reviewStatus === 'APPROVED') {
    void message.warning('该订单已审核通过，不能直接修改。如确需更正，请由ADM负责人先撤回审核并填写原因。')
    return
  }
  void message.warning(
    `当前账号没有${scope}的修改权限，只能查看。如需修改，请联系ADM负责人${record.value.case.coordinatorName ? `“${record.value.case.coordinatorName}”` : ''}。`,
  )
}
function openMasterBasicInfo() {
  if (!canEditMasterBasic.value) readOnlyNotice('主单基础信息')
  masterInfoOpen.value = true
}
function returnWorkbench() {
  const page = Math.max(1, Number(route.query.returnPage || 1))
  const metric = String(route.query.returnMetric || '')
  void router.push({
    path: '/adm/workbench',
    query: {
      ...(page > 1 ? { page: String(page) } : {}),
      ...(metric ? { workMetric: metric } : {}),
    },
  })
}
function canExportLine(line: AdmLine) {
  return (
    record.value.case.caseStatus === 'ACTIVE' &&
    Number(line.operatorId) === myId.value &&
    ['PENDING_ACCEPT', 'PROCESSING'].includes(line.lineStatus)
  )
}
function toggleSelected(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}
function selectFirstBlocker() {
  clearLineFilters()
  const line = activeLines.value.find((item) => item.lineStatus !== 'COMPLETED')
  if (!line) {
    void message.info('当前没有阻断结案的订单')
    return
  }
  openLineDrawer(line)
}
async function openLineDrawer(line: AdmLine) {
  if (!fullDetailLoaded.value) await load(true)
  if (!hasRecord.value || error.value) return
  selectedLineId.value = line.id
  drawerTab.value = canReview.value && line.lineStatus === 'PENDING_REVIEW' ? '审核处理' : '处理决定与结果'
  drawerOpen.value = true
}
async function openLineTask(line: AdmLine, action: string) {
  if (!fullDetailLoaded.value) await load(true)
  const current = record.value.lines.find((item) => Number(item.id) === Number(line.id))
  if (!current || error.value) return
  if (action === 'leader' && !canChangeAdmLeader(current)) {
    void message.warning('操作员已接单，不能更换组长')
    return
  }
  selectedLineId.value = current.id
  openAction(action)
}
function openBasicInfo(line: AdmLine) {
  selectedLineId.value = line.id
  if (!canEditLineBasic(line)) readOnlyNotice('订单基础信息')
  basicInfoOpen.value = true
}
function basicInfoSaved(detail: AdmCaseDetail) {
  record.value = detail
  fullDetailLoaded.value = true
  basicInfoOpen.value = false
  masterInfoOpen.value = false
}

const addLineOpen = ref(false),
  addLineError = ref(''),
  addTargetCaseId = ref<number>(caseId),
  addTargetLoading = ref(false),
  addAmountStep = ref(false),
  addTarget = ref<AdmCaseDetail>(record.value),
  addCases = ref<AdmCaseRow[]>([]),
  addLineForm = reactive<Fields>({}),
  addLineAmounts = reactive<Record<number, string>>({}),
  addMasters = reactive<Record<string, Option[]>>({ department: [], diffType: [], ota: [], supplier: [] })
let addTargetRequest = 0
const fullDetailLoaded = ref(false)
const addOption = (items: Option[]) =>
  items.map((item) => ({ value: item.code, label: `${item.name}（${item.code}）` }))
const filterOption = (input: string, option: Fields) =>
  String(option.label || '').toLowerCase().includes(input.toLowerCase())
const addCaseOptions = computed(() => addCases.value.map((item) => ({
  value: Number(item.id),
  label: `${item.admNo} · ${item.internalNo} · ${item.issuerName} · ${item.currency} ${item.originalAmount}`,
})))
const addDepartmentOptions = computed(() => addOption(addMasters.department)),
  addDiffTypeOptions = computed(() => addMasters.diffType.map((item) => ({ value: item.code, label: item.name }))),
  addOtaOptions = computed(() => addOption(addMasters.ota)),
  addSupplierOptions = computed(() => addOption(addMasters.supplier)),
  addLeaderOptions = computed(() =>
    (config.value?.people.leader || []).map((item) => ({ value: Number(item.id), label: item.name })),
  )
const addActiveLines = computed(() => addTarget.value.lines.filter((line) => line.lineStatus !== 'VOIDED'))
const addLineTotal = computed(
  () =>
    Number(addLineForm.originalAmount || 0) +
    addActiveLines.value.reduce((sum, line) => sum + Number(addLineAmounts[line.id] || 0), 0),
)
const addLineCnyAmount = computed(() => {
  const rate = Number(addTarget.value.fxSnapshot?.rateValue || 0)
  const masterCny = Number((Number(addTarget.value.case.originalAmount || 0) * rate).toFixed(2))
  const existingCny = addActiveLines.value.reduce(
    (sum, line) => sum + Number((Number(addLineAmounts[line.id] || 0) * rate).toFixed(2)), 0,
  )
  return Number.isFinite(masterCny - existingCny) ? (masterCny - existingCny).toFixed(2) : '0.00'
})
const addLineBalanced = computed(
  () =>
    Number.isFinite(addLineTotal.value) &&
    Math.abs(addLineTotal.value - Number(addTarget.value.case.originalAmount || 0)) < 0.005,
)
const isRecoveryAllocation = computed(() => addTarget.value.case.masterRecoveryStatus === 'RECOVERED')
const needsAddLineReason = computed(() => !addTarget.value.case.lineDefaults || !!addActiveLines.value.length)
const addLineReady = computed(
  () =>
    !addTargetLoading.value && Number(addTarget.value.case.id) === Number(addTargetCaseId.value) &&
    addLineBalanced.value &&
    Number(addLineForm.originalAmount) > 0 &&
    addActiveLines.value.every((line) => Number(addLineAmounts[line.id]) > 0) &&
    (!!addTarget.value.case.lineDefaults || (
      !!addLineForm.departmentCode && !!addLineForm.leaderId && !!addLineForm.diffTypeCode &&
      !!String(addLineForm.differenceReason || '').trim()
    )) &&
    (!isRecoveryAllocation.value || !!addLineForm.leaderId) &&
    (!needsAddLineReason.value || !!String(addLineForm.reason || '').trim()),
)
function selectAddOption(kind: string, code?: string) {
  const item = addMasters[kind].find((value) => value.code === code),
    prefix = kind === 'diffType' ? 'diffType' : kind
  addLineForm[`${prefix}Code`] = code || null
  addLineForm[`${prefix}Name`] = item?.name || null
}
function selectAddLeader(id: number) {
  const item = config.value?.people.leader.find((value) => Number(value.id) === Number(id))
  addLineForm.leaderName = item?.name || ''
}
async function loadSelectableCases() {
  const first = await admApi.list({ page: 1, pageSize: 100 })
  const pages = Math.ceil(Number(first.pagination.total || 0) / 100)
  const remaining = pages > 1
    ? await Promise.all(Array.from({ length: pages - 1 }, (_, index) => admApi.list({ page: index + 2, pageSize: 100 })))
    : []
  return [first, ...remaining]
    .flatMap((result) => result.items)
    .filter((item) => ['DRAFT', 'ACTIVE'].includes(item.caseStatus))
}
async function openAddLine() {
  addLineError.value = ''
  Object.keys(addLineForm).forEach((key) => delete addLineForm[key])
  Object.keys(addLineAmounts).forEach((key) => delete addLineAmounts[Number(key)])
  Object.assign(addLineForm, {
    originalAmount: '',
    departmentCode: undefined,
    departmentName: '',
    leaderId: undefined,
    leaderName: '',
    diffTypeCode: undefined,
    diffTypeName: '',
    differenceReason: '',
    investigationNote: '',
    otaCode: undefined,
    otaName: '',
    otaOrderNo: '',
    supplierCode: undefined,
    supplierName: '',
    airlineName: '',
    ticketNo: '',
    pnr: '',
    reason: '',
  })
  addAmountStep.value = false
  addTargetRequest++
  addTargetLoading.value = false
  addTargetCaseId.value = caseId
  addTarget.value = record.value
  if (isRecoveryAllocation.value) addLineForm.leaderId = record.value.case.lineDefaults?.leaderId
  resetAddLineAmounts()
  addLineOpen.value = true
  try {
    const [selectableCases, department, diffType, ota, supplier] = await Promise.all([
      isRecoveryAllocation.value ? Promise.resolve([]) : loadSelectableCases(),
      addTarget.value.case.lineDefaults ? Promise.resolve([]) : admApi.options('department', '', 200),
      addTarget.value.case.lineDefaults ? Promise.resolve([]) : admApi.options('diffType', '', 200),
      admApi.options('ota', '', 200),
      isRecoveryAllocation.value ? Promise.resolve([]) : admApi.options('supplier', '', 200),
    ])
    addCases.value = selectableCases
    if (!addCases.value.some((item) => Number(item.id) === caseId)) addCases.value.unshift(record.value.case)
    Object.assign(addMasters, { department, diffType, ota, supplier })
  } catch (e) {
    addLineError.value = errorText(e)
  }
}
function resetAddLineAmounts() {
  Object.keys(addLineAmounts).forEach((key) => delete addLineAmounts[Number(key)])
  addActiveLines.value.forEach((line) => { addLineAmounts[line.id] = String(line.originalAmount) })
  addLineForm.originalAmount = addTarget.value.case.lineDefaults && !addActiveLines.value.length
    ? String(addTarget.value.case.originalAmount)
    : ''
}
async function selectAddCase(id: number) {
  const seq = ++addTargetRequest
  addTargetLoading.value = true
  addLineError.value = ''
  try {
    const target = Number(id) === Number(record.value.case.id) ? record.value : await admApi.detail(id)
    if (seq !== addTargetRequest) return
    addTarget.value = target
    resetAddLineAmounts()
    if (!target.case.lineDefaults && !addMasters.department.length) {
      const [department, diffType] = await Promise.all([admApi.options('department', '', 200), admApi.options('diffType', '', 200)])
      if (seq === addTargetRequest) Object.assign(addMasters, { department, diffType })
    }
  } catch (e) {
    if (seq === addTargetRequest) {
      addTargetCaseId.value = Number(addTarget.value.case.id)
      addLineError.value = errorText(e)
    }
  } finally {
    if (seq === addTargetRequest) addTargetLoading.value = false
  }
}
async function submitAddLine() {
  if (!addLineReady.value) return
  addLineError.value = ''
  saving.value = true
  try {
    const { reason, ...line } = addLineForm
    const targetCaseId = Number(addTargetCaseId.value)
    await admApi.addLine(targetCaseId, {
      line,
      reason,
      existingAmounts: addActiveLines.value.map((item) => ({ lineId: item.id, originalAmount: addLineAmounts[item.id] })),
    })
    addLineOpen.value = false
    void message.success('订单已新增，明细金额已同步调整')
    if (targetCaseId !== caseId) {
      await router.push(`/adm/cases/${targetCaseId}`)
      return
    }
    await load()
  } catch (e) {
    addLineError.value = errorText(e)
  } finally {
    saving.value = false
  }
}
async function load(full = fullDetailLoaded.value) {
  if (!caseId) return
  loading.value = true
  error.value = ''
  try {
    record.value = full ? await admApi.detail(caseId) : await admApi.summary(caseId)
    fullDetailLoaded.value = full
    if (!selectedLineId.value || !record.value.lines.some((line) => Number(line.id) === Number(selectedLineId.value)))
      selectedLineId.value = record.value.lines[0]?.id || null
  } catch (e) {
    record.value = emptyRecord()
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
const lineRecords = (key: keyof AdmCaseDetail) =>
  ((record.value?.[key] as Fields[]) || []).filter(
    (item) => item.lineId != null && Number(item.lineId) === Number(selectedLineId.value),
  )
const masterOperationsOpen = ref(false)
const caseOperationLogs = computed(() => record.value.operationLogs.filter((item) => item.lineId == null))
async function openMasterOperations() {
  if (!fullDetailLoaded.value) await load(true)
  if (hasRecord.value && !error.value) masterOperationsOpen.value = true
}
const latestReviewFor = (lineId: number) => ((record.value.reviews || []) as Fields[])
    .filter((item) => Number(item.lineId) === Number(lineId)).at(-1),
  returnModeFor = (lineId: number) => {
    const review = latestReviewFor(lineId)
    const line = record.value.lines.find((item) => Number(item.id) === Number(lineId))
    if (line?.reviewStatus === 'WITHDRAWN') return 'WITHDRAWN'
    if (review?.result === 'WITHDRAWN') return 'WITHDRAWN'
    const reason = String(review?.returnReason || '')
    if (reason.startsWith('【驳回补充材料】')) return 'SUPPLEMENT'
    if (reason.startsWith('【驳回重新申诉】')) return 'REAPPEAL'
    if (review?.result === 'RETURNED' || line?.reviewStatus === 'RETURNED') return 'SUPPLEMENT'
    return ''
  },
  cleanReturnReason = (value: unknown) => String(value || '')
    .replace(/^【驳回补充材料】/, '').replace(/^【驳回重新申诉】/, ''),
  latestReview = computed(() => selectedLine.value ? latestReviewFor(selectedLine.value.id) : undefined),
  selectedReturnMode = computed(() => selectedLine.value ? returnModeFor(selectedLine.value.id) : ''),
  latestRecovery = computed(() => lineRecords('recoveries').at(-1)),
  activeAppeal = computed(() => lineRecords('appeals').find((item) => item.status === 'IN_PROGRESS'))
const recoveryTitle = computed(() => ({
    UNDECIDED: '待判断',
    NOT_REQUIRED: '无需恢复编码',
    WAITING: '等待人工恢复',
    REMINDER_DUE: '恢复完成待确认',
    CONFIRMED: '已恢复并处理',
  } as Fields)[selectedLine.value?.recoveryStatus || 'UNDECIDED'] || label(selectedLine.value?.recoveryStatus)),
  recoveryCopy = computed(() => ({
    UNDECIDED: '本笔订单是否需要恢复编码尚未判断，完成判断后才能继续提交处理结果。',
    NOT_REQUIRED: '本笔订单已确认无需恢复编码，可以继续记录申诉决定和最终结果。',
    WAITING: '已记录需要恢复编码，等待线下人工完成后由当前操作员确认。',
    REMINDER_DUE: '系统已提醒恢复结果待查看，请确认线下结果并继续处理。',
    CONFIRMED: '恢复编码已由操作员确认完成并处理。',
  } as Fields)[selectedLine.value?.recoveryStatus || 'UNDECIDED']),
  appealTitle = computed(() => ({
    UNDECIDED: '待决定是否申诉',
    IN_PROGRESS: '申诉处理中',
    SUCCEEDED: '申诉成功',
    FAILED: '申诉失败',
    NO_APPEAL: '不申诉',
  } as Fields)[selectedLine.value?.appealStatus || 'UNDECIDED'] || label(selectedLine.value?.appealStatus)),
  appealCopy = computed(() => ({
    UNDECIDED: '尚未记录申诉决定，请根据实际处理选择发起申诉或不申诉。',
    IN_PROGRESS: '申诉已在系统外发起，等待登记实际最终结果。',
    SUCCEEDED: '申诉成功，本笔无需匹配差异单；负责人审核时确认是否需要回款。',
    FAILED: '申诉失败，负责人审核通过后进入差异单匹配，不进入回款流程。',
    NO_APPEAL: '已决定不申诉，需记录问题归因并提交负责人审核。',
  } as Fields)[selectedLine.value?.appealStatus || 'UNDECIDED'])
const visibleTransfers = computed(() => lineRecords('transfers').filter((item) =>
  isCaseOwner.value ||
  [item.requestedById, item.fromOperatorId, item.toOperatorId].some((id) => Number(id) === myId.value),
).slice().reverse())
function isTransferActionable(item: Fields) {
  return item.status === 'PENDING' && record.value.case.caseStatus === 'ACTIVE' &&
    !!selectedLine.value && !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(selectedLine.value.lineStatus) &&
    Number(item.targetRole === 'LEADER' ? selectedLine.value.leaderId : selectedLine.value.operatorId) === Number(item.fromOperatorId)
}
function transferResultText(item: Fields) {
  if (item.status === 'PENDING') return isTransferActionable(item) ? '待确认' : '待确认 · 当前状态不可处理'
  return ({ ACCEPTED: '已接受', REJECTED: '已拒绝' } as Record<string, string>)[item.status] || label(item.status)
}
const pendingTargetTransfer = computed(() => visibleTransfers.value.find((item) =>
  (item.targetRole === 'LEADER' ? canAssignOperator.value : canHandle.value) &&
  isTransferActionable(item) && Number(item.toOperatorId) === myId.value,
))
function lineDiffMatchLabel(line: AdmLine) {
  if (line.appealStatus === 'SUCCEEDED') return '无需匹配'
  if (!['FAILED', 'NO_APPEAL'].includes(String(line.appealStatus || '')) || line.reviewStatus !== 'APPROVED') {
    return '未开始'
  }
  return diffMatchLabel(line.diffMatchStatus)
}
function lineDiffMatchTone(line: AdmLine) {
  const display = lineDiffMatchLabel(line)
  if (display === '已录入') return 'green'
  if (['未匹配', '未录入', '查询失败', '未连接'].includes(display)) return 'red'
  return 'blue'
}
const canWithdrawReview = computed(
  () =>
    isCaseOwner.value &&
    canManage.value &&
    !!selectedLine.value &&
    ['WAITING_DIFF', 'WAITING_COLLECTION', 'COMPLETED'].includes(selectedLine.value.lineStatus) &&
    lineRecords('reviews').some((item) => item.result === 'APPROVED' && !item.withdrawnFlag) &&
    !lineRecords('collections').some((item) => item.recordStatus === 'VALID'),
)
const operatorOptions = computed(() => admPersonOptions(config.value?.people.handle || [], true))
const leaderOptions = computed(() => admPersonOptions(config.value?.people.leader || [], true))
const assignmentAction = computed(() => ['assign', 'leader', 'transfer'].includes(actionName.value))
const peopleLoading = ref(false)
async function loadPeople() {
  if (peopleLoading.value) return
  peopleLoading.value = true
  try {
    config.value = await admApi.config()
    configError.value = ''
  } catch (e) {
    configError.value = `人员与权限配置加载失败：${errorText(e)}`
  } finally {
    peopleLoading.value = false
  }
}
const appealResultOptions = computed(() =>
  (config.value?.appealResults || []).map((value) => ({
    value,
    label: ({ SUCCEEDED: '成功', FAILED: '失败' } as Fields)[value],
  })),
)
const attributionOptions = [
  { value: 'HUMAN', label: '人为问题' },
  { value: 'PLATFORM', label: '平台问题' },
  { value: 'SYSTEM', label: '系统问题' },
]

const actionOpen = ref(false),
  actionName = ref(''),
  actionError = ref(''),
  actionForm = reactive<Fields>({})
const actionTitles: Fields = {
  assign: '分配操作员',
  leader: '更换组长',
  transfer: '发起转派',
  transferReject: '拒绝转派',
  note: '订单情况说明',
  recovery: '恢复选择',
  appeal: '记录申诉',
  appealResult: '登记申诉结果',
  noAppeal: '登记不申诉',
  review: '负责人审核',
  withdrawReview: '撤回已通过审核',
  collection: '登记回款',
  rebalance: '调整全部有效明细金额',
  voidLine: '作废明细',
  voidCase: '作废主单',
  deleteDraft: '删除草稿',
}
const needsReason = computed(() =>
  [
    'assign',
    'leader',
    'transfer',
    'transferReject',
    'recovery',
    'noAppeal',
    'withdrawReview',
    'rebalance',
    'voidLine',
    'voidCase',
    'deleteDraft',
  ].includes(actionName.value),
)
const reasonRequired = computed(() =>
  actionName.value === 'recovery'
    ? actionForm.decision === 'NOT_NEEDED'
    : actionName.value !== 'assign',
)
const reasonLabel = computed(
  () =>
    (({ recovery: '无需恢复原因', noAppeal: '不申诉原因', leader: '更换原因', transfer: '转派原因' }) as Fields)[
      actionName.value
    ] || '原因/说明',
)
const appealPartyName = computed(() => {
  const type = actionForm.appealTarget
  const line = selectedLine.value
  if (type === record.value.case.issuerType) return record.value.case.issuerName
  return ({ PLATFORM: line?.otaName, AIRLINE: line?.airlineName, SUPPLIER: line?.supplierName } as Fields)[type]
})
function amountInCents(value: unknown): bigint | null {
  const parts = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(value ?? '').trim())
  if (!parts) return null
  return BigInt(parts[1]) * 100n + BigInt((parts[2] || '').padEnd(2, '0'))
}
function centsText(amount: bigint) {
  return `${amount / 100n}.${String(amount % 100n).padStart(2, '0')}`
}
const collectionBalance = computed(() => {
  const expected = amountInCents(selectedLine.value?.expectedCollectionAmount) ?? 0n
  const collected = amountInCents(selectedLine.value?.collectedAmount) ?? 0n
  const current = expected > collected ? expected - collected : 0n
  const amount = amountInCents(actionForm.amount)
  const over = amount !== null && amount > current
  return {
    current: centsText(current),
    projected: amount === null ? null : centsText(over ? 0n : current - amount),
    over,
  }
})
function canTransferOrder(line: Fields) {
  return record.value.case.caseStatus === 'ACTIVE' && !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus) &&
    ((canAssignOperator.value && Number(line.leaderId) === myId.value) ||
      (canHandle.value && Number(line.operatorId) === myId.value))
}
function openAction(name: string) {
  actionName.value = name
  actionError.value = ''
  Object.keys(actionForm).forEach((key) => delete actionForm[key])
  if (name === 'transfer') actionForm.targetRole = canAssignOperator.value && Number(selectedLine.value?.leaderId) === myId.value ? 'LEADER' : 'OPERATOR'
  if (name === 'recovery') actionForm.decision = 'NEEDED'
  if (name === 'review') Object.assign(actionForm, { result: 'APPROVED', collectionRequired: undefined, returnType: 'SUPPLEMENT' })
  if (name === 'collection') {
    actionForm.receivedDate = new Date().toISOString().slice(0, 10)
    actionForm.attachmentIds = []
    collectionFile.value = null
  }
  if (name === 'note') actionForm.investigationNote = selectedLine.value?.investigationNote || ''
  if (name === 'rebalance')
    actionForm.amounts = Object.fromEntries(activeLines.value.map((line) => [line.id, line.originalAmount]))
  actionOpen.value = true
  if (assignmentAction.value) void loadPeople()
}
function openRecoveryAction(decision: 'NEEDED' | 'NOT_NEEDED') {
  openAction('recovery')
  actionForm.decision = decision
}
function rejectPendingTransfer(lineId: number) {
  const transfer = pendingTargetTransfer.value
  if (!transfer) throw new Error('待处理转派已变化，请刷新')
  return admApi.decideTransfer(caseId, lineId, transfer.id, false, actionForm.reason)
}
async function submitAction() {
  if (saving.value || (!selectedLine.value && !['voidCase', 'deleteDraft'].includes(actionName.value))) return
  if (assignmentAction.value && !Number(actionName.value === 'leader' ? actionForm.leaderId : actionForm.operatorId)) {
    actionError.value = '请选择可分配的人员'
    return
  }
  if (actionName.value === 'appeal' && !actionForm.appealTarget) {
    actionError.value = '请选择申诉对象'
    return
  }
  if (actionName.value === 'appealResult' && !actionForm.result) {
    actionError.value = '请选择申诉结果'
    return
  }
  saving.value = true
  actionError.value = ''
  const lineId = selectedLine.value?.id || 0
  try {
    if (['appeal', 'noAppeal'].includes(actionName.value) &&
        ['WAITING', 'REMINDER_DUE'].includes(String(selectedLine.value?.recoveryStatus || ''))) {
      await admApi.recoveryConfirm(caseId, lineId)
    }
    if (actionName.value === 'collection' && collectionFile.value) {
      const uploaded = await admApi.upload(caseId, collectionFile.value, 'COLLECTION', lineId)
      const attachmentId = Number(uploaded.uploadedAttachmentId)
      if (!Number.isSafeInteger(attachmentId) || attachmentId < 1)
        throw new Error('回款凭证已上传，请刷新并选择这次上传的附件后再登记')
      record.value = uploaded
      actionForm.attachmentIds = [...new Set([...(actionForm.attachmentIds || []), attachmentId])]
      collectionFile.value = null
    }
    const calls: Fields = {
      assign: () => admApi.assignOperator(caseId, lineId, actionForm),
      leader: () => admApi.changeLeader(caseId, lineId, actionForm),
      transfer: () => admApi.transfer(caseId, lineId, actionForm),
      transferReject: () => rejectPendingTransfer(lineId),
      note: () => admApi.investigationNote(caseId, lineId, actionForm.investigationNote),
      recovery: () => admApi.recoveryDecision(caseId, lineId, actionForm),
      appeal: () => admApi.startAppeal(caseId, lineId, actionForm),
      appealResult: () => admApi.finishAppeal(caseId, lineId, actionForm),
      noAppeal: () => admApi.noAppeal(caseId, lineId, actionForm),
      review: () => admApi.review(caseId, lineId, actionForm),
      withdrawReview: () => admApi.withdrawReview(caseId, lineId, actionForm.reason),
      collection: () => admApi.collection(caseId, lineId, { ...actionForm }),
      rebalance: () =>
        admApi.rebalanceLines(caseId, {
          reason: actionForm.reason,
          lines: activeLines.value.map((line) => ({ lineId: line.id, originalAmount: actionForm.amounts[line.id] })),
        }),
      voidLine: () => admApi.voidLine(caseId, lineId, actionForm.reason),
      voidCase: () => admApi.voidCase(caseId, actionForm.reason),
      deleteDraft: () => admApi.deleteDraft(caseId, actionForm.reason),
    }
    await calls[actionName.value]()
    actionOpen.value = false
    void message.success('操作已保存')
    if (actionName.value === 'deleteDraft') await router.push('/adm/cases')
    else await load()
  } catch (e) {
    actionError.value = errorText(e)
  } finally {
    saving.value = false
  }
}
async function publishDraft() {
  try {
    saving.value = true
    await admApi.publishDraft(caseId)
    void message.success('草稿已发布，现已进入正式办理流程')
    selectedIds.value = []
    await load()
  } catch (e) {
    void message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function decidePendingTransfer(accepted: boolean) {
  if (saving.value || !selectedLine.value || !pendingTargetTransfer.value) return
  try {
    saving.value = true
    await admApi.decideTransfer(caseId, selectedLine.value.id, pendingTargetTransfer.value.id, accepted)
    void message.success('已接受转派')
    await load()
  } catch (e) {
    void message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function runSimple(name: string) {
  if (saving.value || (!selectedLine.value && name !== 'close')) return
  if (name === 'close' && !canCloseCurrentCase.value) return
  try {
    saving.value = true
    const id = selectedLine.value?.id || 0
    if (name === 'accept') await admApi.accept(caseId, id)
    else if (name === 'recoveryConfirm') await admApi.recoveryConfirm(caseId, id)
    else if (name === 'submitReview') await admApi.submitReview(caseId, id)
    else if (name === 'checkDifference') await admApi.checkDifference(caseId, id)
    else if (name === 'close') await admApi.close(caseId)
    void message.success('操作成功')
    await load()
  } catch (e) {
    void message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function exportSelected() {
  try {
    saving.value = true
    const task = await exportTasks.createBackground('adm_operator_excel', { lineIds: selectedIds.value })
    selectedIds.value = []
    void message.success(
      task.reused ? '相同ADM导出任务正在进行，已打开导出任务' : '已接单并生成导出任务，请在页头“导出任务”下载',
    )
    await load()
  } catch (e) {
    void message.error(errorText(e))
  } finally {
    saving.value = false
  }
}

const attachmentCategoryLabels: Record<string, string> = {
  ADM_ORIGINAL: 'ADM原始附件',
  APPEAL: '申诉附件',
  COLLECTION: '回款凭证',
  OTHER: '其他附件',
}
const attachmentCategoryLabel = (value: unknown) => attachmentCategoryLabels[String(value || '')] || String(value || '未分类')
const masterAttachmentCategory = ref('ADM_ORIGINAL'),
  lineAttachmentCategory = ref('APPEAL'),
  masterAttachmentFile = ref<File | null>(null),
  lineAttachmentFile = ref<File | null>(null),
  masterAttachmentInput = ref<HTMLInputElement | null>(null),
  lineAttachmentInput = ref<HTMLInputElement | null>(null),
  lineAttachmentSection = ref<HTMLElement | null>(null),
  collectionFile = ref<File | null>(null)
const attachmentOptions = computed(() =>
    (config.value?.attachmentCategories || []).map((value) => ({ value, label: attachmentCategoryLabel(value) })),
  ),
  masterAttachmentOptions = computed(() => attachmentOptions.value.filter((item) => ['ADM_ORIGINAL', 'OTHER'].includes(item.value))),
  lineAttachmentOptions = computed(() => attachmentOptions.value.filter((item) => item.value !== 'ADM_ORIGINAL')),
  activeAttachments = computed(() => (record.value?.attachments || []).filter((item) => item.recordStatus === 'ACTIVE')),
  masterAttachments = computed(() => activeAttachments.value.filter((item) => item.sourceLineId == null)),
  selectedLineAttachments = computed(() => activeAttachments.value.filter(
    (item) => Number(item.sourceLineId) === Number(selectedLineId.value),
  )),
  currentAvailableAttachments = computed(() => [...masterAttachments.value, ...selectedLineAttachments.value])
const canUploadAttachment = computed(() => {
  if (!hasRecord.value || isLegacyReadOnly.value || !['DRAFT', 'ACTIVE'].includes(record.value.case.caseStatus)) return false
  if (isCaseOwner.value) return true
  return record.value.case.caseStatus === 'ACTIVE' && activeLines.value.some(
    (line) => !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus) &&
      [Number(line.leaderId), Number(line.operatorId)].includes(myId.value),
  )
})
const canUploadSelectedLineAttachment = computed(() => {
  if (!canUploadAttachment.value || !selectedLine.value) return false
  if (isCaseOwner.value) return true
  return !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(selectedLine.value.lineStatus) &&
    [Number(selectedLine.value.leaderId), Number(selectedLine.value.operatorId)].includes(myId.value)
})
function pickMasterAttachment(event: Event) {
  masterAttachmentFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
function pickLineAttachment(event: Event) {
  lineAttachmentFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
function pickCollectionFile(event: Event) {
  collectionFile.value = (event.target as HTMLInputElement).files?.[0] || null
}
function openLineAttachments(category = 'APPEAL') {
  lineAttachmentCategory.value = category
  drawerTab.value = '附件'
  void nextTick(() => lineAttachmentSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}
async function uploadScopedAttachment(scope: 'CASE' | 'LINE') {
  const file = scope === 'CASE' ? masterAttachmentFile.value : lineAttachmentFile.value
  const category = scope === 'CASE' ? masterAttachmentCategory.value : lineAttachmentCategory.value
  if (!file || (scope === 'LINE' && !selectedLine.value)) return
  try {
    saving.value = true
    await admApi.upload(caseId, file, category, scope === 'LINE' ? selectedLine.value?.id : undefined)
    if (scope === 'CASE') {
      masterAttachmentFile.value = null
      if (masterAttachmentInput.value) masterAttachmentInput.value.value = ''
    } else {
      lineAttachmentFile.value = null
      if (lineAttachmentInput.value) lineAttachmentInput.value.value = ''
    }
    await load()
    void message.success(scope === 'CASE' ? '主单公共附件上传成功' : '当前明细附件上传成功')
  } catch (e) {
    void message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
async function previewFile(item: Fields) {
  try {
    const response = await admApi.file(caseId, item.id, 'preview')
    const url = URL.createObjectURL(response.data)
    window.open(url, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (e) {
    void message.error(errorText(e))
  }
}
async function queueAttachmentExport(item: Fields) {
  try {
    const task = await exportTasks.createBackground('adm_attachment', { caseId, attachmentId: item.id })
    void message.success(task.reused ? '相同附件任务正在进行，已打开导出任务' : '附件原件已加入导出任务，请在页头下载')
  } catch (e) {
    void message.error(errorText(e))
  }
}
function voidAttachment(item: Fields) {
  Modal.confirm({
    title: `作废附件 ${item.originalFileName}`,
    content: '作废后记录保留，但不再作为有效附件。',
    okText: '确定作废',
    cancelText: '取消',
    async onOk() {
      await admApi.voidAttachment(caseId, item.id, '负责人确认作废错误附件')
      await load()
    },
  })
}
onMounted(async () => {
  if (!caseId) return
  const configRequest = loadPeople()
  const taskAction = String(route.query.taskAction || '')
  await Promise.all([load(!!taskAction), configRequest])
  if (route.query.addLine === '1' && canAddLine.value) void openAddLine()
  const requestedStatus = String(route.query.lineStatus || '')
  if (record.value.lines.some((line) => line.lineStatus === requestedStatus)) lineFilter.status = requestedStatus
  if (!taskAction) return
  const line = selectedLine.value
  if (!line || Number(line.id) !== Number(route.query.lineId)) {
    if (hasRecord.value) void message.warning('该订单明细已变化，请从详情重新选择')
    return
  }
  if (record.value.case.caseStatus === 'ACTIVE') {
    if (taskAction === 'assignLeader' && line.lineStatus === 'PENDING_LEADER' && canChangeAdmLeader(line) && isCaseOwner.value && canAssignLeader.value) {
      openAction('leader')
      return
    }
    if (taskAction === 'assign' && line.lineStatus === 'PENDING_OPERATOR' && isCurrentLeader.value) {
      openAction('assign')
      return
    }
  }
  const taskTabs: Record<string, string> = {
    review: '审核处理', diff: '负责人跟进', collection: '负责人跟进',
    transferAccept: '转派记录', transferHistory: '转派记录',
  }
  drawerTab.value = taskTabs[taskAction] || '处理决定与结果'
  drawerOpen.value = true
})
</script>

<style scoped>
.detail-card-head,
.drawer-line-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-bottom: 1px solid #e9edf3;
}
.detail-card-head h2 {
  margin: 0;
  color: #27364e;
  font-size: 15px;
}
.detail-card-head small,
.drawer-line-head small {
  display: block;
  margin-top: 5px;
  color: #8995a7;
  font-size: 10px;
}
.drawer-line-head {
  padding: 0 0 14px;
  margin-bottom: 14px;
}
.process-actions {
  margin-bottom: 14px;
}
.detail-descriptions {
  margin-bottom: 16px;
}
.upload {
  display: grid;
  grid-template-columns: 150px 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}
.amount-adjustments {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 10px 0 16px;
}
.amount-adjustments label {
  display: grid;
  gap: 6px;
  color: #526174;
  font-size: 12px;
}
.block {
  margin-bottom: 16px;
}
@media (max-width: 700px) {
  .upload,
  .amount-adjustments {
    grid-template-columns: 1fr;
  }
}
</style>
