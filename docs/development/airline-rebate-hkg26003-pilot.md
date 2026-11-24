# HKG26003 后返流程试点

已实现正式前端入口与 Flask 后端联动。试点管理员可上传 HKG26003 PDF，下载原件并核对字段，确认后建唯一任务，在「分析此项」手动运行 Hive 试算并按计划起飞日期下钻。分析抽屉保留最近成功结果和旧批次日明细；后续试算失败时展示原因。试点仅允许已确认的 V1。

## 启用和数据来源

部署时由负责人给后端配置 `AIRLINE_REBATE_PILOT_ROOT`，指向只有服务账号可访问的持久目录。配置为空时试点禁用。沿用现有 Hive 连接配置，读取 `lywz.dwd_order_issue_wide_year` 与机场字典。Hive 仅 SELECT，最大 50,000 行。SQLite 位于上述目录，保存上传原件、任务和试算快照，未引入 MySQL 表或写入。可在管理员身份下从「经营与考核 → 后返管理」进入。线上开关、目录权限和部署均待执行。

SQLite 内部存储以 `backend/data_report_api/services/airline_rebates/store.py` 为准。SQLite 不提供独立的表列注释元数据，字段含义如下。

| 表 | 粒度与字段 |
|---|---|
| rebate_policies | 一份 PDF。id 是文件 SHA-256；profile 是文件显示信息及解析字段；original 是原 PDF；confirmed_by、confirmed_at 是人工确认人和 UTC 确认时间，空表示待确认。 |
| rebate_tasks | 一条后返任务。id 是任务 ID；policy_id 是唯一政策引用；profile 是名称及负责人等；run_token 和 run_at 是当前试算令牌和开始 Unix 秒，空表示空闲；current_run 是上次成功运行 ID；run_error 是最近失败信息。 |
| rebate_runs | 一次成功试算。id 是运行 ID；task_id 是所属任务；summary 是版本、截至日、每天累计和金额的不可变快照。金额按字符串保存十进制精度。 |
| rebate_days | 一次运行中的一个计划起飞日。run_id 和 day 组成唯一键；details 是当日输入的订单号、航程、计量票面价和命中、剔除或待核原因。 |

Compose 部署时在环境项目根目录的 .env 添加 `AIRLINE_REBATE_PILOT_ROOT=/app/var/airline-rebates`，使用专用命名卷。拉取提交后仅重建 API 和 Web。可执行以下命令确认目录写权限，命令只打印结果状态。

```sh
docker compose config --quiet
docker compose up -d --no-deps --build api web
docker compose exec -T api test -w /app/var/airline-rebates
```

如目录不可写，由环境负责人执行 `docker compose run --rm --no-deps --user 0 api chown appuser:appgroup /app/var/airline-rebates`。关闭时清空开关并重建 API 容器，保留命名卷。不要执行删除卷的命令。

### T43

T43 使用专用更新器。以服务器的 /data/data_report/.env 为运行配置，配置指定目录后先创建独立的 data_report_airline_rebate_pilot_data 卷，再从更新器部署。更新器检查卷名、挂载路径和应用账号写权限。默认关闭时不挂试点卷，旧版回退配置仍可用。当前在 T43 的步骤按现场确认推进。

## 口径与验证

按销售期 2025-07-01 至 2026-09-30、首段起飞 2026 Q3 取香港供应商、MU/FM 销售航司。逐条匹配 PDF 解析出的票证、航线、舱位及档位。原工作簿的历史导出差异不用于额外排除。状态未决、换开、混合舱位等保留待核，混合舱位未推算票联计奖金额。非港澳始发 1% 单列，在预计后返试算总额中只计一次。本次更保守地将换开和退票中金额挂待核，结果与先前探索性试算会不同。结果使用计划日期和 HKD 票面价，不能替代航司结算。

2026-11-24 实际上传用户原始 PDF，通过本地 Flask 路由直接读真实 Hive。确认前建档被拒绝，确认后重复提交复用任务。查询 43,282 行，生成 92 天；9 月 30 日明细 701 行，验证分页与回读。试算 T3，累计票面价 HKD 39,087,880，预计后返 HKD 640,780.15，含非港澳始发 HKD 98,168.80，待核 12,326 条。另验证失败保留上一批明细，以及普通账号接口拒绝。未做浏览器操作、生产部署、航司结算验收或定时调度。
