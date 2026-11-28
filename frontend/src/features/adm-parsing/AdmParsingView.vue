<template>
  <div class="page-wrap parsing-page">
    <PageHeader
      eyebrow="ADM 控制台 / ADM 解析"
      title="ADM 解析"
      description="上传材料、提取并核对字段；在ADM任务台账选择待登记来件，补充信息后登记。"
    >
      <a-button @click="rulesOpen = true">字段与校验规则</a-button>
      <a-button :loading="loading" @click="refresh">刷新</a-button>
      <a-button
        v-if="selected && (auth.user?.isAdmin || auth.user?.menuCodes?.includes('annotation.center'))"
        @click="router.push({ name: 'annotations', query: { admTask: selected.id } })"
      >
        用于样本标注
      </a-button>
      <a-button type="primary" :disabled="!status?.canUpload" @click="openUpload()">上传文件</a-button>
    </PageHeader>
    <a-alert
      v-if="status?.localTesting"
      type="info"
      show-icon
      message="本地隔离测试 · 真实文件读写与SQLite持久化；未连接生产业务库。模型接入是否启用以下方配置状态为准。"
    />
    <a-alert
      v-if="status && !status.ai.ready"
      type="warning"
      show-icon
      message="ADM 解析 API 尚未配置或启用"
      description="可以真实上传并保存文件。点击解析会读取原文并保留配置缺失原因；配置API后可重新解析，不会生成模拟业务结果。"
    />
    <a-alert v-if="error" type="error" show-icon :message="error" closable @close="error = ''" />
    <p v-if="notice && !selected?.candidate" class="parsing-feedback" role="status">{{ notice }}</p>
    <div class="parsing-workspace" :class="{ 'has-summary': selected }">
      <aside class="parsing-pane">
        <h2>解析来件 · {{ total }} 件</h2>
        <div class="parsing-filter">
          <a-select v-model:value="filter" aria-label="解析状态" :options="stateOptions" @change="changeFilter" />
        </div>
        <a-spin :spinning="loading"
          ><button
            v-for="item in items"
            :key="item.id"
            class="parsing-item"
            :aria-pressed="selected?.id === item.id"
            @click="select(item.id)"
          >
            <b>{{ item.title }}</b
            ><span>{{ item.files.length }} 份附件 · {{ formatTime(item.updatedAt) }}</span
            ><a-tag :color="stateColor(item.state)">{{ stateLabel(item.state) }}</a-tag></button
          ><a-empty v-if="!items.length && !loading" description="暂无来件，请上传文件或调整状态筛选" /></a-spin
        ><a-pagination
          v-if="total"
          v-model:current="page"
          :total="total"
          :page-size="20"
          size="small"
          :show-size-changer="false"
          @change="loadList"
        />
      </aside>
      <header v-if="selected" class="parsing-pane parsing-summary">
        <div>
          <h2>{{ selected.candidate?.adm?.number ? 'ADM ' + selected.candidate.adm.number : selected.title }}</h2>
          <p v-if="selected.candidate?.adm?.amount != null" class="parsing-amount">
            {{ selected.candidate.adm.amount }} {{ selected.candidate.adm.currency || '币种待核对' }}
          </p>
          <div class="parsing-tags">
            <a-tag :color="stateColor(selected.state)">{{ stateLabel(selected.state) }}</a-tag
            ><a-tag :color="selected.saveStatus === 'FAILED' ? 'error' : 'success'">{{
              selected.saveStatus === 'FAILED'
                ? '结果保存失败，可重试'
                : ['SUCCEEDED', 'FAILED'].includes(selected.state)
                  ? '处理结果已保存'
                  : '任务记录已保存'
            }}</a-tag
            ><a-tag>第 {{ selected.attempts }} 次解析</a-tag>
          </div>
        </div>
        <div class="parsing-actions">
          <a-button
            v-if="selected.saveStatus === 'FAILED'"
            type="primary"
            :loading="acting"
            :disabled="!status?.canUpload"
            @click="retrySave"
            >重试保存</a-button
          >
          <a-button
            v-else-if="selected.candidate && !selected.registration && !selected.intakeBlock && !selected.supplementPending && !selected.review"
            type="primary"
            :loading="acting"
            :disabled="!status?.canUpload || busy"
            @click="revalidate"
            >重新校验并保存（不调用模型）</a-button
          >
          <a-button
            v-else-if="!selected.registration && !selected.intakeBlock && !selected.review"
            type="primary"
            :loading="acting"
            :disabled="!status?.canUpload || busy"
            @click="startParse"
            >{{ selected.supplementPending ? '核对材料后重新解析' : selected.attempts ? '重试模型解析' : '开始解析' }}</a-button
          >
          <template v-if="selected.isUploader && !selected.registration && !busy && status?.canUpload">
            <a-button v-if="selected.intakeBlock" @click="openReview('intake')">核对收件</a-button>
            <a-button v-if="selected.intakeBlock" @click="openUpload('replace')">替换整组材料</a-button>
            <a-button v-else-if="selected.supplier" @click="openUpload('append')">追加附件</a-button>
            <a-button
              v-if="selected.candidate && !selected.intakeBlock && !selected.supplementPending && selected.saveStatus === 'SAVED'"
              type="primary"
              @click="openReview('result')"
            >{{ selected.review ? '查看或修正核对结果' : '核对并确认待登记' }}</a-button>
          </template>
          <span v-if="selected.elapsedSeconds !== undefined" class="parsing-muted"
            >解析耗时 {{ selected.elapsedSeconds }} 秒</span
          >
          <details
            v-if="selected.candidate && !selected.registration && !selected.intakeBlock && !selected.supplementPending && !selected.review && !busy && selected.saveStatus !== 'FAILED'"
            class="parsing-extra-actions"
          >
            <summary>其他操作</summary>
            <p>重新调用模型会产生用量；来源校验问题请优先重新校验。</p>
            <a-popconfirm title="确认重新调用模型？将产生额外用量，已有结果保留在历史中。" @confirm="startParse"
              ><a-button :disabled="!status?.canUpload || acting">重新调用模型</a-button></a-popconfirm
            >
          </details>
          <a-popconfirm
            v-if="selected.canDelete"
            title="确认删除此来件？删除后将从来件列表和待登记列表移除。"
            ok-text="删除"
            cancel-text="取消"
            :ok-button-props="{ danger: true }"
            @confirm="deleteIntake"
          >
            <a-button danger :disabled="acting">删除来件</a-button>
          </a-popconfirm>
        </div>
      </header>
      <section class="parsing-pane parsing-result">
        <h2>核对结果</h2>
        <div v-if="selected" class="parsing-content">
          <a-alert v-if="selected.intakeBlock" type="warning" show-icon :message="'待核对 · ' + selected.intakeBlock">
            <template v-if="selected.duplicateIntakeId" #action>
              <a-button size="small" @click="select(selected.duplicateIntakeId!)">查看已有来件</a-button>
            </template>
          </a-alert>
          <a-alert v-else-if="selected.supplementPending" type="warning" show-icon message="已补件，待重新解析。旧解析结果仅供查阅。" />
          <a-alert v-else-if="selected.review && !selected.registration" type="success" show-icon :message="'已核对 · 待登记 ' + selected.review.at" />
          <a-alert
            v-if="selected.error && !selected.candidate"
            type="error"
            show-icon
            :message="selected.error.message"
            :description="selected.error.code"
          />
          <a-alert
            v-if="selected.saveStatus === 'FAILED'"
            type="warning"
            show-icon
            message="解析结果已保留在服务器恢复文件中，尚未完成数据库保存。只重试保存，不重复调用模型。"
          />
          <a-alert v-if="selected.registration" type="success" show-icon style="margin: 12px 0">
            <template #message
              >已登记台账：<router-link :to="`/adm/cases/${selected.registration.caseId}`">{{
                selected.registration.internalNo
              }}</router-link>
              · 登记人 {{ selected.registration.by }} · {{ selected.registration.at }}</template
            >
          </a-alert>
          <div
            v-if="busy || selected.saveStatus === 'FAILED'"
            class="parsing-progress"
            role="status"
            aria-live="polite"
          >
            <strong>{{ progressText }}</strong>
            <p v-if="selected.elapsedSeconds !== undefined">
              本次已用 {{ selected.elapsedSeconds }} 秒 · 最近获取状态 {{ lastChecked || '—' }}
            </p>
            <p v-if="busy">
              排队 → 读取原件 → 等待模型 → 校验字段 → 保存结果。每3秒查询；模型未返回时无法提供生成百分比。
            </p>
            <p v-if="selected.stage === 'MODEL' && busy">原文已读取并保存，正在等待模型响应。请勿重复提交。</p>
            <p v-if="selected.state === 'RUNNING' && !selected.stage">
              此任务由旧版启动，未记录具体阶段；可等待结果，暂勿重新解析。
            </p>
          </div>
          <a-tabs v-model:active-key="tab">
            <a-tab-pane key="issues" :tab="issueTabLabel">
              <a-alert
                v-if="selected.candidate && !busy"
                :type="errorIssues.length ? 'warning' : 'success'"
                show-icon
                :message="errorIssues.length ? '校验未通过' : '字段和来源校验通过'"
                :description="errorIssues.length + ' 项需处理，' + warningIssues.length + ' 项待核对'"
              />
              <article v-for="(issue, i) in reviewIssues" :key="i" class="parsing-issue">
                <div class="parsing-issue-header">
                  <strong>{{ issueLabel(issue) }}</strong>
                  <span v-if="issueValue(issue) != null" class="parsing-issue-value">{{ issueValue(issue) }}</span>
                  <a-tag :color="issue.level === 'error' ? 'error' : 'warning'">
                    {{ issue.level === 'error' ? '需处理' : '待核对' }}
                  </a-tag>
                  <button class="parsing-source" @click="locate(issueTarget(issue))">查看原文 →</button>
                </div>
                <p>{{ issue.message }}</p>
                <small>{{ issue.path }} · {{ issue.code }}</small>
              </article>
              <p v-if="!reviewIssues.length && !selected.candidate">暂无校验问题。</p>
              <details v-if="selected.adjustments?.length">
                <summary>来源兼容处理记录</summary>
                <p v-for="(item, i) in selected.adjustments" :key="i">{{ item.path }}：{{ item.message }}</p>
              </details>
            </a-tab-pane>
            <a-tab-pane key="fields" tab="提取字段">
              <p v-if="!selected.candidate" class="parsing-muted">
                尚无模型字段结果。原件、读取内容和失败原因仍会保留。
              </p>
              <template v-if="selected.candidate"
                ><button
                  v-for="field in fields"
                  :key="field.key"
                  class="parsing-field"
                  :class="{ 'parsing-field-error': errorIssues.some((issue) => issue.path === `/adm/${field.key}`) }"
                  :disabled="selected.candidate.adm?.[field.key] == null"
                  @click="locate(`/adm/${field.key}`)"
                >
                  <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span
                  ><b>{{ selected.candidate.adm?.[field.key] ?? '未提取到' }}</b
                  ><small>{{ selected.candidate.adm?.[field.key] == null ? '未提供' : '来源' }}</small>
                </button>
                <div v-for="field in optionalLists" :key="field.key" class="parsing-airline">
                  <span>{{ field.label }}</span>
                  <span v-if="!selected.candidate.adm?.[field.key]?.length">未提取到</span>
                  <button
                    v-for="(item, index) in selected.candidate.adm?.[field.key]"
                    :key="index"
                    class="parsing-source"
                    @click="locate(`/adm/${field.key}/${index}`)"
                  >
                    {{ item }}
                  </button>
                </div>
                <div class="parsing-airline">
                  <span>系统航司</span
                  ><b v-if="selected.airlineMatch?.status === 'MATCHED'"
                    >{{ selected.airlineMatch.name }}（{{ selected.airlineMatch.code }}）</b
                  ><span v-else>{{ airlineStatus(selected.airlineMatch?.status) }}</span>
                </div>
                <div class="parsing-airline">
                  <span>Related Document Number（关联票号）</span>
                  <span v-if="!selected.relatedDocuments?.length">未提取到关联票号，可重新校验已保存结果</span>
                  <button
                    v-for="document in selected.relatedDocuments"
                    :key="`${document.segmentId}-${document.number}`"
                    class="parsing-source"
                    @click="locateSegment(document.segmentId)"
                  >
                    {{ document.number }} · {{ ticketLabel(document.ticketType) }} · {{ document.locator }}
                  </button>
                </div>
              </template>
              <p v-if="selected.candidate && status?.schemaVersion && selected.candidate.schemaVersion !== status.schemaVersion">
                此为旧版结果，点击“重新校验并保存”应用新口径，不调用模型。
              </p>
              <p class="parsing-muted">解析结果用于人工核对，不自动新建ADM或恢复PNR。</p>
            </a-tab-pane>
            <a-tab-pane key="locators" tab="订座编码（合并）">
              <a-empty v-if="!selected.locatorGroups?.length" description="暂无具备原文依据的订座编码" />
              <a-descriptions v-else bordered size="small" :column="1">
                <a-descriptions-item v-for="(group, index) in selected.locatorGroups" :key="index" label="GDS / PCC / PNR">
                  {{ group.gds || 'GDS待核对' }} / {{ group.pcc || 'PCC待核对' }} / {{ group.pnr }}
                  <a-tag>{{ group.role === 'UNKNOWN' ? '归属待核对' : group.role === 'AIRLINE' ? '航司PNR' : 'GDS PNR' }}</a-tag>
                  <div v-for="(ref, position) in group.evidence" :key="position">
                    <a-button type="link" size="small" @click="locateSegment(ref.segmentId, ref.quote)">查看原文 {{ position + 1 }}</a-button>
                  </div>
                </a-descriptions-item>
              </a-descriptions>
            </a-tab-pane>
            <a-tab-pane key="lines" :tab="'交易明细 ' + displayLines.length">
              <a-empty v-if="!displayLines.length" description="暂无交易明细" />
              <p v-if="selected.attachmentFees?.length" class="parsing-muted">
                附件费用保留原始列名和数值；币种未明确时不猜测、不换汇，不与主单正式金额合计。
              </p>
              <div v-if="displayLines.length" class="parsing-table">
                <table>
                  <thead>
                    <tr>
                      <th>交易 / 编码（按来源区分）</th>
                      <th>票号 / 系统 / PCC</th>
                      <th>金额用途 / 币种 / 佣金</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(entry, i) in displayLines" :key="i">
                      <td>
                        {{ entry.line.transactionNumber ?? entry.line.lineId }} · {{ entry.line.action ?? '—' }}<br />
                        <button
                          v-for="code in pnrFields"
                          :key="code.key"
                          class="parsing-source"
                          @click="locate(`/lines/${entry.index}/${code.key}`)"
                        >
                          {{ code.label }}：{{ showCodes(entry.line[code.key]) }}<br />
                        </button>
                        <div>
                          操作 {{ entry.line.transactionDate ?? '—' }} / 航班 {{ entry.line.flightDate ?? '—' }}
                        </div>
                        <div>
                          <button class="parsing-source" @click="locate(`/lines/${entry.index}/flight`)">
                            航班 {{ entry.line.flight ?? '—' }}
                          </button>
                          · {{ entry.line.origin ?? '—' }} → {{ entry.line.destination ?? '—' }}
                        </div>
                      </td>
                      <td>
                        {{ entry.line.ticketNumber ?? '未提取到' }}（{{ ticketLabel(entry.line.ticketType) }}）<br />{{
                          entry.line.gds ?? '—'
                        }}
                        /
                        {{ entry.line.pcc ?? '—' }}
                      </td>
                      <td>
                        <template v-if="feeFor(entry.index)">
                          <b
                            >附件费用：{{ feeFor(entry.index)?.amount }}
                            {{ feeFor(entry.index)?.currency || '（币种未明确）' }}</b
                          ><br />
                          <button class="parsing-source" @click="locateSegment(feeFor(entry.index)?.headerSegmentId)">
                            列名：{{ feeFor(entry.index)?.label }}</button
                          ><br />
                          <button class="parsing-source" @click="locateSegment(feeFor(entry.index)?.rowSegmentId)">
                            单元格来源：{{ feeFor(entry.index)?.rowLocator }}</button
                          ><br />
                        </template>
                        <template v-else
                          >{{ amountLabel(entry.line.amountPurpose) }}<br />原始费用 {{ entry.line.amountText ?? '—'
                          }}<br />{{ entry.line.amount ?? '未提取到' }} {{ entry.line.currency }}</template
                        >
                        <template v-if="entry.line.commissionRate != null || entry.line.commissionAmount != null"
                          ><br />佣金比例 {{ entry.line.commissionRate ?? '—' }}%<br />佣金
                          {{ entry.line.commissionAmount ?? '—' }} {{ entry.line.commissionCurrency }}</template
                        >
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>
            <a-tab-pane key="json" tab="结果 JSON">
              <pre>{{ JSON.stringify(selected.candidate, null, 2) }}</pre></a-tab-pane
            ><a-tab-pane key="history" tab="解析记录"
              ><p>模型 {{ selected.model || '未调用' }} · 规则 {{ selected.promptVersion || status?.schemaVersion }}</p>
              <p v-if="selected.usage">
                输入 {{ selected.usage.prompt_tokens }} / 输出 {{ selected.usage.completion_tokens }} tokens
              </p>
              <p v-else>本次用量未知或尚未调用，不推算费用。</p>
              <details v-if="selected.originalCandidate">
                <summary>原始模型返回（未改写）</summary>
                <pre>{{ JSON.stringify(selected.originalCandidate, null, 2) }}</pre>
              </details>
              <div v-for="(check, i) in selected.revalidationHistory" :key="`check-${i}`">
                <details>
                  <summary>{{ check.at }} · 重新校验前记录（未调用模型）</summary>
                  <pre>{{ JSON.stringify(check, null, 2) }}</pre>
                </details>
              </div>
              <div v-for="(run, i) in selected.history" :key="i">
                {{ run.at }} · 第{{ run.attempt }}次 · {{ stateLabel(run.state) }}
                <details>
                  <summary>查看历史候选和校验</summary>
                  <pre>{{ JSON.stringify(run, null, 2) }}</pre>
                </details>
              </div></a-tab-pane
            ></a-tabs
          >
          <section v-if="selected.candidate && !busy" class="parsing-event">
            <h3>风控事件</h3>
            <dl>
              <dt>事件类型</dt>
              <dd>{{ eventType }}</dd>
              <dt v-if="eventDepartments">建议核对部门</dt>
              <dd v-if="eventDepartments">{{ eventDepartments }}</dd>
              <dt>下发原因</dt>
              <dd>{{ selected.candidate.adm?.reason || '未提取到' }}</dd>
              <dt>事件角色</dt>
              <dd>待按原件核对</dd>
            </dl>
            <button v-if="selected.candidate.adm?.reason" class="parsing-source" @click="locate('/adm/reason')">
              查看下发原因原文 →
            </button>
          </section>
        </div>
        <a-empty v-else description="选择来件后查看解析结果" />
      </section>
      <section class="parsing-pane parsing-original">
        <h2>原文证据</h2>
        <div class="parsing-content" v-if="selected">
          <label
            >附件<a-select
              v-model:value="fileId"
              :options="selected.files.map((f) => ({ value: f.id, label: f.name }))"
              @change="clearSource"
              style="width: 100%"
          /></label>
          <p>
            <a v-if="fileId" :href="parsingApi.fileUrl(selected.id, fileId)" target="_blank" rel="noopener"
              >查看 / 下载原件</a
            >
          </p>
          <p class="parsing-muted">此处展示实际文件读取的文字；扫描件需先OCR，XLS需先另存为XLSX。</p>
          <div class="parsing-source-status" role="status">
            {{
              sourceNotice ||
              (activeSource
                ? `${activeSource.locator} · ${sourceExcerpt ? '已高亮引用' : '已定位原文段落'}`
                : '点击“查看原文”定位引用')
            }}
          </div>
          <div class="parsing-document">
            <section v-for="s in segments" :key="s.id" :id="`segment-${s.id}`" :class="{ located: located === s.id }">
              <b>{{ s.locator }}</b>
              <span v-if="located === s.id" class="parsing-source-badge">当前引用</span>
              <p v-if="located === s.id && sourceExcerpt">
                {{ sourceExcerpt.before }}<mark>{{ sourceExcerpt.quote }}</mark
                >{{ sourceExcerpt.after }}
              </p>
              <p v-else>{{ s.text }}</p>
            </section>
            <a-empty
              v-if="!segments.length"
              :description="busy ? '正在读取或等待处理结果；请查看解析进度' : '暂无读取正文；原件仍可下载'"
            />
          </div>
        </div>
        <a-empty v-else description="选择来件后查看原件" />
      </section>
    </div>
    <FormDialog
      v-model:open="uploadOpen"
      :title="materialMode === 'append' ? '追加附件' : materialMode === 'replace' ? '替换整组材料' : '上传 ADM 解析材料'"
      :busy="uploading"
      :dirty="files.length > 0"
      :error="uploadError"
      ok-text="上传并保存"
      @submit="upload"
    >
      <a-form-item v-if="materialMode !== 'append'" label="出单来源" required>
        <a-select v-model:value="supplierCode" show-search :filter-option="false" :options="suppliers" @search="searchSuppliers" />
      </a-form-item>
      <label class="parsing-upload"
        >选择文件<input :key="inputKey" type="file" multiple accept=".pdf,.xlsx,.txt,.csv,.docx" @change="choose"
      /></label>
      <p>每件1–10份，单份20MB、合计50MB。支持PDF、XLSX、TXT、CSV、DOCX；同一ADM的材料放在同一来件。</p>
      <ul>
        <li v-for="(f, i) in files" :key="i">{{ f.name }}（{{ Math.ceil(f.size / 1024) }} KB）</li>
      </ul>
      <a-form-item v-if="materialMode !== 'append'" label="主 PDF" required>
        <a-select v-model:value="primaryIndex" :options="primaryOptions" />
      </a-form-item>
      <a-alert type="info" :message="materialMode === 'append' ? '补件核对后手动启动整组重新解析。' : '收件核对和查重通过后自动排队解析。'" />
    </FormDialog>
    <FormDialog v-model:open="reviewOpen" :title="reviewMode === 'intake' ? '核对收件' : '确认解析结果'" :busy="acting" :dirty="true"
      :error="reviewError" ok-text="确认" @submit="submitReview">
      <a-form-item v-if="reviewMode === 'intake' || !selected?.supplier" label="出单来源" required>
        <a-select v-model:value="supplierCode" show-search :filter-option="false" :options="suppliers" @search="searchSuppliers" />
      </a-form-item>
      <a-form-item v-if="reviewMode === 'intake'" label="原件 ADM 号">
        <a-input v-model:value="intakeNumber" placeholder="识别不到时，对照主 PDF 补录" />
      </a-form-item>
      <template v-else>
        <p>逐项对照原件。修改时填写对应原文段落和摘录。</p>
        <a-form-item v-for="field in reviewFields" :key="field.key" :label="field.label" required>
          <a-input v-model:value="draft[field.key].value" />
          <template v-if="draft[field.key].value !== draft[field.key].original || !draft[field.key].existingEvidence">
            <a-select v-model:value="draft[field.key].segmentId" placeholder="选择原文段落" :options="segmentOptions" />
            <a-textarea v-model:value="draft[field.key].quote" :rows="2" placeholder="填写对应原文摘录" />
          </template>
          <small v-else>{{ draft[field.key].quote }}</small>
        </a-form-item>
      </template>
      <a-checkbox v-model:checked="reviewChecked">我已对照原件核对以上内容</a-checkbox>
    </FormDialog>
    <a-drawer v-model:open="rulesOpen" title="固定 JSON 与成功失败规则" width="min(760px, 95vw)"
      ><p>必填：ADM编号、正式金额、币种，且需引用实际上传原文。未知值用null，金额为非负十进制字符串，允许0，不换汇。</p>
      <p>
        缺必填、类型错误、来源不匹配：解析失败；来源冲突、缺可选字段、币种不同、明细合计差异：解析成功但待人工核对。航司提取Airline
        Code并匹配系统航司；日期、截止日期、票号、系统、PCC按原件提取，不编造交易历史。
      </p>
      <p>
        API协议：chat-completions。服务端配置ADM_PARSING_AI_ENABLED、ADM_PARSING_AI_URL（完整HTTPS地址）、ADM_PARSING_AI_KEY、ADM_PARSING_AI_MODEL，重启服务后生效；页面不接收或展示密钥。
      </p>
      <p>
        航司PNR和GDS编码分别保留；来源未明编码不用于自动恢复。虚拟票号禁止匹配真实出票。正式金额、单位罚款、票据总额和佣金分开；只有罚单明细参与合计。报表日不能作为截止日。图片和扫描件需先转为可读正文。
      </p>
      <p>文件和记录按上传人隔离；有ADM管理权限可查看全部。单件最多10次显式解析，不自动付费重试。</p>
      <pre>{{ JSON.stringify(status?.template, null, 2) }}</pre>
    </a-drawer>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import { useAuthStore } from '@/stores/auth'
