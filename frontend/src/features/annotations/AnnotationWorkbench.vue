<template>
  <div class="page-wrap annotation">
    <PageHeader
      eyebrow="数据标注"
      title="标注工作台"
      description="选择原文打标，核对完整性后提交复核，再发布为固定版本的样本集。"
    >
      <a-button :disabled="busy" @click="loadProjects">刷新</a-button>
      <a-button v-if="canCreate" type="primary" @click="openDialog('create')">新建项目</a-button>
    </PageHeader>
    <a-alert v-if="error" type="error" show-icon closable :message="error" @close="error = ''" />
    <a-alert v-if="notice" type="success" show-icon closable :message="notice" @close="notice = ''" />
    <a-spin :spinning="loading">
      <a-empty v-if="!project && !loading" description="暂无可访问的标注项目" />
      <template v-if="project">
        <section class="panel project-bar">
          <div class="toolbar">
            <label class="project-select">
              标注项目
              <a-select
                aria-label="标注项目"
                :disabled="busy"
                :value="project.id"
                :options="projects.map((item) => ({ value: item.id, label: item.name }))"
                @change="switchProject"
              />
            </label>
            <a-tag>{{ roleNames[project.role] }}</a-tag>
            <a-tag v-if="project.kind === 'adm'" color="blue">ADM</a-tag>
          </div>
          <div class="toolbar">
            <a-button @click="showSummary">项目汇总</a-button>
            <a-button v-if="project.role === 'manager'" @click="openDialog('manage')">标签与项目成员</a-button>
            <a-button v-if="project.role !== 'annotator'" @click="showDatasets">样本集版本</a-button>
            <a-button
              v-if="project.kind === 'adm' && project.role === 'manager' && hasAdm"
              @click="openDialog('import')"
              >引用 ADM 来件</a-button
            >
            <a-button v-if="mayUpload" type="primary" @click="openDialog('upload')">添加文件</a-button>
          </div>
        </section>
        <div class="workspace">
          <aside class="panel queue">
            <h2>
              样本队列 <small>{{ total }} 份</small>
            </h2>
            <div class="queue-tools">
              <a-input-search
                v-model:value="keyword"
                maxlength="100"
                aria-label="搜索样本"
                placeholder="文件名、标题、来源"
                @search="applySearch"
              />
              <a-select
                aria-label="样本状态"
                :value="statusFilter"
                :options="statusOptions"
                class="full-width"
                @change="filterStatus"
              />
            </div>
            <div class="queue-list">
              <a-spin :spinning="queueLoading">
                <a-empty v-if="!items.length" description="当前条件没有样本" />
                <div v-for="item in items" :key="item.id" class="queue-row">
                  <button
                    type="button"
                    class="queue-item"
                    :disabled="busy"
                    :aria-pressed="current?.id === item.id"
                    @click="selectSample(item.id)"
                  >
                    <strong>{{ item.title || item.name }}</strong>
                    <small>{{ statusNames[item.status] }} · 已标 {{ item.positionCount }} 处</small>
                  </button>
                  <a-button
                    v-if="item.canDelete"
                    size="small"
                    type="text"
                    danger
                    :disabled="busy || detailLoading || queueLoading"
                    :aria-label="'删除样本 ' + (item.title || item.name)"
                    @click="confirmDelete(item)"
                  >
                    删除
                  </a-button>
                </div>
              </a-spin>
            </div>
            <a-pagination
              v-if="total > pageSize"
              size="small"
              :current="page"
              :total="total"
              :page-size="pageSize"
              :show-size-changer="false"
              @change="changePage"
            />
          </aside>
          <section class="panel original">
            <h2>
              原文证据 <small v-if="current">{{ current.files.length }} 份附件</small>
            </h2>
            <a-spin v-if="detailLoading" :spinning="true" class="detail-spinner" />
            <EvidenceViewer
              v-else-if="current && draft"
              :key="current.id"
              :sample-id="current.id"
              :files="current.files"
              :segments="current.segments"
              :marks="evidenceMarks"
              :active="highlight"
              :editable="editable && !busy"
              @selected="openSelection"
              @clear-selection="clearSelection"
            />
            <a-empty v-else description="选择样本以查看原件" />
          </section>
          <section class="panel detail">
            <h2>
              标注结果
              <a-tag v-if="current" :color="statusColors[current.status]">{{ statusNames[current.status] }}</a-tag>
            </h2>
            <div v-if="current && draft" class="detail-scroll">
              <a-alert v-if="current.reviewNote" type="warning" show-icon :message="current.reviewNote" />
              <a-alert v-if="editable && current.labelReviewNeeded" type="warning" show-icon
                message="项目标签定义已更新。请核对原文标注，再保存草稿。" />
              <a-alert
                v-if="editable && !fieldLabels.length"
                type="info"
                show-icon
                message="本项目尚无字段标签，请联系项目管理员配置。"
              />
              <div class="metadata">
                <label
                  >来源平台 <a-input v-model:value="draft.platform" maxlength="100" :disabled="!editable || busy"
                /></label>
                <label
                  >文件标题
                  <a-input
                    v-model:value="draft.title"
                    maxlength="200"
                    :disabled="!editable || busy"
                    @change="discardTitleEvidence"
                /></label>
                <a-button v-if="draft.titleEvidence" size="small" type="link" @click="focus(draft.titleEvidence)">
                  查看标题证据
                </a-button>
              </div>
              <section v-if="documentLabels.length" class="detail-section">
                <h3>整份文件标签</h3>
                <div class="tag-list">
                  <a-button
                    v-for="label in documentLabels"
                    :key="label.id"
                    size="small"
                    :type="draft.fileLabels.includes(label.id) ? 'primary' : 'default'"
                    :disabled="!editable || busy"
                    :aria-pressed="draft.fileLabels.includes(label.id)"
                    :title="label.description"
                    @click="toggleLabel(label.id)"
                    >{{ label.name }}</a-button
                  >
                </div>
              </section>
              <section class="detail-section">
                <h3>
                  字段证据 <small>已标 {{ positionCount }} 处</small>
                </h3>
                <div class="tag-list">
                  <a-tag v-for="row in labelCounts" :key="row.id">{{ row.name }} {{ row.count }}</a-tag>
                </div>
                <p v-if="!draft.marks.length" class="muted">选中原文后打标签，数字键 1–9 可快速应用。</p>
                <article v-for="(mark, index) in draft.marks" :key="mark.id ?? index" class="mark-row">
                  <a-button type="link" class="mark-link" @click="focus(mark)">
                    <span
                      class="label-color"
                      :style="{ backgroundColor: labelColor(mark.labelId) }"
                      aria-hidden="true"
                    />
                    {{ labelName(mark.labelId) }} · {{ evidenceLocation(mark) }}
                  </a-button>
                  <p>{{ mark.quote }}</p>
                  <div v-if="editable && !busy" class="toolbar">
                    <a-select
                      size="small"
                      :value="mark.labelId"
                      :options="fieldLabels.map((label) => ({ value: label.id, label: label.name }))"
                      aria-label="更换字段标签"
                      class="mark-label"
                      @change="(value: string) => changeMarkLabel(index, value)"
                    />
                    <a-button type="text" size="small" @click="removeMark(index)">移除</a-button>
                  </div>
                </article>
              </section>
              <details v-if="current.history.length" class="detail-section">
                <summary>操作记录</summary>
                <ul class="history">
                  <li v-for="(entry, index) in current.history" :key="index">
                    {{ actionNames[entry.action] ?? entry.action }} · {{ entry.actor }} · {{ displayDate(entry.at) }}
                    <p v-if="entry.note">{{ entry.note }}</p>
                  </li>
                </ul>
              </details>
            </div>
            <a-empty v-else-if="!detailLoading" description="选择样本以查看标注" />
            <footer v-if="current" class="detail-actions">
              <a-button v-if="current.canAssign" :disabled="busy" @click="openDialog('assign')">分配</a-button>
              <a-button
                v-if="current.canReopen"
                :disabled="busy || detailLoading"
                @click="confirmReopen"
              >
                重新编辑
              </a-button>
              <template v-if="editable">
                <a-button :disabled="(!dirty && !current.labelReviewNeeded) || busy" @click="saveDraft">保存草稿</a-button>
                <a-button type="primary" :loading="busy" @click="submitDraft">提交并处理下一份</a-button>
              </template>
              <template v-if="current.canReview">
                <a-button :disabled="busy" @click="openDialog('return')">退回补充</a-button>
                <a-button type="primary" :loading="busy" @click="runAction('approve')">复核通过</a-button>
              </template>
            </footer>
          </section>
        </div>
      </template>
    </a-spin>

    <div
      v-if="selection && editable"
      class="selection-menu"
      :style="{ left: menuPosition.x + 'px', top: menuPosition.y + 'px' }"
      role="group"
      aria-label="选区标签"
    >
      <div class="selection-title">{{ selection.quote }}</div>
      <button type="button" @click="applyTitle">设为文件标题</button>
      <button
        v-for="(label, i) in fieldLabels"
        :key="label.id"
        type="button"
        :title="label.description"
        @click="applyField(label.id)"
      >
        {{ label.name }} <kbd v-if="i < 9">{{ i + 1 }}</kbd>
      </button>
      <button type="button" @click="clearSelection">取消</button>
    </div>

    <FormDialog
      :open="dialog !== null"
      :title="dialogTitle"
      :busy="dialogBusy"
      :error="dialogError"
      :submit-disabled="dialog === 'upload' && !pendingFiles.length"
      :ok-text="
        dialog === 'publish' ? '发布版本' : dialog === 'create' ? '创建' : dialog === 'upload' ? '上传' : '确认'
      "
      @cancel="closeDialog"
      @submit="submitDialog"
    >
      <div v-if="dialog === 'create'" class="dialog-fields">
        <label>项目名称 <a-input v-model:value="projectName" placeholder="例如 ADM 风控事件" maxlength="100" /></label>
        <label>
          项目类型
          <a-select
            v-model:value="projectKind"
            :options="[
              { value: 'general', label: '通用' },
              { value: 'adm', label: 'ADM' },
            ]"
          />
        </label>
      </div>
      <div v-else-if="dialog === 'manage'" class="dialog-fields">
        <h3>标签定义</h3>
        <div v-for="(label, i) in pendingLabels" :key="label.id ?? i" class="label-definition">
          <a-select v-model:value="label.scope" :disabled="!!label.id" aria-label="标签范围" :options="labelScopes" />
          <a-input v-model:value="label.name" aria-label="标签名称" placeholder="名称" maxlength="50" />
          <a-input
            v-model:value="label.description"
            aria-label="标签定义"
            placeholder="定义或取值说明"
            maxlength="300"
          />
          <a-button v-if="!label.id" @click="pendingLabels.splice(i, 1)">移除</a-button>
        </div>
        <a-button @click="pendingLabels.push({ scope: 'field', name: '', description: '' })">新增标签</a-button>
        <h3>项目成员</h3>
        <div v-for="(member, i) in pendingMembers" :key="member.id" class="toolbar">
          <span>{{ member.name }}</span>
          <a-select v-model:value="member.role" aria-label="成员角色" :options="memberRoles" />
          <a-button size="small" @click="pendingMembers.splice(i, 1)">移除</a-button>
        </div>
        <a-select
          :value="null"
          :options="availableAccounts"
          aria-label="添加成员"
          placeholder="选择中台账号添加"
          show-search
          option-filter-prop="label"
          class="full-width"
          @change="addMember"
        />
      </div>
      <div v-else-if="dialog === 'upload'" class="dialog-fields">
        <label>
          选择文件
          <input type="file" multiple accept=".pdf,.xlsx,.txt,.csv,.docx" @change="pickFiles" />
        </label>
        <a-checkbox v-model:checked="groupUpload">作为同一个样本的多份附件</a-checkbox>
        <p v-if="pendingFiles.length">已选 {{ pendingFiles.length }} 份文件</p>
        <p class="muted">支持 PDF、XLSX、TXT、CSV、DOCX。扫描件需先做 OCR。</p>
      </div>
      <div v-else-if="dialog === 'import'" class="dialog-fields">
        <label>
          ADM 解析来件
          <a-select
            v-model:value="admTaskId"
            :options="admOptions"
            show-search
            allow-clear
            option-filter-prop="label"
            aria-label="ADM 解析来件"
            placeholder="从有权访问的近期来件选择"
          />
        </label>
        <label>也可填写来件 ID 或链接 <a-input v-model:value="admTaskId" maxlength="500" /></label>
      </div>
      <div v-else-if="dialog === 'assign'" class="dialog-fields">
        <label>标注人员 <a-select v-model:value="assignee" :options="assigneeOptions" aria-label="标注人员" /></label>
      </div>
      <div v-else-if="dialog === 'return'" class="dialog-fields">
        <label>退回原因 <a-textarea v-model:value="reviewNote" maxlength="500" :rows="3" /></label>
      </div>
      <div v-else-if="dialog === 'publish'" class="dialog-fields">
        <label>样本集名称 <a-input v-model:value="datasetName" maxlength="80" /></label>
        <p class="muted">只允许选择已通过复核的样本。发布后保留当前版本快照。</p>
        <a-spin :spinning="publishLoading">
          <a-checkbox-group v-model:value="publishIds" class="publish-list">
            <a-checkbox v-for="item in publishCandidates" :key="item.id" :value="item.id">
              {{ item.title || item.name }}
            </a-checkbox>
          </a-checkbox-group>
          <a-button
            v-if="publishPage * pageSize < publishTotal"
            :disabled="publishLoading"
            @click="loadPublishPage(publishPage + 1)"
          >
            加载更多
          </a-button>
          <a-empty v-if="!publishCandidates.length && !publishLoading" description="没有可发布的已确认样本" />
        </a-spin>
      </div>
    </FormDialog>

    <a-modal v-model:open="summaryOpen" title="项目样本汇总" :footer="null" :width="780">
      <p class="muted">以下数量以当前账号可访问的项目样本为准。</p>
      <div class="summary-status">
        <button
          v-for="(value, key) in counts"
          :key="key"
          type="button"
          @click="filterFromSummary(key)"
        >
          <strong>{{ value }}</strong> {{ statusNames[key] }}
        </button>
      </div>
      <div class="toolbar">
        <a-select
          v-model:value="summaryStatus"
          :options="statusOptions"
          aria-label="汇总样本状态"
          @change="loadSummary(1)"
        />
      </div>
      <a-spin :spinning="summaryLoading">
        <table class="summary-table">
          <thead>
            <tr>
              <th>标题 / 原件</th>
              <th>来源</th>
              <th>位置</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in summaryItems" :key="item.id">
              <td>
                {{ item.title || item.name
                }}<small v-if="item.title && item.title !== item.name">{{ item.name }}</small>
              </td>
              <td>{{ item.platform || '待填写' }}</td>
              <td>{{ item.positionCount }}/{{ item.expected ?? '未设置' }}</td>
              <td>{{ statusNames[item.status] }}</td>
              <td><a-button size="small" @click="openFromSummary(item.id)">查看原件</a-button></td>
            </tr>
          </tbody>
        </table>
        <a-empty v-if="!summaryItems.length" description="当前条件没有样本" />
      </a-spin>
      <a-pagination
        v-if="summaryTotal > pageSize"
        size="small"
        :current="summaryPage"
        :total="summaryTotal"
        :page-size="pageSize"
        :show-size-changer="false"
        @change="loadSummary"
      />
    </a-modal>

    <a-modal v-model:open="datasetsOpen" title="样本集版本" :footer="null" :width="720">
      <div class="toolbar version-tools">
        <a-button v-if="project?.role === 'manager'" type="primary" @click="openDialog('publish')">发布样本集</a-button>
      </div>
      <a-spin :spinning="datasetLoading">
        <a-empty v-if="!datasets.length" description="尚未发布样本版本" />
        <div v-for="item in datasets" :key="item.id" class="dataset-row">
          <div>
            <strong>{{ item.name }}</strong
            ><small>{{ item.count }} 份 · {{ displayDate(item.createdAt) }}</small>
          </div>
          <div class="toolbar">
            <a-button v-if="project?.kind === 'adm' && hasAdm" size="small" @click="compareDataset(item)"
              >对照 ADM 结果</a-button
            >
            <a-button size="small" :loading="downloading === item.id" @click="exportDataset(item)">导出 JSON</a-button>
          </div>
        </div>
      </a-spin>
    </a-modal>

    <a-modal v-model:open="comparisonOpen" title="ADM 解析结果对照" :footer="null" :width="880">
      <p class="muted">按当前账号可访问的已保存解析结果对照。本操作不会调用模型。</p>
      <a-alert v-if="comparisonError" type="error" show-icon :message="comparisonError" />
      <a-spin :spinning="comparisonLoading">
        <a-empty v-if="!comparisons.length && !comparisonLoading && !comparisonError" description="没有可对照的样本" />
        <article v-for="row in comparisons" :key="row.sampleId" class="comparison">
          <strong>{{ row.title }}</strong>
          <a-tag v-if="row.status !== 'compared'" color="default" class="comparison-tag">
            {{ row.status === 'unlinked' ? '未关联 ADM 来件' : '已保存结果不可用' }}
          </a-tag>
          <table v-else-if="row.fields.length" class="summary-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>人工预期</th>
                <th>已保存结果</th>
                <th>对照</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(field, index) in row.fields" :key="index">
                <td>{{ field.label }}</td>
                <td>{{ field.expected }}</td>
                <td>{{ field.actual.join('、') || '未提取' }}</td>
                <td>
                  <a-tag :color="field.status === 'match' ? 'success' : 'warning'">
                    {{ { match: '一致', missing: '缺失', different: '不一致' }[field.status] }}
                  </a-tag>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted">该样本未包含可对照的字段。</p>
        </article>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { Modal } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FormDialog from '@/components/FormDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
