# GDS资源治理需求与设计基线 1.0

更新：2026-10-29。评审框架已实现；新治理规则处于需求讨论，不执行DDL、ETL、生产上下线或真实通知。

单一维护源：frontend/prototypes/design-review/registry.json。此文档与评审索引由同一来源生成。已有组件定义只是操作定位，不作为新需求完成证据。

## 需求来源

<a id="src-user-1029"></a>
### SRC-USER-1029 · 2026-10-29用户GDS治理需求

- 分类：用户原始输入
- 内容：降低公司查询量；区分用户配置的平台白名单、我司全局白名单及平台自己的白名单；平台仍发送范围外查询需要反馈；核对MPIS配置与实际通道；关注有查询无验价/生单；逐步减少内部宽泛始发地/目的地配置形成的无效航线；识别突破白名单的验价。先讨论行为和数据口径，再确定上下线规则。
- 证据：本会话用户需求原文摘要；保留目标，不代表优先级、阈值及执行方案已确认。

<a id="src-code"></a>
### SRC-CODE · 现有页面、接口与服务代码

- 分类：代码证据
- 内容：现有GDS/OTA汇总、维度分析、航线查询与本地治理演示。代码存在不代表部署、数据就绪或业务验收。
- 证据：frontend/src/features/resource-governance/api.ts；backend/data_report_api/api/resource_governance.py

<a id="src-baseline"></a>
### SRC-BASELINE · 既有闭环复评V3

- 分类：既有设计基线
- 内容：查定比Q/S、MPIS占比、真实数据与演示边界；既有F01—F08不因本轮框架开发自动恢复。
- 证据：docs/product/gds-resource-governance-reassessment-v3.md

## 需求与实现状态

<a id="gds-req-001"></a>
### GDS-REQ-001 · 现有资源数据查看与下钻

- 需求来源：SRC-CODE
- 页面：PG-GDS；PG-OTA；PG-ROUTE
- 规则：RULE-QS；RULE-ROUTE
- 接口：API-GDS；API-OTA；API-ROUTES
- 数据表：TBL-GDS；TBL-OTA；TBL-ROUTE
- 状态：现有前端复用；本机模拟
- 用途：保留日期/维度筛选、分析抽屉、日汇总与航线分析。
- 缺口与待确认：已有日聚合不能证明逐请求白名单命中、分流和转化链路。
- 实现：仅现状模拟
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

<a id="gds-req-002"></a>
### GDS-REQ-002 · 分层白名单与平台范围外查询

- 需求来源：SRC-USER-1029
- 页面：PG-WHITE；PG-GDS
- 规则：RULE-WHITE
- 接口：
- 数据表：TBL-GAP
- 状态：需求已登记；口径待确认
- 用途：区分外部平台发送行为与内部放行行为，提供可向平台反馈的范围外请求证据。
- 缺口与待确认：三层配置归属、组合优先级、作用阶段、生效版本及平台反馈方式待确认；无法直接获知平台自身配置。
- 实现：新规则未实现
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

<a id="gds-req-003"></a>
### GDS-REQ-003 · MPIS应走通道与实际通道校验

- 需求来源：SRC-USER-1029
- 页面：PG-GDS；PG-ROUTE
- 规则：RULE-CHANNEL
- 接口：
- 数据表：TBL-GAP
- 状态：需求已登记；口径待确认
- 用途：核对符合MPIS配置的请求，识别实际走MP或未调用资源的情况。
- 缺口与待确认：请求日志、有效配置快照、预期路由及允许回退原因缺少核验；不能把所有MP回退当故障。
- 实现：新规则未实现
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

<a id="gds-req-004"></a>
### GDS-REQ-004 · 有查询无验价或生单

- 需求来源：SRC-USER-1029
- 页面：PG-GDS；PG-ROUTE
- 规则：RULE-CONVERSION
- 接口：API-GDS；API-ROUTES
- 数据表：TBL-GDS；TBL-ROUTE；TBL-GAP
- 状态：需求已登记；关联口径待确认
- 用途：区分查询、验价、生单行为，观察持续查询没有后续行为的范围。
- 缺口与待确认：关联键、去重、统计对象、观察窗口、流量门槛及缺失数据处理待定；日级零值不能证明单次查询无转化。
- 实现：新规则未实现
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

<a id="gds-req-005"></a>
### GDS-REQ-005 · 宽泛配置与低效航线收敛

