"""
今日练习总结报告
"""

import os
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import memory_db
from config import PHASE_ORDER, PHASE_LABELS, SILICONFLOW_BASE_URL
from prompts import (
    SYSTEM_PROMPT, USER_MULTI_TEMPLATE, USER_SUMMARY_TEMPLATE,
    AI_PAUSE_THRESHOLD_SEC, STRENGTH_TAGS, WEAKNESS_TAGS,
)

log = logging.getLogger(__name__)


def get_date_range_stats(start_date: str, end_date: str) -> Optional[Dict]:
    """获取指定日期范围的统计数据，日期格式: YYYY-MM-DD"""
    records = memory_db.get_records_by_date_range(start_date, end_date)
    if not records:
        return None

    times = [r["total_time"] for r in records]
    record_ids = [r["id"] for r in records]
    phase_avgs = memory_db.get_today_phase_stats(record_ids)

    avg_time = memory_db._trimmed_mean(times)
    best_time = min(times)
    worst_time = max(times)
    std_time = memory_db._std_dev(times) if len(times) >= 2 else 0.0

    ao12_results = _calc_ao12(times, records)

    return {
        "date": f"{start_date} ~ {end_date}",
        "count": len(records),
        "times": times,
        "records": records,
        "avg_time": round(avg_time, 2),
        "std_time": round(std_time, 2),
        "best_time": round(best_time, 2),
        "worst_time": round(worst_time, 2),
        "phase_avgs": phase_avgs,
        "ao12_results": ao12_results,
    }



def get_today_stats() -> Optional[Dict]:
    records = memory_db.get_today_records()
    if not records:
        return None

    times = [r["total_time"] for r in records]
    record_ids = [r["id"] for r in records]
    phase_avgs = memory_db.get_today_phase_stats(record_ids)

    avg_time = memory_db._trimmed_mean(times)
    best_time = min(times)
    worst_time = max(times)
    std_time = memory_db._std_dev(times) if len(times) >= 2 else 0.0

    ao12_results = _calc_ao12(times, records)

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": len(records),
        "times": times,
        "records": records,
        "avg_time": round(avg_time, 2),
        "std_time": round(std_time, 2),
        "best_time": round(best_time, 2),
        "worst_time": round(worst_time, 2),
        "phase_avgs": phase_avgs,
        "ao12_results": ao12_results,
    }


def _calc_ao12(times: List[float], records: List[Dict] = None) -> Optional[Dict]:
    if len(times) < 12:
        return None

    ao12_list = []
    for i in range(len(times) - 11):
        window = times[i:i + 12]
        sorted_window = sorted(window)
        trimmed = sorted_window[1:-1]
        ao12 = sum(trimmed) / len(trimmed)
        entry = {
            "index": i + 1,
            "ao12": round(ao12, 2),
            "times": [round(t, 2) for t in window],
        }
        if records:
            entry["scrambles"] = [records[i + j].get("scramble", "") for j in range(12)]
        ao12_list.append(entry)

    best = min(ao12_list, key=lambda x: x["ao12"])
    worst = max(ao12_list, key=lambda x: x["ao12"])

    return {
        "all": ao12_list,
        "best": best,
        "worst": worst,
    }