import { parsingApi } from '@/features/adm-parsing/api'
import EvidenceViewer from './EvidenceViewer.vue'
import {
  annotationApi,
  type Account,
  type Comparison,
  type Dataset,
  type Evidence,
  type Label,
  type Member,
  type Project,
  type ProjectKind,
  type Sample,
  type SampleDraft,
  type SampleStatus,
  type SampleSummary,
} from './api'

type Dialog = 'create' | 'manage' | 'upload' | 'import' | 'assign' | 'return' | 'publish'
type EditableLabel = Omit<Label, 'id'> & { id?: string }
const auth = useAuthStore()
const route = useRoute()
const roleNames = { manager: '项目管理员', annotator: '标注员', reviewer: '复核员' }
const statusNames = { draft: '待标注', submitted: '待复核', returned: '待补充', approved: '已确认' }
const statusColors = { draft: 'default', submitted: 'processing', returned: 'warning', approved: 'success' }
const actionNames: Record<string, string> = {
  reopen: '重新编辑',
  upload: '导入',
  import: '引用 ADM',
  assign: '分配',
  save: '保存草稿',
  submit: '提交复核',
  return: '退回补充',
  approve: '复核通过',
}
const statusOptions = [
  { value: '', label: '全部状态' },
  ...Object.entries(statusNames).map(([value, label]) => ({ value, label })),
]
const labelScopes = [
  { value: 'field', label: '字段片段' },
  { value: 'document', label: '整份文件' },
]
const memberRoles = [
  { value: 'annotator', label: '标注员' },
  { value: 'reviewer', label: '复核员' },
]
const pageSize = 20
const canCreate = ref(false)
const projects = ref<Project[]>([])
const projectId = ref('')
const project = computed(() => projects.value.find((item) => item.id === projectId.value))
const loading = ref(false)
const queueLoading = ref(false)
const detailLoading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const items = ref<SampleSummary[]>([])
const current = ref<Sample | null>(null)
const draft = ref<SampleDraft | null>(null)
const originalDraft = ref('')
const total = ref(0)
const counts = ref<Record<SampleStatus, number>>({ draft: 0, submitted: 0, returned: 0, approved: 0 })
const page = ref(1)
const keyword = ref('')
const appliedKeyword = ref('')
const statusFilter = ref('')
const selection = ref<Evidence | null>(null)
const highlight = ref<Evidence | null>(null)
const menuPosition = ref({ x: 0, y: 0 })
const dialog = ref<Dialog | null>(null)
const dialogBusy = ref(false)
const dialogError = ref('')
const projectName = ref('')
const projectKind = ref<ProjectKind>('general')
const pendingFiles = ref<File[]>([])
const groupUpload = ref(false)
const admTaskId = ref('')
const admOptions = ref<{ value: string; label: string }[]>([])
const reviewNote = ref('')
const assignee = ref<string | undefined>()
const pendingLabels = ref<EditableLabel[]>([])
const pendingMembers = ref<Member[]>([])
const accountList = ref<Account[]>([])
const summaryOpen = ref(false)
const summaryLoading = ref(false)
const summaryItems = ref<SampleSummary[]>([])
const summaryStatus = ref('')
const summaryPage = ref(1)
const summaryTotal = ref(0)
const datasetsOpen = ref(false)
const datasetLoading = ref(false)
const datasets = ref<Dataset[]>([])
const datasetName = ref('')
const publishIds = ref<string[]>([])
const publishCandidates = ref<SampleSummary[]>([])
const publishLoading = ref(false)
const publishPage = ref(1)
const publishTotal = ref(0)
const downloading = ref('')
const comparisonOpen = ref(false)
const comparisonLoading = ref(false)
const comparisonError = ref('')
const comparisons = ref<Comparison[]>([])
let queueGeneration = 0
let detailGeneration = 0
let summaryGeneration = 0
let admQueryHandled = false

