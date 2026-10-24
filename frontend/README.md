# 前端

入口为`src/main.ts`，路由在`src/router/index.ts`，公共组件在`src/components/`。Vue 3 + TypeScript + Ant Design Vue，Node 22，使用已提交的package-lock安装依赖。

```powershell
npm ci
npm run dev
npm run lint
npm run format:check
npm run type-check
npm run check:components
npm test
npm run build
```

资源治理领域位于`src/features/resource-governance/`，页面、API、状态与展示配置分别维护。旧`views/ResourceGovernanceView.vue`和`api/resourceGovernance.ts`保留显式兼容入口；新领域内部直接引用本领域实现，避免经兼容入口形成循环依赖。其他领域按需求逐步迁移。

`npm run format`只格式化已迁移领域和工程配置。跨领域共享组件留在`components/`，HTTP客户端留在`api/http.ts`。完整依赖与命名规则见[贡献指南](../CONTRIBUTING.md)。

## 新页面和窗口必须复用

先读[页面统一规范](../docs/product/ui-consistency-standard.md)及[公共控件调用契约](../docs/development/frontend-shared-controls.md)。页头用PageHeader、筛选用FilterPanel，新建/编辑优先FormDialog＋FormGrid，日期用DateField/DateRangeField；不要再逐页手写同样的窗口/日期/筛选布局。业务字段、权限和日期边界仍由页面及后端负责。首轮样板为ADM新建/主单编辑及综合分析筛选，历史页面尚未全部迁移。
