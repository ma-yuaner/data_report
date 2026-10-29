# 资源治理原页面评审基线与组件PRD 0.2

2026-10-29。状态：现有前端接入产品评审台，新需求已登记到设计基线1.0，业务口径待讨论；不代表启动暂存F01—F08或正式资源治理开发。

## 原菜单与演示范围

资源治理保留GDS资源治理、OTA渠道质量、航线配置诊断、白名单管理、治理执行、治理复盘六个原入口。直接复用ResourceGovernancePage与GdsRouteGovernanceView及原图表/筛选/下钻，不另造功能菜单。

GDS与OTA原MySQL/Hive请求由本机合成数据适配；航线、配置、白名单、事件、执行和复盘沿用原有本地演示组件，其缓存改为product-review-resource-governance-v01。此键仅原型构建替换，正式源码与原缓存不动。任何确认/接单/下线/恢复动作都只保存本机演示状态，不向真实技术系统、数据库或通知发送。

## 既有业务口径与边界

依据gds-resource-governance-reassessment-v3.md：Q为非MPIS查询（含NDC），S为出票航段，查定比按SUM(Q)/SUM(S)重算，MPIS占比为MPIS/全部查询。OTA质量不套用GDS查定比；航线没有航段分母，不伪造航线查定比。阈值、归因、生产名单和治理效果须真实证据。本机阈值和所有指标都是演示值，不作效果结论。

统计日期、平台、站点、GDS、PCC、资源通道、接口组和组合维度按原组件联动；“分析此项”继承范围到抽屉，再到日汇总和航线。全局导出在本机抽屉生成CSV，不接真实导出队列。

本轮在现状基线上增加需求与设计工作台1.0，需求来源、规则、字段、接口和数据缺口按稳定编号关联；新规则待确认，不把旧演示配置当正式批准方案。由用户自行测试反馈，不做大批浏览器测试。

## 设计追溯入口

完整设计链路见design-baseline-v1.md及评审台的“需求与设计”。正常、零记录、航段部分同步、查询失败、无查询权限可在本机演练；这些仅验证模拟交互，不代表新治理规则完成或正式服务验收。

## 逐组件定义

### 航线配置诊断 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:1。
- 绑定/动作：openRouteDiagnosis；类型：a-button。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：isGds；选项来源：原组件显示。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:2。
- 绑定/动作：preset；类型：a-segmented。
- 用途：昨日、近7个完整日、本月至昨日或自定义；选择后更新日期范围。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：periodOptions。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:3。
- 绑定/动作：draft.startDate；类型：a-date-picker。
- 用途：统计起始日期，使用完整业务日，和结束日期组成查询快照。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:4。
- 绑定/动作：draft.endDate；类型：a-date-picker。
- 用途：统计结束日期，现有组件默认截至昨日；不把不完整今日当完整日。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 平台 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:5。
- 绑定/动作：draft.platform；类型：a-select。
- 用途：业务平台筛选，不与GDS供应资源层混淆。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：selectOptions(data?.options.platform)。

### 站点 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:6。
- 绑定/动作：draft.site；类型：a-select。
- 用途：平台细分站点；下钻时继承已选平台及其他条件。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：selectOptions(data?.options.site)。

### GDS · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:7。
- 绑定/动作：draft.gds；类型：a-select。
- 用途：GDS资源，如1A/1G；阈值按各GDS分别确认，不能直接共用一个正式阈值。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：draft.dataSource === 'gds'；选项来源：selectOptions(data?.options.gds)。

### PCC · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:8。
- 绑定/动作：draft.pcc；类型：a-select。
- 用途：办公号，和GDS、平台、站点组合定位资源消耗。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：draft.dataSource === 'gds'；选项来源：selectOptions(data?.options.pcc)。

### 资源通道 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:9。
- 绑定/动作：draft.resourceChannel；类型：a-select。
- 用途：MP与MPIS资源通道。现行GDS查定比分子不含MPIS、包含NDC；MPIS只观察请求占比和质量。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：draft.dataSource === 'gds'；选项来源：resourceChannelOptions。