const hasAdm = computed(() => Boolean(auth.user?.isAdmin || auth.user?.menuCodes?.includes('adm.center')))
const mayUpload = computed(() => project.value?.role === 'manager' || project.value?.role === 'annotator')
const editable = computed(() => current.value?.canEdit === true)
const fieldLabels = computed(() => project.value?.labels.filter((item) => item.scope === 'field') ?? [])
// Keep the retired defaults in saved dictionaries so historical label IDs still resolve.
const retiredLabels = computed(() =>
  project.value?.kind === 'adm'
    ? project.value.labels.filter(
        (label) =>
          label.scope === 'document' &&
          (label.name === 'ARC 模板' || label.name === 'BSP 模板') &&
          label.description === '整份原件来自 ' + label.name + '。',
      )
    : [],
)
const activeLabels = computed(() => project.value?.labels.filter((label) => !retiredLabels.value.includes(label)) ?? [])
const documentLabels = computed(() => activeLabels.value.filter((label) => label.scope === 'document'))
const dirty = computed(() => draft.value !== null && JSON.stringify(draft.value) !== originalDraft.value)
const evidenceMarks = computed(() => [
  ...(draft.value?.marks ?? []).map((mark) => ({ ...mark, color: labelColor(mark.labelId) })),
  ...(draft.value?.titleEvidence ? [draft.value.titleEvidence] : []),
])
const availableAccounts = computed(() =>
  accountList.value
    .filter(
      (item) => item.id !== project.value?.ownerId && !pendingMembers.value.some((member) => member.id === item.id),
    )
    .map((item) => ({ value: item.id, label: item.name + ' · ' + item.id })),
)
const assigneeOptions = computed(() => {
  const members = (project.value?.members ?? [])
    .filter((item) => item.role === 'annotator')
    .map((item) => ({ value: item.id, label: item.name }))
  const owner = project.value?.ownerId
  if (owner) members.unshift({ value: owner, label: '项目负责人' })
  return members
})
const positionCount = computed(() => new Set(draft.value?.marks.map(positionKey)).size)
const labelCounts = computed(() =>
  fieldLabels.value
    .map((label) => ({
      ...label,
      count: draft.value?.marks.filter((mark) => mark.labelId === label.id).length ?? 0,
    }))
    .filter((label) => label.count > 0),
)
const dialogTitle = computed(
  () =>
    (dialog.value &&
      {
        create: '新建标注项目',
        manage: '标签与项目成员',
        upload: '添加样本文件',
        import: '引用 ADM 来件',
        assign: '分配标注员',
        return: '退回补充',
        publish: '发布样本集',
      }[dialog.value]) ||
    '',
)

