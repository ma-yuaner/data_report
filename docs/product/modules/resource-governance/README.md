# 资源治理评审固定入口

2026-10-29：先接入现有前端作为演示与PRD基线，等待用户新的需求。不自动恢复暂存F01—F08，不启动后端、ETL、DDL、调度、真实治理或部署。

- [现状基线与组件PRD0.1](prototype-prd-v01.md)：六个原菜单入口、原页面与动态图层；点击组件联动说明。
- [既有复评与口径](../../gds-resource-governance-reassessment-v3.md)：区分真实能力、旧演示与未决方案；不能从模拟状态推出生产执行或效果。
- 原页面：`frontend/src/features/resource-governance`、`frontend/src/views/GdsRouteGovernanceView.vue`；正式源文件不改。
- 本机数据/字段含义：`frontend/prototypes/resource-review`。原型共用ADM已建的组件标注、菜单、图层和PRD外壳；门户资源治理指向独立的资源治理HTML，默认打开GDS。
- 后续新需求收到后，按来源、场景、字段/指标、交互、状态、权限及新旧差异整理，再调整这份原型；方案与正式实现授权分开。