### 接口分组 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:10。
- 绑定/动作：draft.apiGroup；类型：a-select。
- 用途：具体接口组，区分普通、MPIS、NDC；选项受资源通道约束。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：apiGroupOptions。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:11。
- 绑定/动作：draft.breachOnly；类型：a-switch。
- 用途：只展示当前目标下超标的对象；未配置目标不等于达标。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 重置 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:12。
- 绑定/动作：resetFilters；类型：a-button。
- 用途：重置属于原资源治理组件ResourceGovernancePage的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 导出汇报 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:13。
- 绑定/动作：exportReport；类型：a-button。
- 用途：按当前已查询的资源或航线范围生成演示导出。
- 条件：当前条件与最近查询一致，不把页面Top结果当真实全量。
- 结果：加入页头模拟导出抽屉，下载本机CSV；不向真实任务队列写入。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查询 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:14。
- 绑定/动作：applyFilters；类型：a-button。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 不适用下钻接口组 · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:15。
- 绑定/动作：内容区；类型：a-table。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：isGds；选项来源：原组件显示。

### 下钻接口组 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:16。
- 绑定/动作：openResourceChannelAnalysis(record)；类型：a-button。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：isGds；选项来源：原组件显示。

### 接口分组分析此项 · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:17。
- 绑定/动作：内容区；类型：a-table。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：isGds && applied.resourceChannel；选项来源：原组件显示。

### 分析此项 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:18。
- 绑定/动作：openApiGroupAnalysis(record)；类型：a-button。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：isGds && applied.resourceChannel；选项来源：原组件显示。

### 统计图表 · chart
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:19。
- 绑定/动作：trendOption；类型：BaseChart。
- 用途：展示当前已应用范围的请求、质量、资源通道或趋势。GDS查定比按非MPIS查询量（含NDC）÷出票航段重算；不能对日比率简单取平均。
- 条件：先检查已应用日期/筛选、分母完整性和目标来源。全部数字为合成样例。
- 结果：图表交互只查看当前样例分布，不能据此认定真实治理效果或人员绩效。
- 原显示条件：data?.available && data.trend.length；选项来源：原组件显示。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:20。
- 绑定/动作：draftGroup；类型：a-segmented。
- 用途：选择要分析的维度；不会清除其他已应用条件。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：dimensionOptions。

### 分析此项 · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:21。
- 绑定/动作：内容区；类型：a-table。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 分析此项 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:22。
- 绑定/动作：openAnalysis(record)；类型：a-button。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 导出航线名单 按当前条件查看航线返回上一级 至 查询量航段数查定比超额查询查询成功验价成功生单成功继续定位问题维度当前条件会一直保留，选择下一层维度继续下钻已到当前汇总表最细维度 / / / 查询请求量查询成功率验价成功率生单成功率 → / / 继续分析当前展示 个航线组合进入完整航线诊断 · layer
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:23。
- 绑定/动作：drawerOpen；类型：a-drawer。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 导出航线名单 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:24。
- 绑定/动作：exportAnalysisRoutes；类型：a-button。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：analysisScope.dataSource === 'gds'；选项来源：原组件显示。

### 按当前条件查看航线 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:25。
- 绑定/动作：openAnalysisRoutes()；类型：a-button。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：analysisScope.dataSource === 'gds'；选项来源：原组件显示。

### 返回上一级 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:26。
- 绑定/动作：backAnalysis；类型：a-button。
- 用途：返回上一级属于原资源治理组件ResourceGovernancePage的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：analysisHistory.length > 1；选项来源：原组件显示。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:27。
- 绑定/动作：analysisView；类型：a-segmented。
- 用途：在同一个分析抽屉切换定位问题、日汇总或航线分析，不自动执行生产治理。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：analysisViewOptions。

### 字段 · field
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:28。
- 绑定/动作：analysisGroup；类型：a-segmented。
- 用途：分析抽屉中的下一层维度，继承当前日期、资源及对象条件。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：analysisView === 'dimension'；analysisDimensionOptions.length；选项来源：analysisDimensionOptions。

### 数据表 · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:29。
- 绑定/动作：内容区；类型：a-table。
- 用途：数据表展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：analysisView === 'dimension'；选项来源：原组件显示。

### 操作 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:30。
- 绑定/动作：hasNextAnalysisDimension ? continueAnalysis(record) : openAnalysisRoutes(record)；类型：a-button。
- 用途：操作属于原资源治理组件ResourceGovernancePage的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：analysisView === 'dimension'；选项来源：原组件显示。

### / / / · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:31。
- 绑定/动作：内容区；类型：a-table。
- 用途：/ / /展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### → / / 继续分析 · table
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:32。
- 绑定/动作：内容区；类型：a-table。
- 用途：→ / / 继续分析展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 继续分析 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:33。
- 绑定/动作：openAnalysisRoute(record)；类型：a-button。
- 用途：继续分析属于原资源治理组件ResourceGovernancePage的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 进入完整航线诊断 · action
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue；定位：RG01:ResourceGovernancePage:34。
- 绑定/动作：openAnalysisRoutes()；类型：a-button。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 返回GDS总览 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:1。
- 绑定/动作：router.push('/resource-governance/gds')；类型：a-button。
- 用途：返回GDS总览属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：isLiveRouteView；选项来源：原组件显示。