function describe(reason: unknown) {
  return reason instanceof Error ? reason.message : '请求失败，请稍后重试。'
}

const displayDate = formatDateTimeDisplay

function positionKey(mark: Evidence) {
  const identity = [mark.fileId, mark.page ?? mark.segmentId ?? null]
  if (mark.page) {
    const pageText = current.value?.segments.find((segment) => segment.fileId === mark.fileId && segment.page === mark.page)
      ?.text.normalize('NFKC').replace(/[\p{White_Space}]/gu, '')
    const quote = mark.quote.normalize('NFKC').replace(/[\p{White_Space}]/gu, '')
    if (pageText && quote) {
      const first = pageText.indexOf(quote)
      if (first >= 0 && pageText.indexOf(quote, first + 1) < 0) {
        const from = Array.from(pageText.slice(0, first)).length
        return JSON.stringify([...identity, 'text', from, from + Array.from(quote).length])
      }
    }
    if (mark.rects?.length) {
      const rectangles = mark.rects.map((rect) => [rect.x, rect.y, rect.w, rect.h].map((value) => value.toFixed(3)).join(',')).sort()
      return JSON.stringify([...identity, 'pdf', ...rectangles])
    }
  }
  return JSON.stringify([...identity, 'raw', mark.start ?? null, mark.end ?? null])
}

