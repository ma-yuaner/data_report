# 数据加工工作台 V1

2026-10-26增量：删除管理、计算列/特征工程、关联重复键及可配精度见[工作台易用性V2](data-workbench-v2.md)，替代下文“固定6位”等旧版限制；未设置scale的历史步骤仍按6位运行。部署及真实容量仍需验收。

状态：2026-10-24 用户授权开发；非已部署/已验收。主会话负责契约、集成与验证，独立代理按文件归属并行实现。

## 范围与界面

现有Vue/Flask中新增 `/data-workbench`，独立菜单权限 `data_workbench`，默认仅管理员，普通用户需显式授权。所有源数据、流程、任务、结果按当前用户隔离，管理员也不默认跨用户取数据。三栏：数据集、受限表格预览、已应用步骤；局部横向滚动，分栏可收起/调整/重置，后台计算不刷新整页。支持真实CSV/XLSX导入、受控算子、精确金额、关联基数拦截、保存/复制流程、换源复跑、后台运行/取消/结果检查与导出。只产出新结果，不写业务表。不提供任意Python/SQL、生产数据直连、跨用户共享或自动销账。

首次采用独立本地持久目录的SQLite元数据＋不可变源文件/Parquet＋DuckDB计算，避免未授权DDL；与业务库分离。单宿主共享卷部署，独立worker，SQLite事务claim/lease/attempt保护，不能跨宿主独立磁盘运行。两年是保留需求，不承诺本轮已经实现自动清理策略。规模与性能以实际合成验收报告为准，不保证秒出或快于Power Query。

## 唯一HTTP契约

路径前缀 `/api/v1/data-workbench`，复用 `{success,message,data}`，错误含 `code`，不可返回内部路径/SQL/堆栈。HTTP适配统一从g.current_user取整数id；每次引用右表/源表/结果必须重新做owner检查。

- GET `/catalog` → `{datasets: Dataset[], recipes: Recipe[], jobs: Job[], operators: string[], limits: object}`。
- POST `/datasets` multipart `file`, `name`(可选), `sheetName`(可选) → Dataset，201。每次导入新版本，不静默追加/覆盖；显式append算子用于追加。
- GET `/datasets/<id>/preview?offset=0&limit=100` → Preview。受限limit最大200。
- POST `/recipes` JSON `{name,sourceId,steps}` → Recipe，201。
- PUT `/recipes/<id>` JSON `{name,sourceId,steps,revision}` → Recipe；乐观版本冲突409。
- POST `/recipes/<id>/copy` JSON `{name?}` → 独立Recipe，201。
- POST `/jobs` JSON `{sourceId,steps,kind:'preview'|'run',recipeId?,recipeRevision?}` → Job，202。任务冻结源/规则快照，preview也由worker执行；不在HTTP内执行无界清洗查询。
- GET `/jobs/<id>` → Job。
- POST `/jobs/<id>/cancel` → Job；取消中不能冒充已取消。
- GET `/jobs/<id>/preview?offset=0&limit=100` → Preview，仅成功结果。
- GET `/jobs/<id>/download` → CSV流，仅成功结果、按用户鉴权；不会下载即删除持久结果；防公式注入。
- POST `/jobs/<id>/publish` JSON `{name?}` → Dataset，成功结果可保存为新数据集继续加工；同任务重复发布返回同一数据集。

`Field={id:string,name:string,type:string,sourceName?:string,position?:number}`。物理字段稳定 `c0001` 等，重复表头保留列序号/来源名，不用原表头当对象键。数据行对象以id为键，十进制/大整数以字符串传输，不在JS计算正式金额。

`Dataset={id,name,rowCount:number,fields:Field[],createdAt,quality:object}`。
`Recipe={id,name,sourceId,steps:Step[],revision:number,createdAt,updatedAt}`。
`Job={id,kind,status:'queued'|'running'|'cancel_requested'|'cancelled'|'succeeded'|'failed',sourceId,steps,createdAt,updatedAt,error?:string,report?:object,fields?:Field[],rowCount?:number}`。
`Preview={fields:Field[],rows:Record<string,string|null>[],total:number,offset:number,limit:number,scope:'source'|'preview'|'full',report?:object}`。

## 步骤契约

Step含稳定`id`及`op`，参数不支持任意表达式字符串。全部字段引用必须存在，不存在就报错，不猜测替换。

