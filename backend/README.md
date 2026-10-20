# 后端

入口为`app.py`，通过`data_report_api.create_app`创建Flask应用。Docker以Gunicorn运行`app:app`，API端口5160。项目根`.env`提供本地环境变量，模板为[.env.example](../.env.example)。

HTTP领域见`data_report_api/api/`，统一注册在`routes.py`；认证适配仍在`auth_routes.py`。服务见`services/`，共享契约见`shared/`，任务见`jobs/`。详见[贡献指南](../CONTRIBUTING.md)。

```powershell
python -m pip install -r requirements-dev.txt
python app.py
python -m pytest -q
```

后台进程兼容入口：`python -m data_report_api.risk_upload_worker`、`python -m data_report_api.target_management_scheduler`。启动会使用环境配置连接数据源，只在获授权的开发/部署环境运行。测试通过TestConfig和隔离替身验证，不以测试结果推断生产部署。