function evidenceLocation(mark: Evidence) {
  return (
    current.value?.segments.find((segment) => segment.id === mark.segmentId)?.locator ??
    (mark.page ? '第 ' + mark.page + ' 页' : current.value?.files.find((file) => file.id === mark.fileId)?.name) ??
    '原文'
  )
}

function labelName(id: string) {
  return project.value?.labels.find((label) => label.id === id)?.name ?? '历史标签'
}

function labelColor(id: string) {
  const palette = ['#ffe3a1', '#b9dfff', '#bbebd2', '#dfcbf8', '#ffd1c5', '#aee9ec']
  const index = fieldLabels.value.findIndex((label) => label.id === id)
  return palette[Math.max(0, index) % palette.length]
}

function acceptSample(sample: Sample) {
  current.value = sample
  const clean = {
    title: sample.title,
    platform: sample.platform,
    marks: sample.marks,
    fileLabels: sample.fileLabels,
    titleEvidence: sample.titleEvidence,
  }
  draft.value = JSON.parse(JSON.stringify(clean)) as SampleDraft
  originalDraft.value = JSON.stringify(draft.value)
  const index = items.value.findIndex((item) => item.id === sample.id)
  if (index !== -1)
    items.value[index] = {
      ...items.value[index],
      title: sample.title,
      platform: sample.platform,
      status: sample.status,
      version: sample.version,
      expected: sample.expected,
      positionCount: sample.positionCount,
      assigneeId: sample.assigneeId,
      canEdit: sample.canEdit,
      canReview: sample.canReview,
      canAssign: sample.canAssign,
      canDelete: sample.canDelete,
    }
}

function confirmLeave(): Promise<boolean> {
  if (busy.value) return Promise.resolve(false)
  if (!dirty.value) return Promise.resolve(true)
  return new Promise((resolve) =>
    Modal.confirm({
      title: '离开当前样本？',
      content: '你还有未保存的标注。',
      okText: '离开',
      cancelText: '继续编辑',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    }),
  )
}

async function loadProjects() {
  if (busy.value) return
  if (!(await confirmLeave())) return
  loading.value = true
  error.value = ''
  try {
    const result = await annotationApi.projects()
    projects.value = result.items
    canCreate.value = result.canCreate
    const next =
      projects.value.find((item) => item.id === projectId.value) ??
      (route.query.admTask
        ? projects.value.find((item) => item.kind === 'adm' && item.role === 'manager')
        : undefined) ??
      projects.value[0]
    await openProject(next?.id ?? '')
    if (
      !admQueryHandled &&
      next?.kind === 'adm' &&
      next.role === 'manager' &&
      hasAdm.value &&
      typeof route.query.admTask === 'string'
    ) {
      admQueryHandled = true
      await openDialog('import')
      admTaskId.value = route.query.admTask
    }
  } catch (reason) {
    error.value = describe(reason)
  } finally {
    loading.value = false
  }
}

async function openProject(id: string) {
  projectId.value = id
  current.value = null
  draft.value = null
  page.value = 1
  keyword.value = ''
  appliedKeyword.value = ''
  statusFilter.value = ''
  notice.value = ''
  clearSelection()
  highlight.value = null
  detailGeneration++
  detailLoading.value = false
  items.value = []
  total.value = 0
  counts.value = { draft: 0, submitted: 0, returned: 0, approved: 0 }
  if (!id) return
  await loadQueue()
}

async function switchProject(id: string) {
  if (!busy.value && id !== projectId.value && (await confirmLeave()) && !busy.value) await openProject(id)
}

async function loadQueue() {
  const generation = ++queueGeneration
  const id = projectId.value
  if (!id) return
  queueLoading.value = true
  try {
    const result = await annotationApi.samples(id, {
      page: page.value,
      status: statusFilter.value,
      search: appliedKeyword.value,
    })
    if (generation !== queueGeneration || id !== projectId.value) return
    items.value = result.items
    total.value = result.total
    counts.value = result.counts
  } catch (reason) {
    if (generation === queueGeneration && id === projectId.value) error.value = describe(reason)
  } finally {
    if (generation === queueGeneration) queueLoading.value = false
  }
}

function applySearch() {
  appliedKeyword.value = keyword.value.trim()
  page.value = 1
  return loadQueue()
}

function filterStatus(value: string) {
  statusFilter.value = value
  page.value = 1
  return loadQueue()
}

function filterFromSummary(status: SampleStatus) {
  summaryOpen.value = false
  return filterStatus(status)
}

function changePage(value: number) {
  page.value = value
  return loadQueue()
}

function confirmDelete(item: SampleSummary) {
  const unsaved = current.value?.id === item.id && dirty.value
  Modal.confirm({
    title: '删除样本？',
    content: '确认从队列删除「' + (item.title || item.name) + '」？' + (unsaved ? '当前未保存的标注也会丢弃。' : ''),
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      if (busy.value || detailLoading.value || item.projectId !== projectId.value) return
      busy.value = true
      error.value = ''
      notice.value = ''
      try {
        await annotationApi.deleteSample(item.id, item.version)
        if (current.value?.id === item.id) {
          current.value = null
          draft.value = null
          clearSelection()
          highlight.value = null
        }
        if (items.value.length === 1 && items.value[0]?.id === item.id && page.value > 1) page.value--
        await loadQueue()
        notice.value = '样本已从队列删除。'
      } catch (reason) {
        error.value = describe(reason)
        await loadQueue()
      } finally {
        busy.value = false
      }
    },
  })
}

async function selectSample(id: string, force = false) {
  if (!force && (busy.value || current.value?.id === id || !(await confirmLeave()) || busy.value)) return
  const generation = ++detailGeneration
  detailLoading.value = true
  clearSelection()
  highlight.value = null
  error.value = ''
  try {
    const sample = await annotationApi.sample(id)
    if (generation === detailGeneration && sample.projectId === projectId.value) acceptSample(sample)
  } catch (reason) {
    if (generation === detailGeneration) error.value = describe(reason)
  } finally {
    if (generation === detailGeneration) detailLoading.value = false
  }
}

function openSelection(evidence: Evidence, x: number, y: number) {
  if (!editable.value || busy.value) return
  selection.value = evidence
  menuPosition.value = {
    x: Math.max(8, Math.min(x + 8, innerWidth - 248)),
    y: Math.max(8, Math.min(y + 8, innerHeight - 275)),
  }
}

function clearSelection() {
  selection.value = null
}

function focus(evidence: Evidence | null) {
  if (evidence) highlight.value = { ...evidence }
}

