# 各菜单内容区主题统一

任务 CONTENT-THEME-20261118。用户已批准综合分析和ADM台账两张视觉样例，要求按同一风格调整各菜单内容，不增加多余图标/统计卡片/业务动作，保留菜单、功能、权限，字体不得放大；完成验证后推送公司GitLab analytics/data_report main，其他任务不得带入。

## 基线与范围

实际隔离基线为 `39f34540f638b1a3ce7aad43e1ba5b3d97909228`，不是旧的c52e224。工作区从最新origin/main创建时，其他已发布任务已在main，全部保留；不复用原fat_cy工作区的未提交内容。工作树：`D:/data_center_code/.worktrees/content-theme-20261118`。

主会话使用chief-of-staff、frontend-design，承担绘景、星桥、明鉴；无子代理。L4评估：多模块公共样式变更，采用路由/依赖清单、全组件源码边界校验、SSR与构建自检；未获本任务独立委派授权，未完成独立审查，不冒充L4通过。

数据容量方法裁剪：仅展示样式，不改加工/查询/分页/导出链路，不下载或处理真实经营数据，不声称容量或性能提升。无SQL、后端或数据写入。

## 已批准样例到正式页面

| 目标 | 实现 | 保留与约束 |
|---|---|---|
| 页头、筛选、页签清晰分层 | 复用现有PageHeader/FilterPanel及公共content-theme.css | 不增删字段或查询入口；原条件生效规则保持 |
| 白色面板、细边界、克制蓝色交互 | theme/platform.ts增加卡片/表格/弹窗/抽屉/页签token；本地CSS接入同一组变量 | 原字体、布局、数据查询及状态归属不变 |
| 不要大面积渐变和重阴影 | 实际业务页的旧渐变标题/主指标块改为白色或现有浅色面板，统一容器边界/8px常用圆角 | 现有指标卡保留，不新增任何指标/统计卡片；保留原统计口径 |
| 密集表格/原生ADM表与Ant表一致 | 统一表头浅蓝灰、细边界；ADM内嵌主题变量对齐平台 | 不改列定义、排序、筛选、分页、合计、按钮或责任链 |
| 弹窗与详情统一 | Modal/Drawer主题token及原有局部CSS接入共享变量 | 不改窗口打开/关闭、保存/重试、脏数据确认或权限逻辑 |
| 图标克制 | 仅移除公共筛选提示和重置按钮旁两个重复装饰图标，保留文字 | 未增加图标；危险/错误/状态及原业务按钮图标不批量删除 |
| 字体不放大 | 逐文件比较全部CSS font相关声明；共享新层不写font/字号 | 字号、字重、font-family及现有行高/布局声明保持；不靠缩字/放大掩盖问题 |

先核对真实路由：当前综合分析使用ComprehensiveAnalysisLiveView，样例图里的演示数据不写入正式页面；ADM仍按实际菜单、阶段、字段和权限展示。图中示意金额、图表、记录和文案不是新的业务契约。菜单、首页、登录/验证码和公司Logo不在本次改造范围。

## 页面与依赖覆盖

路由登记36个唯一页面组件；排除登录、改密、404后，内部页面组件33个，关联Vue依赖69个。多个菜单路由共用组件，不能把唯一组件数当成菜单数或已运行的业务场景数。69个模板均做结构编译；61个既有样式块/外置样式做字体与非视觉属性边界检查。无局部改动的页面通过共享token/公共内容样式承接。

| 页面组件 | 现有标题或模式 |
|---|---|
| `features/adm-parsing/AdmParsingView.vue` | ADM 解析 |
| `features/adm/AdmAnalysisView.vue` | ADM 业务分析 |
| `features/adm/AdmCenterView.vue` | ADM 任务台账 |
| `features/adm/AdmDetailView.vue` | 按路由/模式展示 |
| `features/data-workbench/DataWorkbenchView.vue` | 按路由/模式展示 |
| `features/hr-mail/HrMailView.vue` | HR报表邮件 |
| `features/resource-governance/ResourceGovernancePage.vue` | pageTitle |
| `views/AdminUsersView.vue` | 按路由/模式展示 |
| `views/AssetsView.vue` | 按路由/模式展示 |
| `views/BusinessProfitView.vue` | `${meta.name}利润分析` |
| `views/ComprehensiveAnalysisLiveView.vue` | 综合分析 |
| `views/GdsRouteGovernanceView.vue` | pageMeta.title |
| `views/HomeView.vue` | 按路由/模式展示 |
| `views/MonitoringCenterView.vue` | pageMeta.title |
| `views/OverviewView.vue` | 经营总览 |
| `views/ProblemsView.vue` | 经营问题中心 |
| `views/ProfitView.vue` | 出票利润分析 |
| `views/RiskBusinessAnalysisView.vue` | pageTitle |
| `views/RiskErrorAnalysisView.vue` | 差错分析 |
| `views/RiskFollowupView.vue` | pageTitle |
| `views/RiskMonthlyAnalysisView.vue` | 风控总览 |
| `views/RiskUploadView.vue` | 风控数据上传 |
| `views/RiskVerificationView.vue` | 风控核对 |
| `views/SmartComprehensiveView.vue` | 智能综合分析 |
| `views/SmartDetailView.vue` | 出票明细 |
| `views/SmartDimensionView.vue` | 维度分析 |
| `views/SmartMissedOrdersView.vue` | 漏处理订单 |
| `views/SmartOverviewView.vue` | 智能总览 |
| `views/SmartPlacementOrdersView.vue` | 收单情况 |
| `views/SmartPlacementPolicyView.vue` | 投放政策 |
| `views/TargetManagementView.vue` | 目标配置 |
| `views/TargetProgressView.vue` | 目标进度 |
| `views/UserBehaviorMonitorView.vue` | 用户行为监控 |

