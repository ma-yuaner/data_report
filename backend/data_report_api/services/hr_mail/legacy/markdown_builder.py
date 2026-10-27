"""
邮件内容构建模块 - 将结构化数据转换为 HTML 邮件正文
优化版：融合参考图样式，美化表格展示
"""

import base64
from typing import List, Dict, Optional
from .clock import datetime

from .settings import EMAIL_SUBJECT_TEMPLATE


def get_email_subject(dept_name: str, report_period: str) -> str:
    """根据模板生成邮件主题"""
    return EMAIL_SUBJECT_TEMPLATE.format(dept=dept_name, period=report_period)


def _img_to_base64(img_bytes: bytes) -> str:
    """将图片字节转换为 base64 字符串"""
    return base64.b64encode(img_bytes).decode()


def _build_chart_html(img_bytes: Optional[bytes], title: str) -> str:
    """将图片字节转换为 HTML img 标签"""
    if not img_bytes:
        return ""
    b64 = _img_to_base64(img_bytes)
    return f'''
<div style="margin:16px 0;text-align:center;">
  <div style="font-size:14px;font-weight:bold;color:#333;margin-bottom:12px;text-align:left;">{title}</div>
  <img src="data:image/png;base64,{b64}" alt="{title}"
       style="max-width:100%;border-radius:8px;border:1px solid #eee;display:block;margin:0 auto;" />
</div>'''


def _build_detail_table(detail_data: List[Dict], title: str = "") -> str:
    """
    生成打卡明细表格。

    参数:
        detail_data: [{'time', 'name', 'dept', 'earliest', 'latest', 'result', 'exception'}, ...]
        title: 表格标题，若为空则不输出标题栏
    """
    if not detail_data:
        return ""

    rows_html = ""
    for item in detail_data:
        exc = item.get('exception', 0)
        exc_class = "badge-danger" if exc > 0 else "badge-success"
        result_style = 'style="color:#c0392b;font-weight:500;"' if exc > 0 else 'style="color:#2ecc71;"'

        rows_html += f'''<tr>
          <td>{item.get('time', '')}</td>
          <td><strong>{item.get('name', '')}</strong></td>
          <td>{item.get('dept', '')}</td>
          <td style="text-align:center;color:#555;">{item.get('earliest', '-')}</td>
          <td style="text-align:center;color:#555;">{item.get('latest', '-')}</td>
          <td style="text-align:center;" {result_style}>{item.get('result', '-')}</td>
          <td style="text-align:center;"><span class="badge {exc_class}">{exc}</span></td>
        </tr>'''

    title_html = f'''
  <div style="font-size:15px;font-weight:bold;color:#2c3e50;margin-bottom:12px;
              padding-bottom:8px;border-bottom:2px solid #4472C4;">
    {title}
  </div>''' if title else ""

    return f'''
<div style="margin:8px 0 20px;font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  {title_html}
  <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #ddd;
                border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#34495e;color:white;">
        <th style="padding:10px 10px;text-align:left;font-weight:600;">时间</th>
        <th style="padding:10px 10px;text-align:left;font-weight:600;">姓名</th>
        <th style="padding:10px 10px;text-align:left;font-weight:600;">部门</th>
        <th style="padding:10px 10px;text-align:center;font-weight:600;">最早</th>
        <th style="padding:10px 10px;text-align:center;font-weight:600;">最晚</th>
        <th style="padding:10px 10px;text-align:center;font-weight:600;">考勤结果</th>
        <th style="padding:10px 10px;text-align:center;font-weight:600;">异常</th>
      </tr>
    </thead>
    <tbody style="color:#333;">
      {rows_html}
    </tbody>
  </table>
</div>'''


