# 历史分析资产蒸馏

更新时间：2026-09-12

来源：对 `data-team-repo` 中分析脚本、独立 SQL、自动化报送、数仓 DDL/DML 和 Notebook 的只读盘点。

状态：整理推导；任务名称与现有代码客观存在，但其中业务公式不自动视为已确认口径。

## 1. 盘点范围

| 代码区域 | 文件数量 | 主要内容 |
|---|---:|---|
| `analysis/scripts/work` | 165 | 企业微信报送、分析逻辑、告警框架 |
| `analysis/scripts/sql` | 95 | 报送任务配套 SQL |
| `etl_scripts/automation` | 97 | 历史自动化报表、KPI、预警、ADM |
| `data_pipelines/src/ddl` | 137 | ODS/DWD/DWS/ADS/MySQL/Doris 建模 |
| `data_pipelines/src/dml` | 10 | 同步与加工 SQL |
| `analysis/notebooks` | 9 | 财务、ERP 等探索性分析 |

按任务名对工作脚本、SQL 目录和自动化脚本去重，并排除告警框架内部模块后，共识别 149 个分析、报送或支撑任务。数量不等于独立指标数量：同一业务问题存在日报、周报、图片版、复制版和不同部门版本。

## 2. 十一类分析能力

| 能力域 | 任务数 | 主要问题 | 当前判断 | 数据中心路线 |
|---|---:|---|---|---|
| 利润与亏损 | 19 | 总利润、单票/单段利润、平台航司政策员利润、亏损订单 | 主干较成熟，但历史财务公式待确认 | M1/M2 已接业务估算利润 |
| 出票履约 | 7 | 出票时长、方式、出票员、供应商出票 | 表和指标较集中 | M3 首选 |
| 退票改签售后 | 22 | ATC、航变、退款状态、PCC、供应售后 | 事件和状态口径分散 | M4 统一售后事件后接入 |
| 智能出票与比价 | 27 | 参与率、成功失败、降舱、废票、规则和比价 | 任务最多、版本重复也最多 | 先建立统一事件模型 |
| 搜索与转化 | 10 | GDS/OTA 搜索、验价、达成率 | 已有 DWD/DWS/ADS 基础 | M4 流量转化专题 |
| 供应商与返点 | 8 | 供应出票、航司任务、返点录入缺失 | 数据可用，合同和返点口径待确认 | M3 供应履约，返点暂单列 |
| 政策与任务 | 4 | 政策数量、任务进度、政策阈值 | 政策粒度与目标来源待确认 | 确认后进入政策专题 |
| 财务结算与风控 | 9 | AR/AP、汇率、支付、告警、ADM | 跨系统且不能等同业务估算利润 | M5 结算利润 |
| 增值服务 | 3 | 增值类型、航司、出票员 | 利润主表已接，分类规则待确认 | M4 增值专题 |
| 部门与客户专项 | 20 | 部门、客户、区域、航司专项日报周报 | 多为公共指标的筛选切片 | 不逐张迁移，沉淀公共维度 |
| 基础报送与工具 | 20 | 导出、邮件、图片、PCC、数据补充 | 属于交付或运维能力 | 与指标层分离保留 |

## 3. 全部去重任务索引

以下索引用于未来追溯旧逻辑，不代表这些脚本都应成为菜单。

### 利润与亏损（19）

`1A_KPI`、`1E_KPI`、`1G_KPI`、`Change_Business_Total_Profit_Data`、`Change_Business_Total_Profit_Data_TotalOnly`、`customer_service_profit`、`ongoing_lossmaking_airline_route`、`Platform_KPI`、`policy_officer_loss_alert`、`policy_officer_loss_alert_markering`、`rc_dept_loss_order_yesterday`、`rc_issue_loss_order`、`rd_whtz`、`Ticket_Business_Total_Profit_Data`、`Ticket_Business_Total_Profit_Data_Platform`、`Ticket_Business_Total_Profit_Data_policy`、`Ticket_Business_Total_Profit_Data_RefundOnly`、`Ticket_Business_Total_Profit_Data_Top30airline`、`Ticket_Business_Total_Profit_Data_TotalOnly`。

### 出票履约（7）

`issue_ticket_month`、`Issue_Ticketing`、`ndc_issue_month`、`Supplier_Ticketing`、`tk_issue_time_exceed_60_min`、`tk_issue_time_month`、`tk_issue_way_all_system`。

### 退票改签售后（22）

`atc_auto_change_error_notice`、`atc_auto_refund_error_notice`、`atc_change_daily`、`atc_change_supplier`、`atc_refund_daily`、`atc_refund_supplier`、`BG_platform_refund_month`、`change_pcc_code_count`、`customer_flight_change`、`customer_flight_change_record_count`、`flight_change_refund`、`flight_change_refund_summary`、`order_change_remind_analysis`、`ota_refund_status_conn`、`ota_refund_status_month`、`platform_tiket_change`、`platform_tiket_refund_`、`rc_bet_refund_change`、`rc_refund_check_daily`、`rc_yesterday_exchange_rate`、`refund_down_yesterday`、`Smart_Downgrade_Refund_Log`。

### 智能出票与比价（27）