def generate_charts(times: List[float], save_dir: str = None, title_prefix: str = "今日") -> Tuple[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    font_path = _find_chinese_font()
    if font_path:
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
        plt.rcParams["font.family"] = font_name
    plt.rcParams["axes.unicode_minus"] = False

    if save_dir is None:
        save_dir = os.path.join(os.path.dirname(__file__), ".temp")
    os.makedirs(save_dir, exist_ok=True)

    line_path = os.path.join(save_dir, "daily_line.png")
    hist_path = os.path.join(save_dir, "daily_hist.png")

    fig1, ax1 = plt.subplots(figsize=(6, 3), dpi=120)
    ax1.plot(range(1, len(times) + 1), times, "o-", color="#6c5ce7",
             markersize=4, linewidth=1.5, markerfacecolor="#a29bfe")
    avg = sum(times) / len(times)
    ax1.axhline(y=avg, color="#e17055", linestyle="--", linewidth=1, label=f"平均 {avg:.2f}s")
    ax1.set_xlabel("还原序号")
    ax1.set_ylabel("时间 (s)")
    ax1.set_title(f"{title_prefix}还原时间折线图")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    fig1.tight_layout()
    fig1.savefig(line_path)
    plt.close(fig1)

    fig2, ax2 = plt.subplots(figsize=(6, 3), dpi=120)
    n_bins = min(20, max(5, len(times) // 3))
    ax2.hist(times, bins=n_bins, color="#6c5ce7", edgecolor="white", alpha=0.85)
    ax2.axvline(x=avg, color="#e17055", linestyle="--", linewidth=1, label=f"平均 {avg:.2f}s")
    ax2.set_xlabel("时间 (s)")
    ax2.set_ylabel("次数")
    ax2.set_title(f"{title_prefix}还原时间直方图")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)
    fig2.tight_layout()
    fig2.savefig(hist_path)
    plt.close(fig2)

    return line_path, hist_path


def _find_chinese_font() -> Optional[str]:
    import matplotlib.font_manager as fm
    candidates = ["msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"]
    font_dirs = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        os.path.expanduser("~/.fonts"),
    ]
    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        for c in candidates:
            p = os.path.join(d, c)
            if os.path.isfile(p):
                return p
    for f in fm.findSystemFonts():
        low = os.path.basename(f).lower()
        if "msyh" in low or "simhei" in low or "yahei" in low:
            return f
    return None


def build_stats_text(stats: Dict) -> str:
    lines = []
    date_str = stats['date']
    title_prefix = "训练总结" if "~" in date_str else "今日练习总结"
    lines.append(f"📅 {title_prefix} ({date_str})")
    lines.append(f"{'=' * 40}")
    lines.append(f"")
    lines.append(f"总还原次数: {stats['count']}")
    std_str = f" (σ{stats['std_time']:.2f}s)" if stats.get('std_time') else ""
    lines.append(f"平均时间: {stats['avg_time']:.2f}s{std_str}")
    lines.append(f"最快: {stats['best_time']:.2f}s | 最慢: {stats['worst_time']:.2f}s")

    phase_avgs = stats.get("phase_avgs", {})
    if phase_avgs:
        lines.append(f"")
        lines.append(f"{'─' * 40}")
        lines.append(f"各阶段平均:")
        for phase in PHASE_ORDER:
            if phase in phase_avgs:
                d = phase_avgs[phase]
                label = PHASE_LABELS.get(phase, phase)
                obs_str = f" 观察{d['observation_time']:.1f}s" if phase != "cross" else ""
                time_std_str = f" σ{d['time_std']:.1f}s" if d.get('time_std') else ""
                tps_std_str = f" σ{d['tps_std']:.1f}" if d.get('tps_std') else ""
                lines.append(
                    f"  {label}: {d['steps']:.0f}步 {d['time']:.1f}s{time_std_str} "
                    f"(TPS{d['tps']:.1f}{tps_std_str}{obs_str})"
                )

    ao12 = stats.get("ao12_results")
    if ao12:
        lines.append(f"")
        lines.append(f"{'─' * 40}")
        lines.append(f"12次滑动平均 (Ao12):")
        best = ao12["best"]
        worst = ao12["worst"]
        lines.append(f"")
        lines.append(f"🏆 最佳Ao12: {best['ao12']:.2f}s")
        times_str = "  ".join(f"{t:.2f}" for t in best["times"])
        lines.append(f"    {times_str}")
        lines.append(f"")
        lines.append(f"📉 最差Ao12: {worst['ao12']:.2f}s")
        times_str = "  ".join(f"{t:.2f}" for t in worst["times"])
        lines.append(f"    {times_str}")

    return "\n".join(lines)


def build_ai_prompt(stats: Dict) -> Tuple[str, str]:
    # 构建今日数据文本
    parts = [f"日期: {stats['date']}"]
    parts.append(f"还原次数: {stats['count']}")
    std_str = f" (σ{stats['std_time']:.2f}s)" if stats.get('std_time') else ""
    parts.append(f"平均时间: {stats['avg_time']:.2f}s{std_str}")
    parts.append(f"最快: {stats['best_time']:.2f}s | 最慢: {stats['worst_time']:.2f}s")

    times = stats["times"]
    if len(times) >= 5:
        sorted_t = sorted(times)
        mid = sorted_t[1:-1]
        parts.append(f"去头尾平均: {sum(mid)/len(mid):.2f}s")

    phase_avgs = stats.get("phase_avgs", {})
    if phase_avgs:
        parts.append("")
        parts.append("今日各阶段平均:")
        for phase in PHASE_ORDER:
            if phase in phase_avgs:
                d = phase_avgs[phase]
                label = PHASE_LABELS.get(phase, phase)
                obs_str = f" 观察{d['observation_time']:.1f}s" if phase != "cross" else ""
                time_std_str = f" σ{d['time_std']:.1f}s" if d.get('time_std') else ""
                tps_std_str = f" σ{d['tps_std']:.1f}" if d.get('tps_std') else ""
                parts.append(
                    f"  {label}: {d['steps']:.0f}步 {d['time']:.1f}s{time_std_str} "
                    f"(TPS{d['tps']:.1f}{tps_std_str}{obs_str})"
                )

    ao12 = stats.get("ao12_results")
    if ao12:
        parts.append("")
        parts.append(f"最佳Ao12: {ao12['best']['ao12']:.2f}s")
        parts.append(f"最差Ao12: {ao12['worst']['ao12']:.2f}s")

    today_data = "\n".join(parts)

    # 构建历史对比文本
    history_parts = []
    history_text = _build_history_text()
    if history_text:
        history_parts.append(history_text)

    comparison_text = _build_comparison_text(stats)
    if comparison_text:
        history_parts.append(comparison_text)

    history_data = "\n\n".join(history_parts) if history_parts else "（无历史数据）"

    system = SYSTEM_PROMPT.format(pause_threshold=AI_PAUSE_THRESHOLD_SEC)
    user = USER_SUMMARY_TEMPLATE.format(
        today_data=today_data,
        history_data=history_data,
    )
    return system, user


def _build_history_text() -> str:
    period_avgs = memory_db.get_all_averages_by_period()
    if not period_avgs:
        return ""

    period_order = ["近7天", "近30天", "近1年", "全部"]
    available_periods = [p for p in period_order if p in period_avgs]
    if not available_periods:
        return ""

    lines = ["【历史平均水平】"]
    display_phases = ["cross", "f2l_avg", "oll", "pll"]
    display_labels = {"cross": "Cross", "f2l_avg": "F2L均", "oll": "OLL", "pll": "PLL"}

    for phase_key in display_phases:
        label = display_labels[phase_key]
        parts = [f"{label}:"]
        for period in available_periods:
            avg_data = period_avgs.get(period, {})
            if phase_key == "f2l_avg":
                f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
                f2l_data = [avg_data.get(p, {}) for p in f2l_phases]
                f2l_data = [d for d in f2l_data if d]
                if f2l_data:
                    avg_steps = sum(d["steps"] for d in f2l_data) / len(f2l_data)
                    avg_time = sum(d["time"] for d in f2l_data) / len(f2l_data)
                    avg_tps = sum(d["tps"] for d in f2l_data) / len(f2l_data)
                    avg_obs = sum(d["observation_time"] for d in f2l_data) / len(f2l_data)
                    parts.append(f" {period}={avg_steps:.0f}步{avg_time:.1f}s(TPS{avg_tps:.1f} 观察{avg_obs:.1f}s)")
                else:
                    parts.append(f" {period}=-")
            else:
                d = avg_data.get(phase_key, {})
                if d:
                    obs_str = f" 观察{d['observation_time']:.1f}s" if phase_key != "cross" else ""
                    parts.append(f" {period}={d['steps']:.0f}步{d['time']:.1f}s(TPS{d['tps']:.1f}{obs_str})")
                else:
                    parts.append(f" {period}=-")
        lines.append(" |".join(parts))

    total_avg = memory_db.get_total_time_avg()
    if total_avg:
        lines.append(f"平均总用时: {total_avg:.2f}s")

    return "\n".join(lines)


def _build_comparison_text(stats: Dict) -> str:
    period_avgs = memory_db.get_all_averages_by_period()
    if not period_avgs:
        return ""

    baseline_period = None
    for p in ["全部", "近1年", "近30天", "近7天"]:
        if p in period_avgs:
            baseline_period = p
            break
    if not baseline_period:
        return ""

    baseline = period_avgs[baseline_period]
    today_phase = stats.get("phase_avgs", {})

    lines = [f"【今日与历史对比】（基准：{baseline_period}平均）"]

    for phase_key, phase_label in [("cross", "Cross"), ("oll", "OLL"), ("pll", "PLL")]:
        cur = today_phase.get(phase_key)
        hist = baseline.get(phase_key, {})
        if cur and hist:
            ds = cur["steps"] - hist["steps"]
            dt = cur["time"] - hist["time"]
            dtps = cur["tps"] - hist["tps"]
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            obs_info = ""
            if phase_key != "cross":
                dobs = cur["observation_time"] - hist["observation_time"]
                obs_info = f" 观察{dobs:+.1f}s"
            lines.append(
                f"{phase_label}: 今日 {cur['steps']:.0f}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) "
                f"vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) "
                f"→ 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f}{obs_info} {tag}"
            )

    f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
    cur_f2l = [today_phase[p] for p in f2l_phases if p in today_phase and today_phase[p]["steps"] > 0]
    hist_f2l = [baseline.get(p, {}) for p in f2l_phases]
    hist_f2l_valid = [d for d in hist_f2l if d]
    if cur_f2l and hist_f2l_valid:
        cs = sum(s["steps"] for s in cur_f2l) / len(cur_f2l)
        ct = sum(s["time"] for s in cur_f2l) / len(cur_f2l)
        ctps = sum(s["tps"] for s in cur_f2l) / len(cur_f2l)
        cobs = sum(s.get("observation_time", 0) for s in cur_f2l) / len(cur_f2l)
        hs = sum(d["steps"] for d in hist_f2l_valid) / len(hist_f2l_valid)
        ht = sum(d["time"] for d in hist_f2l_valid) / len(hist_f2l_valid)
        htps = sum(d["tps"] for d in hist_f2l_valid) / len(hist_f2l_valid)
        hobs = sum(d["observation_time"] for d in hist_f2l_valid) / len(hist_f2l_valid)
        ds = cs - hs
        dt = ct - ht
        dtps = ctps - htps
        dobs = cobs - hobs
        tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
        lines.append(
            f"F2L均: 今日 {cs:.0f}步{ct:.1f}s(TPS{ctps:.1f} 观察{cobs:.1f}s) "
            f"vs 历史 {hs:.0f}步{ht:.1f}s(TPS{htps:.1f} 观察{hobs:.1f}s) "
            f"→ 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} 观察{dobs:+.1f}s {tag}"
        )

    total_avg = memory_db.get_total_time_avg()
    if total_avg:
        diff = stats["avg_time"] - total_avg
        tag = "进步" if diff < 0 else ("退步" if diff > 0 else "持平")
        lines.append(f"总用时: 今日 {stats['avg_time']:.1f}s vs 历史 {total_avg:.1f}s → {diff:+.1f}s {tag}")

    return "\n".join(lines)


def call_ai_summary(api_key: str, model: str, stats: Dict) -> str:
    from openai import OpenAI

    system_prompt, user_prompt = build_ai_prompt(stats)

    log.info(f"今日总结System提示词:\n{system_prompt}")
    log.info(f"今日总结User提示词:\n{user_prompt}")

    client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=512,
    )
    return resp.choices[0].message.content.strip()


