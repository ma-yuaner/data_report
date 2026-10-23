# 企业数据中心（data_report）

面向机票业务的经营分析、资源治理、监控协作和目标管理平台。前端采用Vue 3、TypeScript、Ant Design Vue与ECharts，后端采用Flask，按模块访问MySQL或Hive。金额默认属于业务估算，正式财务口径以已确认的数据契约为准。

本页按2026-10-20仓库代码核对。页面、接口存在只证明有相应实现；部署、数据同步、通知调度和业务验收分别记录在[当前工作流](docs/agent/workstreams.md)。

| 入口 | 内容 |
|---|---|
| [项目协作入口](docs/agent/README.md) / [AGENTS.md](AGENTS.md) | 项目记忆、工作边界、角色与交接 |
| [贡献指南](CONTRIBUTING.md) | 目录规范、本地验证、提交与推送流程 |
| [后端说明](backend/README.md) / [前端说明](frontend/README.md) | 模块入口与开发命令 |
| [产品交付规范](docs/product/product-delivery-contract.md) | 页面、数据、API、权限和验收要求 |
| [业务知识入口](docs/business/air_ticketing/README.md) | 指标口径与专题说明 |
| [完整接口目录](docs/api/README.md) | 全部已注册HTTP方法、路径及源码入口 |
| [仓库边界](docs/development/repositories.md) | 应用与独立ETL仓库的职责 |

## 当前菜单与实现边界

菜单名称及层级来自[侧栏布局](frontend/src/layouts/AppLayout.vue)，页面路径以[前端路由](frontend/src/router/index.ts)为准。下列为全量菜单配置；实际显示受账号菜单权限控制，系统管理仅管理员可见。

<!-- BEGIN:CURRENT_MENU -->
<details>
<summary>完整菜单：40个页面入口、3个禁用预留项</summary>

```text
工作台  [/home]
资源治理
  GDS资源治理  [/resource-governance/gds]
  OTA渠道质量  [/resource-governance/ota]
  航线配置诊断  [/resource-governance/route-diagnosis]
  白名单管理  [/resource-governance/whitelist]
  治理执行  [/resource-governance/execution]
  治理复盘  [/resource-governance/review]
经营总览  [/overview]
业务分析
  综合分析  [/analysis/comprehensive]
  出票分析  [/analysis/issue]
  退票分析  [/analysis/refund]
  改签分析  [/analysis/change]
  增值分析  [/analysis/ancillary]
风控分析
  风控总览  [/risk-analysis]
  出票利润分析  [/risk-analysis/issue]
  退票利润分析  [/risk-analysis/refund]
  改签利润分析  [/risk-analysis/change]
  差错分析  [/risk-analysis/errors]
  订单明细  [/risk-analysis/orders]
  数据上传  [/risk-analysis/upload]
客服分析
  退票分析  [预留/禁用，无页面路由]
  改签分析  [预留/禁用，无页面路由]
  清Q/航变分析  [预留/禁用，无页面路由]
智能分析
  智能整体分析
    综合分析  [/smart-analysis/comprehensive]
    智能总览  [/smart-analysis/overview]
    维度分析  [/smart-analysis/dimensions]
    出票明细  [/smart-analysis/details]
  智能投放
    投放政策  [/smart-analysis/placement/policies]
    收单情况  [/smart-analysis/placement/orders]
业务配置
  目标配置  [/business-configuration/targets]
  目标进度  [/business-configuration/target-progress]
监控中心
  监控总览  [/monitoring/overview]
  监控任务  [/monitoring/tasks]
  预警中心  [/monitoring/alerts]
  技术工单  [/monitoring/actions]
  规则模板  [/monitoring/templates]
  监控运行  [/monitoring/runs]
  通知管理  [/monitoring/notifications]
  问题诊断  [/monitoring/diagnostics]
问题中心  [/problems]
数据资产  [/data-assets]
系统管理
  用户行为监控  [/admin/behavior]
  账号管理  [/admin/users]
```

</details>
<!-- END:CURRENT_MENU -->

需要结合以下实现边界理解菜单：