import { admApi } from '@/features/adm/api'
import { parsingApi, type ParseTask, type ParseStatus } from './api'
const router = useRouter()
const auth = useAuthStore()
const materialMode = ref<'new' | 'append' | 'replace'>('new')
const supplierCode = ref<string>()
const suppliers = ref<{ value: string; label: string }[]>([])
const primaryIndex = ref<number>()
const intakeNumber = ref('')
const reviewOpen = ref(false)
const reviewMode = ref<'intake' | 'result'>('result')
const reviewError = ref('')
const reviewChecked = ref(false)
const draft = ref<Record<string, { value: string; original: string; segmentId?: string; quote: string; existingEvidence: boolean }>>({})
const status = ref<ParseStatus>(),
  items = ref<ParseTask[]>([]),
  selected = ref<ParseTask>(),
  total = ref(0),
  page = ref(1),
  filter = ref(''),
  error = ref(''),
  notice = ref(''),
  lastChecked = ref(''),
  sourceNotice = ref(''),
  loading = ref(false),
  acting = ref(false),
  tab = ref('fields'),
  fileId = ref(''),
  located = ref(''),
  rulesOpen = ref(false),
  uploadOpen = ref(false),
  uploading = ref(false),
  uploadError = ref(''),
  files = ref<File[]>([]),
  inputKey = ref(0)