def call_ai_summary_stream(api_key: str, model: str, stats: Dict):
    from openai import OpenAI

    system_prompt, user_prompt = build_ai_prompt(stats)

    log.info(f"今日总结System提示词:\n{system_prompt}")
    log.info(f"今日总结User提示词:\n{user_prompt}")

    client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=512,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            yield ("reasoning", delta.reasoning_content)
        elif delta.content:
            yield ("content", delta.content)


def _build_ao12_prompts(analyzers: list, which: str) -> Tuple[str, str]:
    """构建Ao12分析的提示词，复用USER_MULTI_TEMPLATE"""
    from config import PHASE_ORDER
    from move_utils import get_orientation_desc

    count = len(analyzers)
    times = [a.get_total_time() for a in analyzers]
    avg_time = sum(times) / len(times)
    sorted_times = sorted(times)
    ao_avg = sum(sorted_times[1:-1]) / (len(times) - 2) if len(times) >= 5 else avg_time
    variance = sum((t - avg_time) ** 2 for t in times) / len(times)
    std_dev = variance ** 0.5
    best_idx = times.index(min(times)) + 1
    worst_idx = times.index(max(times)) + 1

    groups_detail = ""
    for i, analyzer in enumerate(analyzers):
        orientation_desc = get_orientation_desc(analyzer.top_color, analyzer.front_color)
        total_steps = sum(analyzer.get_phase_stats()[p]["steps"] for p in PHASE_ORDER)
        total_time = analyzer.get_total_time()
        total_tps = total_steps / total_time if total_time > 0 else 0
        groups_detail += f"\n### 第 {i+1} 组 (总时间: {times[i]:.2f}s)\n"
        groups_detail += f"**朝向**: {orientation_desc}\n\n"
        groups_detail += analyzer.build_phase_details_text()
        groups_detail += f"### 总计\n- 总步数: {total_steps}\n- 总用时: {total_time:.2f}s\n- 总TPS: {total_tps:.1f}\n"
        groups_detail += "\n"

    label = "最佳" if which == "best" else "最差"

    system = SYSTEM_PROMPT.format(pause_threshold=AI_PAUSE_THRESHOLD_SEC)
    user = USER_MULTI_TEMPLATE.format(
        count=count,
        groups_times=', '.join([f'{t:.2f}s' for t in times]),
        avg_time=avg_time,
        ao_avg=ao_avg,
        std_dev=std_dev,
        best_idx=best_idx,
        min_time=min(times),
        worst_idx=worst_idx,
        max_time=max(times),
        groups_detail=groups_detail,
        memory_info=f"\n这是今日{label}Ao12（连续12次还原）的数据。请分析整体表现，找出共性问题、薄弱环节，给出改进建议。200字以内。",
        strength_tags_str="、".join(STRENGTH_TAGS),
        weakness_tags_str="、".join(WEAKNESS_TAGS),
    )
    return system, user


