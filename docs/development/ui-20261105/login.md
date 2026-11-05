# 登录及认证组件UI迭代

任务：UI-LOGIN-20261105。分支`ui/baseline-20261105`，worktree `D:/data_center_code/data_report_ui_20261105`。状态：本组源码实现与隔离验证完成，真实视觉/交互未验；不等于全站完成。

## 本轮授权与方法

用户要求先不开启浏览器，继续优化登录界面及相关UI组件、图标；已确认cron为笔误，不涉及定时任务。沿用frontend-design、chief-of-staff及项目绘景/星桥/明鉴规范，由主会话实施，未启动独立子代理。参谋长用于范围、证据和交接；UI规范用于设计判断，不代表外部设计工具或浏览器已运行。

保持现有Vue 3、TypeScript、Ant Design Vue，复用已安装Ant图标，不引入字体、图片、依赖或静态业务样例。蓝色强调、深蓝背景和白色表单保持既有风格，减少渐变与重阴影，使用更清晰的文字、对齐和间距。本轮授权仅覆盖登录及相邻认证组件，不推广业务页面。

## 改动与保留项

| 文件 | 改动 | 保留 |
|---|---|---|
| `frontend/src/components/AuthFrame.vue` | 提取两页共有的认证外壳、标题、图标位、状态/页脚插槽；样式局部化；320px窄屏及低高度布局；焦点、忙碌和标题语义 | 不查询API、不决定权限、不保存或处理凭据 |
| `frontend/src/views/LoginView.vue` | 用户名/密码图标；显式标签与输入框关联；错误播报；提交中禁止编辑与重复请求；未配置时阻止键盘路径提交 | 原标题、说明、警告、字段、占位文案、64字符上限、自动填充、密码显示/隐藏、登录入口、会话时限文案、原始凭据传参、安全跳转函数、首次改密及配置状态失败的原处理 |
| `frontend/src/views/ChangePasswordView.vue` | 复用同一外壳和安全图标；字段显式标签；错误关联；保存中防重复及暂禁取消/退出，失败保留原输入 | 普通/首次登录标题、原三个字段、密码说明、确认不一致文案、服务端密码规则、保存反馈、普通取消、首次退出、成功/退出跳转 |
| `frontend/src/styles/main.css` | 移除12条仅由上述两页使用的旧认证规则，转入AuthFrame局部样式 | 非认证CSS逐行对照一致；数据资产的先前改动独立保留 |

输入内容仍只在页面原有ref中，不持久化密码；不在日志中输出凭据。接口、CSRF、auth store、后端权限、路由守卫和会话策略不变。本轮没有添加“记住密码”、注册、找回密码或第三方登录等新功能。

## 基线与实际证据

改动前在`.test-artifacts/ui-login-20261105/`保存`source-before.zip`及`fingerprints-before.json`，包括LoginView、ChangePasswordView及原全局CSS。此前全量源码基线也保持完整。未取得截图，遵从本次用户不开启浏览器的选择。

工作目录为本worktree；Node v24.18.0，复用原worktree已安装node_modules目录联接，没有安装或升级依赖。所有测试与证据脚本留本地忽略目录。

| 检查 | 命令/方法 | 实际结果 |
|---|---|---|
| 类型 | frontend内`node node_modules/vue-tsc/bin/vue-tsc.js -b --pretty false` | 退出0，无诊断 |
| lint | frontend内`node node_modules/eslint/bin/eslint.js src/components/AuthFrame.vue src/views/LoginView.vue src/views/ChangePasswordView.vue --max-warnings=0` | 退出0 |
| 组件注册 | frontend内`node scripts/check-ant-components.mjs` | 退出0，74个页面组件通过 |
| SFC及交互 | 根目录`node .test-artifacts/ui-login-20261105/check.cjs` | 退出0；实际三个SFC模板/样式编译、Login/ChangePassword编译setup的状态与事件处理检查通过；API、router为隔离替身 |
| 认证边界 | SHA256对比首阶段inventory.json | auth store、auth API、HTTP/CSRF及router四文件完全未变 |
| CSS边界 | 比较本轮source-before.zip与当前CSS | 只移除`.auth-*`专用规则，其余逐行一致 |
| 差异空白 | `git -c safe.directory=D:/data_center_code/data_report_ui_20261105 diff --check` | 退出0 |
| 生产构建 | 未重试 | 沿用首阶段两次esbuild临时文件删除Access is denied的停止记录；环境未解除，不报告构建通过 |
| 浏览器/真实认证 | 未执行 | 用户选择不开启浏览器；无截图、实测窄屏/中文/焦点/密码显示操作/自动填充或真实服务器登录结果 |

隔离覆盖：空字段不发请求、未初始化时提交受阻、重复提交只发一次、凭据原样传参、认证失败保留输入、成功原路返回、外部及双斜杠重定向沿用原回退、首次改密、配置状态失败原逻辑、两次新密码不一致、改密失败保留输入、改密成功及退出。覆盖不代表后端鉴权或真实会话通过。

本地脚本首跑未等完整登录Promise结束就发下一次请求，触发正确的防重守卫后出现夹具空队列；改为等待实际submit Promise后通过。只修夹具时序，未放宽业务判断或删断言。

## 后续验收

浏览器保持关闭时本组不再增加功能。将来用户启用后，先用归档版本补旧页面基线，再保存本版两页截图，覆盖1440/1280/1024与390/320宽、低高度及125%/150%缩放；实操中文输入、密码显示/隐藏、自动填充、Tab焦点/回车、错误/重试、首次改密/退出及普通取消。不得用静态编译或源码尺寸声明真实布局通过。

全站推广、指标全量定义及实库复算状态继续见[首阶段记录](README.md)，本轮不将它们标完成。不自动合并或部署；本组尚未提交推送。
