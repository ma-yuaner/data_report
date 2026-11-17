# 登录页品牌定稿与服务端图形验证码

任务 LOGIN-BRAND-CAPTCHA-20261117，用户2026-11-17批准最后一张设计图并授权正式页面及图形验证码接入。基线 `fat_cy / 9d5dc13`，保留工作区已有 ADM、财务等无关修改。主会话执行绘景、星桥、磐石、明鉴职责，未启动子代理；明策职责按明确需求裁剪。L4评估：认证跨层变更，保留服务端反例与并发验证；无本任务委派授权，采用主会话自检，独立审查未完成，不称L4通过。

## 现状到目标及需求追溯

| 需求 | 现状及依据 | 实现与验收 |
|---|---|---|
| L1 用户批准的视觉 | 原 LoginView 使用 AuthFrame，深蓝居中账号密码页 | LoginView 独立浅色背景、150px左上公司字标、无顶部白条/标题/右侧说明、左侧文案与数据轨道、右侧白色表单；业务页面与改密页未改主题 |
| L2 系统图标 | 原认证区为图表图标 | 原公司图标组合数据柱，资产在 frontend/src/assets/brand；作为表单系统图标与 favicon。公司图片保持原始比例，顶部通过 multiply 混合白底 |
| L3 图形验证码 | 原登录接口仅 username/password | 公开 GET /api/auth/captcha 返回 challengeId、PNG data URL、expiresIn；POST /api/auth/login 必传 challengeId/captcha，服务端校验后才进入原账号认证 |
| L4 认证契约 | 原首次强制改密、安全回跳、CSRF、会话及账号锁定 | 原始用户名/密码传参、原安全回跳函数和首次改密分支保留；原认证19项回归通过；验证码不替代任何身份权限检查 |
| L5 失败恢复 | 原失败保留输入 | 验证码错误、过期、认证失败后获取新挑战并清空旧码，保留用户名/密码；加载失败可点重试，图片失败提示，提交中禁编辑/防重，离页不回写 |

用户批准的是视觉图，不直接将生成图片作为整页背景；正式页面使用真实输入、组件与矢量轨道。桌面/760px窄屏、360px小宽度与低高度规则已实现，但浏览器禁用，真实尺寸与设计还原度尚未验收。

## 验证码契约

- 4位随机字符，不含易混淆的0/1/I/O，大小写不敏感；有效期180秒。
- HttpOnly、SameSite=Strict 的 `data_report_captcha` Cookie 绑定浏览器，Path=/api/auth，Secure沿用 AUTH_COOKIE_SECURE。回答只出现在PNG像素中，不下发明文/可逆答案令牌。
- 每浏览器仅一个有效挑战：刷新使旧码失效；同浏览器多标签页共享此规则。匹配当前 challengeId 的一次验证会先原子删除再校验答案，错误、成功或后续密码错误均不能重用。未知ID/跨浏览器请求不消费对方挑战。
- 每浏览器每60秒最多20次签发；连接来源地址每60秒最多120次。来源使用 request.remote_addr，忽略任意 X-Forwarded-For，避免伪造绕过。反向代理部署下该限额可能成为代理出口合计；如并发需求超出，需由部署方配置可信代理边界后再调整，不能直接信任公开转发头。
- 活跃挑战最多10000条，签发时清理到期挑战/计数；无后台定时器。签发与单次消费使用 SQLite BEGIN IMMEDIATE，同一主机的 Gunicorn workers 共用文件。过期失败关闭；缓存不可写/不可用返回503，不回退免验证码。签发过频返回429。
- captcha/login响应（含失败）禁止缓存。验证码认证错误使用400与 CAPTCHA_INVALID/CAPTCHA_EXPIRED，限流/故障使用 CAPTCHA_RATE_LIMIT/CAPTCHA_UNAVAILABLE，均保留中文重试提示。
- 无短信服务、未新增短信验证码登录；纯图形挑战不提供非视觉替代，此为当前可访问性限制，后续需要独立认证方案支持。

## 本地临时存储与中文字段字典

默认 `backend/var/auth-captcha/challenges.sqlite3`，容器为 `/app/var/auth-captcha/challenges.sqlite3`，可用 AUTH_CAPTCHA_ROOT 指定可写本地目录。沿用已安装SQLite/Pillow，无新增依赖，无MySQL DDL。SQLite不支持持久表列COMMENT；中文含义保存在本受版本控制文档与源码注释，普通SQL行注释不是元数据注释。

`login_captcha`：浏览器当前短期挑战，每行一个浏览器的最新挑战；不能复用正式会话表，因为签发发生在未登录阶段。无用户表关联，最多一对一浏览器摘要，无外键/分区；主键用于查找和刷新覆盖。

| 字段 | 中文含义 | SQLite类型/约束 | 来源/时间语义 |
|---|---|---|---|
| browser_hash | 随机浏览器Cookie的SHA256摘要，避免保存Cookie原值 | TEXT PRIMARY KEY；业务写入总是非空 | 32随机字节的URL安全编码后取摘要 |
| challenge_id | 当前挑战的随机标识，不携带答案 | TEXT NOT NULL | 24随机字节URL安全编码 |
| answer_hash | 挑战ID拼接大写答案的SHA256摘要 | TEXT NOT NULL | 服务端计算，不下发、不记日志 |
| expires_at | 本条挑战失效时刻 | INTEGER NOT NULL，无默认 | UTC Unix秒，签发时刻+180；当前时刻大于等于即失效 |

