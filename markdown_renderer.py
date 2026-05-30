"""
Markdown渲染工具
"""

import re
import tkinter as tk


def configure_markdown_tags(text_widget: tk.Text):
    """为tkinter文本控件配置Markdown渲染所需的标签样式"""
    text_widget.tag_configure("h1", font=("Microsoft YaHei", 16, "bold"), foreground="#1a1a2e",
                              spacing3=6)
    text_widget.tag_configure("h2", font=("Microsoft YaHei", 14, "bold"), foreground="#16213e",
                              spacing1=10, spacing3=6)
    text_widget.tag_configure("h3", font=("Microsoft YaHei", 12, "bold"), foreground="#0f3460",
                              spacing1=8, spacing3=4)
    text_widget.tag_configure("bold", font=("Consolas", 11, "bold"), foreground="#2d3436")
    text_widget.tag_configure("italic", font=("Consolas", 11, "italic"), foreground="#636e72")
    text_widget.tag_configure("code", font=("Consolas", 10), foreground="#e17055",
                              background="#ffeaa7", relief="flat", borderwidth=0)
    text_widget.tag_configure("list", lmargin1=20, lmargin2=30)
    text_widget.tag_configure("normal", font=("Microsoft YaHei", 11), foreground="#2d3436")
    text_widget.tag_configure("hr", font=("", 2), foreground="#dfe6e9")


def _render_inline(text_widget: tk.Text, content: str, base_tag: str = "normal"):
    """渲染行内Markdown格式（加粗、斜体、行内代码）"""
    pos = 0
    pattern = re.compile(r'(`+)(.+?)\1|\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*')
    while pos < len(content):
        m = pattern.search(content, pos)
        if not m:
            text_widget.insert(tk.END, content[pos:], base_tag)
            break
        if m.start() > pos:
            text_widget.insert(tk.END, content[pos:m.start()], base_tag)
        if m.group(1):
            text_widget.insert(tk.END, m.group(2), "code")
        elif m.group(3):
            text_widget.insert(tk.END, m.group(3), "bold")
        elif m.group(4):
            text_widget.insert(tk.END, m.group(4), "bold")
        elif m.group(5):
            text_widget.insert(tk.END, m.group(5), "italic")
        pos = m.end()
    text_widget.insert(tk.END, "\n")


def render_markdown(text_widget: tk.Text, text: str):
    """将Markdown文本渲染到tkinter文本控件"""
    text_widget.config(state="normal")
    lines = text.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('### '):
            _render_inline(text_widget, stripped[4:], "h3")
        elif stripped.startswith('## '):
            _render_inline(text_widget, stripped[3:], "h2")
        elif stripped.startswith('# '):
            _render_inline(text_widget, stripped[2:], "h1")
        elif stripped == '---' or stripped == '***' or stripped == '___':
            text_widget.insert(tk.END, "\u2500" * 60 + "\n", "hr")
        elif stripped.startswith('- '):
            text_widget.insert(tk.END, "  \u2022 ", "list")
            _render_inline(text_widget, stripped[2:], "normal")
        elif re.match(r'^\d+\.\s', stripped):
            num = re.match(r'^(\d+\.)\s', stripped).group(1)
            text_widget.insert(tk.END, f"  {num} ", "list")
            content = re.sub(r'^\d+\.\s', '', stripped)
            _render_inline(text_widget, content, "normal")
        elif stripped == '':
            text_widget.insert(tk.END, "\n", "normal")
        else:
            _render_inline(text_widget, stripped, "normal")
