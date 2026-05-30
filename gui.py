"""
GUI应用主类 - CFOPAnalyzerGUI
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import List
import threading
import json
import os
from datetime import datetime

from config import (
    THEME, HELP_TEXTS, PHASE_COLORS, PHASE_LABELS,
    ORIENTATION_OPTIONS, PHASE_ORDER,
    BOTTOM_COLOR_NAMES, BOTTOM_COLOR_OPTIONS, OPPOSITE_COLORS,
    RESULT_DIR, SILICONFLOW_BASE_URL
)

from analyzer import CFOPAnalyzer
from move_utils import get_orientation_desc
from api_utils import load_config, save_config, fetch_models
from markdown_renderer import configure_markdown_tags, render_markdown


log = None

def set_logger(logger):
    global log
    log = logger


class CFOPAnalyzerGUI:
    """CFOP分析器的主GUI应用"""

    def __init__(self, root):
        self.root = root
        self.root.title("AI_CFOP（V1.0，交流QQ群:322267527）")
        self.root.geometry("960x980")
        self.root.resizable(True, True)
        self.root.configure(bg=THEME["bg"])
        self._stream_stop = False
        self._last_analyzer = None
        self._stream_buffer = ""
        self._reasoning_buffer = ""
        self._solution_summary = ""
        self._status_dots = 0
        self._status_after_id = None
        self._animation_after_id = None
        self._animation_running = False
        self._animation_frames = []
        self._animation_text = ""
        self._animation_index = 0
        self._render_pending = False

        self._setup_styles()
        self._create_widgets()
        self._load_saved_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.timeline_canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.after(1, self._async_init_tasks)

    def _async_init_tasks(self):
        self.root.update_idletasks()
        self._set_all_controls_state("normal")
        self.root.after(100, lambda: self._show_guide_dialog(True))

    def _set_all_controls_state(self, state: str):
        try:
            if hasattr(self, 'ai_analyze_btn'):
                self.ai_analyze_btn.config(state=state)
            if hasattr(self, 'clear_btn'):
                self.clear_btn.config(state=state)
            if hasattr(self, 'scramble_entry'):
                self.scramble_entry.config(state=state)
            if hasattr(self, 'solution_text'):
                self.solution_text.config(state=state)
            if hasattr(self, 'api_key_entry'):
                self.api_key_entry.config(state=state)
            if hasattr(self, 'model_combo'):
                self.model_combo.config(state="readonly" if state == "normal" else state)
            if hasattr(self, 'analysis_mode_combo'):
                self.analysis_mode_combo.config(state="readonly" if state == "normal" else state)
            if hasattr(self, 'orientation_combo'):
                self.orientation_combo.config(state="readonly" if state == "normal" else state)
            if hasattr(self, 'multi_inputs') and self.multi_inputs:
                for inp in self.multi_inputs:
                    if 'scramble' in inp:
                        inp['scramble'].config(state=state)
                    if 'solution' in inp:
                        inp['solution'].config(state=state)
                    if 'orientation_combo' in inp:
                        inp['orientation_combo'].config(state="readonly" if state == "normal" else state)
                    if 'delete_btn' in inp:
                        inp['delete_btn'].config(state=state)
        except Exception as ex:
            if log:
                log.debug(f"设置控件状态异常: {ex}")


    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("TFrame", background=THEME["bg"])
        style.configure("TLabelframe", background=THEME["bg"], foreground=THEME["fg"])
        style.configure("TLabelframe.Label", background=THEME["bg"], foreground=THEME["accent"],
                        font=("Microsoft YaHei", 10, "bold"))
        
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["fg"],
                        font=("Microsoft YaHei", 10))
        
        style.configure("TEntry", fieldbackground=THEME["input_bg"], foreground=THEME["fg"],
                        font=("Consolas", 10), padding=6)
        
        style.configure("TCombobox", fieldbackground=THEME["input_bg"], foreground=THEME["fg"],
                        font=("Microsoft YaHei", 10), padding=6)
        
        style.configure("Accent.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=THEME["button_bg"], foreground=THEME["button_fg"],
                        padding=(16, 8), borderwidth=0, focuscolor="none")
        style.map("Accent.TButton",
                  background=[("active", THEME["accent_hover"]), ("disabled", "#b2bec3")],
                  foreground=[("disabled", "#dfe6e9")])
        
        style.configure("Secondary.TButton", font=("Microsoft YaHei", 10),
                        background=THEME["card_bg"], foreground=THEME["fg"],
                        padding=(12, 6), borderwidth=1)
        style.map("Secondary.TButton",
                  background=[("active", "#f1f2f6"), ("disabled", "#f1f2f6")],
                  foreground=[("disabled", "#b2bec3")])
        
        style.configure("Danger.TButton", font=("Microsoft YaHei", 10, "bold"),
                        background=THEME["danger"], foreground=THEME["button_fg"],
                        padding=(12, 6))
        style.map("Danger.TButton", background=[("active", "#d63031")])
        
        style.configure("Status.TLabel", background=THEME["bg"], foreground=THEME["danger"],
                        font=("Microsoft YaHei", 10, "bold"))
    
    def _create_help_icon(self, parent, help_key):
        help_text = HELP_TEXTS.get(help_key, "")
        
        canvas = tk.Canvas(parent, width=18, height=18, highlightthickness=0,
                          bg=THEME["bg"], cursor="question_arrow")
        canvas.create_oval(2, 2, 16, 16, fill=THEME["accent"], outline="")
        canvas.create_text(9, 9, text="?", font=("Microsoft YaHei", 9, "bold"),
                          fill="white")
        
        self._create_tooltip(canvas, help_text)
        return canvas
    
    def _create_tooltip(self, widget, text):
        tooltip = [None]
        hide_timer = [None]
        
        def show_tooltip(event):
            if hide_timer[0]:
                widget.after_cancel(hide_timer[0])
                hide_timer[0] = None
            
            if tooltip[0]:
                return
            
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.wm_attributes("-topmost", True)
            
            frame = tk.Frame(tip, bg=THEME["border"], padx=1, pady=1)
            frame.pack(fill="both", expand=True)
            
            lines = text.split('\n')
            max_line_width = max(len(line) for line in lines) if lines else 10
            line_count = len(lines)
            
            text_width = min(max(max_line_width + 2, 30), 60)
            text_height = min(max(line_count, 3), 15)
            
            text_widget = tk.Text(frame, font=("Microsoft YaHei", 9),
                                  bg="#ffffcc", fg=THEME["fg"],
                                  padx=8, pady=6, wrap=tk.WORD,
                                  width=text_width, height=text_height, relief="flat",
                                  cursor="arrow")
            text_widget.pack()
            text_widget.insert("1.0", text)
            text_widget.config(state="normal")
            
            tooltip[0] = tip
            
            def on_tip_enter(e):
                if hide_timer[0]:
                    widget.after_cancel(hide_timer[0])
                    hide_timer[0] = None
            
            def on_tip_leave(e):
                hide_tooltip(None)
            
            tip.bind("<Enter>", on_tip_enter)
            tip.bind("<Leave>", on_tip_leave)
            text_widget.bind("<Leave>", on_tip_leave)
        
        def hide_tooltip(event):
            def do_hide():
                if tooltip[0]:
                    tooltip[0].destroy()
                    tooltip[0] = None
                hide_timer[0] = None
            
            hide_timer[0] = widget.after(100, do_hide)
        
        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)
    
    def _show_guide_dialog(self, is_startup=True):
        if is_startup:
            config = load_config()
            if config.get("skip_startup_dialog", False):
                return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("使用说明" if is_startup else "关于")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        dialog_width = 500
        dialog_height = 520
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog_width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=24, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_text = "欢迎使用 AI_CFOP" if is_startup else "AI_CFOP"
        title_label = tk.Label(main_frame, text=title_text,
                              font=("Microsoft YaHei", 16, "bold"),
                              fg=THEME["accent"], bg=THEME["card_bg"])
        title_label.pack(pady=(0, 16))
        
        guide_text = """本软件通过AI分析您的魔方CFOP还原过程，提供技术评估和训练建议。

