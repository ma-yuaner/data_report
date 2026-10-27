import pytest

from data_report_api.services.hr_mail.store import MailError
from data_report_api.services.hr_mail.transport import mail_config


def test_smtp_mail_config_reads_environment_shape_and_defaults():
    value = mail_config(
        {
            "HR_MAIL_METHOD": "SMTP",
            "HR_MAIL_SMTP_HOST": "smtp.example.com",
            "HR_MAIL_SMTP_PORT": "587",
            "HR_MAIL_SMTP_USE_SSL": "false",
            "HR_MAIL_SMTP_USER": "sender@example.com",
            "HR_MAIL_SMTP_PASSWORD": "password",
            "HR_MAIL_SMTP_FROM": "",
            "HR_MAIL_SENDER_NAME": "",
        }
    )

    assert value["method"] == "smtp"
    assert value["smtp_port"] == 587
    assert value["smtp_use_ssl"] is False
    assert value["smtp_from"] == "sender@example.com"
    assert value["sender_name"] == "人事部自动报表"


def test_wecom_mail_config_reads_environment_shape():
    value = mail_config(
        {
            "HR_MAIL_METHOD": "wecom",
            "HR_MAIL_WECOM_CORP_ID": "corp",
            "HR_MAIL_WECOM_AGENT_ID": "agent",
            "HR_MAIL_WECOM_APP_SECRET": "secret",
        }
    )

    assert value == {
        "method": "wecom",
        "corp_id": "corp",
        "agent_id": "agent",
        "app_secret": "secret",
    }


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"HR_MAIL_METHOD": "smtp"},
        {
            "HR_MAIL_METHOD": "smtp",
            "HR_MAIL_SMTP_HOST": "smtp.example.com",
            "HR_MAIL_SMTP_USER": "sender@example.com",
            "HR_MAIL_SMTP_PASSWORD": "password",
            "HR_MAIL_SMTP_USE_SSL": "invalid",
        },
        {
            "HR_MAIL_METHOD": "wecom",
            "HR_MAIL_WECOM_CORP_ID": "corp\nheader",
            "HR_MAIL_WECOM_AGENT_ID": "agent",
            "HR_MAIL_WECOM_APP_SECRET": "secret",
        },
    ],
)
def test_incomplete_or_unsafe_mail_config_is_rejected(config):
    with pytest.raises(MailError) as caught:
        mail_config(config)

    assert caught.value.code == "HR_MAIL_CONFIG_NOT_READY"
