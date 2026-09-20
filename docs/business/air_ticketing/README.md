# 公司机票业务知识库

本目录将公司机票业务知识沉淀为可版本化、可追溯的分析依据。首版来源为 2026-09-11 数据部机票业务知识会议纪要。

## 当前成熟度

- 知识版本：`v0.2`
- 当前状态：会议纪要结构化完成，尚待业务、财务和数据负责人逐项确认
- 可用于：业务理解、分析方案设计、数据盘点、指标讨论、看板原型
- 暂不可直接用于：财务结算、正式绩效、合同判断、对外口径或自动化业务决策

## 信息状态

| 状态 | 含义 | 分析使用规则 |
|---|---|---|
| 已确认 | 由对应业务/财务负责人确认 | 可作为正式分析口径 |
| 会议陈述 | 会议或纪要中明确提到 | 可用于提出假设，结论中注明来源 |
| 整理推导 | 根据多条会议内容归纳 | 必须说明是分析框架，不当作事实 |
| 待确认 | 存在歧义、缺少合同或缺少数据验证 | 不得进入正式指标 |
| 已废弃 | 历史口径已停止使用 | 仅用于历史追溯 |

除非文档明确标为“已确认”，本版内容默认属于“会议陈述”或“整理推导”。

## 阅读路由

- 理解公司机票业务全流程：阅读 [business-model.md](business-model.md)
- 计算或分析利润：阅读 [profit-model.md](profit-model.md) 和 [analysis-rules.md](analysis-rules.md)
- 开发经营总览出退改增利润：阅读 [profit-overview.md](profit-overview.md)
- 开发风控核对出退改月度票数和利润对比：阅读 [risk-monthly-analysis.md](risk-monthly-analysis.md)
- 开发综合分析真实MySQL ADS查询、筛选与质量校验：阅读 [comprehensive-analysis-live.md](comprehensive-analysis-live.md)
- 追溯综合分析历史界面预览：阅读 [comprehensive-analysis-preview.md](comprehensive-analysis-preview.md)
- 配置 MySQL 默认查询或临时切回 Hive：阅读 [data-source-switch.md](data-source-switch.md)
- 开发出票利润分析和检查字段齐全度：阅读 [issue-profit-analysis.md](issue-profit-analysis.md)
- 开发数据模型、SQL、宽表或看板：阅读 [data-model.md](data-model.md) 和 [analysis-rules.md](analysis-rules.md)
- 设计数据中心菜单和 MVP 页面：阅读 [mvp-menu-architecture.md](mvp-menu-architecture.md)
- 查看当前 M1 已实现的数据表、指标和页面边界：阅读 [m1-core-framework.md](m1-core-framework.md)
- 查看历史分析脚本的完整蒸馏与能力分组：阅读 [legacy-analysis-inventory.md](legacy-analysis-inventory.md)
- 开发经营问题中心：阅读 [m2-problem-center.md](m2-problem-center.md)
- 查询术语：阅读 [glossary.md](glossary.md)
- 判断现有材料能否直接使用：阅读 [open-questions.md](open-questions.md)
- 追溯本次会议输入：阅读 [sources/2026-09-11-meeting.md](sources/2026-09-11-meeting.md)

## 知识权威顺序

1. 用户在当前任务中明确给出的最新规则；
2. 已生效合同、财务确认文件、系统正式规则；
3. 本知识库中标记为“已确认”的条目；
4. 会议纪要中的会议陈述；
5. 数据字段名、历史 SQL、行业常识和整理推导。

低等级材料与高等级材料冲突时，以高等级材料为准并记录差异。行业定义只能帮助理解，不能替代公司合同和系统实际配置。

## 知识更新格式

新增或修改重要规则时至少记录：

```yaml
knowledge_id: 唯一编码
name: 业务规则或指标名称
status: 会议陈述 | 待确认 | 已确认 | 已废弃
definition: 清晰定义
scope: 适用平台、航司、渠道、时间范围
grain: 订单 | 乘机人票 | 客票 | 航段 | 售后单 | 结算项
owner: 业务或财务确认人
source: 会议、合同、系统、SQL或数据表
effective_from: 生效日期
updated_at: 最后更新日期
```
