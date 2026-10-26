"""
图表生成模块 - 使用 matplotlib 生成数据图表
"""

import io
import warnings
from pathlib import Path
from typing import List, Dict, Optional
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib import rcParams
from matplotlib.font_manager import FontProperties

from .settings import CHART_FIGURE_DPI, CHART_WIDTH, CHART_HEIGHT

warnings.filterwarnings("ignore", category=UserWarning)

# 预加载并缓存中文字体
_cached_font: Optional[FontProperties] = None


def _get_chinese_font() -> FontProperties:
    """返回中文字体 FontProperties（带缓存）"""
    global _cached_font
    if _cached_font is not None:
        return _cached_font

    preferred = ['Microsoft YaHei', 'SimHei', 'STXihei', 'KaiTi', 'STKaiti',
                 'WenQuanYi Micro Hei', 'Microsoft JhengHei']
    all_names = set(f.name for f in fm.fontManager.ttflist)
    for name in preferred:
        if name in all_names:
            _cached_font = FontProperties(fname=fm.findfont(name))
            rcParams['font.sans-serif'] = [name]
            rcParams['font.family'] = 'sans-serif'
            rcParams['axes.unicode_minus'] = False
            return _cached_font

    _cached_font = FontProperties()
    return _cached_font


def _setup_chinese_font():
    """预初始化中文字体（供其他模块调用，如截图模块）"""
    _get_chinese_font()


# 预初始化字体
_chinese_fp = _get_chinese_font()


def _reset_style_with_font():
    """每次绘图前重置字体设置（对抗 seaborn style 的覆盖）"""
    name = rcParams['font.sans-serif'][0] if rcParams['font.sans-serif'] else None
    if name:
        fp = FontProperties(fname=fm.findfont(name))
        rcParams['font.sans-serif'] = [name]
        rcParams['font.family'] = 'sans-serif'


def generate_chart(
    dept_name: str,
    report_month: str,
    indicators: Dict[str, float],
    output_dir: Optional[Path] = None,
    chart_type: str = "auto"
) -> bytes:
    """生成图表图片并返回 PNG 字节数据。"""
    if not indicators:
        raise ValueError("指标数据为空，无法生成图表")

    labels = list(indicators.keys())
    values = list(indicators.values())
    chart_type = chart_type if chart_type != "auto" else ("bar" if len(labels) <= 5 else "line")

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(CHART_WIDTH, CHART_HEIGHT))

    if chart_type == "bar":
        colors = ['#4C78A8', '#F58518', '#E45756', '#72B7B2', '#54A24B', '#439894']
        bars = ax.bar(labels, values, color=colors[:len(labels)], edgecolor='white', linewidth=0.7)
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=10, fontproperties=fp)
        ax.set_ylabel("次数", fontsize=11, fontproperties=fp)
        ax.set_title(f"{dept_name} {report_month} 数据报表",
                     fontsize=13, fontweight='bold', pad=12, fontproperties=fp)
    else:
        ax.plot(labels, values, marker='o', markersize=8, linewidth=2.5,
                color='#4C78A8', markerfacecolor='#4C78A8', markeredgecolor='white')
        for x, y in zip(labels, values):
            ax.annotate(f'{y}', xy=(x, y), xytext=(0, 8),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=10, fontproperties=fp)
        ax.set_ylabel("数值", fontsize=11, fontproperties=fp)
        ax.set_title(f"{dept_name} {report_month} 数据报表",
                     fontsize=13, fontweight='bold', pad=12, fontproperties=fp)
        ax.grid(True, alpha=0.3)

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dept_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        with open(output_dir / f"{safe_name}_{report_month}_chart.png", 'wb') as f:
            f.write(image_bytes)

    return image_bytes
