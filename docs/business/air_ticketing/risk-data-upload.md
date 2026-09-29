# 风控出退改数据上传

来源：用户2026-09-20明确要求在“风控分析”下增加数据上传菜单，将出票、退票、改签三类利润核对Excel写入Hive；用户2026-09-21进一步确认三类上传均为增量文件，上传记录的预估利润为0时作为删除指令；用户2026-09-28确认同一增量中重复唯一键可以整组忽略；用户2026-09-29将出票、退票唯一键调整为“出票票号 + 乘客姓名”，并将改签唯一键调整为“出票票号 + 乘客姓名 + 改签单号”。字段映射来自主仓库历史提交`d5c5caa`中的三个`excel_to_dwd_order_*_profit_reconcile_year.py`脚本；这些脚本随后被回滚，当前页面采用独立且可部署的后台Worker实现相同入口。

状态：菜单、上传队列、字段校验、ORC/WebHDFS传输及出退改复合键增量合并流程已实现；实际生产文件及DataNode重定向网络仍须由风控人员在测试环境验证。2026-09-29用户将MySQL三张BI核对表的指定金额字段改为`decimal(18,8)`，并进一步明确要求上传时将Hive目标表所有`decimal(18,4)`字段统一升级为`decimal(18,8)`；Worker现会在生成ORC前自动完成升级并重新读取结构。[精度迁移SQL](../../sql/hive-risk-profit-reconcile-decimal-18-8.sql)仅作为手工迁移与核验参考。更新日期：2026-09-29。

## 页面与目标表

菜单：风控分析 → 数据上传，路由`/risk-analysis/upload`。

| 入口 | Hive目标表 | 默认工作表 | 成功后的写入方式 |
|---|---|---|---|
| 出票 | `lywz.dwd_order_issue_profit_reconcile_year` | `2026年1-8月明细` | 按`issue_ticket_no + passenger_name`增量合并；0利润删除 |
| 退票 | `lywz.dwd_order_refund_profit_reconcile_year` | `2026年明细表格` | 按`issue_ticket_no + passenger_name`增量合并；0利润删除 |
| 改签 | `lywz.dwd_order_change_profit_reconcile_year` | `月度明细` | 按`issue_ticket_no + passenger_name + change_order_no`增量合并；0利润删除 |

只支持`.xlsx`和`.xlsm`。上传文件属于乘客与财务敏感数据，任务结束后自动删除，只保留文件名、SHA256、行数、状态与不包含数据行的运行日志。

## 安全写入顺序

1. API校验业务类型、扩展名、文件大小、工作表名称、覆盖确认和可选导入口令；
2. 独立Worker流式读取Excel，不在HTTP请求中执行长任务；
3. 校验所需中文表头全部存在；额外字段忽略，不按列位置盲写；
4. 通过`DESCRIBE`读取Hive正式表字段名称、顺序和类型；若存在`decimal(18,4)`字段，先逐列自动执行`CHANGE COLUMN ... DECIMAL(18,8)`，再重新`DESCRIBE`确认不存在4位小数字段；
5. Worker流式生成与目标表字段、顺序和类型一致的本地ORC，通过WebHDFS上传到唯一临时目录；不输出订单、乘客或金额明细日志；
6. 完成可能耗时较长的ORC转换和WebHDFS上传后重新建立Hive连接，避免复用已空闲失效的Thrift会话；Hive再通过`10000`创建指向该ORC目录的临时外部表；Excel有效行数、HDFS文件大小与Hive临时表行数一致后，任一唯一键字段为空时停止任务；同一批中重复的完整组合及其全部增量行被忽略，只保留本批唯一组合继续合并；正式表复合键不完整或重复时停止；
7. Hive生成“未命中原记录 + 本次非0利润记录”的完整合并临时表；本次0利润记录只删除完整复合键相同的旧行，不进入正式表，利润NULL仍作为缺失值保留；
8. 按新增、替换、删除数量校验总量和复合键唯一性，通过后重写对应正式表；
9. 正式表再次校验通过后清理Hive临时表、HDFS临时目录、本地ORC和上传文件。

任何表头、类型、目标表结构或行数校验失败都会停止正式表覆盖。Worker重启时，运行中的任务标记失败并要求人工核对，不自动重放不确定任务。

金额转换失败日志会同时显示Excel行号、中文表头、Hive字段名及Hive目标类型。上传程序按`DESCRIBE`结果动态生成ORC，不硬编码小数精度，也不会为了通过校验把8位金额静默四舍五入到4位。

## 部署配置

API和Worker共享Docker命名卷`risk_upload_data`。生产建议在真实`.env`中配置：

```dotenv
RISK_UPLOAD_ENABLED=true
RISK_UPLOAD_TOKEN=仅部署人员持有的导入口令
RISK_UPLOAD_MAX_MB=200
RISK_UPLOAD_WEBHDFS_URL=http://t217:9870;http://t218:9870
RISK_UPLOAD_WEBHDFS_USER=lywz
RISK_UPLOAD_WEBHDFS_HOST_MAP=t216=39.108.97.159,t217=120.79.238.200,t218=120.79.241.111
RISK_UPLOAD_WEBHDFS_CONNECT_TIMEOUT=10
RISK_UPLOAD_WEBHDFS_READ_TIMEOUT=300
RISK_UPLOAD_HDFS_URI=hdfs://mycluster
RISK_UPLOAD_HDFS_ROOT=/tmp/data-report/risk-uploads
RISK_UPLOAD_ORC_TIMEZONE=Asia/Shanghai
RISK_UPLOAD_POLL_SECONDS=2
```

同时必须配置现有`HIVE_HOST`、`HIVE_PORT`、`HIVE_DATABASE`、`HIVE_USER`、`HIVE_PASSWORD`和`HIVE_AUTH`。真实口令和数据库密码不得写入`.env.example`或提交Git。

WebHDFS只使用NameNode HTTP端口`9870`发起请求，不依赖NameNode RPC端口`8020`；上传文件正文时NameNode会重定向到DataNode HTTP端口（通常为`9864`）。`RISK_UPLOAD_WEBHDFS_HOST_MAP`同时改写初始NameNode地址和DataNode重定向地址，避免依赖Worker容器的DNS或`/etc/hosts`。ORC始终先上传到唯一临时目录，不直接写正式表LOCATION。

## 业务边界

- 本功能只负责把用户确认的增量Excel合并到三张利润核对表，不修改利润公式或原因分类；
- 出退改最终均在Hive内生成完整结果并重写正式表；不把Hive原表下载到Python内存；Excel只在Worker中流式转换为ORC；
- 出票、退票唯一键是`TRIM(issue_ticket_no) + UPPER(TRIM(passenger_name))`；改签再增加`TRIM(change_order_no)`；
- 增量文件任一唯一键字段为空时停止；同一批增量中的重复完整复合键整组跳过，不任意保留其中一行，正式表对应旧数据保持不变；Hive原表复合键不完整或重复时停止；
- `estimated_profit_cny=0`是本上传流程的删除指令，只删除相同复合键的记录；NULL是利润缺失，不等于0，仍按增量记录新增或替换；
- 页面提交前要求操作者通过弹窗明确确认；
- 2026-09-29出票Excel与目标表调整为81列：删除`正确原因`、`计入差错`、`备注【原始】`，增加`备注【整理】 → sort_remark`；退票、改签仍分别为74、66列。若目标表字段或顺序不一致，上传任务会停止而不会猜测映射；
- Hive仍是这三张上传表的写入目标，MySQL核对表的后续同步仍由现有调度负责；本功能不会直接写MySQL。
