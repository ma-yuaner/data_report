<template>
  <div class="v05-app embedded">
    <main class="v05-main">
      <header class="v05-top">
        <div><h1>ADM 任务台账</h1><p>按当前责任办理待办，也可查看全部主单与订单明细。</p></div>
        <a-space wrap>
          <a-button v-if="canCreate" @click="openImport">跨主单批量导入</a-button>
          <a-button v-if="canCreate" type="primary" @click="openCreate">新建 ADM 主单</a-button>
        </a-space>
      </header>
      <section class="v05-card adm-flow" aria-label="ADM 业务流转">
        <strong>业务流转</strong>
        <ol><li v-for="step in workflowSteps" :key="step">{{ step }}</li></ol>
      </section>
      <a-tabs :active-key="isWorkbench ? 'mine' : 'all'" @change="switchScope">
        <a-tab-pane key="mine" tab="我的待办" />
        <a-tab-pane key="all" tab="全部记录" />
      </a-tabs>
      <section v-if="isWorkbench" class="v05-page">
        <div class="v05-toolbar">
          <a-space wrap>
            <a-select :value="workMetric" aria-label="待办阶段" style="width: 180px"
              :options="workPhaseOptions" @change="selectWorkPhase" />
            <a-button v-if="canCloseWorkQueue" @click="openWorkMetric('close')">可以结案</a-button>
            <a-button v-if="canTransferWorkQueue" @click="openWorkMetric('transfer')">转派记录</a-button>
            <a-button v-if="canOperatorWork" :disabled="!exportCandidates.length" @click="openExportSelection">接单并导出</a-button>
            <a-button v-if="canOperatorWork" @click="operatorImportOpen = true">导入处理结果</a-button>
            <a-button :disabled="loading" @click="load">刷新</a-button>
          </a-space>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <a-alert v-if="configError" type="warning" show-icon :message="configError" />
        <a-alert v-if="workbenchSummary.truncated" type="warning" show-icon
          :message="`当前显示前 ${workbenchItems.length} 条任务，共 ${workbenchSummary.total} 条；分类数仅统计已加载任务。`" />
        <a-space v-if="batchRows.length" wrap class="block">
          <span>已选 {{ batchRows.length }} 条</span>
          <a-button v-for="action in batchActions" :key="action" @click="openWorkbenchBatch(action)">
            {{ workbenchActionLabels[action] }}
          </a-button>
          <span v-if="!batchActions.length">请选择同一阶段且可执行同一操作的任务</span>
          <a-button type="link" @click="workSelection = []">清除选择</a-button>
        </a-space>
        <div class="v05-work-list">
          <p v-if="loading" class="v05-card v05-empty" role="status">正在读取 ADM 任务…</p>
          <p v-else-if="error" class="v05-card v05-empty"><a-button @click="load">重试</a-button></p>
          <div v-else-if="pagedTasks.length" class="work-task-table">
            <div class="work-task-row work-task-head">
              <a-checkbox aria-label="选择当前页任务"
                :checked="!!pagedTasks.length && pagedTasks.every((task) => workSelection.includes(workTaskKey(task)))"
                @change="selectWorkbenchPage" />
              <span>ADM / 内部明细</span><span>任务类型</span><span>当前责任分配</span><span>当前需要处理</span><span>处理截止</span><span>操作</span>
            </div>
            <div v-for="task in pagedTasks" :key="workTaskKey(task)" class="work-task-row">
              <a-checkbox :aria-label="`选择 ${task.lineInternalNo || task.admNo}`"
                :checked="workSelection.includes(workTaskKey(task))"
                @change="toggleWorkbenchTask(task)" />
              <div>
                <a-button type="link" @click="openTask(task)">{{ task.admNo || task.internalNo }}</a-button>
                <small>{{ task.lineInternalNo || '主单' }}</small>
                <a-tag v-if="task.leaderOverdueAt" color="red">组长分派超 3 天</a-tag>
                <a-tag v-if="task.operatorOverdueAt" color="red">操作员分派超 3 天</a-tag>
                <a-tag v-if="task.hasTransfer || task.transferId" color="blue">转派</a-tag>
              </div>
              <span class="work-task-type">{{ task.role }}任务：{{ task.title }}</span>
              <span>{{ task.assignment }}</span>
              <span>{{ task.requiredAction }}</span>
              <b :class="{ danger: task.overdue }">{{ dateText(task.deadline) }}</b>
              <a-button
                v-if="canAcceptTask(task)"
                type="primary"
                :loading="acceptingLines.has(Number(task.lineId))"
                @click="acceptTask(task)"
              >接单</a-button>
              <a-button v-else-if="task.kind === 'leaderRecovery'" type="primary" @click="openWorkbenchBatch('recovery', [task])">恢复判断</a-button>
              <a-button v-else-if="task.kind === 'ownerRecovery'" type="primary" @click="openWorkbenchBatch('startRecovery', [task])">正在恢复</a-button>
              <a-button v-else-if="task.kind === 'recovered'" type="primary" @click="openTask(task)">录入明细</a-button>
              <a-button v-else-if="task.kind === 'transferAccept'" type="primary" @click="openWorkbenchBatch('transferAccept', [task])">确认转派</a-button>
              <a-button v-else-if="task.kind === 'assign' || task.kind === 'assignLeader'" type="primary"
                @click="openWorkbenchBatch(task.kind, [task])">{{ workbenchActionLabels[task.kind] }}</a-button>
            </div>
          </div>
          <div v-if="workbenchReady && !loading && !error && !visibleTasks.length" class="v05-card v05-empty">
            {{ workMetric ? '当前筛选下没有待办任务' : '当前账号暂无需要处理的ADM任务' }}
          </div>
        </div>
        <div v-if="workbenchReady && !error && visibleTasks.length" class="v05-pager">
          <a-pagination v-model:current="workPage" :page-size="workPageSize" :total="visibleTasks.length"
            :show-size-changer="false" :disabled="loading" :show-total="taskTotalText" />
        </div>
      </section>

      <section v-else class="v05-page">
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <a-alert v-if="configError" type="warning" show-icon :message="configError" />
        <div class="v05-card">
          <div class="v05-toolbar">
            <a-space wrap>
              <a-input v-model:value="filters.search" allow-clear aria-label="搜索 ADM 台账"
                placeholder="ADM 单号、内部主单编号、下发方" style="width: min(300px, 65vw)" @press-enter="query" />
              <a-select v-model:value="filters.status" aria-label="主单状态" style="width: 140px"
                :options="[{ value: '', label: '全部状态' }, ...(config?.caseStatuses || []).map((status) => ({ value: status, label: label(status) }))]"
                @change="query" />
              <a-button type="primary" :loading="loading" @click="query">查询</a-button>
              <a-button @click="resetFilters">重置</a-button>
              <a-select :value="metric" aria-label="主单范围" style="width: 150px"
                :options="masterScopeOptions" @change="selectMetric" />
              <a-button @click="openGlobalOrders('all')">订单明细</a-button>
            </a-space>
          </div>
          <div class="v05-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ADM 单号 / 下发方</th>
                  <th>金额</th>
                  <th>处理截止</th>
                  <th>订单进度</th>
                  <th>阶段分布</th>
                  <th>当前状态</th>
                  <th>结案阻断</th>
                  <th>风险标签</th>
                  <th>最近更新</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="record in shownRows" :key="record.id">
                  <td>
                    <button class="link" @click="openMasterInfo(record)">{{ record.admNo }}</button
                    ><small>{{ label(record.issuerType) }} · {{ record.issuerName }}</small
                    ><small>系统记录：{{ record.internalNo }}</small>
                    <span :class="['source-badge', sourceTone(record.sourceType)]">{{ sourceText(record.sourceType) }}</span>
                  </td>
                  <td>
                    <b>{{ record.currency }} {{ record.originalAmount }}</b
                    ><small>折合人民币 ¥ {{ record.cnyAmount }}</small>
                  </td>
                  <td>
                    {{ dateText(record.replyDeadline) }}<small>{{ riskText(record) }}</small>
                  </td>
                  <td>
                    <div class="progress"><i :style="{ width: progressWidth(record) }"></i></div>
                    <small>{{ Number(record.completedLineCount || 0) }} / {{ activeLineCount(record) }} 已完成</small>
                  </td>
                  <td>
                    <div class="stage-list">
                      <span v-for="stage in stageSummary(record)" :key="stage.label"
                        ><i></i>{{ stage.label }}<b>{{ stage.count }}</b></span
                      >
                    </div>
                  </td>
                  <td>
                    <span :class="['pill', statusTone(record.caseStatus)]">● {{ label(record.caseStatus) }}</span>
                  </td>
                  <td>{{ blockerText(record) }}</td>
                  <td>
                    <span :class="['pill', riskTone(record)]">{{ riskText(record) }}</span>
                  </td>
                  <td>{{ dateText(record.updatedAt) }}</td>
                  <td>
                    <div class="record-actions master-record-actions">
                      <a-button type="primary" @click="openCase(record)">{{ ledgerDetailText(record) }}</a-button>
                      <a-dropdown v-if="ledgerStages(record).length > 1" :trigger="['click']">
                        <a-button>按阶段查看</a-button>
                        <template #overlay>
                          <a-menu @click="({ key }: { key: string | number }) => openCase(record, String(key))">
                            <a-menu-item v-for="stage in ledgerStages(record)" :key="stage.status">
                              {{ stage.title }}（{{ stage.count }}）
                            </a-menu-item>
                          </a-menu>
                        </template>
                      </a-dropdown>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="loading" class="empty" role="status">正在读取 ADM 台账…</div>
            <div v-else-if="error" class="empty"><button @click="load">重试读取台账</button></div>
            <div v-else-if="ledgerReady && !rows.length" class="empty">暂无符合条件的 ADM 主单</div>
          </div>
          <div class="v05-pager">
            <a-pagination
              :current="page"
              :page-size="pageSize"
              :total="total"
              :disabled="loading || !!error"
              :show-total="recordTotalText"
              :page-size-options="['10', '20', '50', '100']"
              show-size-changer
              @change="changeLedgerPage"
            />
          </div>
        </div>
      </section>
    </main>

    <a-modal v-model:open="workbenchBatchOpen" :title="workbenchActionLabels[workbenchBatchAction]"
      :confirm-loading="workbenchBatchBusy" :closable="!workbenchBatchBusy"
      :mask-closable="!workbenchBatchBusy" :keyboard="!workbenchBatchBusy"
      :cancel-button-props="{ disabled: workbenchBatchBusy }" @ok="submitWorkbenchBatch">
      <a-form layout="vertical" :disabled="workbenchBatchBusy">
        <a-form-item v-if="['assign', 'assignLeader', 'transfer'].includes(workbenchBatchAction)" label="目标人员" required>
          <a-radio-group v-if="workbenchBatchAction === 'transfer' && workbenchBatchRows.every(canTransferLeader)"
            v-model:value="workbenchBatchForm.targetRole" @change="workbenchBatchForm.targetUserId = undefined">
            <a-radio-button value="OPERATOR">操作员</a-radio-button>
            <a-radio-button value="LEADER">组长</a-radio-button>
          </a-radio-group>
          <a-select v-model:value="workbenchBatchForm.targetUserId" show-search option-filter-prop="label"
            :options="workbenchPeople" placeholder="搜索姓名、部门或账号" />
        </a-form-item>
        <a-form-item v-if="workbenchBatchAction === 'recovery'" label="是否恢复编码" required>
          <a-radio-group v-model:value="workbenchBatchForm.recoveryAction">
            <a-radio value="skip">无需恢复，生成明细</a-radio>
            <a-radio value="request">需要恢复，交回 ADM 负责人</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="workbenchBatchAction === 'recovery' && workbenchBatchForm.recoveryAction === 'request'"
          label="GDS-PCC-PNR" required>
          <a-textarea v-model:value="workbenchBatchForm.locators" placeholder="1G-5S75-13124N,1A-BKK247-123NE" />
        </a-form-item>
        <a-alert v-if="workbenchBatchAction === 'startRecovery'" type="info" show-icon
          :message="workbenchBatchRows[0]?.recoveryLocators || ''"
          description="在 GDS 操作后确认正在恢复。从确认时起 48 小时后自动交回组长。" />
        <a-form-item v-if="workbenchBatchAction === 'transferAccept'" label="确认结果">
          <a-radio-group v-model:value="workbenchBatchForm.accepted">
            <a-radio :value="true">接受</a-radio><a-radio :value="false">拒绝</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="['assignLeader', 'transfer'].includes(workbenchBatchAction) ||
          (workbenchBatchAction === 'transferAccept' && !workbenchBatchForm.accepted)" label="原因" required>
          <a-textarea v-model:value="workbenchBatchForm.reason" />
        </a-form-item>
        <a-form-item v-if="workbenchBatchAction === 'transfer' && workbenchBatchRows.every((task) => !!task.lineId)" label="交接说明" required>
          <a-textarea v-model:value="workbenchBatchForm.handoverNote" />
        </a-form-item>
        <a-alert v-if="workbenchBatchError" type="warning" show-icon :message="workbenchBatchError" />
      </a-form>
    </a-modal>

    <a-modal
      v-if="isWorkbench"
      :open="!!workQueue"
      :title="workQueue === 'close' ? '可以结案的主单' : '我的转派申请'"
      :footer="null"
      :width="900"
      @cancel="closeWorkQueue"
    >
      <a-radio-group
        v-if="workQueue === 'transfer'"
        v-model:value="queueStatus"
        :disabled="queueLoading"
        @change="resetWorkQueuePage"
      >
        <a-radio-button value="pending">待确认</a-radio-button>
        <a-radio-button value="all">全部记录</a-radio-button>
      </a-radio-group>
      <a-alert v-if="queueError" type="error" show-icon :message="queueError">
        <template #action><a-button size="small" @click="loadWorkQueue">重试</a-button></template>
      </a-alert>
      <a-table
        :columns="queueColumns"
        :data-source="queueRows"
        :row-key="(row: Fields) => row.transferId || row.caseId"
        :loading="queueLoading"
        :locale="{ emptyText: queueError ? '读取失败' : queueLoading ? '正在读取清单…' : '当前没有符合条件的记录' }"
        :pagination="false"
        :scroll="{ x: workQueue === 'transfer' ? 760 : 540 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'identity'">
            <strong>{{ record.admNo || record.internalNo }}</strong>
            <div>{{ record.lineInternalNo || record.internalNo }}</div>
          </template>
          <template v-else-if="column.key === 'operators'">
            {{ record.fromOperatorName }} → {{ record.toOperatorName }}
            <div>申请人 {{ record.requestedByName }}</div>
          </template>
          <template v-else-if="column.key === 'status'">
            {{ transferStatusText(record) }}
            <div v-if="record.decidedAt">{{ record.decidedByName }} · {{ dateText(record.decidedAt) }}</div>
            <div v-if="record.decisionReason">{{ record.decisionReason }}</div>
          </template>
          <template v-else-if="column.key === 'date'">{{ dateText(record.requestedAt || record.replyDeadline) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" @click="openQueueRecord(record)">
              {{ workQueue === 'close' ? '前往结案' : '查看明细' }}
            </a-button>
          </template>
        </template>
      </a-table>
      <div v-if="queueTotal" class="v05-pager">
        <a-pagination
          v-model:current="queuePage"
          :page-size="20"
          :total="queueTotal"
          :show-size-changer="false"
          :disabled="queueLoading"
          :show-total="recordTotalText"
          @change="loadWorkQueue"
        />
      </div>
    </a-modal>

    <AdmMasterBasicModal :open="masterInfoOpen" :detail="selectedMasterDetail" :editable="selectedMasterEditable" @close="masterInfoOpen = false" @saved="masterInfoSaved" />

    <a-modal v-model:open="exportSelectionOpen" title="导出本人待处理订单" width="min(1600px, 96vw)" :footer="null" wrap-class-name="v05-modal operator-export-modal">
      <p class="context">按任务类型、筛选范围和具体订单确定本次 Excel 内容；待接单订单会在导出时自动接单。</p>
      <section class="operator-export-section">
        <h3>1. 选择任务类型</h3>
        <div class="export-task-types">
          <a-checkbox :checked="allExportTypesSelected" @change="toggleAllExportTypes">全选 <b>{{ exportCandidates.length }}</b></a-checkbox>
          <a-checkbox v-for="item in exportTaskTypes" :key="item.name" :checked="selectedExportTypes.includes(item.name)" @change="toggleExportType(item.name)">
            {{ item.name }} <b>{{ item.count }}</b>
          </a-checkbox>
        </div>
      </section>
      <section class="operator-export-section">
        <h3>2. 继续筛选</h3>
        <div class="export-filters">
          <a-input v-model:value="exportFilters.adm" allow-clear placeholder="ADM 单号" />
          <a-select v-model:value="exportFilters.leader" allow-clear placeholder="全部组长" :options="exportFilterOptions.leader" />
          <a-select v-model:value="exportFilters.deadline" allow-clear placeholder="全部截止时间" :options="exportFilterOptions.deadline" />
        </div>
      </section>
      <section class="operator-export-section">
        <h3>3. 确定导出范围</h3>
        <div class="export-scope">
          <a-radio-group v-model:value="exportScope">
            <a-radio value="all">当前筛选全部订单（{{ filteredExportCandidates.length }}）</a-radio>
            <a-radio value="selected">仅勾选订单（{{ selectedFilteredExportCount }}）</a-radio>
          </a-radio-group>
          <strong>最终导出 {{ finalExportCandidates.length }} 笔</strong>
        </div>
      <div class="v05-table-wrap export-selection-table">
        <table>
          <thead><tr><th><a-checkbox :checked="allFilteredSelected" @change="toggleAllExport">全选</a-checkbox></th><th>任务类型</th><th>ADM / 内部明细</th><th>部门 / 组长</th><th>操作人员</th><th>截止时间</th></tr></thead>
          <tbody>
            <tr v-for="item in filteredExportCandidates" :key="item.lineId">
              <td><a-checkbox :checked="selectedExportIds.includes(item.lineId)" @change="toggleExportItem(item.lineId)" /></td>
              <td>{{ exportTaskType(item) }}</td>
              <td><b>{{ item.admNo || item.internalNo }}</b><small>{{ item.lineInternalNo }}</small></td>
              <td>{{ item.departmentName }}<small>{{ item.leaderName || '未分配组长' }}</small></td>
              <td>{{ item.operatorName || '未分配' }}</td><td>{{ dateText(item.deadline) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      </section>
      <div class="v05-modal-actions"><button @click="exportSelectionOpen = false">取消</button><button class="primary" :disabled="!finalExportCandidates.length" @click="claimAndExport">4. 导出 Excel（{{ finalExportCandidates.length }}）</button></div>
    </a-modal>

    <a-modal
      v-model:open="globalOrdersOpen"
      :title="`订单清单 · ${orderMetrics.find((item) => item.key === orderMetric)?.title || '全部订单明细'}`"
      width="1180px"
      :footer="null"
      wrap-class-name="v05-modal global-orders-modal"
      ><a-space class="block">
        <a-select :value="orderMetric" aria-label="订单明细范围" style="width: 200px"
          :options="orderMetrics.map(({ key, title }) => ({ value: key, label: title }))"
          @change="(value: unknown) => openGlobalOrders(String(value))" />
      </a-space>
      <div class="v05-table-wrap global-order-table">
        <table>
          <thead>
            <tr>
              <th>ADM单号 / 内部明细</th>
              <th>票号 / OTA订单号 / PNR</th>
              <th>业务部门 / 组长</th>
              <th>操作人员</th>
              <th>当前状态</th>
              <th>当前任务</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in globalOrders" :key="item.id">
              <td class="order-identity-cell">
                <div class="order-cell-stack">
                  <span class="order-cell-label">ADM单号</span>
                  <b class="order-cell-primary">{{ item.admNo || '未填写' }}</b>
                  <span class="order-cell-label">内部明细</span>
                  <small class="order-cell-code">{{ item.lineInternalNo }}</small>
                </div>
              </td>
              <td class="order-reference-cell">
                <div class="order-cell-stack">
                  <span class="order-cell-label">票号</span>
                  <b class="order-cell-primary">{{ item.ticketNo || '未填写' }}</b>
                  <div class="order-cell-pairs">
                    <small><span>OTA订单号</span><b>{{ item.otaOrderNo || '未填写' }}</b></small>
                    <small><span>PNR</span><b>{{ item.pnr || '未填写' }}</b></small>
                  </div>
                </div>
              </td>
              <td class="order-owner-cell">
                <div class="order-cell-pairs owner-pairs">
                  <small><span>业务部门</span><b>{{ item.departmentName || '未分配' }}</b></small>
                  <small><span>负责组长</span><b>{{ item.leaderName || '未分配' }}</b></small>
                </div>
              </td>
              <td>{{ item.operatorName || '未分配' }}</td>
              <td>
                <span :class="['pill', lineStatusTone(item.lineStatus)]">{{ label(item.lineStatus) }}</span>
              </td>
              <td>{{ lineTask(item.lineStatus) }}</td>
              <td>
                <button class="primary" @click="openGlobalLine(item.caseId, item.id)">查看详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="ordersLoading" class="empty" role="status">正在读取订单明细…</p>
        <a-alert v-else-if="ordersError" type="error" show-icon :message="ordersError" />
        <p v-else-if="!globalOrders.length" class="empty">当前指标下没有订单明细</p>
      </div>
      <div class="v05-pager">
        <div class="v05-pager">
          <a-pagination v-model:current="ordersPage" :page-size="pageSize" :total="ordersTotal"
            :show-size-changer="false" :disabled="ordersLoading || !!ordersError"
            :show-total="recordTotalText" @change="loadGlobalOrders" />
        </div>
        <small v-if="ordersError"><button @click="loadGlobalOrders">重试</button></small>
        <small v-else-if="ordersTotal">共 {{ ordersTotal }} 条</small>
      </div></a-modal
    >
    <a-modal v-model:open="operatorImportOpen" title="导入处理结果" :footer="null" wrap-class-name="v05-modal"
      ><p class="context">
        回传从本人工作台导出的单 Sheet Excel；系统按内部明细编号、当前操作员和数据版本校验，不接受新增订单行。
      </p>
      <div class="import-zone">
        <b>⇧<br />上传操作人员处理结果</b>
        <p>待编码处理完成后才进入待决定；审核退回会明确区分“补充材料”或“重新申诉”，并只提供对应处理动作。</p>
        <input type="file" accept=".xlsx" @change="selectOperatorImport" />
        <small>恢复编码决定和处理确认只在对应阶段的单元格中解锁；已恢复待确认时，可同一行确认处理并提交最终结果。</small>
      </div>
      <a-alert
        v-if="operatorImportNotice"
        :type="operatorImportPreview?.canCommit ? 'success' : 'error'"
        show-icon
        :message="operatorImportNotice"
        style="margin-top: 14px"
      />
      <div v-if="operatorImportPreview?.rows?.length" class="v05-table-wrap">
        <div class="import-summary">
          <span>共 {{ operatorImportPreview.totalRows }} 行</span>
          <span class="ok">可提交 {{ operatorImportPreview.validRows }} 行</span>
          <span>跳过 {{ operatorImportPreview.skippedRows }} 行</span>
          <span class="bad">错误 {{ operatorImportPreview.failedRows }} 行</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Excel行</th>
              <th>内部明细</th>
              <th>处理动作</th>
              <th>预检状态</th>
              <th>预检说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in operatorImportPreview.rows" :key="item.rowNumber">
              <td>{{ item.rowNumber }}</td>
              <td>{{ item.lineInternalNo }}</td>
              <td>{{ item.action }}</td>
              <td>{{ item.status }}</td>
              <td>{{ item.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="v05-modal-actions">
        <button @click="operatorImportOpen = false">取消</button
        ><button :disabled="!operatorImportFile || operatorImportBusy" @click="previewOperatorImport">预检文件</button
        ><button
          class="primary"
          :disabled="!operatorImportPreview?.canCommit || operatorImportBusy"
          @click="commitOperatorImport"
        >
          确认提交
        </button>
      </div></a-modal
    >
    <a-modal
      v-model:open="createOpen"
      title="新建 ADM 主单"
      width="1180px"
      :footer="null"
      wrap-class-name="v05-modal"
      ><a-alert
        type="info"
        show-icon
        message="主单可单独保存，之后从详情录入订单明细。"
        style="margin-bottom: 16px"
      /><a-alert
        v-if="referenceError"
        type="warning"
        show-icon
        :message="referenceError"
        style="margin-bottom: 16px"
      >
        <template #action><a-button size="small" @click="retryCreateReferences">重试</a-button></template>
      </a-alert>
      <div class="v05-form-grid">
          <label><span class="form-field-label">ADM 单号 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.admNo" /></label
          ><label
            ><span class="form-field-label">下发方类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
              v-model:value="form.issuerType"
              :options="issuerOptions"
              @change="form.issuerName = ''" /></label
          ><label>
            <span class="form-field-label">{{ form.issuerType === 'SUPPLIER' ? '供应商名称' : '航司名称' }} <span class="form-required-mark" aria-hidden="true">*</span></span>
            <a-input aria-required="true" v-model:value="form.issuerName" />
          </label>
          ><label
            ><span class="form-field-label">关联航司 <span class="form-required-mark" aria-hidden="true">*</span></span>
              <a-input aria-required="true" v-model:value="form.airlineName" /></label>
          <label><span class="form-field-label">原币币种 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
              v-model:value="form.currency"
              :options="currencyOptions"
              :loading="referenceLoading.currency"
              @change="loadExchangeRate" /></label
          ><label><span class="form-field-label">原币总金额 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.originalAmount" /></label
          ><label
            >换算汇率（对人民币）<a-input
              :value="fxLoading ? '读取中…' : fxSnapshot?.rateValue || '暂无可用汇率'"
              readonly /></label
          ><label>人民币总金额<a-input :value="masterCnyAmount" readonly /></label
          ><label
            >汇率日期 / 来源<a-input
              :value="fxSnapshot ? `${fxSnapshot.sourceUpdatedAt || '即时'} / ${fxSnapshot.actualSource}` : '—'"
              readonly /></label
          ><label><span class="form-field-label">下发日期 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.issuedDate" type="date" /></label
          ><label><span class="form-field-label">处理截止 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.replyDeadline" type="datetime-local" /></label
          ><label>
            <span class="form-field-label">归属部门 <span class="form-required-mark" aria-hidden="true">*</span></span>
            <a-select aria-required="true" v-model:value="form.departmentCode" :options="config?.masterDepartments || []" />
          </label><label>
            <span class="form-field-label">负责组长 <span class="form-required-mark" aria-hidden="true">*</span></span>
            <a-select aria-required="true" v-model:value="form.leaderId" :options="leaderOptions"
              show-search option-filter-prop="label" placeholder="搜索姓名、部门或账号" />
          </label><label>
            <span class="form-field-label">差异类型 <span class="form-required-mark" aria-hidden="true">*</span></span>
            <a-select aria-required="true" v-model:value="form.diffTypeCode" :options="diffTypeOptions"
              :loading="referenceLoading.diffType" show-search option-filter-prop="label" />
          </label><label class="wide">
            <span class="form-field-label">细分差异原因 <span class="form-required-mark" aria-hidden="true">*</span></span>
            <a-textarea aria-required="true" v-model:value="form.differenceReason" :rows="2" />
          </label><label class="wide">备注（选填）<a-textarea v-model:value="form.remark" :rows="2" /></label
          ><label class="wide"
            >主单公共附件（选填）<input type="file" multiple @change="pickMasterFiles" /><span>{{
              masterFiles.map((file) => file.name).join('、') || '未选择附件'
            }}</span></label
          >
        </div>
        <p class="hint"><b>*</b> 为必填项。ADM负责人由系统自动记录；汇率保存为创建时快照。</p>
        <a-alert v-if="createError" type="error" show-icon :message="createError" class="block" />
        <div class="v05-modal-actions">
          <a-button :disabled="saving" @click="createOpen = false">取消</a-button>
          <a-button type="primary" :loading="saving" @click="createCase">保存主单</a-button>
        </div>
    </a-modal>
    <a-modal
      v-model:open="importOpen"
      title="跨主单批量导入（19列）"
      :confirm-loading="importBusy"
      :ok-button-props="{ disabled: !preview?.canCommit }"
      @ok="commitImport"
      wrap-class-name="v05-modal"
      ><p>一行就是一条明细；同一ADM主单的多笔明细请分多行填写，并重复相同ADM单号及一致的主单字段。系统会为每行自动生成不同的内部明细ID。</p>
      <p class="hint">模板自带两行同主单示例；ADM单号以“【示例】”开头的行会在预检时自动忽略。同号但不同主单请拆成两次上传。</p>
      <p class="hint">当前19列模板只导入主单和明细，不导入附件；建单后请在ADM详情中分别上传主单公共附件或明细附件。</p>
      <div class="v05-actions">
        <button @click="downloadTemplate">下载 Excel 模板</button
        ><input type="file" accept=".xlsx" @change="selectImport" /><button
          :disabled="!importFile"
          @click="previewImport"
        >
          预检文件
        </button>
      </div>
      <a-alert
        v-if="preview"
        :type="preview.canCommit ? 'success' : 'warning'"
        show-icon
        :message="`共 ${preview.totalRows} 行，有效 ${preview.validRows} 行，错误 ${preview.failedRows} 行`"
        style="margin-top: 14px" />
      <p v-for="item in preview?.groups || []" :key="item.firstRow">
        第 {{ item.firstRow }} 行起 · {{ item.admNo || '未识别' }} · {{ item.rowCount }} 条明细 ·
        {{ item.status === 'VALID' ? '校验通过' : '校验失败' }} {{ item.message || '' }}
      </p>
      <a-alert v-if="importError" type="error" show-icon :message="importError"
    /></a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { createOperationIdentifier } from '@/utils/operationIdentifier'
import AdmMasterBasicModal from './AdmMasterBasicModal.vue'
import {
  admApi,
  admPersonOptions,
  errorText,
  label,
  type AdmCaseDetail,
  type AdmCaseRow,
  type AdmConfig,
  type AdmLedgerLine,
  type Fields,
  type FxSnapshot,
  type Option,
} from './api'
import './adm-v05.css'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore(),
  exportTasks = useComprehensiveExportStore(),
  isWorkbench = computed(() => route.query.scope === 'mine')
const config = ref<AdmConfig | null>(null),
  rows = ref<AdmCaseRow[]>([]),
  workbenchItems = ref<Fields[]>([]),
  workbenchSummary = ref<Fields>({}),
  ledgerReady = ref(false),
  workbenchReady = ref(false),
  loading = ref(false),
  error = ref(''),
  configError = ref(''),
  page = ref(1),
  pageSize = ref(20),
  total = ref(0),
  metric = ref(''),
  orderMetric = ref(''),
  workMetric = ref(isWorkbench.value ? String(route.query.workMetric || '') : '')
const masterInfoOpen = ref(false),
  selectedMasterDetail = ref<AdmCaseDetail | null>(null),
  selectedMasterEditable = ref(false)
const filters = reactive({ search: '', status: '' })
const appliedFilters = ref({ ...filters })
const recordTotalText = (count: number) => `共 ${count} 条`
const taskTotalText = (count: number) => `共 ${count} 条任务`
const shownRows = computed(() => loading.value || error.value ? [] : rows.value)
let request = 0
let configRequest: Promise<void> | undefined
function loadConfig(refresh = false) {
  if (config.value && !refresh) return Promise.resolve()
  configRequest ??= admApi.config().then(
    (value) => { config.value = value; configError.value = '' },
    (e) => { configError.value = `人员与权限配置加载失败：${errorText(e)}` },
  ).finally(() => { configRequest = undefined })
  return configRequest
}
async function load() {
  const seq = ++request
  loading.value = true
  error.value = ''
  void loadConfig()
  try {
    if (isWorkbench.value) {
      const result = await admApi.workbench()
      if (seq !== request) return
      workbenchItems.value = result.items
      workbenchSummary.value = result.summary || {}
      workbenchReady.value = true
      workPage.value = Math.min(workPage.value, Math.max(1, Math.ceil(visibleTasks.value.length / workPageSize)))
      return
    }
    const result = await admApi.list({
      ...appliedFilters.value,
      metric: metric.value,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (seq !== request) return
    rows.value = result.items
    total.value = result.pagination.total
    ledgerReady.value = true
  } catch (e) {
    if (seq === request) error.value = errorText(e)
  } finally {
    if (seq === request) loading.value = false
  }
}
function changeLedgerPage(nextPage: number, nextSize: number) {
  page.value = nextSize === pageSize.value ? nextPage : 1
  pageSize.value = nextSize
  void load()
}
function query() {
  appliedFilters.value = { ...filters }
  page.value = 1
  void load()
}
function resetFilters() {
  filters.search = ''
  filters.status = ''
  metric.value = ''
  query()
}
const myId = computed(() => Number(auth.user?.id)),
  now = () => Date.now(),
  dateText = (v: unknown) => (v ? String(v).replace('T', ' ').slice(0, 16) : '—')
const sourceText = (value: unknown) => ({
    TEST: '测试数据', LEGACY: '旧系统数据 / 历史只读',
    MANUAL: '新系统人工数据', EXCEL: '新系统导入数据',
  } as Fields)[String(value || '')] || '来源未标记',
  sourceTone = (value: unknown) => String(value || '').toLowerCase()
const taskReturnMode = (item: Fields) => {
  const reason = String(item.latestReviewReturnReason || '')
  if (reason.startsWith('【驳回补充材料】')) return 'SUPPLEMENT'
  if (reason.startsWith('【驳回重新申诉】')) return 'REAPPEAL'
  if (item.latestReviewStatus === 'RETURNED' || item.reviewStatus === 'RETURNED') return 'SUPPLEMENT'
  return ''
}
const taskKind = (s: string) =>
  (
    ({
      PENDING_LEADER: 'assignLeader',
      PENDING_OPERATOR: 'assign',
      PENDING_ACCEPT: 'accept',
      PROCESSING: 'process',
      PENDING_REVIEW: 'review',
      WAITING_DIFF: 'diff',
      WAITING_COLLECTION: 'collection',
    }) as Fields
  )[s] || 'other'
const tasks = computed<Fields[]>(() =>
  workbenchItems.value.map((line): Fields => {
    const masterStages: Fields = {
      MASTER_LEADER_FOLLOWUP: ['masterLeaderFollowup', '组长', '负责人恢复编码中，可跟进或转派组长'],
      MASTER_TRANSFER_ACCEPT: ['transferAccept', '组长', '确认是否接受组长转派'],
      MASTER_TRANSFER_WAIT: ['masterTransferWait', '组长', '等待目标组长确认转派'],
      LEADER_DECISION: ['leaderRecovery', '组长', '判断是否恢复编码'],
      OWNER_RECOVERY: ['ownerRecovery', 'ADM负责人', '在 GDS 操作后标记正在恢复'],
      RECOVERING: ['recovering', 'ADM负责人', '等待 48 小时自动恢复'],
      RECOVERED: ['recovered', '组长', '已恢复，录入订单明细'],
      LEADER_FOLLOWUP: ['leaderFollowup', '组长', '跟进或转派单笔订单'],
    }
    const stage = masterStages[line.taskType]
    if (stage) return {
      ...line, status: line.lineStatus, kind: stage[0], role: stage[1], title: stage[2],
      requiredAction: stage[2], assignment: line.leaderName || line.coordinatorName || '—',
      deadline: line.masterRecoveryDueAt || line.replyDeadline,
    }
    const transferTask = line.taskType === 'TRANSFER_ACCEPT'
    const returnMode = taskReturnMode(line)
    const reviewWithdrawn = line.reviewStatus === 'WITHDRAWN' || line.latestReviewStatus === 'WITHDRAWN'
    const role = transferTask
      ? (line.targetRole === 'LEADER' ? '组长' : '操作人员')
      : ['PENDING_LEADER', 'PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(line.lineStatus)
      ? 'ADM负责人'
      : line.lineStatus === 'PENDING_OPERATOR'
        ? '组长'
        : '操作人员'
    return {
      ...line,
      status: line.lineStatus,
      role,
      kind: transferTask ? 'transferAccept' : taskKind(line.lineStatus),
      title: transferTask ? '确认是否接受转派' : (
        {
          PENDING_LEADER: '分配负责组长',
          PENDING_OPERATOR: '分配操作人员',
          PENDING_ACCEPT: '确认接单',
          PROCESSING: reviewWithdrawn ? '审核撤回待重提' : returnMode === 'SUPPLEMENT' ? '驳回补充材料' : returnMode === 'REAPPEAL' ? '驳回重新申诉' : '办理订单',
          PENDING_REVIEW: 'ADM负责人审核',
          WAITING_DIFF: '匹配差异单',
          WAITING_COLLECTION: '登记回款',
        } as Fields
      )[line.lineStatus],
      assignment: transferTask
        ? `${line.fromOperatorName || line.operatorName || '原操作员'} → ${line.toOperatorName || '当前账号'}`
        : `${line.departmentName} · ${line.leaderName || '未分配组长'} · ${line.operatorName || '未分配操作员'}`,
      requiredAction: transferTask ? '确认接受转派，或填写原因拒绝转派' : (
        {
          PENDING_LEADER: '选择并分配负责组长',
          PENDING_OPERATOR: '选择并分配操作人员',
          PENDING_ACCEPT: '确认是否接单',
          PROCESSING: reviewWithdrawn
            ? '按撤回原因更正资料后重新提交审核'
            : returnMode === 'SUPPLEMENT'
            ? '补充订单资料、问题说明或附件后重新提交审核'
            : returnMode === 'REAPPEAL'
              ? '重新选择申诉或不申诉，并提交新的处理结果'
              : '完成编码恢复判断和处理决定，并提交审核',
          PENDING_REVIEW: '审核处理结果，选择通过或退回',
          WAITING_DIFF: '核验是否已匹配差异单',
          WAITING_COLLECTION: '登记本次回款信息及凭证',
        } as Fields
      )[line.lineStatus],
      deadline: line.replyDeadline,
      overdue: !!line.replyDeadline && new Date(line.replyDeadline).getTime() < now(),
    }
  }),
)
const dueKind = (t: Fields) => {
  if (!t.deadline) return 'normal'
  const d = new Date(t.deadline).getTime() - now()
  return d < 0 ? 'late' : d < 86400000 ? 'soon' : 'normal'
}
const workflowSteps = ['新建主单', '恢复判断', '分配与接单', '订单办理', '负责人审核', '差异或回款', '结案']
const canCloseWorkQueue = computed(() => auth.user?.isAdmin || config.value?.permissions.close)
const canTransferWorkQueue = computed(() => auth.user?.isAdmin || config.value?.permissions.assignOperator ||
  config.value?.permissions.assign || config.value?.permissions.handle)
const workPhaseOptions = [
  { value: '', label: '全部待办阶段' },
  ...Object.entries({
    assignLeader: '待分配组长', leaderRecovery: '待恢复判断', ownerRecovery: '待 GDS 操作',
    recovering: '正在恢复', recovered: '已恢复待录入', assign: '待分配操作员',
    accept: '待接单', process: '本人待办理', appeal: '申诉中', review: '待审核',
    diff: '待匹配差异单', collection: '待回款跟进', transferAccept: '待确认转派',
    masterTransferWait: '等待组长确认转派', masterLeaderFollowup: '组长恢复跟进', leaderFollowup: '组长订单跟进',
    codeReminder: '编码恢复提醒', soon: '即将超时', late: '已超时',
  }).map(([value, label]) => ({ value, label })),
]
function selectWorkPhase(value: unknown) {
  workSelection.value = []
  workMetric.value = String(value ?? '')
  workPage.value = 1
}
function switchScope(value: string | number) {
  if ((value === 'mine') === isWorkbench.value) return
  void router.push({ name: 'adm-cases', query: value === 'mine' ? { scope: 'mine' } : {} })
}
const visibleTasks = computed(() => {
  if (!workMetric.value) return tasks.value
  if (['soon', 'late'].includes(workMetric.value)) return tasks.value.filter((t) => dueKind(t) === workMetric.value)
  if (workMetric.value === 'codeReminder') return tasks.value.filter((t) => t.recoveryStatus === 'REMINDER_DUE')
  if (workMetric.value === 'appeal') return tasks.value.filter((t) => t.appealStatus === 'IN_PROGRESS')
  return tasks.value.filter((t) => t.kind === workMetric.value)
})
const workPageSize = 20
const requestedWorkPage = Number(route.query.page)
const workPage = ref(Number.isSafeInteger(requestedWorkPage) && requestedWorkPage > 0 ? requestedWorkPage : 1)
const pagedTasks = computed(() =>
  visibleTasks.value.slice((workPage.value - 1) * workPageSize, workPage.value * workPageSize),
)
const workQueue = ref<'close' | 'transfer' | null>(null)
const queueStatus = ref<'pending' | 'all'>('pending')
const queuePage = ref(1)
const queueTotal = ref(0)
const queueRows = ref<Fields[]>([])
const queueLoading = ref(false)
const queueError = ref('')
let queueRequest = 0
const queueColumns = computed(() => [
  { title: 'ADM / 内部单号', key: 'identity' },
  ...(workQueue.value === 'transfer'
    ? [{ title: '承办人变更', key: 'operators' }, { title: '处理结果', key: 'status' }]
    : []),
  { title: workQueue.value === 'transfer' ? '申请时间' : '处理截止', key: 'date' },
  { title: '操作', key: 'action' },
])
function transferStatusText(row: Fields) {
  if (row.transferStatus === 'PENDING') return row.actionable ? '待接收人确认' : '待确认 · 当前状态不可处理'
  return ({ ACCEPTED: '已接受', REJECTED: '已拒绝' } as Record<string, string>)[row.transferStatus] || label(row.transferStatus)
}
async function loadWorkQueue() {
  const queue = workQueue.value
  if (!queue) return
  const seq = ++queueRequest
  queueLoading.value = true
  queueError.value = ''
  queueRows.value = []
  try {
    const result = await admApi.workbenchQueue({
      queue, status: queueStatus.value, page: queuePage.value, pageSize: 20,
    })
    if (seq !== queueRequest) return
    queueRows.value = result.items
    queueTotal.value = result.pagination.total
    if (queue === 'close') workbenchSummary.value.closableCaseCount = queueTotal.value
    else if (queueStatus.value === 'pending') workbenchSummary.value.pendingTransferCount = queueTotal.value
    const lastPage = Math.max(1, Math.ceil(queueTotal.value / 20))
    if (queuePage.value > lastPage) {
      queuePage.value = lastPage
      await loadWorkQueue()
    }
  } catch (e) {
    if (seq === queueRequest) queueError.value = errorText(e)
  } finally {
    if (seq === queueRequest) queueLoading.value = false
  }
}
function resetWorkQueuePage() {
  queuePage.value = 1
  queueTotal.value = 0
  void loadWorkQueue()
}
function closeWorkQueue() {
  workQueue.value = null
  queueRequest++
}
function openQueueRecord(row: Fields) {
  if (workQueue.value === 'transfer') openTask({ ...row, kind: 'transferHistory' })
  else void router.push({
    path: `/adm/cases/${row.caseId}`,
    query: { returnPage: String(workPage.value), ...(workMetric.value ? { returnMetric: workMetric.value } : {}) },
  })
  closeWorkQueue()
}
function openWorkMetric(key: 'close' | 'transfer') {
  workQueue.value = key
  queueStatus.value = 'pending'
  resetWorkQueuePage()
}
function openTask(t: Fields) {
  void router.push({
    path: `/adm/cases/${t.caseId}`,
    query: {
      lineId: t.lineId,
      taskAction: t.lineId ? t.kind : undefined,
      addLine: t.kind === 'recovered' ? '1' : undefined,
      returnPage: String(workPage.value),
      ...(workMetric.value ? { returnMetric: workMetric.value } : {}),
    },
  })
}
const canCreate = computed(() => !!auth.user?.isAdmin || !!config.value?.permissions.create),
  canOperatorWork = computed(() => !!auth.user?.isAdmin || !!config.value?.permissions.handle),
  exportCandidates = computed(() => {
    const unique = new Map<number, Fields>()
    tasks.value
      .filter((t) => ['PENDING_ACCEPT', 'PROCESSING'].includes(t.status) && Number(t.operatorId) === myId.value)
      .forEach((item) => unique.set(Number(item.lineId), item))
    return [...unique.values()]
  })
const workSelection = ref<string[]>([])
const workTaskKey = (task: Fields) => `${task.caseId}-${task.lineId || 0}-${task.kind}-${task.transferId || 0}`
const batchRows = computed(() => visibleTasks.value.filter((task) => workSelection.value.includes(workTaskKey(task))))
const canTransferLeader = (task: Fields) => !['transferAccept', 'masterTransferWait'].includes(task.kind) && Number(task.leaderId) === myId.value &&
  (auth.user?.isAdmin || config.value?.permissions.assignOperator)
const canTransferOperator = (task: Fields) => !!task.operatorId &&
  (canTransferLeader(task) || (canOperatorWork.value && Number(task.operatorId) === myId.value))
const workbenchActionLabels: Record<string, string> = {
  assign: '分配操作员', assignLeader: '分配组长', accept: '接单', transfer: '转派',
  transferAccept: '确认转派', recovery: '恢复编码判断', startRecovery: '正在恢复',
}
const batchActions = computed(() => {
  const rows = batchRows.value
  if (!rows.length || !rows.every((task) => task.kind === rows[0].kind)) return []
  const actions = ['assign', 'assignLeader', 'accept', 'transferAccept'].includes(rows[0].kind) ? [rows[0].kind] : []
  if (rows.every((task) => task.kind !== 'transferAccept' && (canTransferLeader(task) || canTransferOperator(task)))) actions.push('transfer')
  return actions
})
function toggleWorkbenchTask(task: Fields) {
  const key = workTaskKey(task)
  workSelection.value = workSelection.value.includes(key)
    ? workSelection.value.filter((item) => item !== key) : [...workSelection.value, key]
}
function selectWorkbenchPage() {
  const keys = pagedTasks.value.map(workTaskKey)
  workSelection.value = keys.every((key) => workSelection.value.includes(key))
    ? workSelection.value.filter((key) => !keys.includes(key))
    : [...new Set([...workSelection.value, ...keys])]
}
const workbenchBatchOpen = ref(false)
const workbenchBatchBusy = ref(false)
const workbenchBatchRows = ref<Fields[]>([])
const workbenchBatchAction = ref('')
const workbenchBatchError = ref('')
const workbenchBatchForm = reactive<Fields>({})
const workbenchPeople = computed(() => admPersonOptions(
  (workbenchBatchAction.value === 'assignLeader' || workbenchBatchForm.targetRole === 'LEADER'
    ? config.value?.people.leader : config.value?.people.handle) || [],
))
function openWorkbenchBatch(action: string, rows = batchRows.value) {
  if (!rows.length) return
  workbenchBatchRows.value = rows
  workbenchBatchAction.value = action
  workbenchBatchError.value = ''
  Object.assign(workbenchBatchForm, {
    targetUserId: undefined, targetRole: action === 'transfer' && !rows.every(canTransferOperator) ? 'LEADER' : 'OPERATOR',
    reason: '', handoverNote: '', recoveryAction: undefined, locators: '', accepted: true,
  })
  workbenchBatchOpen.value = true
}
async function submitWorkbenchBatch() {
  if (workbenchBatchBusy.value) return
  const action = workbenchBatchAction.value
  const form = { ...workbenchBatchForm }
  if (action === 'transfer' && form.targetRole === 'OPERATOR' && !workbenchBatchRows.value.every(canTransferOperator)) {
    workbenchBatchError.value = '选中明细中有尚未分配操作员的记录，请转派给组长或重新选择'
    return
  }
  const failures: Fields[] = []
  const errors: string[] = []
  workbenchBatchBusy.value = true
  try {
    for (const task of workbenchBatchRows.value) {
      const caseId = Number(task.caseId), lineId = Number(task.lineId)
      try {
        if (action === 'assign') await admApi.assignOperator(caseId, lineId, { operatorId: form.targetUserId })
        if (action === 'assignLeader') await admApi.changeLeader(caseId, lineId, { leaderId: form.targetUserId, reason: form.reason })
        if (action === 'accept') await admApi.accept(caseId, lineId)
        if (action === 'transfer') {
          if (task.lineId) await admApi.transfer(caseId, lineId, form)
          else await admApi.masterLeaderTransfer(caseId, { targetUserId: form.targetUserId, reason: form.reason })
        }
        if (action === 'transferAccept') {
          if (task.lineId) await admApi.decideTransfer(caseId, lineId, Number(task.transferId), form.accepted, form.reason)
          else await admApi.masterLeaderTransfer(caseId, { accepted: form.accepted, reason: form.reason })
        }
        if (action === 'recovery' || action === 'startRecovery')
          await admApi.masterRecovery(caseId, action === 'startRecovery' ? 'start' : form.recoveryAction, form.locators)
      } catch (e) {
        failures.push(task)
        errors.push(`${task.lineInternalNo || task.admNo}：${errorText(e)}`)
      }
    }
    const success = workbenchBatchRows.value.length - failures.length
    if (success) void message.success(`成功处理 ${success} 条`)
    workbenchBatchRows.value = failures
    workSelection.value = failures.map(workTaskKey)
    workbenchBatchError.value = errors.join('；')
    if (!failures.length) workbenchBatchOpen.value = false
    await load()
  } finally {
    workbenchBatchBusy.value = false
  }
}
const acceptingLines = reactive(new Set<number>())
function canAcceptTask(task: Fields) {
  return task.kind === 'accept' && canOperatorWork.value && Number(task.operatorId) === myId.value
}
async function acceptTask(task: Fields) {
  const lineId = Number(task.lineId)
  if (!canAcceptTask(task) || acceptingLines.has(lineId)) return
  acceptingLines.add(lineId)
  try {
    await admApi.accept(Number(task.caseId), lineId)
    void message.success('已接单，可在「本人待办理」继续处理')
  } catch (e) {
    void message.error(`接单失败：${errorText(e)}`)
  } finally {
    if (isWorkbench.value) await load()
    acceptingLines.delete(lineId)
  }
}
const exportSelectionOpen = ref(false),
  selectedExportIds = ref<number[]>([]),
  selectedExportTypes = ref<string[]>([]),
  exportScope = ref<'all' | 'selected'>('all'),
  exportFilters = reactive({ adm: '', leader: undefined as string | undefined, deadline: undefined as string | undefined })
function exportTaskType(item: Fields) {
  if (item.reviewStatus === 'WITHDRAWN' || item.latestReviewStatus === 'WITHDRAWN') return '审核撤回待重提'
  const returnMode = taskReturnMode(item)
  if (returnMode === 'SUPPLEMENT') return '驳回补充材料'
  if (returnMode === 'REAPPEAL') return '驳回重新申诉'
  if (['UNDECIDED', 'WAITING', 'REMINDER_DUE'].includes(String(item.recoveryStatus || 'UNDECIDED'))) return '待编码处理'
  if (item.appealStatus === 'IN_PROGRESS') return '申诉中'
  return '待决定'
}
const exportTaskTypes = computed(() =>
    ['待编码处理', '待决定', '申诉中', '驳回补充材料', '驳回重新申诉', '审核撤回待重提'].map((name) => ({
      name,
      count: exportCandidates.value.filter((item) => exportTaskType(item) === name).length,
    })),
  ),
  allExportTypesSelected = computed(() =>
    !!exportTaskTypes.value.length && exportTaskTypes.value.every((item) => selectedExportTypes.value.includes(item.name)),
  ),
  exportFilterOptions = computed(() => {
    const options = (key: string) => [...new Set(exportCandidates.value.map((item) => String(item[key] || '')).filter(Boolean))]
      .map((value) => ({ label: value, value }))
    return { leader: options('leaderName'), deadline: options('deadline') }
  }),
  filteredExportCandidates = computed(() => exportCandidates.value.filter((item) =>
    selectedExportTypes.value.includes(exportTaskType(item)) &&
    (!exportFilters.adm || `${item.admNo || ''}${item.internalNo || ''}${item.lineInternalNo || ''}`.toLowerCase().includes(exportFilters.adm.toLowerCase())) &&
    (!exportFilters.leader || item.leaderName === exportFilters.leader) &&
    (!exportFilters.deadline || item.deadline === exportFilters.deadline),
  )),
  selectedFilteredExportCount = computed(() => filteredExportCandidates.value.filter((item) => selectedExportIds.value.includes(Number(item.lineId))).length),
  allFilteredSelected = computed(() => !!filteredExportCandidates.value.length && selectedFilteredExportCount.value === filteredExportCandidates.value.length),
  finalExportCandidates = computed(() => exportScope.value === 'all'
    ? filteredExportCandidates.value
    : filteredExportCandidates.value.filter((item) => selectedExportIds.value.includes(Number(item.lineId))))
function openExportSelection() {
  selectedExportIds.value = []
  selectedExportTypes.value = exportTaskTypes.value.map((item) => item.name)
  exportScope.value = 'all'
  Object.assign(exportFilters, { adm: '', leader: undefined, deadline: undefined })
  exportSelectionOpen.value = true
}
function toggleExportType(name: string) {
  selectedExportTypes.value = selectedExportTypes.value.includes(name)
    ? selectedExportTypes.value.filter((item) => item !== name)
    : [...selectedExportTypes.value, name]
}
function toggleAllExportTypes() {
  selectedExportTypes.value = allExportTypesSelected.value ? [] : exportTaskTypes.value.map((item) => item.name)
}
function toggleExportItem(id: number) {
  selectedExportIds.value = selectedExportIds.value.includes(id)
    ? selectedExportIds.value.filter((item) => item !== id)
    : [...selectedExportIds.value, id]
}
function toggleAllExport() {
  const filteredIds = new Set(filteredExportCandidates.value.map((item) => Number(item.lineId)))
  selectedExportIds.value = allFilteredSelected.value
    ? selectedExportIds.value.filter((id) => !filteredIds.has(id))
    : [...new Set([...selectedExportIds.value, ...filteredIds])]
}
async function claimAndExport() {
  const lineIds = finalExportCandidates.value.map((item) => Number(item.lineId))
  if (!lineIds.length) {
    void message.info('请先选择要接单并导出的订单')
    return
  }
  try {
    const task = await exportTasks.createBackground('adm_operator_excel', { lineIds })
    exportSelectionOpen.value = false
    selectedExportIds.value = []
    void message.success(
      task.reused ? '相同ADM导出任务正在进行，已打开导出任务' : '已接单并生成导出任务，请在页头“导出任务”下载',
    )
    await load()
  } catch (e) {
    void message.error(errorText(e))
  }
}
const operatorImportOpen = ref(false),
  operatorImportFile = ref<File | null>(null),
  operatorImportNotice = ref(''),
  operatorImportBusy = ref(false),
  operatorImportPreview = ref<Fields | null>(null)
function selectOperatorImport(e: Event) {
  operatorImportFile.value = (e.target as HTMLInputElement).files?.[0] || null
  operatorImportNotice.value = ''
  operatorImportPreview.value = null
}
async function previewOperatorImport() {
  if (!operatorImportFile.value) return
  operatorImportBusy.value = true
  try {
    operatorImportPreview.value = await admApi.operatorImport(operatorImportFile.value, true)
    operatorImportNotice.value = operatorImportPreview.value.canCommit
      ? `预检通过，可提交 ${operatorImportPreview.value.validRows} 行`
      : `预检发现 ${operatorImportPreview.value.failedRows} 行错误，请修正后重新上传`
  } catch (e) {
    operatorImportPreview.value = null
    operatorImportNotice.value = errorText(e)
  } finally {
    operatorImportBusy.value = false
  }
}
async function commitOperatorImport() {
  if (!operatorImportFile.value || !operatorImportPreview.value?.canCommit) return
  operatorImportBusy.value = true
  try {
    const result = await admApi.operatorImport(operatorImportFile.value, false)
    operatorImportOpen.value = false
    void message.success(`已导入 ${result.committed} 行处理结果`)
    await load()
  } catch (e) {
    operatorImportNotice.value = errorText(e)
    operatorImportPreview.value = null
  } finally {
    operatorImportBusy.value = false
  }
}
const masterScopeOptions = [
  { value: '', label: '全部主单范围' }, { value: 'pending', label: '待处理主单' },
  { value: 'open', label: '未结案主单' }, { value: 'soon', label: '即将超时' },
  { value: 'late', label: '已超时' },
]
const openLineCount = (r: AdmCaseRow) =>
  Math.max(
    0,
    Number(r.lineCount || 0) - Number(r.completedLineCount || 0) - Number(r.voidedLineCount || 0) -
      Number(r.historicalLineCount || 0),
  )
const orderMetrics = [
  { key: 'all', title: '全部订单明细' }, { key: 'pending', title: '待处理订单明细' },
  { key: 'open', title: '未完成订单明细' }, { key: 'soon', title: '即将超时订单明细' },
  { key: 'late', title: '已超时订单明细' },
]
const globalOrdersOpen = ref(false),
  globalOrders = ref<AdmLedgerLine[]>([]),
  ordersPage = ref(1),
  ordersTotal = ref(0),
  ordersLoading = ref(false),
  ordersError = ref('')
let ordersRequest = 0
async function loadGlobalOrders() {
  const seq = ++ordersRequest
  ordersLoading.value = true
  ordersError.value = ''
  globalOrders.value = []
  try {
    const result = await admApi.ledgerLines({
      ...appliedFilters.value, metric: orderMetric.value, page: ordersPage.value, pageSize: pageSize.value,
    })
    if (seq !== ordersRequest) return
    globalOrders.value = result.items
    ordersTotal.value = result.pagination.total
  } catch (e) {
    if (seq === ordersRequest) ordersError.value = errorText(e)
  } finally {
    if (seq === ordersRequest) ordersLoading.value = false
  }
}
function openGlobalOrders(key: string) {
  orderMetric.value = key
  ordersPage.value = 1
  ordersTotal.value = 0
  globalOrdersOpen.value = true
  void loadGlobalOrders()
}
function openGlobalLine(caseId: number, lineId: number) {
  globalOrdersOpen.value = false
  void router.push({ path: `/adm/cases/${caseId}`, query: { lineId } })
}
function lineStatusTone(status: string) {
  return status === 'COMPLETED'
    ? 'green'
    : status === 'VOIDED'
      ? 'red'
      : ['PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(status)
        ? 'amber'
        : 'blue'
}
function lineTask(status: string) {
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
    )[status] || '查看处理记录'
  )
}
function selectMetric(k: string) {
  metric.value = k
  page.value = 1
  void load()
}
const activeLineCount = (r: AdmCaseRow) => Math.max(0, Number(r.lineCount || 0) - Number(r.voidedLineCount || 0)),
  progressWidth = (r: AdmCaseRow) =>
    `${activeLineCount(r) ? Math.min(100, (Number(r.completedLineCount || 0) / activeLineCount(r)) * 100) : 0}%`
function stageSummary(row: AdmCaseRow) {
  return [
    { label: '待办', count: Number(row.pendingLeaderCount || 0) + Number(row.pendingOperatorCount || 0) + Number(row.pendingAcceptCount || 0) },
    { label: '处理中', count: Number(row.processingCount || 0) },
    { label: '待审核', count: Number(row.pendingReviewCount || 0) },
    { label: '待差异/回款', count: Number(row.waitingDiffCount || 0) + Number(row.waitingCollectionCount || 0) },
    { label: '完成', count: Number(row.completedLineCount || 0) },
  ].filter((item) => item.count)
}
function ledgerStages(row: AdmCaseRow) {
  if (row.caseStatus !== 'ACTIVE') return []
  return [
    { status: 'PENDING_LEADER', title: '待分配组长', count: Number(row.pendingLeaderCount || 0) },
    { status: 'PENDING_OPERATOR', title: '待分配操作员', count: Number(row.pendingOperatorCount || 0) },
    { status: 'PENDING_ACCEPT', title: '待接单', count: Number(row.pendingAcceptCount || 0) },
    { status: 'PROCESSING', title: '办理中', count: Number(row.processingCount || 0) },
    { status: 'PENDING_REVIEW', title: '待负责人审核', count: Number(row.pendingReviewCount || 0) },
    { status: 'WAITING_DIFF', title: '待匹配差异单', count: Number(row.waitingDiffCount || 0) },
    { status: 'WAITING_COLLECTION', title: '待回款', count: Number(row.waitingCollectionCount || 0) },
  ].filter((stage) => stage.count > 0)
}
function ledgerDetailText(row: AdmCaseRow) {
  if (row.caseStatus === 'DRAFT') return '草稿详情'
  if (row.caseStatus !== 'ACTIVE') return 'ADM 详情'
  if (!activeLineCount(row)) return '主单详情'
  const stages = ledgerStages(row)
  if (stages.length === 1) return `查看${stages[0].title}明细`
  if (!stages.length && canCloseLedgerCase(row)) return '查看结案'
  return '订单明细'
}
function canCloseLedgerCase(row: AdmCaseRow) {
  return activeLineCount(row) > Number(row.historicalLineCount || 0) && !!config.value?.permissions.close &&
    Number(row.coordinatorId) === myId.value && !openLineCount(row)
}
function blockerText(row: AdmCaseRow) {
  if (row.caseStatus !== 'ACTIVE') return '—'
  if (!activeLineCount(row)) {
    const recovery = ({
      LEADER_DECISION: '待组长判断恢复编码', OWNER_RECOVERY: '待负责人恢复编码',
      RECOVERING: '正在恢复编码', RECOVERED: '已恢复，待组长录入明细',
    } as Record<string, string>)[row.masterRecoveryStatus]
    return recovery || '暂无有效订单明细'
  }
  const stages = ledgerStages(row)
  if (!stages.length) return openLineCount(row) ? '存在未完成明细' : '全部有效订单已完成'
  return stages.slice(0, 2).map(({ title, count }) => `${count}笔${title}`).join('；')
}
function riskText(r: AdmCaseRow) {
  if (!r.replyDeadline) return '未设期限'
  const d = new Date(r.replyDeadline).getTime() - now()
  return d < 0 ? '已超时' : d < 86400000 ? '即将超时' : '正常'
}
function riskTone(r: AdmCaseRow) {
  return riskText(r) === '已超时' ? 'red' : riskText(r) === '即将超时' ? 'amber' : 'green'
}
function statusTone(s: string) {
  return s === 'VOIDED' ? 'red' : s === 'CLOSED' ? 'green' : s === 'DRAFT' ? 'amber' : 'blue'
}
function showMasterReadOnlyNotice(record: AdmCaseRow) {
  void message.warning(`当前账号不是该主单ADM负责人，只能查看。如需修改，请联系ADM负责人${record.coordinatorName ? `“${record.coordinatorName}”` : ''}。`)
}
function openCase(record: AdmCaseRow, status?: string) {
  const stages = ledgerStages(record)
  const lineStatus = status || (stages.length === 1 ? stages[0].status : undefined)
  void router.push({ path: `/adm/cases/${record.id}`, query: { lineStatus } })
}
function canEditMasterRow(record: AdmCaseRow) {
  const allowed = !!(
    config.value?.permissions.create || config.value?.permissions.manage || config.value?.permissions.review
  )
  const owner = Number(record.coordinatorId) === Number(auth.user?.id)
  return allowed && owner && ['DRAFT', 'ACTIVE'].includes(record.caseStatus)
}
async function openMasterInfo(record: AdmCaseRow) {
  selectedMasterEditable.value = canEditMasterRow(record)
  if (!selectedMasterEditable.value) showMasterReadOnlyNotice(record)
  masterInfoOpen.value = true
  selectedMasterDetail.value = null
  try {
    selectedMasterDetail.value = await admApi.detail(record.id)
  } catch (requestError) {
    masterInfoOpen.value = false
    void message.error(errorText(requestError))
  }
}
async function masterInfoSaved(detail: AdmCaseDetail) {
  selectedMasterDetail.value = detail
  masterInfoOpen.value = false
  await load()
}

const createOpen = ref(false),
  saving = ref(false),
  createError = ref(''),
  fxError = ref(''),
  fxLoading = ref(false),
  fxSnapshot = ref<FxSnapshot | null>(null),
  masterFiles = ref<File[]>([]),
  masters = reactive<Record<CreateReferenceKind, Option[]>>({ diffType: [], currency: [] }),
  form = reactive<Fields>({})
const masterReferenceKinds = ['currency', 'diffType'] as const
type CreateReferenceKind = typeof masterReferenceKinds[number]
const referenceLabels: Record<CreateReferenceKind, string> = {
  currency: '原币币种', diffType: '差异类型',
}
const referenceTtl = 5 * 60 * 1000
const referenceLoadedAt: Partial<Record<CreateReferenceKind, number>> = {}
const referenceRequests: Partial<Record<CreateReferenceKind, Promise<void>>> = {}
const referenceLoading = reactive<Partial<Record<CreateReferenceKind, boolean>>>({})
const referenceErrors = reactive<Partial<Record<CreateReferenceKind, string>>>({})
const referenceError = computed(() => {
  return [...masterReferenceKinds.map((kind) => referenceErrors[kind]), fxError.value].filter(Boolean).join('；')
})
function loadCreateReference(kind: CreateReferenceKind) {
  if (referenceRequests[kind]) return referenceRequests[kind]
  const loadedAt = referenceLoadedAt[kind]
  if (loadedAt !== undefined && Date.now() - loadedAt < referenceTtl) return Promise.resolve()
  referenceLoading[kind] = true
  delete referenceErrors[kind]
  const pending = admApi.options(kind, '', 200).then(
    (rows) => {
      masters[kind] = rows
      referenceLoadedAt[kind] = Date.now()
    },
    (error) => { referenceErrors[kind] = `${referenceLabels[kind]}读取失败：${errorText(error)}` },
  ).finally(() => {
    referenceLoading[kind] = false
    delete referenceRequests[kind]
  })
  referenceRequests[kind] = pending
  return pending
}
function retryCreateReferences() {
  masterReferenceKinds.forEach((kind) => { if (referenceErrors[kind]) void loadCreateReference(kind) })
  if (fxError.value) void loadExchangeRate()
}
const issuerOptions = [
    { value: 'SUPPLIER', label: '供应商' },
    { value: 'AIRLINE', label: '航司' },
  ],
  currencyOptions = computed(() => {
    const rows = masters.currency.length ? masters.currency : [{ code: 'CNY', name: 'CNY' }]
    return rows.map((item) => ({ value: item.code, label: item.name === item.code ? item.code : `${item.name}（${item.code}）` }))
  }),
  diffTypeOptions = computed(() => masters.diffType.map((i) => ({ value: i.code, label: i.name }))),
  leaderOptions = computed(() => admPersonOptions(config.value?.people.leader || []))
const masterCnyAmount = computed(() => {
  if (!fxSnapshot.value) return '—'
  const amount = Number(form.originalAmount || 0), rate = Number(fxSnapshot.value.rateValue)
  return Number.isFinite(amount * rate) ? `¥ ${(amount * rate).toFixed(2)}` : '—'
})
function pickMasterFiles(e: Event) {
  masterFiles.value = Array.from((e.target as HTMLInputElement).files || [])
}
function openCreate() {
  masterFiles.value = []
  Object.assign(form, {
    admNo: '',
    issuerType: 'SUPPLIER',
    issuerName: '',
    airlineName: '',
    currency: 'CNY',
    originalAmount: '',
    issuedDate: '',
    replyDeadline: '',
    remark: '',
    departmentCode: undefined,
    leaderId: undefined,
    diffTypeCode: undefined,
    differenceReason: '',
  })
  createError.value = ''
  createOpen.value = true
  void loadConfig(true)
  masterReferenceKinds.forEach((kind) => { void loadCreateReference(kind) })
  void loadExchangeRate()
}
let fxRequest = 0
async function loadExchangeRate() {
  const seq = ++fxRequest
  const currency = String(form.currency || '')
  fxLoading.value = true
  fxError.value = ''
  fxSnapshot.value = null
  try {
    const snapshot = await admApi.exchangeRate(currency)
    if (seq === fxRequest && createOpen.value) fxSnapshot.value = snapshot
  } catch (e) {
    if (seq === fxRequest && createOpen.value) fxError.value = `汇率读取失败：${errorText(e)}`
  } finally {
    if (seq === fxRequest) fxLoading.value = false
  }
}
async function createCase() {
  if (saving.value) return
  saving.value = true
  createError.value = ''
  try {
    const r = await admApi.create({ ...form, masterOnly: true }, createOperationIdentifier())
    const attachmentErrors: string[] = []
    for (const file of masterFiles.value) {
      try {
        await admApi.upload(Number(r.case.id), file, 'ADM_ORIGINAL')
      } catch (e) {
        attachmentErrors.push(`${file.name}：${errorText(e)}`)
      }
    }
    createOpen.value = false
    if (attachmentErrors.length) {
      void message.warning(
        `主单已保存：${r.case.internalNo}；部分附件上传失败，可进入详情重新上传`,
      )
    } else {
      void message.success(`主单已保存：${r.case.internalNo}`)
    }
    await router.push(`/adm/cases/${r.case.id}`)
  } catch (e) {
    createError.value = errorText(e)
  } finally {
    saving.value = false
  }
}
const importOpen = ref(false),
  importFile = ref<File | null>(null),
  importBusy = ref(false),
  preview = ref<Fields | null>(null),
  importError = ref('')
function openImport() {
  importOpen.value = true
  importFile.value = null
  preview.value = null
  importError.value = ''
}
function selectImport(e: Event) {
  importFile.value = (e.target as HTMLInputElement).files?.[0] || null
  preview.value = null
  importError.value = ''
}
async function downloadTemplate() {
  try {
    const task = await exportTasks.createBackground('adm_import_template', {})
    void message.success(
      task.reused ? '相同模板任务正在进行，已打开导出任务' : '模板已生成，请在页头“导出任务”下载',
    )
  } catch (e) {
    void message.error(errorText(e))
  }
}
async function previewImport() {
  if (!importFile.value) return
  importBusy.value = true
  importError.value = ''
  preview.value = null
  try {
    preview.value = await admApi.importPreview(importFile.value)
  } catch (e) {
    importError.value = errorText(e)
  } finally {
    importBusy.value = false
  }
}
async function commitImport() {
  if (!preview.value?.batchNo) return
  importBusy.value = true
  try {
    await admApi.importCommit(preview.value.batchNo)
    importOpen.value = false
    void message.success('导入完成')
    await load()
  } catch (e) {
    importError.value = errorText(e)
  } finally {
    importBusy.value = false
  }
}
watch(
  () => !isWorkbench.value && ledgerReady.value && canCreate.value,
  (ready) => {
    if (ready) masterReferenceKinds.forEach((kind) => { void loadCreateReference(kind) })
  },
  { immediate: true },
)
watch(isWorkbench, () => {
  if (route.name !== 'adm-cases') return
  workSelection.value = []
  const requestedPage = Number(route.query.page)
  workPage.value = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  workMetric.value = isWorkbench.value ? String(route.query.workMetric || '') : ''
  ordersRequest++
  globalOrdersOpen.value = false
  orderMetric.value = ''
  closeWorkQueue()
  void load()
}, { immediate: true })
watch([workPage, workMetric], ([currentPage, currentMetric]) => {
  if (route.name !== 'adm-cases' || !isWorkbench.value) return
  const nextQuery: Fields = { ...route.query }
  if (currentPage > 1) nextQuery.page = String(currentPage)
  else delete nextQuery.page
  if (currentMetric) nextQuery.workMetric = currentMetric
  else delete nextQuery.workMetric
  if (String(route.query.page || '') === String(nextQuery.page || '') && String(route.query.workMetric || '') === String(nextQuery.workMetric || '')) return
  void router.replace({ query: nextQuery })
})
watch(() => route.name === 'adm-cases' && route.query.create === '1', async (create) => {
  if (!create) return
  await loadConfig()
  if (route.name === 'adm-cases' && route.query.create === '1' && config.value?.permissions.create) {
    const nextQuery = { ...route.query }
    delete nextQuery.create
    await router.replace({ query: nextQuery })
    openCreate()
  }
}, { immediate: true })
onBeforeUnmount(() => {
  fxRequest++
  queueRequest++
  request++
  ordersRequest++
})
</script>