- 需求来源：SRC-USER-1029
- 页面：PG-ROUTE；PG-EXEC；PG-REVIEW
- 规则：RULE-CONFIG
- 接口：API-ROUTES
- 数据表：TBL-ROUTE；TBL-GAP
- 状态：需求已登记；调整规则待确认
- 用途：将航线流量和效果追溯到业务配置，讨论逐步减少无效范围。
- 缺口与待确认：配置展开方式、归属ID、效果定义、最小样本、保留例外、审批和恢复条件待定。
- 实现：新规则未实现
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

<a id="gds-req-006"></a>
### GDS-REQ-006 · 识别验价突破白名单

- 需求来源：SRC-USER-1029
- 页面：PG-WHITE；PG-ROUTE
- 规则：RULE-WHITE
- 接口：
- 数据表：TBL-GAP
- 状态：需求已登记；验价适用规则待确认
- 用途：识别验价发生时未命中适用白名单的请求，并解释是否允许例外。
- 缺口与待确认：验价是否复用查询白名单、历史缓存/订单触发例外、当时版本和命中日志待确认。
- 实现：新规则未实现
- 部署：未部署本轮变更
- 验收：待用户确认口径并操作评审
- 负责人：业务确认人/数据负责人待指定

## 业务规则与未决问题

<a id="rule-qs"></a>
### RULE-QS · GDS查定比与MPIS占比

- 状态：既有口径
- 说明：Q为非MPIS查询（含NDC），S为出票航段；汇总按SUM(Q)/SUM(S)，MPIS占比为MPIS/全部查询。缺分母不计算。
- 待确认：真实分母完整性、目标版本及具体来源仍需数据核验。

<a id="rule-route"></a>
### RULE-ROUTE · 航线没有分母时不计算查定比

- 状态：既有边界
- 说明：航线查询使用请求/验价/生单质量；现有航线API不提供出票航段分母。
- 待确认：不以平台或PCC总航段替代航线分母。

<a id="rule-white"></a>
### RULE-WHITE · 三层白名单与验价范围

- 状态：待确认
- 说明：分别记录外部平台发送、内部接收、规则判断、放行或拦截。
- 待确认：各层组合方式、阶段、生效时间、例外及版本如何确定？

<a id="rule-channel"></a>
### RULE-CHANNEL · 预期与实际资源通道

- 状态：待确认
- 说明：预期MP/MPIS与实际调用分别表达，并保存分流或回退原因。
- 待确认：何种配置要求MPIS？哪些情况允许回退MP？没有实际调用如何分类？

<a id="rule-conversion"></a>
### RULE-CONVERSION · 查询、验价、生单关联

- 状态：待确认
- 说明：分别计量三类行为，再按确认的关联方式判断后续行为。
- 待确认：使用请求链、会话、订单还是航线日聚合？多次重试和观察窗口如何处理？

<a id="rule-config"></a>
### RULE-CONFIG · 宽泛配置收敛与上下线

- 状态：待确认
- 说明：建议调整应关联到具体配置、范围、证据及可恢复方案。
- 待确认：何谓无效？谁确认？缩减与恢复窗口、护栏和执行回执如何约定？

## 原型索引与模块对应

<a id="pg-gds"></a>
### PG-GDS · GDS资源治理

- 路由：/resource-governance/gds
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

<a id="pg-ota"></a>
### PG-OTA · OTA渠道质量

- 路由：/resource-governance/ota
- 组件：frontend/src/features/resource-governance/ResourceGovernancePage.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

<a id="pg-route"></a>
### PG-ROUTE · 航线配置诊断

- 路由：/resource-governance/route-diagnosis
- 组件：frontend/src/views/GdsRouteGovernanceView.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

<a id="pg-white"></a>
### PG-WHITE · 白名单管理

- 路由：/resource-governance/whitelist
- 组件：frontend/src/views/GdsRouteGovernanceView.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

<a id="pg-exec"></a>
### PG-EXEC · 治理执行

- 路由：/resource-governance/execution
- 组件：frontend/src/views/GdsRouteGovernanceView.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

<a id="pg-review"></a>
### PG-REVIEW · 治理复盘

- 路由：/resource-governance/review
- 组件：frontend/src/views/GdsRouteGovernanceView.vue
- 状态：原页面已接入模拟评审，正式部署与验收未核验

## 字段与数据口径

<a id="fld-001"></a>
### FLD-001 · 开始日期

- 字段标识：startDate
- 类型：string(date)
- 状态：已有前端契约
- 用途：查询范围起点，按业务日期，不等同请求事件时间。
- 接口字段：query.startDate
- 存储映射：服务解析的期间；时区以正式契约核验
- 关联需求：GDS-REQ-001

