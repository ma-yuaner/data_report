"""Read mail credentials from deployment environment; never from API/DB payloads."""
import json
import time
import urllib.parse
import urllib.request

from .store import MailError


def mail_config(config):
    try:
        method = str(config.get("HR_MAIL_METHOD", "")).strip().lower()
        if method not in {"smtp", "wecom"}:
            raise ValueError()
        if method == "smtp":
            use_ssl = config.get("HR_MAIL_SMTP_USE_SSL", True)
            if not isinstance(use_ssl, bool):
                normalized = str(use_ssl).strip().lower()
                if normalized not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                    raise ValueError()
                use_ssl = normalized in {"1", "true", "yes", "on"}
            value = {
                "method": method,
                "smtp_host": str(config.get("HR_MAIL_SMTP_HOST", "")).strip(),
                "smtp_port": int(config.get("HR_MAIL_SMTP_PORT", 465)),
                "smtp_use_ssl": use_ssl,
                "smtp_user": str(config.get("HR_MAIL_SMTP_USER", "")).strip(),
                "smtp_password": str(config.get("HR_MAIL_SMTP_PASSWORD", "")),
                "smtp_from": str(config.get("HR_MAIL_SMTP_FROM", "")).strip(),
                "sender_name": str(config.get("HR_MAIL_SENDER_NAME", "人事部自动报表")).strip(),
            }
            required = ("smtp_host", "smtp_user", "smtp_password")
        else:
            value = {
                "method": method,
                "corp_id": str(config.get("HR_MAIL_WECOM_CORP_ID", "")).strip(),
                "agent_id": str(config.get("HR_MAIL_WECOM_AGENT_ID", "")).strip(),
                "app_secret": str(config.get("HR_MAIL_WECOM_APP_SECRET", "")),
            }
            required = ("corp_id", "agent_id", "app_secret")
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required):
            raise ValueError()
        if any("\r" in str(v) or "\n" in str(v) for v in value.values()):
            raise ValueError()
        if method == "smtp":
            if type(value.get("smtp_use_ssl", True)) is not bool or not 1 <= int(value.get("smtp_port", 465)) <= 65535:
                raise ValueError()
            value["smtp_from"] = value.get("smtp_from") or value["smtp_user"]
            value["sender_name"] = value.get("sender_name") or "人事部自动报表"
        return value
    except (ValueError, TypeError, KeyError):
        raise MailError("邮件环境变量未配置或格式不完整，请由部署人核对；无需在页面填写密码", "HR_MAIL_CONFIG_NOT_READY", 503) from None


def sender(config):
    # Imports only after explicit sending, never network-probe on page load.
    from .legacy.email_sender import SMTPSender, WeComMailer
    value = mail_config(config)
    if value["method"] == "smtp":
        return SMTPSender(value)

    class EnvironmentWeComMailer(WeComMailer):
        def _get_access_token(self):
            now = time.time()
            if self._access_token and now < self._token_expires_at:
                return self._access_token
            query = urllib.parse.urlencode({"corpid": value["corp_id"], "corpsecret": value["app_secret"]})
            with urllib.request.urlopen(self.TOKEN_URL + "?" + query, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("errcode") != 0 or not result.get("access_token"):
                raise MailError("企微邮件认证失败", "HR_MAIL_AUTH_FAILED", 503)
            self._access_token = result["access_token"]
            self._token_expires_at = now + int(result.get("expires_in", 7200)) - 300
            return self._access_token

    return EnvironmentWeComMailer()


def send_result(mailer, item, attachment):
    """Keep original MIME/recipients; redact provider diagnostics and avoid retries."""
    try:
        result = mailer.send_mail(to=item["to"], cc=item["cc"], subject=item["subject"], html_body=item["html_body"], attachments=[str(attachment)])
    except Exception:
        return "UNKNOWN", "HR_MAIL_DELIVERY_UNCONFIRMED：通道中断，发送结果未知，请核实后再决定是否重发"
    if result.get("success"):
        return "SUCCESS", ""
    # The legacy adapters catch network exceptions. A false result is not proof
    # that no recipient accepted the message. Never automatically retry it.
    if "认证失败" in str(result.get("error", "")):
        return "FAILED", "HR_MAIL_AUTH_FAILED：邮件认证失败，请检查服务器环境变量"
    return "UNKNOWN", "HR_MAIL_DELIVERY_UNCONFIRMED：邮件通道未确认成功，请核实收件情况；未自动重发"
