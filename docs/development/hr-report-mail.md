# HR报表邮件：等价迁移交付与部署验收

2026-10-24。入口`/hr-mail`，菜单“HR报表邮件”。这是中台Python/Vue模块，不再生成或发布Windows EXE。业务来源和原文件SHA256见[迁移基线](../product/hr-report-mail-migration.md)。

## 1. 已实现

- 分别上传周报、月报、部门映射，显式选择本次类型；保留原文件名周期，不改原始文件。
- 原函数生成部门、指标、异常人员、缺邮箱提示；全选/取消/仅有效，逐部门主题/HTML/收抄送和附件核查；最后确认清单才进入发送。
- 原周报排行榜和汇总图表；原周/月部门独立Excel附件。额外Sheet按旧规则保留并提示，不擅自删除。月报总览保留本部门全部人员，正文仅异常>0且原排序，AB文本扣罚不转0。
- 私有上传/输出持久卷、数据库批次/逐封结果/事件审计/预览回执；本人范围，管理员可查看全部，无普通账号默认授权。
- 专用worker串行执行批次；版本/CAS防并发重复领取。发送前持久化SENDING，成功是服务端接受，不保证最终投递；通道中断/部分拒收/崩溃结果未知，不自动重发。
- SMTP和企业微信**邮件API**均保留，不使用群机器人替代；凭据仅由服务器`.env`注入，无前端输入接口、无明文业务字段、无本地JSON发送日志。

旧JSON日志尚未自动回灌；旧程序可留作只读历史依据。新批次全部写数据库。真实投递、生产MySQL、Linux字体/浏览器交互需人工验收，尚未部署。

## 2. 原函数保留与技术适配

`services/hr_mail/legacy`复用原excel_parser、markdown_builder、chart_generator和email_sender。非业务适配仅：配置import改为无凭据默认值、平台北京时间页脚、附件output_dir、SMTP部分收件人拒收不再误报全部成功；企微token在实例中读服务器环境变量，收抄送/MIME/正文/附件构造仍调用原实现。

