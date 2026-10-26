"""Non-secret desktop defaults only. Runtime credentials are injected from Secret."""
EMAIL_SUBJECT_TEMPLATE = "【{period}】{dept} 考勤异常周报 — 人事部发"
CHART_FIGURE_DPI = 150
CHART_WIDTH = 10
CHART_HEIGHT = 6
SMTP_HOST = SMTP_USER = SMTP_PASSWORD = SMTP_FROM = ""
SENDER_NAME = "人事部自动报表"
WECOM_CORP_ID = WECOM_AGENT_ID = WECOM_APP_SECRET = ""
SMTP_PORT = 465
SMTP_USE_SSL = True
EMAIL_SEND_METHOD = 0
