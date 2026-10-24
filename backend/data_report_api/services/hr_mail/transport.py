"""Read-only Secret credentials; never accept credentials from API/DB payloads."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .store import MailError


def secret_config(config):
    try:
        path = Path(config.get("HR_MAIL_SECRET_FILE", "/run/secrets/hr_mail_config"))
        if not path.is_file() or path.stat().st_size > 16384:
            raise ValueError()
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("method") not in {"smtp", "wecom"}:
            raise ValueError()
        required = ("smtp_host", "smtp_user", "smtp_password") if value["method"] == "smtp" else ("corp_id", "agent_id", "app_secret")
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required):
            raise ValueError()
        if any("\r" in str(v) or "\n" in str(v) for v in value.values()):
            raise ValueError()
        if value["method"] == "smtp":
            if type(value.get("smtp_use_ssl", True)) is not bool or not 1 <= int(value.get("smtp_port", 465)) <= 65535:
                raise ValueError()
            value["smtp_port"] = int(value.get("smtp_port", 465))
            value["smtp_from"] = value.get("smtp_from") or value["smtp_user"]
        return value
    except (OSError, ValueError, TypeError, KeyError):
        raise MailError("邮件Secret未挂载或格式不完整，请由部署人核对；无需在页面填写密码", "HR_MAIL_SECRET_NOT_READY", 503) from None


def sender(config):
    # Imports only after explicit sending, never network-probe on page load.
    from .legacy.email_sender import SMTPSender, WeComMailer
    value = secret_config(config)
    if value["method"] == "smtp":
        return SMTPSender(value)

    class SecretWeComMailer(WeComMailer):
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

    return SecretWeComMailer()


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
        return "FAILED", "HR_MAIL_AUTH_FAILED：邮件认证失败，请检查Secret"
    return "UNKNOWN", "HR_MAIL_DELIVERY_UNCONFIRMED：邮件通道未确认成功，请核实收件情况；未自动重发"
