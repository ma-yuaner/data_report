# 数据资产正式开发 V1：ASSET-IMPL-20261116

用户2026-11-16认可0.1架构并授权直接开发，业务内容要求重新梳理。主会话承担明策/绘景/磐石/星桥/明鉴职责，使用chief-of-staff与frontend-design，无独立代理。正式集成工作区基于GitLab main e36d08c；原常用目录fat_cy落后且有其他任务未提交改动，未重置或合并这些改动。

## 已实现与内容边界

- 原数据资产菜单接入正式快照目录、字段/分区详情、声明键/索引、局部上下游、5跳/500对象有界潜在影响、治理分页与成功采集记录。原经营指标/分析与四表业务状态移入“经营口径与分析”，公式和原接口保留。
- 物理结构注释、既有登记参考、人工业务字典分别展示。核心表契约和既有经营报表可作为登记参考；不自动发布为确认口径。不按名称补造负责人/粒度/业务主键，前缀分层保持候选。
- 字典有服务端持久草稿、独立发布修订、历史及快照依据。采集刷新不覆盖字典，保存草稿不改变发布口径或物理注释缺口；发布只表示授权人员维护了业务字典，不等于独立业务验收。
- 新增assets.inventory.view和assets.dictionary.manage，绑定data_assets菜单。管理员按既有规则允许；普通用户完整目录需显式授权查看，维护需同时具备两项。旧资产目录接口与旧经营资产权限不扩大。新接口继承既有认证、改密和CSRF。

## 运行文件与采集

ASSET_INVENTORY_ROOT默认指向本地应用var/assets；Docker明确使用/app/var/assets，并新增asset_inventory_data持久卷。目录包括current.json原子指针、snapshots/<SHA-256>.json不可变结构版本、dictionary.sqlite3业务字典。运行文件与真实元数据不进Git。

scripts/publish_asset_inventory.py只读取本地盘点CSV，不联网：校验实例身份、对象/字段/库覆盖、端点和静态证据状态，全部通过后写不可变快照，最后原子切换指针；校验失败保留旧指针。API不扫描源库，不提供任意文件上传、SQL/DDL执行或网络连接入口。当前采集由已交付脚本/部署人执行，不声称已有Web采集调度器、部分成功作业历史或自动刷新SLA。

本次种子来自2026-11-16真实只读盘点：6库/1067对象/34431字段，313条依赖证据，244条两端命中、69条端点待核对。定义依赖、视图定义和DataX配置分开；运行状态全部未验证。45条外键列声明只作为结构关系。未补齐的业务字典和源到ODS采集映射继续显示待维护/待核验。

重新采集/离线解析使用独立工具环境scripts/asset_inventory_requirements.txt（sqlglot沿用本次实测版本），不改应用或公共连接依赖。当前部署种子导入只用Python标准库，不需要安装解析工具，也不会执行其连接逻辑。

## API

以下路径前缀/api/v1/assets/inventory：

| 方法/路径 | 行为 |
|---|---|
| GET /summary | 当前版本、来源覆盖、对象/字段、字典/证据计数及权限 |
| GET /objects | version、database、layer、search、dictionaryState、page/pageSize分页；上限100 |
| GET /detail | assetId与version；字段、键、索引、缺口、发布字典；仅维护者可见草稿 |
| GET /lineage | assetId、version、scope；depth默认5，上限10；最多500下游对象，返回截断与未解析前沿 |
| GET /gaps | version、gap、page/pageSize；缺口记录与是否可定位 |
| PUT /dictionary | assetId、结构version、draftRevision、publishedRevision、values；版本冲突409 |
| POST /dictionary/publish | 同资产/结构/字典版本，将已保存草稿发布为新修订；空字典及旧快照草稿拒绝 |

运行证据未采集时返回not_collected和未知前沿，不把空列表解释为无影响。物理结构未知不会补0；未发布快照503，结构版本变化409，无对象404，权限不足403。前端请求序号防迟到响应覆盖新查询，失败保留旧结果并显示已展示范围；保存冲突保留用户输入。

## SQLite表及逐字段中文说明

DDL在docs/sql/asset-dictionary-sqlite-v1.sql；应用首次字典写入创建私有文件表，无需对生产MySQL/Hive执行DDL。SQLite没有COMMENT元数据能力，中文说明在版本化DDL注释和本表维护。新库无历史回填，不改变任何源业务表。

| 字段 | 所属表 | 类型/约束 | 中文含义及空值 |
|---|---|---|---|
| asset_id | 两表 | TEXT；草稿主键，发布联合主键 | 来源别名/实例指纹/库/对象稳定身份；应用仅允许当前快照内对象，不能空 |
| revision | 两表 | INTEGER NOT NULL | 草稿或发布修订号，从1递增；由服务端生成，不接受NULL/0作为已保存版本 |
| base_revision | 草稿 | INTEGER NOT NULL | 草稿所基于的最新发布版本，0表示没有发布；和当前发布版本一致才能继续 |
| body | 两表 | TEXT NOT NULL | JSON文本，见下列八字段；草稿允许全空，但不能发布全空字典 |
| snapshot_version | 两表 | TEXT NOT NULL | 保存/发布时依据的结构SHA-256，发布前与当前结构一致 |
| updated_at | 两表 | TEXT NOT NULL | 草稿更新时间或发布时间，business_now的含时区时间 |
| updated_by | 两表 | TEXT NOT NULL | 服务端登录账号ID字符串，开发禁用认证模式为既有development账号；客户端不得伪造 |