def _build_ranking_table(ranking_data: List[Dict], title: str = "") -> str:
    """
    生成考勤数据异常部门排行榜表格。

    参数:
        ranking_data: [{'department': str, 'count': int}, ...]
        title: 表格标题
    """
    if not ranking_data:
        return ""

    rows_html = ""
    for item in ranking_data:
        count = item.get('count', 0)
        if count >= 5:
            badge_class = "badge-danger"
        elif count >= 3:
            badge_class = "badge-warning"
        else:
            badge_class = "badge-info"

        rows_html += f'''<tr>
          <td style="padding:10px 14px;color:#2c3e50;font-weight:600;">{item.get('department', '')}</td>
          <td style="text-align:center;padding:10px 14px;"><span class="badge {badge_class}">{count} 次</span></td>
        </tr>'''

    return f'''
<div style="margin:8px 0 20px;font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <div style="font-size:15px;font-weight:bold;color:#2c3e50;margin-bottom:12px;
              padding-bottom:8px;border-bottom:2px solid #E74C3C;">
    {title}
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #ddd;
                border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#E74C3C;color:white;">
        <th style="padding:10px 14px;text-align:left;font-weight:600;">部门</th>
        <th style="padding:10px 14px;text-align:center;font-weight:600;">异常次数</th>
      </tr>
    </thead>
    <tbody style="color:#333;">
      {rows_html}
    </tbody>
  </table>
</div>'''


def _build_flexible_table(flexible_data: List[Dict], title: str = "") -> str:
    """
    生成弹性班次踩点表格。

    参数:
        flexible_data: [{'name', 'dept', 'count'}, ...]
        title: 表格标题，若为空则不输出标题栏
    """
    if not flexible_data:
        return ""

    rows_html = ""
    for item in flexible_data:
        count = item.get('count', 0)
        if count >= 4:
            badge_class = "badge-danger"
        elif count >= 3:
            badge_class = "badge-warning"
        else:
            badge_class = "badge-info"

        rows_html += f'''<tr>
          <td style="padding:10px 14px;"><strong>{item.get('name', '')}</strong></td>
          <td style="padding:10px 14px;">{item.get('dept', '')}</td>
          <td style="text-align:center;padding:10px 14px;"><span class="badge {badge_class}">{count} 次</span></td>
        </tr>'''

    title_html = f'''
  <div style="font-size:15px;font-weight:bold;color:#2c3e50;margin-bottom:12px;
              padding-bottom:8px;border-bottom:2px solid #5d4e75;">
    {title}
  </div>''' if title else ""

    return f'''
<div style="margin:8px 0 20px;font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  {title_html}
  <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #ddd;
                border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#5d4e75;color:white;">
        <th style="padding:10px 14px;text-align:left;font-weight:600;">姓名</th>
        <th style="padding:10px 14px;text-align:left;font-weight:600;">部门</th>
        <th style="padding:10px 14px;text-align:center;font-weight:600;">踩点次数</th>
      </tr>
    </thead>
    <tbody style="color:#333;">
      {rows_html}
    </tbody>
  </table>
</div>'''


def _build_greeting(leader: str) -> str:
    """构建开头语区域（完整版：尊敬的 XXX 领导）"""
    return f'''
<div style="font-size:14px;color:#444;line-height:2;margin-bottom:24px;
            padding:16px 20px;background:#f8f9fa;border-radius:8px;
            border-left:4px solid #4472C4;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <p style="margin:0 0 4px;">尊敬的 <strong style="color:#2c3e50;">{leader}</strong> 领导：</p>
  <p style="margin:0 0 4px;">您好！</p>
</div>'''


def _build_greeting_monthly(leader: str, period: str) -> str:
    """月报版本开头语"""
    return f'''
<div style="font-size:14px;color:#444;line-height:2;margin-bottom:18px;
            padding:16px 20px;background:#f8f9fa;border-radius:8px;
            border-left:4px solid #7030A0;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <p style="margin:0 0 4px;">尊敬的 <strong style="color:#2c3e50;">{leader}</strong> 领导：</p>
  <p style="margin:0 0 4px;">
    您好！请查收 <strong style="color:#7030A0;">{period}</strong> 部门考勤统计表。
  </p>
  <p style="margin:0;">本次统计包含部门员工的出勤、迟到、早退、请假及异常考勤情况，数据请详见附件Excel表格。</p>
</div>'''


def _build_monthly_exception_intro() -> str:
    """月报异常人员列表前的小标题"""
    return _build_section_intro(
        "以下是您所负责部门的考勤异常人员月度异常数据，明细详情见附件，请协助核实："
    )


def _build_monthly_signature() -> str:
    """月报专用署名区域"""
    return f'''
<div style="font-size:13px;color:#555;line-height:2;margin-top:18px;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <p style="margin:0 0 4px;">
    以上如有疑问和其他需求，请于<strong>今天18点前</strong>与 <strong>人事行政部--高宝来</strong> 联系，逾期不予调整。
  </p>
  <p style="margin:0 0 4px;">感谢您对人事工作的支持与配合！</p>
  <p style="margin:0 0 4px;">祝工作顺利！</p>
  <p style="margin:0;">谢谢！</p>
</div>'''