function applyField(labelId: string) {
  const evidence = selection.value
  if (!draft.value || !evidence || !editable.value) return
  if (!draft.value.marks.some((mark) => mark.labelId === labelId && positionKey(mark) === positionKey(evidence))) {
    if (draft.value.marks.length >= 300 || evidence.quote.length > 2000 || (evidence.rects?.length ?? 0) > 100) {
      error.value = '每份样本最多 300 条字段标注。单个选区请控制在 2,000 字和 100 个高亮区域内。'
      return
    }
    draft.value.marks.push({ ...evidence, labelId })
  }
  focus(evidence)
  clearSelection()
  window.getSelection()?.removeAllRanges()
}

function applyTitle() {
  if (!draft.value || !selection.value || !editable.value) return
  if (selection.value.quote.length > 200) {
    error.value = '标题最多 200 字，请缩小选区。'
    return
  }
  draft.value.title = selection.value.quote
  draft.value.titleEvidence = selection.value
  focus(selection.value)
  clearSelection()
  window.getSelection()?.removeAllRanges()
}

function discardTitleEvidence() {
  if (draft.value?.titleEvidence && draft.value.title !== draft.value.titleEvidence.quote)
    draft.value.titleEvidence = null
}

function changeMarkLabel(index: number, value: string) {
  const mark = draft.value?.marks[index]
  if (!mark || !draft.value) return
  if (
    draft.value.marks.some(
      (other, i) => i !== index && other.labelId === value && positionKey(mark) === positionKey(other),
    )
  ) {
    error.value = '该位置已有此字段标签。'
    return
  }
  mark.labelId = value
}

function removeMark(index: number) {
  draft.value?.marks.splice(index, 1)
  highlight.value = null
}

function toggleLabel(id: string) {
  if (!draft.value) return
  const index = draft.value.fileLabels.indexOf(id)
  if (index < 0) draft.value.fileLabels.push(id)
  else draft.value.fileLabels.splice(index, 1)
}

async function saveDraft() {
  if (!current.value || !draft.value || !project.value || !editable.value || busy.value || detailLoading.value) return
  busy.value = true
  error.value = ''
  try {
    acceptSample(await annotationApi.updateSample(current.value.id, current.value.version, project.value.version, draft.value))
    notice.value = '草稿已保存。'
  } catch (reason) {
    error.value = describe(reason)
  } finally {
    busy.value = false
  }
}

async function submitDraft() {
  if (!draft.value || !current.value || !project.value || !editable.value || busy.value || detailLoading.value) return
  if (!draft.value.title.trim() || !draft.value.platform.trim() || !draft.value.marks.length) {
    error.value = '请填写来源平台和文件标题，并至少标记一处字段证据。'
    return
  }
  const id = current.value.id
  const projectVersion = project.value.version
  const pending = items.value.filter(
    (item) => item.id !== id && item.canEdit && ['draft', 'returned'].includes(item.status),
  )
  const currentIndex = items.value.findIndex((item) => item.id === id)
  const next = pending.find((item) => items.value.indexOf(item) > currentIndex) ?? pending[0]
  busy.value = true
  error.value = ''
  try {
    if (current.value.labelReviewNeeded && !dirty.value) {
      error.value = '请核对标签定义并重新保存草稿，再提交。'
      return
    }
    if (dirty.value) acceptSample(await annotationApi.updateSample(id, current.value.version, projectVersion, draft.value))
    const submitted = await annotationApi.action(id, { version: current.value.version, projectVersion, action: 'submit' })
    acceptSample(submitted)
    await loadQueue()
    const nextId =
      next?.id ?? submitted.nextEditableId ?? items.value.find((item) => item.id !== id && item.canEdit)?.id
    if (nextId) await selectSample(nextId, true)
    notice.value = '已提交复核。' + (nextId && current.value?.id === nextId ? '已打开下一份待标注样本。' : '')
  } catch (reason) {
    error.value = describe(reason)
  } finally {
    busy.value = false
  }
}

function confirmReopen() {
  const sample = current.value
  if (!sample?.canReopen || busy.value || detailLoading.value) return
  Modal.confirm({
    title: '重新编辑这个样本？',
    content: '样本将回到待标注。修改完成后，请重新提交复核。',
    okText: '重新编辑',
    cancelText: '取消',
    onOk: async () => {
      if (current.value?.id === sample.id && current.value.version === sample.version) await runAction('reopen')
    },
  })
}

async function runAction(action: 'approve' | 'return' | 'assign' | 'reopen', value = '') {
  if (!current.value || busy.value || detailLoading.value) return false
  busy.value = true
  error.value = ''
  try {
    const data = {
      version: current.value.version,
      action,
      ...(action === 'assign' ? { assigneeId: value } : action === 'return' ? { note: value } : {}),
    }
    acceptSample(await annotationApi.action(current.value.id, data))
    await loadQueue()
    notice.value = {
      approve: '复核通过。',
      return: '已退回补充。',
      assign: '已分配标注人员。',
      reopen: '样本已回到待标注，可以继续编辑。',
    }[action]
    return true
  } catch (reason) {
    const message = describe(reason)
    if (dialog.value) dialogError.value = message
    else error.value = message
    return false
  } finally {
    busy.value = false
  }
}

async function openDialog(next: Dialog) {
  dialogError.value = ''
  dialog.value = next
  if (next === 'create') {
    projectName.value = ''
    projectKind.value = 'general'
  } else if (next === 'upload') {
    pendingFiles.value = []
    groupUpload.value = false
  } else if (next === 'manage' && project.value) {
    pendingLabels.value = activeLabels.value.map((label) => ({ ...label }))
    pendingMembers.value = project.value.members.map((member) => ({ ...member }))
    accountList.value = []
    try {
      accountList.value = (await annotationApi.accounts(project.value.id)).items
    } catch (reason) {
      dialogError.value = describe(reason)
    }
  } else if (next === 'import') {
    admTaskId.value = ''
    admOptions.value = []
    try {
      const data = await parsingApi.list(1, '')
      admOptions.value = data.items.map((item) => ({
        value: item.id,
        label: [item.title, item.createdAt].filter(Boolean).join(' · '),
      }))
    } catch {
      dialogError.value = '来件列表暂不可用，仍可填写已知的来件 ID。'
    }
  } else if (next === 'assign') {
    assignee.value = current.value?.assigneeId ?? undefined
  } else if (next === 'return') {
    reviewNote.value = ''
  } else if (next === 'publish') {
    datasetsOpen.value = false
    datasetName.value = ''
    publishIds.value = []
    await loadPublishPage(1)
  }
}