- **工作台、经营与业务分析**：工作台是默认首页；业务分析包括综合、出票、退票、改签和增值。经营利润与风控核对利润分开展示，不能合并为同一口径。
- **资源治理**：GDS/OTA总览有服务端实现；航线诊断的航线视图读取Hive。配置视图、白名单、治理执行和复盘页面仍含localStorage演示；正式事件及技术工单在监控中心。详见[页面边界](docs/business/air_ticketing/gds-route-governance-preview.md)和[本轮复评](docs/product/gds-resource-governance-reassessment-v3.md)。
- **风控分析**：已有总览、出退改利润、差错、订单明细和数据上传入口。上传由独立Worker执行Hive增量合并；网络、目标表、精度变更及真实文件仍需按[上传说明](docs/business/air_ticketing/risk-data-upload.md)核验。
- **客服分析**：退票、改签、清Q/航变分析为禁用预留项，尚无对应页面路由。
- **智能分析**：采用“智能整体分析”和“智能投放”两组三级菜单。智能分析现已固定读取MySQL年度指标及明细表；投放政策与收单情况有页面和服务端流程，生产表、规则计算与通知调度需按[智能投放说明](docs/business/air_ticketing/smart-placement-mvp.md)核对。
- **业务配置与监控**：目标配置、目标进度、手动刷新，以及规则、事件、技术工单和通知配置已有实现。完成量依赖ETL，通知和资源日检查依赖独立调度；详见[目标管理](docs/business/air_ticketing/target-management-v1.md)和[监控中心](docs/business/air_ticketing/monitoring-center-v1.md)。
- **问题中心、数据资产与系统管理**：分别提供负利润证据、表与指标目录、行为监控及账号管理。账号管理包含角色、菜单、功能权限和审计；当前授权模型见[权限说明](docs/access-control.md)。

登录与修改密码是配套页面；旧`/gds-route-governance/*`地址保留重定向，`/analysis/profit`保留为出票分析别名，不作为新增菜单重复列出。

## 技术与数据来源

```text
浏览器 → Nginx / Vue → Flask API → MySQL / Hive
                            ├─ 风控上传Worker → Hive
                            └─ 目标进度后台任务 → MySQL
独立ETL仓库 → 数据同步、规则计算、资源日检查与通知发送
```

| 模块 | 当前数据源与边界 |
|---|---|
| 经营总览、基础利润分析、问题中心、数据资产 | 支持的查询跟随`DATA_MODE`，默认MySQL；兼容Hive人工切换，不静默补数，详见[切换说明](docs/business/air_ticketing/data-source-switch.md) |
| 业务综合分析 | 固定MySQL ADS及配套业务宽表；ADS默认100万行上限、分批校验汇总；宽表支持50万条以内后台导出、全局进度与取消；真实长周期和大文件性能待部署验收，详见[综合分析](docs/business/air_ticketing/comprehensive-analysis-live.md) |
| 风控专题、月度与订单查询 | 固定MySQL利润核对表；文件上传Worker另行写入Hive |
| GDS/OTA资源总览 | 固定MySQL资源服务表；独立航线诊断固定Hive日汇总表 |
| 智能分析与智能投放 | 固定MySQL；智能分析使用`bi_smart_issue_dimension_year`和`bi_smart_issue_detail_year`，详见[智能分析](docs/business/air_ticketing/smart-analysis-live.md) |
| 认证、目标、监控、行为记录 | MySQL服务与授权写入；ERP花名册、目标进度任务可使用独立连接 |

`DATA_MODE`不是所有模块的全局数据库开关。未同步、缺失、无权限与真实0分别展示；演示交互不能作为交易系统执行或治理效果证据。

## 本地开发

Python 3.12、Node 22。首次从[.env.example](.env.example)创建项目根`.env`并填写开发环境配置，已有文件保留；数据库密码、令牌和Webhook仅保存在授权环境，不提交Git。

后端（在仓库根目录执行）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
cd backend
..\.venv\Scripts\python.exe app.py
```

另开终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

开发地址为`http://127.0.0.1:5173`，Vite将`/api`代理至`http://127.0.0.1:5160`。启动会按配置连接数据源，只在获授权的开发环境运行。

