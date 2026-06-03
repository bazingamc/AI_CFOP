"""
GUI应用主类 - CFOPAnalyzerGUI
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import List, Dict
import threading
import json
import re
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
from api_utils import load_config, save_config, fetch_models, _xor_encode, _xor_decode
from markdown_renderer import configure_markdown_tags, render_markdown
import memory_db
import user_manager


log = None

def set_logger(logger):
    global log
    log = logger


class CFOPAnalyzerGUI:
    """CFOP分析器的主GUI应用"""

    def __init__(self, root):
        self.root = root
        self.root.title("AI_CFOP V1.0")
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
        self._clipboard_monitor_id = None
        self._last_clipboard = ""
        self._smart_paste_var = tk.BooleanVar(value=True)
        self._use_memory_var = tk.BooleanVar(value=True)
        self._stats_expanded = False

        self._current_user_id = None
        self._current_username = ""
        self._setup_styles()
        self._create_widgets()
        self._load_saved_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.timeline_canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.after(1, self._show_user_select_and_init)

    def _show_user_select_and_init(self):
        try:
            memory_db.init_db()
            user_manager.init_users_table()
            config = load_config()
            last_user_id = config.get("last_user_id")
            users = user_manager.get_all_users()
            if not users:
                uid = user_manager.ensure_default_user()
                users = user_manager.get_all_users()
            if last_user_id:
                user = user_manager.get_user(last_user_id)
                if user:
                    self._select_user_and_continue(user)
                    return
            self._show_user_select_dialog()
        except Exception as e:
            if log:
                log.error(f"用户选择初始化失败: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            users = user_manager.get_all_users()
            if users:
                self._select_user_and_continue(users[0])
            else:
                uid = user_manager.ensure_default_user()
                user = user_manager.get_user(uid)
                if user:
                    self._select_user_and_continue(user)

    def _select_user_and_continue(self, user: dict):
        self._current_user_id = user["id"]
        self._current_username = user["username"]
        memory_db.set_current_user(user["id"])
        config = load_config()
        config["last_user_id"] = user["id"]
        save_config(config)
        self._update_user_display()
        self._async_init_tasks()

    def _show_user_select_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("选择用户")
        dialog.configure(bg=THEME["bg"])
        dialog.resizable(False, False)
        dialog.attributes('-topmost', True)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._on_user_dialog_close(dialog))

        dialog_width = 500
        dialog_height = 520
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=24, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        title_label = tk.Label(main_frame, text="选择用户",
                               font=("Microsoft YaHei", 16, "bold"),
                               fg=THEME["accent"], bg=THEME["card_bg"])
        title_label.pack(pady=(0, 16))

        list_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, bg=THEME["card_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=THEME["card_bg"])
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_user_list():
            for w in scroll_frame.winfo_children():
                w.destroy()
            users = user_manager.get_all_users()
            for u in users:
                row = tk.Frame(scroll_frame, bg=THEME["card_bg"], pady=6)
                row.pack(fill=tk.X, padx=8)

                avatar_path = u.get("avatar", "")
                if avatar_path and os.path.isfile(avatar_path):
                    try:
                        from PIL import Image as PILImage, ImageTk
                        img = PILImage.open(avatar_path).resize((40, 40), PILImage.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        avatar_lbl = tk.Label(row, image=photo, bg=THEME["card_bg"])
                        avatar_lbl.image = photo
                        avatar_lbl.pack(side=tk.LEFT, padx=(0, 10))
                    except Exception:
                        _add_default_avatar(row)
                else:
                    _add_default_avatar(row)

                name_lbl = tk.Label(row, text=u["username"],
                                    font=("Microsoft YaHei", 12),
                                    fg=THEME["fg"], bg=THEME["card_bg"])
                name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                select_btn = ttk.Button(row, text="选择",
                                        command=lambda uid=u["id"]: self._on_user_selected(uid, dialog),
                                        style="Accent.TButton")
                select_btn.pack(side=tk.RIGHT, padx=(4, 0))

                edit_btn = tk.Button(row, text="✏️", width=3,
                                     font=("Microsoft YaHei", 9),
                                     fg="#fff", bg=THEME["accent"],
                                     activebackground="#5B8DEE",
                                     relief="flat", cursor="hand2",
                                     command=lambda uid=u["id"], uname=u["username"]: self._show_edit_user_dialog(dialog, uid, uname, refresh_user_list))
                edit_btn.pack(side=tk.RIGHT, padx=(4, 0))

                if u["id"] != self._current_user_id:
                    del_btn = tk.Button(row, text="🗑", width=3,
                                        font=("Microsoft YaHei", 9),
                                        fg="#fff", bg=THEME["danger"],
                                        activebackground="#d63031",
                                        relief="flat", cursor="hand2",
                                        command=lambda uid=u["id"]: self._delete_user_confirm(uid, refresh_user_list))
                    del_btn.pack(side=tk.RIGHT, padx=(4, 0))

        def _add_default_avatar(parent):
            default_path = user_manager.get_default_avatar_path()
            if os.path.isfile(default_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(default_path).resize((40, 40), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(parent, image=photo, bg=THEME["card_bg"])
                    lbl.image = photo
                    lbl.pack(side=tk.LEFT, padx=(0, 10))
                    return
                except Exception:
                    pass
            avatar_canvas = tk.Canvas(parent, width=40, height=40,
                                      highlightthickness=0, bg=THEME["accent"])
            avatar_canvas.create_text(20, 20, text="👤",
                                      font=("Microsoft YaHei", 16), fill="white")
            avatar_canvas.pack(side=tk.LEFT, padx=(0, 10))

        refresh_user_list()

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(16, 0))

        create_btn = ttk.Button(btn_frame, text="➕ 创建用户",
                                command=lambda: self._show_create_user_dialog(dialog, refresh_user_list),
                                style="Accent.TButton")
        create_btn.pack(side=tk.LEFT)

    def _on_user_selected(self, user_id: int, dialog):
        user = user_manager.get_user(user_id)
        if user:
            dialog.destroy()
            self._select_user_and_continue(user)

    def _on_user_dialog_close(self, dialog):
        if self._current_user_id is None:
            users = user_manager.get_all_users()
            if users:
                self._select_user_and_continue(users[0])
                dialog.destroy()
            else:
                uid = user_manager.ensure_default_user()
                user = user_manager.get_user(uid)
                self._select_user_and_continue(user)
                dialog.destroy()
        else:
            dialog.destroy()

    def _show_create_user_dialog(self, parent, on_created=None):
        dialog = tk.Toplevel(parent)
        dialog.title("创建用户")
        dialog.configure(bg=THEME["bg"])
        dialog.resizable(False, False)
        dialog.attributes('-topmost', True)
        dialog.grab_set()

        dialog_width = 400
        dialog_height = 240
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=20, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(main_frame, text="用户名:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky=tk.W, pady=8)
        name_entry = tk.Entry(main_frame, width=20, font=("Microsoft YaHei", 10),
                              bg=THEME["input_bg"], fg=THEME["fg"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=THEME["border"],
                              highlightcolor=THEME["accent"])
        name_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=(8, 0))

        random_btn = ttk.Button(main_frame, text="🎲 随机",
                                command=lambda: name_entry.delete(0, tk.END) or name_entry.insert(0, user_manager.generate_random_username()),
                                style="Secondary.TButton")
        random_btn.grid(row=0, column=2, padx=(8, 0), pady=8)

        error_label = tk.Label(main_frame, text="", bg=THEME["card_bg"],
                               fg=THEME["danger"], font=("Microsoft YaHei", 9))
        error_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.grid(row=2, column=0, columnspan=3, pady=(8, 0))

        def on_create():
            username = name_entry.get().strip()
            if not username:
                error_label.config(text="用户名不能为空")
                return
            if user_manager.check_username_exists(username):
                error_label.config(text="用户名已存在")
                return
            uid = user_manager.create_user(username)
            if uid:
                dialog.destroy()
                if on_created:
                    on_created()
            else:
                error_label.config(text="创建失败")

        ttk.Button(btn_frame, text="创建", command=on_create,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy,
                   style="Secondary.TButton").pack(side=tk.LEFT)

        main_frame.columnconfigure(1, weight=1)

    def _show_user_manage_dialog(self, parent, on_changed=None):
        dialog = tk.Toplevel(parent)
        dialog.title("用户管理")
        dialog.configure(bg=THEME["bg"])
        dialog.resizable(False, False)
        dialog.attributes('-topmost', True)
        dialog.grab_set()

        dialog_width = 500
        dialog_height = 480
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=16, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(main_frame, text="用户管理",
                 font=("Microsoft YaHei", 14, "bold"),
                 fg=THEME["accent"], bg=THEME["card_bg"]).pack(pady=(0, 12))

        list_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, bg=THEME["card_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=THEME["card_bg"])
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_list():
            for w in scroll_frame.winfo_children():
                w.destroy()
            users = user_manager.get_all_users()
            for u in users:
                row = tk.Frame(scroll_frame, bg=THEME["card_bg"], pady=4)
                row.pack(fill=tk.X, padx=4, pady=2)

                avatar_path = u.get("avatar", "")
                if avatar_path and os.path.isfile(avatar_path):
                    try:
                        from PIL import Image as PILImage, ImageTk
                        img = PILImage.open(avatar_path).resize((32, 32), PILImage.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        avatar_lbl = tk.Label(row, image=photo, bg=THEME["card_bg"])
                        avatar_lbl.image = photo
                        avatar_lbl.pack(side=tk.LEFT, padx=(0, 8))
                    except Exception:
                        _add_small_avatar(row)
                else:
                    _add_small_avatar(row)

                current_mark = " ✓" if u["id"] == self._current_user_id else ""
                name_lbl = tk.Label(row, text=u["username"] + current_mark,
                                    font=("Microsoft YaHei", 11),
                                    fg=THEME["fg"], bg=THEME["card_bg"])
                name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                edit_btn = tk.Button(row, text="✏️", width=3,
                                     font=("Microsoft YaHei", 9),
                                     fg="#fff", bg=THEME["accent"],
                                     activebackground="#5B8DEE",
                                     relief="flat", cursor="hand2",
                                     command=lambda uid=u["id"], uname=u["username"]: self._show_edit_user_dialog(dialog, uid, uname, refresh_list))
                edit_btn.pack(side=tk.RIGHT, padx=(4, 0))

                if u["id"] != self._current_user_id:
                    del_btn = tk.Button(row, text="删除", width=4,
                                        font=("Microsoft YaHei", 8),
                                        fg="#fff", bg=THEME["danger"],
                                        activebackground="#d63031",
                                        relief="flat", cursor="hand2",
                                        command=lambda uid=u["id"]: self._delete_user_confirm(uid, refresh_list))
                    del_btn.pack(side=tk.RIGHT, padx=(4, 0))

        def _add_small_avatar(parent):
            default_path = user_manager.get_default_avatar_path()
            if os.path.isfile(default_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(default_path).resize((32, 32), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(parent, image=photo, bg=THEME["card_bg"])
                    lbl.image = photo
                    lbl.pack(side=tk.LEFT, padx=(0, 8))
                    return
                except Exception:
                    pass
            c = tk.Canvas(parent, width=32, height=32, highlightthickness=0, bg=THEME["accent"])
            c.create_text(16, 16, text="👤", font=("Microsoft YaHei", 12), fill="white")
            c.pack(side=tk.LEFT, padx=(0, 8))

        refresh_list()

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(btn_frame, text="➕ 创建用户",
                   command=lambda: self._show_create_user_dialog(dialog, refresh_list),
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="关闭",
                   command=lambda: (on_changed() if on_changed else None, dialog.destroy()),
                   style="Secondary.TButton").pack(side=tk.RIGHT)

    def _show_edit_user_dialog(self, parent, user_id: int, current_name: str, on_done=None):
        dialog = tk.Toplevel(parent)
        dialog.title("修改用户")
        dialog.configure(bg=THEME["bg"])
        dialog.resizable(False, False)
        dialog.attributes('-topmost', True)
        dialog.grab_set()

        dialog_width = 420
        dialog_height = 280
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=20, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(main_frame, text="修改用户信息",
                 font=("Microsoft YaHei", 13, "bold"),
                 fg=THEME["accent"], bg=THEME["card_bg"]).grid(row=0, column=0, columnspan=3, pady=(0, 12), sticky=tk.W)

        tk.Label(main_frame, text="用户名:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky=tk.W, pady=8)
        name_entry = tk.Entry(main_frame, width=18, font=("Microsoft YaHei", 10),
                              bg=THEME["input_bg"], fg=THEME["fg"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=THEME["border"],
                              highlightcolor=THEME["accent"])
        name_entry.insert(0, current_name)
        name_entry.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=(8, 0))

        random_btn = ttk.Button(main_frame, text="🎲",
                                command=lambda: name_entry.delete(0, tk.END) or name_entry.insert(0, user_manager.generate_random_username()),
                                style="Secondary.TButton")
        random_btn.grid(row=1, column=2, padx=(8, 0), pady=8)

        tk.Label(main_frame, text="头像:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky=tk.W, pady=8)

        avatar_preview_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        avatar_preview_frame.grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=8, padx=(8, 0))

        user_info = user_manager.get_user(user_id)
        current_avatar = user_info.get("avatar", "") if user_info else ""
        avatar_preview = tk.Canvas(avatar_preview_frame, width=48, height=48,
                                    highlightthickness=1, highlightbackground=THEME["border"],
                                    bg=THEME["card_bg"], cursor="hand2")
        avatar_preview.pack(side=tk.LEFT, padx=(0, 8))

        _avatar_photo = [None]

        def _update_avatar_preview(image_path):
            avatar_preview.delete("all")
            if image_path and os.path.isfile(image_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(image_path).resize((48, 48), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    _avatar_photo[0] = photo
                    avatar_preview.create_image(24, 24, image=photo)
                    return
                except Exception:
                    pass
            default_path = user_manager.get_default_avatar_path()
            if os.path.isfile(default_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(default_path).resize((48, 48), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    _avatar_photo[0] = photo
                    avatar_preview.create_image(24, 24, image=photo)
                    return
                except Exception:
                    pass
            avatar_preview.create_text(24, 24, text="👤", font=("Microsoft YaHei", 18), fill=THEME["accent"])

        _update_avatar_preview(current_avatar)

        new_avatar_path = [current_avatar]

        def _choose_avatar():
            dialog.grab_release()
            dialog.attributes('-topmost', False)
            dialog.lower()
            self.root.update()
            path = filedialog.askopenfilename(
                title="选择头像图片",
                filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp"), ("所有文件", "*.*")]
            )
            dialog.attributes('-topmost', True)
            dialog.lift()
            dialog.grab_set()
            if path:
                new_avatar_path[0] = path
                _update_avatar_preview(path)

        avatar_preview.bind("<Button-1>", lambda e: _choose_avatar())

        choose_btn = ttk.Button(avatar_preview_frame, text="选择图片",
                                command=_choose_avatar, style="Secondary.TButton")
        choose_btn.pack(side=tk.LEFT)

        error_label = tk.Label(main_frame, text="", bg=THEME["card_bg"],
                               fg=THEME["danger"], font=("Microsoft YaHei", 9))
        error_label.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(8, 0))

        def on_save():
            username = name_entry.get().strip()
            if not username:
                error_label.config(text="用户名不能为空")
                return
            if username != current_name and user_manager.check_username_exists(username, exclude_id=user_id):
                error_label.config(text="用户名已存在")
                return
            user_manager.update_user(user_id, username=username, avatar=new_avatar_path[0])
            if user_id == self._current_user_id:
                self._current_username = username
                self._update_user_display()
            dialog.destroy()
            if on_done:
                on_done()

        ttk.Button(btn_frame, text="保存", command=on_save,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="取消", command=dialog.destroy,
                   style="Secondary.TButton").pack(side=tk.LEFT)

        main_frame.columnconfigure(1, weight=1)

    def _delete_user_confirm(self, user_id: int, on_done=None):
        user = user_manager.get_user(user_id)
        if not user:
            return
        confirm = tk.Toplevel(self.root)
        confirm.title("确认删除")
        confirm.configure(bg=THEME["bg"])
        confirm.resizable(False, False)
        confirm.attributes('-topmost', True)
        confirm.grab_set()

        confirm_width = 360
        confirm_height = 160
        confirm.geometry(f"{confirm_width}x{confirm_height}")
        confirm.update_idletasks()
        x = (confirm.winfo_screenwidth() - confirm_width) // 2
        y = (confirm.winfo_screenheight() - confirm_height) // 2
        confirm.geometry(f"+{x}+{y}")

        frame = tk.Frame(confirm, bg=THEME["card_bg"], padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(frame, text=f"确定删除用户「{user['username']}」？",
                 font=("Microsoft YaHei", 11), bg=THEME["card_bg"],
                 fg=THEME["fg"]).pack(pady=(0, 4))
        tk.Label(frame, text="该用户的所有数据将被删除，此操作不可撤销！",
                 font=("Microsoft YaHei", 9), bg=THEME["card_bg"],
                 fg=THEME["danger"]).pack(pady=(0, 12))

        btn_frame = tk.Frame(frame, bg=THEME["card_bg"])
        btn_frame.pack()

        def do_delete():
            user_manager.delete_user(user_id)
            confirm.destroy()
            if on_done:
                on_done()

        ttk.Button(btn_frame, text="删除", command=do_delete,
                   style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(btn_frame, text="取消", command=confirm.destroy,
                   style="Secondary.TButton").pack(side=tk.LEFT)

    def _update_user_display(self):
        if hasattr(self, '_user_label'):
            self._user_label.config(text=self._current_username)
        if hasattr(self, '_user_avatar_canvas'):
            self._user_avatar_canvas.delete("all")
            default_path = user_manager.get_default_avatar_path()
            user_info = user_manager.get_user(self._current_user_id) if self._current_user_id else None
            avatar_path = user_info.get("avatar", "") if user_info else ""
            if avatar_path and os.path.isfile(avatar_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(avatar_path).resize((28, 28), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._user_avatar_canvas.create_image(14, 14, image=photo)
                    self._user_avatar_canvas._avatar_photo = photo
                    return
                except Exception:
                    pass
            if os.path.isfile(default_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    img = PILImage.open(default_path).resize((28, 28), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._user_avatar_canvas.create_image(14, 14, image=photo)
                    self._user_avatar_canvas._avatar_photo = photo
                    return
                except Exception:
                    pass
            self._user_avatar_canvas.create_text(14, 14, text="👤",
                                                  font=("Microsoft YaHei", 12), fill="white")

    def _switch_user(self):
        self._show_user_select_dialog()

    def _check_anomaly_and_confirm(self, solve_time: float, mode: str) -> bool:
        if not self._use_memory_var.get():
            return True
        avg = memory_db.get_total_time_avg()
        if avg is None or avg <= 0:
            return True
        if mode == '单组':
            threshold = 0.70
        else:
            threshold = 0.40
        diff_ratio = abs(solve_time - avg) / avg
        if diff_ratio > threshold:
            return self._show_anomaly_dialog(solve_time, avg, mode, threshold)
        return True

    def _show_anomaly_dialog(self, solve_time: float, avg: float, mode: str, threshold: float) -> bool:
        result = [None]

        dialog = tk.Toplevel(self.root)
        dialog.title("成绩异常提示")
        dialog.configure(bg=THEME["bg"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        dialog_width = 420
        dialog_height = 240
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog_width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=20, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(main_frame, text="⚠️ 成绩异常提示",
                 font=("Microsoft YaHei", 14, "bold"),
                 fg=THEME["danger"], bg=THEME["card_bg"]).pack(pady=(0, 12))

        mode_label = "单组还原" if mode == '单组' else "多组平均"
        info_text = (
            f"当前用户：{self._current_username}\n"
            f"当前用户平均水平：{avg:.2f}s\n"
            f"本次{mode_label}时间：{solve_time:.2f}s\n"
            f"偏差超过±{threshold * 100:.0f}%，请确认当前用户是否正确"
        )
        tk.Label(main_frame, text=info_text,
                 font=("Microsoft YaHei", 10),
                 fg=THEME["fg"], bg=THEME["card_bg"],
                 justify=tk.LEFT).pack(pady=(0, 16))

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.pack()

        def on_keep():
            result[0] = True
            dialog.destroy()

        def on_switch():
            result[0] = False
            dialog.destroy()
            self.root.after(100, self._switch_user)

        ttk.Button(btn_frame, text="仍使用当前用户", command=on_keep,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="切换用户", command=on_switch,
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=8)

        dialog.wait_window()
        return result[0] if result[0] is not None else True

    def _async_init_tasks(self):
        self.root.update_idletasks()
        memory_db.init_db()
        self._update_memory_count()
        self._refresh_home_stats()
        if hasattr(self, '_refresh_data_tab'):
            self._refresh_data_tab()
        if self._smart_paste_var.get():
            self._start_clipboard_monitor()
        self._set_all_controls_state("normal")

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
        except tk.TclError:
            pass
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
                        font=("Microsoft YaHei", 9), padding=2)
        
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
        
        style.configure("TNotebook", background=THEME["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", font=("Microsoft YaHei", 10),
                        padding=[16, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", THEME["card_bg"]), ("!selected", THEME["bg"])],
                  foreground=[("selected", THEME["accent"]), ("!selected", THEME["fg"])])
    
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
            max_line_width = max(len(line) for line in lines if line.strip()) if lines else 10
            
            text_width = min(max(max_line_width + 2, 30), 55)
            visible_height = 10
            
            text_widget = tk.Text(frame, font=("Microsoft YaHei", 9),
                                  bg="#ffffcc", fg=THEME["fg"],
                                  padx=8, pady=6, wrap=tk.WORD,
                                  width=text_width, height=visible_height, relief="flat",
                                  cursor="arrow")
            scrollbar = tk.Scrollbar(frame, command=text_widget.yview, width=12)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.config(yscrollcommand=scrollbar.set)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            text_widget.insert("1.0", text.strip())
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

    def _on_smart_paste_toggle(self):
        if self._smart_paste_var.get():
            self._last_clipboard = ""
            self._start_clipboard_monitor()
        else:
            self._stop_clipboard_monitor()

    def _start_clipboard_monitor(self):
        self._stop_clipboard_monitor()
        self._poll_clipboard()

    def _stop_clipboard_monitor(self):
        if self._clipboard_monitor_id:
            self.root.after_cancel(self._clipboard_monitor_id)
            self._clipboard_monitor_id = None

    def _poll_clipboard(self):
        if not self._smart_paste_var.get():
            return
        try:
            clipboard = self.root.clipboard_get()
            if clipboard != self._last_clipboard:
                self._last_clipboard = clipboard
                scramble, solution = self._parse_cstimer_clipboard(clipboard)
                if scramble or solution:
                    self._do_smart_paste(scramble, solution)
        except Exception:
            pass
        self._clipboard_monitor_id = self.root.after(500, self._poll_clipboard)

    def _is_duplicate_paste(self, scramble, solution):
        mode = self.analysis_mode_var.get()
        if mode == '单组':
            if scramble and self.scramble_entry.get().strip() == scramble:
                return True
            if solution and self.solution_text.get().strip() == solution:
                return True
        else:
            if not hasattr(self, 'multi_inputs') or not self.multi_inputs:
                return False
            for inp in self.multi_inputs:
                if scramble and inp['scramble'].get().strip() == scramble:
                    return True
                if solution and inp['solution'].get().strip() == solution:
                    return True
        return False

    def _do_smart_paste(self, scramble, solution):
        if self._is_duplicate_paste(scramble, solution):
            self._set_status("数据已存在，跳过粘贴")
            self.root.after(2000, self._clear_status)
            return

        mode = self.analysis_mode_var.get()
        if mode == '单组':
            if scramble:
                self.scramble_entry.delete(0, tk.END)
                self.scramble_entry.insert(0, scramble)
            if solution:
                self.solution_text.delete(0, tk.END)
                self.solution_text.insert(0, solution)
            self._set_status("智能粘贴成功" if (scramble and solution) else "部分粘贴成功")
            self.root.after(2000, self._clear_status)
        else:
            if not hasattr(self, 'multi_inputs') or not self.multi_inputs:
                return
            target = None
            if scramble and not solution:
                for inp in self.multi_inputs:
                    if not inp['scramble'].get().strip():
                        target = inp
                        break
            elif solution and not scramble:
                for inp in self.multi_inputs:
                    if inp['scramble'].get().strip() and not inp['solution'].get().strip():
                        target = inp
                        break
            else:
                for inp in self.multi_inputs:
                    if not inp['scramble'].get().strip() and not inp['solution'].get().strip():
                        target = inp
                        break
            if target is None:
                if solution and not scramble:
                    self._set_status("请先复制打乱公式")
                    self.root.after(2000, self._clear_status)
                    return
                if len(self.multi_inputs) < 20:
                    self._add_multi_row()
                    target = self.multi_inputs[-1]
                else:
                    target = self.multi_inputs[-1]
            if scramble:
                target['scramble'].delete(0, tk.END)
                target['scramble'].insert(0, scramble)
            if solution:
                target['solution'].delete(0, tk.END)
                target['solution'].insert(0, solution)
            self._set_status("智能粘贴成功")
            self.root.after(2000, self._clear_status)

    def _parse_cstimer_clipboard(self, text: str):
        text = text.strip()
        if not text:
            return ("", "")

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        scramble_lines = []
        solution_lines = []
        current_section = None

        for line in lines:
            if re.match(r'^\d+\.?\d*s?\s*([+]\d|DNF)?$', line, re.IGNORECASE):
                continue
            if re.match(r'^[第N]o\.?\d+', line, re.IGNORECASE):
                continue

            scramble_match = re.match(r'^(打乱公式?|Scramble)\s*[:：]\s*(.*)', line, re.IGNORECASE)
            review_match = re.match(r'^(回顾|Review)\s*[:：]\s*(.*)', line, re.IGNORECASE)

            if scramble_match:
                current_section = 'scramble'
                content = scramble_match.group(2).strip()
                if content:
                    scramble_lines.append(content)
                continue

            if review_match:
                current_section = 'solution'
                content = review_match.group(2).strip()
                if content:
                    solution_lines.append(content)
                continue

            has_timestamp = bool(re.search(r'@\d+\.?\d*', line))

            if has_timestamp:
                solution_lines.append(line)
                current_section = 'solution'
            elif current_section == 'scramble':
                scramble_lines.append(line)
            elif current_section == 'solution':
                solution_lines.append(line)
            else:
                if re.match(r'^[RULDFBMSrwuldfbmsxyz]([2\']?w?\s|$)', line):
                    scramble_lines.append(line)
                    current_section = 'scramble'

        scramble = ' '.join(scramble_lines).strip()
        solution = ' '.join(solution_lines).strip()

        return (scramble, solution)

    def _toggle_stats_panel(self):
        if self._stats_expanded:
            self._stats_panel.pack_forget()
            self._stats_toggle_btn.config(text="  ▶ 水平统计")
            self._stats_expanded = False
        else:
            self._refresh_stats_panel()
            self._stats_panel.pack(fill=tk.X, pady=(0, 8), after=self._stats_header)
            self._stats_toggle_btn.config(text="  ▼ 水平统计")
            self._stats_expanded = True

    def _refresh_stats_panel(self):
        from config import PHASE_ORDER
        avg = memory_db.get_averages()
        if not avg:
            self._stats_text.config(state="normal")
            self._stats_text.delete("1.0", tk.END)
            self._stats_text.insert("1.0", "暂无数据，完成分析后自动记录")
            self._stats_text.config(state="disabled")
            return

        sep = "─" * 80

        self._stats_text.config(state="normal")
        self._stats_text.delete("1.0", tk.END)

        pb = memory_db.get_pb()
        total_avg = memory_db.get_total_time_avg()
        total_std = memory_db.get_total_time_std()
        if pb:
            self._stats_text.insert(tk.END, "PB: ", "bold")
            self._stats_text.insert(tk.END, f"{pb['time']:.2f}s", "bold")
            self._stats_text.insert(tk.END, f" ({pb['date']})\n")
        if total_avg:
            self._stats_text.insert(tk.END, "平均: ", "bold")
            self._stats_text.insert(tk.END, f"{total_avg:.2f}s", "bold")
            if total_std:
                self._stats_text.insert(tk.END, f"  标准差: ", "bold")
                self._stats_text.insert(tk.END, f"{total_std:.2f}s\n", "bold")
            else:
                self._stats_text.insert(tk.END, "\n")

        if pb or total_avg:
            self._stats_text.insert(tk.END, sep + "\n")

        self._stats_text.insert(tk.END, f"阶段\t步数(σ)\t用时(s)(σ)\t观察(s)(σ)\t卡顿\t废步\tTPS(σ)\n")
        self._stats_text.insert(tk.END, sep + "\n")

        phase_labels = {
            "cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
            "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL",
        }
        for phase in PHASE_ORDER:
            if phase in avg:
                s = avg[phase]
                label = phase_labels.get(phase, phase)
                self._stats_text.insert(
                    tk.END,
                    f"{label}\t{s['steps']:.1f}({s['steps_std']:.1f})"
                    f"\t{s['time']:.2f}({s['time_std']:.2f})"
                    f"\t{s['observation_time']:.2f}({s['observation_time_std']:.2f})"
                    f"\t{s['stutter_count']:.1f}"
                    f"\t{s['wasted_moves']:.1f}"
                    f"\t{s['tps']:.1f}({s['tps_std']:.1f})\n"
                )

        date_range = memory_db.get_date_range()
        count = memory_db.get_record_count()
        self._stats_text.insert(tk.END, sep + "\n")
        self._stats_text.insert(tk.END, f"记录: {count}条 | 时间: {date_range} | 统计: 最近1000次")

        self._stats_text.config(state="disabled")

    def _update_memory_count(self):
        count = memory_db.get_record_count()
        if hasattr(self, '_memory_count_label'):
            self._memory_count_label.config(text=f"📝{count}条记录" if count > 0 else "暂无记录")

    def _on_stats_manage_click(self, event):
        x = event.x
        widget_width = self._stats_manage_btn.winfo_width()
        third = widget_width / 3
        if x < third:
            self._import_cstimer()
        elif x < third * 2:
            self._export_memory()
        else:
            self._clear_memory()

    def _import_cstimer(self):
        path = filedialog.askopenfilename(
            title="选择csTimer导出文件",
            filetypes=[("csTimer导出", "*.txt"), ("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        
        progress_win = tk.Toplevel(self.root)
        progress_win.title("导入csTimer数据")
        progress_win.geometry("350x120")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        progress_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 350) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
        progress_win.geometry(f"+{x}+{y}")
        
        tk.Label(progress_win, text="正在导入，请稍候...", font=("Microsoft YaHei", 10)).pack(pady=(15, 5))
        progress_label = tk.Label(progress_win, text="准备中...", font=("Microsoft YaHei", 9), fg="#666")
        progress_label.pack(pady=5)
        
        def on_progress(current, total):
            progress_label.config(text=f"处理中: {current}/{total}")
            progress_win.update()

        def do_import():
            try:
                result = memory_db.import_cstimer(path, progress_cb=on_progress)
                self.root.after(0, lambda: self._on_import_done(progress_win, result))
            except Exception as e:
                self.root.after(0, lambda: self._on_import_done(progress_win, {
                    "total": 0, "imported": 0, "skipped_no_review": 0, "skipped_parse_error": 0, "error": str(e)
                }))
        
        import threading
        t = threading.Thread(target=do_import, daemon=True)
        t.start()

    def _on_import_done(self, progress_win, result):
        try:
            progress_win.destroy()
        except Exception:
            pass
        
        self._update_memory_count()
        if hasattr(self, '_refresh_home_stats'):
            self._refresh_home_stats()
        if hasattr(self, '_refresh_data_tab'):
            self._refresh_data_tab()
        
        if "error" in result:
            messagebox.showerror("导入失败", f"导入过程中出错:\n{result['error']}")
            return
        
        msg = f"导入完成！\n\n总计: {result['total']} 条\n成功导入: {result['imported']} 条"
        if result.get('skipped_duplicate', 0) > 0:
            msg += f"\n重复跳过: {result['skipped_duplicate']} 条"
        if result.get('skipped_incomplete', 0) > 0:
            msg += f"\n未还原/阶段不全跳过: {result['skipped_incomplete']} 条"
        if result.get('skipped_no_review', 0) > 0:
            msg += f"\n无回顾数据跳过: {result['skipped_no_review']} 条"
        if result.get('skipped_parse_error', 0) > 0:
            msg += f"\n解析失败跳过: {result['skipped_parse_error']} 条"
        if result.get('skipped_abnormal', 0) > 0:
            msg += f"\n异常数据跳过: {result['skipped_abnormal']} 条"
        if result.get('skipped_cross_solved', 0) > 0:
            msg += f"\nCross预还原跳过: {result['skipped_cross_solved']} 条"
        messagebox.showinfo("导入结果", msg)

    def _export_memory(self):
        username = self._current_username or "unknown"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv")],
            initialfile=f"cfop_{username}_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not path:
            return
        count = memory_db.export_csv(path)
        if count > 0:
            messagebox.showinfo("导出成功", f"已导出 {count} 条记录到:\n{path}")
        else:
            messagebox.showwarning("提示", "没有数据可导出")

    def _clear_memory(self):
        count = memory_db.get_record_count()
        if count == 0:
            messagebox.showinfo("提示", "当前没有记忆数据")
            return
        if not messagebox.askyesno("确认清除", f"确定清除所有 {count} 条记忆数据？\n此操作不可撤销！"):
            return
        memory_db.clear_all()
        self._update_memory_count()
        if hasattr(self, '_refresh_home_stats'):
            self._refresh_home_stats()
        if hasattr(self, '_refresh_data_tab'):
            self._refresh_data_tab()
        self._set_status("记忆数据已清除")
        self.root.after(2000, self._clear_status)

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
• 生成训练建议

【交流反馈】
• 交流QQ群：322267527"""
        
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
        top_bar = tk.Frame(self.root, bg=THEME["card_bg"], padx=12, pady=6,
                           highlightthickness=0)
        top_bar.pack(fill=tk.X)

        tk.Label(top_bar, text="AI_CFOP", font=("Microsoft YaHei", 14, "bold"),
                 fg=THEME["accent"], bg=THEME["card_bg"]).pack(side=tk.LEFT)

        self._user_area = tk.Frame(top_bar, bg=THEME["card_bg"], cursor="hand2")
        self._user_area.pack(side=tk.RIGHT, padx=(0, 4))

        self._user_avatar_canvas = tk.Canvas(self._user_area, width=28, height=28,
                                              highlightthickness=0, bg=THEME["accent"], cursor="hand2")
        self._user_avatar_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self._user_avatar_canvas.create_text(14, 14, text="👤",
                                              font=("Microsoft YaHei", 12), fill="white")
        self._user_avatar_canvas.bind("<Button-1>", lambda e: self._show_user_manage_from_topbar())

        self._user_label = tk.Label(self._user_area, text=f"👤 {self._current_username}",
                                     font=("Microsoft YaHei", 10),
                                     bg=THEME["card_bg"], fg=THEME["fg"])
        self._user_label.pack(side=tk.LEFT)
        self._user_area.bind("<Button-1>", lambda e: self._show_user_manage_from_topbar())
        self._user_label.bind("<Button-1>", lambda e: self._show_user_manage_from_topbar())
        self._create_tooltip(self._user_area, "点击管理用户")

        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._tab_home = ttk.Frame(self._notebook)
        self._tab_analysis = ttk.Frame(self._notebook)
        self._tab_data = ttk.Frame(self._notebook)
        self._tab_settings = ttk.Frame(self._notebook)
        self._tab_help = ttk.Frame(self._notebook)

        self._notebook.add(self._tab_home, text="  🏠 首页  ")
        self._notebook.add(self._tab_analysis, text="  🔬 深度分析  ")
        self._notebook.add(self._tab_data, text="  📂 数据管理  ")
        self._notebook.add(self._tab_settings, text="  ⚙️ 设置  ")
        self._notebook.add(self._tab_help, text="  ❓ 帮助  ")

        self._build_home_tab()
        self._build_analysis_tab()
        self._build_data_tab()
        self._build_settings_tab()
        self._build_help_tab()

    def _show_user_manage_from_topbar(self):
        self._show_user_select_dialog()

    def _build_home_tab(self):
        tab = self._tab_home

        stats_header = ttk.Frame(tab)
        stats_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(stats_header, text="  📊 水平统计", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        self._home_stats_panel = tk.Frame(tab, bg=THEME["card_bg"], padx=12, pady=8,
                                           highlightthickness=1, highlightbackground=THEME["border"])
        self._home_stats_panel.pack(fill=tk.X, padx=8, pady=(0, 8))

        self._home_stats_text = tk.Text(self._home_stats_panel, font=("Consolas", 9),
                                         bg=THEME["card_bg"], fg=THEME["fg"],
                                         height=18, wrap=tk.NONE, relief="flat",
                                         cursor="arrow", state="disabled",
                                         selectbackground=THEME["accent"],
                                         selectforeground="white")
        self._home_stats_text.tag_configure("bold", font=("Consolas", 9, "bold"))
        self._home_stats_text.tag_configure("highlight_label", font=("Consolas", 11, "bold"), foreground="#4A90D9")
        self._home_stats_text.tag_configure("highlight_value", font=("Consolas", 13, "bold"), foreground="#2E6FBA")
        self._home_stats_scroll_y = tk.Scrollbar(self._home_stats_panel, command=self._home_stats_text.yview, width=10)
        self._home_stats_scroll_x = tk.Scrollbar(self._home_stats_panel, command=self._home_stats_text.xview,
                                                  orient=tk.HORIZONTAL, width=10)
        self._home_stats_text.config(yscrollcommand=self._home_stats_scroll_y.set,
                                      xscrollcommand=self._home_stats_scroll_x.set)
        self._home_stats_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self._home_stats_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._home_stats_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        train_header = ttk.Frame(tab)
        train_header.pack(fill=tk.X, pady=(0, 2), padx=8)
        ttk.Label(train_header, text="  🎯 智能训练", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        train_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=12, pady=12,
                                highlightthickness=1, highlightbackground=THEME["border"])
        train_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Button(train_frame, text="📊 今日训练总结", command=self._show_daily_report,
                   style="Accent.TButton").pack(side=tk.LEFT)

        self._refresh_home_stats()

    def _refresh_home_stats(self):
        from config import PHASE_ORDER
        avg = memory_db.get_averages()
        text_widget = self._home_stats_text

        if not avg:
            text_widget.config(state="normal")
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", "暂无数据，完成分析后自动记录")
            text_widget.config(state="disabled")
            return

        sep = "─" * 80

        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)

        pb = memory_db.get_pb()
        total_avg = memory_db.get_total_time_avg()
        total_std = memory_db.get_total_time_std()
        total_tps_avg = memory_db.get_total_tps_avg()
        total_tps_std = memory_db.get_total_tps_std()

        if pb:
            text_widget.insert(tk.END, "PB: ", "highlight_label")
            text_widget.insert(tk.END, f"{pb['time']:.2f}s", "highlight_value")
            text_widget.insert(tk.END, f" ({pb['date']})\n")
        if total_avg:
            text_widget.insert(tk.END, "近1000次平均: ", "highlight_label")
            text_widget.insert(tk.END, f"{total_avg:.2f}s", "highlight_value")
            if total_std:
                text_widget.insert(tk.END, "  标准差: ", "highlight_label")
                text_widget.insert(tk.END, f"{total_std:.2f}s", "highlight_value")
            if total_tps_avg:
                text_widget.insert(tk.END, "  TPS: ", "highlight_label")
                text_widget.insert(tk.END, f"{total_tps_avg:.1f}", "highlight_value")
                if total_tps_std:
                    text_widget.insert(tk.END, f"(σ{total_tps_std:.1f})", "highlight_value")
            text_widget.insert(tk.END, "\n")

        if pb or total_avg:
            text_widget.insert(tk.END, sep + "\n")

        text_widget.insert(tk.END, f"阶段\t步数(σ)\t用时(s)(σ)\t观察(s)(σ)\t卡顿\t废步\tTPS(σ)\n")
        text_widget.insert(tk.END, sep + "\n")

        phase_labels = {
            "cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
            "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL",
        }
        for phase in PHASE_ORDER:
            if phase in avg:
                s = avg[phase]
                label = phase_labels.get(phase, phase)
                text_widget.insert(
                    tk.END,
                    f"{label}\t{s['steps']:.1f}({s['steps_std']:.1f})"
                    f"\t{s['time']:.2f}({s['time_std']:.2f})"
                    f"\t{s['observation_time']:.2f}({s['observation_time_std']:.2f})"
                    f"\t{s['stutter_count']:.1f}"
                    f"\t{s['wasted_moves']:.1f}"
                    f"\t{s['tps']:.1f}({s['tps_std']:.1f})\n"
                )

        date_range = memory_db.get_date_range()
        count = memory_db.get_record_count()
        text_widget.insert(tk.END, sep + "\n")
        text_widget.insert(tk.END, f"记录: {count}条 | 时间: {date_range} | 统计: 最近1000次")

        text_widget.config(state="disabled")

    def _build_analysis_tab(self):
        tab = self._tab_analysis

        input_header = ttk.Frame(tab)
        input_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(input_header, text="  输入参数", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        self._create_help_icon(input_header, "input").pack(side=tk.LEFT, padx=(4, 0))

        mode_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=12, pady=8,
                              highlightthickness=1, highlightbackground=THEME["border"])
        mode_frame.pack(fill=tk.X, padx=8, pady=(0, 2))

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

        self.input_container = tk.Frame(tab, bg=THEME["bg"])
        self.input_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._create_single_input_ui()

        button_frame = ttk.Frame(tab)
        button_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.ai_analyze_btn = ttk.Button(button_frame, text="🚀 AI分析", command=self._ai_analyze, style="Accent.TButton")
        self.ai_analyze_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(button_frame, text="⏹ 停止", command=self._stop_analyze, state="disabled", style="Danger.TButton")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.save_btn = ttk.Button(button_frame, text="💾 保存", command=self._save_result, style="Secondary.TButton")
        self.save_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.clear_btn = ttk.Button(button_frame, text="🗑 清空", command=self._clear, style="Secondary.TButton")
        self.clear_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = ttk.Label(button_frame, text="", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.timeline_header = ttk.Frame(tab)
        self.timeline_header.pack(fill=tk.X, padx=8, pady=(0, 2))
        ttk.Label(self.timeline_header, text="  还原步骤时间轴", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        self.timeline_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=8, pady=8,
                                  highlightthickness=1, highlightbackground=THEME["border"])
        self.timeline_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.timeline_canvas = tk.Canvas(self.timeline_frame, height=100, bg=THEME["card_bg"],
                                          highlightthickness=0)
        self.timeline_canvas.pack(fill=tk.X)

        self.result_header = ttk.Frame(tab)
        self.result_header.pack(fill=tk.X, padx=8, pady=(0, 2))
        ttk.Label(self.result_header, text="  分析结果", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        self.ai_status_label = tk.Label(self.result_header, text="", font=("Microsoft YaHei", 10, "bold"),
                                        bg=THEME["bg"], fg=THEME["accent"])
        self.ai_status_label.pack(side=tk.LEFT, padx=(8, 0))

        self.result_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=8, pady=8,
                                highlightthickness=1, highlightbackground=THEME["border"])
        self.result_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.result_text = scrolledtext.ScrolledText(self.result_frame, width=60, height=20, wrap=tk.WORD,
                                                      font=("Microsoft YaHei", 11),
                                                      bg=THEME["card_bg"], fg=THEME["fg"],
                                                      relief="flat", borderwidth=0,
                                                      highlightthickness=0,
                                                      insertbackground=THEME["accent"])
        self.result_text.pack(fill=tk.BOTH, expand=True)
        configure_markdown_tags(self.result_text)

    def _build_data_tab(self):
        tab = self._tab_data

        filter_header = ttk.Frame(tab)
        filter_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(filter_header, text="  📂 数据管理", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        filter_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=12, pady=8,
                                 highlightthickness=1, highlightbackground=THEME["border"])
        filter_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        tk.Label(filter_frame, text="日期:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)

        self._data_date_var = tk.StringVar()
        self._data_date_combo = ttk.Combobox(filter_frame, textvariable=self._data_date_var,
                                              width=14, state="readonly", font=("Microsoft YaHei", 10))
        self._data_date_combo.pack(side=tk.LEFT, padx=(6, 8))
        self._data_date_combo.bind("<<ComboboxSelected>>", self._on_data_date_change)

        ttk.Button(filter_frame, text="📅 今天", command=self._set_data_date_today,
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(filter_frame, text="🔄 刷新", command=self._refresh_data_tab,
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))

        self._data_count_label = ttk.Label(filter_frame, text="", style="Status.TLabel")
        self._data_count_label.pack(side=tk.LEFT, padx=(8, 0))

        btn_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=12, pady=8,
                              highlightthickness=1, highlightbackground=THEME["border"])
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        ttk.Button(btn_frame, text="📂 导入csTimer数据", command=self._import_cstimer,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="📊 导出CSV", command=self._export_memory,
                   style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="🗑 清除数据", command=self._clear_memory,
                   style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 8))

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self._data_analyze_btn = ttk.Button(btn_frame, text="🔬 分析选中项（支持多选）", command=self._data_to_analysis,
                                             style="Accent.TButton")
        self._data_analyze_btn.pack(side=tk.LEFT, padx=(0, 8))

        tree_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=4, pady=4,
                               highlightthickness=1, highlightbackground=THEME["border"])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        columns = ("time", "total_time", "scramble")
        self._data_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                        selectmode="extended", height=20)

        self._data_tree.heading("time", text="还原时间 ▲", command=lambda: self._sort_data_by_column("time"))
        self._data_tree.heading("total_time", text="总用时(s) ▲", command=lambda: self._sort_data_by_column("total_time"))
        self._data_tree.heading("scramble", text="打乱公式")

        self._data_tree.column("time", width=160, anchor="center")
        self._data_tree.column("total_time", width=90, anchor="center")
        self._data_tree.column("scramble", width=500, anchor="w")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._data_tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._data_tree.xview)
        self._data_tree.configure(yscrollcommand=tree_scroll_y.set,
                                   xscrollcommand=tree_scroll_x.set)

        self._data_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._data_tree.bind("<Double-1>", self._on_data_row_double_click)
        self._data_tree.bind("<Button-3>", self._on_data_right_click)

        self._data_context_menu = tk.Menu(self.root, tearoff=0)
        self._data_context_menu.add_command(label="🗑 删除选中记录", command=self._delete_selected_records)

        self._data_records = []
        self._data_sort_column = "time"
        self._data_sort_ascending = True

        self._refresh_data_tab()

    def _refresh_data_tab(self):
        dates = memory_db.get_available_dates()
        today = datetime.now().strftime("%Y-%m-%d")
        self._data_date_combo['values'] = dates
        if dates:
            if today in dates:
                self._data_date_var.set(today)
            else:
                self._data_date_var.set(dates[0])
        else:
            self._data_date_var.set("")
        self._load_data_records()

    def _set_data_date_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        dates = list(self._data_date_combo['values'])
        if today not in dates:
            dates.insert(0, today)
            self._data_date_combo['values'] = dates
        self._data_date_var.set(today)
        self._load_data_records()

    def _on_data_date_change(self, event=None):
        self._load_data_records()

    def _load_data_records(self):
        date_str = self._data_date_var.get()
        records = memory_db.get_records_by_date(date_str if date_str else None)

        if self._data_sort_column == "total_time":
            records.sort(key=lambda r: r["total_time"], reverse=not self._data_sort_ascending)
        else:
            records.sort(key=lambda r: r["date"], reverse=not self._data_sort_ascending)

        self._data_records = records

        for item in self._data_tree.get_children():
            self._data_tree.delete(item)

        for rec in records:
            time_str = rec["date"][11:] if len(rec["date"]) > 10 else rec["date"]
            self._data_tree.insert("", tk.END, iid=str(rec["id"]),
                                    values=(time_str, f"{rec['total_time']:.2f}", rec["scramble"]))

        count = len(records)
        self._data_count_label.config(text=f"共 {count} 条记录")

        self._update_memory_count()

    def _sort_data_by_column(self, col: str):
        if self._data_sort_column == col:
            self._data_sort_ascending = not self._data_sort_ascending
        else:
            self._data_sort_column = col
            self._data_sort_ascending = True

        arrow = "▲" if self._data_sort_ascending else "▼"
        if col == "time":
            self._data_tree.heading("time", text=f"还原时间 {arrow}", command=lambda: self._sort_data_by_column("time"))
            self._data_tree.heading("total_time", text="总用时(s)", command=lambda: self._sort_data_by_column("total_time"))
        else:
            self._data_tree.heading("time", text="还原时间", command=lambda: self._sort_data_by_column("time"))
            self._data_tree.heading("total_time", text=f"总用时(s) {arrow}", command=lambda: self._sort_data_by_column("total_time"))

        self._load_data_records()

    def _on_data_row_double_click(self, event=None):
        selection = self._data_tree.selection()
        if not selection:
            return
        record_id = int(selection[0])
        self._show_record_detail(record_id)

    def _on_data_right_click(self, event):
        item = self._data_tree.identify_row(event.y)
        if item:
            if item not in self._data_tree.selection():
                self._data_tree.selection_set(item)
            try:
                self._data_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._data_context_menu.grab_release()

    def _delete_selected_records(self):
        selection = self._data_tree.selection()
        if not selection:
            return

        count = len(selection)
        if not messagebox.askyesno("确认删除",
                                    f"确定删除选中的 {count} 条记录？\n\n⚠ 此操作不可恢复！"):
            return

        record_ids = [int(item_id) for item_id in selection]
        deleted = memory_db.delete_records(record_ids)

        self._refresh_data_tab()
        self._refresh_home_stats()

        if deleted > 0:
            self._set_status(f"已删除 {deleted} 条记录")
            self.root.after(2000, self._clear_status)

    def _show_record_detail(self, record_id: int):
        detail = memory_db.get_record_detail(record_id)
        if not detail:
            messagebox.showwarning("提示", "未找到记录详情")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("还原详情")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)

        dialog_width = 700
        dialog_height = 550
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog_width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=16, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        info_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        info_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(info_frame, text=f"📅 {detail['date']}", font=("Microsoft YaHei", 10),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(info_frame, text=f"⏱ 总用时: {detail['total_time']:.2f}s", font=("Microsoft YaHei", 10, "bold"),
                 bg=THEME["card_bg"], fg=THEME["accent"]).pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(info_frame, text=f"🎨 底色: {detail['bottom_color']}", font=("Microsoft YaHei", 10),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT)

        scramble_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        scramble_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(scramble_frame, text="打乱公式:", font=("Microsoft YaHei", 9, "bold"),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w")
        tk.Label(scramble_frame, text=detail["scramble"], font=("Consolas", 9),
                 bg=THEME["card_bg"], fg=THEME["fg"], wraplength=650, justify="left").pack(anchor="w", padx=(12, 0))

        solution_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        solution_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(solution_frame, text="还原步骤:", font=("Microsoft YaHei", 9, "bold"),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w")
        sol_text = tk.Text(solution_frame, font=("Consolas", 9), height=3, wrap=tk.WORD,
                           bg=THEME["input_bg"], fg=THEME["fg"], relief="flat", borderwidth=0)
        sol_text.insert("1.0", detail["solution"])
        sol_text.config(state="disabled")
        sol_text.pack(fill=tk.X, padx=(12, 0))

        phase_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        phase_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        tk.Label(phase_frame, text="各阶段详情:", font=("Microsoft YaHei", 9, "bold"),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w")

        phase_tree_frame = tk.Frame(phase_frame, bg=THEME["card_bg"])
        phase_tree_frame.pack(fill=tk.BOTH, expand=True, padx=(12, 0))

        phase_columns = ("phase", "steps", "time", "obs_time", "stutter", "wasted", "tps")
        phase_tree = ttk.Treeview(phase_tree_frame, columns=phase_columns, show="headings", height=7)

        phase_tree.heading("phase", text="阶段")
        phase_tree.heading("steps", text="步数")
        phase_tree.heading("time", text="用时(s)")
        phase_tree.heading("obs_time", text="观察(s)")
        phase_tree.heading("stutter", text="卡顿")
        phase_tree.heading("wasted", text="废步")
        phase_tree.heading("tps", text="TPS")

        phase_tree.column("phase", width=70, anchor="center")
        phase_tree.column("steps", width=60, anchor="center")
        phase_tree.column("time", width=80, anchor="center")
        phase_tree.column("obs_time", width=80, anchor="center")
        phase_tree.column("stutter", width=60, anchor="center")
        phase_tree.column("wasted", width=60, anchor="center")
        phase_tree.column("tps", width=60, anchor="center")

        phase_labels = {"cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
                        "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL"}
        phase_order = ["cross", "f2l1", "f2l2", "f2l3", "f2l4", "oll", "pll"]

        has_phases = any(detail["phase_stats"].get(pk) for pk in phase_order)
        if not has_phases:
            tk.Label(phase_tree_frame, text="⚠ 无阶段数据，该记录可能未完成还原或数据异常",
                     font=("Microsoft YaHei", 9), bg=THEME["card_bg"], fg="#e17055").pack(anchor="w", pady=8)

        for phase_key in phase_order:
            ps = detail["phase_stats"].get(phase_key, {})
            if ps:
                phase_tree.insert("", tk.END, values=(
                    phase_labels.get(phase_key, phase_key),
                    ps.get("steps", 0),
                    f"{ps.get('time', 0):.2f}",
                    f"{ps.get('observation_time', 0):.2f}",
                    ps.get("stutter_count", 0),
                    ps.get("wasted_moves", 0),
                    f"{ps.get('tps', 0):.1f}"
                ))

        present_phases = [pk for pk in phase_order if detail["phase_stats"].get(pk)]
        if has_phases and len(present_phases) < len(phase_order):
            missing = [phase_labels[pk] for pk in phase_order if not detail["phase_stats"].get(pk)]
            tk.Label(phase_tree_frame, text=f"⚠ 缺少阶段: {', '.join(missing)}",
                     font=("Microsoft YaHei", 9), bg=THEME["card_bg"], fg="#e17055").pack(anchor="w", pady=(4, 0))

        phase_tree.pack(fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_frame, text="关闭", command=dialog.destroy,
                   style="Secondary.TButton").pack(side=tk.RIGHT)

    def _data_to_analysis(self):
        selection = self._data_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要分析的还原数据")
            return

        selected_records = []
        for item_id in selection:
            record_id = int(item_id)
            detail = memory_db.get_record_detail(record_id)
            if detail:
                selected_records.append(detail)

        if not selected_records:
            messagebox.showwarning("提示", "未找到选中记录的详情")
            return

        if len(selected_records) == 1:
            self._fill_single_analysis(selected_records[0])
        else:
            self._fill_multi_analysis(selected_records)

        self._notebook.select(self._tab_analysis)

    def _fill_single_analysis(self, record: dict):
        if self.analysis_mode_var.get() != '单组':
            self.analysis_mode_var.set('单组')
            self._on_mode_change()

        self.scramble_entry.delete(0, tk.END)
        self.scramble_entry.insert(0, record["scramble"])

        self.solution_text.delete(0, tk.END)
        self.solution_text.insert(0, record["solution"])

        bottom_color = record.get("bottom_color", "白")
        bottom_name = self._get_bottom_name_from_color(bottom_color)
        if bottom_name:
            self.orientation_var.set(bottom_name)

    def _fill_multi_analysis(self, records: list):
        if self.analysis_mode_var.get() != '多组':
            self.analysis_mode_var.set('多组')
            self._on_mode_change()
        else:
            if hasattr(self, 'multi_inputs') and self.multi_inputs:
                for inp in self.multi_inputs:
                    for key in ('num_label', 'scramble', 'orientation_combo', 'solution', 'del_btn'):
                        if key in inp:
                            inp[key].destroy()
                self.multi_inputs.clear()

        for rec in records:
            if len(self.multi_inputs) >= 20:
                break
            self._add_multi_row()
            inp = self.multi_inputs[-1]
            inp['scramble'].delete(0, tk.END)
            inp['scramble'].insert(0, rec["scramble"])
            inp['solution'].delete(0, tk.END)
            inp['solution'].insert(0, rec["solution"])

            bottom_color = rec.get("bottom_color", "白")
            bottom_name = self._get_bottom_name_from_color(bottom_color)
            if bottom_name:
                inp['orientation_var'].set(bottom_name)

        self._update_multi_row_numbers()
        self._update_multi_count()
        self._reindex_multi_grid()

    def _get_bottom_name_from_color(self, color: str) -> str:
        bottom_data = next((opt for opt in BOTTOM_COLOR_OPTIONS if opt[1] == color), None)
        return bottom_data[0] if bottom_data else BOTTOM_COLOR_NAMES[0]

    def _build_settings_tab(self):
        tab = self._tab_settings

        header = ttk.Frame(tab)
        header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(header, text="  🔑 大模型设置", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        ai_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=16, pady=16,
                            highlightthickness=1, highlightbackground=THEME["border"])
        ai_frame.pack(fill=tk.X, padx=8, pady=(0, 12))

        tk.Label(ai_frame, text="API Key:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky=tk.W, pady=8)
        self.api_key_entry = ttk.Entry(ai_frame, width=45, show="●", font=("Consolas", 10))
        self.api_key_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=(12, 0))

        tk.Label(ai_frame, text="模型:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky=tk.W, pady=8)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(ai_frame, textvariable=self.model_var, width=40, state="readonly")
        self.model_combo.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=(12, 0))

        self.refresh_btn = ttk.Button(ai_frame, text="🔄 刷新模型列表", command=self._refresh_models, style="Accent.TButton")
        self.refresh_btn.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        ai_frame.columnconfigure(1, weight=1)

        feature_header = ttk.Frame(tab)
        feature_header.pack(fill=tk.X, pady=(0, 2), padx=8)
        ttk.Label(feature_header, text="  🛠 功能设置", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        feature_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=16, pady=16,
                                  highlightthickness=1, highlightbackground=THEME["border"])
        feature_frame.pack(fill=tk.X, padx=8, pady=(0, 12))

        smart_paste_frame = tk.Frame(feature_frame, bg=THEME["card_bg"])
        smart_paste_frame.pack(fill=tk.X, pady=(0, 12))
        self._settings_smart_paste_cb = tk.Checkbutton(smart_paste_frame, text="📋 智能粘贴",
                                                        variable=self._smart_paste_var,
                                                        command=self._on_smart_paste_toggle,
                                                        bg=THEME["card_bg"], fg=THEME["fg"],
                                                        selectcolor=THEME["card_bg"],
                                                        activebackground=THEME["card_bg"],
                                                        activeforeground=THEME["accent"],
                                                        font=("Microsoft YaHei", 10))
        self._settings_smart_paste_cb.pack(side=tk.LEFT)
        self._create_help_icon(smart_paste_frame, "smart_paste").pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(smart_paste_frame, text="自动从剪贴板识别csTimer数据",
                 bg=THEME["card_bg"], fg="#888",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=(16, 0))

        memory_frame = tk.Frame(feature_frame, bg=THEME["card_bg"])
        memory_frame.pack(fill=tk.X)
        self._settings_memory_cb = tk.Checkbutton(memory_frame, text="🧠 记忆模式",
                                                    variable=self._use_memory_var,
                                                    bg=THEME["card_bg"], fg=THEME["fg"],
                                                    selectcolor=THEME["card_bg"],
                                                    activebackground=THEME["card_bg"],
                                                    activeforeground=THEME["accent"],
                                                    font=("Microsoft YaHei", 10))
        self._settings_memory_cb.pack(side=tk.LEFT)
        self._create_help_icon(memory_frame, "memory").pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(memory_frame, text="记录分析历史，提供对比参考和训练建议",
                 bg=THEME["card_bg"], fg="#888",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=(16, 0))

    def _build_help_tab(self):
        tab = self._tab_help

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
• 生成训练建议

【交流反馈】
• 交流QQ群：322267527"""

        main_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=24, pady=20,
                               highlightthickness=1, highlightbackground=THEME["border"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        title_label = tk.Label(main_frame, text="AI_CFOP 使用说明",
                              font=("Microsoft YaHei", 16, "bold"),
                              fg=THEME["accent"], bg=THEME["card_bg"])
        title_label.pack(pady=(0, 16))

        text_widget = scrolledtext.ScrolledText(main_frame, width=60, height=25,
                                                font=("Microsoft YaHei", 10),
                                                bg=THEME["card_bg"],
                                                fg=THEME["fg"],
                                                relief="flat", borderwidth=0,
                                                wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert("1.0", guide_text)
        text_widget.config(state="disabled")
    
    def _create_single_input_ui(self):
        for widget in self.input_container.winfo_children():
            widget.destroy()
        
        self.multi_inputs = None
        
        input_frame = tk.Frame(self.input_container, bg=THEME["card_bg"], padx=10, pady=6,
                               highlightthickness=1, highlightbackground=THEME["border"])
        input_frame.pack(fill=tk.X)
        
        tk.Label(input_frame, text="打乱公式:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.scramble_entry = tk.Entry(input_frame, width=60, font=("Consolas", 9),
                                        bg=THEME["input_bg"], fg=THEME["fg"],
                                        relief="flat", borderwidth=0,
                                        highlightthickness=1, highlightbackground=THEME["border"],
                                        highlightcolor=THEME["accent"])
        self.scramble_entry.grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(6, 0))
        
        tk.Label(input_frame, text="底色:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
        
        self.orientation_var = tk.StringVar(value=BOTTOM_COLOR_NAMES[0])
        self.orientation_combo = ttk.Combobox(input_frame, textvariable=self.orientation_var,
                                               width=12, state="readonly", font=("Microsoft YaHei", 9),
                                               height=1)
        self.orientation_combo['values'] = BOTTOM_COLOR_NAMES
        self.orientation_combo.grid(row=1, column=1, sticky=tk.W, pady=2, padx=(6, 0))
        self.orientation_combo.bind("<MouseWheel>", lambda e: "break")
        
        tk.Label(input_frame, text="还原步骤 (回顾):", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.solution_text = tk.Entry(input_frame, width=60,
                                       font=("Consolas", 9), bg=THEME["input_bg"],
                                       fg=THEME["fg"], relief="flat", borderwidth=0,
                                       highlightthickness=1, highlightbackground=THEME["border"],
                                       highlightcolor=THEME["accent"])
        self.solution_text.grid(row=2, column=1, sticky=tk.EW, pady=2, padx=(6, 0))
        
        input_frame.columnconfigure(1, weight=1)
        
        self.mode_desc_label.config(text="单组模式：分析单次还原过程")
    
    def _create_multi_input_ui(self):
        for widget in self.input_container.winfo_children():
            widget.destroy()
        
        self.multi_inputs = []
        
        outer_frame = tk.Frame(self.input_container, bg=THEME["card_bg"], padx=8, pady=4,
                               highlightthickness=1, highlightbackground=THEME["border"])
        outer_frame.pack(fill=tk.BOTH, expand=True)
        
        rows_container = tk.Frame(outer_frame, bg=THEME["card_bg"])
        rows_container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(rows_container, bg=THEME["card_bg"], highlightthickness=0, height=200)
        scrollbar = ttk.Scrollbar(rows_container, orient="vertical", command=canvas.yview)
        self.multi_rows_frame = tk.Frame(canvas, bg=THEME["card_bg"])
        
        self.multi_rows_frame.columnconfigure(1, weight=0)
        self.multi_rows_frame.columnconfigure(2, weight=0)
        self.multi_rows_frame.columnconfigure(3, weight=1)
        
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
        
        tk.Label(self.multi_rows_frame, text="#", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 8, "bold"), width=3, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(self.multi_rows_frame, text="打乱公式", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 8, "bold"), anchor="w").grid(row=0, column=1, sticky="w", padx=(2, 0))
        tk.Label(self.multi_rows_frame, text="底色", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 8, "bold"), anchor="w").grid(row=0, column=2, sticky="w", padx=(2, 0))
        tk.Label(self.multi_rows_frame, text="还原步骤", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 8, "bold"), anchor="w").grid(row=0, column=3, sticky="ew", padx=(2, 0))
        tk.Label(self.multi_rows_frame, text="", bg=THEME["card_bg"],
                 font=("Microsoft YaHei", 8), width=2).grid(row=0, column=4, padx=(1, 0))
        
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
        
        num_label = tk.Label(self.multi_rows_frame, text=f"{idx+1}", bg=THEME["card_bg"], fg=THEME["accent"],
                             font=("Microsoft YaHei", 8, "bold"), width=3, anchor="w")
        num_label.grid(row=idx + 1, column=0, sticky="w")
        
        scramble_entry = tk.Entry(self.multi_rows_frame, font=("Consolas", 8), width=40,
                                  bg=THEME["input_bg"], fg=THEME["fg"],
                                  relief="flat", borderwidth=0,
                                  highlightthickness=1, highlightbackground=THEME["border"],
                                  highlightcolor=THEME["accent"])
        scramble_entry.grid(row=idx + 1, column=1, sticky="w", padx=(2, 0))
        
        orientation_var = tk.StringVar(value=BOTTOM_COLOR_NAMES[0])
        orientation_combo = ttk.Combobox(self.multi_rows_frame, textvariable=orientation_var,
                                          width=8, state="readonly", font=("Microsoft YaHei", 8),
                                          height=1)
        orientation_combo['values'] = BOTTOM_COLOR_NAMES
        orientation_combo.grid(row=idx + 1, column=2, sticky="w", padx=(2, 0))
        orientation_combo.bind("<MouseWheel>", lambda e: "break")
        
        solution_entry = tk.Entry(self.multi_rows_frame, font=("Consolas", 8),
                                  bg=THEME["input_bg"], fg=THEME["fg"],
                                  relief="flat", borderwidth=0,
                                  highlightthickness=1, highlightbackground=THEME["border"],
                                  highlightcolor=THEME["accent"])
        solution_entry.grid(row=idx + 1, column=3, sticky="ew", padx=(2, 0))
        
        inp = {
            'num_label': num_label,
            'scramble': scramble_entry,
            'orientation_var': orientation_var,
            'orientation_combo': orientation_combo,
            'solution': solution_entry
        }
        
        del_btn = tk.Button(self.multi_rows_frame, text="✕", width=2,
                            font=("Microsoft YaHei", 7), fg="#fff", bg=THEME["danger"],
                            activebackground="#d63031", activeforeground="#fff",
                            relief="flat", borderwidth=0, cursor="hand2",
                            command=lambda: self._remove_multi_row_by_inp(inp))
        del_btn.grid(row=idx + 1, column=4, padx=(2, 0))
        inp['del_btn'] = del_btn
        
        if hasattr(self, 'multi_mousewheel_func'):
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
            for key in ('num_label', 'scramble', 'orientation_combo', 'solution', 'del_btn'):
                if key in inp:
                    inp[key].destroy()
            self.multi_inputs.remove(inp)
            self._update_multi_row_numbers()
            self._update_multi_count()
            self._reindex_multi_grid()
    
    def _update_multi_row_numbers(self):
        for i, inp in enumerate(self.multi_inputs):
            inp['num_label'].config(text=f"{i+1}")
    
    def _reindex_multi_grid(self):
        for i, inp in enumerate(self.multi_inputs):
            inp['num_label'].grid(row=i + 1, column=0, sticky="w")
            inp['scramble'].grid(row=i + 1, column=1, sticky="w", padx=(2, 0))
            inp['orientation_combo'].grid(row=i + 1, column=2, sticky="w", padx=(2, 0))
            inp['solution'].grid(row=i + 1, column=3, sticky="ew", padx=(2, 0))
            inp['del_btn'].grid(row=i + 1, column=4, padx=(2, 0))
    
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
            config["solution"] = self.solution_text.get().strip()
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
                self.solution_text.insert(0, config["solution"])
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
            decrypted = _xor_decode(config["api_key"])
            self.api_key_entry.insert(0, decrypted if decrypted else config["api_key"])
        if config.get("model"):
            self.model_var.set(config["model"])
        if config.get("models"):
            self.model_combo["values"] = config["models"]

        if "smart_paste" in config and not config["smart_paste"]:
            self._smart_paste_var.set(False)
        
        if "use_memory" in config and not config["use_memory"]:
            self._use_memory_var.set(False)
        
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
            config["api_key"] = _xor_encode(self.api_key_entry.get().strip())
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
        try:
            config["smart_paste"] = self._smart_paste_var.get()
        except Exception:
            pass
        try:
            config["use_memory"] = self._use_memory_var.get()
        except Exception:
            pass
        save_config(config)
    
    def _on_close(self):
        log.info("关闭程序")
        self._save_current_config()
        self._clear_status()
        self._stream_stop = True
        self._stop_clipboard_monitor()
        self.root.destroy()
    
    def _clear(self):
        log.info("清空输入")
        mode = self.analysis_mode_var.get()
        
        if mode == '单组':
            self.scramble_entry.delete(0, tk.END)
            self.solution_text.delete(0, tk.END)
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
        username = self._current_username or "unknown"
        
        if mode == '单组' and self._last_analyzer:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                scramble = self.scramble_entry.get().strip().replace(" ", "")
                total_time = self._last_analyzer.get_total_time()
                default_name = f"{username}_{date_str}_{scramble}_{total_time:.1f}s"
            except Exception:
                pass
        elif mode == '多组' and hasattr(self, 'multi_inputs') and self.multi_inputs:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            count = len(self.multi_inputs)
            default_name = f"{username}_{date_str}_多组{count}组"
        
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
        solution = self.solution_text.get().strip()
        api_key = self.api_key_entry.get().strip()
        model = self.model_var.get()
        
        bottom_name = self.orientation_var.get()
        bottom_color = self._get_bottom_color_from_name(bottom_name)
        
        if not bottom_color:
            self._reset_analysis_ui()
            messagebox.showwarning("错误", "请选择有效的底色")
            return
        
        if not scramble or not solution:
            self._reset_analysis_ui()
            messagebox.showwarning("警告", "请先输入打乱公式和还原步骤！")
            return
        if not api_key:
            self._reset_analysis_ui()
            messagebox.showwarning("警告", "请输入API Key！")
            return
        if not model:
            self._reset_analysis_ui()
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

            total_time = analyzer.get_total_time()
            if not self._check_anomaly_and_confirm(total_time, '单组'):
                self._reset_analysis_ui()
                return
            
            memory_text = self._build_memory_text() if self._use_memory_var.get() else ""
            comparison_text = self._build_comparison_text(analyzer) if self._use_memory_var.get() else ""
            system_prompt, user_prompt = analyzer.build_ai_prompt(memory_text + comparison_text)
            
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
        scramble = self.scramble_entry.get().strip()
        self._solution_summary = (
            f"【解法复盘】\n\n"
            f"【打乱】:{scramble}\n"
            f"【底色】:{bottom_name} | 【自动朝向】:{get_orientation_desc(analyzer.top_color, analyzer.front_color)}\n"
            + analyzer.format_output()
        )
        self._count_consumed = False
        self.ai_analyze_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "🤔 AI思考中...\n", "italic")
        
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
            if self._solution_summary:
                self.result_text.insert(tk.END, self._solution_summary, "normal")
                self.result_text.insert(tk.END, "\n\n", "normal")
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
        self._save_to_memory()
    
    def _build_memory_text(self) -> str:
        from config import PHASE_ORDER
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
        
        return "\n".join(lines) + "\n"

    def _build_comparison_text(self, analyzer) -> str:
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
        stats = analyzer.get_phase_stats()
        
        lines = [f"【本次与历史对比】（基准：{baseline_period}平均）"]
        
        cur = stats["cross"]
        hist = baseline.get("cross", {})
        if hist:
            ds = cur["steps"] - hist["steps"]
            dt = cur["time"] - hist["time"]
            dtps = cur["tps"] - hist["tps"]
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            lines.append(f"Cross: 本次 {cur['steps']}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} {tag}")
        
        f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
        cur_f2l = [stats[p] for p in f2l_phases if stats[p]["steps"] > 0]
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
            lines.append(f"F2L均: 本次 {cs:.0f}步{ct:.1f}s(TPS{ctps:.1f} 观察{cobs:.1f}s) vs 历史 {hs:.0f}步{ht:.1f}s(TPS{htps:.1f} 观察{hobs:.1f}s) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} 观察{dobs:+.1f}s {tag}")
        
        for phase_key, phase_label in [("oll", "OLL"), ("pll", "PLL")]:
            cur = stats[phase_key]
            hist = baseline.get(phase_key, {})
            if hist:
                ds = cur["steps"] - hist["steps"]
                dt = cur["time"] - hist["time"]
                dtps = cur["tps"] - hist["tps"]
                tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
                obs_cur = cur.get("observation_time")
                obs_hist = hist.get("observation_time")
                obs_info = ""
                if obs_cur is not None and obs_hist is not None:
                    dobs = obs_cur - obs_hist
                    obs_info = f" 观察{dobs:+.1f}s"
                lines.append(f"{phase_label}:   本次 {cur['steps']}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f}{obs_info} {tag}")
        
        total_avg = memory_db.get_total_time_avg()
        if total_avg:
            cur_total = analyzer.get_total_time()
            diff = cur_total - total_avg
            tag = "进步" if diff < 0 else ("退步" if diff > 0 else "持平")
            lines.append(f"总用时: 本次 {cur_total:.1f}s vs 历史 {total_avg:.1f}s → {diff:+.1f}s {tag}")
        
        return "\n".join(lines) + "\n"

    def _build_multi_comparison_text(self, analyzers) -> str:
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
        
        phases = ["cross", "f2l1", "f2l2", "f2l3", "f2l4", "oll", "pll"]
        avg_stats = {}
        for phase in phases:
            valid = [a.get_phase_stats()[phase] for a in analyzers if a.get_phase_stats()[phase]["steps"] > 0]
            if valid:
                avg_stats[phase] = {
                    "steps": sum(s["steps"] for s in valid) / len(valid),
                    "time": sum(s["time"] for s in valid) / len(valid),
                    "tps": sum(s["tps"] for s in valid) / len(valid),
                    "observation_time": sum(s.get("observation_time", 0) for s in valid) / len(valid) if phase != "cross" else None,
                }
        
        lines = [f"【多组平均与历史对比】（基准：{baseline_period}平均）"]
        
        cur = avg_stats.get("cross", {})
        hist = baseline.get("cross", {})
        if cur and hist:
            ds = cur["steps"] - hist["steps"]
            dt = cur["time"] - hist["time"]
            dtps = cur["tps"] - hist["tps"]
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            lines.append(f"Cross: 本次均 {cur['steps']:.0f}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} {tag}")
        
        f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
        cur_f2l = [avg_stats.get(p, {}) for p in f2l_phases]
        cur_f2l_valid = [d for d in cur_f2l if d]
        hist_f2l = [baseline.get(p, {}) for p in f2l_phases]
        hist_f2l_valid = [d for d in hist_f2l if d]
        if cur_f2l_valid and hist_f2l_valid:
            cs = sum(d["steps"] for d in cur_f2l_valid) / len(cur_f2l_valid)
            ct = sum(d["time"] for d in cur_f2l_valid) / len(cur_f2l_valid)
            ctps = sum(d["tps"] for d in cur_f2l_valid) / len(cur_f2l_valid)
            cobs = sum(d["observation_time"] for d in cur_f2l_valid) / len(cur_f2l_valid)
            hs = sum(d["steps"] for d in hist_f2l_valid) / len(hist_f2l_valid)
            ht = sum(d["time"] for d in hist_f2l_valid) / len(hist_f2l_valid)
            htps = sum(d["tps"] for d in hist_f2l_valid) / len(hist_f2l_valid)
            hobs = sum(d["observation_time"] for d in hist_f2l_valid) / len(hist_f2l_valid)
            ds = cs - hs
            dt = ct - ht
            dtps = ctps - htps
            dobs = cobs - hobs
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            lines.append(f"F2L均: 本次均 {cs:.0f}步{ct:.1f}s(TPS{ctps:.1f} 观察{cobs:.1f}s) vs 历史 {hs:.0f}步{ht:.1f}s(TPS{htps:.1f} 观察{hobs:.1f}s) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} 观察{dobs:+.1f}s {tag}")
        
        for phase_key, phase_label in [("oll", "OLL"), ("pll", "PLL")]:
            cur = avg_stats.get(phase_key, {})
            hist = baseline.get(phase_key, {})
            if cur and hist:
                ds = cur["steps"] - hist["steps"]
                dt = cur["time"] - hist["time"]
                dtps = cur["tps"] - hist["tps"]
                tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
                obs_info = ""
                if cur.get("observation_time") is not None and hist.get("observation_time") is not None:
                    dobs = cur["observation_time"] - hist["observation_time"]
                    obs_info = f" 观察{dobs:+.1f}s"
                lines.append(f"{phase_label}:   本次均 {cur['steps']:.0f}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f}{obs_info} {tag}")
        
        total_avg = memory_db.get_total_time_avg()
        if total_avg:
            cur_total = sum(a.get_total_time() for a in analyzers) / len(analyzers)
            diff = cur_total - total_avg
            tag = "进步" if diff < 0 else ("退步" if diff > 0 else "持平")
            lines.append(f"总用时: 本次均 {cur_total:.1f}s vs 历史 {total_avg:.1f}s → {diff:+.1f}s {tag}")
        
        return "\n".join(lines) + "\n"

    def _save_to_memory(self):
        if not self._use_memory_var.get():
            return
        mode = self.analysis_mode_var.get()
        try:
            if mode == '单组':
                if not hasattr(self, '_last_analyzer') or not self._last_analyzer:
                    return
                analyzer = self._last_analyzer
                stats = analyzer.get_phase_stats()
                scramble_text = self.scramble_entry.get().strip() if hasattr(self, 'scramble_entry') else ""
                solution_text = self.solution_text.get().strip() if hasattr(self, 'solution_text') else ""
                total_time = analyzer.get_total_time()
                bottom_name = self.orientation_var.get() if hasattr(self, 'orientation_var') else ""
                memory_db.save_record(scramble_text, solution_text, total_time, bottom_name, stats)
            else:
                if not hasattr(self, '_last_multi_data') or not self._last_multi_data:
                    return
                for g, analyzer in self._last_multi_data:
                    stats = analyzer.get_phase_stats()
                    total_time = analyzer.get_total_time()
                    memory_db.save_record(g['scramble'], g['solution'], total_time, g['bottom_name'], stats)
            self._update_memory_count()
            if hasattr(self, '_refresh_home_stats'):
                self._refresh_home_stats()
            if hasattr(self, '_refresh_data_tab'):
                self._refresh_data_tab()
        except Exception as e:
            log.error(f"保存记忆数据失败: {e}")

    def _on_ai_error(self, error_msg: str):
        log.error(f"AI分析失败: {error_msg}")
        self.ai_analyze_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._stop_ai_status_animation()
        self._clear_status()
        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, f"分析失败: {error_msg}")

    def _show_daily_report(self):
        import daily_report

        stats = daily_report.get_today_stats()
        if not stats:
            messagebox.showinfo("今日总结", "今日暂无练习数据。")
            return

        win = tk.Toplevel(self.root)
        win.title(f"今日练习总结 ({stats['date']})")
        win.geometry("720x820")
        win.configure(bg=THEME["bg"])
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()

        main_frame = tk.Frame(win, bg=THEME["bg"], padx=16, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        btn_frame = tk.Frame(main_frame, bg=THEME["bg"])
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        chart_frame = tk.Frame(main_frame, bg=THEME["card_bg"],
                               highlightthickness=1, highlightbackground=THEME["border"])
        chart_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 8))

        text_frame = tk.Frame(main_frame, bg=THEME["card_bg"],
                              highlightthickness=1, highlightbackground=THEME["border"])
        text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 8))

        report_text = tk.Text(text_frame, font=("Microsoft YaHei", 10),
                              bg=THEME["card_bg"], fg=THEME["fg"],
                              wrap=tk.WORD, relief="flat", padx=12, pady=10,
                              cursor="arrow", state="disabled")
        report_text.tag_configure("bold", font=("Microsoft YaHei", 10, "bold"))
        report_text.tag_configure("heading", font=("Microsoft YaHei", 14, "bold"),
                                  foreground=THEME["accent"])
        report_text.tag_configure("section", font=("Microsoft YaHei", 11, "bold"),
                                  foreground=THEME["accent"])
        report_text.tag_configure("ai_summary", font=("Microsoft YaHei", 10),
                                  foreground="#2d3436", background="#f0eef8",
                                  lmargin1=10, lmargin2=10, spacing1=6, spacing3=6)
        report_text.tag_configure("italic", font=("Microsoft YaHei", 10, "italic"),
                                  foreground="#636e72")
        report_text.tag_configure("thinking", font=("Microsoft YaHei", 9),
                                  foreground="#b2bec3", lmargin1=20, lmargin2=20)
        report_text.tag_configure("step_status", font=("Microsoft YaHei", 11, "bold"),
                                  foreground=THEME["accent"])
        scroll = tk.Scrollbar(text_frame, command=report_text.yview, width=10)
        report_text.config(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        report_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        stats_text = daily_report.build_stats_text(stats)
        report_text.config(state="normal")
        for line in stats_text.split("\n"):
            if line.startswith("📅"):
                report_text.insert(tk.END, line + "\n", "heading")
            elif line.startswith("各阶段") or line.startswith("12次") or line.startswith("Ao12"):
                report_text.insert(tk.END, line + "\n", "section")
            elif line.startswith("🏆") or line.startswith("📉"):
                report_text.insert(tk.END, line + "\n", "bold")
            else:
                report_text.insert(tk.END, line + "\n", "normal")
        report_text.config(state="disabled")

        try:
            line_path, hist_path = daily_report.generate_charts(stats["times"])
            chart_inner = tk.Frame(chart_frame, bg=THEME["card_bg"])
            chart_inner.pack(fill=tk.X, padx=8, pady=8)

            if os.path.isfile(line_path):
                from PIL import Image as PILImage, ImageTk
                img = PILImage.open(line_path)
                img.thumbnail((330, 165), PILImage.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl1 = tk.Label(chart_inner, image=photo, bg=THEME["card_bg"])
                lbl1.image = photo
                lbl1.pack(side=tk.LEFT, padx=(0, 4))

            if os.path.isfile(hist_path):
                from PIL import Image as PILImage, ImageTk
                img2 = PILImage.open(hist_path)
                img2.thumbnail((330, 165), PILImage.LANCZOS)
                photo2 = ImageTk.PhotoImage(img2)
                lbl2 = tk.Label(chart_inner, image=photo2, bg=THEME["card_bg"])
                lbl2.image = photo2
                lbl2.pack(side=tk.LEFT, padx=(4, 0))
        except Exception as e:
            log.warning(f"图表生成失败: {e}")
            err_lbl = tk.Label(chart_frame, text=f"图表生成失败: {e}",
                               bg=THEME["card_bg"], fg="#888",
                               font=("Microsoft YaHei", 9))
            err_lbl.pack(pady=8)

        ai_summary_holder = {"text": ""}
        ao12_analysis_holder = {"best": "", "worst": ""}

        def do_ai_summary():
            api_key = self.api_key_entry.get().strip()
            model = self.model_var.get()
            if not api_key or not model:
                messagebox.showwarning("警告", "请先输入API Key并选择模型！", parent=win)
                return

            confirm_win = tk.Toplevel(win)
            confirm_win.title("AI总结")
            confirm_win.geometry("320x200")
            confirm_win.configure(bg=THEME["bg"])
            confirm_win.resizable(False, False)
            confirm_win.transient(win)
            confirm_win.grab_set()

            tk.Label(confirm_win, text=f"将使用模型: {model}",
                     font=("Microsoft YaHei", 10), bg=THEME["bg"],
                     fg=THEME["fg"]).pack(pady=(16, 8))

            has_ao12 = stats.get("ao12_results") is not None
            analyze_best_var = tk.BooleanVar(value=False)
            analyze_worst_var = tk.BooleanVar(value=False)

            cb_frame = tk.Frame(confirm_win, bg=THEME["bg"])
            cb_frame.pack(pady=4)
            cb_best = tk.Checkbutton(cb_frame, text="分析最佳Ao12", variable=analyze_best_var,
                                     bg=THEME["bg"], fg=THEME["fg"],
                                     activebackground=THEME["bg"],
                                     font=("Microsoft YaHei", 9),
                                     state="normal" if has_ao12 else "disabled")
            cb_best.pack(anchor="w", padx=40)
            cb_worst = tk.Checkbutton(cb_frame, text="分析最差Ao12", variable=analyze_worst_var,
                                      bg=THEME["bg"], fg=THEME["fg"],
                                      activebackground=THEME["bg"],
                                      font=("Microsoft YaHei", 9),
                                      state="normal" if has_ao12 else "disabled")
            cb_worst.pack(anchor="w", padx=40)

            if not has_ao12:
                tk.Label(confirm_win, text="（今日还原次数≤12，无法计算Ao12）",
                         font=("Microsoft YaHei", 8), bg=THEME["bg"],
                         fg="#999").pack(pady=(2, 0))

            btn_row = tk.Frame(confirm_win, bg=THEME["bg"])
            btn_row.pack(pady=12)

            def on_confirm():
                confirm_win.destroy()
                _start_ai(api_key, model, analyze_best_var.get(), analyze_worst_var.get())

            def on_cancel():
                confirm_win.destroy()

            ttk.Button(btn_row, text="确认", command=on_confirm,
                       style="Accent.TButton").pack(side=tk.LEFT, padx=8)
            ttk.Button(btn_row, text="取消", command=on_cancel,
                       style="Secondary.TButton").pack(side=tk.LEFT, padx=8)

        def _start_ai(api_key: str, model: str, analyze_best: bool, analyze_worst: bool):
            ai_btn.config(state="disabled", text="⏳ AI思考中...")

            _daily_stream_stop = [False]
            _current_step_id = [0]

            def _update_step_status(step_text):
                report_text.config(state="normal")
                tag_name = f"_step_{step_text}"
                report_text.tag_configure(tag_name, font=("Microsoft YaHei", 11, "bold"),
                                          foreground=THEME["accent"])
                report_text.insert(tk.END, f"\n{step_text}\n", tag_name)
                report_text.config(state="disabled")
                report_text.see(tk.END)
                win.update_idletasks()

            _thinking_mark = "_thinking_start"
            _thinking_mark_set = [False]

            def _set_thinking_mark():
                report_text.mark_set(_thinking_mark, tk.END + "-1c")
                report_text.mark_gravity(_thinking_mark, tk.LEFT)
                _thinking_mark_set[0] = True

            def _update_thinking_preview(text, step_id):
                if step_id != _current_step_id[0]:
                    return
                report_text.config(state="normal")
                if _thinking_mark_set[0]:
                    start_idx = report_text.index(_thinking_mark)
                    end_idx = report_text.index(tk.END + "-1c")
                    if start_idx != end_idx:
                        report_text.delete(start_idx, end_idx)
                report_text.insert(tk.END, text, "thinking")
                report_text.config(state="disabled")
                report_text.see(tk.END)

            def _clear_thinking(step_id):
                if step_id != _current_step_id[0]:
                    return
                report_text.config(state="normal")
                if _thinking_mark_set[0]:
                    start_idx = report_text.index(_thinking_mark)
                    end_idx = report_text.index(tk.END + "-1c")
                    if start_idx != end_idx:
                        report_text.delete(start_idx, end_idx)
                _thinking_mark_set[0] = False
                report_text.config(state="disabled")

            def _append_content(text):
                report_text.config(state="normal")
                report_text.insert(tk.END, text, "ai_summary")
                report_text.config(state="disabled")
                report_text.see(tk.END)

            def _stream_step(api_key, model, stream_fn, step_label):
                _current_step_id[0] += 1
                step_id = _current_step_id[0]

                win.after(0, lambda: _update_step_status(step_label))
                win.after(0, lambda: _set_thinking_mark())

                reasoning_buffer = ""
                content_buffer = ""
                has_output = False

                for chunk_type, chunk_text in stream_fn(api_key, model):
                    if _daily_stream_stop[0]:
                        break
                    if chunk_type == "reasoning":
                        reasoning_buffer += chunk_text
                        if not has_output:
                            preview = reasoning_buffer[-300:] if len(reasoning_buffer) > 300 else reasoning_buffer
                            win.after(0, lambda p=preview, sid=step_id: _update_thinking_preview(p, sid))
                    elif chunk_type == "content":
                        if not has_output:
                            has_output = True
                            win.after(0, lambda sid=step_id: _clear_thinking(sid))
                        content_buffer += chunk_text
                        win.after(0, lambda t=chunk_text: _append_content(t))

                return content_buffer

            def _stream_ao12_analysis(api_key, model, analyzers, which):
                from openai import OpenAI

                memory_text = self._build_memory_text() if self._use_memory_var.get() else ""
                comparison_text = self._build_multi_comparison_text(analyzers) if self._use_memory_var.get() else ""
                system_prompt, user_prompt = self._build_multi_analysis_prompts(
                    analyzers, memory_text + comparison_text
                )

                count = len(analyzers)
                multi_max_tokens = 4096 + count * 800
                if multi_max_tokens > 16384:
                    multi_max_tokens = 16384

                client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=True,
                    max_tokens=multi_max_tokens,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        yield ("reasoning", delta.reasoning_content)
                    elif delta.content:
                        yield ("content", delta.content)

            def _run():
                try:
                    summary_result = _stream_step(
                        api_key, model,
                        lambda ak, md: daily_report.call_ai_summary_stream(ak, md, stats),
                        "⏳ 正在总结今日练习..."
                    )
                    ai_summary_holder["text"] = summary_result

                    best_analysis = ""
                    worst_analysis = ""

                    if analyze_best:
                        analyzers_best = _build_ao12_analyzers(stats, "best")
                        if analyzers_best:
                            best_analysis = _stream_step(
                                api_key, model,
                                lambda ak, md, a=analyzers_best: _stream_ao12_analysis(ak, md, a, "best"),
                                "🏆 正在分析最佳Ao12..."
                            )
                        else:
                            best_analysis = "最佳Ao12分析: 无法解析有效数据"
                        ao12_analysis_holder["best"] = best_analysis

                    if analyze_worst:
                        analyzers_worst = _build_ao12_analyzers(stats, "worst")
                        if analyzers_worst:
                            worst_analysis = _stream_step(
                                api_key, model,
                                lambda ak, md, a=analyzers_worst: _stream_ao12_analysis(ak, md, a, "worst"),
                                "📉 正在分析最差Ao12..."
                            )
                        else:
                            worst_analysis = "最差Ao12分析: 无法解析有效数据"
                        ao12_analysis_holder["worst"] = worst_analysis

                    win.after(0, lambda: _on_ai_done(summary_result, best_analysis, worst_analysis))
                except Exception as ex:
                    win.after(0, lambda e=str(ex): _on_ai_error(e))

            threading.Thread(target=_run, daemon=True).start()

        def _build_ao12_analyzers(stats: Dict, which: str):
            from analyzer import CFOPAnalyzer
            from config import COLOR_CODES

            ao12 = stats["ao12_results"]
            group = ao12[which]
            records = stats["records"]
            start_idx = group["index"] - 1

            analyzers = []
            for j in range(12):
                rec = records[start_idx + j]
                scramble = rec["scramble"]
                solution = rec["solution"]
                bottom_name = rec["bottom_color"]
                bottom_color = COLOR_CODES.get(bottom_name, bottom_name)
                if not bottom_color or len(bottom_color) > 1:
                    continue
                try:
                    analyzer = CFOPAnalyzer.from_bottom_color(scramble, solution, bottom_color)
                    if analyzer.is_solve_complete():
                        analyzers.append(analyzer)
                except Exception:
                    continue

            return analyzers

        def _on_ai_done(result, best_analysis, worst_analysis):
            ai_btn.config(state="normal", text="🤖 AI总结")

            report_text.config(state="normal")
            report_text.delete("1.0", tk.END)
            stats_text_new = daily_report.build_stats_text(stats)
            for line in stats_text_new.split("\n"):
                if line.startswith("📅"):
                    report_text.insert(tk.END, line + "\n", "heading")
                elif line.startswith("各阶段") or line.startswith("12次") or line.startswith("Ao12"):
                    report_text.insert(tk.END, line + "\n", "section")
                elif line.startswith("🏆") or line.startswith("📉"):
                    report_text.insert(tk.END, line + "\n", "bold")
                else:
                    report_text.insert(tk.END, line + "\n", "normal")
            report_text.insert(tk.END, "\n🤖 AI 总结\n", "section")
            report_text.insert(tk.END, result + "\n", "ai_summary")

            if best_analysis:
                report_text.insert(tk.END, "\n🏆 最佳Ao12 AI分析\n", "section")
                report_text.insert(tk.END, best_analysis + "\n", "ai_summary")
            if worst_analysis:
                report_text.insert(tk.END, "\n📉 最差Ao12 AI分析\n", "section")
                report_text.insert(tk.END, worst_analysis + "\n", "ai_summary")

            report_text.config(state="disabled")
            report_text.see(tk.END)

        def _on_ai_error(err):
            ai_btn.config(state="normal", text="🤖 AI总结")
            messagebox.showerror("AI总结失败", err, parent=win)

        def do_save_pdf():
            path = filedialog.asksaveasfilename(
                parent=win,
                defaultextension=".pdf",
                filetypes=[("PDF文件", "*.pdf")],
                initialfile=f"CFOP今日总结_{stats['date']}.pdf",
            )
            if not path:
                return
            try:
                line_p = ""
                hist_p = ""
                try:
                    line_p, hist_p = daily_report.generate_charts(stats["times"])
                except Exception:
                    pass
                daily_report.save_pdf(stats, ai_summary_holder["text"],
                                      line_p, hist_p, path,
                                      ao12_best_analysis=ao12_analysis_holder["best"],
                                      ao12_worst_analysis=ao12_analysis_holder["worst"])
                messagebox.showinfo("保存成功", f"报告已保存至:\n{path}", parent=win)
            except Exception as ex:
                messagebox.showerror("保存失败", str(ex), parent=win)

        ai_btn = ttk.Button(btn_frame, text="🤖 AI总结", command=do_ai_summary,
                            style="Accent.TButton")
        ai_btn.pack(side=tk.LEFT, padx=(0, 8))

        pdf_btn = ttk.Button(btn_frame, text="📄 保存PDF", command=do_save_pdf,
                             style="Secondary.TButton")
        pdf_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btn_frame, text="关闭", command=win.destroy,
                   style="Secondary.TButton").pack(side=tk.RIGHT)
    
    def _do_multi_analysis(self):
        api_key = self.api_key_entry.get().strip()
        model = self.model_var.get()
        
        if not api_key:
            self._reset_analysis_ui()
            messagebox.showwarning("警告", "请输入API Key！")
            return
        if not model:
            self._reset_analysis_ui()
            messagebox.showwarning("警告", "请选择模型！")
            return
        
        if not hasattr(self, 'multi_inputs') or not self.multi_inputs:
            self._reset_analysis_ui()
            messagebox.showwarning("警告", "请先输入数据！")
            return
        
        groups_data = []
        for i, inp in enumerate(self.multi_inputs):
            scramble = inp['scramble'].get().strip()
            solution = inp['solution'].get().strip()
            bottom_name = inp['orientation_var'].get()
            bottom_color = self._get_bottom_color_from_name(bottom_name)
            
            if not bottom_color:
                self._reset_analysis_ui()
                messagebox.showwarning("警告", f"第 {i+1} 组底色无效，请检查！")
                return
            
            if not scramble or not solution:
                self._reset_analysis_ui()
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

        multi_times = [a.get_total_time() for a in analyzers]
        if multi_times:
            avg_time = sum(multi_times) / len(multi_times)
            if not self._check_anomaly_and_confirm(avg_time, '多组'):
                self._reset_analysis_ui()
                return

        memory_text = self._build_memory_text() if self._use_memory_var.get() else ""
        comparison_text = self._build_multi_comparison_text(analyzers) if self._use_memory_var.get() else ""
        system_prompt, user_prompt = self._build_multi_analysis_prompts(analyzers, memory_text + comparison_text)
        
        self._last_multi_data = list(zip(groups_data, analyzers))
        
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
    
    def _build_multi_analysis_prompts(self, analyzers, memory_text=""):
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
            groups_detail=groups_detail,
            memory_info=memory_text
        )
        
        return (system, user)