const labels: Record<string, string> = {
  UPLOADED: '已上传',
  QUEUED: '排队中',
  RUNNING: '解析中',
  SUCCEEDED: '解析成功',
  FAILED: '解析失败',
}
const stateOptions = [
  { value: '', label: '全部' },
  ...Object.entries(labels).map(([value, label]) => ({ value, label })),
]
const stateLabel = (s: string) => labels[s] || s
const stateColor = (s: string) =>
  s === 'SUCCEEDED'
    ? 'success'
    : s === 'FAILED'
      ? 'error'
      : ['QUEUED', 'RUNNING'].includes(s)
        ? 'processing'
        : 'default'
const fields = [
  { key: 'number', label: 'ADM编号', required: true },
  { key: 'airlineCode', label: 'Airline Code' },
  { key: 'issuedDate', label: '开具日期' },
  { key: 'amount', label: '正式金额', required: true },
  { key: 'currency', label: '币种', required: true },
  { key: 'reportingDate', label: '报表日期' },
  { key: 'dueDate', label: '截止日期' },
  { key: 'reason', label: '下发原因' },
]
const reviewFields = fields.slice(0, 5)
const primaryOptions = computed(() => files.value.flatMap((file, index) => /\.pdf$/i.test(file.name) ? [{ value: index, label: file.name }] : []))
const segmentOptions = computed(() => (selected.value?.segments || []).map((segment) => ({
  value: segment.id,
  label: `${selected.value?.files.find((file) => file.id === segment.fileId)?.name || ''} · ${segment.locator}`,
})))
let supplierSearchVersion = 0
async function searchSuppliers(search = '') {
  const version = ++supplierSearchVersion
  try {
    const rows = await admApi.options('supplier', search, 50)
    if (version !== supplierSearchVersion) return
    const options = rows.map((row) => ({ value: String(row.code), label: row.name }))
    const current = selected.value?.supplier
    if (current && supplierCode.value === current.code && !options.some((option) => option.value === current.code)) {
      options.unshift({ value: current.code, label: current.name })
    }
    suppliers.value = options
  } catch (e) {
    if (version === supplierSearchVersion) {
      if (reviewOpen.value) reviewError.value = message(e)
      else uploadError.value = message(e)
    }
  }
}
const optionalLists = [
  { key: 'noticeTypes', label: '罚单类型' },
  { key: 'attachmentReferences', label: '原文附件清单' },
] as const
const pnrFields = [
  { key: 'airlinePnrs', label: '航司PNR' },
  { key: 'gdsPnrs', label: 'GDS编码' },
  { key: 'pnrs', label: '来源未明PNR' },
]
const feeFor = (index: number) => selected.value?.attachmentFees?.find((fee) => fee.lineIndex === index)
const showCodes = (value: unknown) => (Array.isArray(value) ? value.join(' / ') || '未提取到' : '未提取到')
const ticketLabel = (value: unknown) =>
  ({ real: '真实票号', virtual: '虚拟票号，禁止匹配出票', unknown: '类型待核对' })[String(value)] || '类型待核对'