## Docker与首次配置

```powershell
docker compose up -d --build
```

| 服务 | 作用 | 默认端口 |
|---|---|---|
| `web` | Nginx与前端静态资源 | 1818 |
| `api` | Flask/Gunicorn接口 | 5160 |
| `worker` | 风控上传队列、ORC/WebHDFS与Hive合并 | 无外部端口 |
| `target-etl` | 目标进度定时任务，默认间隔900秒 | 无外部端口 |

访问`http://127.0.0.1:1818`；健康检查为`http://127.0.0.1:5160/api/health`。默认业务时间为Asia/Shanghai。

- 账号复用`sys_user`，采用角色菜单、功能权限和个人例外。新环境按[本地认证技术方案](docs/product/local-account-auth-technical-design.md)初始化；仅在账号表为空时使用`AUTH_BOOTSTRAP_ADMIN_*`，首次改密后移除临时密码。
- 认证扩展表由`AUTH_AUTO_CREATE_TABLES`控制；没有DDL权限时先按方案执行[认证表SQL](docs/sql/local-auth-schema.sql)。其他业务表、ETL与调度逐专题核对，不因启动容器就假定已完成。
- 生产启用HTTPS时核对安全Cookie、密钥及访问配置。数据库、ERP、Hive和上传参数见模板；实际部署值以环境为准。
- SQL、生产调度和服务器部署按授权执行，分别记录结果；代码推送不代表部署或验收。

## 接口索引

API统一前缀为`/api`。认证与账号管理使用`/api/auth/*`、`/api/admin/*`；业务接口主要使用`/api/v1/*`。登录后使用会话Cookie，非安全方法需携带CSRF头；JSON通常返回`success/message/data`，导出接口返回文件。具体权限、参数与错误见[完整接口目录](docs/api/README.md)及对应源码。

<!-- BEGIN:API_SUMMARY -->
当前静态登记 **120个HTTP方法/路径条目**（含认证与管理接口，不重复列自动HEAD/OPTIONS）。

| 接口领域 | 条目数 | 完整清单 |
|---|---:|---|
| 账号认证与权限管理 | 24 | [auth](docs/api/README.md#auth) |
| 基础信息、资产与兼容入口 | 5 | [core](docs/api/README.md#core) |
| 经营总览与利润核对 | 3 | [dashboard](docs/api/README.md#dashboard) |
| 业务、风控分析与问题中心 | 13 | [analysis](docs/api/README.md#analysis) |
| GDS/OTA资源治理与航线诊断 | 6 | [resource_governance](docs/api/README.md#resource_governance) |
| 智能分析、导出与视图模板 | 13 | [smart_analysis](docs/api/README.md#smart_analysis) |
| 智能投放与收单 | 17 | [smart_placement](docs/api/README.md#smart_placement) |
| 监控、规则、事件、工单与通知 | 26 | [monitoring](docs/api/README.md#monitoring) |
| 目标配置、进度与刷新 | 7 | [targets](docs/api/README.md#targets) |
| 风控文件上传 | 2 | [risk_upload](docs/api/README.md#risk_upload) |
| 行为采集与管理看板 | 4 | [telemetry](docs/api/README.md#telemetry) |
<!-- END:API_SUMMARY -->

## 开发交付与README维护

本地验证按[贡献指南](CONTRIBUTING.md)执行，完成后直接提交并推送GitLab、GitHub，默认不查询或等待CI；服务器部署另行授权。

README由产品经理**明策**负责。菜单、路由、功能状态、启动配置变化时，先核对当前源码与[工作流](docs/agent/workstreams.md)，再更新本页和相关专题。目录块可用以下脚本同步或检查，业务状态仍需人工审核：

```powershell
python scripts/check_readme.py --write
python scripts/check_readme.py --check
```

脚本只解析源文件并更新指定的文档目录块，不启动应用、读取真实`.env`或连接数据库。可复用的[明策README提示词](docs/agent/prompts.md#6-明策维护项目readme)和[能力卡](docs/agent/roles/product.md)用于后续维护。