def call_ao12_analysis(api_key: str, model: str, analyzers: list, which: str) -> str:
    from openai import OpenAI

    system, user = _build_ao12_prompts(analyzers, which)

    label = "最佳" if which == "best" else "最差"
    log.info(f"Ao12分析({label})System提示词:\n{system}")
    log.info(f"Ao12分析({label})User提示词:\n{user}")

    client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
    )
    return resp.choices[0].message.content.strip()


def call_ao12_analysis_stream(api_key: str, model: str, analyzers: list, which: str):
    from openai import OpenAI

    system, user = _build_ao12_prompts(analyzers, which)

    label = "最佳" if which == "best" else "最差"
    log.info(f"Ao12分析({label})System提示词:\n{system}")
    log.info(f"Ao12分析({label})User提示词:\n{user}")

    client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=1024,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            yield ("reasoning", delta.reasoning_content)
        elif delta.content:
            yield ("content", delta.content)


def save_pdf(stats: Dict, ai_summary: str, chart_line: str, chart_hist: str,
             output_path: str, ao12_best_analysis: str = "", ao12_worst_analysis: str = "") -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path = _find_chinese_font()
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont("Chinese", font_path))
            cn_font = "Chinese"
        except Exception:
            cn_font = "Helvetica"
    else:
        cn_font = "Helvetica"

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CnTitle", parent=styles["Title"],
        fontName=cn_font, fontSize=18, spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "CnHeading", parent=styles["Heading2"],
        fontName=cn_font, fontSize=13, spaceAfter=4,
        textColor=HexColor("#6c5ce7"),
    )
    body_style = ParagraphStyle(
        "CnBody", parent=styles["Normal"],
        fontName=cn_font, fontSize=10, leading=16,
    )

    story = []

    story.append(Paragraph(f"今日练习总结 ({stats['date']})", title_style))
    story.append(Spacer(1, 6))

    basic_data = [
        ["还原次数", str(stats["count"])],
        ["平均时间", f"{stats['avg_time']:.2f}s" + (f" (σ{stats['std_time']:.2f}s)" if stats.get('std_time') else "")],
        ["最快", f"{stats['best_time']:.2f}s"],
        ["最慢", f"{stats['worst_time']:.2f}s"],
    ]
    t = Table(basic_data, colWidths=[60 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), cn_font),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#f0eef8")),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dfe6e9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    phase_avgs = stats.get("phase_avgs", {})
    if phase_avgs:
        story.append(Paragraph("各阶段平均", heading_style))
        phase_data = [["阶段", "步数", "用时(s)", "σ(s)", "TPS", "σ", "观察时间"]]
        for phase in PHASE_ORDER:
            if phase in phase_avgs:
                d = phase_avgs[phase]
                label = PHASE_LABELS.get(phase, phase)
                obs = f"{d['observation_time']:.1f}s" if phase != "cross" else "-"
                time_std = f"{d['time_std']:.1f}" if d.get('time_std') else "-"
                tps_std = f"{d['tps_std']:.1f}" if d.get('tps_std') else "-"
                phase_data.append([
                    label, f"{d['steps']:.0f}", f"{d['time']:.1f}",
                    time_std, f"{d['tps']:.1f}", tps_std, obs,
                ])
        pt = Table(phase_data, colWidths=[30 * mm, 15 * mm, 18 * mm, 15 * mm, 15 * mm, 15 * mm, 22 * mm])
        pt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), cn_font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#6c5ce7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dfe6e9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(pt)
        story.append(Spacer(1, 8))

    ao12 = stats.get("ao12_results")
    if ao12:
        story.append(Paragraph("Ao12 分析", heading_style))
        ao12_data = [
            ["类型", "Ao12", "起止序号"],
            ["最佳", f"{ao12['best']['ao12']:.2f}s",
             f"第{ao12['best']['index']}~{ao12['best']['index']+11}次"],
            ["最差", f"{ao12['worst']['ao12']:.2f}s",
             f"第{ao12['worst']['index']}~{ao12['worst']['index']+11}次"],
        ]
        at = Table(ao12_data, colWidths=[30 * mm, 30 * mm, 40 * mm])
        at.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), cn_font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#6c5ce7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dfe6e9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(at)
        story.append(Spacer(1, 6))

        for label, group in [("🏆 最佳Ao12详情", ao12["best"]), ("📉 最差Ao12详情", ao12["worst"])]:
            story.append(Paragraph(label, heading_style))
            times_str = "  ".join(f"{t:.2f}" for t in group["times"])
            story.append(Paragraph(times_str, body_style))
            story.append(Spacer(1, 6))

    if os.path.isfile(chart_line):
        story.append(Paragraph("还原时间折线图", heading_style))
        img = Image(chart_line, width=160 * mm, height=80 * mm)
        story.append(img)
        story.append(Spacer(1, 6))

    if os.path.isfile(chart_hist):
        story.append(Paragraph("还原时间直方图", heading_style))
        img2 = Image(chart_hist, width=160 * mm, height=80 * mm)
        story.append(img2)
        story.append(Spacer(1, 8))

    if ai_summary:
        story.append(Paragraph("AI 总结", heading_style))
        summary_text = ai_summary.replace("\n", "<br/>")
        story.append(Paragraph(summary_text, body_style))

    if ao12_best_analysis:
        story.append(Spacer(1, 6))
        story.append(Paragraph("🏆 最佳Ao12 AI分析", heading_style))
        best_text = ao12_best_analysis.replace("\n", "<br/>")
        story.append(Paragraph(best_text, body_style))

    if ao12_worst_analysis:
        story.append(Spacer(1, 6))
        story.append(Paragraph("📉 最差Ao12 AI分析", heading_style))
        worst_text = ao12_worst_analysis.replace("\n", "<br/>")
        story.append(Paragraph(worst_text, body_style))

    doc.build(story)
    return output_path