const amountLabel = (value: unknown) =>
  ({
    admCharge: '罚单明细',
    unitPenalty: '单位罚款',
    ticketTotal: '票据总额',
    other: '其他金额',
    unknown: '用途待核对',
  })[String(value)] || '用途待核对'
const errorIssues = computed(() => selected.value?.issues?.filter((item) => item.level === 'error') || [])
const warningIssues = computed(() => selected.value?.issues?.filter((item) => item.level === 'warning') || [])
const reviewIssues = computed(() => [...errorIssues.value, ...warningIssues.value])
const issueTabLabel = computed(() =>
  errorIssues.value.length
    ? '待处理 ' + errorIssues.value.length
    : warningIssues.value.length
      ? '待核对 ' + warningIssues.value.length
      : '校验结果',
)
const eventMatches = computed(() => selected.value?.classification?.matches || [])
const eventType = computed(() => {
  const reasons = [...new Set(eventMatches.value.map((match) => match.reason))]
  return reasons.length ? reasons.join(' / ') + ' · 建议，待业务确认' : '待归类'
})
const eventDepartments = computed(() => [...new Set(eventMatches.value.map((match) => match.department))].join(' / '))
const sourceExcerpt = ref<{ before: string; quote: string; after: string }>()
const activeSource = computed(() => segments.value.find((segment) => segment.id === located.value))
const issueTarget = (issue: { path: string }) => {
  const index = /^\/evidence\/(\d+)$/.exec(issue.path)
  return index ? selected.value?.candidate?.evidence?.[Number(index[1])]?.path || issue.path : issue.path
}
const issueValue = (issue: { path: string }) => {
  const key = /^\/adm\/([^/]+)$/.exec(issueTarget(issue))?.[1]
  return key ? selected.value?.candidate?.adm?.[key] : undefined
}
const issueLabel = (issue: { path: string }) => {
  const path = issueTarget(issue)
  const name = fields.find((item) => `/adm/${item.key}` === path)?.label
  if (path === '/lines') return '明细／附件费用'
  const row = /^\/lines\/(\d+)$/.exec(path)
  if (row) return `明细${Number(row[1]) + 1}`
  const line = /^\/lines(?:\/|\[)(\d+)\]?\/(.+)$/.exec(path)
  return (
    name ||
    (line
      ? `明细${Number(line[1]) + 1} · ${pnrFields.find((item) => item.key === line[2])?.label || { currency: '币种', amount: '金额', amountText: '原始费用', gds: 'GDS系统', pcc: 'PCC', action: '动作', flight: '航班', flightDate: '航班日期', transactionDate: '操作日期', ticketNumber: '票号' }[line[2]] || line[2]}`
      : '来源引用')
  )
}
const airlineStatus = (status?: string) =>
  ({
    NOT_PROVIDED: '未提取到Airline Code',
    NOT_FOUND: '编码未匹配到系统航司',
    AMBIGUOUS: '系统资料多个匹配，待核对',
    UNAVAILABLE: '系统航司资料暂不可用，请重新校验',
    SOURCE_INVALID: '编码来源校验未通过',
  })[status || ''] || '尚未按新口径匹配，请重新校验'
