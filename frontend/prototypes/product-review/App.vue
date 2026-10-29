<template>
  <a-layout class="app-shell review-portal">
    <a-layout-sider class="app-sidebar" :width="200" breakpoint="lg" collapsed-width="64" collapsible>
      <div class="app-brand"><div class="brand-copy"><strong>企业数据中台</strong><span>本地产品评审台</span></div></div>
      <a-menu theme="dark" mode="inline" :selected-keys="[page]" @click="selectPage">
        <a-menu-item key="home">模块目录</a-menu-item>
        <a-menu-item v-for="item in modules" :key="item.id">{{ item.name }}</a-menu-item>
        <a-menu-item key="requirements">ADM 需求整理</a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout class="app-main">
      <header class="portal-header"><strong>需求先行 · 原型评审模式</strong><span>本地工作区 · {{ PORTAL_VERSION }}</span></header>
      <div v-if="message" class="portal-message" role="status">{{ message }}<button @click="message = ''">关闭</button></div>
      <div class="portal-workspace" :style="{ '--left': split + '%' }">
        <main class="portal-main">
          <div class="page-wrap">
            <PageHeader eyebrow="PRODUCT REVIEW" :title="title" description="先了解需求，再复用页面和组件；你审核具体版本后交开发。" />
            <template v-if="page === 'home'">
              <section class="portal-section"><h2>从同一个入口进入各模块</h2><p>ADM 和资源治理可以开始体验，其余模块在需求与范围明确后逐步接入。</p>
                <div class="module-list"><article v-for="item in modules" :key="item.id">
                  <div><h3>{{ item.name }}</h3><a-tag>{{ item.status }}</a-tag></div><p>{{ item.description }}</p>
                  <a-button @click="page = item.id">{{ item.artifact ? '进入模块' : '查看接入说明' }}</a-button>
                </article></div>
              </section>
            </template>
            <template v-else-if="page === 'requirements'">
              <section class="portal-section"><h2>按你熟悉的方式写，不必写成专业 PRD</h2><p>可以在这里整理，也可以直接给我 Word、Excel、文字或会议纪要。无法确定的内容写“待讨论”。</p>
                <p class="local-note">本机保存不会同步给同事或写入 Git。请导出文件交给我；不要只保留浏览器缓存。</p>
                <label class="requirement-field">整理人<a-input v-model:value="draft.author" :maxlength="100" /></label>
                <label v-for="item in requirementPrompts" :key="item.id" class="requirement-field">{{ item.title }}<small>{{ item.hint }}</small>
                  <a-textarea v-model:value="draft.notes[item.id]" :rows="4" :maxlength="20000" />
                </label>
                <div class="portal-actions"><a-button @click="saveDraft">保存本机草稿</a-button><a-button type="primary" @click="exportText">导出需求文字</a-button>
                  <a-button @click="exportDraft">导出草稿备份</a-button><label class="import-draft">恢复草稿<input type="file" accept=".json" @change="restoreDraft" /></label>
                </div>
              </section>
            </template>
            <template v-else>
              <section class="portal-section"><div class="module-heading"><h2>{{ activeModule.name }}</h2><a-tag>{{ activeModule.status }}</a-tag></div>
                <p>{{ activeModule.description }}</p><p>{{ activeModule.next }}</p>
                <template v-if="activeModule.artifact">
                  <div class="portal-actions"><a-button type="primary" :href="activeModule.artifact" target="_blank" rel="noopener">打开当前模块与联动 PRD</a-button><a-button @click="page = 'requirements'">整理 ADM 需求</a-button></div>
                  <p>ADM 0.4 / 资源治理 0.1 均复用现有前端；弹窗和抽屉在左侧动态打开，右侧组件PRD同步。会议规则与未实现边界在原型中明确列出。</p>
                  <dl><dt>原型源码</dt><dd>{{ activeModule.source }}</dd><dt>需求与交接入口</dt><dd>{{ activeModule.document }}</dd></dl>
                </template>
                <p v-else>接入时先读取已有需求和页面，复用可独立的展示组件，补充模拟数据。此入口尚无可操作业务页面。</p>
              </section>
              <section class="portal-section"><h2>同事如何接手</h2><ol><li>拉取 data_report 仓库，阅读 docs/product/local-product-review.md。</li><li>按文档构建本地评审包，打开统一首页。</li><li>先读本模块需求与待确认项，复用组件并局部修改。</li><li>用户批准版本和范围后再接正式接口。</li></ol></section>
            </template>
          </div>
        </main>
        <PanelDivider v-model="split" :min="50" :max="75" label="调整工作区和说明宽度" />
        <PrdPanel v-model="docTab" :title="title" :subtitle="`${PORTAL_VERSION} · 使用与交接说明`" :tabs="tabs">
          <template v-if="docTab === 'guide'"><h2>现在做什么</h2><p>{{ page === 'requirements' ? '写业务事实、问题、期望与例子。保留不同意见，不要求你先决定所有规则。' : '从模块目录选择业务，进入已有原型或查看接入状态。' }}</p>
            <h3>固定工作顺序</h3><ol><li>读取业务需求与来源。</li><li>对齐关键缺口和待确认项。</li><li>复用组件制作场景与联动PRD。</li><li>操作、提意见、修改、复验。</li><li>批准具体版本和范围后交开发。</li></ol>
            <h3>当前实际范围</h3><p>本页提供模块目录和ADM需求文字整理。ADM与资源治理已有可操作原型；其他模块尚待接入。全部为本地原型，业务数据使用合成示例。</p>
          </template>
          <template v-else-if="docTab === 'handoff'"><h2>你整理好后怎样给我</h2><ol><li>把需求文档、截图或脱敏样例放入工作区的“产品评审资料/ADM”文件夹。</li><li>告诉我文件路径以及哪个版本最新。</li><li>如果用了原型意见功能，把导出的JSON一并放入。</li></ol><p>例如：“按需求先行·原型评审模式，先读 D:\data_center_code\产品评审资料\ADM 里的最新版需求，先反馈理解和待确认项。”</p><p>也可以直接在聊天附文件。页面不能自动读取整个文件夹，资料由你告诉我位置后再读取。</p>
          </template>
          <template v-else><h2>维护入口</h2><dl><dt>模块注册</dt><dd>frontend/prototypes/product-review/catalog.ts</dd><dt>公共原型组件</dt><dd>frontend/prototypes/shared/README.md</dd><dt>需求与开发交接</dt><dd>docs/product/local-product-review.md</dd><dt>ADM需求索引</dt><dd>docs/product/modules/adm/README.md</dd></dl><p>源码和脱敏后的需求基线提交Git。线下原件、本机草稿与评审导出由业务人员保留，确认后再整理为可提交的需求台账。</p><p>页面框架复用中台 Ant Design Vue Layout/Menu、PageHeader 和 main.css；正式AppLayout含登录与权限请求，因此原型采用隔离入口。</p></template>
          <template #footer><a-button @click="page = 'requirements'">整理 ADM 需求</a-button></template>
        </PrdPanel>
      </div>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import PageHeader from '../../src/components/PageHeader.vue'
