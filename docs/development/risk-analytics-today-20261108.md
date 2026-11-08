# 小时分析仅当天（2026-11-08）

用户确认：小时调度仅需当天，一次调度处理一个结束日期。本说明覆盖旧版默认31天、多历史结束日期及15分钟提示；不改变生命周期或每日06:00最新配置观察的范围和频率。

## 原因与边界

用户提供677358/1714100日志：首个2026-11-08快照覆盖30个有数据日、141402订单，readSeconds=1144.39，aggregateSeconds=2.753，1213桶，发布0.067秒；之后开始另一个31日历史窗口。附件970个分页事件读取合计1850.24秒、聚合4.671秒，附件尾部仍在历史加工。不能将附件阶段合计当完整38分50秒解释，也不能宣称索引或硬件已证实存在问题。
主要可证实原因是原加工范围超过本次当天需求、多个结束日期及读取成本；不是聚合计算复杂。生产单日规模、SQL计划、单日完成时间尚无新版实测，不承诺提速比例。

## 实现

- CLI默认window-days=1、max-end-days=1，固定本次结束日期（默认Asia/Shanghai当天），不继续消费历史队列。旧无参数Shell更新代码后也适用。
- 保留原有批量250、有界桶数、互斥锁、源一致性快照、原子发布及失败留旧；不改核实、责任或金额口径，不引入DDL、平台或公共配置变更。
- 历史显式加工仍支持window-days=1..31，单次固定一个结束日期。内部Python旧API默认31天保留兼容，不作为新调度默认入口。
- API验证已发布windowStart/windowEnd覆盖请求；当天快照不能冒充多日完整统计，范围不覆盖返回pending/ANALYTICS_RANGE_NOT_PREPARED。历史请求仍可登记，但小时任务不会自动消费，需显式加工。
- 页面默认当天，提示每小时刷新及历史单独加工；查询读取汇总，不逐单计算。

## 实际可用入口

沿用现有小时调度，无需新增节点或依赖。将现有分析Shell替换为同仓库文件etl_scripts/automation/risk_verification_analytics_task.sh内容（两项参数显式为1）；即使保留无参数旧命令，新版CLI也仅当天。

```sh
set -eu
export TZ=Asia/Shanghai
/opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_analytics_etl.py --window-days 1 --max-end-days 1
```

历史补偿示例（显式操作，非小时调度）：
```sh
TZ=Asia/Shanghai /opt/module/miniconda3/envs/python3.11/bin/python -B /home/lywz/data-team-repo/etl_scripts/automation/risk_verification_analytics_etl.py --end-date 2026-11-07 --window-days 7 --max-end-days 1
```

生命周期、小时分析、每日配置观察继续独立，最终反映上游最近成功发布事实；不存在要求强行串行的调度依赖。本轮未登录服务器、启用调度或执行生产写入，代码更新须覆盖实际执行Worker216/218，应用须按既有流程更新前后端；推送不等于部署。

## 另一个脚本

1714375的10:17日志与此前相同，只有通用LATEST_DATABASE_OR_RUNTIME_FAILED，不能由它再次确定底层错误。已发布ETL 102f26f修正参数化DATE_FORMAT百分号驱动错误（改为CAST），并补充脱敏阶段诊断；本次提交包含该修复。需要Worker更新到102f26f或后续版本后重新执行。若新运行仍失败，读取新输出的阶段/异常诊断，不将旧日志当新版复测结果。每日观察依旧06:00，原命令不变，无新增DDL。

## 验证与验收

独立预期：1000历史单与2当天单，日任务只发布2单、一次仅一个结果、历史队列未消费；多日读不得显示当天局部结果为完整；显式2天跨日重复单仍正确去重；无参数CLI只当天。与原21项失败留旧/事务/权限/跨日/25001合成容量回归合计24项通过（5.79秒，本机SQLite，不代表MySQL性能）。原先环境导入/兼容测试失败已定位修正，未删除断言。

证据留应用.test-artifacts/latest-config/test_today_analytics.py、today-final.log、today-evidence.json；原始附件及旧日志不提交Git。Python运行时版本与源码哈希记录于该JSON。生成运行时由权威应用导出，check通过、preview无数据库访问。

本轮主会话执行和自检，无独立执行者。vue-tsc类型检查及该组件ESLint通过，Python3.11 AST检查通过（不是服务器实跑）；本机类型/静态检查与真实页面验收分别记录；浏览器沿用已确认禁用。没有生产新版真实周期、目标MySQL计划/性能或服务器Python3.11实跑证据。不报告已完成这些验收。
