# 风控跟进V1：五表中文数据字典

数据库：MySQL（正式目标版本待部署人回读确认），目标为既有sibebid；字符集utf8mb4，排序规则沿用目标库默认，不另改公共库。DDL支持中文表/列COMMENT；本轮只交脚本，未执行正式DDL或回读元数据。

五表分别承担共享案例、订单当前人工核实、追加事件历史、不可变策略版本和幂等回执。既有自动结果/ETL事实/旧个人案例无法承载此共享状态与事务，因此新增专用表，不迁移或覆盖旧记录。SQL见[完整DDL](../sql/risk-followup-v1.sql)。

所有表由风控API专用服务访问；认证、菜单和动作权限在服务端校验。无旅客明细或凭据字段，无金额单位/币种字段；业务日期和ISO业务时间按Asia/Shanghai，数据库自动TIMESTAMP须核对连接时区。类型和约束以附表DDL为准，未知不补0或空结论。

保留策略：应用不自动删除当前记录、事件、策略版本或幂等回执；后续清理须单独决定。案例与订单为一对多；每订单/出票日最多关联一个案例，原问题标签仍独立保留。无数据库外键，逻辑关联与更新由应用同事务/版本检查保证，避免跨旧模块强制迁移。

主键/索引：案例ID唯一；订单人工记录以订单ID＋出票日复合主键防重复；事件seq稳定排序且id唯一；策略ID唯一；请求ID唯一阻止并发重复写。案例池、负责人/期限、最近更新、关联案例及事件倒序索引支撑筛选和详情；无分区或额外全局索引。

JSON结构：case body对应服务FollowCase；review body含resultId/证据元数据/conclusion/reason/policy/caseId/actor/at/version；event body含before/after/note/actor/at/kind；policy body含name/policyVersion/start/end/scope/basis；request response保存已成功响应。字段升级须保持历史可读，未知版本不能冒充当前有效。


## bi_risk_followup_cases

风控共享跟进案例：一行一个跨订单案例，认定与跟进状态独立。

| 字段 | 中文含义 | 类型与约束 | 来源及空值说明 |
|---|---|---|---|
| id | 案例唯一编号，由应用随机生成 | `CHAR(32) NOT NULL PRIMARY KEY` | 应用生成或核实表单，受服务端校验 |
| version | 案例并发版本，每次有效修改递增 | `INT NOT NULL` | 应用生成或核实表单，受服务端校验 |
| conclusion | 人工实际问题结论：no_issue无问题、problem有问题、unknown暂无法判断 | `VARCHAR(20) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| disposition | 当前差错认定：pending待认定、included计入、excluded不计入 | `VARCHAR(20) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| state | 跟进状态：todo待跟进、following跟进中、waiting等待反馈、done已完成 | `VARCHAR(20) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| assignee | 实际跟进负责人姓名，不代表数据库账号授权 | `VARCHAR(80) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| next_at | 下次跟进时间，Asia/Shanghai带时区ISO字符串，已完成为NULL | `VARCHAR(40) NULL` | 应用生成或核实表单，受服务端校验 |
| first_seen | 是否人工确认首次出现：1是、0否，默认0不自动推断 | `TINYINT NOT NULL DEFAULT 0` | 应用生成或核实表单，受服务端校验 |
| special | 是否人工标记特殊案例：1是、0否，默认0 | `TINYINT NOT NULL DEFAULT 0` | 应用生成或核实表单，受服务端校验 |
| body | 完整案例JSON快照，含标题、原因、责任归属、下一步、标记依据及创建时间 | `LONGTEXT NOT NULL` | 版本化JSON快照；必填，不补空对象冒充有效记录 |
| updated_at | 最近有效修改时间，Asia/Shanghai带时区ISO字符串 | `VARCHAR(40) NOT NULL` | 应用生成或核实表单，受服务端校验 |

## bi_risk_order_reviews

订单人工核实当前记录：一行一个内部订单ID和出票日组合。

| 字段 | 中文含义 | 类型与约束 | 来源及空值说明 |
|---|---|---|---|
| order_id | ERP内部订单ID字符串，不保存旅客身份信息 | `VARCHAR(40) NOT NULL` | 已发布目录内部主键；案例级事件无单据时NULL |
| issue_date | 关联证据的出票业务日期，Asia/Shanghai | `DATE NOT NULL` | 已发布目录出票日；案例级事件无单据时NULL |
| version | 本订单本出票日人工核实版本，每次核实或结论变更递增 | `INT NOT NULL` | 应用生成或核实表单，受服务端校验 |
| case_id | 关联跟进案例编号，单独确认无问题可为NULL | `CHAR(32) NULL` | 逻辑关联共享案例；独立无问题记录可NULL |
| body | 人工核实JSON快照，含系统证据身份、人工结论、策略快照、依据和操作者 | `LONGTEXT NOT NULL` | 版本化JSON快照；必填，不补空对象冒充有效记录 |