`login_captcha_rate`：短期签发频率窗口，每行一个浏览器或连接来源范围；与用户无关联，主键用于固定窗口计数，过期清理，无外键/分区。

| 字段 | 中文含义 | SQLite类型/约束 | 来源/时间语义 |
|---|---|---|---|
| scope_hash | 带browser/peer前缀范围的SHA256摘要 | TEXT PRIMARY KEY；业务写入总是非空 | 浏览器Cookie或连接来源地址，不保存IP原值 |
| hits | 本窗口成功提交的签发计数 | INTEGER NOT NULL，无默认 | 初始1，每次事务递增；窗口超过阈值拒绝并回滚 |
| expires_at | 固定窗口失效时刻 | INTEGER NOT NULL，无默认 | 首次签发UTC Unix秒+60，后续递增不延长 |

SQL完整源码在 `backend/data_report_api/services/login_captcha.py`，含DDL与参数化增删查改，资产库同步归档 AUTH-CAPTCHA-001；这是应用支撑缓存，不是经营指标。SQLite默认文本比较区分大小写；答案在比较前仅对验证码大写化，不变换密码。无金额、币种或统计公式。

## 发布与回退

前后端必须同批更新：旧前端缺challenge字段会被拒绝。缓存目录由应用进程自动创建；现有Dockerfile已使/app/var归appuser，无须新增生产表或手工SQL。容器重建丢失挑战时用户刷新即可，不影响既有正式登录会话。多个独立容器/主机不能各用独立文件部署本方案；需共享同机本地文件或另行提供可靠共享缓存，不能使用不支持SQLite锁的网络文件系统。

本次未执行服务器/容器部署。回退需同时回退登录页、auth API/store、后端路由及验证码服务；临时缓存不包含业务历史，不迁移或回填用户资料，不动账号密码表。

## 实际验证

- 前端 vue-tsc 退出0；四个相关文件 ESLint退出0。
- Vite生产构建退出0，最终版本30.03秒；使用bundled Python subprocess及任务专用TEMP，产物在 `.test-artifacts/login-brand-captcha-20261117/dist`，保留原有大包警告。
- 原认证/通讯录回归19项通过，包含首次改密、CSRF、会话、锁定、权限；测试辅助函数改为获取并提交真实挑战（测试固定生成字符，真实服务端校验不绕过）。
- 验证码专项11项通过，真实Flask test_client、隔离MemoryAuthStore及SQLite：字段元数据/UTF-8与摘要存储、PNG尺寸/无答案字段/Cookie/缓存、缺验证码拒绝、错码单次消费、大小写、跨浏览器、刷新失效、到期边界、密码失败后不复用、两个服务实例并发仅一次成功、限流及伪造转发头、存储故障关闭、Secure Cookie。
- 前端SFC模板/样式编译及隔离setup检查通过：原始凭据、空输入、验证码契约、认证失败刷新与保留密码、刷新防重、图片失败/网络重试、提交防重、站内回跳/外部回退、首次改密、未初始化守卫、卸载后不回写。
- 全站组件登记受既有 `AdmDetailView.vue` 的未登记 `a-typography-text` 阻断，本次所用Input/Button/Alert已有映射；未借本任务修改ADM。
- 浏览器仍按AGENTS的禁用记录跳过，未伪造截图；真实视觉/键盘/中文输入/密码管理器、实际HTTP代理与Secure策略、正式账号登录、目标服务器权限/容量均未验。pytest缓存目录权限警告不影响30项退出0。

前端隔离夹具修正了执行目录、CommonJS exports重名、路由快照以及跨VM Error原型的问题；未修改断言预期或放宽业务限制。源码、构建、隔离验证、部署与业务验收分层记录。

复盘：本次沿用已有品牌与认证方法，无新增通用方法回传；未修改MYE，无外部通知，无CI查询。独立审查未完成。

最终版本验证汇总在 `.test-artifacts/login-brand-captcha-20261117/checks.json`；后端30项通过（31.68秒），README/API索引239条检查通过，前端隔离SFC检查、类型、lint和最新生产构建均退出0。最终pytest禁用缓存插件，避免无关缓存目录警告。登录页局部ConfigProvider固定浅色与青色交互，防止退出深色业务页后登录控件沿用深色。

## 公司GitLab main集成（2026-11-17）

用户明确授权将本分支合入公司GitLab analytics/data_report 的main，且不得带入其他任务。基于远端main `c59f8821481a441f1e16079712adf2fb3250da42`，在独立worktree进行真实双亲合并；本功能分支相对该main仅一笔新增提交dbc0a21，不包含额外历史变更。相对main核对仅20个本任务文件，原fat_cy工作区不切分支、不暂存、不覆盖。

README、接口索引、决策及工作流的4处文件冲突均保留main已有内容，再加入本任务增量。接口索引重新生成并验证为274条。合并版本的原认证与验证码专项30项、前端类型/ESLint/SFC状态检查均通过。独立worktree首轮构建出现esbuild临时文件删除Access is denied，改用本任务此前已验证的TEMP目录后构建通过（23.81秒），未修改业务源码或依赖来绕过检查。保留既有大包警告；浏览器/真实账号及部署仍未验。

本次仅授权公司GitLab main，不推送GitHub，不部署、不发消息、不查询CI；远端提交回读结果另存本地发布回执。