body只接收八个字符串字段：businessUse业务用途≤2000字；grain业务粒度≤1000；businessKey业务唯一键/去重约定≤1000；timeField业务时间字段≤500；timeMeaning时间口径/时区≤1000；domain业务主题域≤100；owner口径负责人≤200；refreshSla更新约定/时效要求≤1000。空字符串表示待维护，不表示0、未知事实已经确认或已经指定人员。owner目前是口径登记文本，不自动发送消息或授予账号权限。

草稿每资产一条；发布历史每资产多条，用(asset_id,revision)唯一。发布在BEGIN IMMEDIATE事务内校验草稿和发布版本、写修订、移除草稿；冲突回滚。跨进程依赖SQLite事务锁，线程另有本地锁。仅适用于单机API实例共享本地持久卷，不承诺跨主机NFS多写。历史不自动清理；迁移、备份与扩容另行评估。

## 验证证据及限制

旧检出验证20项；最新main隔离集成36项相关pytest通过，覆盖计数/分页/字段、内容分离、保存发布历史、并发写只有一个成功、旧快照/空发布/参数拒绝、权限/CSRF、失败导入保留旧指针与旧资产接口。新增测试仅在本机忽略.test-artifacts内。

实际Vue setup隔离验证覆盖手动查询、迟到响应拒绝、失败保留、草稿冲突保输入、显式保存/发布、运行证据未知、权限和卸载。最新main强制vue-tsc -b --force、改动ESLint、85组件注册检查通过。最新集成真实本机HTTP闭环通过，真实元数据＋合成字典，冷summary约144.63ms；不是247性能或生产写入验收。

原检出Windows构建曾通过；最新main集成Windows构建连续遇到esbuild删除临时文件Access is denied（含沙箱外/独立TEMP），两次后停止同路径重试。最终在已有Ubuntu中用隔离便携Node22.16.0、原package-lock执行npm ci与npm run build退出0；245份输入文件和当前源码SHA-256逐一一致，回执linux-build-receipt.json及日志在本机.test-artifacts/assets-implementation。没有修改系统Node、降低构建检查或套用旧产物。浏览器仍禁用，未验真实点击、中文输入、缩放与视觉。未登录服务器、执行生产DDL或部署、查询CI、发送群通知。

## 部署交接

代码分支feat/assets-inventory-20261116以GitLab main为基线。GitLab/GitHub main已分叉，不强推覆盖；两端独立分支推送结果见最终回执。先在目标仓库检查无未提交跟踪改动，再fetch并切换该分支；不能拉旧main就宣称已更新资产功能。

本地交付包：工作区数据库结构核对/数据资产前期盘点_20261116/数据资产上线种子包_20261116.tar.gz，包含受控盘点inventory目录、解析覆盖、完整发布脚本及部署Shell，不包含.env/账号密码。将包放到247应用仓库根目录，由部署人执行包内deploy_asset_inventory.sh。Shell只构建api/web、把本地CSV复制进临时导入目录，再以容器Python校验并原子发布到新持久卷；不连ERP/Hive、不改源表或已有业务字典。失败退出，未通过导入不切换资产指针。不把此交接当已部署。

首次安装后，由管理员在原账号权限页面为需要的人授权完整资产目录；维护者另授字典维护。主业务服务端口沿用1818/5160。若回滚代码，保留asset_inventory_data卷和字典数据库，不docker compose down -v；结构快照和字典备份需一起保管。

复盘：本次最早偏差是用相邻公共配置失败代替应用.env可达性结论；现已按实际入口复核。跨项目可迁移的配置核验、实例身份、四类事实分离与原子发布方法合入MYE既有数据链路规范，企业元数据留本项目；MYE提交/推送状态单独记录。

MYE回流：通用方法文档检查通过，本地提交e2fb0d1，仅两份方法文档；推送其main被自动审批以“本轮未明确授权该仓库默认main推送”为由拒绝，未绕过或改用其他路径发布。公司资产模块开发不受此独立发布限制影响。


## 已授权推送与通知回执

最新发布回执（2026-11-16）：用户明确授权两端独立分支及MYE/main后，资产代码9d4c64a已推送GitLab/GitHub的feat/assets-inventory-20261116，两端远端SHA均核对为9d4c64a526ccf058d5e4149fb4862489af9c0c99；MYE/main已核对为e2fb0d10ffb8bba3f56169052ec4839d1dbf0382。此前自动审批阻碍已由本次明确授权解除。用户确认申请人马远尔，复用既有qa_wecom_delivery.py发送一次发版群通知，HTTP200/errcode=0、0.261秒；明确独立分支已推送、main未合并、247未部署。无重复通知、不查CI、不部署。安全回执在原常用目录.test-artifacts/assets-implementation/notify及工作区盘点目录开发交付回执JSON。