## bi_risk_followup_events

人工核实及案例跟进追加历史：一行一次有效操作事件，不覆盖旧记录。

| 字段 | 中文含义 | 类型与约束 | 来源及空值说明 |
|---|---|---|---|
| seq | 历史事件自增序号，用于稳定展示最近操作 | `BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY` | 应用生成或核实表单，受服务端校验 |
| id | 事件唯一随机编号，防止重复标识 | `CHAR(32) NOT NULL UNIQUE` | 应用生成或核实表单，受服务端校验 |
| case_id | 关联案例编号，独立无问题核实时可为NULL | `CHAR(32) NULL` | 逻辑关联共享案例；独立无问题记录可NULL |
| order_id | 订单级核实事件的内部订单ID，案例级跟进事件为NULL | `VARCHAR(40) NULL` | 已发布目录内部主键；案例级事件无单据时NULL |
| issue_date | 订单级核实事件关联出票日，案例级事件为NULL | `DATE NULL` | 已发布目录出票日；案例级事件无单据时NULL |
| body | 事件JSON，含操作人、业务时间、类型、修改前后快照和依据 | `LONGTEXT NOT NULL` | 版本化JSON快照；必填，不补空对象冒充有效记录 |
| created_at | 数据库写入时间戳，由数据库CURRENT_TIMESTAMP生成，连接时区须核对 | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 数据库默认；连接时区影响显示，非人工核实业务时间 |

## bi_risk_review_policies

公司策略不可变版本登记：一行一个由业务认可并人工登记的具体策略版本。

| 字段 | 中文含义 | 类型与约束 | 来源及空值说明 |
|---|---|---|---|
| id | 策略版本唯一随机编号，历史核实保存本版本快照 | `CHAR(32) NOT NULL PRIMARY KEY` | 应用生成或核实表单，受服务端校验 |
| body | 策略JSON，含名称、版本、适用出票日起止、适用范围、认可依据和登记人 | `LONGTEXT NOT NULL` | 版本化JSON快照；必填，不补空对象冒充有效记录 |
| created_at | 数据库登记时间戳，默认CURRENT_TIMESTAMP，连接时区须核对 | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 数据库默认；连接时区影响显示，非人工核实业务时间 |

## bi_risk_followup_requests

人工跟进写入幂等回执：一行一个操作草稿的唯一请求，和业务写入同事务。

| 字段 | 中文含义 | 类型与约束 | 来源及空值说明 |
|---|---|---|---|
| id | 前端每份草稿固定请求标识，失败重试沿用，不是凭据 | `VARCHAR(80) NOT NULL PRIMARY KEY` | 应用生成或核实表单，受服务端校验 |
| actor | 发起操作的已认证账号ID，由服务端取得 | `VARCHAR(80) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| digest | 规范化请求内容的SHA256摘要，用于拒绝同键不同内容 | `CHAR(64) NOT NULL` | 应用生成或核实表单，受服务端校验 |
| response | 成功业务响应JSON，用于重复请求返回同一结果 | `LONGTEXT NOT NULL` | 应用生成或核实表单，受服务端校验 |
| created_at | 数据库回执写入时间戳，默认CURRENT_TIMESTAMP，连接时区须核对 | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 数据库默认；连接时区影响显示，非人工核实业务时间 |

## 部署、兼容与验证

只创建新表，不对旧表回填默认结论。发布顺序为部署人显式建表→结构就绪门禁→API/Web；缺表不自动创建或降级假保存。CREATE IF NOT EXISTS不会更新已经存在的表注释，若此前执行过无注释版本，须部署人先核对实际结构并另行批准元数据修订，不能假称本脚本已补注释。

应用业务验证28项、独立定向7项支持服务契约；DDL仅结构解析/中文覆盖核对，不证明目标MySQL执行、注释元数据回读或并发锁已验。数据库支持的中文注释已提供，正式版本兼容性与实际落库仍待部署验收。失败保留已创建新表与既有业务数据，不清库、删卷或自动回退元数据。