<a id="fld-002"></a>
### FLD-002 · 结束日期

- 字段标识：endDate
- 类型：string(date)
- 状态：已有前端契约
- 用途：查询范围终点；原页面默认昨日，不假定当天数据完整。
- 接口字段：query.endDate
- 存储映射：服务解析的期间
- 关联需求：GDS-REQ-001

<a id="fld-003"></a>
### FLD-003 · 平台

- 字段标识：platform
- 类型：string
- 状态：已有前端契约
- 用途：请求所属平台，与站点共同限定范围。
- 接口字段：query.platform / filters.platform
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-004"></a>
### FLD-004 · 站点

- 字段标识：site
- 类型：string
- 状态：已有前端契约
- 用途：平台下的站点归属，不等于用户配置主体。
- 接口字段：query.site / filters.site
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-005"></a>
### FLD-005 · GDS

- 字段标识：gds
- 类型：string
- 状态：已有前端契约
- 用途：资源系统代码；不等同MP/MPIS通道。
- 接口字段：query.gds
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-006"></a>
### FLD-006 · PCC

- 字段标识：pcc
- 类型：string
- 状态：已有前端契约
- 用途：资源账户范围，和平台/站点组合分析。
- 接口字段：query.pcc
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-007"></a>
### FLD-007 · 资源通道

- 字段标识：resourceChannel
- 类型：enum(MP,MPIS)
- 状态：已有前端契约
- 用途：当前实际资源通道统计维度，不能证明配置本应走哪条。
- 接口字段：query.resourceChannel
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-008"></a>
### FLD-008 · 接口组

- 字段标识：apiGroup
- 类型：string
- 状态：已有前端契约
- 用途：区分接口来源，NDC仍纳入非MPIS查询口径。
- 接口字段：query.apiGroup
- 存储映射：已聚合维度
- 关联需求：GDS-REQ-001

<a id="fld-009"></a>
### FLD-009 · 查询量

- 字段标识：searchRequests
- 类型：integer
- 状态：已有前端契约
- 用途：现有GDS经营范围与接口组范围口径不同，结合ratioApplicable看待；不能冒充OTA入口原始请求量。
- 接口字段：summary.searchRequests
- 存储映射：既有聚合服务计算字段
- 关联需求：GDS-REQ-001；GDS-REQ-004

<a id="fld-010"></a>
### FLD-010 · 验价量

- 字段标识：verifyRequests
- 类型：integer
- 状态：已有前端契约
- 用途：验价阶段请求量；不等同有多少查询产生验价。
- 接口字段：summary.verifyRequests
- 存储映射：既有聚合服务计算字段
- 关联需求：GDS-REQ-001；GDS-REQ-004

<a id="fld-011"></a>
### FLD-011 · 生单请求量

- 字段标识：orderRequests
- 类型：integer
- 状态：已有前端契约
- 用途：生单阶段请求量，不等同已支付或已出票订单数。
- 接口字段：summary.orderRequests
- 存储映射：既有聚合服务计算字段
- 关联需求：GDS-REQ-001；GDS-REQ-004

<a id="fld-012"></a>
### FLD-012 · 出票航段

- 字段标识：segmentCount
- 类型：integer|null
- 状态：已有前端契约
- 用途：查定比分母；NULL表示缺失或不适用，不补为0。
- 接口字段：summary.segmentCount
- 存储映射：GDS日指标；航线API无此字段
- 关联需求：GDS-REQ-001

<a id="fld-013"></a>
### FLD-013 · 查定比

- 字段标识：queryToSegmentRatio
- 类型：decimal-string|null
- 状态：已有前端契约
- 用途：Q/S，按汇总分子分母重算；缺失/部分同步时不输出结论。
- 接口字段：summary.queryToSegmentRatio
- 存储映射：服务计算，无需新增页面同名表列
- 关联需求：GDS-REQ-001

<a id="fld-014"></a>
### FLD-014 · 航线

- 字段标识：route
- 类型：string
- 状态：已有前端契约
- 用途：现有航线维度，不假定已经与内部配置ID关联。
- 接口字段：query.route / rows.route
- 存储映射：Hive航线日汇总
- 关联需求：GDS-REQ-001

<a id="fld-101"></a>
### FLD-101 · 请求关联标识

- 字段标识：requestTraceId
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：关联入口、规则判断和实际调用；重试与去重规则待定。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-002；GDS-REQ-003；GDS-REQ-004；GDS-REQ-006

<a id="fld-102"></a>
### FLD-102 · 行为阶段