### 重置演示 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:2。
- 绑定/动作：resetDemo；类型：a-button。
- 用途：重置演示属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：!isLiveRouteView；选项来源：原组件显示。

### 操作 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:3。
- 绑定/动作：router.push(item.path)；类型：button。
- 用途：操作属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 字段 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:4。
- 绑定/动作：diagnosisView；类型：a-segmented。
- 用途：航线视图与配置视图切换；航线沿用日请求量和质量指标，不能计算缺分母的航线查定比。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：page === 'routes'；选项来源：[{ label: '航线视图', value: 'route' }, { label: '配置视图', value: 'configuration' }]。

### 字段 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:5。
- 绑定/动作：executionTab；类型：a-segmented。
- 用途：切换异常处置或上下线任务。当前只是原组件的本机演示状态链。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：page === 'execution'；选项来源：[{ label: '异常处置', value: 'events' }, { label: '上下线任务', value: 'actions' }]。

### 操作 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:6。
- 绑定/动作：router.push(step.path)；类型：button。
- 用途：操作属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：page === 'overview'；选项来源：原组件显示。

### 查看全部 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:7。
- 绑定/动作：router.push('/gds-route-governance/routes')；类型：a-button。
- 用途：查看全部属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：page === 'overview'；选项来源：原组件显示。

### · / · : 1目标 ≤ 4,000 : 1 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:8。
- 绑定/动作：openRoute(item)；类型：button。
- 用途：· / · : 1目标 ≤ 4,000 : 1属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：page === 'overview'；选项来源：原组件显示。

### 进入处置台 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:9。
- 绑定/动作：router.push('/gds-route-governance/events')；类型：a-button。
- 用途：进入处置台属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：page === 'overview'；选项来源：原组件显示。

### 前往GDS资源治理 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:10。
- 绑定/动作：router.push('/resource-governance/gds')；类型：a-button。
- 用途：前往GDS资源治理属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；!hasAnalysisEntry；选项来源：原组件显示。

### 统计日期（完整业务日） · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:11。
- 绑定/动作：dateRange；类型：a-range-picker。
- 用途：航线查询的起止日期；沿用上游分析范围，修改后需重新查询。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### GDS · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:12。
- 绑定/动作：filters.gds；类型：a-select。
- 用途：GDS资源，如1A/1G；阈值按各GDS分别确认，不能直接共用一个正式阈值。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：gdsOptions。

### PCC · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:13。
- 绑定/动作：filters.pcc；类型：a-select。
- 用途：办公号，和GDS、平台、站点组合定位资源消耗。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：pccOptions。

### 平台 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:14。
- 绑定/动作：filters.platform；类型：a-select。
- 用途：业务平台筛选，不与GDS供应资源层混淆。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：platformOptions。

### 站点 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:15。
- 绑定/动作：filters.site；类型：a-select。
- 用途：平台细分站点；下钻时继承已选平台及其他条件。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：siteOptions。

### 资源通道 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:16。
- 绑定/动作：filters.resourceChannel；类型：a-select。
- 用途：MP与MPIS资源通道。现行GDS查定比分子不含MPIS、包含NDC；MPIS只观察请求占比和质量。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：resourceChannelOptions。

### 接口分组 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:17。
- 绑定/动作：filters.apiGroup；类型：a-select。
- 用途：具体接口组，区分普通、MPIS、NDC；选项受资源通道约束。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：apiGroupOptions。