def generate_summary_chart(
    all_dept_data: List[Dict],
    output_dir: Optional[Path] = None
) -> bytes:
    """生成各部门异常次数对比柱状图，返回 PNG 字节数据。"""
    if not all_dept_data:
        raise ValueError("无数据，无法生成汇总图表")

    sorted_data = sorted(all_dept_data,
                         key=lambda x: x["indicators"].get("异常次数", 0), reverse=True)
    labels = [d['dept_name'] for d in sorted_data]
    values = [d['indicators'].get("异常次数", 0) for d in sorted_data]

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.2), 5))

    max_val = max(values) if values else 1
    colors = ['#E45756' if v == max_val else
              '#F58518' if v >= max_val * 0.5 else
              '#4C78A8' for v in values]

    bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=0.7)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontproperties=fp)

    ax.set_title("各部门考勤异常次数对比",
                 fontsize=13, fontweight='bold', pad=12, fontproperties=fp)
    ax.set_ylabel("异常次数", fontsize=11, fontproperties=fp)

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
        label.set_rotation(20)
        label.set_ha('right')
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "summary_exception_chart.png", 'wb') as f:
            f.write(image_bytes)

    return image_bytes


def generate_dept_own_chart(
    dept_name: str,
    exception_count: int,
    report_period: str,
    output_dir: Optional[Path] = None
) -> bytes:
    """生成单个部门的异常次数展示图，返回 PNG 字节数据。"""
    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.barh([dept_name], [exception_count], color='#E45756', edgecolor='white', linewidth=0.7)
    ax.annotate(f'{exception_count} 次', xy=(exception_count, 0),
                xytext=(5, 0), textcoords="offset points",
                ha='left', va='center', fontsize=14, fontweight='bold',
                color='#E45756', fontproperties=fp)

    ax.set_xlim(0, max(exception_count * 1.3, 3))
    ax.set_title(f"{report_period} {dept_name} 考勤异常情况",
                 fontsize=13, fontweight='bold', pad=10, fontproperties=fp)
    ax.set_xlabel("异常次数", fontsize=11, fontproperties=fp)

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dept_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        with open(output_dir / f"{safe_name}_own_chart.png", 'wb') as f:
            f.write(image_bytes)

    return image_bytes


def generate_ranking_chart(ranking_data: List[Dict]) -> bytes:
    """
    生成部门异常排行榜柱状图（横向）。
    ranking_data: [{'department': str, 'count': int}, ...]
    """
    if not ranking_data:
        raise ValueError("排行榜数据为空")

    # 按异常次数降序排序
    sorted_data = sorted(ranking_data, key=lambda x: x.get('count', 0), reverse=True)
    labels = [d['department'] for d in sorted_data]
    values = [d['count'] for d in sorted_data]

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(8, max(4, len(labels) * 0.6)))

    max_val = max(values) if values else 1
    colors = ['#E45756' if v == max_val else
              '#F58518' if v >= max_val * 0.5 else
              '#4C78A8' for v in values]

    bars = ax.barh(labels, values, color=colors, edgecolor='white', linewidth=0.7)
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f'{int(w)}', xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points",
                    ha='left', va='center', fontsize=10, fontweight='bold', fontproperties=fp)

    ax.set_xlabel("异常次数", fontsize=11, fontproperties=fp)
    ax.set_title("考勤数据异常部门排行榜",
                 fontsize=14, fontweight='bold', pad=12, fontproperties=fp)
    ax.invert_yaxis()

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    return image_bytes


def generate_summary_charts(person_data: List[Dict], dept_data: List[Dict]) -> tuple:
    """
    生成概况统计图表（柱状图）。
    返回: (person_chart_bytes, dept_chart_bytes)

    注意：person_data 现在已经是按部门过滤后的数据，直接用于TOP10展示
    """
    person_bytes = _generate_person_bar_chart(person_data)
    dept_bytes = _generate_dept_summary_chart(dept_data)
    return person_bytes, dept_bytes