- 字段标识：requestStage
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：明确查询/验价/生单；不能靠接口名猜测行为。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-004；GDS-REQ-006

<a id="fld-103"></a>
### FLD-103 · 生效配置版本

- 字段标识：configVersion
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：回溯请求发生时的白名单及路由配置。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-002；GDS-REQ-003；GDS-REQ-006

<a id="fld-104"></a>
### FLD-104 · 白名单层级

- 字段标识：whitelistLayer
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：区分用户平台配置、内部全局和外部平台；外部配置可能不可获取。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-002；GDS-REQ-006

<a id="fld-105"></a>
### FLD-105 · 命中与放行结果

- 字段标识：whitelistDecision
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：分别表达命中、拦截、放行和例外，不简单用一个是否违规字段替代。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-002；GDS-REQ-006

<a id="fld-106"></a>
### FLD-106 · 预期通道

- 字段标识：expectedChannel
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：按生效配置与确认规则推导；尚无可用数据来源证明。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-003

<a id="fld-107"></a>
### FLD-107 · 实际通道

- 字段标识：actualChannel
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：实际MP/MPIS及未调用，需请求级证据；不拿聚合通道反推单请求。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-003

<a id="fld-108"></a>
### FLD-108 · 回退原因

- 字段标识：fallbackReason
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：解释应走MPIS却走MP，是否允许要按业务规则判断。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-003

<a id="fld-109"></a>
### FLD-109 · 内部配置标识

- 字段标识：configId
- 类型：待数据核对后确定
- 状态：候选数据需求，未新增表列
- 用途：连接始发地/目的地配置及展开航线范围。
- 接口字段：无已确认接口映射
- 存储映射：待核对日志、配置快照及关联键；不生成DDL
- 关联需求：GDS-REQ-005

<a id="fld-015"></a>
### FLD-015 · 分析维度

- 字段标识：groupBy
- 类型：string
- 状态：已有前端契约
- 用途：切换组合、平台、站点、GDS、PCC或接口组等聚合维度，不能把不同粒度直接拼接。
- 接口字段：query.groupBy
- 存储映射：查询参数；不是新增数据库列
- 关联需求：GDS-REQ-001

<a id="fld-016"></a>
### FLD-016 · 仅看超标

- 字段标识：breachOnly
- 类型：boolean
- 状态：已有前端契约
- 用途：按既有目标筛选；目标未确认、数据不完整或不适用时不能补出超标结论。
- 接口字段：query.breachOnly
- 存储映射：查询参数；不是新增数据库列
- 关联需求：GDS-REQ-001

<a id="fld-017"></a>
### FLD-017 · 航线关键字

- 字段标识：keyword
- 类型：string
- 状态：已有前端契约
- 用途：查询已限定范围中的航线或对象，不代替完整配置归属。
- 接口字段：query.keyword
- 存储映射：查询参数；不是新增数据库列
- 关联需求：GDS-REQ-001

## 接口契约

<a id="api-gds"></a>
### API-GDS · GDS日汇总

- 路径：/v1/resource-governance/gds/overview
- 方法：GET
- 状态：已有代码接口；本轮只模拟
- 请求：startDate/endDate；platform/site/gds/pcc/resourceChannel/apiGroup；overview增加groupBy/breachOnly；routes增加route/keyword
- 响应：ApiEnvelope；具体TS类型见frontend/src/features/resource-governance/api.ts
- 证据：backend/data_report_api/api/resource_governance.py
- 缺口与待确认：OpenAPI为评审契约摘录，不是服务端校验、鉴权或全量schema证明。
- 关联需求：GDS-REQ-001

<a id="api-ota"></a>
### API-OTA · OTA质量汇总

- 路径：/v1/resource-governance/ota/overview
- 方法：GET
- 状态：已有代码接口；本轮只模拟
- 请求：startDate/endDate；platform/site/gds/pcc/resourceChannel/apiGroup；overview增加groupBy/breachOnly；routes增加route/keyword
- 响应：ApiEnvelope；具体TS类型见frontend/src/features/resource-governance/api.ts
- 证据：backend/data_report_api/api/resource_governance.py
- 缺口与待确认：OpenAPI为评审契约摘录，不是服务端校验、鉴权或全量schema证明。
- 关联需求：GDS-REQ-001

<a id="api-routes"></a>
### API-ROUTES · 航线日汇总