const busy = computed(
  () => ['QUEUED', 'RUNNING'].includes(selected.value?.state || '') && selected.value?.saveStatus !== 'FAILED',
)
const progressText = computed(() => {
  const task = selected.value
  if (!task) return ''
  if (task.saveStatus === 'FAILED') return '模型处理已结束，结果待重试保存'
  if (task.state === 'SUCCEEDED') return '解析和结果保存完成，请核对字段'
  if (task.state === 'FAILED') return '处理失败，失败原因已保存'
  return (
    {
      UPLOADED: '原件已保存，等待开始解析',
      QUEUED: '已排队，等待处理',
      READING: '正在校验原件并读取正文',
      MODEL: '正文已保存，正在等待模型响应',
      VALIDATING: '模型已返回，正在校验字段并准备保存',
    }[task.stage || task.state] || '后台处理中'
  )
})
const segments = computed(() => selected.value?.segments?.filter((s) => s.fileId === fileId.value) || [])
const displayLines = computed(() => {
  const lines = selected.value?.candidate?.lines
  return Array.isArray(lines)
    ? lines
        .map((line, index) => ({ line, index }))
        .filter((entry) => !!entry.line && typeof entry.line === 'object' && !Array.isArray(entry.line))
    : []
})
const formatTime = formatDateTimeDisplay
let stopped = false,
  listGeneration = 0,
  generation = 0,
  timer: ReturnType<typeof setTimeout> | undefined,
  requestKey = ''
