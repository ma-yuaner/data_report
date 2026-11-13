# ADM运营数据字典与部署说明

2026-11-13。新增三张辅助表，并将订单及申诉的problem_attribution归因列统一为VARCHAR(32)可空，兼容新增分类；复用现有主单、订单、操作日志、转派及企业微信通知端点。目标MySQL 5.7+/8.0、InnoDB、utf8mb4；实际目标版本和落库元数据尚未验证。

所有业务时间均为北京时间；金额沿用既有冻结人民币，不新增金额列。逻辑关联由主单/明细锁及应用事务校验，不新增外键以免改变已有迁移和作废行为。

## admwf_line_context

| 字段 | 类型及约束 | 中文含义 |
|---|---|---|
| line_id | BIGINT NOT NULL | 订单明细ID，一笔明细一条当前原因记录 |
| case_id | BIGINT NOT NULL | 所属ADM主单ID，由应用事务校验一致 |
| cause_category | VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN' | 根因：HUMAN人为/SYSTEM系统/EXTERNAL外部规则平台/BUSINESS业务/FORCE_MAJEURE不可抗力/UNKNOWN待查明 |
| cause_detail | TEXT NULL | 根本原因及调查结论，不以罚单事项代替根因 |
| evidence_note | TEXT NULL | 证据说明或附件引用，不存附件正文 |
| blocking_reason | TEXT NULL | 当前阻塞原因，解决后可更新 |
| responsible_link | VARCHAR(2000) NULL | 涉及责任环节，例如订位、出票或退款，不表示已认定个人责任 |
| updated_by_id | BIGINT NOT NULL | 最后补充信息的中台用户ID |
| updated_at | DATETIME NOT NULL | 最后更新时间，Asia/Shanghai业务本地时间 |

## admwf_operations_config

| 字段 | 类型及约束 | 中文含义 |
|---|---|---|
| id | INT NOT NULL | 固定1，运营配置单例 |
| settings_json | JSON NOT NULL | 配置：enabled开关、endpointId现有群端点ID、times每日1到2个HH:mm、slaHours各阶段小时、baseUrl页面地址；不存Webhook密钥 |
| updated_by_id | BIGINT NOT NULL | 配置修改人中台ID |
| updated_at | DATETIME NOT NULL | 配置修改时间，Asia/Shanghai |

## admwf_reminder_delivery

| 字段 | 类型及约束 | 中文含义 |
|---|---|---|
| id | BIGINT NOT NULL AUTO_INCREMENT | 发送记录ID |
| delivery_key | CHAR(64) NOT NULL | 日期时段与群端点ID的SHA256去重键 |
| slot_key | VARCHAR(32) NOT NULL | 计划时段YYYY-MM-DD HH:mm，Asia/Shanghai |
| endpoint_id | VARCHAR(64) NOT NULL | 监控中心企业微信群端点ID，不存地址或密钥 |
| status | VARCHAR(16) NOT NULL | CLAIMED已占用/SENT已送达/FAILED平台明确失败/UNKNOWN网络结果不明/SKIPPED无待办 |
| task_count | INT NOT NULL | 本次汇总当前有效待办项数 |
| message_summary | TEXT NOT NULL | 实际发送文本，包含单号和责任人，不包含PNR票号及Webhook |
| created_at | DATETIME NOT NULL | 发送占用时间，Asia/Shanghai |
| finished_at | DATETIME NULL | 本地发送完成时间，未知或进程中断可空 |

## 表职责与索引