- 路径：/v1/resource-governance/gds/routes
- 方法：GET
- 状态：已有代码接口；本轮只模拟
- 请求：startDate/endDate；platform/site/gds/pcc/resourceChannel/apiGroup；overview增加groupBy/breachOnly；routes增加route/keyword
- 响应：ApiEnvelope；具体TS类型见frontend/src/features/resource-governance/api.ts
- 证据：backend/data_report_api/api/resource_governance.py
- 缺口与待确认：OpenAPI为评审契约摘录，不是服务端校验、鉴权或全量schema证明。
- 关联需求：GDS-REQ-001

## 数据来源与表设计边界

<a id="tbl-gds"></a>
### TBL-GDS · bi_gds_resource_metric_day

- 粒度：日×资源/平台/站点等现有服务组合；准确唯一键待核对
- 状态：服务默认表名，未连接数据库核验
- 证据：backend/data_report_api/services/resource_governance.py: DEFAULT_GDS_METRIC_TABLE
- 缺口与待确认：数据库名可配置；真实字段/唯一键/完整性不能仅凭代码认定。
- 负责人：数据/业务负责人待指定
- 执行状态：本轮未执行DDL、ETL或查库

<a id="tbl-ota"></a>
### TBL-OTA · bi_ota_gds_request_day

- 粒度：现有OTA请求日聚合，准确键待核对
- 状态：服务引用表名，未核验实际库
- 证据：backend/data_report_api/services/resource_governance.py: REQUEST_TABLE_NAME
- 缺口与待确认：不能把调用资源的聚合量当作所有OTA入口请求量。
- 负责人：数据/业务负责人待指定
- 执行状态：本轮未执行DDL、ETL或查库

<a id="tbl-route"></a>
### TBL-ROUTE · dws_gds_airroute_day

- 粒度：航线请求日汇总，维度保留情况待核验
- 状态：Hive默认表名，可被配置覆盖
- 证据：backend/data_report_api/services/gds_route_analysis.py: GDS_ROUTE_HIVE_TABLE
- 缺口与待确认：不提供航线出票航段分母，也未证明配置归属ID可用。
- 负责人：数据/业务负责人待指定
- 执行状态：本轮未执行DDL、ETL或查库

<a id="tbl-gap"></a>
### TBL-GAP · 请求日志与生效配置快照（待盘点）

- 粒度：候选请求/配置版本粒度，未定
- 状态：数据缺口；未设计实体表名
- 证据：SRC-USER-1029
- 缺口与待确认：需核对日志/配置已有数据再确定复用、关联与存储；没有DDL和ETL实现。
- 负责人：数据/业务负责人待指定
- 执行状态：本轮未执行DDL、ETL或查库

## 演练场景

<a id="scn-normal"></a>
### SCN-NORMAL · 正常样例

- 操作步骤：进入GDS资源治理；调整日期/维度并查询；分析此项并查看下钻；导出当前范围
- 预期：当前筛选与样例、图层和PRD对应，导出本机文件。
- 适用范围：已有交互演练
- 状态：用户待操作，未业务验收

<a id="scn-empty"></a>
### SCN-EMPTY · 查询结果为零

- 操作步骤：选择“查询结果为零”；查看汇总与列表
- 预期：没有记录，不误报查询失败或超标；导出没有样例行。
- 适用范围：已有交互演练
- 状态：用户待操作，未业务验收

<a id="scn-partial"></a>
### SCN-PARTIAL · 航段同步不完整

- 操作步骤：选择“航段数据不完整”；查看查定比与维度榜
- 预期：请求量保留；分母/比率为空，不输出超标结论。
- 适用范围：GDS汇总演练，OTA及航线不适用
- 状态：用户待操作，未业务验收

<a id="scn-error"></a>
### SCN-ERROR · 查询失败及恢复

- 操作步骤：选择“查询失败与重试”；查看错误；切回正常样例
- 预期：失败显示原因，恢复后重新查询，不连接生产。
- 适用范围：已有交互演练
- 状态：用户待操作，未业务验收

<a id="scn-denied"></a>
### SCN-DENIED · 接口无查询权限

- 操作步骤：选择“无查询权限”；查看拒绝说明
- 预期：接口模拟拒绝；保留菜单不代表有权限读取数据。
- 适用范围：模拟权限，不是正式鉴权验收
- 状态：用户待操作，未业务验收

<a id="scn-discuss"></a>
### SCN-DISCUSS · 新治理业务讨论

- 操作步骤：逐项查看REQ-002至REQ-006；核对候选字段与数据来源；确认未决规则后再设计场景
- 预期：不预设阈值、观察窗口、白名单优先级或自动上下线。
- 适用范围：讨论提纲，尚无新规则可运行
- 状态：用户待操作，未业务验收
