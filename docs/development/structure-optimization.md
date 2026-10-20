# 项目结构优化

日期：2026-10-20。用户已授权按结构评估开展优化。范围为协作契约、工程门禁、HTTP领域拆分、共享依赖和前端资源治理试点；接口及业务口径保持兼容。ETL独立仓库、生产数据库与服务器部署不在本轮变更范围。

## 本轮交付与效果

| 项目 | 优化前 | 优化后 | 验收证据 |
|---|---|---|---|
| 角色与交接 | product/ui/frontend/backend/qa说明分散 | AGENTS.md明确五类角色输入、输出、完成标准及冲突处理 | 文档检查与交叉链接 |
| 工程入口 | 根README负责所有说明 | 前后端README、贡献指南、双仓说明提供各自入口 | 文件与链接检查 |
| HTTP适配 | routes.py集中约1286行、90条路由 | routes.py只负责注册，api下10个领域与公共响应模块 | 原路由快照校验路径、方法、端点名；现有HTTP测试 |
| 日期/权限共享 | 跨service引用私有函数，调用方依赖具体服务 | shared提供公共日期、权限表示和目标权限常量 | 区分两套日期默认值/范围限制的边界测试；权限回归 |
| 应用内任务 | service依赖根级命令入口 | 实现在jobs/，根级保留兼容命令入口 | 目标任务及手动刷新现有测试 |
| 前端资源治理 | 视图混合请求、图表、下钻、表格与展示工具 | features/resource-governance拆分API、页面、查询状态、下钻状态、图表、列定义及展示函数 | 类型/构建、6项组合状态与交互回归；旧API和视图保留入口 |
| 依赖规则 | 人工识别循环和越界依赖 | Python AST与TypeScript/Vue AST检查本地导入、循环、私有导入和层次边界 | 本地及GitHub/GitLab CI门禁 |
| 质量门禁 | 后端测试、前端类型/组件/构建 | 增加Ruff错误检查、ESLint、迁移目录格式检查及可选pre-commit | 双端CI执行同样检查 |

上述效果针对修改定位、交接和回归约束；查询性能没有作为本轮验收目标。其他大型service与页面仍按业务需求逐域拆分，避免无依据的大规模搬迁。

## 依赖检查的覆盖范围

Python检查源码中的显式本地import，frontend检查import/export及字面量动态import（包含类型依赖）。拒绝循环、service/jobs反向依赖HTTP/启动入口、shared依赖应用层、HTTP领域互相引用、frontend领域依赖旧兼容入口。运行时字符串拼接导入不在静态检查范围。

格式门禁覆盖Python新建的api/shared/jobs/scripts，前端资源治理领域和工程配置。存量目录先执行错误级lint，不做全仓格式化。版本化规则位于pyproject.toml、frontend/eslint.config.mjs和frontend/.prettierrc.json。

## 存量问题 STRUCT-001

接入错误级lint发现`services/monitoring.py`中`diagnose_rule`引用未定义的`canonical_platform_name`和`canonical_site_name`。Git基线已有此问题，现有测试没有覆盖该分支。本轮保留既有行为，以路径、错误信息和源行登记在`scripts/backend-lint-baseline.json`；lint包装器仍拒绝所有新增错误，基线问题消失时要求删除相应记录。

后续需为旧平台/站点条件准备隔离数据，验证名称转换和规则判定后专项修复。不能因为本轮CI允许已登记基线，就把该分支报告为正确或已验收。

## 后续拆分顺序

1. 监控领域：规则、事件/工单、通知适配；先补STRUCT-001的行为覆盖。
2. 智能投放：政策、执行、复盘、收单各自归组，保留监控协作契约。
3. 目标管理：目标配置与进度读取分离，任务与调度继续按现有部署归属。
4. 前端后续领域采用本轮features边界，重复行为成立后再抽公共组件。

每批独立验证HTTP、权限、空态和交互，并按AGENTS.md核验两端CI。发布与验收证据持续记入[工作流](../agent/workstreams.md)。