def _build_monthly_persons_table(persons: list) -> str:
    """
    生成月报异常人员表格。
    列：序号 / 姓名 / 部门 / 总工作时长 / 平均每日工作时长 / 异常合计 / 迟到 / 早退 / 旷工 / 缺卡 / 考勤扣罚
    """
    if not persons:
        return ""
    rows_html = ""
    for i, p in enumerate(persons, start=1):
        rows_html += f'''<tr>
          <td style="text-align:center;padding:8px 10px;">{i}</td>
          <td style="padding:8px 10px;"><strong>{p.name}</strong></td>
          <td style="padding:8px 10px;">{p.department}</td>
          <td style="text-align:center;padding:8px 10px;">{p.total_work_duration}</td>
          <td style="text-align:center;padding:8px 10px;">{p.average_daily_work_duration}</td>
          <td style="text-align:center;padding:8px 10px;">{p.exception_total}</td>
          <td style="text-align:center;padding:8px 10px;">{p.late}</td>
          <td style="text-align:center;padding:8px 10px;">{p.early_leave}</td>
          <td style="text-align:center;padding:8px 10px;">{p.absenteeism}</td>
          <td style="text-align:center;padding:8px 10px;">{p.missed_card}</td>
          <td style="text-align:center;padding:8px 10px;">{p.deduction}</td>
        </tr>'''
    return f'''
<table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #ddd;
              border-radius:8px;overflow:hidden;margin-top:6px;
              font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <thead>
    <tr style="background:#7030A0;color:white;">
      <th style="padding:10px 10px;text-align:center;font-weight:600;">序号</th>
      <th style="padding:10px 10px;text-align:left;font-weight:600;">姓名</th>
      <th style="padding:10px 10px;text-align:left;font-weight:600;">部门</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">总工作时长</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">平均每日工作时长</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">异常合计</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">迟到</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">早退</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">旷工</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">缺卡</th>
      <th style="padding:10px 10px;text-align:center;font-weight:600;">考勤扣罚</th>
    </tr>
  </thead>
  <tbody style="color:#333;">
    {rows_html}
  </tbody>
</table>'''