原月报总览实际格式范围为A1:XFD333，不能因此裁掉列：缓存重复Sheet读取、附件只读取首行表头、写入时不分配末尾无样式None单元格（原序列化本来不输出它们）。完整表头及尺寸保留；业务列、空值、值/排序/字段不改。合成XFD格式样本新旧xlsx内部xl/*逐XML一致。

依赖沿原兼容版pandas2.2.3/numpy1.26.4/matplotlib3.8.4；新增Linux中文字体WenQuanYi，避免中文方框。不同系统字体不承诺像素完全一致，不改变图表数据/主题。新模块涉及HR个人信息，文件与审计只按授权可见，不进入Git/外部AI。

## 3. 建表、权限及备份

部署人先核对实际MYSQL_DATABASE（默认sibebid）并备份，在同库手工执行[HR专用DDL](../sql/hr-report-mail-v1.sql)，共`hr_mail_upload`、`hr_mail_batch`、`hr_mail_preview`三表。无须新建数据库、不改ERP表；API不自动建生产表，SQLite只用于显式TESTING。

通过现有账号管理给HR操作账号配置菜单`hr.mail`；上传/解析权限`hr.mail.upload`，最终发送权限`hr.mail.send`分别授予。普通账号仅本人上传与批次；管理员可核查全部。全站管理员拥有管理权限是现有平台约定，不新增跨部门普通角色默认授权。

同时备份MySQL三表和`hr_mail_data`持久卷，冻结附件/正文/审计配套恢复；勿`down -v`。上传默认20MiB、xlsx展开上限200MiB/5000ZIP条目，超限明确拒绝，不截断。文件不会下载后即删（须用于发送与审计），不与全站临时导出清理混用；保留期由HR/运维确认后另行清理，不默认删除历史。

## 4. `.env`邮件配置（用户服务器执行）

2026-10-27按用户最终决定，邮件认证信息直接由部署目录的私密`.env`提供，不再创建或挂载`hr_mail_config.json`。真实`.env`不得提交Git、发到聊天、写入日志、前端或业务库；Linux上建议归部署账号所有并设`chmod 600 .env`，同时保护服务器磁盘与备份。Docker管理员仍可查看容器环境，因此这不是加密密钥库。

SMTP配置示意（占位值不能发送）：

```dotenv
HR_MAIL_METHOD=smtp
HR_MAIL_SMTP_HOST=smtp.example.invalid
HR_MAIL_SMTP_PORT=465
HR_MAIL_SMTP_USE_SSL=true
HR_MAIL_SMTP_USER=sender@example.invalid
HR_MAIL_SMTP_PASSWORD=REPLACE_ON_SERVER
HR_MAIL_SMTP_FROM=sender@example.invalid
HR_MAIL_SENDER_NAME=人事部自动报表
HR_MAIL_SEND_ENABLED=false
```

企微邮件API替代配置（不是Webhook）：

```dotenv
HR_MAIL_METHOD=wecom
HR_MAIL_WECOM_CORP_ID=REPLACE_ON_SERVER
HR_MAIL_WECOM_AGENT_ID=REPLACE_ON_SERVER
HR_MAIL_WECOM_APP_SECRET=REPLACE_ON_SERVER
HR_MAIL_SEND_ENABLED=false
```

只选实际通道的一套配置，不把SMTP密码改作企微应用Secret。保留原SMTP主机/端口/SSL、发件人和显示名；`HR_MAIL_SENDER_NAME`留空时用“人事部自动报表”，`HR_MAIL_SMTP_FROM`留空时回退到登录账号。587沿旧规则STARTTLS，465为SSL；不擅改邮件收件规则。先保持发送开关为false完成解析和预览，准备真实受控投递时再由部署人改为true并重建API/worker。未配置邮件变量仍可上传解析预览，不能发送；轮换密码后同样需要重建两个容器。

## 5. 更新部署

在现有data_report部署目录执行（沿用1818/5160及其他服务）：

```bash
git pull --ff-only
docker compose -p data_report -f docker-compose.yml -f docker-compose.hr-mail.yml up -d --build api web hr-mail-worker
docker compose -p data_report -f docker-compose.yml -f docker-compose.hr-mail.yml ps
```

只有HR实际发信才需要额外worker，无新增端口。默认主Compose不开HR worker，仍可解析/预览；开启发信后日常更新继续带两个`-f`，避免漏启动worker。不要同时启动旧EXE和中台向同一周期发信。

页面配置状态只证明环境变量结构/DDL可读，不证明SMTP网络或实际送达。QUEUED长时间不动先检查hr-mail-worker是否运行、同库/同卷/环境变量是否一致；INTERRUPTED/UNKNOWN先查审计及邮箱服务，不盲目新批次重发。邮件环境变量缺失显示HR_MAIL_CONFIG_NOT_READY；缺表/列HR_MAIL_DDL_MISSING；版本冲突HR_MAIL_CONFLICT；未逐封预览HR_MAIL_PREVIEW_REQUIRED。

## 6. 人工验收顺序

1. 默认发送关闭，用同一周报/月报及原部门映射分别解析；核对周期/部门/收抄送/指标，不用新模板重做输入。
2. 月报核对异常>0、倒序、W至AB字段、文本扣罚；异常0但有请假/出差仍按原规则有部门附件。
3. 全选/取消/仅有效，缺邮箱不能发送。逐封查看原主题/正文、下载部门附件，对照旧工具Sheet/行/字段；注意原算法额外Sheet保留。
4. 未预览时发送按钮不可用；逐封预览后最终清单再次列出收抄送、主题、附件。取消清单不发送，修改输入使旧预览失效。
5. 开启发送时先用HR批准的测试映射/测试邮箱，明确点最终确认；看QUEUED→RUNNING→逐封结果，收件箱核对主题/正文/附件。测试企微时必须确认企业邮箱权限，不能借其他项目机器人测试。
6. 重复确认/刷新不重发；暂时关闭发送开关或撤销账号权限应阻止未开始的发送；UNKNOWN不自动重试。服务已接受仍需收件箱验证。
7. 刷新/重新登录查询历史，核对批次/周期/操作人/部门/收抄送/结果/错误；普通另一账号不能查前一账号文件或批次。
8. 小屏/低高度/缩放检查表格横滚、日期/筛选、预览和最终按钮；页面轮询4秒、隐藏暂停、最多90轮后可手动刷新，不能把暂停刷新当发送停止。

## 7. 本机证据与未验项

13项隔离测试通过23.43秒：合成周/月新旧部门/人员/指标/收抄送一致；冻结时钟主题HTML一致；合成附件xl/*逐XML一致（含XFD空白格式列及空字符串）；两个周报图表同环境字节一致；原始周/月报解析与正文对照；缺邮箱/无预览/文件变化/邮件配置缺失/越权/双worker/崩溃/不重发覆盖。实际月报所有部门附件源行/表头与Sheet范围核对通过（空字符串按原openpyxl保存后的空白规范化比较）。FakeSMTP验证587先STARTTLS再登录、默认发件人与原MIME/附件、部分拒收为UNKNOWN；另补企微请求体和token缓存隔离验证，结果见工作流。不把合成/模拟发送当真实投递。

旧全量月附件XML对照因原算法巨大空白范围过慢已终止，未声称通过；未改输入表，后续用原业务值/Sheet规则核查实际附件，合成宽格式样本验证优化不改XML。原始HR数据、测试DB、附件、脚本及依赖仅在忽略目录。

前端类型/相关ESLint/注册和状态断言通过，生产构建18.14秒、保留既有大包提示。浏览器Work设置禁用，未绕过；服务器Docker/MySQL DDL、Linux字体显示、真实SMTP/企微投递、历史旧日志回灌未验/未执行。代码推送不是上线，不发未确认申请人的群通知。
