"""Trusted server-side bridges to existing account and notification components."""
from .policy import AdmError


def configure_providers(config, manager):
    from ..monitoring import MonitoringService

    def user(user_id):
        result = manager.store.get_user_by_id(int(user_id))
        if result and "adm.scope.team" in set(result.get("permissions") or []):
            result["managed_user_ids"] = manager.store.list_managed_member_ids(int(user_id), "adm")
        return result

    def options(actor):
        try:
            rows = MonitoringService(config).list_notify_endpoints(actor)
            return [{"id": str(row["id"]), "name": row["endpointName"]} for row in rows if row["status"] == "ACTIVE" and row["channel"] == "WECOM"]
        except Exception as error:
            raise AdmError("监控中心通知端点暂不可用，请先完成原有端点配置", 503) from error

    def endpoint(actor, endpoint_id):
        try:
            return MonitoringService(config).resolve_notification_endpoint(actor, endpoint_id)
        except Exception as error:
            raise AdmError("端点不存在、停用或不可读，请重新核对批准", 503) from error

    def mention(actor, recipient):
        binding = manager.employee_binding(actor, int(recipient))
        employee = binding.get("employee") or {}
        return employee.get("wechatId") if binding.get("status") == "ACTIVE" else None

    config["ADM_USER_RESOLVER"] = user
    config["ADM_ENDPOINT_OPTIONS"] = options
    config["ADM_ENDPOINT_RESOLVER"] = endpoint
    config["ADM_NOTIFICATION_IDENTITY"] = mention
