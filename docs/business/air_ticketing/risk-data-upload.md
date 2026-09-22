# 风控出退改数据上传

来源：用户2026-09-20明确要求在“风控分析”下增加数据上传菜单，将出票、退票、改签三类利润核对Excel写入Hive；用户2026-09-21进一步确认三类上传均为增量文件，统一以出票票号作为唯一键，新票号新增、已有票号整行替换，上传记录的预估利润为0时作为删除指令。字段映射来自主仓库历史提交`d5c5caa`中的三个`excel_to_dwd_order_*_profit_reconcile_year.py`脚本；这些脚本随后被回滚，当前页面采用独立且可部署的后台Worker实现相同入口。

状态：菜单、上传队列、字段校验及出退改票号增量合并流程已实现；实际生产文件仍须由风控人员上传验证。更新日期：2026-09-21。

## 页面与目标表

菜单：风控分析 → 数据上传，路由`/risk-analysis/upload`。

| 入口 | Hive目标表 | 默认工作表 | 成功后的写入方式 |
|---|---|---|---|
| 出票 | `lywz.dwd_order_issue_profit_reconcile_year` | `2026年1-8月明细` | 按`issue_ticket_no`增量合并；0利润删除 |
| 退票 | `lywz.dwd_order_refund_profit_reconcile_year` | `2026年明细表格` | 按`issue_ticket_no`增量合并；0利润删除 |
| 改签 | `lywz.dwd_order_change_profit_reconcile_year` | `月度明细` | 按`issue_ticket_no`增量合并；0利润删除 |

只支持`.xlsx`和`.xlsm`。上传文件属于乘客与财务敏感数据，任务结束后自动删除，只保留文件名、SHA256、行数、状态与不包含数据行的运行日志。

## 安全写入顺序

1. API校验业务类型、扩展名、文件大小、工作表名称、覆盖确认和可选导入口令；
2. 独立Worker流式读取Excel，不在HTTP请求中执行长任务；
3. 校验所需中文表头全部存在；额外字段忽略，不按列位置盲写；
4. 通过`DESCRIBE`校验Hive正式表字段名称、顺序和类型；
5. 分批写入本次会话的Hive临时表；不输出订单、乘客或金额明细日志；
6. Excel有效行数与Hive临时表行数一致后，三类业务分别校验增量票号非空且唯一；原表空票号记录在本次合并时自动清理，原表有效票号仍须唯一；
7. Hive生成“未命中原记录 + 本次非0利润记录”的完整合并临时表；本次0利润记录只删除同票号旧行，不进入正式表，利润NULL仍作为缺失值保留；
8. 按新增、替换、删除数量校验总量和票号唯一性，通过后重写对应正式表；
9. 正式表再次校验通过后清理临时表与上传文件。

任何表头、类型、目标表结构或行数校验失败都会停止正式表覆盖。Worker重启时，运行中的任务标记失败并要求人工核对，不自动重放不确定任务。

## 部署配置

API和Worker共享Docker命名卷`risk_upload_data`。生产建议在真实`.env`中配置：

```dotenv
RISK_UPLOAD_ENABLED=true
RISK_UPLOAD_TOKEN=仅部署人员持有的导入口令
RISK_UPLOAD_MAX_MB=200
RISK_UPLOAD_INSERT_BATCH_SIZE=2000
RISK_UPLOAD_POLL_SECONDS=2
```

同时必须配置现有`HIVE_HOST`、`HIVE_PORT`、`HIVE_DATABASE`、`HIVE_USER`、`HIVE_PASSWORD`和`HIVE_AUTH`。真实口令和数据库密码不得写入`.env.example`或提交Git。

### Hive/Hadoop容器客户端预检（尚未切换上传实现）

来源：用户2026-09-22要求先在测试环境验证容器内Hive/Hadoop客户端连通性，通过后再决定是否修改现有出退改上传代码。当前上传Worker仍使用上述`INSERT VALUES`路径；此探针不修改它。更新日期：2026-09-22。

测试机已有的Hive、Hadoop、Java客户端需要只读挂载进独立的`hadoop-probe`容器。先复制`hadoop-probe.env.example`为不提交的`hadoop-probe.env`，核对五个客户端/配置目录；`hive-site.xml`必须对应目标集群。默认命令只读检查HDFS目录和`hive -e SELECT 1`，不创建表。若容器内解析不了`t217`/`t218`或访问不了集群RPC端口，探针会失败；宿主机有客户端并不代表容器能访问。

该探针在隔离容器中以root运行，避免基础镜像中UID 1000无用户名导致Hadoop登录失败；客户端与配置文件均为只读挂载，HDFS用户由`HADOOP_PROBE_USER`指定。若服务器上`/opt/ha/hadoop/etc/hadoop/core-site.xml`不是`hdfs://mycluster`，应把`HADOOP_CLIENT_CONF`指向正确的配置目录，不要修改宿主机现有Hadoop配置。

```bash
docker compose --env-file hadoop-probe.env -f docker-compose.hadoop-probe.yml run --rm hadoop-probe
```

探针只验证读连通性，不创建测试表，也不执行`LOAD DATA LOCAL`。若最终无法连通，按用户要求移除探针，不继续增加配置复杂度。

## 业务边界

- 本功能只负责把用户确认的增量Excel合并到三张利润核对表，不修改利润公式或原因分类；
- 出退改最终均在Hive内生成完整结果并重写正式表；不把Hive原表下载到Python内存；
- 增量文件出票票号为空或重复时停止；Hive原表空票号记录在下一次合并时直接清理，有效票号重复仍停止，不进行不确定替换；
- `estimated_profit_cny=0`是本上传流程的删除指令；NULL是利润缺失，不等于0，仍按增量记录新增或替换；
- 页面提交前要求操作者通过弹窗明确确认；
- 2026-09-20只读`DESCRIBE`确认三张目标表均为非分区表，字段顺序分别与83、74、66列映射完全一致；若表结构后续改为分区表，上传任务会停止而不会猜测分区口径；
- Hive仍是这三张上传表的写入目标，MySQL核对表的后续同步仍由现有调度负责；本功能不会直接写MySQL。