const message = (e: unknown) => (e instanceof Error ? e.message : '操作失败，请刷新状态后重试')
async function loadList() {
  const token = ++listGeneration
  loading.value = true
  try {
    const result = await parsingApi.list(page.value, filter.value)
    if (!stopped && token === listGeneration) {
      items.value = result.items
      total.value = result.total
    }
  } catch (e) {
    if (token === listGeneration) error.value = message(e)
  } finally {
    if (token === listGeneration) loading.value = false
  }
}
async function changeFilter() {
  page.value = 1
  await loadList()
}
async function deleteIntake() {
  const task = selected.value
  if (!task?.canDelete || acting.value) return
  acting.value = true
  error.value = ''
  notice.value = ''
  try {
    await parsingApi.delete(task)
    if (selected.value?.id === task.id) {
      generation++
      selected.value = undefined
      clearSource()
    }
    notice.value = '来件已删除'
    if (route.query.task === task.id) {
      const query = { ...route.query }
      delete query.task
      await router.replace({ query })
    }
    await loadList()
    const lastPage = Math.max(1, Math.ceil(total.value / 20))
    if (page.value > lastPage) {
      page.value = lastPage
      await loadList()
    }
  } catch (e) {
    error.value = message(e)
  } finally {
    acting.value = false
  }
}
function schedule() {
  if (timer) clearTimeout(timer)
  if (!stopped && busy.value)
    timer = setTimeout(async () => {
      if (!document.hidden && selected.value) await select(selected.value.id, false)
      else schedule()
    }, 3000)
}
async function select(id: string, reset = true) {
  const token = ++generation
  if (reset) {
    selected.value = undefined
    if (timer) clearTimeout(timer)
  }
  try {
    const task = await parsingApi.detail(id)
    if (stopped || token !== generation) return
    selected.value = task
    lastChecked.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    if (reset || !task.files.some((f) => f.id === fileId.value)) {
      fileId.value = task.files[0]?.id || ''
      clearSource()
      tab.value = task.issues?.length ? 'issues' : 'fields'
    }
    items.value = items.value.map((item) => (item.id === id ? task : item))
    schedule()
  } catch (e) {
    if (token === generation) {
      error.value = message(e)
      if (timer) clearTimeout(timer)
    }
  }
}
const route = useRoute()
async function refresh() {
  error.value = ''
  try {
    status.value = await parsingApi.status()
    await loadList()
    if (selected.value) await select(selected.value.id, false)
    else if (typeof route.query.task === 'string') await select(route.query.task)
    else if (items.value[0]) await select(items.value[0].id)
  } catch (e) {
    error.value = message(e)
  }
}
function openUpload(mode: 'new' | 'append' | 'replace' = 'new') {
  materialMode.value = mode
  supplierCode.value = mode === 'new' ? undefined : selected.value?.supplier?.code
  primaryIndex.value = undefined
  files.value = []
  uploadError.value = ''
  inputKey.value++
  requestKey = `admparse_${Date.now()}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`
  uploadOpen.value = true
  if (mode !== 'append') void searchSuppliers()
}
function choose(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files || [])
  primaryIndex.value = primaryOptions.value.length === 1 ? primaryOptions.value[0].value : undefined
}
async function upload() {
  if (uploading.value) return
  if (materialMode.value !== 'append' && (!supplierCode.value || primaryIndex.value === undefined)) {
    uploadError.value = '请选择出单来源和主 PDF'
    return
  }
  if (
    !files.value.length ||
    files.value.length > 10 ||
    files.value.some((f) => !f.size || f.size > 20 * 1024 * 1024 || !/\.(pdf|xlsx|txt|csv|docx)$/i.test(f.name)) ||
    files.value.reduce((sum, f) => sum + f.size, 0) > 50 * 1024 * 1024
  ) {
    uploadError.value = '请选择1–10份支持格式的非空文件，单份20MB、合计50MB以内'
    return
  }
  uploading.value = true
  uploadError.value = ''
  try {
    const task = await parsingApi.upload(files.value, requestKey, supplierCode.value || '', primaryIndex.value ?? -1,
      materialMode.value === 'new' ? undefined : selected.value, materialMode.value === 'replace')
    uploadOpen.value = false
    notice.value = task.alreadyReceived ? '已收件，已打开原来件。' : '材料已保存，请查看来件状态。'
    filter.value = ''
    page.value = 1
    await loadList()
    await select(task.id)
  } catch (e) {
    uploadError.value = message(e)
  } finally {
    uploading.value = false
  }
}
function openReview(mode: 'intake' | 'result') {
  const task = selected.value
  if (!task) return
  reviewMode.value = mode
  reviewError.value = ''
  reviewChecked.value = false
  supplierCode.value = task.supplier?.code
  intakeNumber.value = task.intakeNumber || ''
  draft.value = Object.fromEntries(reviewFields.map((field) => {
    const value = String(task.candidate?.adm?.[field.key] || '')
    const path = `/adm/${field.key}`
    const cite = task.candidate?.evidence.find((item) => item.path === path)
    return [field.key, { value, original: value, segmentId: cite?.segmentId, quote: cite?.quote || '',
      existingEvidence: Boolean(cite) && !task.issues?.some((issue) => issue.level === 'error' && issue.path === path) }]
  }))
  reviewOpen.value = true
  if (mode === 'intake' || !task.supplier) void searchSuppliers()
}
async function submitReview() {
  const task = selected.value
  if (!task || acting.value) return
  if (!reviewChecked.value) {
    reviewError.value = '请先对照原件核对并勾选确认'
    return
  }
  acting.value = true
  reviewError.value = ''
  try {
    if (reviewMode.value === 'intake') {
      await parsingApi.resolve(task, supplierCode.value || '', intakeNumber.value.trim())
    } else {
      const edits = Object.fromEntries(Object.entries(draft.value)
        .filter(([, field]) => field.value !== field.original || !field.existingEvidence)
        .map(([key, field]) => [key, { value: field.value, segmentId: field.segmentId || '', quote: field.quote }]))
      await parsingApi.confirm(task, supplierCode.value || '', edits)
    }
    reviewOpen.value = false
    await loadList()
    await select(task.id, false)
  } catch (e) {
    reviewError.value = message(e)
  } finally {
    acting.value = false
  }
}
async function startParse() {
  if (!selected.value || acting.value || busy.value) return
  acting.value = true
  error.value = ''
  const task = selected.value,
    token = generation
  try {
    const result = await parsingApi.parse(task)
    if (stopped || token !== generation) return
    selected.value = result
    notice.value = '解析请求已提交，当前阶段见下方进度。'
    schedule()
  } catch (e) {
    error.value = message(e)
    if (token === generation && selected.value) await select(selected.value.id, false)
  } finally {
    acting.value = false
  }
}
async function revalidate() {
  if (!selected.value || acting.value || busy.value) return
  acting.value = true
  error.value = ''
  const task = selected.value,
    token = generation
  try {
    const result = await parsingApi.revalidate(task)
    if (stopped || token !== generation) return
    selected.value = result
    tab.value = result.issues?.length ? 'issues' : 'fields'
    await loadList()
  } catch (e) {
    if (token === generation) error.value = message(e)
  } finally {
    acting.value = false
  }
}
async function retrySave() {
  if (!selected.value || acting.value) return
  acting.value = true
  const task = selected.value,
    token = generation
  try {
    const result = await parsingApi.retrySave(task)
    if (stopped || token !== generation) return
    selected.value = result
    notice.value = '保存状态已核对，未重新调用模型。'
    await loadList()
  } catch (e) {
    error.value = message(e)
  } finally {
    acting.value = false
  }
}
async function locate(path: string) {
  const evidence = selected.value?.candidate?.evidence
  const e = evidence?.find((e) => e.path === path) || evidence?.find((e) => e.path.startsWith(`${path}/`))
  await locateSegment(e?.segmentId, e?.quote)
}
function clearSource() {
  located.value = ''
  sourceExcerpt.value = undefined
  sourceNotice.value = ''
}
async function locateSegment(segmentId?: string, quote?: string) {
  const segment = selected.value?.segments?.find((s) => s.id === segmentId)
  if (!segment) {
    clearSource()
    sourceNotice.value = '该字段暂无可定位的原文引用。'
    await nextTick()
    document.querySelector('.parsing-source-status')?.scrollIntoView({ block: 'nearest' })
    return
  }
  const words = quote?.trim().split(/\s+/).filter(Boolean) || []
  const pattern = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+')
  const match = pattern ? new RegExp(pattern).exec(segment.text) : null
  sourceExcerpt.value = match
    ? {
        before: segment.text.slice(0, match.index),
        quote: match[0],
        after: segment.text.slice(match.index + match[0].length),
      }
    : undefined
  sourceNotice.value = pattern && !match ? '已定位原文段落，引用文字未能逐字匹配。' : ''
  fileId.value = segment.fileId
  located.value = segment.id
  await nextTick()
  const source = document.getElementById(`segment-${segment.id}`)
  const highlight = source?.querySelector('mark') || source
  highlight?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
}