- admwf_line_context：一行对应一笔明细的当前根因、证据和阻塞信息；line_id主键防重复，case_id索引用于主单回读，cause_category索引用于分类。历史改动写admwf_operation_log。
- admwf_operations_config：id固定1，当前配置单例；enabled默认关闭，不保存Webhook，仅引用通知中心端点ID。slaHours建议初值：恢复判断/派单/接单72小时，正在恢复48小时，其他24小时，可调整。时限按阶段进入日志起算，与主单截止取较早者；不是承诺所有历史阶段均有完整事件。
- admwf_reminder_delivery：日期时段+群端点唯一去重，CLAIMED占用后才发送。SENT是平台errcode=0，FAILED是平台明确拒绝，UNKNOWN是网络返回不明，SKIPPED是本时段无待办。中断留下CLAIMED需人工核对，默认不重试，避免重复发群。时间索引供发送记录查询。仅存必要的单号/责任人摘要，不存PNR/票号/Webhook。保留期尚未配置自动清理。

## 部署与启用

1. 首次执行新版本部署时显式启用新增表：`ADM_APPLY_OPERATIONS_SCHEMA=1 bash scripts/deploy_adm.sh <本次提交>`。执行三表CREATE IF NOT EXISTS及两列归因类型扩展；不删表、不重写旧归因值。两条ALTER可能涉及锁表，需在正式库评估执行窗口。
2. 之后常规部署使用原命令，脚本先校验这三张表的22个新增列和两处扩展归因列的存在、类型及数据库列注释；未就绪时停止切换服务。脚本提供不代表已执行。
3. 为分析人员配置adm.analysis（全部ADM分析，不受个人待办范围限制），为提醒负责人配置adm.notify.manage。普通操作员继续使用本人订单办理权限收集原因。
4. 从ADM控制台「业务分析与跟进」打开「提醒与阶段时限」，选择现有正式企业微信群。已确认每天09:30、16:30；早间全部待办，下午只临期/超时。服务器环境ADM_EXTERNAL_DELIVERY_ENABLED=true与页面开关必须同时开启。群未指定，当前不启用。
5. 先预览，再通过真实发送记录验收。没有发送测试群，也没有生产群消息证据。阶段明细、分析导出最多10000行，超过明确拒绝；分析接口服务端聚合、明细50行分页，维度最多200组，日期最多367天。生产规模、时延和执行计划待验。

## 指标口径

主单数按case_id去重；航司/供应商/业务分类/罚单事项/来源分组先去重主单金额再加总。平台/根因/人员/阶段等明细维度用line_cny，未分单金额不冒充已分配金额。跨明细维度主单数不能直接相加。申诉成功率为当前明细成功/(成功+失败)，不含不申诉和进行中；历史多轮以当前有效结果为准。状态图是当前快照，时间趋势仅下发主单数，不伪造历史积压。
阶段进入时间优先采用匹配当前状态的最近流转日志，缺少日志从主单创建时间起算；转派待确认用请求时间。历史缺事件不声称精确时效。根因以订单当前归因为准，旧平台归因映射为外部规则/平台，尚未有有效值时才回退过程补充表，否则为待查明。新增分类同时适用于申诉结果、人工补充和操作员Excel导入导出，不把不可抗力折成平台问题。

## 验证范围

本地SQLite隔离执行验证SQL逻辑（对MySQL日期函数及upsert作等价适配），不能替代真实MySQL方言、事务并发、执行计划和元数据检查。真实数据库、浏览器布局、服务器部署与群送达均待验。

## 既有列扩展字典

| 表.字段 | 变更后定义 | 中文业务含义与兼容 |
|---|---|---|
| admwf_case_line.problem_attribution | VARCHAR(32) NULL | 当前订单根因；HUMAN人为、PLATFORM旧平台兼容、SYSTEM系统、EXTERNAL外部规则平台、BUSINESS业务、FORCE_MAJEURE不可抗力、UNKNOWN待查明；NULL表示尚未登记。不清理历史值。 |
| admwf_appeal.problem_attribution | VARCHAR(32) NULL | 该轮申诉/不申诉所登记的根因，同上枚举，保留各轮当时归因，不随当前订单补充修改而覆盖历史。 |

过程根因补充同时更新订单当前归因并增加版本号，完整证据/说明/阻塞写辅助表；所有修改写既有操作日志。两列可能原为枚举或字符类型，部署前检查，--apply明确统一字符类型，不执行分类回填。
