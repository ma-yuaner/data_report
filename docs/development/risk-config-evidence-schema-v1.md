# 配置原证据与最新观察：中文数据字典 V1

用途：保留一张订单在指定出票日首次明确保存的核对证据，以及该原关联规则后续的离散观察。复用已有配置ruleId/版本/快照/哈希/出票时点/历史引用和原止损计算函数；不新建规则匹配或历史还原引擎。

为何新增两表：prepared日事实会随清洗原子替换，既有生命周期历史由ETL维护且不等于人工固定原核对；旧auto_results为账号加载缓存，不能作为共享不可覆盖锚点。原证据锚点与观察事件是一对多，分别承担首次固定和追加提醒，不改写上述旧表或源ERP。

数据库：既有sibebid，MySQL方言（目标实际版本待部署人回读）；InnoDB、utf8mb4_bin。标识列ascii_bin区分幂等标识大小写。原核对/观察JSON均为schemaVersion=1；原票金额/阈值保留十进制字符串（元/CNY），不会用JSON浮点重算。表本身无独立金额列。

一条原证据粒度为内部订单ID＋出票日；一条观察粒度为一次显式观察操作，可含多张票和多个原规则。订单/出票日唯一索引防止新清洗覆盖原证据；事件序号支撑最新排序，request_id唯一索引防重试重复写；evidence_id＋seq索引支撑分页历史，无分区。无物理外键，逻辑关联与请求回执由应用事务保证。

## 表与字段


### bi_risk_config_evidence

一行一个订单/出票日的固定原核对，应用无UPDATE/DELETE入口。

| 字段 | 中文含义 | 类型、可空、默认及约束 | 来源/示例/关联 |
|---|---|---|---|
| id | 固定证据唯一随机编号 | `CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY` | 服务端随机标识，合成例：32位十六进制 |
| order_id | ERP内部订单ID，字符串保留完整标识 | `VARCHAR(19) CHARACTER SET ascii COLLATE ascii_bin NOT NULL` | 已发布目录内部主键，合成例：101，不用订单名称匹配 |
| issue_date | 原核对关联出票业务日，Asia/Shanghai | `DATE NOT NULL` | 已发布日事实出票日，业务时区Asia/Shanghai |
| original_result_id | 保存时已发布日事实的稳定核对结果ID | `CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL` | 当前日事实的稳定ID，保存时锁定并核对 |
| body | 不可覆盖的原核对JSON，含逐票止损、结果、配置身份快照和历史证明、保存人时间及哈希 | `LONGTEXT NOT NULL` | 服务端构造JSON，结构见下文，必填不以空对象冒充有效记录 |
| created_at | 数据库首次写入时间，连接时区须回读核对 | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 数据库CURRENT_TIMESTAMP；连接时区影响显示，非变更生效时间 |

### bi_risk_config_observations

一行一次配置观察，应用仅追加，不覆盖更早观察。

| 字段 | 中文含义 | 类型、可空、默认及约束 | 来源/示例/关联 |
|---|---|---|---|
| seq | 观察事件递增序号，用于同一证据的最新观察排序 | `BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY` | 数据库自增，表示记录顺序，不证明源配置变更先后 |
| id | 本次观察事件唯一随机编号 | `CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE` | 服务端随机标识，合成例：32位十六进制 |
| evidence_id | 逻辑关联原证据ID，原证据一对多观察 | `CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL` | 逻辑关联bi_risk_config_evidence.id，一对多 |
| request_id | 观察草稿的固定幂等标识，重试不重复查询和写入 | `VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE` | 前端每份观察操作固定的幂等键，失败后沿用；不是凭据 |
| request_hash | 发起人和请求内容SHA256，拒绝同键不同请求 | `CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL` | 已认证账号＋订单/日期＋规范化请求的SHA256 |
| body | 追加观察JSON，含原值上次值最新值、源版本快照、观察时间、更新时间及未证实生效时间说明 | `LONGTEXT NOT NULL` | 服务端构造JSON，结构见下文，必填不以空对象冒充有效记录 |
| created_at | 数据库追加写入时间，非源变更生效时间 | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 数据库CURRENT_TIMESTAMP；连接时区影响显示，非变更生效时间 |

## JSON字段契约及时间语义

原证据body：schemaVersion、id、orderId、issueDate、savedAt（应用保存时刻，Asia/Shanghai ISO）、savedBy（认证账号ID）、original（原AutoRiskResult完整结构，包括逐票stopLoss/status/configuration）、originalHash（完整原结果SHA256）。configuration沿用ruleId/configurationVersion/configurationSnapshot/configurationHash/asOf/historyReferences/basis/historyProof，不补造缺失字段。只有basis=issue_time_configuration且asOf/historyProof齐全才显示已有出票时历史证明。

观察body：schemaVersion、id、evidenceId、observedBy、observedAt（ERP只读事务内CURRENT_TIMESTAMP(6)，按+08:00解释）、recordedAt（应用入库业务时间）、previousObservationId、tickets、changed、hasUnavailable、hasUnknownComparison。每票保留ticketId、原配置ID和版本/哈希、原值/原结论、beforeStopLoss（上次观察或原值）、latestStopLoss、源版本/update_time/start/end/status/快照及指纹、当前是否有效、原历史依据状态和变更标志（valueChanged表示相对上次观察，differentFromOriginal表示相对固定原值，configurationChanged表示配置整体变化）。

观察effectiveChangeAt始终NULL：本次没有使用可证明最新变更生效的完整日志链，源update_time只标为更新时间，start/end只是当前配置登记有效期，不能冒充某次阈值修改真实生效时间。usedForOriginalCalculation始终false。缺值为NULL，合法0保留；Decimal精确比较50和50.0不误报金额变化。规则停用/过期仍可展示当前存储数值，但明确不在有效启用状态；规则缺失/类型改变/截断/非法数值则不提供最新阈值。

原证据首次保存后不可覆盖；多个清洗版本、后续源配置修改均不能更新该表body。观察是离散快照，不宣称完整源变更流水；两次观察之间未捕获的中间值不补造。无变化也可记录一次观察，changed=false不是一次业务变更；依据不全时明确未知。

## 发布、权限与留存

GET只读已保存证据，不查ERP、不自动保存。保存需risk.verification.review，观察需risk.verification.check，均还需菜单/view及全局认证/CSRF。共享范围沿用本次团队风控授权，不向所有登录账号公开。

部署人显式执行[两表DDL](../sql/risk-config-evidence-v1.sql)，或在已批准服务器运行既有脚本--config-evidence选项；应用HTTP不建表、不GRANT。普通部署增加只读就绪门禁。DDL先行，API/Web后行；不迁移/清空旧表。CREATE IF NOT EXISTS不修复已存在的结构或注释，必须回读实际列/索引/注释；不同结构须另定迁移，不删表重建。

无自动删除/压缩历史策略，原证据和观察均持久保留；详情仅展示最近500次观察，更早记录不删除。回退应用保留两表和历史。MySQL DDL可能部分成功，失败保留现场，不清库盲重跑。

当前仅交付DDL、中文字典与静态覆盖核对，目标两表DDL执行/中文元数据回读、真实MySQL写入及并发锁仍未验；合成事务和源码检查不能冒充落库验收。
