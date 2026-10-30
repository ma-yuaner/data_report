# 资源治理评审固定入口

2026-10-29：现有前端已接入，新增GDS需求已整理为设计基线1.0，关键业务口径待讨论。不自动恢复暂存F01—F08，不启动后端、ETL、DDL、调度、真实治理或部署。

- [原型0.2与组件PRD](prototype-prd-v02.md)：复用原AppLayout布局、场景切换及按需联动PRD。
- [后续固定规则V1](../../../business/air_ticketing/gds-mpis-governance-rules.md)：用户2026-10-30确认，后续分析/SQL/PRD/原型/开发先读；未决技术含义仍需核实。
- [需求与设计基线1.0](design-baseline-v1.md)：6项需求、26个已有/候选字段、3个已有接口及数据表证据/缺口。
- [白名单、分流与MPIS容量分析V1](mpis-analysis-baseline-v1.md)：2026-10-30离线核对；7542条全局航线、600万cells及容量分配方案，未修改线上配置。
- [历史现状基线与组件PRD0.1](prototype-prd-v01.md)：六个原菜单入口、原页面与动态图层；点击组件联动说明。
- [既有复评与口径](../../gds-resource-governance-reassessment-v3.md)：区分真实能力、旧演示与未决方案；不能从模拟状态推出生产执行或效果。
- 原页面：`frontend/src/features/resource-governance`、`frontend/src/views/GdsRouteGovernanceView.vue`；正式源文件不改。
- 本机数据/字段含义：`frontend/prototypes/resource-review`。原型共用ADM已建的组件标注、菜单、图层和PRD外壳；门户资源治理指向独立的资源治理HTML，默认打开GDS。
- 后续新需求收到后，按来源、场景、字段/指标、交互、状态、权限及新旧差异整理，再调整这份原型；方案与正式实现授权分开。

- 维护源：`frontend/prototypes/design-review/registry.json`；执行原打包命令时自动核对编号引用并生成设计文档、工作台数据与接口评审摘录。字段与表设计状态明确，不把候选字段视为已新增列。
