# 原型评审组件复用入口

统一门户已在 `../product-review` 接入 PrdPanel/PanelDivider，中台 PageHeader/Layout/Menu/main.css 继续复用。两个原型的离线构建共用 `offline-build.ts`，不再各写内联打包逻辑。执行 `npm --prefix frontend run package:product-review` 可构建并打包门户和ADM；开发交接见 `docs/product/local-product-review.md`。

ADM 评审前只整理无业务依赖的展示组件；业务需求和流程仍待用户审核。组件不访问 API、不读取账号、不写 localStorage、不批准业务版本。后续先复用此目录与 `src/components`，不复制整份 ADM App.vue。

| 入口 | 调用契约 | 业务页面保留职责 |
| --- | --- | --- |
| ReviewToolbar.vue | title/version/status，v-model:show-docs，can-detach；export/import(Event)/detach 事件，默认插槽补充操作 | 文件校验、导入确认、导出结构、独立窗口通信 |
| PrdPanel.vue | title/subtitle/label、tabs[{id,title}]、v-model 当前分类；默认内容插槽、footer 插槽 | 按需求编号提供 PRD、检查项、意见、批准范围和版本 |
| PanelDivider.vue | v-model 左侧百分比，min/max 默认40/70；父元素为左右面板共同容器 | 用百分比控制左侧宽度；自行决定窄屏布局 |
| review.css | 原型入口引入一次；工具栏、PRD、分隔条的公共结构样式 | 宿主的基础字体/按钮样式与响应式布局；正式应用不全局引入 |

PanelDivider 支持方向键/Home/End，指针取消、失焦、丢失捕获和卸载清理。只管理宽度，不操作业务状态或持久化数据。父层用 v-if 隐藏时会卸载并结束拖动。

现有表单继续直接使用 `src/components/FormDialog.vue`、`FormGrid.vue`、`AccountSelect.vue`、`DateField.vue`，无需再包一套。详细接口见 `docs/development/frontend-shared-controls.md`。

ADM 的 `definition.ts` 是当前需求/场景说明入口，`model.ts` 保留 ADM 模拟状态与金额/权限规则；App.vue 负责组合和本地评审记录。暂不将 ADM 审批、财务、任务分派或导入校验做成通用引擎。其他模块应提供自己的规则与记录命名空间，不能继承 ADM 的人员、版本批准或业务结论。

复用示例：

```vue
<PrdPanel v-model="tab" :title="requirement.title" :subtitle="version" :tabs="tabs">
  <p>{{ requirement.description }}</p>
  <template #footer><button @click="saveFeedback">保存意见</button></template>
</PrdPanel>
```

本轮验证只需 `npm --prefix frontend run build:adm-demo`；交付 HTML 使用 `node frontend/prototypes/adm-review/package-demo.mjs`。保留 ADM-DEMO-0.1 的业务版本及本地记录格式；组件重构不视作业务批准。真实浏览器拖拽、双窗口、缩放仍需人工验收。