### 航线 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:18。
- 绑定/动作：filters.route；类型：a-input。
- 用途：航线筛选，来自上游分析条件或当前选定航线。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 出发城市 / 到达城市 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:19。
- 绑定/动作：filters.keyword；类型：a-input。
- 用途：航线或对象关键字，点击查询才更新当前结果范围。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 查询 / 刷新 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:20。
- 绑定/动作：loadRouteAnalysis；类型：a-button。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 导出航线名单 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:21。
- 绑定/动作：exportRoutes；类型：a-button。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### → 成功 · 失败 成功 · 失败 成功 · 失败 / / 分析此项 · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:22。
- 绑定/动作：内容区；类型：a-table。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 航线 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:23。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### → · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:24。
- 绑定/动作：openLiveRoute(record)；类型：button。
- 用途：→属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 平台 / 站点 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:25。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：平台 / 站点展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### GDS / PCC · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:26。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：GDS / PCC展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 查询阶段 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:27。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 验价阶段 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:28。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：验价阶段展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 生单阶段 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:29。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：生单阶段展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 普通MP / MPIS / NDC · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:30。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：普通MP / MPIS / NDC展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 结果成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:31。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：结果成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 查询超时率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:32。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 平均查询耗时 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:33。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 验价 / 生单变价率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:34。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：验价 / 生单变价率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 操作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:35。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：操作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 分析此项 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:36。
- 绑定/动作：openLiveRoute(record)；类型：a-button。
- 用途：把当前对象及全部适用筛选带入原分析抽屉，逐层定位问题。
- 条件：当前查询已完成且对象粒度可明确；组合行需要完整GDS/PCC/平台/站点。
- 结果：打开或更新当前抽屉，可继续维度分析、日汇总或航线分析；返回保留分析路径，不连接生产。
- 原显示条件：diagnosisView === 'route'；选项来源：原组件显示。

### 全部只看异常 · field
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:37。
- 绑定/动作：configView；类型：a-radio-group。
- 用途：全部只看异常限定当前资源治理查询或本机演示对象的范围。
- 条件：按当前页面显示条件填写；日期/范围变化后须查询，不沿用过期结果。
- 结果：保留当前上下文，在查询或保存时应用；不会触发真实订单请求、白名单或技术系统操作。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### · 停留 : 1% · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:38。
- 绑定/动作：内容区；类型：a-table。
- 用途：· 停留 : 1%展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 配置 / 航线 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:39。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 乘客 / 行程 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:40。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：乘客 / 行程展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 去程 / 回程 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:41。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：去程 / 回程展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 通道 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:42。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：通道展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查询量 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:43。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 航段数 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:44。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：航段数展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查定比 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:45。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：查定比展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:46。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 建议动作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:47。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：建议动作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 结论 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:48。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：结论展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### %%%% · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:49。
- 绑定/动作：内容区；类型：a-table。
- 用途：%%%%展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### GDS / PCC · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:50。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：GDS / PCC展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 接口组 / 平台 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:51。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：接口组 / 平台展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查询量 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:52。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查询成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:53。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 验价成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:54。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：验价成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 生单成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:55。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：生单成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 超时率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:56。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：超时率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 主要失败原因 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:57。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：主要失败原因展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 状态 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:58。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：状态展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 至 · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:59。
- 绑定/动作：内容区；类型：a-table。
- 用途：至展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 白名单ID · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:60。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：白名单ID展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 航线 / 航司 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:61。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 平台 / 站点 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:62。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：平台 / 站点展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### GDS / PCC · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:63。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：GDS / PCC展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 开放通道 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:64。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：开放通道展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 配置数 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:65。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：配置数展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 有效期 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:66。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：有效期展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 版本 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:67。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：版本展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 状态 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:68。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：状态展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### · 要求 确认观察生成任务查看任务 · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:69。
- 绑定/动作：内容区；类型：a-table。
- 用途：演示原有异常→确认/观察→任务→接单/执行→恢复→复盘的人工状态链。
- 条件：仅原组件当前状态允许时可用；这里没有接入技术系统、真实白名单版本或执行凭据。
- 结果：只修改独立本机演示缓存，不代表已下线、恢复、发送通知或改善真实指标。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 等级 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:70。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：等级展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 异常 / 对象 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:71。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：异常 / 对象展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 实际 / 阈值 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:72。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：实际 / 阈值展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 命中证据 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:73。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：命中证据展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 责任人 / 截止 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:74。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：责任人 / 截止展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 白名单版本 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:75。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：白名单版本展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 状态 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:76。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：状态展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 操作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:77。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：操作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 确认 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:78。
- 绑定/动作：acknowledge(record.id)；类型：a-button。
- 用途：演示原有异常→确认/观察→任务→接单/执行→恢复→复盘的人工状态链。
- 条件：仅原组件当前状态允许时可用；这里没有接入技术系统、真实白名单版本或执行凭据。
- 结果：只修改独立本机演示缓存，不代表已下线、恢复、发送通知或改善真实指标。
- 原显示条件：record.status === 'OPEN'；选项来源：原组件显示。