def _generate_person_bar_chart(person_data: List[Dict]) -> bytes:
    """生成按姓名汇总的柱状图（TOP10）"""
    if not person_data:
        return _generate_blank_chart("无打卡明细数据")

    # 只显示前10名
    top_data = person_data[:10]
    labels = [d['name'] for d in top_data]
    values = [d['total'] for d in top_data]

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.5)))

    # 使用渐变色
    colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe',
              '#00f2fe', '#43e97b', '#38f9d7', '#ff9a9e', '#a18cd1']
    colors = colors[:len(labels)]

    bars = ax.bar(range(len(labels)), values, color=colors, edgecolor='white', linewidth=0.7)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold', fontproperties=fp)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha='right', fontsize=9)
    ax.set_ylabel("异常次数", fontsize=11, fontproperties=fp)
    ax.set_title("异常次数按姓名 TOP10",
                 fontsize=14, fontweight='bold', pad=12, fontproperties=fp)
    ax.set_ylim(0, max(values) * 1.2 if values else 1)

    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    return image_bytes


def _generate_dept_summary_chart(dept_data: List[Dict]) -> bytes:
    """生成按部门汇总的柱状图"""
    if not dept_data:
        return _generate_blank_chart("无部门汇总数据")

    labels = [d['department'] for d in dept_data]
    values = [d['total'] for d in dept_data]

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(8, max(4, len(labels) * 0.5)))

    colors = ['#4472C4', '#ED7D31', '#A5A5A5', '#FFC000', '#5B9BD5',
              '#70AD47', '#264478', '#9E480E', '#636363', '#997300']
    colors = colors[:len(labels)]

    bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=0.7)
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold', fontproperties=fp)

    ax.set_ylabel("异常次数", fontsize=11, fontproperties=fp)
    ax.set_title("异常次数按部门汇总",
                 fontsize=14, fontweight='bold', pad=12, fontproperties=fp)
    ax.set_ylim(0, max(values) * 1.2 if values else 1)

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
        label.set_rotation(15)
        label.set_ha('right')
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    return image_bytes


def _generate_blank_chart(message: str = "暂无数据") -> bytes:
    """生成空白占位图"""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.text(0.5, 0.5, message, ha='center', va='center',
            fontsize=14, color='#aaa', transform=ax.transAxes)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    return image_bytes


def generate_flexible_list_chart(flexible_data: List[Dict]) -> bytes:
    """
    生成弹性班次踩点关注名单图表。
    flexible_data: [{'name': str, 'department': str, 'count': int}, ...]
    """
    if not flexible_data:
        return _generate_blank_chart("无弹性班次踩点数据")

    # 按次数降序
    sorted_data = sorted(flexible_data, key=lambda x: x.get('count', 0), reverse=True)
    labels = [f"{d['name']}\n({d['department']})" for d in sorted_data]
    values = [d['count'] for d in sorted_data]

    plt.style.use("seaborn-v0_8-whitegrid")
    _reset_style_with_font()
    fp = _get_chinese_font()

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.2), 5))

    colors = ['#FF6B6B' if v >= 4 else '#FFE66D' if v >= 3 else '#4ECDC4' for v in values]
    bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=0.7)

    for bar in bars:
        h = bar.get_height()
        ax.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold', fontproperties=fp)

    ax.set_ylabel("踩点次数", fontsize=11, fontproperties=fp)
    ax.set_title("弹性班次踩点关注名单",
                 fontsize=14, fontweight='bold', pad=12, fontproperties=fp)
    ax.set_ylim(0, max(values) * 1.3 if values else 1)

    for label in ax.get_xticklabels():
        label.set_fontproperties(fp)
        label.set_rotation(15)
        label.set_ha('right')
        label.set_fontsize(9)
    for label in ax.get_yticklabels():
        label.set_fontproperties(fp)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=CHART_FIGURE_DPI, bbox_inches='tight')
    buf.seek(0)
    image_bytes = buf.read()
    plt.close(fig)

    return image_bytes