def build_monthly_email_html(
    dept_name: str,
    dept_leader: str,
    dept_email: str,
    report_period: str,
    exception_persons: Optional[list] = None,
    has_leave: bool = False,
    has_business_trip: bool = False,
) -> str:
    """
    构建月报部门邮件 HTML 正文。

    逻辑：
    - 若存在异常人员（exception_persons 非空）：
        显示「考勤异常人员月度异常数据」表格 + 标题段
    - 若存在请假或出差外出明细（即使无异常合计）：
        仍需在邮件正文提示附件内容（附件内部分 sheet）
    - 邮件正文始终显示基础抬头和署名
    """
    has_exc = bool(exception_persons)

    # 正文区块
    body_sections = ""
    if has_exc:
        body_sections += _build_monthly_exception_intro()
        body_sections += _build_monthly_persons_table(exception_persons)

    # 无异常合计但有请假/出差外出时，说明附件内容
    if not has_exc and (has_leave or has_business_trip):
        parts = []
        if has_leave:
            parts.append("请假明细")
        if has_business_trip:
            parts.append("出差/外出明细")
        body_sections += _build_section_intro(
            "以下为您所负责部门的"
            + "、".join(parts)
            + "，详情见附件Excel表格，请协助关注。"
        )

    # 问候语
    greeting_html = _build_greeting_monthly(dept_leader or dept_name, report_period)

    # 署名
    signature_html = _build_monthly_signature()

    # 邮件主题对应异常人员数
    exc_count = len(exception_persons) if has_exc else 0

    # 页脚
    footer_html = f'''
<div style="font-size:11px;color:#bbb;margin-top:24px;padding-top:16px;
            border-top:1px solid #eee;text-align:center;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  此邮件由 考勤月报自动发送工具（人事部） 生成 &nbsp;|&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>'''

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ margin:0; padding:0; background:#f0f2f5; font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif; }}
  a {{ color:#4472C4; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  table tbody tr:nth-child(even) {{ background:#f9fafb; }}
  table tbody tr:hover {{ background:#f0f4ff; }}
</style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:24px 0;">
<tr><td>
<div style="max-width:960px;margin:0 auto;background:white;border-radius:12px;
             box-shadow:0 2px 16px rgba(0,0,0,0.1);overflow:hidden;">

  <!-- 页眉：紫色 -->
  <div style="background:linear-gradient(135deg,#7030A0 0%,#5B2583 100%);padding:28px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="vertical-align:middle;">
          <div style="color:white;font-size:22px;font-weight:bold;letter-spacing:1px;">考勤月报</div>
          <div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:6px;">
            {report_period} &nbsp;|&nbsp; {dept_name}
          </div>
        </td>
        <td style="text-align:right;vertical-align:middle;">
          <div style="background:rgba(255,255,255,0.15);border-radius:10px;
                      padding:14px 20px;display:inline-block;text-align:center;">
            <div style="color:rgba(255,255,255,0.8);font-size:11px;margin-bottom:2px;">异常人员</div>
            <div style="color:white;font-size:30px;font-weight:bold;line-height:1.2;">{exc_count}</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- 正文 -->
  <div style="padding:28px 32px;">
    {greeting_html}
    {body_sections}
    {signature_html}
    {footer_html}
  </div>
</div>
</td></tr></table>
</body>
</html>"""

    return html
def get_monthly_email_subject(dept_name: str, report_period: str) -> str:
    """生成月报邮件主题"""
    return f"【{report_period}】{dept_name} 部门考勤月报 — 人事部发"


def _build_section_intro(text: str) -> str:
    """构建板块引导文字"""
    return f'''
<div style="font-size:13px;color:#555;margin:16px 0 10px;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  {text}
</div>'''


def _build_remark_section() -> str:
    """构建备注区域（浅灰底色 + 左侧蓝线）"""
    return f'''
<div style="margin-top:20px;padding:16px 20px;background:#f8f9fa;border-radius:8px;
            border-left:4px solid #4472C4;font-size:13px;color:#555;line-height:2;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <p style="margin:0;">
    <strong>备注：</strong>定义：一周 &ge; 3次在 9:20-9:30 / 8:20-8:30 打卡的人员；
    部门负责人需根据该人员工作情况进行评估，必要时进行谈话。
  </p>
</div>'''


def _build_signature_section() -> str:
    """构建署名区域（纯文字，无任何样式）"""
    return f'''
<div style="font-size:13px;color:#555;line-height:2;margin-top:16px;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <p style="margin:0 0 4px;">
    请您抽空查阅并核实部门成员的考勤异常，如有疑问和其他需求，
    请于 <strong>人事行政部 -- 高宝来</strong> 联系。
  </p>
  <p style="margin:0 0 4px;">感谢您对人事部工作的支持与配合！</p>
  <p style="margin:0 0 4px;">祝工作顺利！</p>
  <p style="margin:0;">谢谢！</p>
</div>'''


def build_email_html(
    dept_name: str,
    dept_leader: str,
    dept_email: str,
    report_period: str,
    exception_count: int,
    detail_data: Optional[List[Dict]] = None,
    flexible_data: Optional[List[Dict]] = None,
    ranking_data: Optional[List[Dict]] = None,
    has_ranking_version: bool = False,
) -> str:
    """
    构建部门邮件 HTML 正文。

    板块结构（根据版本类型决定）：
    - 有异常排行版本（has_ranking_version=True）：
      - 开头：尊敬的 XXX 领导 / 您好
      - 异常排行榜截图（如果有）
      - 考勤数据异常部门排行榜表格
      - 打卡明细表格（有数据才显示，带描述文字，编号连续）
      - 弹性班次表格（有数据才显示，带描述文字，编号连续）
      - 备注（浅灰底色）
      - 署名（纯文字）
    - 只有弹性班次版本（has_ranking_version=False）：
      - 开头：尊敬的 XXX 领导 / 您好
      - 弹性班次表格（带描述文字）
      - 备注（浅灰底色）
      - 署名（纯文字）

    参数:
        detail_data: 打卡明细 [{'time', 'name', 'dept', 'earliest', 'latest', 'result', 'exception'}, ...]
        flexible_data: 弹性班次 [{'name', 'dept', 'count'}, ...]
        ranking_data: 排行榜 [{'department', 'count'}, ...]
        has_ranking_version: 是否为异常排行版本（True=完整版，False=只有弹性班次）
    """
    # 过滤排行榜数据：只保留异常次数>0的部门
    # 但如果当前部门异常次数为0，也不显示排行榜
    filtered_ranking_data = None
    if ranking_data and exception_count > 0:
        filtered = [d for d in ranking_data if d.get('count', 0) > 0]
        if filtered:
            filtered_ranking_data = filtered
    has_ranking = bool(filtered_ranking_data)
    has_detail = bool(detail_data)
    has_flexible = bool(flexible_data)

    # 编号生成器（中文数字）
    num = [0]
    CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

    def next_num():
        num[0] += 1
        n = num[0]
        if n <= 10:
            return CN_NUM[n - 1] + "、"
        else:
            return str(n) + "、"

    body_sections = ""

    if has_ranking_version and has_ranking:
        # ── 有排行榜版本：显示排行榜 + 打卡明细 + 弹性班次 ──

        # 考勤数据异常部门排行榜
        body_sections += _build_ranking_table(
            filtered_ranking_data,
            f"{next_num()}考勤数据异常部门排行榜"
        )

        # 打卡明细表格
        if has_detail:
            body_sections += _build_section_intro(
                "以下是您所负责部门的考勤异常人员汇总数据，异常明细见附件："
            )
            body_sections += _build_detail_table(detail_data, "")

        # 弹性班次表格
        if has_flexible:
            body_sections += _build_section_intro(
                "以下是您所负责部门的弹性班次踩点人员名单，踩点时间明细见附件："
            )
            body_sections += _build_flexible_table(flexible_data, "")
    else:
        # ── 只有弹性班次版本：只显示弹性班次 ──
        if has_flexible:
            body_sections += _build_section_intro(
                "以下是您所负责部门的弹性班次踩点人员名单，踩点时间明细见附件："
            )
            body_sections += _build_flexible_table(flexible_data, "")

    # ── 备注 + 署名 ──
    body_sections += _build_remark_section()
    body_sections += _build_signature_section()

    # ── 问候语 ──
    greeting_html = _build_greeting(dept_leader or dept_name)

    # ── 页脚 ──
    footer_html = f'''
<div style="font-size:11px;color:#bbb;margin-top:24px;padding-top:16px;
            border-top:1px solid #eee;text-align:center;
            font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  此邮件由 考勤异常周报自动发送工具（数据部） 生成 &nbsp;|&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>'''

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ margin:0; padding:0; background:#f0f2f5; font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif; }}
  a {{ color:#4472C4; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .badge {{
    display:inline-block; padding:3px 10px; border-radius:12px;
    font-size:12px; font-weight:bold; line-height:1.4;
  }}
  .badge-danger {{ background:#FDEDEE; color:#E74C3C; }}
  .badge-warning {{ background:#FEF5E7; color:#F39C12; }}
  .badge-info {{ background:#EBF5FB; color:#3498DB; }}
  .badge-success {{ background:#E8F8F0; color:#27AE60; }}
  table tbody tr:nth-child(even) {{ background:#f9fafb; }}
  table tbody tr:hover {{ background:#f0f4ff; }}
</style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:24px 0;">
<tr><td>
<div style="max-width:720px;margin:0 auto;background:white;border-radius:12px;
             box-shadow:0 2px 16px rgba(0,0,0,0.1);overflow:hidden;">

  <!-- 页眉 -->
  <div style="background:linear-gradient(135deg,#4472C4 0%,#2F5496 100%);padding:28px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="vertical-align:middle;">
          <div style="color:white;font-size:22px;font-weight:bold;letter-spacing:1px;">考勤异常周报</div>
          <div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:6px;">
            {report_period} &nbsp;|&nbsp; {dept_name}
          </div>
        </td>
        <td style="text-align:right;vertical-align:middle;">
          <div style="background:rgba(255,255,255,0.15);border-radius:10px;
                      padding:14px 20px;display:inline-block;text-align:center;">
            <div style="color:rgba(255,255,255,0.8);font-size:11px;margin-bottom:2px;">本周异常</div>
            <div style="color:white;font-size:30px;font-weight:bold;line-height:1.2;">{exception_count}</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- 正文 -->
  <div style="padding:28px 32px;">

    {greeting_html}

    {body_sections}

    {footer_html}

  </div>
</div>
</td></tr></table>
</body>
</html>"""

    return html


def build_summary_email_html(
    report_period: str,
    dept_list: List[Dict],
    ranking_chart_bytes: Optional[bytes] = None,
    summary_chart_bytes: Optional[bytes] = None,
) -> str:
    """
    构建汇总邮件（发给 HR 自己的汇总报告，融合参考图样式）。
    """
    # 生成汇总表格 HTML
    rows_html = ""
    for dept in dept_list:
        ec = dept["indicators"].get("异常次数", 0)
        if ec >= 3:
            badge_class = "badge-danger"
        elif ec >= 2:
            badge_class = "badge-warning"
        else:
            badge_class = "badge-info"
        rows_html += f"""<tr>
  <td style="padding:12px 16px;border-bottom:1px solid #eee;color:#2c3e50;font-weight:600;">{dept["dept_name"]}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #eee;text-align:center;">
    <span class="badge {badge_class}">{ec} 次</span>
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #eee;color:#555;">{dept["dept_leader"]}</td>
</tr>"""

    table_html = f"""
<div style="margin:20px 0 24px;font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
  <div style="font-size:15px;font-weight:bold;color:#2c3e50;margin-bottom:12px;
              padding-bottom:8px;border-bottom:2px solid #c0392b;">
    各部门考勤异常汇总
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #ddd;
                border-radius:8px;overflow:hidden;">
    <thead>
      <tr style="background:#c0392b;color:white;">
        <th style="padding:12px 16px;text-align:left;font-weight:600;">部门</th>
        <th style="padding:12px 16px;text-align:center;font-weight:600;">异常次数</th>
        <th style="padding:12px 16px;text-align:left;font-weight:600;">负责人</th>
      </tr>
    </thead>
    <tbody style="color:#333;">
      {rows_html}
    </tbody>
  </table>
</div>"""

    # 排行榜图表
    ranking_section = ""
    if ranking_chart_bytes:
        ranking_section = _build_chart_html(ranking_chart_bytes, "部门异常排行榜")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ margin:0; padding:0; background:#f0f2f5; font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif; }}
  a {{ color:#4472C4; text-decoration:none; }}
  .badge {{
    display:inline-block;
    padding:4px 12px;
    border-radius:12px;
    font-size:12px;
    font-weight:bold;
    line-height:1.4;
  }}
  .badge-danger {{ background:#FDEDEE; color:#E74C3C; }}
  .badge-warning {{ background:#FEF5E7; color:#F39C12; }}
  .badge-info {{ background:#EBF5FB; color:#3498DB; }}
  table tbody tr:nth-child(even) {{ background:#f9fafb; }}
</style>
</head>
<body>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:24px 0;">
<tr><td>
<div style="max-width:700px;margin:0 auto;background:white;border-radius:12px;
             box-shadow:0 2px 16px rgba(0,0,0,0.1);overflow:hidden;">

  <!-- 页眉：紫色渐变 -->
  <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:28px 32px;">
    <div style="color:white;font-size:22px;font-weight:bold;letter-spacing:1px;">
      HR考勤周报 &mdash; 汇总报告
    </div>
    <div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:6px;">{report_period}</div>
  </div>

  <div style="padding:28px 32px;">

    <div style="font-size:14px;color:#555;line-height:2;margin-bottom:24px;
                padding:16px 20px;background:#f8f9fa;border-radius:8px;
                border-left:4px solid #667eea;
                font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
      <p style="margin:0 0 4px;">您好，</p>
      <p style="margin:0 0 4px;">
        以下是 <strong style="color:#667eea;">{report_period}</strong> 各部门考勤异常汇总，请查收。
      </p>
      <p style="margin:0;">如对数据有疑问，请联系人事部门。</p>
    </div>

    <!-- 汇总表格 -->
    {table_html}

    <!-- 排行榜图表 -->
    {ranking_section}

    <div style="font-size:12px;color:#aaa;margin-top:32px;padding-top:20px;
                border-top:1px solid #eee;line-height:2;text-align:center;
                font-family:Microsoft YaHei,微软雅黑,Arial,sans-serif;">
      <p style="margin:0 0 4px;">此邮件由 <strong>考勤异常周报自动发送工具（数据部）</strong> 自动生成。</p>
      <p style="margin:0;">发送时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

  </div>
</div>
</td></tr></table>
</body>
</html>"""

    return html
