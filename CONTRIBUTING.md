# 开发与结构约定

先读[AGENTS.md](AGENTS.md)、[项目入口](docs/agent/README.md)和[仓库边界](docs/development/repositories.md)。五类角色的职责与交接以AGENTS.md为准。

## 目录与依赖

- `backend/data_report_api/api/`：按领域组织HTTP适配，参数、响应和状态码；由`routes.py`统一注册，保留`api.*`端点名。
- `backend/data_report_api/services/`：既有应用服务与数据访问。逐域迁移，避免为目录整齐一次搬动所有文件。
- `backend/data_report_api/shared/`：明确公共契约的日期、权限等工具；不依赖API、应用工厂、服务或任务。
- `backend/data_report_api/jobs/`：应用内任务实现；根级worker/scheduler保留启动兼容入口。
- `frontend/src/features/<domain>/`：已迁移领域的页面、API、组合式状态和局部展示配置；`views/`与`api/`允许保留显式兼容入口。
- `frontend/src/components/`：跨领域复用组件；`utils/`不依赖页面、路由、store或领域；新领域不得反向依赖旧兼容入口。
- `backend/tests/`：服务与HTTP回归；`scripts/`：只读工程检查。

依赖方向：应用入口 → HTTP领域 → 服务/任务 → 共享工具与数据访问。frontend领域 → 公共组件/HTTP客户端。跨模块使用公开符号，禁止引用其他模块的`_private`函数。迁移前后保持路由、权限、响应字段、日期默认值和范围限制兼容。

Python文件用snake_case、Vue组件用PascalCase、TypeScript模块用camelCase；目录用小写连字符。Python包用`__init__.py`声明公共导出，前端领域入口显式导出，避免通配导出。拆分依据职责与依赖，行数仅作为审查提示。

## 本地检查

后端Python 3.12，前端Node 22。依赖分别由`backend/requirements-dev.txt`和`frontend/package-lock.json`管理。

```powershell
python -m pip install -r backend/requirements-dev.txt
python scripts/check_backend_lint.py
python -m ruff format --check backend/data_report_api/api backend/data_report_api/shared backend/data_report_api/jobs scripts
python scripts/check_architecture.py
python -m pytest -q
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run type-check
npm --prefix frontend run check:components
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

全量错误级lint与依赖检查用于整个源码。监控服务已有两处F821以路径、错误、源行精确登记在`scripts/backend-lint-baseline.json`，新增问题仍失败，已修复基线必须删除；后续专项修复需要行为回归。格式门禁先覆盖新领域和工程配置；历史大文件仅在职责迁移时格式化，避免无关格式差异。详见[结构优化记录](docs/development/structure-optimization.md)。格式修复使用`ruff format <文件>`或`npm --prefix frontend run format`。

可在激活开发虚拟环境后执行`pre-commit install`，启用本地钩子；CI始终执行同样的门禁，钩子安装不作为协作前提。Windows测试临时目录若受历史权限影响，可使用新建的`.test-artifacts`子目录，勿清理无关目录。

本次任务的代码、验证、剩余项记入`docs/agent/workstreams.md`；提交只包含当前范围，推送两个已核对远端并查询实际CI结果。