### 观察 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:79。
- 绑定/动作：observe(record.id)；类型：a-button。
- 用途：演示原有异常→确认/观察→任务→接单/执行→恢复→复盘的人工状态链。
- 条件：仅原组件当前状态允许时可用；这里没有接入技术系统、真实白名单版本或执行凭据。
- 结果：只修改独立本机演示缓存，不代表已下线、恢复、发送通知或改善真实指标。
- 原显示条件：['OPEN','ACKNOWLEDGED'].includes(record.status)；选项来源：原组件显示。

### 生成任务 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:80。
- 绑定/动作：createAction(record.id)；类型：a-button。
- 用途：生成任务属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：['ACKNOWLEDGED','OBSERVING'].includes(record.status)；选项来源：原组件显示。

### 查看任务 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:81。
- 绑定/动作：executionTab = 'actions'；类型：a-button。
- 用途：查看任务属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：record.status === 'ACTION_PENDING'；选项来源：原组件显示。

### · 来源 第 次 已闭环 · table
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:82。
- 绑定/动作：内容区；类型：a-table。
- 用途：· 来源 第 次 已闭环展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 任务编号 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:83。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：任务编号展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 治理对象 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:84。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：治理对象展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 动作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:85。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：动作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 控制窗口 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:86。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：控制窗口展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 技术负责人 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:87。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：技术负责人展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 回执 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:88。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：回执展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 状态 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:89。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：状态展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 操作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:90。
- 绑定/动作：内容区；类型：a-table-column。
- 用途：操作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 操作 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:91。
- 绑定/动作：advanceAction(record.id)；类型：a-button。
- 用途：操作属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：record.status !== 'RECOVERED'；选项来源：原组件显示。

### 航线诊断 · layer
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:92。
- 绑定/动作：routeDrawerOpen；类型：a-drawer。
- 用途：在已有GDS范围下观察航线查询、验价、生单质量，再识别配置组合。
- 条件：原组件要求从GDS“分析此项”带入entry与完整条件；直接打开航线页不自动查大表。
- 结果：本机样例代替Hive返回；缺少航线出票航段分母，禁止据此生成航线查定比。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 展示字段 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:93。
- 绑定/动作：内容区；类型：a-descriptions。
- 用途：展示字段展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 查询接口成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:94。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 查询结果成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:95。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 验价成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:96。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：验价成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 生单成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:97。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：生单成功率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 查询超时率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:98。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 查询缓存率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:99。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 查询失败量 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:100。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 验价失败量 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:101。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：验价失败量展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 生单失败量 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:102。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：生单失败量展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 验价超时率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:103。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：验价超时率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 生单超时率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:104。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：生单超时率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 验价变价率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:105。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：验价变价率展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 直飞方案数 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:106。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：直飞方案数展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 中转方案数 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:107。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：中转方案数展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 最近源数据 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:108。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：最近源数据展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 关闭 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:109。
- 绑定/动作：routeDrawerOpen = false；类型：a-button。
- 用途：关闭属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### 配置分析待接入 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:110。
- 绑定/动作：内容区；类型：a-button。
- 用途：配置分析待接入属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：selectedLiveRoute；选项来源：原组件显示。

### %%% · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:111。
- 绑定/动作：内容区；类型：a-descriptions。
- 用途：%%%展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 白名单 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:112。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：白名单展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 查询成功率 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:113。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：将当前草稿日期和维度条件作为新查询快照。
- 条件：起止日期有效，样例范围最多90天；OTA和GDS保持分层。
- 结果：刷新当前图表和表格，本机没有匹配样例时显示空态，不请求数据库。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### MP占比 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:114。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：MP占比展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### MPIS占比 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:115。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：MPIS占比展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 建议动作 · display
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:116。
- 绑定/动作：内容区；类型：a-descriptions-item。
- 用途：建议动作展示当前范围的资源指标或演示对象；缺数、未配置和0需分别解释。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 关闭 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:117。
- 绑定/动作：routeDrawerOpen = false；类型：a-button。
- 用途：关闭属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。

### 进入配置分析 · action
- 组件：frontend/src/views/GdsRouteGovernanceView.vue；定位：RG01:GdsRouteGovernanceView:118。
- 绑定/动作：openConfigurationView；类型：a-button。
- 用途：进入配置分析属于原资源治理组件GdsRouteGovernanceView的交互或内容区域。
- 条件：保留原组件权限/状态/条件展示，当前全部是演示基线；新规则尚未实现，来源及待确认项见设计链路。
- 结果：按原组件在页面或图层内联动；不调用真实MySQL/Hive、上下线、企微或调度。
- 原显示条件：当前区域打开；选项来源：原组件显示。