function closeDialog() {
  dialog.value = null
}

function addMember(id: string) {
  const account = accountList.value.find((item) => item.id === id)
  if (account) pendingMembers.value.push({ ...account, role: 'annotator' })
}

function pickFiles(event: Event) {
  pendingFiles.value = [...((event.target as HTMLInputElement).files ?? [])]
}

function parseAdmReference(value: string) {
  const input = value.trim()
  if (!input.includes('?')) return input
  return new URL(input, window.location.origin).searchParams.get('task')?.trim() ?? ''
}

async function submitDialog() {
  if (dialogBusy.value) return
  const action = dialog.value
  const id = projectId.value
  dialogBusy.value = true
  dialogError.value = ''
  try {
    if (action === 'create') {
      if (!projectName.value.trim()) throw new Error('请输入项目名称。')
      if (!(await confirmLeave())) return
      const created = await annotationApi.createProject(projectName.value.trim(), projectKind.value)
      projects.value.push(created)
      closeDialog()
      await openProject(created.id)
    } else if (action === 'manage' && project.value) {
      if (pendingLabels.value.some((label) => !label.name.trim() || !label.description.trim()))
        throw new Error('请填写标签名称和定义。')
      const updated = await annotationApi.updateProject(id, {
        version: project.value.version,
        labels: [...pendingLabels.value, ...retiredLabels.value],
        members: pendingMembers.value,
      })
      projects.value = projects.value.map((item) => (item.id === id ? updated : item))
      closeDialog()
    } else if (action === 'upload' || action === 'import') {
      if (!(await confirmLeave())) return
      const sourceId = action === 'import' ? parseAdmReference(admTaskId.value ?? '') : ''
      if (action === 'import' && !sourceId) throw new Error('请选择 ADM 来件或填写包含 task 的来件链接。')
      const result =
        action === 'upload'
          ? await annotationApi.upload(id, pendingFiles.value, groupUpload.value)
          : { items: [await annotationApi.importAdm(id, sourceId)], errors: [] }
      await loadQueue()
      if (result.items[0]) await selectSample(result.items[0].id, true)
      if (result.errors.length) dialogError.value = result.errors.map((row) => row.name + '：' + row.message).join('；')
      else closeDialog()
      notice.value = result.items.length ? '已加入 ' + result.items.length + ' 份样本。' : ''
    } else if (action === 'assign') {
      if (!assignee.value) throw new Error('请选择标注人员。')
      if (!(await confirmLeave())) return
      if (await runAction('assign', assignee.value)) closeDialog()
    } else if (action === 'return') {
      if (!reviewNote.value.trim()) throw new Error('请说明需要补充的内容。')
      if (await runAction('return', reviewNote.value.trim())) closeDialog()
    } else if (action === 'publish') {
      if (!datasetName.value.trim() || !publishIds.value.length) throw new Error('请输入样本集名称并选择至少一份样本。')
      await annotationApi.publish(id, datasetName.value.trim(), publishIds.value)
      closeDialog()
      await showDatasets()
      notice.value = '样本集已发布。'
    }
  } catch (reason) {
    dialogError.value = describe(reason)
  } finally {
    dialogBusy.value = false
  }
}

async function loadSummary(next: number) {
  const id = projectId.value
  if (!id) return
  const generation = ++summaryGeneration
  summaryPage.value = next
  summaryLoading.value = true
  try {
    const data = await annotationApi.samples(id, { page: next, status: summaryStatus.value, search: '' })
    if (generation === summaryGeneration && id === projectId.value) {
      summaryItems.value = data.items
      summaryTotal.value = data.total
      counts.value = data.counts
    }
  } catch (reason) {
    if (generation === summaryGeneration) error.value = describe(reason)
  } finally {
    if (generation === summaryGeneration) summaryLoading.value = false
  }
}

async function showSummary() {
  summaryStatus.value = ''
  summaryItems.value = []
  summaryTotal.value = 0
  summaryOpen.value = true
  await loadSummary(1)
}

async function openFromSummary(id: string) {
  summaryOpen.value = false
  await selectSample(id)
}

async function showDatasets() {
  const id = projectId.value
  datasetsOpen.value = true
  datasetLoading.value = true
  try {
    datasets.value = (await annotationApi.datasets(id)).items
  } catch (reason) {
    error.value = describe(reason)
  } finally {
    datasetLoading.value = false
  }
}

async function loadPublishPage(next: number) {
  if (publishLoading.value) return
  publishLoading.value = true
  try {
    const result = await annotationApi.samples(projectId.value, { page: next, status: 'approved', search: '' })
    publishCandidates.value = next === 1 ? result.items : [...publishCandidates.value, ...result.items]
    publishPage.value = next
    publishTotal.value = result.total
  } catch (reason) {
    dialogError.value = describe(reason)
  } finally {
    publishLoading.value = false
  }
}

async function exportDataset(item: Dataset) {
  downloading.value = item.id
  try {
    const payload = await annotationApi.dataset(projectId.value, item.id)
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' }),
    )
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = '标注样本集-' + item.id + '.json'
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch (reason) {
    error.value = describe(reason)
  } finally {
    downloading.value = ''
  }
}

async function compareDataset(item: Dataset) {
  if (comparisonLoading.value) return
  datasetsOpen.value = false
  comparisonOpen.value = true
  comparisonLoading.value = true
  comparisonError.value = ''
  comparisons.value = []
  try {
    comparisons.value = (await annotationApi.compareAdm(projectId.value, item.id)).samples
  } catch (reason) {
    comparisonError.value = describe(reason)
  } finally {
    comparisonLoading.value = false
  }
}

function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') clearSelection()
  if (
    !selection.value ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    (event.target instanceof HTMLElement && /INPUT|TEXTAREA|SELECT/.test(event.target.tagName))
  )
    return
  if (!/^[1-9]$/.test(event.key)) return
  const label = fieldLabels.value[Number(event.key) - 1]
  if (!label) return
  event.preventDefault()
  applyField(label.id)
}

function outsideSelection(event: PointerEvent) {
  if (event.target instanceof HTMLElement && !event.target.closest('.selection-menu, .viewer-scroll')) clearSelection()
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) event.preventDefault()
}