- trim `{id,op:'trim',columns:string[]}`。
- replace `{id,op:'replace',column,from:string,to:string}`，精确值替换。
- cast `{id,op:'cast',column,type:'text'|'decimal'|'date'}`，非法值NULL并计数，保留失败来源信息；空串与0不等同。
- filter `{id,op:'filter',column,operator:'eq'|'ne'|'gt'|'gte'|'lt'|'lte'|'contains'|'is_null'|'not_null',value?:string}`。
- derive `{id,op:'derive',name,kind:'add'|'subtract'|'multiply'|'divide'|'concat'|'condition',left:string,right?:string,value?:string,operator?:string,then?:string,else?:string}`。left/right字段，若无right则value为字面量；condition采用filter的比较运算。输出id=`d_`+step.id，数值运算精确DECIMAL，除零NULL并计数；除法明确约定结果6位小数，不能静默浮点。
- group `{id,op:'group',keys:string[],aggregations:{column,fn:'sum'|'count'|'min'|'max',name}[]}`。输出键保留id，聚合字段id=`g_`+step.id+`_`+索引。
- join `{id,op:'join',rightSourceId,leftKeys:string[],rightKeys:string[],how:'left'|'inner'|'full'|'anti'}`。仅数据集右表，右输出id=`r_`+step.id+`_`+右字段id；等值关联，NULL不匹配。执行前精确检查键频次/预计输出量/膨胀倍数，超过限制拒绝，不靠用户确认绕开；report展示检查结果和建议。
- append `{id,op:'append',rightSourceId,mapping:Record<string,string>}`，mapping左字段id→右字段id，所有左字段都需显式映射，类型可兼容才追加，不自动去重。
- select `{id,op:'select',columns:string[]}`。

## 运行与验收

### 部署与使用

由用户在目标服务更新代码后，执行`docker compose up -d --build api web data-workbench-worker`；本轮不代为部署。端口仍为1818/5160，新增持久卷`data_workbench_data`必须与API和worker共同挂载并纳入备份（SQLite元数据、源文件、结果需要一致性备份）；单宿主部署，不将多个独立本地卷当作共享存储。普通用户在账号管理显式授予`data_workbench`菜单。启动worker后用户进入“数据加工工作台”：导入→添加类型转换/加工步骤→步骤预览→全量运行→检查报告→导出或保存为数据集继续加工；保存流程可复制、换结构兼容来源复跑。右表如需先清洗，先将其加工结果保存为数据集，再选择关联。

默认限制：每源最多200万行、300个原始字段，单次文件190MiB（低于代理200MiB限制以留multipart余量）；关联/结果最多300万行、关联膨胀不超过5倍；每用户最多5个待处理任务；全局worker并发默认1，单任务2线程/512MB引擎内存/2GB临时磁盘、运行600秒，导入300秒。Docker worker另设3GB内存和2CPU上限。API的`DATA_WORKBENCH_*`配置控制新任务冻结预算；提高导入时限时需同步前端360秒请求和Nginx360秒代理时限，不只改worker环境。CSV目前仅UTF-8/UTF-8 BOM；XLSX只读公式缓存值，不负责Excel公式重算。分组编辑器每步一个聚合字段，引擎支持多聚合；不承诺本轮已提供财务专用预置口径、字段拖拽排序、列宽拖动、共享发布或两年自动清理。

内置模板当前采用通用受控步骤起步，不擅自配置未确认毛利公式；业务字段映射/固定清洗模板由真实样本和确认口径补充，不能将任意同名字段自动当作相同含义。

数值转换首版固定6位小数，检查报告列出`decimalScale`及`precisionChanges`；存在更高精度汇率时，不能未经确认直接用此转换结果做正式财务核算。原始文本仍保留，可回到源数据核查；可配置精度和财务专用模板属于后续补充。数值千分位只接受标准分组，不将`1,23`悄悄转换为123。

源文件流式限大小、Excel压缩炸弹/列数/行数保护；上传解析由有界流程执行，不用整份pandas。任务有全局worker并发/CPU线程/内存/临时磁盘与超时限制，失效lease可重试但旧attempt不得发布结果；失败/取消不发布。每步report提供输入/输出行数、转换失败、除零及关联统计；最终金额合计只对明确数值字段提供，标全量/预览，预览不得截断输入后冒充正确关联/汇总。

保存/复制/复跑保持历史任务快照。源结构变化致字段失效需定位步骤，不能静默采用同名列。检查正常主链、NULL/0/负数/重复表头/非法字段/关联爆炸/越权/乐观冲突/取消与重启。测试与数据只留忽略目录；真实业务数据、远端部署、生产权限/存储备份和真实并发另验。