onMounted(refresh)
onBeforeUnmount(() => {
  stopped = true
  generation++
  if (timer) clearTimeout(timer)
})
</script>
<style scoped>
.parsing-page {
  min-width: 0;
}
.parsing-page > .ant-alert {
  margin-bottom: 16px;
}
.parsing-filter {
  padding: 12px;
}
.parsing-filter :deep(.ant-select) {
  width: 100%;
}
.parsing-workspace > aside {
  grid-area: inbox;
}
.parsing-summary {
  grid-area: summary;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 16px;
}
.parsing-summary h2 {
  padding: 0;
  border: 0;
  overflow-wrap: anywhere;
}
.parsing-summary .parsing-tags,
.parsing-summary .parsing-actions {
  margin-bottom: 0;
}
.parsing-amount {
  margin: 6px 0;
}
.parsing-workspace {
  --panel-height: clamp(450px, calc(100dvh - 340px), 820px);
  display: grid;
  grid-template-columns: 190px minmax(0, 1.55fr) minmax(0, 1fr);
  grid-template-areas: 'inbox result original';
  grid-template-rows: var(--panel-height);
  gap: 16px;
}
.parsing-workspace.has-summary {
  grid-template-areas: 'summary summary summary' 'inbox result original';
  grid-template-rows: auto var(--panel-height);
}
.parsing-result {
  grid-area: result;
}
.parsing-original {
  grid-area: original;
}
.parsing-pane {
  min-width: 0;
  min-height: 0;
  background: white;
  border: 1px solid #dce3ec;
  border-radius: 6px;
}
.parsing-pane h2 {
  font-size: 16px;
  padding: 16px;
  border-bottom: 1px solid #e8edf3;
  margin: 0;
}
.parsing-content {
  padding: 16px;
}
.parsing-workspace > aside,
.parsing-result,
.parsing-original {
  display: flex;
  flex-direction: column;
}
.parsing-workspace > aside :deep(.ant-spin-nested-loading),
.parsing-result > .parsing-content {
  flex: 1 1 0;
  min-height: 0;
  overflow: auto;
}
.parsing-original > .parsing-content {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1 1 0;
  overflow: auto;
}
.parsing-item {
  display: grid;
  gap: 7px;
  width: 100%;
  text-align: left;
  padding: 16px;
  background: white;
  border: 0;
  border-bottom: 1px solid #e8edf3;
  cursor: pointer;
  color: var(--platform-text, #203447);
  overflow-wrap: anywhere;
}
.parsing-item[aria-pressed='true'] {
  background: var(--platform-selected, #eaf3fc);
  box-shadow: inset 3px 0 var(--platform-primary, #2673ad);
}
.parsing-item span,
.parsing-muted {
  font-size: 12px;
  color: #58677b;
}
.parsing-field {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) 30px;
  gap: 8px;
  width: 100%;
  border: 0;
  border-bottom: 1px solid #e8edf3;
  padding: 10px 0;
  text-align: left;
  background: white;
  cursor: pointer;
}
.parsing-field-error {
  border-left: 3px solid #cf1322;
  padding-left: 8px;
}
.parsing-field:disabled {
  cursor: default;
  color: #58677b;
}
.parsing-field b {
  overflow-wrap: anywhere;
}
.parsing-field small,
.parsing-source {
  color: #1667ce;
}
.parsing-document {
  flex: 1 1 auto;
  min-height: 120px;
  overflow: auto;
  background: var(--platform-hover, #f0f6fc);
  border: 1px solid #e1e6ed;
  padding: 12px;
}
.parsing-document section {
  border-left: 3px solid transparent;
  padding: 8px;
}
.parsing-document .located {
  border-color: #d49400;
  background: #fff3cd;
}
.parsing-document p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.parsing-tags,
.parsing-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 8px 0 16px;
}
.parsing-table {
  overflow: auto;
}
.parsing-table table {
  width: 100%;
  min-width: 440px;
  border-collapse: collapse;
}
.parsing-table td,
.parsing-table th {
  padding: 8px;
  border-bottom: 1px solid #e8edf3;
  text-align: left;
}
.parsing-table td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.parsing-source {
  border: 0;
  background: none;
  cursor: pointer;
  text-align: left;
}
.parsing-issue {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #e1e6ed;
  border-radius: 6px;
  background: var(--platform-hover, #f0f6fc);
}
.parsing-issue-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.parsing-issue-header .parsing-source {
  margin-left: auto;
}
.parsing-issue-value {
  overflow-wrap: anywhere;
}
.parsing-issue p {
  margin: 8px 0 4px;
  overflow-wrap: anywhere;
}
.parsing-issue small {
  overflow-wrap: anywhere;
  color: #58677b;
}
.parsing-event {
  margin-top: 20px;
  border-top: 1px solid #e1e6ed;
}
.parsing-event dl {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px 16px;
}
.parsing-event dt {
  color: #58677b;
}
.parsing-event dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.parsing-document mark {
  background: #ffdc74;
  color: #523000;
  font-weight: 700;
  border-bottom: 2px solid #a86300;
}
.parsing-source-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 6px;
  border-radius: 4px;
  color: #523000;
  background: #ffdc74;
  font-size: 12px;
}
.parsing-source-status {
  margin-bottom: 8px;
  color: #58677b;
}
.parsing-progress {
  padding: 12px;
  border: 1px solid #dce3ec;
  margin-bottom: 16px;
}
.parsing-progress p {
  margin: 8px 0 0;
  overflow-wrap: anywhere;
}
.parsing-extra-actions {
  margin-left: auto;
  font-size: 12px;
}
.parsing-airline {
  display: grid;
  gap: 8px;
  padding: 12px 0;
  border-bottom: 1px solid #e8edf3;
}
.parsing-feedback {
  padding: 12px;
  background: var(--platform-selected, #eaf3fc);
  color: #1656a0;
}
.parsing-upload {
  display: grid;
  gap: 8px;
  margin: 16px 0;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 550px;
  overflow: auto;
}
button:focus-visible {
  outline: 2px solid var(--platform-primary, #2673ad);
  outline-offset: 2px;
}
h3 {
  font-size: 14px;
  margin-top: 16px;
}
.parsing-pane > .ant-pagination {
  padding: 12px;
}
@media (max-width: 1050px) {
  .parsing-workspace,
  .parsing-workspace.has-summary {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto;
    grid-template-areas: 'inbox' 'result' 'original';
  }
  .parsing-workspace.has-summary {
    grid-template-areas: 'summary' 'inbox' 'result' 'original';
  }
  .parsing-workspace > aside :deep(.ant-spin-nested-loading),
  .parsing-result > .parsing-content,
  .parsing-original > .parsing-content {
    flex: 0 1 auto;
  }
  .parsing-workspace > aside :deep(.ant-spin-nested-loading),
  .parsing-document {
    max-height: 360px;
  }
}
</style>