详细依赖闭包与原始清单在本worktree `.test-artifacts/content-theme-20261118/inventory.json`、page-coverage.json。归档功能也在主题覆盖范围；首页沿用已批准外壳/内容，不重做。构建或源码覆盖不代表所有权限、查询与业务流程已经真实运行。

## 验证方法与边界

- 69个关联SFC的模板与脚本对比基线；除公共FilterPanel删除两个装饰图标及其未用import外，业务内容、v-if/v-for、事件、表单字段、props/emits与数据逻辑不变。由此核对没有新增卡片、按钮或权限条件。
- 既有CSS按声明序列比较：font/字号/字重与所有非视觉属性一致，只允许颜色、背景、边框、圆角、阴影、描边、主题变量变化。不改display/visibility/宽高/网格/定位/滚动属性，避免视觉修改隐藏或挤掉功能。
- 原红/橙/绿语义与JS图表系列数据/配色保留。旧深色标题内的浅红风险字在白底上改用可读的红色；负数主利润块改为白底红色文字/边界，保留负数文本和状态class，不变成正常结论。未同步、缺失、错误、加载的原文案与分支不变。
- 实际Vue/Ant SSR覆盖原菜单管理员/受限账号、收起和深色壳；另外渲染原公共PageHeader/FilterPanel/页签/表格/表单，使用合成的长标识、大负金额、未同步、禁用、加载和错误场景。不发业务HTTP请求、不写库。
- 生产构建、强制类型（vue-tsc -b --force）、相关ESLint、组件登记、README接口/菜单索引及diff空白检查分别记录，原始命令/退出码/耗时在checks.json。

项目AGENTS记录Work浏览器禁用，用户未解除该限制，本轮未启动或换通道绕过。SSR不是实际浏览器截图；真实1440/1280/1024、125%/150%缩放、长表格横滚、弹窗滚动、Tab/焦点/中文输入与真实账号业务验收仍未验，不称全站视觉或业务验收通过。既有DarkMode仅保持兼容，不称全部历史页面深色模式完成。

## 发布与复盘

只发布本任务frontend主题/样式与相关交付文档；API、router、stores、backend、数据库、部署脚本和其他任务不改。仅推公司GitLab main，不推GitHub、不部署、不查询CI、不发送群消息。若发布前main更新，先保留对方改动再集成，不强推。

复用本项目既有主题变量、组件和本地检查入口，无新增依赖；清理FilterPanel未用图标import。普通主题实现与既有方法应用，没有新增通用能力回传MYE；未改MYE。源码、隔离渲染、真实浏览器、远端发布、服务器部署与业务验收分别报告。


## 最终本地检查回执

- 强制类型 `vue-tsc -b --force` 退出0；相关51个Vue/TS源码文件ESLint退出0。
- 33内部页面组件/69关联SFC全部模板编译；61个既有样式块/外置样式完成字体及非视觉属性一致性检查。0新增卡片、0新增业务动作、0新增图标，移除两个装饰图标。新公共层只增加页头16px下留白及配色/边界规则，不增加字号或隐藏功能。
- 原菜单角色/收起/深色壳SSR与公共内容组件长文本/大负数/未知/加载/错误SSR均退出0；Modal/Drawer检查限于原有源码、CSS及token契约，未冒充真实打开窗口。
- 组件登记87个页面组件通过；README索引54菜单/274接口通过；差异空白检查通过。
- Vite生产构建退出0，26.32秒，保留原有大包警告。源码与容量/业务性能无关，不用此耗时宣称性能提升。
- 发布清单57个文件：51个既有局部/公共样式文件、2个主题/入口TS、1个新公共内容CSS、3个交付/规范/工作流文档；不包含测试脚本、构建包、其他工作区或后端内容。

脚本由已有项目检查复用扩展：修正纯模板FormGrid无script标签的SSR加载假设后通过，没有为夹具改业务实现或放宽字体/边界断言。独立审查、浏览器及业务验收仍未完成。main推送结果另以实际远端回读回执记录。
