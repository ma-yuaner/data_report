"""
邮件发送模块
支持两种发送方式：
1. SMTP 协议发送（传统方式）
2. 企业微信邮件 API（推荐，无需SMTP配置）

界面配置优先：当用户通过界面配置了SMTP设置时，使用界面配置代替settings.py中的配置
"""

import smtplib
import ssl
import json
import tempfile
import os
import time
import base64
import re
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Optional, Callable

from .settings import (
    SMTP_HOST, SMTP_PORT, SMTP_USE_SSL, SMTP_USER,
    SMTP_PASSWORD, SMTP_FROM, SENDER_NAME,
    EMAIL_SEND_METHOD, WECOM_CORP_ID, WECOM_AGENT_ID, WECOM_APP_SECRET
)


def is_smtp_configured() -> bool:
    """检查 SMTP 是否已配置（检查settings.py）"""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def test_smtp_connection() -> tuple[bool, str]:
    """
    测试 SMTP 连接是否可用。

    返回: (是否成功, 消息)
    """
    if not is_smtp_configured():
        return False, "SMTP 未配置，请在 config/settings.py 中填写企业邮箱信息"

    try:
        if SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.ehlo()
                if SMTP_PORT == 587:
                    server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
        return True, "SMTP 连接测试成功"
    except smtplib.SMTPAuthenticationError:
        return False, "认证失败：用户名或密码错误"
    except smtplib.SMTPException as e:
        return False, f"SMTP 错误：{e}"
    except Exception as e:
        return False, f"连接失败：{e}"


def test_smtp_connection_ui(settings: dict) -> tuple[bool, str]:
    """
    使用界面配置测试 SMTP 连接。

    参数:
        settings: 包含 smtp_host, smtp_port, smtp_use_ssl, smtp_user, smtp_password 的字典

    返回: (是否成功, 消息)
    """
    try:
        host = settings.get("smtp_host")
        port = settings.get("smtp_port", 465)
        use_ssl = settings.get("smtp_use_ssl", True)
        user = settings.get("smtp_user")
        password = settings.get("smtp_password")

        if not host or not user or not password:
            return False, "SMTP 配置不完整"

        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                if port == 587:
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
        return True, "SMTP 连接测试成功"
    except smtplib.SMTPAuthenticationError:
        return False, "认证失败：用户名或密码错误"
    except smtplib.SMTPConnectError:
        return False, "连接失败：无法连接到服务器"
    except TimeoutError:
        return False, "连接超时：服务器无响应"
    except smtplib.SMTPException as e:
        return False, f"SMTP 错误：{e}"
    except Exception as e:
        return False, f"连接失败：{e}"


def is_smtp_configured_ui(settings: dict) -> bool:
    """检查界面配置的SMTP是否完整"""
    return bool(
        settings.get("smtp_host") and
        settings.get("smtp_user") and
        settings.get("smtp_password")
    )


