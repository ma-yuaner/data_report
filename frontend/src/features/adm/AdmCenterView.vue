<template>
  <div class="v05-app embedded">
    <main class="v05-main">
      <section v-if="isWorkbench" class="v05-page">
        <header class="v05-top">
          <div>
            <h1>我的工作台</h1>
            <p>{{ roleHint }}</p>
          </div>
          <div class="v05-actions">
            <button :disabled="!canOperatorWork || !exportCandidates.length" @click="openExportSelection">
              接单并导出（可选 {{ exportCandidates.length }}）</button
            ><button v-if="canOperatorWork" @click="operatorImportOpen = true">导入处理结果</button
            ><button :disabled="loading" @click="load">刷新任务</button>
          </div>
        </header>
        <div v-if="workbenchReady" class="v05-metrics">
          <button
            v-for="item in workMetrics"
            :key="item.key"
            :class="{ selected: workMetric === item.key }"
            @click="openWorkMetric(item.key)"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <a-alert v-if="configError" type="warning" show-icon :message="configError" />
        <a-alert v-if="workbenchSummary.truncated" type="warning" show-icon
          :message="`当前显示前 ${workbenchItems.length} 条任务，共 ${workbenchSummary.total} 条；分类数仅统计已加载任务。`" />
        <div class="v05-work-list">
          <p v-if="loading" class="v05-card v05-empty" role="status">正在读取 ADM 任务…</p>
          <p v-else-if="error" class="v05-card v05-empty"><a-button @click="load">重试</a-button></p>
          <div v-else-if="pagedTasks.length" class="work-task-table">
            <div class="work-task-row work-task-head" aria-hidden="true">
              <span>ADM / 内部明细</span><span>任务类型</span><span>当前责任分配</span><span>当前需要处理</span><span>处理截止</span><span>操作</span>
            </div>
            <div v-for="task in pagedTasks" :key="`${task.caseId}-${task.lineId}-${task.kind}`" class="work-task-row">
              <div><b>{{ task.admNo || task.internalNo }}</b><small>{{ task.lineInternalNo }}</small></div>
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
              <a-button v-else type="primary" @click="openTask(task)">去处理 →</a-button>
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
        <header class="v05-top">
          <div>
            <h1>ADM 台账</h1>
            <p>查看公司 ADM 全貌、处理进度、结案阻断与当前风险。</p>
          </div>
          <div class="v05-actions">
            <button :disabled="!canCreate" @click="openImport">跨主单批量导入</button
            ><button :disabled="!canCreate" class="primary" @click="openCreate">＋ 新建 ADM</button>
          </div>
        </header>
        <p class="v05-label">主单指标 · 点击筛选台账</p>
        <div v-if="ledgerReady" class="v05-metrics">
          <button
            v-for="item in masterMetrics"
            :key="item.key"
            :class="{ selected: metric === item.key }"
            @click="selectMetric(item.key)"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <p class="v05-label">订单指标 · 点击查看订单清单</p>
        <div v-if="ledgerReady" class="v05-metrics">
          <button
            v-for="item in orderMetrics"
            :key="item.key"
            :disabled="loading || !!error"
            :class="{ selected: orderMetric === item.key }"
            @click="openGlobalOrders(item.key)"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <a-alert v-if="configError" type="warning" show-icon :message="configError" />
        <div class="v05-card">
          <div class="v05-toolbar">
            <label
              >⌕<input v-model="filters.search" placeholder="搜索 ADM 单号、内部主单编号、下发方" @keyup.enter="query"
            /></label>
            <div>
              <select v-model="filters.status" @change="query">
                <option value="">全部状态</option>
                <option v-for="status in config?.caseStatuses || []" :key="status" :value="status">
                  {{ label(status) }}
                </option></select
              ><button @click="resetFilters">重置</button>
            </div>
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
        :locale="{ emptyText: queueError ? '读取失败' : '当前没有符合条件的记录' }"
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
      ><div class="v05-table-wrap global-order-table">
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
      :title="createStep === 1 ? '新建 ADM 主单' : '录入订单明细'"
      width="1180px"
      :footer="null"
      wrap-class-name="v05-modal"
      ><a-alert
        type="info"
        show-icon
        message="先填写主单，再录入一笔或多笔订单；明细金额合计必须等于主单金额。"
        style="margin-bottom: 16px"
      /><a-alert
        v-if="referenceError"
        type="warning"
        show-icon
        :message="referenceError"
        style="margin-bottom: 16px"
      /><template v-if="createStep === 1"
        ><div class="v05-form-grid">
          <label><span class="form-field-label">ADM 单号 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.admNo" /></label
          ><label
            ><span class="form-field-label">下发方类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
              v-model:value="form.issuerType"
              :options="issuerOptions"
              @change="issuerChanged" /></label
          ><label v-if="form.issuerType === 'AIRLINE'"><span class="form-field-label">航司名称 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.issuerName" /></label
          ><label v-else
            ><span class="form-field-label">下发方 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
              v-model:value="form.issuerCode"
              show-search
              :filter-option="filterOption"
              :options="issuerMasterOptions"
              @change="issuerSelected" /></label
          ><label
            ><span class="form-field-label">原币币种 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
              v-model:value="form.currency"
              :options="currencyOptions"
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
          ><label class="wide">备注（选填）<a-textarea v-model:value="form.remark" :rows="2" /></label
          ><label class="wide"
            >主单公共附件（选填）<input type="file" multiple @change="pickMasterFiles" /><span>{{
              masterFiles.map((file) => file.name).join('、') || '未选择附件'
            }}</span></label
          >
        </div>
        <p class="hint"><b>*</b> 为必填项。ADM负责人由系统自动记录；汇率保存为创建时快照。</p>
        <div class="v05-modal-actions">
          <button @click="createOpen = false">取消</button
          ><button class="primary" @click="createStep = 2">保存并录入订单</button>
        </div></template
      >
      <template v-else
        ><p class="context">
          <b>{{ form.admNo }}</b
          > {{ form.issuerName }} 原币总金额 {{ form.currency }} {{ form.originalAmount }} 处理截止
          {{ form.replyDeadline || '未设置' }}
        </p>
        <p class="v05-label">订单明细 · OTA平台、OTA订单号、供应商、航司、票号、PNR均为选填</p>
        <div v-for="(line, index) in form.lines" :key="line.key" class="v05-line-card">
          <header>
            <b>订单明细 {{ Number(index) + 1 }}</b
            ><button v-if="form.lines.length > 1" class="danger" @click="form.lines.splice(Number(index), 1)">
              移除
            </button>
          </header>
          <div class="v05-form-grid">
            <label>OTA订单号（选填）<a-input v-model:value="line.otaOrderNo" /></label
            ><label>票号（选填）<a-input v-model:value="line.ticketNo" /></label
            ><label>PNR编码（选填）<a-input v-model:value="line.pnr" /></label
            ><label
              >OTA平台（选填）<a-select
                v-model:value="line.otaCode"
                allow-clear
                :options="otaOptions"
                @change="(v?: string) => selectOption(line, 'ota', v)" /></label
            ><label
              ><span class="form-field-label">业务归属部门 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
                v-model:value="line.departmentCode"
                show-search
                :filter-option="filterOption"
                :options="departmentOptions"
                @change="(v: string) => selectOption(line, 'department', v)" /></label
            ><label
              ><span class="form-field-label">负责组长 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
                v-model:value="line.leaderId"
                :options="leaderOptions"
                @change="(v: string) => selectLeader(line, v)" /></label
            ><label>截止时间（继承主单）<a-input :value="form.replyDeadline" readonly /></label
            ><label
              >供应商（选填）<a-select
                v-model:value="line.supplierCode"
                allow-clear
                :options="supplierOptions"
                @change="(v?: string) => selectOption(line, 'supplier', v)" /></label
            ><label>航司（选填）<a-input v-model:value="line.airlineName" /></label
            ><label><span class="form-field-label">ADM金额（原币） <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="line.originalAmount" /></label
            ><label>币种（继承主单）<a-input :value="form.currency" readonly /></label
            ><label>ADM金额（人民币，系统换算）<a-input :value="lineCnyAmount(Number(index))" readonly /></label
            ><label class="wide"
              >订单情况说明（选填）<a-textarea
                v-model:value="line.investigationNote"
                :rows="2"
                placeholder="填写当前已知的订单情况，操作员办理时可继续更新" /></label
            ><label
              ><span class="form-field-label">差异类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true"
                v-model:value="line.diffTypeCode"
                show-search
                :filter-option="filterOption"
                :options="diffTypeOptions"
                @change="(v: string) => selectOption(line, 'diffType', v)" /></label
            ><label class="wide"><span class="form-field-label">细分差异原因 <span class="form-required-mark" aria-hidden="true">*</span></span><a-textarea aria-required="true" v-model:value="line.differenceReason" :rows="3" /></label>
          </div>
        </div>
        <section class="entry-extra">
          <h3>本次已录入 {{ form.lines.length }} 笔</h3>
          <div class="v05-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>序号</th>
                  <th>OTA订单号 / 票号 / PNR</th>
                  <th>部门 / 组长</th>
                  <th>原币金额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in form.lines" :key="`summary-${line.key}`">
                  <td>{{ Number(index) + 1 }}</td>
                  <td>
                    {{ line.otaOrderNo || '未填写' }} / {{ line.ticketNo || '未填写' }} / {{ line.pnr || '未填写' }}
                  </td>
                  <td>{{ line.departmentName || '未选择' }} / {{ line.leaderName || '未选择' }}</td>
                  <td>{{ form.currency }} {{ line.originalAmount || '0.00' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <a-alert v-if="createError" type="error" show-icon :message="createError" style="margin-top: 12px" />
        <div class="v05-modal-actions">
          <button @click="createStep = 1">返回主单</button><button @click="addLine">＋ 继续新增一笔</button
          ><button :disabled="saving" @click="createCase(true)">保存草稿</button
          ><button class="primary" :disabled="saving" @click="createCase(false)">保存并进入详情</button>
        </div></template
      >
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
  isWorkbench = computed(() => route.meta.admView === 'workbench')
const config = ref<AdmConfig | null>(null),
  rows = ref<AdmCaseRow[]>([]),
  ledgerSummary = ref<Fields>({}),
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
function loadConfig() {
  if (config.value) return Promise.resolve()
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
    ledgerSummary.value = result.summary || {}
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
const availableRoles = computed(() => {
  if (auth.user?.isAdmin) return ['ADM负责人', '组长', '操作人员']
  const p = config.value?.permissions,
    roles: string[] = []
  if (p?.review || p?.create || p?.collection || p?.diffMatch || p?.close || p?.assignLeader) roles.push('ADM负责人')
  if (p?.assign || p?.assignOperator) roles.push('组长')
  if (p?.handle) roles.push('操作人员')
  return roles
})
const tasks = computed<Fields[]>(() =>
  workbenchItems.value.map((line): Fields => {
    const transferTask = line.taskType === 'TRANSFER_ACCEPT'
    const returnMode = taskReturnMode(line)
    const reviewWithdrawn = line.reviewStatus === 'WITHDRAWN' || line.latestReviewStatus === 'WITHDRAWN'
    const role = transferTask
      ? '操作人员'
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
const roleHint = computed(() =>
  !config.value
    ? '按当前账号的权限展示 ADM 任务。'
    : availableRoles.value.length
    ? '合并展示当前账号需要处理的全部ADM任务，每笔任务标明本次办理职责。'
    : '当前账号仅有查看权限，可前往ADM台账查看数据。',
)
const workMetrics = computed(() => {
  const due = (k: string) => tasks.value.filter((t) => dueKind(t) === k).length,
    items: Fields[] = []
  if (availableRoles.value.includes('ADM负责人'))
    items.push(
      { key: 'assignLeader', title: '待分配组长', value: tasks.value.filter((t) => t.kind === 'assignLeader').length },
      { key: 'review', title: '待审核', value: tasks.value.filter((t) => t.kind === 'review').length },
      { key: 'diff', title: '待匹配差异单', value: tasks.value.filter((t) => t.kind === 'diff').length },
      { key: 'collection', title: '待回款跟进', value: tasks.value.filter((t) => t.kind === 'collection').length },
    )
  if (auth.user?.isAdmin || config.value?.permissions.close)
    items.push({ key: 'close', title: '可以结案', value: Number(workbenchSummary.value.closableCaseCount || 0) })
  if (availableRoles.value.includes('组长'))
    items.push({ key: 'assign', title: '待分配操作员', value: tasks.value.filter((t) => t.kind === 'assign').length })
  if (availableRoles.value.some((role) => role === '组长' || role === '操作人员'))
    items.push({ key: 'transfer', title: '转派申请', value: Number(workbenchSummary.value.pendingTransferCount || 0) })
  if (availableRoles.value.includes('操作人员'))
    items.push(
      { key: 'transferAccept', title: '待确认转派', value: tasks.value.filter((t) => t.kind === 'transferAccept').length },
      { key: 'accept', title: '待接单', value: tasks.value.filter((t) => t.kind === 'accept').length },
      { key: 'process', title: '本人待办理', value: tasks.value.filter((t) => t.kind === 'process').length },
      {
        key: 'codeReminder',
        title: '编码恢复提醒',
        value: tasks.value.filter((item) => item.recoveryStatus === 'REMINDER_DUE').length,
      },
      {
        key: 'appeal',
        title: '申诉中',
        value: tasks.value.filter((item) => item.appealStatus === 'IN_PROGRESS').length,
      },
    )
  items.push(
    { key: 'soon', title: '即将超时', value: due('soon') },
    { key: 'late', title: '已超时', value: due('late') },
  )
  return items
})
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
  if (row.transferStatus === 'PENDING') return row.actionable ? '待目标操作员确认' : '待确认 · 当前状态不可处理'
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
function openWorkMetric(key: string) {
  if (key === 'close' || key === 'transfer') {
    workQueue.value = key
    queueStatus.value = 'pending'
    resetWorkQueuePage()
    return
  }
  workMetric.value = workMetric.value === key ? '' : key
  workPage.value = 1
}
function openTask(t: Fields) {
  void router.push({
    path: `/adm/cases/${t.caseId}`,
    query: {
      lineId: t.lineId,
      taskAction: t.kind,
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
const isPendingCase = (r: AdmCaseRow) =>
    ['DRAFT', 'PENDING'].includes(r.caseStatus) ||
    Number(r.pendingOperatorCount || 0) + Number(r.pendingAcceptCount || 0) > 0,
  isOpenCase = (r: AdmCaseRow) => !['CLOSED', 'VOIDED'].includes(r.caseStatus)
const masterMetrics = computed(() => [
  { key: 'range', title: '范围内主单', value: Number(ledgerSummary.value.caseCount ?? total.value) },
  { key: 'pending', title: '待处理主单', value: Number(ledgerSummary.value.pendingCaseCount ?? rows.value.filter(isPendingCase).length) },
  { key: 'open', title: '未结案主单', value: Number(ledgerSummary.value.openCaseCount ?? rows.value.filter(isOpenCase).length) },
  { key: 'soon', title: '即将超时主单', value: Number(ledgerSummary.value.soonCaseCount ?? rows.value.filter((r) => riskText(r) === '即将超时').length) },
  { key: 'late', title: '已超时主单', value: Number(ledgerSummary.value.overdueCaseCount ?? rows.value.filter((r) => riskText(r) === '已超时').length) },
])
const openLineCount = (r: AdmCaseRow) =>
  Math.max(
    0,
    Number(r.lineCount || 0) - Number(r.completedLineCount || 0) - Number(r.voidedLineCount || 0) -
      Number(r.historicalLineCount || 0),
  )
const sumRows = (selector: (row: AdmCaseRow) => number) => rows.value.reduce((sum, row) => sum + selector(row), 0)
const orderMetrics = computed(() => [
  { key: 'all', title: '订单明细', value: Number(ledgerSummary.value.lineCount ?? sumRows((r) => Number(r.lineCount || 0))) },
  {
    key: 'pending',
    title: '待处理订单明细',
    value: Number(ledgerSummary.value.pendingLineCount ?? sumRows((r) => Number(r.pendingLeaderCount || 0) + Number(r.pendingOperatorCount || 0) + Number(r.pendingAcceptCount || 0))),
  },
  {
    key: 'open',
    title: '未完成订单明细',
    value: Number(ledgerSummary.value.openLineCount ?? sumRows(openLineCount)),
  },
  {
    key: 'soon',
    title: '即将超时订单明细',
    value: Number(ledgerSummary.value.soonLineCount ?? sumRows((r) => (riskText(r) === '即将超时' ? openLineCount(r) : 0))),
  },
  {
    key: 'late',
    title: '已超时订单明细',
    value: Number(ledgerSummary.value.overdueLineCount ?? sumRows((r) => (riskText(r) === '已超时' ? openLineCount(r) : 0))),
  },
])
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
  metric.value = metric.value === k ? '' : k
  page.value = 1
  void load()
}
const activeLineCount = (r: AdmCaseRow) => Math.max(0, Number(r.lineCount || 0) - Number(r.voidedLineCount || 0)),
  progressWidth = (r: AdmCaseRow) =>
    `${activeLineCount(r) ? Math.min(100, (Number(r.completedLineCount || 0) / activeLineCount(r)) * 100) : 100}%`
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
  const stages = ledgerStages(row)
  if (stages.length === 1) return `查看${stages[0].title}明细`
  if (!stages.length && canCloseLedgerCase(row)) return '查看结案'
  return '订单明细'
}
function canCloseLedgerCase(row: AdmCaseRow) {
  return Number(row.lineCount) > 0 && !!config.value?.permissions.close &&
    Number(row.coordinatorId) === myId.value && !openLineCount(row)
}
function blockerText(row: AdmCaseRow) {
  if (row.caseStatus !== 'ACTIVE') return '—'
  if (!Number(row.lineCount)) return '暂无订单明细'
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
  createStep = ref(1),
  saving = ref(false),
  createError = ref(''),
  referenceError = ref(''),
  fxLoading = ref(false),
  fxSnapshot = ref<FxSnapshot | null>(null),
  masterFiles = ref<File[]>([]),
  masters = reactive<Record<string, Option[]>>({ department: [], diffType: [], ota: [], supplier: [], currency: [] }),
  form = reactive<Fields>({ lines: [] })
const issuerOptions = [
    { value: 'SUPPLIER', label: '供应商' },
    { value: 'PLATFORM', label: '平台' },
    { value: 'AIRLINE', label: '航司' },
  ],
  currencyOptions = computed(() => {
    const rows = masters.currency.length ? masters.currency : [{ code: 'CNY', name: 'CNY' }]
    return rows.map((item) => ({ value: item.code, label: item.name === item.code ? item.code : `${item.name}（${item.code}）` }))
  }),
  mapOptions = (x: Option[]) => x.map((i) => ({ value: i.code, label: `${i.name}（${i.code}）` })),
  departmentOptions = computed(() => mapOptions(masters.department)),
  diffTypeOptions = computed(() => masters.diffType.map((i) => ({ value: i.code, label: i.name }))),
  otaOptions = computed(() => mapOptions(masters.ota)),
  supplierOptions = computed(() => mapOptions(masters.supplier)),
  issuerMasterOptions = computed(() => (form.issuerType === 'PLATFORM' ? otaOptions.value : supplierOptions.value)),
  leaderOptions = computed(() => (config.value?.people.leader || []).map((i) => ({ value: i.id, label: i.name }))),
  filterOption = (input: string, o: Fields) =>
    String(o.label || '')
      .toLowerCase()
      .includes(input.toLowerCase())
const masterCnyAmount = computed(() => {
  const amount = Number(form.originalAmount || 0), rate = Number(fxSnapshot.value?.rateValue || 0)
  return Number.isFinite(amount * rate) ? `¥ ${(amount * rate).toFixed(2)}` : '—'
})
const lineCnyAmount = (index: number) => {
  const rate = Number(fxSnapshot.value?.rateValue || 0)
  if (!Number.isFinite(rate)) return '—'
  const rounded = form.lines.map((line: Fields) => Number((Number(line.originalAmount || 0) * rate).toFixed(2)))
  if (index === form.lines.length - 1) {
    const master = Number((Number(form.originalAmount || 0) * rate).toFixed(2))
    return `¥ ${(master - rounded.slice(0, -1).reduce((sum: number, value: number) => sum + value, 0)).toFixed(2)}`
  }
  return `¥ ${rounded[index].toFixed(2)}`
}
function blankLine() {
  return {
    key: createOperationIdentifier(),
    originalAmount: '',
    departmentCode: '',
    departmentName: '',
    leaderId: undefined,
    leaderName: '',
    diffTypeCode: '',
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
  }
}
function addLine() {
  form.lines.push(blankLine())
}
function pickMasterFiles(e: Event) {
  masterFiles.value = Array.from((e.target as HTMLInputElement).files || [])
}
async function openCreate() {
  createStep.value = 1
  masterFiles.value = []
  Object.assign(form, {
    admNo: '',
    issuerType: 'SUPPLIER',
    issuerCode: '',
    issuerName: '',
    currency: 'CNY',
    originalAmount: '',
    issuedDate: '',
    replyDeadline: '',
    remark: '',
    lines: [blankLine()],
  })
  createError.value = ''
  referenceError.value = ''
  fxSnapshot.value = null
  createOpen.value = true
  const kinds = ['department', 'diffType', 'ota', 'supplier', 'currency'] as const
  const results = await Promise.allSettled(kinds.map((kind) => admApi.options(kind, '', 200)))
  const failures: string[] = []
  const labels = { department: '业务部门', diffType: '差异类型', ota: 'OTA平台', supplier: '供应商', currency: '原币币种' }
  results.forEach((result, index) => {
    const kind = kinds[index]
    if (result.status === 'fulfilled') masters[kind] = result.value
    else {
      masters[kind] = []
      failures.push(`${labels[kind]}：${errorText(result.reason)}`)
    }
  })
  referenceError.value = failures.length ? `部分基础资料读取失败：${failures.join('；')}` : ''
  await loadExchangeRate()
}
async function loadExchangeRate() {
  fxLoading.value = true
  fxSnapshot.value = null
  try {
    fxSnapshot.value = await admApi.exchangeRate(String(form.currency || ''))
  } catch (e) {
    referenceError.value = `汇率读取失败：${errorText(e)}`
  } finally {
    fxLoading.value = false
  }
}
function issuerChanged() {
  form.issuerCode = ''
  form.issuerName = ''
}
function issuerSelected(code: string) {
  const i = (form.issuerType === 'PLATFORM' ? masters.ota : masters.supplier).find((v) => v.code === code)
  form.issuerName = i?.name || ''
}
function selectOption(line: Fields, kind: string, code?: string) {
  const i = masters[kind].find((v) => v.code === code),
    p = kind === 'diffType' ? 'diffType' : kind
  line[`${p}Code`] = code || null
  line[`${p}Name`] = i?.name || null
}
function selectLeader(line: Fields, id: string) {
  line.leaderName = config.value?.people.leader.find((v) => v.id === id)?.name || ''
}
async function createCase(saveAsDraft: boolean) {
  saving.value = true
  createError.value = ''
  try {
    const r = await admApi.create({ ...JSON.parse(JSON.stringify(form)), saveAsDraft }, createOperationIdentifier())
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
        `${saveAsDraft ? '草稿已保存' : '主单及订单已创建'}：${r.case.internalNo}；部分附件上传失败，可进入详情重新上传`,
      )
    } else {
      void message.success(saveAsDraft ? `草稿已保存：${r.case.internalNo}` : `已创建：${r.case.internalNo}`)
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
watch(() => route.name, (name) => {
  if (name !== 'adm-workbench' && name !== 'adm-cases') return
  ordersRequest++
  globalOrdersOpen.value = false
  orderMetric.value = ''
  closeWorkQueue()
  void load()
}, { immediate: true })
watch([workPage, workMetric], ([currentPage, currentMetric]) => {
  if (route.name !== 'adm-workbench') return
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
    await router.replace({ path: '/adm/cases' })
    await openCreate()
  }
}, { immediate: true })
onBeforeUnmount(() => {
  queueRequest++
  request++
  ordersRequest++
})
</script>
