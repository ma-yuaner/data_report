# HTTP接口完整目录

维护人：明策（产品）；接口契约由星桥、磐石协作核对。清单从应用蓝图注册、领域路由和认证路由静态提取；用`python scripts/check_readme.py --write`更新，再用`--check`检查是否遗漏。自动HEAD/OPTIONS不重复列出。

这是路由目录，列出方法、完整路径、处理函数和源码入口；参数、响应字段、功能权限与数据依赖还需结合对应函数及专题文档。当前代码存在不代表服务器已部署、数据已同步或生产链路已验收。

## 访问与契约

- 基础前缀来自[应用工厂](../../backend/data_report_api/__init__.py)的蓝图注册；业务路由由[统一注册入口](../../backend/data_report_api/routes.py)加载，认证与账号管理在[auth_routes.py](../../backend/data_report_api/auth_routes.py)。
- `GET /api/health`、`GET /api/auth/status`和`POST /api/auth/login`是默认公开入口；其余请求按认证、菜单和功能规则处理。
- 认证启用时，登录建立会话Cookie；受保护的非GET/HEAD/OPTIONS请求需`X-CSRF-Token`。首次登录强制改密、会话失效和权限不足分别由接口返回对应错误。
- JSON响应通常为`{"success": true, "message": "OK", "data": ...}`，部分错误附加`code`；Excel导出返回文件，上传使用表单文件。
- `<int:user_id>`等保留Flask动态路径写法，调用时替换为实际值。菜单权限与功能权限不等同于行级数据隔离，当前边界见[权限说明](../access-control.md)。

| 领域契约 | 说明 |
|---|---|
| [认证方案](../product/local-account-auth-technical-design.md) / [权限模型](../access-control.md) | 登录、账号、角色、菜单、个人例外与审计 |
| [综合分析](../business/air_ticketing/comprehensive-analysis-live.md) / [风控](../business/air_ticketing/risk-profit-dashboard.md) | 经营分析、诊断、订单与核对口径 |
| [资源治理](../business/air_ticketing/gds-resource-governance-live.md) / [航线页面边界](../business/air_ticketing/gds-route-governance-preview.md) | 总览、导出、Hive航线与演示边界 |
| [智能分析](../business/air_ticketing/smart-analysis-live.md) / [智能投放](../business/air_ticketing/smart-placement-mvp.md) | 分析、模板、任务流、审核和收单 |
| [监控中心](../business/air_ticketing/monitoring-center-v1.md) / [目标管理](../business/air_ticketing/target-management-v1.md) | 规则、事件、技术工单、通知、目标与进度 |
| [上传说明](../business/air_ticketing/risk-data-upload.md) / [行为监控](../product/user-behavior-monitoring-v1.md) | 上传队列和行为采集 |

<!-- BEGIN:API_ROUTES -->
共 **177个HTTP方法/路径条目**。方法和动态路径参数保留源码写法。

<a id="auth"></a>