`bi_business_sum_day_smart_integrated`、`bi_hold_job_waste_ticket_analysis_day`、`DowngradeMissedOrder`、`hit_smart_strategy_delivery_check`、`hit_smart_strategy_issue_add`、`hit_smart_strategy_issue_check`、`hold_job_data_hive`、`hold_job_data_hive_simple`、`Intelligent_downgrade_ticket`、`Intelligent_waste_ticket`、`near_expiration_smart_rule`、`smart_early_warning_notice`、`smart_early_warning_participation_notice`、`smart_history_data_3_months_ago`、`smart_order_check_month`、`smart_order_check_new_day`、`smart_order_check_week`、`Smart_price_comparison`、`smart_rule_yesterday_increase`、`smart_waste_progress_v1`、`smart_waste_progress_v2`、`system_ota_smart_participate_daily_report`、`WasteMissedOrder`、`week_smart_failure`、`week_smart_success_detail`、`yesterday_smart_failure`、`yesterday_smart_paticipate_rate`。

### 搜索与转化（10）

`gds_1a_search_rate_alert`、`gds_1a_search_rate_monitor`、`mh_pnr_search_verify_order_rate`、`ota_search_verify_order`、`Qunar_OTA_Achievement_Rate`、`qvo`、`szx173_gds_search_rate_report`、`szx173_pnr_search_rate_alert`、`travelsky_segment_search_rate`、`travelsky_SZX173_segment_search_rate`。

### 供应商与返点（8）

`bd_supplier_airline_day_ticket_alert`、`bd_supplier_airline_week_ticket_alert`、`hotel_supplier_daily_data`、`Supplier_Rebate_Entry_Statistics`、`supplier_week_ticket_alert`、`tk_enter_supplier_rebate_data`、`tk_yesterday_no_match_supplier_rebate`、`zdh_supplier_airline_day_week_ticket_alert`。

### 政策与任务（4）

`api_week_policy_count`、`bi_business_plan`、`HK_WUZHOU_CZ_Q2_PROGRESS`、`hotel_dept_2_progress_task`。

### 财务结算与风控（9）

`adm_dashboard_mock_api`、`auxiliary_fi_order_info_ar_ap`、`dep_2_ho_jply_vcc`、`DTT_WARNING`、`early_warning_notice`、`ET_GDS_WARNING`、`ET_HKD_WARNING`、`GDS_WARNING`、`ota_pay_sale`。

### 增值服务（3）

`ota_issue_auxiliary_type`、`tk_auxiliary_airline_order`、`tk_auxiliary_type_ticketer_count`。

### 部门与客户专项（20）

`bd_cz_lywz_bsp_b2b`、`bd_et_hk_ng_chow_travel_week`、`bd_hknc_bsp_daily_report`、`bd_ho_lywz_bsp`、`bd_lywz_ke_oz_zh_week`、`bd_lywznc_bsp_daily_report`、`bd_lywznc_bsp_daily_report_image`、`bd_sv_hk_month`、`dep_2_feizhu_product`、`dep_2_oz_xgwz_hk_trip_count`、`dep_5_month_data`、`dept_6_england_polani`、`ERP_6_department`、`ERP_business_sales_reward_trip_count`、`ERP_business_sales_trip_count`、`erp_daily_data`、`erp_week_aline`、`rd_a_airline_country_reward_trip`、`xgwz_cz`、`zhi_lian_trip_count_rate_yesterday`。

### 基础报送与工具（20）

`airline_gds_pcc`、`api_method_unconfigured_alert`、`bi_customer_summary_day_analysis`、`customer_ota_service_issue`、`customer_service_issue`、`daily_todo_digest`、`daolv_daily_excel_export`、`ET_HKD_ISSUE`、`extract_void_help_data`、`fetch_and_pivot_data`、`GDS_DAILY_EMAIL`、`gds_pcc_rate_alert`、`gds_pcc_rate_analysis`、`gds_pcc_rate_report`、`gds_pcc_rate_report_v2`、`get_ticket_data`、`hot_low_cabin_airline`、`hotel_daily_data`、`supplement_airline_cabin`、`tk_ticket_agent_ticket_data`。

## 4. 蒸馏后的关键结论

1. 旧项目不是“没有数据”，而是分析能力散落在脚本、SQL、Excel、图片和群消息中，缺少统一入口、口径状态和下钻证据。
2. 不应把 149 个任务迁成 149 个页面。部门日报通常只是平台、航司、组织、客户等公共维度的固定筛选。
3. 历史利润脚本存在 FI/ERP 跨库、AR/AP 合并、商品类型重算等复杂公式，只能作为 M5 结算利润的调查材料，不能覆盖当前业务估算利润。
4. 智能出票相关任务最多，但事件定义、成功失败、降舱、废票和规则版本需先统一，否则页面越多口径越乱。
5. 出票履约使用的订单、出票时间、出票方式、供应商和人员字段相对集中，是问题中心之后最适合进入 M3 的主题。

## 5. 里程碑映射

- M1：经营总览、出退改增分析、数据资产——已完成。
- M2：分析资产目录、四类负利润问题中心与证据——当前实现。
- M3：出票履约与供应履约——出票时长、方式、自动化率、供应商结构。
- M4：售后事件、智能出票、搜索转化和增值专题——先统一各自事件口径。
- M5：财务结算利润——打通 FI/ERP、返点、汇率、支付、ADM，形成预估与结算差异。