import PrdPanel from '../shared/PrdPanel.vue'
import PanelDivider from '../shared/PanelDivider.vue'
import { modules, requirementPrompts, emptyDraft, parseDraft, requirementText } from './catalog'

const PORTAL_VERSION = '产品评审台 0.1'
const STORAGE = 'data-report-product-review-adm-draft-v1'
const page = ref('home'), docTab = ref('guide'), split = ref(65), message = ref('')
const draft = ref(emptyDraft())
const tabs = [{ id: 'guide', title: '操作说明' }, { id: 'handoff', title: '需求怎么交' }, { id: 'source', title: '复用与维护' }]
const activeModule = computed(() => modules.find(item => item.id === page.value) || modules[0])
const title = computed(() => page.value === 'home' ? '本地产品评审台' : page.value === 'requirements' ? 'ADM 需求整理' : activeModule.value.name)
function selectPage({ key }: { key: string | number }) { page.value = String(key) }
try { const saved = localStorage.getItem(STORAGE); if (saved) draft.value = parseDraft(saved) }
catch { message.value = '本机草稿不可用，可以重新填写或恢复已导出的草稿。' }
function saveDraft() {
  try { localStorage.setItem(STORAGE, JSON.stringify(draft.value)); message.value = '已保存本机草稿。请同时导出文件保留。' }
  catch { message.value = '本机保存失败，请导出文件保留需求。' }
}
function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', content], { type }))
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  message.value = '已发起下载，请检查浏览器下载目录；把文件交给我后才能整理需求。'
}
function exportText() { download('ADM需求整理.txt', requirementText(draft.value), 'text/plain;charset=utf-8') }
function exportDraft() { download('ADM需求草稿.json', JSON.stringify(draft.value, null, 2), 'application/json;charset=utf-8') }
async function restoreDraft(event: Event) {
  const input = event.target as HTMLInputElement
  try {
    const file = input.files?.[0]; if (!file) return
    if (file.size > 2 * 1024 * 1024) throw new Error('草稿不能超过2MB')
    const next = parseDraft((await file.text()).replace(/^\uFEFF/, ''))
    if (!window.confirm('恢复草稿会替换当前填写内容，是否继续？')) return
    draft.value = next; message.value = '草稿已恢复，请核对后保存或导出。'
  } catch (error) { message.value = error instanceof Error ? error.message : '草稿恢复失败' }
  finally { input.value = '' }
}
</script>
