# 风控核对读取性能修复（2026-11-08）

用户反馈已有ETL但风控核对首屏仍等待5–10秒。主会话按chief-of-staff定位、自检，无独立代理；浏览器禁用约束保留。涉及API读取及ETL已有日诊断投影，不改前端布局、阈值规则、金额、人工写入或调度范围。

## 原因证据

页面RiskVerificationView.queryOverview串行等待summary、orders、followup.summaries。真实外部MySQL只读服务分段（非服务器HTTP/浏览器）：summary排除账号个人抽样读取后14.199秒、6条SQL，其中状态查询14.070秒；订单首屏0.247秒、7条SQL；人工状态逐单快照/人工记录20单41条SQL，约0.7–0.9秒。ETL已做规则计算，但summary仍对所选日每单的大result_json执行3个JSON字段提取再在Python计数，不能等同直接读小汇总。原数据留在受控项目，输出仅查询哈希/时间/数量。

## 修复

1. ETL Preparation在原计算循环按reason/status累计categoryStatuses及summaryVersion=1，随已有diagnostics_json在目录/准备同一日事务发布；复用结果也计入，零日保存空映射，写入计数不一致不发布。无新增表/列/DDL，不改变证据、历史阈值或结果身份。
2. summary在单日、同批次/规则SHA就绪、无个人抽样记录时读取已发布分类计数。校验分类集合、非负整数、逐分类总量、全日总量和原statuses一致；坏投影报错，不返回0。旧报告缺版本、多日跨日去重或有账号个人抽样记录时保留原事实校验路径。因此不是对所有条件保证恒定耗时；工作台和人工确认语义不改变。
3. followup.summaries对最多100组order_id/issue_date一次有界关联查询，读取状态头部/人工记录，不把完整证据JSON传回Python；稳定结果ID、过期判断、目录回退、顺序/重复项及缺日/损坏校验保持。只优化列表批量读取，不改详情/写动作的完整证据检查。

## 验证

23项定向隔离测试、13项既有真实快照/权限回归及3项ETL投影发布测试通过，共39项。包含0/1/20/100单一次查询、原逐单结果等价、重复/跨日/旧批次/未接规则/错误JSON、过期人工记录、版本/分类/总量异常、旧批次与个人抽样回退、复用/零日及计数不符拒绝发布。初次SQLite夹具缺%s转换及原文检测误匹配JSON_EXTRACT已修正，业务断言未删。

真实只读同一MySQL快照20单，优化前41次/0.655秒，后1次/0.184秒，完整结果hash相同。当天真实数据的汇总投影进程内回放：原14.147秒/6次SQL，投影0.048秒/5次SQL，metrics/categories/sampling/period完全一致。投影由同快照原状态构造供验证，没有写生产，也不是已上线ETL结果/用户页面秒开证据；排除了账号抽样查询、服务器/浏览器/网络路径，单次先旧后新可能有冷热影响，不报告生产提速比例或P95。

证据位于.test-artifacts/risk-read-latency-20261108/{before.json,measurement.json,test_read_performance.py,measure_summaries.py}；ETL var/risk-cleaning/test_category_projection.py。两套生成runtime校验通过，3.11仅语法解析，非Worker实跑。SQL源码归档RISK-CHECK-043。

## 生效步骤

先更新实际216/218 Worker的ETL main，让原当天生命周期任务成功再发布一次（无需改现有调度）；再更新应用后端main/rebuild API。本轮前端未改，不新增调度/DDL。旧ETL批次尚无summaryVersion时，新API仍兼容读取，速度优化需新批次才能生效。可在summary响应dataFreshness.preparation.reports中核对summaryVersion=1及categoryStatuses；仍慢时分开核对汇总/列表/人工状态请求，不把全部时间继续归于ETL。

本轮未执行生产写入/部署、无真实HTTP或浏览器验收；公司GitLab和现有GitHub发布回执另记。未来多日与个人抽样路径仍可能有大JSON状态开销，本次明确保留，不能声称全场景已优化。