【须知】
1.本软件需要配合智能魔方使用，不限品牌，可以连接cstimer（https://www.cstimer.net/）进行还原即可。
2.目前支持三阶魔方、任意底色、CFOP方法还原。
3.本软件免费使用，但需要用户自备token，token获取方式见下文。

【免责声明】
本软件提供的魔方还原分析与训练建议基于算法模型生成，仅供参考，不构成任何专业指导或结果保证。
用户应自行判断分析结果的适用性，并对使用本软件产生的任何后果承担责任。
软件开发者不对因使用本软件导致的直接或间接损失负责。

【快速开始】
1. 在cstimer中打乱并还原您的魔方。
2. 点击成绩列表中的还原时间，完整复制弹窗中的"打乱公式"和"回顾"中的内容到软件输入框。
3. 配置硅基流动API Key 并选择合适的模型。
4. 点击"AI分析"开始分析。
5. 分析结果可以保存到本地。

【API Key获取】
- 从硅基流动平台获取API密钥
- 注册并完成实名认证后可获得价值16元的token（使用GLM5.1可分析约180次，使用deepseek-v3.2可分析约2000次）
- 注册链接：https://cloud.siliconflow.cn/i/k2AMkh34
- 邀请码：k2AMkh34

【模型选择】
- 点击"刷新"按钮获取可用模型列表
- 不同模型分析结果可能有较大差异，性能越高的模型分析结果越准确
- 高性能模型推荐GLM系列，性价比模型推荐DeepSeek系列 