## 账号认证与权限管理（auth）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/admin/audits` | [list_audits](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/business-roles` | [list_business_roles](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/employees` | [list_employees](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/menu-catalog` | [list_menu_catalog](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/permission-catalog` | [list_permission_catalog](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/roles` | [list_roles](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/admin/roles` | [create_role](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/roles/<string:role_code>` | [update_role](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/users` | [list_users](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/admin/users` | [create_user](../../backend/data_report_api/auth_routes.py) |
| `PATCH` | `/api/admin/users/<int:user_id>` | [update_user](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/users/<int:user_id>/business-roles` | [update_business_roles](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/users/<int:user_id>/employee-binding` | [get_employee_binding](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/users/<int:user_id>/employee-binding` | [update_employee_binding](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/admin/users/<int:user_id>/managed-members` | [list_managed_members](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/users/<int:user_id>/managed-members` | [update_managed_members](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/users/<int:user_id>/menus` | [update_user_menus](../../backend/data_report_api/auth_routes.py) |
| `PUT` | `/api/admin/users/<int:user_id>/permissions` | [update_user_permissions](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/admin/users/<int:user_id>/reset-password` | [reset_password](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/auth/change-password` | [change_password](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/auth/login` | [login](../../backend/data_report_api/auth_routes.py) |
| `POST` | `/api/auth/logout` | [logout](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/auth/me` | [me](../../backend/data_report_api/auth_routes.py) |
| `GET` | `/api/auth/status` | [status](../../backend/data_report_api/auth_routes.py) |

<a id="core"></a>

## 基础信息、资产与兼容入口（core）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/health` | [health](../../backend/data_report_api/api/core.py) |
| `GET` | `/api/v1/assets/catalog` | [asset_catalog](../../backend/data_report_api/api/core.py) |
| `GET` | `/api/v1/assets/coverage` | [asset_coverage](../../backend/data_report_api/api/core.py) |
| `GET` | `/api/v1/issues` | [issues](../../backend/data_report_api/api/core.py) |
| `GET` | `/api/v1/meta` | [meta](../../backend/data_report_api/api/core.py) |

<a id="dashboard"></a>

## 经营总览与利润核对（dashboard）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/dashboard/overview` | [overview](../../backend/data_report_api/api/dashboard.py) |
| `GET` | `/api/v1/dashboard/risk-profit-filter-options` | [risk_profit_filter_options](../../backend/data_report_api/api/dashboard.py) |
| `GET` | `/api/v1/dashboard/risk-profit-summary` | [risk_profit_summary](../../backend/data_report_api/api/dashboard.py) |

<a id="analysis"></a>

## 业务、风控分析与问题中心（analysis）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/analysis/business-profit/<business_type>` | [business_profit_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/comprehensive` | [comprehensive_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/comprehensive/details` | [comprehensive_details](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/comprehensive/diagnosis` | [comprehensive_diagnosis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/comprehensive/exports` | [comprehensive_export_list](../../backend/data_report_api/api/analysis.py) |
| `POST` | `/api/v1/analysis/comprehensive/exports` | [comprehensive_export_create](../../backend/data_report_api/api/analysis.py) |
| `POST` | `/api/v1/analysis/comprehensive/exports/<task_id>/cancel` | [comprehensive_export_cancel](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/comprehensive/exports/<task_id>/download` | [comprehensive_export_download](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/issue-profit` | [issue_profit_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/risk-business/<business_type>` | [risk_business_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/risk-daily` | [risk_daily_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/analysis/risk-monthly` | [risk_monthly_analysis](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/exports` | [comprehensive_export_list](../../backend/data_report_api/api/analysis.py) |
| `POST` | `/api/v1/exports` | [comprehensive_export_create](../../backend/data_report_api/api/analysis.py) |
| `POST` | `/api/v1/exports/<task_id>/cancel` | [comprehensive_export_cancel](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/exports/<task_id>/download` | [comprehensive_export_download](../../backend/data_report_api/api/analysis.py) |
| `GET` | `/api/v1/problems/profit-loss` | [profit_loss_problems](../../backend/data_report_api/api/analysis.py) |

<a id="resource_governance"></a>

## GDS/OTA资源治理与航线诊断（resource_governance）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/resource-governance/gds/export` | [gds_resource_governance_export](../../backend/data_report_api/api/resource_governance.py) |
| `GET` | `/api/v1/resource-governance/gds/overview` | [gds_resource_governance_overview](../../backend/data_report_api/api/resource_governance.py) |
| `GET` | `/api/v1/resource-governance/gds/routes` | [gds_route_analysis](../../backend/data_report_api/api/resource_governance.py) |
| `GET` | `/api/v1/resource-governance/ota/export` | [ota_resource_governance_export](../../backend/data_report_api/api/resource_governance.py) |
| `GET` | `/api/v1/resource-governance/ota/overview` | [ota_resource_governance_overview](../../backend/data_report_api/api/resource_governance.py) |

<a id="smart_analysis"></a>

## 智能分析、导出与视图模板（smart_analysis）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/smart-analysis/comprehensive` | [smart_analysis_comprehensive](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/details` | [smart_analysis_details](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/dimensions` | [smart_analysis_dimensions](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/exports/details` | [smart_analysis_export_details](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/exports/dimensions` | [smart_analysis_export_dimensions](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/exports/trend` | [smart_analysis_export_trend](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/filter-options` | [smart_analysis_filter_options](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/overview` | [smart_analysis_overview](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/templates` | [smart_analysis_templates](../../backend/data_report_api/api/smart_analysis.py) |
| `POST` | `/api/v1/smart-analysis/templates` | [save_smart_analysis_template](../../backend/data_report_api/api/smart_analysis.py) |
| `DELETE` | `/api/v1/smart-analysis/templates/<int:template_id>` | [delete_smart_analysis_template](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/tickets/<issue_id>` | [smart_analysis_ticket](../../backend/data_report_api/api/smart_analysis.py) |
| `GET` | `/api/v1/smart-analysis/trends` | [smart_analysis_trends](../../backend/data_report_api/api/smart_analysis.py) |

<a id="smart_placement"></a>

## 智能投放与收单（smart_placement）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/smart-placement/dimensions` | [smart_placement_dimensions](../../backend/data_report_api/api/smart_placement.py) |
| `GET` | `/api/v1/smart-placement/orders` | [smart_placement_orders](../../backend/data_report_api/api/smart_placement.py) |
| `PATCH` | `/api/v1/smart-placement/orders/<int:match_id>/attention` | [update_smart_placement_attention](../../backend/data_report_api/api/smart_placement.py) |
| `GET` | `/api/v1/smart-placement/tasks` | [smart_placement_tasks](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks` | [create_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `DELETE` | `/api/v1/smart-placement/tasks/<int:task_id>` | [delete_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `GET` | `/api/v1/smart-placement/tasks/<int:task_id>` | [smart_placement_task_detail](../../backend/data_report_api/api/smart_placement.py) |
| `PATCH` | `/api/v1/smart-placement/tasks/<int:task_id>` | [update_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/cancel` | [cancel_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/claim` | [claim_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/effect-reviews` | [create_smart_placement_effect_review](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/executions` | [register_smart_placement_execution](../../backend/data_report_api/api/smart_placement.py) |
| `GET` | `/api/v1/smart-placement/tasks/<int:task_id>/monitoring` | [smart_placement_task_monitoring](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/reviews` | [review_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/stop` | [stop_smart_placement_monitoring](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/<int:task_id>/withdraw` | [withdraw_smart_placement_task](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/policy-changes` | [change_placed_policies](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/policy-changes/preview` | [change_placed_policies](../../backend/data_report_api/api/smart_placement.py) |
| `POST` | `/api/v1/smart-placement/tasks/reviews/batch` | [batch_review_smart_placement_tasks](../../backend/data_report_api/api/smart_placement.py) |

<a id="monitoring"></a>

## 监控、规则、事件、工单与通知（monitoring）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/monitoring/action-orders` | [monitoring_action_orders](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/action-orders/<int:action_order_id>` | [monitoring_action_order_detail](../../backend/data_report_api/api/monitoring.py) |
| `PATCH` | `/api/v1/monitoring/action-orders/<int:action_order_id>/status` | [update_monitoring_action_order](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/event-assignees` | [monitoring_event_assignees](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/events` | [monitoring_events](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/events/<int:event_id>` | [monitoring_event_detail](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/events/<int:event_id>/action-orders` | [create_monitoring_action_order](../../backend/data_report_api/api/monitoring.py) |
| `PATCH` | `/api/v1/monitoring/events/<int:event_id>/status` | [update_monitoring_event_status](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/message-templates` | [monitoring_message_templates](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/message-templates` | [create_monitoring_message_template](../../backend/data_report_api/api/monitoring.py) |
| `PUT` | `/api/v1/monitoring/message-templates/<int:template_id>` | [update_monitoring_message_template](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/notify-endpoints` | [monitoring_notify_endpoints](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/notify-endpoints` | [create_monitoring_notify_endpoint](../../backend/data_report_api/api/monitoring.py) |
| `PUT` | `/api/v1/monitoring/notify-endpoints/<int:endpoint_id>` | [update_monitoring_notify_endpoint](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/notify-endpoints/<int:endpoint_id>/test` | [test_monitoring_notify_endpoint](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/notify-routes` | [monitoring_notify_routes](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/notify-routes` | [create_monitoring_notify_route](../../backend/data_report_api/api/monitoring.py) |
| `PUT` | `/api/v1/monitoring/notify-routes/<int:route_id>` | [update_monitoring_notify_route](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/overview` | [monitoring_overview](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/rules` | [monitoring_rules](../../backend/data_report_api/api/monitoring.py) |
| `POST` | `/api/v1/monitoring/rules` | [create_monitoring_rule](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/rules/<int:rule_id>` | [monitoring_rule_detail](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/rules/<int:rule_id>/diagnose` | [diagnose_monitoring_rule](../../backend/data_report_api/api/monitoring.py) |
| `PATCH` | `/api/v1/monitoring/rules/<int:rule_id>/status` | [update_monitoring_rule_status](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/runs` | [monitoring_runs](../../backend/data_report_api/api/monitoring.py) |
| `GET` | `/api/v1/monitoring/templates` | [monitoring_templates](../../backend/data_report_api/api/monitoring.py) |

<a id="targets"></a>

## 目标配置、进度与刷新（targets）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/business-configuration/target-progress` | [target_progress_dashboard](../../backend/data_report_api/api/targets.py) |
| `POST` | `/api/v1/business-configuration/target-progress/refresh` | [target_progress_refresh](../../backend/data_report_api/api/targets.py) |
| `GET` | `/api/v1/business-configuration/target-progress/refresh/status` | [target_progress_refresh_status](../../backend/data_report_api/api/targets.py) |
| `GET` | `/api/v1/business-configuration/targets` | [target_management_list](../../backend/data_report_api/api/targets.py) |
| `POST` | `/api/v1/business-configuration/targets` | [target_management_save](../../backend/data_report_api/api/targets.py) |
| `GET` | `/api/v1/business-configuration/targets/metrics` | [target_management_metrics](../../backend/data_report_api/api/targets.py) |
| `GET` | `/api/v1/business-configuration/targets/options` | [target_management_options](../../backend/data_report_api/api/targets.py) |

<a id="risk_upload"></a>

## 风控文件上传（risk_upload）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/risk-uploads` | [risk_upload_status](../../backend/data_report_api/api/risk_upload.py) |
| `POST` | `/api/v1/risk-uploads` | [create_risk_upload](../../backend/data_report_api/api/risk_upload.py) |

<a id="data_workbench"></a>

## 数据加工工作台（data_workbench）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/data-workbench/catalog` | [workbench_catalog](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/cleanup` | [workbench_cleanup](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/datasets` | [workbench_upload](../../backend/data_report_api/api/data_workbench.py) |
| `GET` | `/api/v1/data-workbench/datasets/<dataset_id>/preview` | [workbench_dataset_preview](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/jobs` | [workbench_create_job](../../backend/data_report_api/api/data_workbench.py) |
| `GET` | `/api/v1/data-workbench/jobs/<job_id>` | [workbench_get_job](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/jobs/<job_id>/cancel` | [workbench_cancel_job](../../backend/data_report_api/api/data_workbench.py) |
| `GET` | `/api/v1/data-workbench/jobs/<job_id>/download` | [workbench_download](../../backend/data_report_api/api/data_workbench.py) |
| `GET` | `/api/v1/data-workbench/jobs/<job_id>/preview` | [workbench_job_preview](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/jobs/<job_id>/publish` | [workbench_publish](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/recipes` | [workbench_create_recipe](../../backend/data_report_api/api/data_workbench.py) |
| `PUT` | `/api/v1/data-workbench/recipes/<recipe_id>` | [workbench_update_recipe](../../backend/data_report_api/api/data_workbench.py) |
| `POST` | `/api/v1/data-workbench/recipes/<recipe_id>/copy` | [workbench_copy_recipe](../../backend/data_report_api/api/data_workbench.py) |

<a id="hr_mail"></a>

## HR报表邮件（hr_mail）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/hr-mail/batches` | [hr_mail_history](../../backend/data_report_api/api/hr_mail.py) |
| `POST` | `/api/v1/hr-mail/batches` | [hr_mail_parse](../../backend/data_report_api/api/hr_mail.py) |
| `GET` | `/api/v1/hr-mail/batches/<batch_id>` | [hr_mail_detail](../../backend/data_report_api/api/hr_mail.py) |
| `GET` | `/api/v1/hr-mail/batches/<batch_id>/files/<file_id>` | [hr_mail_file](../../backend/data_report_api/api/hr_mail.py) |
| `GET` | `/api/v1/hr-mail/batches/<batch_id>/items/<item_id>/preview` | [hr_mail_preview](../../backend/data_report_api/api/hr_mail.py) |
| `POST` | `/api/v1/hr-mail/batches/<batch_id>/send` | [hr_mail_confirm](../../backend/data_report_api/api/hr_mail.py) |
| `GET` | `/api/v1/hr-mail/config` | [hr_mail_config](../../backend/data_report_api/api/hr_mail.py) |
| `POST` | `/api/v1/hr-mail/uploads` | [hr_mail_upload](../../backend/data_report_api/api/hr_mail.py) |

<a id="telemetry"></a>

## 行为采集与管理看板（telemetry）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/admin/telemetry/dashboard` | [telemetry_dashboard](../../backend/data_report_api/api/telemetry.py) |
| `POST` | `/api/v1/telemetry/events` | [record_telemetry_events](../../backend/data_report_api/api/telemetry.py) |
| `POST` | `/api/v1/telemetry/visits` | [start_telemetry_visit](../../backend/data_report_api/api/telemetry.py) |
| `PATCH` | `/api/v1/telemetry/visits/<visit_id>` | [update_telemetry_visit](../../backend/data_report_api/api/telemetry.py) |

<a id="adm"></a>

## adm（adm）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/adm/cases` | [adm_cases](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases` | [adm_create](../../backend/data_report_api/api/adm.py) |
| `GET` | `/api/v1/adm/cases/<case_id>` | [adm_detail](../../backend/data_report_api/api/adm.py) |
| `PATCH` | `/api/v1/adm/cases/<case_id>` | [adm_update](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/actions` | [adm_case_action](../../backend/data_report_api/api/adm.py) |
| `GET` | `/api/v1/adm/cases/<case_id>/closure-check` | [adm_closure_check](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/copy` | [adm_copy](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/lines` | [adm_add_line](../../backend/data_report_api/api/adm.py) |
| `PATCH` | `/api/v1/adm/cases/<case_id>/lines/<line_id>` | [adm_update_line](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/lines/<line_id>/actions` | [adm_line_action](../../backend/data_report_api/api/adm.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/lines/bulk-assign` | [adm_bulk_assign](../../backend/data_report_api/api/adm.py) |
| `GET` | `/api/v1/adm/cases/<case_id>/timeline` | [adm_timeline](../../backend/data_report_api/api/adm.py) |
| `GET` | `/api/v1/adm/config` | [adm_config](../../backend/data_report_api/api/adm.py) |
| `GET` | `/api/v1/adm/workflow/overview` | [adm_workflow_overview](../../backend/data_report_api/api/adm.py) |

<a id="adm_exchange"></a>

## adm_exchange（adm_exchange）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `POST` | `/api/v1/adm/imports/<preview_id>/commit` | [adm_import_commit](../../backend/data_report_api/api/adm_exchange.py) |
| `POST` | `/api/v1/adm/imports/preview` | [adm_import_preview](../../backend/data_report_api/api/adm_exchange.py) |
| `GET` | `/api/v1/adm/templates` | [adm_template_download](../../backend/data_report_api/api/adm_exchange.py) |

<a id="adm_files"></a>

## adm_files（adm_files）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/adm/cases/<case_id>/attachments` | [adm_attachment_list](../../backend/data_report_api/api/adm_files.py) |
| `POST` | `/api/v1/adm/cases/<case_id>/attachments` | [adm_attachment_upload](../../backend/data_report_api/api/adm_files.py) |
| `GET` | `/api/v1/adm/cases/<case_id>/attachments/<attachment_id>/download` | [adm_attachment_download](../../backend/data_report_api/api/adm_files.py) |
| `GET` | `/api/v1/adm/cases/<case_id>/attachments/<attachment_id>/preview` | [adm_attachment_preview](../../backend/data_report_api/api/adm_files.py) |

<a id="adm_operations"></a>

## adm_operations（adm_operations）

| 方法 | 完整路径 | 处理函数 / 源码 |
|---|---|---|
| `GET` | `/api/v1/adm/operations/config` | [adm_operation_config](../../backend/data_report_api/api/adm_operations.py) |
| `PUT` | `/api/v1/adm/operations/config` | [adm_operation_config_save](../../backend/data_report_api/api/adm_operations.py) |
| `GET` | `/api/v1/adm/operations/deliveries` | [adm_operation_deliveries](../../backend/data_report_api/api/adm_operations.py) |
| `GET` | `/api/v1/adm/operations/inbox` | [adm_operation_inbox](../../backend/data_report_api/api/adm_operations.py) |
| `POST` | `/api/v1/adm/operations/inbox/<record_id>/read` | [adm_operation_read](../../backend/data_report_api/api/adm_operations.py) |
| `POST` | `/api/v1/adm/operations/preview` | [adm_operation_preview](../../backend/data_report_api/api/adm_operations.py) |
| `GET` | `/api/v1/adm/reports` | [adm_reports](../../backend/data_report_api/api/adm_operations.py) |
| `GET` | `/api/v1/adm/reports/<record_id>` | [adm_report_detail](../../backend/data_report_api/api/adm_operations.py) |
| `POST` | `/api/v1/adm/reports/<record_id>/publish` | [adm_report_publish](../../backend/data_report_api/api/adm_operations.py) |
| `POST` | `/api/v1/adm/reports/capture` | [adm_report_capture](../../backend/data_report_api/api/adm_operations.py) |
<!-- END:API_ROUTES -->