onBeforeRouteLeave(() => !busy.value && confirmLeave())
onMounted(async () => {
  document.addEventListener('keydown', keydown)
  document.addEventListener('pointerdown', outsideSelection)
  window.addEventListener('beforeunload', beforeUnload)
  await nextTick()
  await loadProjects()
})
onBeforeUnmount(() => {
  queueGeneration++
  detailGeneration++
  summaryGeneration++
  document.removeEventListener('keydown', keydown)
  document.removeEventListener('pointerdown', outsideSelection)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<style scoped>
.annotation {
  min-width: 0;
  display: grid;
  gap: 12px;
}
.panel {
  min-width: 0;
  min-height: 0;
  border: 1px solid #dbe4ef;
  border-radius: 7px;
  background: #fff;
}
.project-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.toolbar,
.tag-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.project-select {
  display: flex;
  align-items: center;
  gap: 8px;
}
.project-select :deep(.ant-select) {
  min-width: 175px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(150px, 0.63fr) minmax(270px, 2fr) minmax(240px, 1fr);
  gap: 12px;
  height: clamp(380px, calc(100dvh - var(--annotation-top-space, 288px)), 860px);
}
.annotation:has(> .ant-alert) {
  --annotation-top-space: 344px;
}
.annotation:has(> .ant-alert + .ant-alert) {
  --annotation-top-space: 398px;
}
.queue,
.original,
.detail {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
h2 {
  font-size: 15px;
  margin: 0;
  padding: 11px 13px;
  border-bottom: 1px solid #e7edf4;
}
h2 small,
h3 small {
  color: #51677f;
  font-weight: 400;
  margin-left: 8px;
}
h3 {
  font-size: 14px;
}
.queue-tools,
.detail-scroll {
  padding: 11px 13px;
}
.queue-tools {
  display: grid;
  gap: 7px;
}
.queue-list,
.detail-scroll {
  overflow: auto;
  flex: 1 1 auto;
  min-height: 0;
}
.queue-row {
  display: flex;
  align-items: center;
  border-top: 1px solid #e8eef5;
}
.queue-row > :deep(.ant-btn) {
  flex: none;
  margin-right: 6px;
}
.queue-item {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 3px;
  padding: 9px 12px;
  width: 100%;
  text-align: left;
  overflow-wrap: anywhere;
  background: #fff;
  border: none;
  cursor: pointer;
  color: #25364b;
}
.queue-item:hover,
.queue-item[aria-pressed='true'] {
  background: #eaf4ff;
}
.queue-item[aria-pressed='true'] {
  border-left: 3px solid #2867a3;
  padding-left: 9px;
}
.queue-item:focus-visible,
.selection-menu button:focus-visible {
  outline: 2px solid #3475b4;
  outline-offset: -2px;
}
.queue-item small,
.muted {
  color: #52677f;
}
.queue :deep(.ant-pagination) {
  padding: 8px;
}
.original > :deep(.evidence-panel) {
  flex: 1 1 auto;
}
.detail-spinner {
  margin: auto;
}
.metadata,
.dialog-fields {
  display: grid;
  gap: 9px;
}
.metadata label,
.dialog-fields label {
  display: grid;
  gap: 4px;
}
.metadata :deep(.ant-input-number),
.full-width {
  width: 100%;
}
.detail-section {
  margin-top: 13px;
  padding-top: 10px;
  border-top: 1px solid #e8edf4;
}
.detail-actions {
  padding: 9px;
  border-top: 1px solid #e7edf4;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.mark-row {
  border-bottom: 1px solid #e8edf4;
  padding: 6px 0;
}
.mark-row p {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  margin-bottom: 4px;
}
.mark-link {
  padding: 0;
  max-width: 100%;
  white-space: normal;
  text-align: left;
  height: auto;
}
.label-color {
  display: inline-block;
  width: 9px;
  height: 9px;
  border: 1px solid #9eb0c3;
  border-radius: 50%;
  margin-right: 4px;
}
.mark-label {
  flex: 1;
  min-width: 125px;
}
.history {
  padding-left: 18px;
}
.history li {
  margin: 5px 0;
}
.selection-menu {
  position: fixed;
  z-index: 1050;
  width: 235px;
  max-height: min(260px, 46dvh);
  overflow: auto;
  background: #fff;
  border: 1px solid #cadaed;
  border-radius: 6px;
  box-shadow: 0 5px 22px #16345430;
  padding: 6px;
}
.selection-title {
  color: #4f647e;
  font-size: 12px;
  padding: 3px 7px 5px;
  overflow-wrap: anywhere;
  max-height: 44px;
  overflow: hidden;
}
.selection-menu button {
  display: flex;
  justify-content: space-between;
  border: none;
  background: #fff;
  color: #203754;
  width: 100%;
  padding: 6px 8px;
  text-align: left;
  cursor: pointer;
}
.selection-menu button:hover {
  background: #eaf4ff;
}
kbd {
  font-size: 12px;
  color: #526b84;
  padding-left: 8px;
}
.label-definition {
  display: grid;
  grid-template-columns: 112px minmax(90px, 1fr) minmax(100px, 1.8fr) auto;
  gap: 6px;
}
.summary-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.summary-status button {
  padding: 6px 10px;
  color: #234567;
  background: #f1f6fd;
  border: 1px solid #dce8f8;
  cursor: pointer;
  border-radius: 5px;
}
.summary-table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  text-align: left;
}
.summary-table :is(th, td) {
  padding: 8px;
  border-bottom: 1px solid #e5edf6;
  overflow-wrap: anywhere;
}
.summary-table small,
.dataset-row small {
  display: block;
  color: #536982;
}
.dataset-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #e5edf6;
}
.version-tools {
  margin-bottom: 10px;
}
.publish-list {
  display: grid;
  gap: 6px;
  margin-bottom: 8px;
}
.comparison {
  padding: 12px 0;
  border-bottom: 1px solid #e5edf6;
}
.comparison-tag {
  margin-left: 8px;
}
@media (max-width: 1040px) {
  .workspace {
    height: auto;
    grid-template-columns: minmax(135px, 0.6fr) minmax(230px, 1.6fr);
  }
  .detail {
    grid-column: 1 / -1;
  }
  .detail-scroll {
    max-height: 380px;
  }
  .queue,
  .original {
    height: clamp(430px, 64dvh, 650px);
  }
}
@media (max-width: 650px) {
  .workspace {
    grid-template-columns: 1fr;
  }
  .queue {
    height: 220px;
  }
  .original {
    height: clamp(430px, 65dvh, 620px);
  }
  .label-definition {
    grid-template-columns: 1fr;
  }
}
</style>