【功能特点】
• 自动识别CFOP各阶段
• 计算观察时间和执行时间
• 定位卡顿点
• 生成训练建议"""
        
        text_widget = scrolledtext.ScrolledText(main_frame, width=55, height=16,
                                                font=("Microsoft YaHei", 10),
                                                bg=THEME["card_bg"],
                                                fg=THEME["fg"],
                                                relief="flat", borderwidth=0,
                                                wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert("1.0", guide_text)
        text_widget.config(state="disabled")
        
        config = load_config()
        skip_var = tk.BooleanVar(value=config.get("skip_startup_dialog", False))
        
        def on_close():
            config["skip_startup_dialog"] = skip_var.get()
            save_config(config)
            dialog.destroy()
        
        checkbox_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        checkbox_frame.pack(fill=tk.X, pady=(12, 0))
        
        skip_cb = tk.Checkbutton(checkbox_frame, text="启动时不再显示使用说明",
                                 variable=skip_var,
                                 bg=THEME["card_bg"],
                                 fg=THEME["fg"],
                                 selectcolor=THEME["card_bg"],
                                 activebackground=THEME["card_bg"],
                                 font=("Microsoft YaHei", 9))
        skip_cb.pack(side=tk.LEFT)
        
        btn_text = "开始使用" if is_startup else "关闭"
        close_btn = ttk.Button(main_frame, text=btn_text, command=on_close,
                              style="Accent.TButton")
        close_btn.pack(pady=(12, 0))
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        input_header = ttk.Frame(main_frame)
        input_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(input_header, text="  输入参数", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        self._create_help_icon(input_header, "input").pack(side=tk.LEFT, padx=(4, 0))
        
        mode_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=12, pady=8,
                              highlightthickness=1, highlightbackground=THEME["border"])
        mode_frame.pack(fill=tk.X, pady=(0, 2))
        
        tk.Label(mode_frame, text="分析模式:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        
        self.analysis_mode_var = tk.StringVar(value='单组')
        self.analysis_mode_combo = ttk.Combobox(mode_frame, textvariable=self.analysis_mode_var,
                                                 width=10, state="readonly", font=("Microsoft YaHei", 10))
        self.analysis_mode_combo['values'] = ['单组', '多组']
        self.analysis_mode_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.analysis_mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)
        
        self.mode_desc_label = tk.Label(mode_frame, text="", bg=THEME["card_bg"],
                                        fg=THEME["fg"], font=("Microsoft YaHei", 9))
        self.mode_desc_label.pack(side=tk.LEFT, padx=(16, 0))
        
        self.input_container = tk.Frame(main_frame, bg=THEME["bg"])
        self.input_container.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        self._create_single_input_ui()
        
        ai_header = ttk.Frame(main_frame)
        ai_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(ai_header, text="  AI分析设置", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        self._create_help_icon(ai_header, "ai").pack(side=tk.LEFT, padx=(4, 0))
        
        ai_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=12, pady=12,
                            highlightthickness=1, highlightbackground=THEME["border"])
        ai_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(ai_frame, text="API Key:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky=tk.W, pady=4)
        self.api_key_entry = ttk.Entry(ai_frame, width=35, show="●", font=("Consolas", 10))
        self.api_key_entry.grid(row=0, column=1, sticky=tk.EW, pady=4, padx=(8, 0))
        
        tk.Label(ai_frame, text="模型:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=0, column=2, sticky=tk.W, pady=4, padx=(12, 0))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(ai_frame, textvariable=self.model_var, width=30, state="readonly")
        self.model_combo.grid(row=0, column=3, sticky=tk.EW, pady=4, padx=(8, 0))
        
        self.refresh_btn = ttk.Button(ai_frame, text="🔄 刷新", command=self._refresh_models, style="Secondary.TButton")
        self.refresh_btn.grid(row=0, column=4, padx=(8, 0), pady=4)
        
        ai_frame.columnconfigure(1, weight=1)
        ai_frame.columnconfigure(3, weight=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.ai_analyze_btn = ttk.Button(button_frame, text="🚀 AI分析", command=self._ai_analyze, style="Accent.TButton")
        self.ai_analyze_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.stop_btn = ttk.Button(button_frame, text="⏹ 停止", command=self._stop_analyze, state="disabled", style="Danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.save_btn = ttk.Button(button_frame, text="💾 保存", command=self._save_result, style="Secondary.TButton")
        self.save_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.clear_btn = ttk.Button(button_frame, text="🗑 清空", command=self._clear, style="Secondary.TButton")
        self.clear_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        self.about_btn = ttk.Button(button_frame, text="ℹ️ 关于", command=lambda: self._show_guide_dialog(False), style="Secondary.TButton")
        self.about_btn.pack(side=tk.LEFT, padx=(0, 16))
        
        self.status_label = ttk.Label(button_frame, text="", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)
        
        self.timeline_header = ttk.Frame(main_frame)
        self.timeline_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(self.timeline_header, text="  还原步骤时间轴", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        
        self.timeline_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=8, pady=8,
                                  highlightthickness=1, highlightbackground=THEME["border"])
        self.timeline_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.timeline_canvas = tk.Canvas(self.timeline_frame, height=100, bg=THEME["card_bg"],
                                          highlightthickness=0)
        self.timeline_canvas.pack(fill=tk.X)
        
        self.result_header = ttk.Frame(main_frame)
        self.result_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(self.result_header, text="  分析结果", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        
        self.ai_status_label = tk.Label(self.result_header, text="", font=("Microsoft YaHei", 10, "bold"),
                                        bg=THEME["bg"], fg=THEME["accent"])
        self.ai_status_label.pack(side=tk.LEFT, padx=(8, 0))
        
        self.result_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=8, pady=8,
                                highlightthickness=1, highlightbackground=THEME["border"])
        self.result_frame.pack(fill=tk.BOTH, expand=True)
        
        self.result_text = scrolledtext.ScrolledText(self.result_frame, width=60, height=20, wrap=tk.WORD,
                                                      font=("Microsoft YaHei", 11),
                                                      bg=THEME["card_bg"], fg=THEME["fg"],
                                                      relief="flat", borderwidth=0,
                                                      highlightthickness=0,
                                                      insertbackground=THEME["accent"])
        self.result_text.pack(fill=tk.BOTH, expand=True)
        configure_markdown_tags(self.result_text)
    
    def _create_single_input_ui(self):
        for widget in self.input_container.winfo_children():
            widget.destroy()
        
        self.multi_inputs = None
        
        input_frame = tk.Frame(self.input_container, bg=THEME["card_bg"], padx=12, pady=12,
                               highlightthickness=1, highlightbackground=THEME["border"])
        input_frame.pack(fill=tk.X)
        
        tk.Label(input_frame, text="打乱公式:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky=tk.W, pady=4)
        self.scramble_entry = ttk.Entry(input_frame, width=60, font=("Consolas", 10))
        self.scramble_entry.grid(row=0, column=1, sticky=tk.EW, pady=4, padx=(8, 0))
        
        tk.Label(input_frame, text="底色:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky=tk.W, pady=4)
        
        self.orientation_var = tk.StringVar(value=BOTTOM_COLOR_NAMES[0])
        self.orientation_combo = ttk.Combobox(input_frame, textvariable=self.orientation_var,
                                               width=12, state="readonly", font=("Microsoft YaHei", 10))
        self.orientation_combo['values'] = BOTTOM_COLOR_NAMES
        self.orientation_combo.grid(row=1, column=1, sticky=tk.W, pady=4, padx=(8, 0))
        self.orientation_combo.bind("<MouseWheel>", lambda e: "break")
        
        tk.Label(input_frame, text="还原步骤 (回顾):", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky=tk.NW, pady=4)
        self.solution_text = scrolledtext.ScrolledText(input_frame, width=60, height=6, wrap=tk.WORD,
                                                        font=("Consolas", 10), bg=THEME["input_bg"],
                                                        fg=THEME["fg"], relief="flat", borderwidth=0,
                                                        highlightthickness=1, highlightbackground=THEME["border"],
                                                        highlightcolor=THEME["accent"])
        self.solution_text.grid(row=2, column=1, sticky=tk.EW, pady=4, padx=(8, 0))
        
        input_frame.columnconfigure(1, weight=1)
        
        self.mode_desc_label.config(text="单组模式：分析单次还原过程")
    
    def _create_multi_input_ui(self):
        for widget in self.input_container.winfo_children():
            widget.destroy()
        
        self.multi_inputs = []
        
        outer_frame = tk.Frame(self.input_container, bg=THEME["card_bg"], padx=12, pady=8,
                               highlightthickness=1, highlightbackground=THEME["border"])
        outer_frame.pack(fill=tk.BOTH, expand=True)
        
        header_frame = tk.Frame(outer_frame, bg=THEME["card_bg"])
        header_frame.pack(fill=tk.X, pady=(0, 4))
        
        header_frame.columnconfigure(1, weight=1)
        
        tk.Label(header_frame, text="#", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 9, "bold"), width=3, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(header_frame, text="打乱公式", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 9, "bold"), anchor="w").grid(row=0, column=1, sticky="w", padx=(4, 0))
        tk.Label(header_frame, text="底色", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 9, "bold"), width=10, anchor="w").grid(row=0, column=2, sticky="w", padx=(4, 0))
        tk.Label(header_frame, text="还原步骤", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 9, "bold"), width=34, anchor="w").grid(row=0, column=3, sticky="w", padx=(4, 0))
        tk.Label(header_frame, text="", bg=THEME["card_bg"],
                 font=("Microsoft YaHei", 9), width=2).grid(row=0, column=4, padx=(2, 0))
        
        rows_container = tk.Frame(outer_frame, bg=THEME["card_bg"])
        rows_container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(rows_container, bg=THEME["card_bg"], highlightthickness=0, height=200)
        scrollbar = ttk.Scrollbar(rows_container, orient="vertical", command=canvas.yview)
        self.multi_rows_frame = tk.Frame(canvas, bg=THEME["card_bg"])
        
        self.multi_rows_frame.columnconfigure(0, weight=1)
        
        self.multi_rows_frame.bind("<Configure>", 
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas_window = canvas.create_window((0, 0), window=self.multi_rows_frame, anchor="nw")
        
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind("<MouseWheel>", _on_mousewheel)
        self.multi_canvas = canvas
        self.multi_mousewheel_func = _on_mousewheel
        
        outer_frame.bind("<MouseWheel>", _on_mousewheel)
        rows_container.bind("<MouseWheel>", _on_mousewheel)
        self.multi_rows_frame.bind("<MouseWheel>", _on_mousewheel)
        
        btn_frame = tk.Frame(outer_frame, bg=THEME["card_bg"], pady=8)
        btn_frame.pack(fill=tk.X)
        
        add_btn = ttk.Button(btn_frame, text="➕ 添加一组", command=self._add_multi_row, style="Accent.TButton")
        add_btn.pack(side=tk.LEFT)
        
        self.multi_count_label = tk.Label(btn_frame, text="", bg=THEME["card_bg"],
                                           fg=THEME["fg"], font=("Microsoft YaHei", 9))
        self.multi_count_label.pack(side=tk.LEFT, padx=(16, 0))
        
        for _ in range(5):
            self._add_multi_row()
        
        self.mode_desc_label.config(text="多组模式：分析多组还原，计算平均、波动度等")
        self._hide_timeline()
    
    def _add_multi_row(self):
        if not hasattr(self, 'multi_rows_frame'):
            return
        
        if len(self.multi_inputs) >= 20:
            messagebox.showwarning("提示", "最多支持20组数据")
            return
        
        idx = len(self.multi_inputs)
        
        row_frame = tk.Frame(self.multi_rows_frame, bg=THEME["card_bg"])
        row_frame.columnconfigure(1, weight=1)
        row_frame.grid(row=idx, column=0, sticky="ew", pady=1)
        
        num_label = tk.Label(row_frame, text=f"{idx+1}", bg=THEME["card_bg"], fg=THEME["accent"],
                             font=("Microsoft YaHei", 9, "bold"), width=3, anchor="w")
        num_label.grid(row=0, column=0, sticky="w")
        
        scramble_entry = ttk.Entry(row_frame, font=("Consolas", 9), width=35)
        scramble_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        
        orientation_var = tk.StringVar(value=BOTTOM_COLOR_NAMES[0])
        orientation_combo = ttk.Combobox(row_frame, textvariable=orientation_var,
                                          width=8, state="readonly", font=("Microsoft YaHei", 9))
        orientation_combo['values'] = BOTTOM_COLOR_NAMES
        orientation_combo.grid(row=0, column=2, sticky="w", padx=(4, 0))
        orientation_combo.bind("<MouseWheel>", lambda e: "break")
        
        solution_entry = ttk.Entry(row_frame, font=("Consolas", 9), width=34)
        solution_entry.grid(row=0, column=3, sticky="w", padx=(4, 0))
        
        inp = {
            'row_frame': row_frame,
            'num_label': num_label,
            'scramble': scramble_entry,
            'orientation_var': orientation_var,
            'orientation_combo': orientation_combo,
            'solution': solution_entry
        }
        
        del_btn = ttk.Button(row_frame, text="✕", width=2, style="Danger.TButton",
                             command=lambda: self._remove_multi_row_by_inp(inp))
        del_btn.grid(row=0, column=4, padx=(2, 0))
        inp['del_btn'] = del_btn
        
        if hasattr(self, 'multi_mousewheel_func'):
            row_frame.bind("<MouseWheel>", self.multi_mousewheel_func)
            scramble_entry.bind("<MouseWheel>", self.multi_mousewheel_func)
            orientation_combo.bind("<MouseWheel>", lambda e: "break")
            solution_entry.bind("<MouseWheel>", self.multi_mousewheel_func)
            del_btn.bind("<MouseWheel>", self.multi_mousewheel_func)
        
        self.multi_inputs.append(inp)
        
        self._update_multi_row_numbers()
        self._update_multi_count()
        self._scroll_multi_to_bottom()
    
    def _scroll_multi_to_bottom(self):
        if hasattr(self, 'multi_canvas'):
            self.multi_canvas.update_idletasks()
            self.multi_canvas.yview_moveto(1.0)
    
    def _remove_multi_row_by_inp(self, inp: dict):
        if len(self.multi_inputs) <= 5:
            messagebox.showwarning("提示", "至少需要保留5组数据")
            return
        
        if inp in self.multi_inputs:
            inp['row_frame'].destroy()
            self.multi_inputs.remove(inp)
            self._update_multi_row_numbers()
            self._update_multi_count()
    
    def _update_multi_row_numbers(self):
        for i, inp in enumerate(self.multi_inputs):
            inp['num_label'].config(text=f"{i+1}")
    
    def _update_multi_count(self):
        count = len(self.multi_inputs) if hasattr(self, 'multi_inputs') else 0
        self.multi_count_label.config(text=f"当前 {count} 组")
    
    def _show_timeline(self):
        self.timeline_header.pack(fill=tk.X, pady=(0, 2), before=self.result_header)
        self.timeline_frame.pack(fill=tk.X, pady=(0, 8), before=self.result_header)
    
    def _hide_timeline(self):
        self.timeline_header.pack_forget()
        self.timeline_frame.pack_forget()
    
    def _on_mode_change(self, event=None):
        old_mode = '单组'
        if hasattr(self, 'multi_inputs') and self.multi_inputs:
            old_mode = '多组'
        
        if old_mode == '单组':
            self._save_single_data()
        else:
            self._save_multi_data()
        
        new_mode = self.analysis_mode_var.get()
        if new_mode == '单组':
            self._create_single_input_ui()
            self._show_timeline()
            self._load_single_data()
        else:
            self._create_multi_input_ui()
            self._load_multi_data()
    
    def _save_single_data(self):
        try:
            config = load_config()
            config["scramble"] = self.scramble_entry.get().strip()
            config["solution"] = self.solution_text.get("1.0", tk.END).strip()
            config["orientation"] = self.orientation_var.get()
            config["analysis_mode"] = "单组"
            save_config(config)
        except Exception:
            pass
    
    def _save_multi_data(self):
        try:
            config = load_config()
            multi_data = []
            for inp in self.multi_inputs:
                group_data = {
                    "scramble": inp['scramble'].get().strip(),
                    "solution": inp['solution'].get().strip(),
                    "orientation": inp['orientation_var'].get(),
                }
                multi_data.append(group_data)
            config["multi_groups"] = multi_data
            config["analysis_mode"] = "多组"
            save_config(config)
        except Exception:
            pass

    def _get_bottom_color_from_name(self, name: str):
        bottom_data = next((opt for opt in BOTTOM_COLOR_OPTIONS if opt[0] == name), None)
        if bottom_data:
            return bottom_data[1]

        old_orientation = next((opt for opt in ORIENTATION_OPTIONS if opt[0] == name), None)
        if old_orientation:
            return OPPOSITE_COLORS.get(old_orientation[1])

        return None

    def _get_bottom_name_from_saved(self, name: str) -> str:
        bottom_color = self._get_bottom_color_from_name(name)
        bottom_data = next((opt for opt in BOTTOM_COLOR_OPTIONS if opt[1] == bottom_color), None)
        return bottom_data[0] if bottom_data else BOTTOM_COLOR_NAMES[0]
    
    def _load_single_data(self):
        config = load_config()
        try:
            if config.get("scramble"):
                self.scramble_entry.insert(0, config["scramble"])
            if config.get("solution"):
                self.solution_text.insert("1.0", config["solution"])
            if config.get("orientation"):
                self.orientation_var.set(self._get_bottom_name_from_saved(config["orientation"]))
        except Exception:
            pass
    
    def _load_multi_data(self):
        if not hasattr(self, 'multi_inputs') or not self.multi_inputs:
            return
        config = load_config()
        multi_data = config.get("multi_groups", [])
        if multi_data:
            while len(self.multi_inputs) < len(multi_data):
                self._add_multi_row()
            for i, g in enumerate(multi_data):
                try:
                    inp = self.multi_inputs[i]
                    inp['scramble'].insert(0, g.get('scramble', ''))
                    inp['solution'].insert(0, g.get('solution', ''))
                    orientation = g.get('orientation', BOTTOM_COLOR_NAMES[0])
                    inp['orientation_var'].set(self._get_bottom_name_from_saved(orientation))
                except Exception:
                    pass
    
    def _load_saved_config(self):
        config = load_config()
        
        saved_mode = config.get("analysis_mode", "单组")
        if saved_mode in ["单组", "多组"]:
            self.analysis_mode_var.set(saved_mode)
        
        if config.get("api_key"):
            self.api_key_entry.insert(0, config["api_key"])
        if config.get("model"):
            self.model_var.set(config["model"])
        if config.get("models"):
            self.model_combo["values"] = config["models"]
        
        mode = self.analysis_mode_var.get()
        if mode == '多组':
            self._create_multi_input_ui()
            self._hide_timeline()
            self._load_multi_data()
        else:
            self._create_single_input_ui()
            self._show_timeline()
            self._load_single_data()
    
    def _save_current_config(self):
        mode = '单组'
        if hasattr(self, 'multi_inputs') and self.multi_inputs:
            mode = '多组'
        
        if mode == '单组':
            self._save_single_data()
        else:
            self._save_multi_data()
        
        try:
            config = load_config()
            config["api_key"] = self.api_key_entry.get().strip()
        except Exception:
            pass
        try:
            config["model"] = self.model_var.get()
        except Exception:
            pass
        try:
            config["models"] = list(self.model_combo["values"]) if self.model_combo["values"] else []
        except Exception:
            pass
        save_config(config)
    
    def _on_close(self):
        log.info("关闭程序")
        self._save_current_config()
        self._clear_status()
        self._stream_stop = True
        self.root.destroy()
    
    def _clear(self):
        log.info("清空输入")
        mode = self.analysis_mode_var.get()
        
        if mode == '单组':
            self.scramble_entry.delete(0, tk.END)
            self.solution_text.delete(1.0, tk.END)
        elif hasattr(self, 'multi_inputs') and self.multi_inputs:
            for inp in self.multi_inputs:
                inp['scramble'].delete(0, tk.END)
                inp['solution'].delete(0, tk.END)
        
        self.result_text.delete(1.0, tk.END)
        self.timeline_canvas.delete("all")
    
    def _refresh_models(self):
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            messagebox.showwarning("警告", "请先输入API Key！")
            return
        
        log.info("刷新模型列表")
        self.refresh_btn.config(state="disabled")
        self.root.config(cursor="watch")
        
        def do_refresh():
            try:
                models = fetch_models(api_key)
                self.root.after(0, lambda: self._on_models_fetched(models, None))
            except Exception as e:
                self.root.after(0, lambda: self._on_models_fetched(None, str(e)))
        
        threading.Thread(target=do_refresh, daemon=True).start()
    
    def _on_models_fetched(self, models, error):
        self.refresh_btn.config(state="normal")
        self.root.config(cursor="")
        
        if error:
            log.error(f"获取模型列表失败: {error}")
            messagebox.showerror("错误", f"获取模型列表失败:\n{error}")
            return
        
        if models:
            log.info(f"获取到 {len(models)} 个模型: {models[:5]}...")
            self.model_combo["values"] = models
            self.model_var.set(models[0])
            messagebox.showinfo("成功", f"获取到 {len(models)} 个模型")
        else:
            log.warning("未获取到任何模型")
            messagebox.showwarning("警告", "未获取到任何模型")
    
    def _on_canvas_resize(self, event):
        if self._last_analyzer is not None:
            self._draw_timeline(self._last_analyzer)
    
    def _draw_timeline(self, analyzer: CFOPAnalyzer):
        self.timeline_canvas.delete("all")
        timestamps = analyzer.phase_timestamps
        if not timestamps:
            return
        
        canvas_width = self.timeline_canvas.winfo_width()
        if canvas_width < 100:
            canvas_width = 720
        
        margin_left = 40
        margin_right = 20
        bar_y = 30
        bar_height = 28
        axis_y = bar_y + bar_height + 8
        draw_width = canvas_width - margin_left - margin_right
        
        all_times = []
        for phase in PHASE_ORDER:
            if phase in timestamps:
                all_times.extend([timestamps[phase]["start"], timestamps[phase]["end"]])
        if not all_times:
            return
        
        time_min = min(all_times)
        time_max = max(all_times)
        if time_max == time_min:
            time_max = time_min + 1
        
        def time_to_x(t):
            return margin_left + (t - time_min) / (time_max - time_min) * draw_width
        
        continuous_start = None
        for phase in PHASE_ORDER:
            if phase in timestamps and timestamps[phase]["end"] > timestamps[phase]["start"]:
                if continuous_start is None:
                    continuous_start = timestamps[phase]["start"]
                
                x_start = time_to_x(continuous_start)
                x_end = time_to_x(timestamps[phase]["end"])
                color = PHASE_COLORS.get(phase, "#b2bec3")
                label = PHASE_LABELS.get(phase, phase)
                total_duration_s = (timestamps[phase]["end"] - continuous_start) / 1000.0
                
                self.timeline_canvas.create_rectangle(x_start, bar_y, x_end, bar_y + bar_height,
                                                       fill=color, outline="", width=0)
                mid_x = (x_start + x_end) / 2
                
                if (x_end - x_start) > 25:
                    self.timeline_canvas.create_text(mid_x, bar_y - 10, text=label,
                                                      font=("Microsoft YaHei", 8, "bold"), fill=color)
                
                time_text = f"{total_duration_s:.2f}s"
                if (x_end - x_start) > 45:
                    self.timeline_canvas.create_text(mid_x, bar_y + bar_height / 2,
                                                      text=time_text,
                                                      font=("Consolas", 8, "bold"), fill="white")
                else:
                    self.timeline_canvas.create_text(x_end + 4, bar_y + bar_height / 2,
                                                      text=time_text, anchor=tk.W,
                                                      font=("Consolas", 8), fill=color)
                
                continuous_start = timestamps[phase]["end"]
        
        self.timeline_canvas.create_line(margin_left, axis_y, canvas_width - margin_right, axis_y,
                                          fill=THEME["border"], width=1)
        tick_count = 8
        for i in range(tick_count + 1):
            t = time_min + (time_max - time_min) * i / tick_count
            x = time_to_x(t)
            self.timeline_canvas.create_line(x, axis_y, x, axis_y + 4, fill=THEME["border"], width=1)
            self.timeline_canvas.create_text(x, axis_y + 14, text=f"{t / 1000:.1f}s",
                                              font=("Consolas", 8), fill="#636e72")
    
    def _stop_analyze(self):
        log.info("停止AI分析")
        self._stream_stop = True
        self.ai_analyze_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._clear_status()
    
    def _set_status(self, text: str):
        if self._status_after_id:
            self.root.after_cancel(self._status_after_id)
            self._status_after_id = None
        self.status_label.config(text=text)
    
    def _clear_status(self):
        self._animation_running = False
        if self._status_after_id:
            self.root.after_cancel(self._status_after_id)
            self._status_after_id = None
        if self._animation_after_id:
            self.root.after_cancel(self._animation_after_id)
            self._animation_after_id = None
        self.status_label.config(text="")
        self.ai_status_label.config(text="")
    
    def _start_ai_status_animation(self, status_type: str = "thinking"):
        self._stop_ai_status_animation()
        
        if status_type == "building":
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            text = "构建分析数据"
        elif status_type == "thinking":
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            text = "AI思考中"
        elif status_type == "output":
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            text = "AI输出中"
        else:
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            text = status_type
        
        self._animation_running = True
        self._animation_frames = frames
        self._animation_text = text
        self._animation_index = 0
        
        def animate():
            if not self._animation_running:
                return
            frame = self._animation_frames[self._animation_index % len(self._animation_frames)]
            self.ai_status_label.config(text=f"  {frame} {self._animation_text}")
            self._animation_index += 1
            self._animation_after_id = self.root.after(100, animate)
        
        animate()
    
    def _stop_ai_status_animation(self):
        self._animation_running = False
        if self._animation_after_id:
            self.root.after_cancel(self._animation_after_id)
            self._animation_after_id = None
        self.ai_status_label.config(text="")
    
    def _reset_analysis_ui(self):
        """重置分析相关的UI状态（恢复按钮）"""
        try:
            self.ai_analyze_btn.config(state="normal")
            if hasattr(self, 'stop_btn'):
                self.stop_btn.config(state="disabled")
            self._stop_ai_status_animation()
            self._set_status("")
            self._stream_stop = True
        except Exception as ex:
            if log:
                log.debug(f"重置UI状态异常: {ex}")
    
    def _save_result(self):
        content = self.result_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "没有可保存的分析结果！")
            return
        
        os.makedirs(RESULT_DIR, exist_ok=True)
        
        default_name = ""
        mode = self.analysis_mode_var.get()
        
        if mode == '单组' and self._last_analyzer:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                scramble = self.scramble_entry.get().strip().replace(" ", "")
                total_time = self._last_analyzer.get_total_time()
                default_name = f"{date_str}_{scramble}_{total_time:.1f}s"
            except Exception:
                pass
        elif mode == '多组' and hasattr(self, 'multi_inputs') and self.multi_inputs:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            count = len(self.multi_inputs)
            default_name = f"{date_str}_多组{count}组"
        
        initial_dir = RESULT_DIR
        filepath = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="保存分析结果"
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                log.info(f"保存分析结果到: {filepath}")
                messagebox.showinfo("成功", f"结果已保存到:\n{filepath}")
            except Exception as e:
                log.error(f"保存结果失败: {str(e)}")
                messagebox.showerror("错误", f"保存失败:\n{str(e)}")
    
    def _validate_analyzer(self, analyzer: CFOPAnalyzer) -> str:
        result = analyzer.analyze()
        
        cross = result.get("cross") or []
        oll = result.get("oll") or []
        pll = result.get("pll") or []
        f2l_all = [result.get(f"f2l{i}") or [] for i in range(1, 5)]
        
        total_steps = len(cross) + len(oll) + len(pll) + sum(len(f) for f in f2l_all)
        
        if total_steps == 0:
            return "步骤拆解异常：未识别到任何还原步骤\n\n请检查输入的打乱和还原步骤是否正确"
        
        skipped_phases = []
        if not cross:
            skipped_phases.append("Cross（打乱即完成或已归位）")
        if not any(f2l_all):
            skipped_phases.append("F2L（所有槽位已归位）")
        elif len([f for f in f2l_all if f]) < 4:
            skipped_count = 4 - len([f for f in f2l_all if f])
            skipped_phases.append(f"{skipped_count}组F2L（已归位跳过）")
        if not oll:
            skipped_phases.append("OLL（顶层朝向已正确）")
        if not pll:
            skipped_phases.append("PLL（顶层排列已正确）")
        
        if skipped_phases:
            log.info(f"检测到跳步阶段: {', '.join(skipped_phases)}")
        
        return ""
    
    def _ai_analyze(self):
        mode = self.analysis_mode_var.get()
        count = 1 if mode == '单组' else (len(self.multi_inputs) if hasattr(self, 'multi_inputs') and self.multi_inputs else 0)
        if count <= 0:
            messagebox.showwarning("警告", "请先输入数据！")
            return

        model = self.model_var.get() or "未选择"

        msg = f"本次使用 AI 模型: {model}\n\n是否开始分析？"
        if not messagebox.askyesno("确认分析", msg):
            return

        self.ai_analyze_btn.config(state="disabled")
        self._start_ai_status_animation("building")
        threading.Thread(target=self._do_analysis_in_thread, args=(mode,), daemon=True).start()

    def _do_analysis_in_thread(self, mode: str):
        self.root.after(0, lambda: self._start_analysis(mode))
    
    def _start_analysis(self, mode: str):
        if mode == '单组':
            self._do_single_analysis()
        else:
            self._do_multi_analysis()

    def _do_single_analysis(self):
        scramble = self.scramble_entry.get().strip()
        solution = self.solution_text.get(1.0, tk.END).strip()
        api_key = self.api_key_entry.get().strip()
        model = self.model_var.get()
        
        bottom_name = self.orientation_var.get()
        bottom_color = self._get_bottom_color_from_name(bottom_name)
        
        if not bottom_color:
            messagebox.showwarning("错误", "请选择有效的底色")
            return
        
        if not scramble or not solution:
            messagebox.showwarning("警告", "请先输入打乱公式和还原步骤！")
            return
        if not api_key:
            messagebox.showwarning("警告", "请输入API Key！")
            return
        if not model:
            messagebox.showwarning("警告", "请选择模型！")
            return
        
        log.info(f"开始AI分析, 模型: {model}, 打乱: {scramble}, 底色: {bottom_color}")
        
        self._start_ai_status_animation("building")
        
        try:
            analyzer = CFOPAnalyzer.from_bottom_color(scramble, solution, bottom_color)
            
            validation_errors = self._validate_analyzer(analyzer)
            if validation_errors:
                self._reset_analysis_ui()
                messagebox.showerror("步骤拆解异常", validation_errors)
                return
            
            system_prompt, user_prompt = analyzer.build_ai_prompt()
            
            log.info(f"AI分析System提示词:\n{system_prompt}")
            log.info(f"AI分析User提示词:\n{user_prompt}")
            self._draw_timeline(analyzer)
            self._last_analyzer = analyzer
        except Exception as e:
            log.error(f"构建分析数据失败: {str(e)}")
            self._reset_analysis_ui()
            messagebox.showerror("错误", f"构建分析数据失败:\n{str(e)}")
            return
        
        self._stream_stop = False
        self._stream_buffer = ""
        self._reasoning_buffer = ""
        self._solution_summary = analyzer.format_output()
        self._count_consumed = False
        self.ai_analyze_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        
        scramble = self.scramble_entry.get().strip()
        self.result_text.insert(tk.END, "【解法复盘】\n\n", "normal")
        self.result_text.insert(tk.END, f"【打乱】:{scramble}\n", "normal")
        self.result_text.insert(
            tk.END,
            f"【底色】:{bottom_name} | 【自动朝向】:{get_orientation_desc(analyzer.top_color, analyzer.front_color)}\n",
            "normal"
        )
        for line in self._solution_summary.split("\n"):
            self.result_text.insert(tk.END, line + "\n", "normal")
        self.result_text.insert(tk.END, "\n---\n\n", "hr")
        
        self._start_ai_status_animation("thinking")
        
        def do_stream():
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    stream=True,
                    max_tokens=4096
                )
                has_output = False
                for chunk in stream:
                    if self._stream_stop:
                        self.root.after(0, self._on_stream_done)
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        self._reasoning_buffer += delta.reasoning_content
                        if not has_output:
                            self.root.after(0, lambda: self._start_ai_status_animation("thinking"))
                            self.root.after(0, self._schedule_render)
                    elif delta.content:
                        if not has_output:
                            has_output = True
                            self._reasoning_buffer = ""
                            self.root.after(0, lambda: self._start_ai_status_animation("output"))
                        self._stream_buffer += delta.content
                        self.root.after(0, self._schedule_render)
                else:
                    self.root.after(0, self._on_stream_done)
                    return
                
                self.root.after(0, self._on_stream_done)
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._on_ai_error(error_msg))
        
        threading.Thread(target=do_stream, daemon=True).start()
    
    def _schedule_render(self):
        if self._render_pending:
            return
        self._render_pending = True
        self.root.after(150, self._do_render)
    
    def _do_render(self):
        self._render_pending = False
        self._render_buffer()
    
    def _render_buffer(self):
        is_at_bottom = self._is_scroll_at_bottom()
        
        if not is_at_bottom:
            scroll_pos = self.result_text.yview()
        
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", tk.END)
        
        if self._stream_buffer:
            mode = self.analysis_mode_var.get()
            if self._solution_summary:
                self.result_text.insert(tk.END, self._solution_summary, "normal")
            elif mode == '单组':
                try:
                    scramble = self.scramble_entry.get().strip()
                    self.result_text.insert(tk.END, "【解法复盘】\n\n", "normal")
                    self.result_text.insert(tk.END, f"【打乱】:{scramble}\n", "normal")
                    for line in self._solution_summary.split("\n"):
                        self.result_text.insert(tk.END, line + "\n", "normal")
                    self.result_text.insert(tk.END, "\n---\n\n", "hr")
                except Exception:
                    pass
            render_markdown(self.result_text, self._stream_buffer)
        elif self._reasoning_buffer:
            self.result_text.insert(tk.END, "🤔 AI思考中...\n\n", "italic")
            thinking_preview = self._reasoning_buffer[-500:] if len(self._reasoning_buffer) > 500 else self._reasoning_buffer
            self.result_text.insert(tk.END, thinking_preview, "normal")
        
        if is_at_bottom:
            self.result_text.see(tk.END)
        else:
            try:
                self.result_text.yview_moveto(scroll_pos[0])
            except:
                pass
    
    def _is_scroll_at_bottom(self) -> bool:
        try:
            visible_fraction = self.result_text.yview()[1]
            return visible_fraction >= 0.99
        except Exception:
            return True
    
    def _on_stream_done(self):
        log.info("AI分析完成")
        self._render_pending = False
        self._render_buffer()
        self.ai_analyze_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._stream_stop = False
        self._stop_ai_status_animation()
        self._set_status("分析完成")
        self.root.after(3000, self._clear_status)
    
    def _on_ai_error(self, error_msg: str):
        log.error(f"AI分析失败: {error_msg}")
        self.ai_analyze_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._stop_ai_status_animation()
        self._clear_status()
        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, f"分析失败: {error_msg}")
    
    def _do_multi_analysis(self):
        api_key = self.api_key_entry.get().strip()
        model = self.model_var.get()
        
        if not api_key:
            messagebox.showwarning("警告", "请输入API Key！")
            return
        if not model:
            messagebox.showwarning("警告", "请选择模型！")
            return
        
        if not hasattr(self, 'multi_inputs') or not self.multi_inputs:
            messagebox.showwarning("警告", "请先输入数据！")
            return
        
        groups_data = []
        for i, inp in enumerate(self.multi_inputs):
            scramble = inp['scramble'].get().strip()
            solution = inp['solution'].get().strip()
            bottom_name = inp['orientation_var'].get()
            bottom_color = self._get_bottom_color_from_name(bottom_name)
            
            if not bottom_color:
                messagebox.showwarning("警告", f"第 {i+1} 组底色无效，请检查！")
                return
            
            if not scramble or not solution:
                messagebox.showwarning("警告", f"第 {i+1} 组数据不完整，请检查！")
                return
            
            groups_data.append({
                'index': i + 1,
                'scramble': scramble,
                'solution': solution,
                'bottom_color': bottom_color,
                'bottom_name': bottom_name
            })
        
        count = len(groups_data)
        log.info(f"开始多组分析, 模型: {model}, 共 {count} 组数据")
        
        self._start_ai_status_animation("building")
        
        analyzers = []
        for g in groups_data:
            try:
                analyzer = CFOPAnalyzer.from_bottom_color(g['scramble'], g['solution'], g['bottom_color'])
                validation_errors = self._validate_analyzer(analyzer)
                if validation_errors:
                    self._reset_analysis_ui()
                    messagebox.showerror(f"第 {g['index']} 组步骤拆解异常", validation_errors)
                    return
                analyzers.append(analyzer)
            except Exception as e:
                log.error(f"第 {g['index']} 组构建分析数据失败: {str(e)}")
                self._reset_analysis_ui()
                messagebox.showerror("错误", f"第 {g['index']} 组构建分析数据失败:\n{str(e)}")
                return
        
        system_prompt, user_prompt = self._build_multi_analysis_prompts(analyzers)
        
        log.info(f"多组分析System提示词:\n{system_prompt}")
        log.info(f"多组分析User提示词:\n{user_prompt}")
        
        self._stream_stop = False
        self._stream_buffer = ""
        self._reasoning_buffer = ""
        self._solution_summary = ""
        self._count_consumed = False
        
        self.ai_analyze_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        
        times = []
        for i, (g, a) in enumerate(zip(groups_data, analyzers)):
            total_time = a.get_total_time()
            times.append(total_time)
        
        multi_max_tokens = 4096 + count * 800
        if multi_max_tokens > 16384:
            multi_max_tokens = 16384
        self._multi_max_tokens = multi_max_tokens
        
        if times:
            avg_time = sum(times) / len(times)
            sorted_times = sorted(times)
            ao_avg = sum(sorted_times[1:-1]) / (len(times) - 2) if len(times) >= 5 else avg_time
            variance = sum((t - avg_time) ** 2 for t in times) / len(times)
            std_dev = variance ** 0.5
            best_idx = times.index(min(times)) + 1
            worst_idx = times.index(max(times)) + 1
            
            summary_lines = [f"【多组分析】共 {count} 组\n\n"]
            
            summary_lines.append(f"## 整体数据统计\n")
            summary_lines.append(f"- 总组数: {count}\n")
            summary_lines.append(f"- 各组时间: {', '.join([f'{t:.2f}s' for t in times])}\n")
            summary_lines.append(f"- 平均时间: {avg_time:.2f}s\n")
            if count >= 5:
                summary_lines.append(f"- 去头尾平均: {ao_avg:.2f}s\n")
                summary_lines.append(f"- 波动度(标准差): {std_dev:.2f}s\n")
            summary_lines.append(f"- 最佳组: 第{best_idx}组 ({min(times):.2f}s)\n")
            summary_lines.append(f"- 最差组: 第{worst_idx}组 ({max(times):.2f}s)\n")
            
            summary_lines.append(f"\n## 各组解法复盘\n")
            for i, (g, a) in enumerate(zip(groups_data, analyzers)):
                front_desc = get_orientation_desc(a.top_color, a.front_color)
                summary_lines.append(
                    f"\n### 第 {i+1} 组 (总时间: {times[i]:.2f}s, "
                    f"底色: {g['bottom_name']}, 自动前色: {front_desc})\n"
                )
                summary_lines.append(a.format_output())
                summary_lines.append("\n")
            
            summary_lines.append("\n---\n\n")
            self._solution_summary = "".join(summary_lines)
        
        self._start_ai_status_animation("thinking")
        
        def do_stream():
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    stream=True,
                    max_tokens=self._multi_max_tokens
                )
                has_output = False
                for chunk in stream:
                    if self._stream_stop:
                        self.root.after(0, self._on_stream_done)
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        self._reasoning_buffer += delta.reasoning_content
                        if not has_output:
                            self.root.after(0, lambda: self._start_ai_status_animation("thinking"))
                            self.root.after(0, self._schedule_render)
                    elif delta.content:
                        if not has_output:
                            has_output = True
                            self._reasoning_buffer = ""
                            self.root.after(0, lambda: self._start_ai_status_animation("output"))
                        self._stream_buffer += delta.content
                        self.root.after(0, self._schedule_render)
                else:
                    self.root.after(0, self._on_stream_done)
                    return
                
                self.root.after(0, self._on_stream_done)
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._on_ai_error(error_msg))
        
        threading.Thread(target=do_stream, daemon=True).start()
    
    def _build_multi_analysis_prompts(self, analyzers):
        from config import SYSTEM_PROMPT, USER_MULTI_TEMPLATE, AI_PAUSE_THRESHOLD_SEC
        
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
            groups_detail += f"\n### 第 {i+1} 组 (总时间: {times[i]:.2f}s)\n"
            groups_detail += analyzer.format_output()
            groups_detail += "\n"
        
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
            groups_detail=groups_detail
        )
        
        return (system, user)
