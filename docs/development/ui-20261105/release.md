# 测试发版记录

## 后续明确合并授权（2026-11-05）

用户在247执行`git pull --ff-only origin main`未取得UI改动后，明确要求将独立分支合并main；本次授权替代此前“不自动合并”的限制，范围为本次UI改动及交付记录，推送到此前已明确授权的GitLab/GitHub两个仓库main。不包含服务器部署或群通知，用户此前“不发群通知”的决定继续有效。

合并前实际fetch两个远端：origin/main与github/main均为`4ed3145e51d89992afcb47a66965c0f29869bf91`，UI功能提交`803f590`为直接后继，无分叉、无冲突。采用非强制快进推送；不切换或修改原worktree脏main，不覆盖用户已有改动。代码与已通过验证时一致，复用既有类型/lint/隔离回归；构建权限失败与浏览器未验限制仍保留。实际两端main推送结果以本地release-receipt.json与最终交付为准，以下记录描述先前独立分支阶段。

2026-11-05，用户明确授权本次测试发版。目标沿用项目约定测试247；本次交付独立分支`ui/baseline-20261105`的源码，保留不自动合并或部署的约定。登录、修改密码、数据资产及共用认证外壳为当前源码范围；全站推广及指标全量建设不在已完成范围。

## 发布前验证

复用本分支类型、相关ESLint、74组件注册、认证接口/CSRF/路由SHA保留与数据资产原目录接口验证。新增发版回归实际执行：

```powershell
node .test-artifacts/ui-login-20261105/check.cjs
node .test-artifacts/ui-baseline-20261105/assets-check.cjs
git -c safe.directory=D:/data_center_code/data_report_ui_20261105 diff --check
```

以上均退出0。仅隔离API/路由替身及真实编译的Vue setup，不是浏览器或真实服务器登录。

用户本次发版授权后，将构建命令提升到沙箱外执行，使用独立TEMP/TMP目录，确认是否为此前沙箱限制；仍失败：Vite 7.3.6转换4048模块，在rendering chunks的esbuild-transpile阶段删除临时文件Access is denied，19.85s，退出1。日志`.test-artifacts/ui-login-20261105/release-build.log`。相比此前仅改变执行权限和临时目录，未改编译目标、压缩、依赖或测试预期。原运行命令为bundled Python subprocess执行`node node_modules/vite/bin/vite.js build`，stdout/stderr写上述UTF8日志。

达到同类问题两次修复仍未通过的停止条件，不再重试或绕过构建阶段。没有可交付为通过的构建包。后续需环境维护人处理esbuild临时文件删除权限，环境明确改变后再构建。

## 发布边界与待验

- 仅提交和推送已核对的本任务文件到GitLab origin及GitHub github的独立分支，实际commit/push结果见最终交付及本地`.test-artifacts/ui-login-20261105/release-receipt.json`；不把计划写成成功。
- 原main用户已有改动保留；不合并到main，不更新247服务器，不触发部署、DDL、业务写入或真实邮件。
- 浏览器按用户选择保持关闭；无前后截图及真实页面验收。
- 本次申请人尚待用户确认，未确认不发送发版群通知；通知复用项目既有qa_wecom_delivery.py，只发一次且明确“独立分支已推送、构建失败、待部署”。不得用“测试通过”概括本次全部验证。
- 默认不查询或等待CI，现有CI配置不变。

先前阶段文档的“未提交推送”是对应阶段时间点状态；本记录及最终回执为当前发布状态依据，不代表全站任务验收完成。