class SMTPSender:
    """
    通过 SMTP 协议发送邮件。
    支持：HTML 正文、附件、内嵌图片。

    如果提供了 ui_settings 参数，则使用界面配置；否则使用 config/settings.py 中的配置
    """

    def __init__(self, ui_settings: dict = None):
        self._connected = False
        self._ui_settings = ui_settings

    def _get_connection(self):
        """建立或复用 SMTP 连接"""
        if self._connected:
            return

        # 优先使用界面配置
        if self._ui_settings:
            host = self._ui_settings.get("smtp_host")
            port = self._ui_settings.get("smtp_port", 465)
            use_ssl = self._ui_settings.get("smtp_use_ssl", True)
            user = self._ui_settings.get("smtp_user")
            password = self._ui_settings.get("smtp_password")
        else:
            host = SMTP_HOST
            port = SMTP_PORT
            use_ssl = SMTP_USE_SSL
            user = SMTP_USER
            password = SMTP_PASSWORD

        if use_ssl:
            context = ssl.create_default_context()
            self._server = smtplib.SMTP_SSL(
                host, port, context=context, timeout=20
            )
        else:
            self._server = smtplib.SMTP(host, port, timeout=20)
            self._server.ehlo()
            if port == 587:
                self._server.starttls()
                self._server.ehlo()

        self._server.login(user, password)
        self._connected = True

    def send_mail(
        self,
        to: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[str]] = None,
        image_attachments: Optional[List[dict]] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        sender_name: str = None,
    ) -> dict:
        """
        发送单封邮件。

        参数:
            to: 收件人邮箱
            subject: 邮件主题
            html_body: HTML 格式邮件正文
            attachments: 附件文件路径列表
            image_attachments: 内嵌图片 [{"cid": "chart1", "bytes": b"..."}]
            cc: 抄送
            bcc: 密送
            sender_name: 发件人显示名

        返回:
            {"success": True} 或 {"success": False, "error": "错误信息"}
        """
        try:
            self._get_connection()

            # 确定发件人地址
            if self._ui_settings and self._ui_settings.get("smtp_from"):
                from_addr = self._ui_settings.get("smtp_from")
            else:
                from_addr = SMTP_FROM or SMTP_USER

            # 确定发件人显示名
            if self._ui_settings and self._ui_settings.get("sender_name"):
                display_name = self._ui_settings.get("sender_name")
            else:
                display_name = sender_name or SENDER_NAME

            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = f"{display_name} <{from_addr}>"
            msg["To"] = to
            if cc:
                msg["Cc"] = cc
            if bcc:
                msg["BCC"] = bcc

            # HTML 正文
            body_alternative = MIMEMultipart("alternative")
            text_part = MIMEText(
                "您的邮件客户端不支持 HTML 格式，请使用支持 HTML 的客户端查看。",
                "plain", "utf-8"
            )
            html_part = MIMEText(html_body, "html", "utf-8")
            body_alternative.attach(text_part)
            body_alternative.attach(html_part)
            msg.attach(body_alternative)

            # 处理内嵌图片
            embedded_body = html_body
            if image_attachments:
                for img in image_attachments:
                    cid = img["cid"]
                    img_bytes = img["bytes"]

                    # 写入临时文件
                    temp_img_path = os.path.join(
                        tempfile.gettempdir(), f"hr_tool_{cid}.png"
                    )
                    with open(temp_img_path, "wb") as f:
                        f.write(img_bytes)

                    img_part = MIMEApplication(img_bytes, _subtype="png")
                    img_part.add_header(
                        "Content-Disposition", "inline",
                        filename=f"{cid}.png"
                    )
                    img_part.add_header(
                        "Content-ID", f"<{cid}>"
                    )
                    img_part.add_header(
                        "Content-Transfer-Encoding", "base64"
                    )
                    msg.attach(img_part)

                    # 替换 HTML 中的 base64 src 为 cid:src
                    embedded_body = embedded_body.replace(
                        f'src="data:image/png;base64,',
                        f'src="cid:{cid}"'
                    )

            # 重新附加处理后的 HTML（替换了 cid 引用）
            if image_attachments:
                msg.pop(-1)  # 移除之前附加的原始 html_part
                html_part_new = MIMEText(embedded_body, "html", "utf-8")
                body_alternative.pop(-1)
                body_alternative.attach(html_part_new)

            # 添加附件
            if attachments:
                for path in attachments:
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            filename = os.path.basename(path)
                            part = MIMEApplication(f.read(), _subtype="octet-stream")
                            part.add_header(
                                "Content-Disposition",
                                "attachment",
                                filename=("gbk", "", filename)
                            )
                            msg.attach(part)

            # 构建收件人列表
            recipients = [to]
            if cc:
                # 同时支持分号和逗号分隔
                for part in re.split(r'[;,]', cc):
                    if part.strip():
                        recipients.append(part.strip())
            if bcc:
                recipients += bcc.split(",")

            refused = self._server.sendmail(
                from_addr,
                recipients,
                msg.as_bytes() if hasattr(msg, "as_bytes") else msg.as_string()
            )

            if refused:
                return {"success": False, "error": "SMTP_PARTIAL_RECIPIENTS", "uncertain": True}
            return {"success": True}

        except smtplib.SMTPAuthenticationError:
            return {"success": False, "error": "认证失败：用户名或密码错误"}
        except smtplib.SMTPRecipientsRefused as e:
            return {"success": False, "error": f"收件人被拒绝：{e}"}
        except smtplib.SMTPException as e:
            self._connected = False
            return {"success": False, "error": f"SMTP 错误：{e}"}
        except Exception as e:
            self._connected = False
            return {"success": False, "error": str(e)}

    def send_batch(
        self,
        emails: List[dict],
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """
        批量发送邮件。

        参数:
            emails: 邮件列表，每项包含 to/subject/html_body/attachments
            on_progress: 进度回调 (current, total, dept_name)

        返回:
            {"total": N, "success": M, "failed": K, "details": [...]}
        """
        results = {
            "total": len(emails),
            "success": 0,
            "failed": 0,
            "details": [],
        }

        for i, email in enumerate(emails, 1):
            dept_name = email.get("dept_name", email.get("to", "未知"))
            if on_progress:
                on_progress(i, len(emails), dept_name)

            result = self.send_mail(
                to=email["to"],
                subject=email["subject"],
                html_body=email["html_body"],
                attachments=email.get("attachments", []),
                image_attachments=email.get("image_attachments", []),
                cc=email.get("cc"),
                bcc=email.get("bcc"),
            )

            detail = {
                "dept_name": dept_name,
                "to": email["to"],
                "cc": email.get("cc", ""),
                "success": result["success"],
                "error": result.get("error", ""),
            }
            results["details"].append(detail)

            if result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    def close(self):
        """关闭 SMTP 连接"""
        if self._connected and hasattr(self, "_server"):
            try:
                self._server.quit()
            except Exception:
                pass
            self._connected = False


# ─────────────────────────────────────────────────────────
# 企业微信邮件 API 发送器
# ─────────────────────────────────────────────────────────

def is_wecom_configured() -> bool:
    """检查企业微信 API 是否已配置"""
    return bool(WECOM_CORP_ID and WECOM_AGENT_ID and WECOM_APP_SECRET)


def test_wecom_connection() -> tuple[bool, str]:
    """
    测试企业微信 API 连接是否可用。

    返回: (是否成功, 消息)
    """
    if not is_wecom_configured():
        return False, "企业微信 API 未配置，请在 config/settings.py 中填写企业信息"

    try:
        mailer = WeComMailer()
        token = mailer._get_access_token()
        if token:
            return True, "企业微信 API 连接成功"
        return False, "获取 access_token 失败"
    except Exception as e:
        return False, f"企业微信 API 错误：{e}"


class WeComMailer:
    """
    通过企业微信邮件 API 发送邮件。
    无需 SMTP 配置，使用企业自建应用的 CorpID 和 Secret 认证。
    """

    TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/exmail/app/compose_send"

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _get_access_token(self) -> Optional[str]:
        """获取 access_token，带缓存（有效期2小时）"""
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        url = f"{self.TOKEN_URL}?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("errcode") == 0:
                    self._access_token = data["access_token"]
                    self._token_expires_at = now + data.get("expires_in", 7200) - 300
                    return self._access_token
                else:
                    raise Exception(f"获取 token 失败: {data.get('errmsg')}")
        except urllib.error.HTTPError as e:
            raise Exception(f"HTTP 错误: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"网络错误: {e.reason}")

    def _http_post(self, url: str, data: dict) -> dict:
        """发送 POST 请求"""
        token = self._get_access_token()
        full_url = f"{url}?access_token={token}"

        req_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            full_url,
            data=req_data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            raise Exception(f"HTTP {e.code}: {body}")
        except urllib.error.URLError as e:
            raise Exception(f"网络错误: {e.reason}")

    def send_mail(
        self,
        to: str,
        subject: str,
        html_body: str,
        attachments: Optional[List[str]] = None,
        image_attachments: Optional[List[dict]] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        sender_name: str = None,
    ) -> dict:
        """
        发送单封邮件。

        参数:
            to: 收件人邮箱
            subject: 邮件主题
            html_body: HTML 格式邮件正文
            attachments: 附件文件路径列表
            image_attachments: 内嵌图片（企业微信API暂不支持内嵌图片，将转为附件）
            cc: 抄送
            bcc: 密送
            sender_name: 发件人显示名（企业微信API由应用配置决定，此参数暂未使用）

        返回:
            {"success": True} 或 {"success": False, "error": "错误信息"}
        """
        try:
            to_list = self._parse_email_list(to)
            cc_list = self._parse_email_list(cc) if cc else []
            bcc_list = self._parse_email_list(bcc) if bcc else []

            request_data = {
                "to": {"emails": to_list, "userids": []},
                "cc": {"emails": cc_list, "userids": []},
                "bcc": {"emails": bcc_list, "userids": []},
                "subject": subject,
                "content": html_body,
                "content_type": "html",
                "attachment_list": self._build_attachments(attachments, image_attachments),
            }

            result = self._http_post(self.SEND_URL, request_data)

            if result.get("errcode") == 0:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": result.get("errmsg", "未知错误")
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _parse_email_list(self, emails: str) -> List[str]:
        """解析分号或逗号分隔的邮箱字符串为列表"""
        if not emails:
            return []
        return [e.strip() for e in re.split(r'[;,]', emails) if e.strip()]

    def _build_attachments(
        self,
        attachments: Optional[List[str]],
        image_attachments: Optional[List[dict]]
    ) -> List[dict]:
        """构建附件列表，文件转为 Base64"""
        result = []

        if attachments:
            for path in attachments:
                if os.path.exists(path):
                    filename = os.path.basename(path)
                    with open(path, "rb") as f:
                        content = base64.b64encode(f.read()).decode("utf-8")
                    ext = os.path.splitext(filename)[1].lower()
                    subtype = "octet-stream"
                    if ext == ".txt":
                        subtype = "plain"
                    elif ext == ".pdf":
                        subtype = "pdf"
                    elif ext in (".jpg", ".jpeg"):
                        subtype = "jpeg"
                    elif ext == ".png":
                        subtype = "png"
                    result.append({
                        "file_name": filename,
                        "content": content,
                        "content_type": subtype,
                    })

        if image_attachments:
            for img in image_attachments:
                cid = img.get("cid", "chart")
                img_bytes = img.get("bytes", b"")
                content = base64.b64encode(img_bytes).decode("utf-8")
                result.append({
                    "file_name": f"{cid}.png",
                    "content": content,
                    "content_type": "png",
                })

        return result

    def send_batch(
        self,
        emails: List[dict],
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> dict:
        """
        批量发送邮件。

        参数:
            emails: 邮件列表，每项包含 to/subject/html_body/attachments
            on_progress: 进度回调 (current, total, dept_name)

        返回:
            {"total": N, "success": M, "failed": K, "details": [...]}
        """
        results = {
            "total": len(emails),
            "success": 0,
            "failed": 0,
            "details": [],
        }

        for i, email in enumerate(emails, 1):
            dept_name = email.get("dept_name", email.get("to", "未知"))
            if on_progress:
                on_progress(i, len(emails), dept_name)

            result = self.send_mail(
                to=email["to"],
                subject=email["subject"],
                html_body=email["html_body"],
                attachments=email.get("attachments", []),
                image_attachments=email.get("image_attachments", []),
                cc=email.get("cc"),
                bcc=email.get("bcc"),
            )

            detail = {
                "dept_name": dept_name,
                "to": email["to"],
                "cc": email.get("cc", ""),
                "success": result["success"],
                "error": result.get("error", ""),
            }
            results["details"].append(detail)

            if result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    def close(self):
        """关闭连接（企业微信API无持久连接，此方法保留兼容性）"""
        pass


# ─────────────────────────────────────────────────────────
# 统一入口：根据配置选择发送方式
# ─────────────────────────────────────────────────────────

def get_mailer(ui_settings: dict = None):
    """根据配置返回对应的邮件发送器

    参数:
        ui_settings: 界面配置的SMTP设置字典，如果提供则优先使用
    """
    if EMAIL_SEND_METHOD == 1:
        return WeComMailer()
    else:
        return SMTPSender(ui_settings)


def is_mail_configured() -> tuple[bool, str]:
    """检查邮件发送配置是否就绪"""
    if EMAIL_SEND_METHOD == 1:
        return test_wecom_connection()
    else:
        return test_smtp_connection()
