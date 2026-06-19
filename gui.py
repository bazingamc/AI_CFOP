"""
GUI应用主类 - CFOPAnalyzerGUI
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict
import threading
import json
import re
import os
from datetime import datetime

from config import (
    THEME, HELP_TEXTS, PHASE_COLORS, PHASE_LABELS,
    ORIENTATION_OPTIONS, PHASE_ORDER,
    BOTTOM_COLOR_NAMES, BOTTOM_COLOR_OPTIONS, OPPOSITE_COLORS, COLOR_NAMES,
    RESULT_DIR, SILICONFLOW_BASE_URL, APP_DIR,
    OLL_ALGORITHMS, PLL_ALGORITHMS, OP_ALGO_CONFIG_FILE
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

    @staticmethod
    def _resolve_avatar_path(avatar_path: str) -> str:
        """将头像路径解析为绝对路径，支持相对路径（png/avatars/...）和绝对路径"""
        if not avatar_path:
            return ""
        if os.path.isabs(avatar_path):
            return avatar_path
        # 相对路径，基于APP_DIR解析
        abs_path = os.path.join(APP_DIR, avatar_path)
        if os.path.isfile(abs_path):
            return abs_path
        # 兼容旧的绝对路径
        if os.path.isfile(avatar_path):
            return avatar_path
        return abs_path

    def _center_window(self, win):
        """将弹窗居中于主窗口"""
        win.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_w = self.root.winfo_width()
        main_h = self.root.winfo_height()
        win_w = win.winfo_width()
        win_h = win.winfo_height()
        x = main_x + (main_w - win_w) // 2
        y = main_y + (main_h - win_h) // 2
        win.wm_geometry(f"+{x}+{y}")

    def __init__(self, root):
        self.root = root
        self.root.title("AI_CFOP V1.3")
        self.root.geometry("960x980")
        self.root.resizable(True, True)
        self.root.configure(bg=THEME["bg"])
        self._stream_stop = False
        self._stream_buffer = ""
        self._reasoning_buffer = ""
        self._solution_summary = ""
        self._replay_analyzers = []
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
        # 提前初始化数据库，确保_create_widgets中访问数据库时表已存在
        memory_db.init_db()
        self._setup_styles()
        self._create_widgets()
        self._load_saved_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1, self._show_user_select_and_init)

    def _show_user_select_and_init(self):
        try:
            memory_db.init_db()
            user_manager.init_users_table()
            # 回填processed_solve字段（仅对空值记录，一次性操作）
            try:
                updated = memory_db.backfill_processed_solve()
                if updated > 0 and log:
                    log.info(f"已回填 {updated} 条记录的processed_solve字段")
            except Exception as e:
                if log:
                    log.warning(f"回填processed_solve失败: {e}")
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

        dialog.geometry("500x520")
        self._center_window(dialog)

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

        def _on_user_select_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_user_select_mousewheel)
        scroll_frame.bind("<MouseWheel>", _on_user_select_mousewheel)
        list_frame.bind("<MouseWheel>", _on_user_select_mousewheel)

        def refresh_user_list():
            for w in scroll_frame.winfo_children():
                w.destroy()
            users = user_manager.get_all_users()
            for u in users:
                row = tk.Frame(scroll_frame, bg=THEME["card_bg"], pady=6)
                row.pack(fill=tk.X, padx=8)

                avatar_path = self._resolve_avatar_path(u.get("avatar", ""))
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

        dialog.geometry("400x240")
        self._center_window(dialog)

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

        dialog.geometry("500x480")
        self._center_window(dialog)

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

        def _on_user_manage_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_user_manage_mousewheel)
        scroll_frame.bind("<MouseWheel>", _on_user_manage_mousewheel)
        list_frame.bind("<MouseWheel>", _on_user_manage_mousewheel)

        def refresh_list():
            for w in scroll_frame.winfo_children():
                w.destroy()
            users = user_manager.get_all_users()
            for u in users:
                row = tk.Frame(scroll_frame, bg=THEME["card_bg"], pady=4)
                row.pack(fill=tk.X, padx=4, pady=2)

                avatar_path = self._resolve_avatar_path(u.get("avatar", ""))
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

        dialog.geometry("420x280")
        self._center_window(dialog)

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
        current_avatar = self._resolve_avatar_path(user_info.get("avatar", "")) if user_info else ""
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
                # 复制头像到png/avatars目录
                avatar_dir = os.path.join(APP_DIR, "png", "avatars")
                os.makedirs(avatar_dir, exist_ok=True)
                ext = os.path.splitext(path)[1] or ".png"
                import shutil
                dest_name = f"user_{user_id}{ext}"
                dest_path = os.path.join(avatar_dir, dest_name)
                try:
                    shutil.copy2(path, dest_path)
                    # 存储相对路径 png/avatars/user_X.png
                    new_avatar_path[0] = os.path.join("png", "avatars", dest_name)
                except Exception:
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

        confirm.geometry("360x160")
        self._center_window(confirm)

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
            # 如果删除的是当前用户，重置用户状态
            if user_id == self._current_user_id:
                self._current_user_id = None
                self._current_username = ""
                memory_db.set_user(None)
            confirm.destroy()
            # 刷新数据管理页面和首页统计
            if hasattr(self, '_refresh_data_tab'):
                self._refresh_data_tab()
            if hasattr(self, '_refresh_home_stats'):
                self._refresh_home_stats()
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
            avatar_path = self._resolve_avatar_path(user_info.get("avatar", "")) if user_info else ""
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

        dialog.geometry("420x240")
        self._center_window(dialog)

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
            if hasattr(self, 'multi_inputs') and self.multi_inputs:
                for inp in self.multi_inputs:
                    if 'scramble' in inp:
                        inp['scramble'].config(state=state)
                    if 'solution' in inp:
                        inp['solution'].config(state=state)
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

        # 统一滚动条样式
        style.configure("TScrollbar",
                        background=THEME["border"],
                        troughcolor=THEME["card_bg"],
                        borderwidth=0,
                        arrowsize=13,
                        relief="flat")
        style.map("TScrollbar",
                  background=[("active", THEME["accent"]), ("pressed", THEME["accent_hover"])],
                  arrowcolor=[("active", THEME["button_fg"])])
    
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
            text_height = len(lines)

            label = tk.Label(frame, text=text.strip(), font=("Microsoft YaHei", 9),
                             bg="#ffffcc", fg=THEME["fg"],
                             padx=8, pady=6, wraplength=text_width * 9,
                             justify=tk.LEFT, anchor="nw")
            label.pack()

            tooltip[0] = tip

            def on_tip_enter(e):
                if hide_timer[0]:
                    widget.after_cancel(hide_timer[0])
                    hide_timer[0] = None

            def on_tip_leave(e):
                hide_tooltip(None)

            tip.bind("<Enter>", on_tip_enter)
            tip.bind("<Leave>", on_tip_leave)
            label.bind("<Leave>", on_tip_leave)

        def hide_tooltip(event):
            def do_hide():
                if tooltip[0]:
                    tooltip[0].destroy()
                    tooltip[0] = None
                hide_timer[0] = None

            hide_timer[0] = widget.after(100, do_hide)

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    def _on_recalculate_db(self):
        """点击数据库更新按钮，重新计算所有记录"""
        if not messagebox.askyesno("确认", "将重新计算当前用户所有记录的分析结果，是否继续？"):
            return

        # 创建进度弹窗
        progress_win = tk.Toplevel(self.root)
        progress_win.title("更新数据库")
        progress_win.geometry("400x150")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()
        progress_win.configure(bg=THEME["bg"])
        self._center_window(progress_win)

        tk.Label(progress_win, text="正在重新计算分析结果...",
                 bg=THEME["bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 11)).pack(pady=(20, 10))

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_win, variable=progress_var, maximum=100, length=350)
        progress_bar.pack(pady=5)

        status_label = tk.Label(progress_win, text="准备中...",
                                bg=THEME["bg"], fg="#888",
                                font=("Microsoft YaHei", 9))
        status_label.pack(pady=5)

        def on_progress(current, total):
            progress_win.after(0, lambda: progress_var.set(current / total * 100 if total > 0 else 0))
            progress_win.after(0, lambda: status_label.config(text=f"{current}/{total}"))

        def do_recalculate():
            result = memory_db.recalculate_all_records(progress_cb=on_progress)
            progress_win.after(0, lambda: self._on_recalculate_done(progress_win, result))

        import threading
        t = threading.Thread(target=do_recalculate, daemon=True)
        t.start()

    def _on_recalculate_done(self, progress_win, result):
        """数据库重算完成回调"""
        try:
            progress_win.destroy()
        except Exception:
            pass

        total = result.get("total", 0)
        updated = result.get("updated", 0)
        failed = result.get("failed", 0)

        msg = f"更新完成！\n总计: {total} 条\n成功: {updated} 条\n失败: {failed} 条"
        messagebox.showinfo("更新完成", msg)

        # 刷新界面
        if hasattr(self, '_refresh_data_tab'):
            self._refresh_data_tab()
        if hasattr(self, '_refresh_home_stats'):
            self._refresh_home_stats()

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
        self._center_window(progress_win)

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

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="选择CSV文件",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        if not path:
            return

        progress_win = tk.Toplevel(self.root)
        progress_win.title("导入CSV数据")
        progress_win.geometry("350x120")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()
        self._center_window(progress_win)

        tk.Label(progress_win, text="正在导入，请稍候...", font=("Microsoft YaHei", 10)).pack(pady=(15, 5))
        progress_label = tk.Label(progress_win, text="准备中...", font=("Microsoft YaHei", 9), fg="#666")
        progress_label.pack(pady=5)

        def on_progress(current, total):
            progress_label.config(text=f"处理中: {current}/{total}")
            progress_win.update()

        def do_import():
            try:
                result = memory_db.import_csv(path, progress_cb=on_progress)
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

        dialog.geometry("500x520")
        self._center_window(dialog)
        
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
3. 配置API Key 并选择合适的模型。
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

【功能说明】

🏠 首页
• 水平统计：展示PB、平均用时、TPS、各阶段详细统计（步数/用时/观察/卡顿/废步/TPS及标准差），以及优点和缺点TOP3标签
• 智能训练：今日训练总结，包含统计文本、时间趋势折线图、时间分布直方图，支持AI总结和Ao12分析

🔬 深度分析
• 单组/多组模式：单组分析单次还原，多组分析最多20组还原并计算平均和波动度
• 底色自动识别：无需手动选择底色，软件自动检测
• 解法复盘：Canvas色块时间轴，按CFOP阶段分行显示，步骤宽度与时间成正比，鼠标悬停查看步骤详情和阶段统计
• AI流式输出：实时显示AI推理过程和分析结果，支持Markdown格式渲染
• 智能粘贴：开启后自动监控剪贴板，识别csTimer数据并填入输入框，支持去重检测

📂 数据管理
• 数据列表：展示还原记录，支持按时间/用时/步数/TPS排序，点击列标题切换升降序
• 日期筛选：按日期范围筛选记录，支持"本月"快捷按钮
• 多选分析：支持Ctrl/Shift多选记录，点击"分析选中项"直接跳转深度分析
• 还原详情：双击记录查看详情，含解法复盘时间轴和优缺点标签
• 数据导入：支持csTimer导出文件和CSV文件导入，带进度弹窗
• 数据导出：导出为CSV文件

⚙️ 设置
• API Key配置：密钥加密存储，安全可靠
• 模型选择：从API获取可用模型列表
• 智能粘贴开关：控制剪贴板自动监控
• 记忆模式开关：记录分析历史，提供对比参考和训练建议
• 数据库更新：重新计算所有记录的分析结果

👤 用户管理
• 多用户支持：创建、编辑、删除用户，支持自定义头像
• 成绩异常检测：分析时自动检测成绩偏差，偏差过大时提示确认或切换用户

【交流反馈】
• 交流QQ群：322267527"""
        
        text_widget = tk.Text(main_frame, width=55, height=16,
                              font=("Microsoft YaHei", 10),
                              bg=THEME["card_bg"],
                              fg=THEME["fg"],
                              relief="flat", borderwidth=0,
                              wrap=tk.WORD, highlightthickness=0)
        guide_scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=guide_scrollbar.set)
        guide_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
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
        self._tab_training = ttk.Frame(self._notebook)
        self._tab_analysis = ttk.Frame(self._notebook)
        self._tab_data = ttk.Frame(self._notebook)
        self._tab_settings = ttk.Frame(self._notebook)
        self._tab_help = ttk.Frame(self._notebook)

        self._notebook.add(self._tab_home, text="  🏠 首页  ")
        self._notebook.add(self._tab_training, text="  🎯 智能训练  ")
        self._notebook.add(self._tab_analysis, text="  🔬 深度分析  ")
        self._notebook.add(self._tab_data, text="  📂 数据管理  ")
        self._notebook.add(self._tab_settings, text="  ⚙️ 设置  ")
        self._notebook.add(self._tab_help, text="  ❓ 帮助  ")

        self._build_home_tab()
        self._build_training_tab()
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
        ttk.Button(stats_header, text="🔄 刷新", command=self._refresh_home_stats,
                   style="Accent.TButton").pack(side=tk.RIGHT)

        # 内容容器（无滚动条，一页展示）
        self._home_scroll_frame = tk.Frame(tab, bg=THEME["bg"])
        self._home_scroll_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self._refresh_home_stats()

    def _make_stat_card(self, parent, title, value, subtitle="", bg_color=None, width=160):
        """创建一个统计卡片"""
        card_bg = bg_color or THEME["card_bg"]
        card = tk.Frame(parent, bg=card_bg, padx=12, pady=8,
                        highlightthickness=1, highlightbackground=THEME["border"])
        card.pack(side=tk.LEFT, padx=(0, 8), fill=tk.BOTH, expand=True)

        tk.Label(card, text=title, font=("Microsoft YaHei", 9),
                 bg=card_bg, fg="#888888").pack(anchor="w")
        tk.Label(card, text=value, font=("Microsoft YaHei", 20, "bold"),
                 bg=card_bg, fg=THEME["fg"]).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, font=("Microsoft YaHei", 8),
                     bg=card_bg, fg="#999999").pack(anchor="w")
        return card

    def _make_phase_card(self, parent, phase, label, data, color):
        """创建一个阶段统计卡片"""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        light_bg = f"#{min(r+140,255):02x}{min(g+140,255):02x}{min(b+140,255):02x}"

        card = tk.Frame(parent, bg=light_bg, padx=10, pady=6,
                        highlightthickness=1, highlightbackground=color)
        card.pack(side=tk.LEFT, padx=(0, 6), pady=2, fill=tk.BOTH, expand=True)

        tk.Label(card, text=label, font=("Microsoft YaHei", 11, "bold"),
                 bg=light_bg, fg=color).pack(anchor="w")

        time_str = f"{data['time'] + data['observation_time']:.2f}s"
        tk.Label(card, text=time_str, font=("Microsoft YaHei", 16, "bold"),
                 bg=light_bg, fg=THEME["fg"]).pack(anchor="w")

        detail = f"{data['steps']:.1f}步  {data['tps']:.1f}TPS"
        tk.Label(card, text=detail, font=("Microsoft YaHei", 10),
                 bg=light_bg, fg="#666666").pack(anchor="w")

        obs_str = f"观察 {data['observation_time']:.2f}s"
        tk.Label(card, text=obs_str, font=("Microsoft YaHei", 10),
                 bg=light_bg, fg="#666666").pack(anchor="w")

        std_str = f"σ步{data['steps_std']:.1f} σ时{data['time_std']:.2f}"
        tk.Label(card, text=std_str, font=("Microsoft YaHei", 9),
                 bg=light_bg, fg="#aaaaaa").pack(anchor="w")

        return card

    def _make_tag_chip(self, parent, text, is_strength=True):
        """创建优缺点标签"""
        bg = "#d4edda" if is_strength else "#f8d7da"
        fg = "#155724" if is_strength else "#721c24"
        chip = tk.Label(parent, text=text, font=("Microsoft YaHei", 9),
                        bg=bg, fg=fg, padx=8, pady=3, relief="flat")
        chip.pack(side=tk.LEFT, padx=(0, 6), pady=2)
        return chip

    def _refresh_home_stats(self):
        from config import PHASE_ORDER, PHASE_COLORS, PHASE_LABELS
        parent = self._home_scroll_frame

        for w in parent.winfo_children():
            w.destroy()

        avg = memory_db.get_averages()
        if not avg:
            tk.Label(parent, text="暂无数据，完成分析后自动记录",
                     font=("Microsoft YaHei", 11), bg=THEME["bg"], fg="#999999").pack(pady=40)
            return

        pb = memory_db.get_pb()
        total_avg = memory_db.get_total_time_avg()
        total_std = memory_db.get_total_time_std()
        total_tps_avg = memory_db.get_total_tps_avg()
        total_tps_std = memory_db.get_total_tps_std()
        total_avg_7d = memory_db.get_total_time_avg(days=7)
        total_tps_7d = memory_db.get_total_tps_avg(days=7)

        # ═══ 第一行：核心指标卡片 ═══
        cards_row = tk.Frame(parent, bg=THEME["bg"])
        cards_row.pack(fill=tk.X, pady=(4, 8))

        pb_val = f"{pb['time']:.2f}s" if pb else "--"
        pb_sub = f"({pb['date']}) 全部数据" if pb else "全部数据"
        self._make_stat_card(cards_row, "🏆 个人最佳", pb_val, pb_sub, width=180)

        avg_val = f"{total_avg:.2f}s" if total_avg else "--"
        avg_sub_parts = []
        avg_sub_parts.append("最近1000次")
        if total_std:
            avg_sub_parts.append(f"σ {total_std:.2f}s")
        if total_avg_7d and total_avg:
            diff = total_avg_7d - total_avg
            arrow = "↑" if diff < 0 else "↓"
            color_hint = "进步" if diff < 0 else "退步"
            avg_sub_parts.append(f"近7天 {total_avg_7d:.2f}s {arrow}{color_hint}")
        avg_sub = "  |  ".join(avg_sub_parts)
        self._make_stat_card(cards_row, "⏱ 平均用时", avg_val, avg_sub, width=220)

        tps_val = f"{total_tps_avg:.1f}" if total_tps_avg else "--"
        tps_sub_parts = []
        tps_sub_parts.append("最近1000次")
        if total_tps_std:
            tps_sub_parts.append(f"σ {total_tps_std:.1f}")
        if total_tps_7d and total_tps_avg:
            diff = total_tps_7d - total_tps_avg
            arrow = "↑" if diff > 0 else "↓"
            tps_sub_parts.append(f"近7天 {total_tps_7d:.1f} {arrow}")
        tps_sub = "  |  ".join(tps_sub_parts)
        self._make_stat_card(cards_row, "⚡ 平均TPS", tps_val, tps_sub, width=200)

        # ═══ 第二行：各阶段统计卡片 ═══
        phase_section = tk.Frame(parent, bg=THEME["bg"])
        phase_section.pack(fill=tk.X, pady=(0, 8))

        tk.Label(phase_section, text="各阶段统计（最近1000次）", font=("Microsoft YaHei", 10, "bold"),
                 bg=THEME["bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 4))

        row1 = tk.Frame(phase_section, bg=THEME["bg"])
        row1.pack(fill=tk.X, pady=(0, 4))

        if "cross" in avg:
            self._make_phase_card(row1, "cross", "Cross", avg["cross"], PHASE_COLORS["cross"])

        f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
        f2l_available = [p for p in f2l_phases if p in avg]
        if f2l_available:
            f2l_avg = {
                "time": sum(avg[p]["time"] for p in f2l_available) / len(f2l_available),
                "steps": sum(avg[p]["steps"] for p in f2l_available) / len(f2l_available),
                "tps": sum(avg[p]["tps"] for p in f2l_available) / len(f2l_available),
                "observation_time": sum(avg[p]["observation_time"] for p in f2l_available) / len(f2l_available),
                "steps_std": sum(avg[p]["steps_std"] for p in f2l_available) / len(f2l_available),
                "time_std": sum(avg[p]["time_std"] for p in f2l_available) / len(f2l_available),
            }
            self._make_phase_card(row1, "f2l", "F2L均值", f2l_avg, "#6c5ce7")

        if "oll" in avg:
            self._make_phase_card(row1, "oll", "OLL", avg["oll"], PHASE_COLORS["oll"])

        if "pll" in avg:
            self._make_phase_card(row1, "pll", "PLL", avg["pll"], PHASE_COLORS["pll"])

        if f2l_available:
            f2l_label_row = tk.Frame(phase_section, bg=THEME["bg"])
            f2l_label_row.pack(fill=tk.X, pady=(0, 2))
            tk.Label(f2l_label_row, text="F2L各组:", font=("Microsoft YaHei", 9),
                     bg=THEME["bg"], fg="#888888").pack(side=tk.LEFT, padx=(0, 6))

            row2 = tk.Frame(phase_section, bg=THEME["bg"])
            row2.pack(fill=tk.X, pady=(0, 4))

            for p in f2l_phases:
                if p in avg:
                    self._make_phase_card(row2, p, PHASE_LABELS[p], avg[p], PHASE_COLORS[p])

        # ═══ 第三行：趋势对比 ═══
        trend_periods = [
            ("近7天", 7), ("近30天", 30), ("近1年", 365), ("全部", None)
        ]
        trend_data = []
        for label, days in trend_periods:
            t_avg = memory_db.get_total_time_avg(days=days, limit=None)
            s_avg = memory_db.get_total_steps_avg(days=days, limit=None)
            tps_avg = memory_db.get_total_tps_avg(days=days, limit=None)
            cnt = memory_db.get_record_count_by_period(days=days)
            if t_avg is not None:
                trend_data.append((label, t_avg, s_avg, tps_avg, cnt))

        if len(trend_data) >= 2:
            trend_section = tk.Frame(parent, bg=THEME["bg"])
            trend_section.pack(fill=tk.X, pady=(0, 8))

            tk.Label(trend_section, text="趋势对比", font=("Microsoft YaHei", 10, "bold"),
                     bg=THEME["bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 4))

            trend_card = tk.Frame(trend_section, bg=THEME["card_bg"], padx=12, pady=8,
                                   highlightthickness=1, highlightbackground=THEME["border"])
            trend_card.pack(fill=tk.X)

            # 使用grid布局保证对齐
            headers = ["时段", "记录数", "用时", "变化", "步数", "TPS"]
            header_anchors = ["w", "e", "e", "e", "e", "w"]
            for col, (h, a) in enumerate(zip(headers, header_anchors)):
                trend_card.columnconfigure(col, weight=0, minsize=10)
                tk.Label(trend_card, text=h, font=("Microsoft YaHei", 9, "bold"),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor=a
                         ).grid(row=0, column=col, padx=(8, 4), pady=(0, 4), sticky="w" if a == "w" else "e")
            # 空列撑满右侧留白
            trend_card.columnconfigure(len(headers), weight=1)
            tk.Label(trend_card, text="", bg=THEME["card_bg"]
                     ).grid(row=0, column=len(headers), sticky="ew")

            sep_frame = tk.Frame(trend_card, bg=THEME["border"], height=1)
            sep_frame.grid(row=1, column=0, columnspan=len(headers), sticky="ew", pady=2)

            for row_idx, (period_label, t_avg, s_avg, tps_avg, cnt) in enumerate(trend_data, start=2):
                tk.Label(trend_card, text=period_label, font=("Microsoft YaHei", 9),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor="w"
                         ).grid(row=row_idx, column=0, padx=(8, 4), pady=1, sticky="w")

                tk.Label(trend_card, text=str(cnt), font=("Microsoft YaHei", 9),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor="e"
                         ).grid(row=row_idx, column=1, padx=(4, 6), pady=1, sticky="e")

                tk.Label(trend_card, text=f"{t_avg:.2f}s", font=("Microsoft YaHei", 9),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor="e"
                         ).grid(row=row_idx, column=2, padx=(4, 6), pady=1, sticky="e")

                # 变化趋势：当前行与下一行（更长时段）比较
                next_idx = row_idx - 2 + 1  # trend_data中的下一个索引
                if next_idx < len(trend_data):
                    next_time = trend_data[next_idx][1]
                    diff = t_avg - next_time
                    if abs(diff) > 0.01:
                        arrow = "↑" if diff < 0 else "↓"
                        arrow_fg = "#e74c3c" if diff < 0 else "#27ae60"
                        diff_str = f"{arrow} {abs(diff):.2f}s"
                        tk.Label(trend_card, text=diff_str, font=("Microsoft YaHei", 9),
                                 bg=THEME["card_bg"], fg=arrow_fg, anchor="e"
                                 ).grid(row=row_idx, column=3, padx=(4, 6), pady=1, sticky="e")
                    else:
                        tk.Label(trend_card, text="--", font=("Microsoft YaHei", 9),
                                 bg=THEME["card_bg"], fg="#999999", anchor="e"
                                 ).grid(row=row_idx, column=3, padx=(4, 6), pady=1, sticky="e")
                else:
                    tk.Label(trend_card, text="--", font=("Microsoft YaHei", 9),
                             bg=THEME["card_bg"], fg="#999999", anchor="e"
                             ).grid(row=row_idx, column=3, padx=(4, 6), pady=1, sticky="e")

                steps_str = f"{s_avg:.1f}" if s_avg else "--"
                tk.Label(trend_card, text=steps_str, font=("Microsoft YaHei", 9),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor="e"
                         ).grid(row=row_idx, column=4, padx=(4, 6), pady=1, sticky="e")

                tps_str = f"{tps_avg:.1f}" if tps_avg else "--"
                tk.Label(trend_card, text=tps_str, font=("Microsoft YaHei", 9),
                         bg=THEME["card_bg"], fg=THEME["fg"], anchor="w"
                         ).grid(row=row_idx, column=5, padx=(4, 6), pady=1, sticky="w")

        # ═══ 第四行：优缺点标签 ═══
        tag_stats = memory_db.get_tag_stats()
        top_s = tag_stats.get("top_strengths", [])
        top_w = tag_stats.get("top_weaknesses", [])

        if top_s or top_w:
            tag_section = tk.Frame(parent, bg=THEME["bg"])
            tag_section.pack(fill=tk.X, pady=(0, 8))

            if top_s:
                s_row = tk.Frame(tag_section, bg=THEME["bg"])
                s_row.pack(fill=tk.X, pady=(0, 4))
                tk.Label(s_row, text="💪 优点:", font=("Microsoft YaHei", 9, "bold"),
                         bg=THEME["bg"], fg="#27ae60").pack(side=tk.LEFT, padx=(0, 6))
                for tag, cnt in top_s:
                    self._make_tag_chip(s_row, f"{tag} ({cnt})", is_strength=True)

            if top_w:
                w_row = tk.Frame(tag_section, bg=THEME["bg"])
                w_row.pack(fill=tk.X, pady=(0, 4))
                tk.Label(w_row, text="⚠ 缺点:", font=("Microsoft YaHei", 9, "bold"),
                         bg=THEME["bg"], fg="#e74c3c").pack(side=tk.LEFT, padx=(0, 6))
                for tag, cnt in top_w:
                    self._make_tag_chip(w_row, f"{tag} ({cnt})", is_strength=False)

        # ═══ 底部信息栏 ═══
        date_range = memory_db.get_date_range()
        count = memory_db.get_record_count()
        footer = tk.Frame(parent, bg=THEME["bg"])
        footer.pack(fill=tk.X, pady=(0, 4))
        tk.Label(footer, text=f"📋 {count}条记录  |  📅 {date_range}",
                 font=("Microsoft YaHei", 8), bg=THEME["bg"], fg="#aaaaaa").pack(anchor="w")

        # 刷新训练列表
        if hasattr(self, '_refresh_training_lists'):
            self._refresh_training_lists()

    def _build_training_tab(self):
        tab = self._tab_training

        # 可滚动容器
        canvas = tk.Canvas(tab, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=canvas.yview)
        self._train_scroll_frame = tk.Frame(canvas, bg=THEME["bg"])

        self._train_scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=self._train_scroll_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        parent = self._train_scroll_frame

        train_header = ttk.Frame(parent)
        train_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(train_header, text="  🎯 智能训练", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        # === OLL训练部分 ===
        oll_header = ttk.Frame(parent)
        oll_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(oll_header, text="  OLL训练", font=("Microsoft YaHei", 12, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        ttk.Button(oll_header, text="📈 OLL统计", command=self._show_oll_stats,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        self._oll_train_frame = tk.Frame(parent, bg=THEME["card_bg"], padx=12, pady=8,
                                          highlightthickness=1, highlightbackground=THEME["border"])
        self._oll_train_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        # === PLL训练部分 ===
        pll_header = ttk.Frame(parent)
        pll_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(pll_header, text="  PLL训练", font=("Microsoft YaHei", 12, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)
        ttk.Button(pll_header, text="📈 PLL统计", command=self._show_pll_stats,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=(4, 0))

        self._pll_train_frame = tk.Frame(parent, bg=THEME["card_bg"], padx=12, pady=8,
                                          highlightthickness=1, highlightbackground=THEME["border"])
        self._pll_train_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        # === 训练总结部分 ===
        summary_header = ttk.Frame(parent)
        summary_header.pack(fill=tk.X, pady=(8, 2), padx=8)
        ttk.Label(summary_header, text="  训练总结", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        summary_ctrl = tk.Frame(parent, bg=THEME["card_bg"], padx=12, pady=8,
                                 highlightthickness=1, highlightbackground=THEME["border"])
        summary_ctrl.pack(fill=tk.X, padx=8, pady=(0, 8))

        tk.Label(summary_ctrl, text="起始日期:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._summary_start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._summary_start_entry = ttk.Entry(summary_ctrl, textvariable=self._summary_start_var,
                                                width=12, font=("Microsoft YaHei", 9))
        self._summary_start_entry.pack(side=tk.LEFT, padx=(4, 8))

        tk.Label(summary_ctrl, text="结束日期:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self._summary_end_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._summary_end_entry = ttk.Entry(summary_ctrl, textvariable=self._summary_end_var,
                                              width=12, font=("Microsoft YaHei", 9))
        self._summary_end_entry.pack(side=tk.LEFT, padx=(4, 8))

        ttk.Button(summary_ctrl, text="📊 生成训练总结", command=self._show_date_range_report,
                   style="Accent.TButton").pack(side=tk.LEFT)

        # 初始化时填充训练列表
        self._refresh_training_lists()

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

        # 解法复盘显示区域（Canvas时间轴）
        self.replay_header = ttk.Frame(tab)
        self.replay_header.pack(fill=tk.X, padx=8, pady=(0, 2))
        ttk.Label(self.replay_header, text="  解法复盘", font=("Microsoft YaHei", 10, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        self.replay_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=8, pady=8,
                                      highlightthickness=1, highlightbackground=THEME["border"])
        self.replay_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.replay_frame.pack_propagate(False)
        self.replay_frame.configure(height=200)

        # 使用ScrolledText作为容器，内部放置Canvas
        self.replay_canvas_container = tk.Frame(self.replay_frame, bg=THEME["card_bg"])
        self.replay_canvas_container.pack(fill=tk.BOTH, expand=True)

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

        self.result_text = tk.Text(self.result_frame, width=60, height=20, wrap=tk.WORD,
                                   font=("Microsoft YaHei", 11),
                                   bg=THEME["card_bg"], fg=THEME["fg"],
                                   relief="flat", borderwidth=0,
                                   highlightthickness=0,
                                   insertbackground=THEME["accent"])
        result_scrollbar = ttk.Scrollbar(self.result_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        result_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
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

        tk.Label(filter_frame, text="开始日期:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self._data_start_date_var = tk.StringVar()
        self._data_start_date_combo = ttk.Combobox(filter_frame, textvariable=self._data_start_date_var,
                                                    width=12, state="readonly", font=("Microsoft YaHei", 10))
        self._data_start_date_combo.pack(side=tk.LEFT, padx=(4, 8))

        tk.Label(filter_frame, text="结束日期:", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self._data_end_date_var = tk.StringVar()
        self._data_end_date_combo = ttk.Combobox(filter_frame, textvariable=self._data_end_date_var,
                                                  width=12, state="readonly", font=("Microsoft YaHei", 10))
        self._data_end_date_combo.pack(side=tk.LEFT, padx=(4, 8))

        self._data_start_date_combo.bind("<<ComboboxSelected>>", self._on_data_date_change)
        self._data_end_date_combo.bind("<<ComboboxSelected>>", self._on_data_date_change)

        ttk.Button(filter_frame, text="📅 本月", command=self._set_data_date_this_month,
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
        ttk.Button(btn_frame, text="📥 导入CSV", command=self._import_csv,
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

        columns = ("time", "total_time", "total_steps", "total_tps", "scramble", "strength", "weakness")
        self._data_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                        selectmode="extended", height=20)

        self._data_tree.heading("time", text="还原时间 ▲", command=lambda: self._sort_data_by_column("time"))
        self._data_tree.heading("total_time", text="用时(s) ▲", command=lambda: self._sort_data_by_column("total_time"))
        self._data_tree.heading("total_steps", text="步数 ▲", command=lambda: self._sort_data_by_column("total_steps"))
        self._data_tree.heading("total_tps", text="TPS ▲", command=lambda: self._sort_data_by_column("total_tps"))
        self._data_tree.heading("scramble", text="打乱公式")
        self._data_tree.heading("strength", text="优点")
        self._data_tree.heading("weakness", text="缺点")

        self._data_tree.column("time", width=180, anchor="center", minwidth=140)
        self._data_tree.column("total_time", width=80, anchor="center", minwidth=60)
        self._data_tree.column("total_steps", width=60, anchor="center", minwidth=50)
        self._data_tree.column("total_tps", width=60, anchor="center", minwidth=50)
        self._data_tree.column("scramble", width=300, anchor="w", minwidth=100)
        self._data_tree.column("strength", width=260, anchor="w", minwidth=80)
        self._data_tree.column("weakness", width=260, anchor="w", minwidth=80)

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

        self._data_tree.tag_configure("analyzed", foreground="#2563eb")

        self._data_context_menu = tk.Menu(self.root, tearoff=0)
        self._data_context_menu.add_command(label="🗑 删除选中记录", command=self._delete_selected_records)

        self._data_records = []
        self._data_sort_column = "time"
        self._data_sort_ascending = True

        self._refresh_data_tab()

    def _refresh_data_tab(self):
        dates = memory_db.get_available_dates()
        today = datetime.now().strftime("%Y-%m-%d")
        self._data_start_date_combo['values'] = dates
        self._data_end_date_combo['values'] = dates
        # 默认显示今天到今天
        if dates:
            if today in dates:
                self._data_start_date_var.set(today)
                self._data_end_date_var.set(today)
            else:
                # dates是降序，dates[0]是最新的日期
                self._data_start_date_var.set(dates[0])
                self._data_end_date_var.set(dates[0])
        else:
            self._data_start_date_var.set("")
            self._data_end_date_var.set("")
        self._load_data_records()

    def _set_data_date_this_month(self):
        today = datetime.now().strftime("%Y-%m-%d")
        start_of_month = today[:8] + "01"
        # 重新从数据库获取日期列表，保持原有排序
        dates = memory_db.get_available_dates()
        # 确保日期在列表中
        if start_of_month not in dates:
            dates.insert(0, start_of_month)
        if today not in dates:
            dates.insert(0, today)
        # 保持降序排列
        dates = sorted(set(dates), reverse=True)
        self._data_start_date_combo['values'] = dates
        self._data_end_date_combo['values'] = dates
        self._data_start_date_var.set(start_of_month)
        self._data_end_date_var.set(today)
        self._load_data_records()

    def _on_data_date_change(self, event=None):
        start = self._data_start_date_var.get()
        end = self._data_end_date_var.get()
        if start and end:
            try:
                from datetime import datetime as dt
                s = dt.strptime(start, "%Y-%m-%d")
                e = dt.strptime(end, "%Y-%m-%d")
                if s > e:
                    messagebox.showwarning("提示", "开始日期不能晚于结束日期")
                    return
                delta = (e - s).days
                if delta > 93:
                    messagebox.showwarning("提示", "日期范围不能超过3个月（93天）")
                    return
            except ValueError:
                pass
        self._load_data_records()

    def _load_data_records(self):
        start_date = self._data_start_date_var.get()
        end_date = self._data_end_date_var.get()
        if start_date and end_date:
            records = memory_db.get_records_by_date(start_date=start_date, end_date=end_date)
        else:
            records = memory_db.get_records_by_date()

        # 为缺少total_steps/total_tps的记录回填
        for rec in records:
            if rec.get("total_steps", 0) == 0 and rec.get("solution"):
                from move_utils import parse_timed_moves
                try:
                    timed = parse_timed_moves(rec["solution"])
                    rec["total_steps"] = len(timed)
                    total_time = rec.get("total_time", 0)
                    rec["total_tps"] = rec["total_steps"] / total_time if total_time > 0 else 0
                except Exception:
                    pass

        if self._data_sort_column == "total_time":
            records.sort(key=lambda r: r["total_time"], reverse=not self._data_sort_ascending)
        elif self._data_sort_column == "total_steps":
            records.sort(key=lambda r: r.get("total_steps", 0), reverse=not self._data_sort_ascending)
        elif self._data_sort_column == "total_tps":
            records.sort(key=lambda r: r.get("total_tps", 0), reverse=not self._data_sort_ascending)
        else:
            records.sort(key=lambda r: r["date"], reverse=not self._data_sort_ascending)

        self._data_records = records

        for item in self._data_tree.get_children():
            self._data_tree.delete(item)

        for rec in records:
            time_str = rec["date"] if rec["date"] else ""
            s_tags = rec.get("strength_tags", "") or ""
            w_tags = rec.get("weakness_tags", "") or ""
            is_analyzed = rec.get("analyzed", 0)
            tag_name = "analyzed" if is_analyzed else ""
            total_steps = rec.get("total_steps", 0)
            total_tps = rec.get("total_tps", 0)
            self._data_tree.insert("", tk.END, iid=str(rec["id"]),
                                    values=(time_str, f"{rec['total_time']:.2f}",
                                            total_steps, f"{total_tps:.1f}",
                                            rec["scramble"], s_tags, w_tags),
                                    tags=(tag_name,))

        count = len(records)
        self._data_count_label.config(text=f"共 {count} 条记录")

        self._update_memory_count()

        # 自适应列宽
        self._auto_size_data_columns()

    def _auto_size_data_columns(self):
        """根据内容自动调整数据表格列宽"""
        if not hasattr(self, '_data_tree'):
            return
        # 用于测量文字宽度的字体
        col_font = ("Microsoft YaHei", 9)
        header_font = ("Microsoft YaHei", 9, "bold")
        pad = 20  # 左右内边距

        col_keys = ["time", "total_time", "total_steps", "total_tps", "scramble", "strength", "weakness"]
        headings = {"time": "还原时间", "total_time": "用时(s)",
                    "total_steps": "步数", "total_tps": "TPS",
                    "scramble": "打乱公式", "strength": "优点", "weakness": "缺点"}

        max_widths = {}
        for key in col_keys:
            # 标题宽度
            hw = self._measure_text_width(header_font, headings.get(key, key)) + pad + 20
            max_widths[key] = hw

        # 遍历所有行内容取最大宽度
        for item_id in self._data_tree.get_children():
            values = self._data_tree.item(item_id, "values")
            for i, key in enumerate(col_keys):
                if i < len(values):
                    val = str(values[i])
                    w = self._measure_text_width(col_font, val) + pad
                    if w > max_widths[key]:
                        max_widths[key] = w

        # 设置列宽，scramble列限制最大宽度
        for key in col_keys:
            max_w = max_widths[key]
            if key == "scramble":
                max_w = min(max_w, 600)
            self._data_tree.column(key, width=max_w)

    def _measure_text_width(self, font, text: str) -> int:
        """测量文本在指定字体下的像素宽度"""
        try:
            from tkinter import font as tkfont
            f = tkfont.Font(family=font[0], size=font[1],
                            weight="bold" if len(font) > 2 and font[2] == "bold" else "normal")
            return f.measure(text)
        except Exception:
            # 回退：按字符数估算
            return len(text) * 10

    def _wrap_tags(self, tags_str: str, per_line: int = 2) -> str:
        """将逗号分隔的标签字符串按每per_line个换行显示"""
        if not tags_str:
            return ""
        parts = [t.strip() for t in tags_str.split(",") if t.strip()]
        if not parts:
            return ""
        lines = []
        for i in range(0, len(parts), per_line):
            lines.append(",".join(parts[i:i + per_line]))
        return "\n".join(lines)

    def _sort_data_by_column(self, col: str):
        if self._data_sort_column == col:
            self._data_sort_ascending = not self._data_sort_ascending
        else:
            self._data_sort_column = col
            self._data_sort_ascending = True

        arrow = "▲" if self._data_sort_ascending else "▼"
        # 重置所有排序列标题
        self._data_tree.heading("time", text=f"还原时间 {arrow}" if col == "time" else "还原时间",
                                command=lambda: self._sort_data_by_column("time"))
        self._data_tree.heading("total_time", text=f"用时(s) {arrow}" if col == "total_time" else "用时(s)",
                                command=lambda: self._sort_data_by_column("total_time"))
        self._data_tree.heading("total_steps", text=f"步数 {arrow}" if col == "total_steps" else "步数",
                                command=lambda: self._sort_data_by_column("total_steps"))
        self._data_tree.heading("total_tps", text=f"TPS {arrow}" if col == "total_tps" else "TPS",
                                command=lambda: self._sort_data_by_column("total_tps"))

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

        dialog.geometry("800x650")
        self._center_window(dialog)

        main_frame = tk.Frame(dialog, bg=THEME["card_bg"], padx=16, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        info_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        info_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(info_frame, text=f"📅 {detail['date']}", font=("Microsoft YaHei", 10),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(info_frame, text=f"⏱ 总用时: {detail['total_time']:.2f}s", font=("Microsoft YaHei", 10, "bold"),
                 bg=THEME["card_bg"], fg=THEME["accent"]).pack(side=tk.LEFT, padx=(0, 16))
        # 从phase_stats或solution计算步数和TPS
        total_steps = detail.get("total_steps", 0)
        total_tps = detail.get("total_tps", 0)
        if total_steps == 0 and detail.get("solution"):
            from move_utils import parse_timed_moves
            try:
                timed = parse_timed_moves(detail["solution"])
                total_steps = len(timed)
                total_time = detail.get("total_time", 0)
                total_tps = total_steps / total_time if total_time > 0 else 0
            except Exception:
                pass
        tk.Label(info_frame, text=f"🔢 步数: {total_steps}", font=("Microsoft YaHei", 10, "bold"),
                 bg=THEME["card_bg"], fg=THEME["accent"]).pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(info_frame, text=f"⚡ TPS: {total_tps:.1f}", font=("Microsoft YaHei", 10, "bold"),
                 bg=THEME["card_bg"], fg=THEME["accent"]).pack(side=tk.LEFT)

        # 优缺点标签显示
        s_tags = detail.get("strength_tags", "") or ""
        w_tags = detail.get("weakness_tags", "") or ""
        if s_tags or w_tags:
            tags_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
            tags_frame.pack(fill=tk.X, pady=(0, 4))
            if s_tags:
                s_parts = [t.strip() for t in s_tags.split(",") if t.strip()]
                tk.Label(tags_frame, text="优点:", font=("Microsoft YaHei", 9, "bold"),
                         bg=THEME["card_bg"], fg="#27ae60").pack(side=tk.LEFT, padx=(0, 4))
                for t in s_parts:
                    tk.Label(tags_frame, text=t, font=("Microsoft YaHei", 9),
                             bg="#e8f8f0", fg="#27ae60", padx=4, pady=1,
                             relief="groove", borderwidth=1).pack(side=tk.LEFT, padx=(0, 4))
            if w_tags:
                w_parts = [t.strip() for t in w_tags.split(",") if t.strip()]
                if s_tags:
                    tk.Label(tags_frame, text="  ", bg=THEME["card_bg"]).pack(side=tk.LEFT)
                tk.Label(tags_frame, text="缺点:", font=("Microsoft YaHei", 9, "bold"),
                         bg=THEME["card_bg"], fg="#e74c3c").pack(side=tk.LEFT, padx=(0, 4))
                for t in w_parts:
                    tk.Label(tags_frame, text=t, font=("Microsoft YaHei", 9),
                             bg="#fdecea", fg="#e74c3c", padx=4, pady=1,
                             relief="groove", borderwidth=1).pack(side=tk.LEFT, padx=(0, 4))

        scramble_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        scramble_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(scramble_frame, text="打乱公式:", font=("Microsoft YaHei", 11, "bold"),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w")
        tk.Label(scramble_frame, text=detail["scramble"], font=("Consolas", 12),
                 bg=THEME["card_bg"], fg=THEME["fg"], wraplength=650, justify="left").pack(anchor="w", padx=(12, 0))

        # 解法复盘：使用processed_solve（已转换坐标系、已合并步骤）
        from analyzer import CFOPAnalyzer, PHASE_ORDER
        from config import PHASE_COLORS, PHASE_LABELS as CFG_PHASE_LABELS
        from analyzer import COLOR_NAMES

        processed_solve = detail.get("processed_solve", "")
        # 如果没有processed_solve，尝试从原始数据重新分析生成
        parsed_phases = None
        if processed_solve:
            try:
                parsed_phases = CFOPAnalyzer.parse_processed_solve(processed_solve)
            except Exception:
                parsed_phases = None
        if not parsed_phases:
            try:
                _, replay_analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(detail["scramble"], detail["solution"])
                parsed_phases = CFOPAnalyzer.parse_processed_solve(replay_analyzer.generate_processed_solve())
            except Exception:
                parsed_phases = None

        solution_frame = tk.Frame(main_frame, bg=THEME["card_bg"])
        solution_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(solution_frame, text="解法复盘:", font=("Microsoft YaHei", 11, "bold"),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w")

        if parsed_phases:
            # 朝向信息：优先使用processed_solve中的底色/前色
            bc = parsed_phases.get("bottom_color", "")
            fc = parsed_phases.get("front_color", "")
            bottom_name = COLOR_NAMES.get(bc, detail.get("bottom_color", "白")) if bc else detail.get("bottom_color", "白")
            front_name = COLOR_NAMES.get(fc, "") if fc else ""
            orient_frame = tk.Frame(solution_frame, bg=THEME["card_bg"])
            orient_frame.pack(anchor="w", padx=(12, 0), pady=(2, 4))
            if front_name:
                tk.Label(orient_frame, text=f"底色：{bottom_name}  前色：{front_name}",
                         font=("Microsoft YaHei", 10), bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT, padx=(0, 12))
            else:
                tk.Label(orient_frame, text=f"底色：{bottom_name}",
                         font=("Microsoft YaHei", 10), bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT, padx=(0, 12))

            # 重新计算OLL/PLL编码并显示
            oll_case = ""
            pll_case = ""
            try:
                _scramble = detail.get("scramble", "")
                _solution = detail.get("solution", "")
                if _scramble and _solution:
                    _, _analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(_scramble, _solution)
                    oll_case, pll_case = _analyzer.identify_oll_pll()
                    # 回写数据库
                    if oll_case or pll_case:
                        memory_db.update_oll_pll_case(detail["id"], oll_case, pll_case)
            except Exception as e:
                if log:
                    log.warning(f"[GUI] OLL/PLL识别失败(id={detail.get('id', '?')}): {e}")
            if oll_case:
                oll_text = "跳O" if oll_case == "skip" else f"OLL {oll_case}"
                tk.Label(orient_frame, text=oll_text, font=("Microsoft YaHei", 10),
                         bg="#e8f0fe", fg="#1565c0", padx=8, pady=2,
                         relief="groove", borderwidth=1).pack(side=tk.LEFT, padx=(0, 8))
            if pll_case:
                pll_text = "跳P" if pll_case == "skip" else f"PLL {pll_case}"
                tk.Label(orient_frame, text=pll_text, font=("Microsoft YaHei", 10),
                         bg="#fef0e8", fg="#c62828", padx=8, pady=2,
                         relief="groove", borderwidth=1).pack(side=tk.LEFT, padx=(0, 8))

            phase_data = parsed_phases.get("phases", parsed_phases)

            # 步骤颜色映射
            face_colors = {
                'U': "#0984e3", "U'": "#74b9ff", "U2": "#0984e3",
                'D': "#00b894", "D'": "#55efc4", "D2": "#00b894",
                'F': "#e17055", "F'": "#fab1a0", "F2": "#e17055",
                'R': "#fd79a8", "R'": "#fdcb6e", "R2": "#fd79a8",
                'B': "#6c5ce7", "B'": "#a29bfe", "B2": "#6c5ce7",
                'L': "#fdcb6e", "L'": "#ffeaa7", "L2": "#fdcb6e",
                'M': "#e84393", "M'": "#fd79a8", "M2": "#e84393",
                'E': "#00cec9", "E'": "#81ecec", "E2": "#00cec9",
                'S': "#d63031", "S'": "#ff7675", "S2": "#d63031",
            }

            min_block_width = 12
            y_rotation_width = 16

            bar_height = 18
            label_height = 16
            row_height = bar_height + label_height + 10
            margin_left = 50
            margin_right = 20

            # 从parsed_phases计算每步时间间隔
            phase_step_data = {}
            for phase in PHASE_ORDER:
                pd = phase_data.get(phase)
                if not pd or not pd.get("moves"):
                    continue
                moves = pd["moves"]  # [(move, ts_ms), ...]
                y_rotation = pd.get("y_rotation", "")
                # 计算每步时间间隔
                step_times = []
                for i, (move, ts) in enumerate(moves):
                    if i + 1 < len(moves):
                        step_times.append(moves[i + 1][1] - ts)
                    else:
                        # 最后一步：用该阶段其他步的平均时间估算
                        if len(step_times) > 0:
                            step_times.append(sum(step_times) / len(step_times))
                        else:
                            step_times.append(100)
                # 步骤已经是合并后的（processed_solve中已合并）
                merged_moves = [m for m, _ in moves]
                merged_times = step_times
                total_ms = sum(merged_times)
                phase_step_data[phase] = (merged_moves, y_rotation, merged_times, total_ms)

            # 计算最短步骤时间
            min_step_time = float('inf')
            for phase in PHASE_ORDER:
                if phase not in phase_step_data:
                    continue
                _, _, merged_times, _ = phase_step_data[phase]
                for t in merged_times:
                    if t > 0 and t < min_step_time:
                        min_step_time = t
            if min_step_time == float('inf'):
                min_step_time = 100

            # 计算每行自然宽度（按时间比例，最小宽度保证）
            time_to_width_ratio = min_block_width / min_step_time
            row_natural_widths = {}
            for phase in PHASE_ORDER:
                if phase not in phase_step_data:
                    continue
                _, y_rotation, merged_times, _ = phase_step_data[phase]
                natural_w = sum(max(min_block_width, t * time_to_width_ratio) for t in merged_times)
                if y_rotation:
                    natural_w += y_rotation_width
                row_natural_widths[phase] = natural_w

            max_natural_width = max(row_natural_widths.values()) if row_natural_widths else 0

            total_rows = sum(1 for p in PHASE_ORDER if p in phase_step_data)
            canvas_height = total_rows * row_height + 10

            timeline_frame = tk.Frame(solution_frame, bg=THEME["card_bg"])
            timeline_frame.pack(fill=tk.BOTH, expand=True, padx=(12, 0), pady=(2, 0))

            timeline_canvas = tk.Canvas(timeline_frame, height=canvas_height,
                                        bg=THEME["card_bg"], highlightthickness=0)
            timeline_canvas.pack(fill=tk.BOTH, expand=True)

            # 阶段详情tooltip
            tooltip_win = [None]
            tooltip_text = [None]

            def _show_tooltip(event, text):
                if tooltip_text[0] == text and tooltip_win[0]:
                    # 内容不变，只更新位置
                    tooltip_win[0].wm_geometry(f"+{event.x_root + 12}+{event.y_root + 8}")
                    return
                _hide_tooltip()
                tw = tk.Toplevel(timeline_canvas)
                tw.wm_overrideredirect(True)
                tw.wm_attributes("-topmost", True)
                tw.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 8}")
                lbl = tk.Label(tw, text=text, font=("Microsoft YaHei", 9),
                               bg="#ffffdd", fg="#333333", relief="solid", borderwidth=1,
                               padx=6, pady=4, justify="left")
                lbl.pack()
                tooltip_win[0] = tw
                tooltip_text[0] = text

            def _hide_tooltip():
                if tooltip_win[0]:
                    tooltip_win[0].destroy()
                    tooltip_win[0] = None
                tooltip_text[0] = None

            # 记录区域用于tooltip：色块区域和阶段标签区域
            step_rects = []   # [(x1, x2, y1, y2, tooltip_text), ...]
            label_rects = []  # [(x1, x2, y1, y2, tooltip_text), ...]

            def _on_timeline_canvas_configure(event):
                available_width = event.width - margin_left - margin_right
                if available_width <= 0:
                    return
                # 始终按比例缩放填满可用宽度，但每个步骤最小宽度保证
                scale_ratio = available_width / max_natural_width if max_natural_width > 0 else 1

                # 修正：最小宽度约束可能导致实际总宽度超出可用宽度
                if scale_ratio < 1:
                    max_actual_width = 0
                    for phase in PHASE_ORDER:
                        if phase not in phase_step_data:
                            continue
                        _, y_rotation, merged_times, _ = phase_step_data[phase]
                        actual_w = sum(max(min_block_width, max(min_block_width, t * time_to_width_ratio) * scale_ratio) for t in merged_times)
                        if y_rotation:
                            actual_w += y_rotation_width
                        max_actual_width = max(max_actual_width, actual_w)
                    if max_actual_width > available_width and max_actual_width > 0:
                        scale_ratio *= available_width / max_actual_width

                timeline_canvas.delete("all")
                step_rects.clear()
                label_rects.clear()

                row_idx = 0
                for phase in PHASE_ORDER:
                    if phase not in phase_step_data:
                        continue
                    merged_moves, y_rotation, merged_times, total_ms = phase_step_data[phase]
                    phase_color = PHASE_COLORS.get(phase, "#b2bec3")
                    phase_label = CFG_PHASE_LABELS.get(phase, phase)

                    y_base = row_idx * row_height + 5

                    # 阶段标签
                    timeline_canvas.create_text(margin_left - 6, y_base + label_height + bar_height / 2,
                                                text=phase_label, anchor=tk.E,
                                                font=("Microsoft YaHei", 9, "bold"), fill=phase_color)
                    # 阶段标签区域（左侧）
                    label_rects.append((0, margin_left, y_base, y_base + row_height,
                                        _build_phase_tooltip(phase, phase_label)))

                    # 绘制转体步骤（透明色块，固定宽度）
                    x = margin_left
                    if y_rotation:
                        rx_end = x + y_rotation_width
                        timeline_canvas.create_rectangle(x, y_base + label_height, rx_end,
                                                         y_base + label_height + bar_height,
                                                         fill="", outline=THEME["border"], width=1, dash=(2, 2))
                        timeline_canvas.create_text((x + rx_end) / 2, y_base + 6, text=y_rotation,
                                                    font=("Consolas", 8, "bold"), fill=THEME["fg"])
                        # 转体色块tooltip
                        step_rects.append((x, rx_end, y_base + label_height,
                                           y_base + label_height + bar_height,
                                           f"{y_rotation}"))
                        x = rx_end

                    # 绘制每个步骤色块
                    for i, move in enumerate(merged_moves):
                        st_ms = merged_times[i]
                        natural_w = max(min_block_width, st_ms * time_to_width_ratio)
                        block_width = max(min_block_width, natural_w * scale_ratio)

                        color = face_colors.get(move, face_colors.get(move[0], "#b2bec3"))

                        x_end = x + block_width

                        timeline_canvas.create_rectangle(x, y_base + label_height, x_end,
                                                         y_base + label_height + bar_height,
                                                         fill=color, outline="", width=0)

                        mid_x = (x + x_end) / 2
                        timeline_canvas.create_text(mid_x, y_base + 6, text=move,
                                                    font=("Consolas", 11, "bold"), fill=color)

                        # 色块tooltip：显示步骤时间
                        step_time_s = st_ms / 1000.0
                        step_rects.append((x, x_end, y_base + label_height,
                                           y_base + label_height + bar_height,
                                           f"{move}  {step_time_s:.3f}s"))

                        x = x_end

                    row_idx += 1

            def _build_phase_tooltip(phase, phase_label):
                ps = detail["phase_stats"].get(phase, {})
                if ps:
                    return (
                        f"{phase_label}\n"
                        f"步数: {ps.get('steps', 0)}\n"
                        f"用时: {ps.get('time', 0):.2f}s\n"
                        f"观察: {ps.get('observation_time', 0):.2f}s\n"
                        f"卡顿: {ps.get('stutter_count', 0)}\n"
                        f"废步: {ps.get('wasted_moves', 0)}\n"
                        f"TPS: {ps.get('tps', 0):.1f}"
                    )
                return f"{phase_label}\n(无阶段数据)"

            timeline_canvas.bind("<Configure>", _on_timeline_canvas_configure)

            def _on_canvas_motion(event):
                x, y = event.x, event.y
                # 先检查阶段标签区域
                for rx1, rx2, ry1, ry2, text in label_rects:
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        _show_tooltip(event, text)
                        return
                # 再检查色块区域
                for rx1, rx2, ry1, ry2, text in step_rects:
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        _show_tooltip(event, text)
                        return
                _hide_tooltip()

            def _on_canvas_leave(event):
                _hide_tooltip()

            timeline_canvas.bind("<Motion>", _on_canvas_motion)
            timeline_canvas.bind("<Leave>", _on_canvas_leave)
        else:
            # 分析失败时显示原始solution
            sol_text = tk.Text(solution_frame, font=("Consolas", 11), height=4, wrap=tk.WORD,
                               bg=THEME["input_bg"], fg=THEME["fg"], relief="flat", borderwidth=0)
            sol_text.insert("1.0", detail.get("solution", ""))
            sol_text.config(state="disabled")
            sol_text.pack(fill=tk.X, padx=(12, 0))

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

    def _fill_multi_analysis(self, records: list):
        if self.analysis_mode_var.get() != '多组':
            self.analysis_mode_var.set('多组')
            # 不调用 _on_mode_change()，因为它会加载之前保存的数据
            # 直接创建多组输入UI，不加载旧数据
            self._save_single_data()
            self._create_multi_input_ui(skip_default_rows=True)
        else:
            if hasattr(self, 'multi_inputs') and self.multi_inputs:
                for inp in self.multi_inputs:
                    for key in ('num_label', 'scramble', 'solution', 'del_btn'):
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

        # 数据库更新
        db_header = ttk.Frame(tab)
        db_header.pack(fill=tk.X, pady=(0, 2), padx=8)
        ttk.Label(db_header, text="  💾 数据库维护", font=("Microsoft YaHei", 11, "bold"),
                  foreground=THEME["accent"], background=THEME["bg"]).pack(side=tk.LEFT)

        db_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=16, pady=16,
                            highlightthickness=1, highlightbackground=THEME["border"])
        db_frame.pack(fill=tk.X, padx=8, pady=(0, 12))

        db_update_frame = tk.Frame(db_frame, bg=THEME["card_bg"])
        db_update_frame.pack(fill=tk.X)
        ttk.Button(db_update_frame, text="🔄 更新数据库", command=self._on_recalculate_db,
                   style="Accent.TButton").pack(side=tk.LEFT)
        tk.Label(db_update_frame, text="重新计算所有记录的分析结果（底色、步数、TPS、解法复盘等）",
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
3. 配置API Key 并选择合适的模型。
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

【功能说明】

🏠 首页
• 水平统计：展示PB、平均用时、TPS、各阶段详细统计（步数/用时/观察/卡顿/废步/TPS及标准差），以及优点和缺点TOP3标签
• 智能训练：今日训练总结，包含统计文本、时间趋势折线图、时间分布直方图，支持AI总结和Ao12分析

🔬 深度分析
• 单组/多组模式：单组分析单次还原，多组分析最多20组还原并计算平均和波动度
• 底色自动识别：无需手动选择底色，软件自动检测
• 解法复盘：Canvas色块时间轴，按CFOP阶段分行显示，步骤宽度与时间成正比，鼠标悬停查看步骤详情和阶段统计
• AI流式输出：实时显示AI推理过程和分析结果，支持Markdown格式渲染
• 智能粘贴：开启后自动监控剪贴板，识别csTimer数据并填入输入框，支持去重检测

📂 数据管理
• 数据列表：展示还原记录，支持按时间/用时/步数/TPS排序，点击列标题切换升降序
• 日期筛选：按日期范围筛选记录，支持"本月"快捷按钮
• 多选分析：支持Ctrl/Shift多选记录，点击"分析选中项"直接跳转深度分析
• 还原详情：双击记录查看详情，含解法复盘时间轴和优缺点标签
• 数据导入：支持csTimer导出文件和CSV文件导入，带进度弹窗
• 数据导出：导出为CSV文件

⚙️ 设置
• API Key配置：密钥加密存储，安全可靠
• 模型选择：从API获取可用模型列表
• 智能粘贴开关：控制剪贴板自动监控
• 记忆模式开关：记录分析历史，提供对比参考和训练建议
• 数据库更新：重新计算所有记录的分析结果

👤 用户管理
• 多用户支持：创建、编辑、删除用户，支持自定义头像
• 成绩异常检测：分析时自动检测成绩偏差，偏差过大时提示确认或切换用户

【交流反馈】
• 交流QQ群：322267527"""

        main_frame = tk.Frame(tab, bg=THEME["card_bg"], padx=24, pady=20,
                               highlightthickness=1, highlightbackground=THEME["border"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        title_label = tk.Label(main_frame, text="AI_CFOP 使用说明",
                              font=("Microsoft YaHei", 16, "bold"),
                              fg=THEME["accent"], bg=THEME["card_bg"])
        title_label.pack(pady=(0, 16))

        text_widget = tk.Text(main_frame, width=60, height=25,
                              font=("Microsoft YaHei", 10),
                              bg=THEME["card_bg"],
                              fg=THEME["fg"],
                              relief="flat", borderwidth=0,
                              wrap=tk.WORD, highlightthickness=0)
        help_scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=help_scrollbar.set)
        help_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
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

        tk.Label(input_frame, text="还原步骤 (回顾):", bg=THEME["card_bg"],
                 fg=THEME["fg"], font=("Microsoft YaHei", 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.solution_text = tk.Entry(input_frame, width=60,
                                       font=("Consolas", 9), bg=THEME["input_bg"],
                                       fg=THEME["fg"], relief="flat", borderwidth=0,
                                       highlightthickness=1, highlightbackground=THEME["border"],
                                       highlightcolor=THEME["accent"])
        self.solution_text.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(6, 0))

        input_frame.columnconfigure(1, weight=1)

        self.mode_desc_label.config(text="单组模式：分析单次还原过程（底色自动识别）")
    
    def _create_multi_input_ui(self, skip_default_rows=False):
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
        self.multi_rows_frame.columnconfigure(2, weight=1)
        
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
        tk.Label(self.multi_rows_frame, text="还原步骤", bg=THEME["card_bg"], fg=THEME["fg"],
                 font=("Microsoft YaHei", 8, "bold"), anchor="w").grid(row=0, column=2, sticky="ew", padx=(2, 0))
        tk.Label(self.multi_rows_frame, text="", bg=THEME["card_bg"],
                 font=("Microsoft YaHei", 8), width=2).grid(row=0, column=3, padx=(1, 0))
        
        btn_frame = tk.Frame(outer_frame, bg=THEME["card_bg"], pady=8)
        btn_frame.pack(fill=tk.X)
        
        add_btn = ttk.Button(btn_frame, text="➕ 添加一组", command=self._add_multi_row, style="Accent.TButton")
        add_btn.pack(side=tk.LEFT)
        
        self.multi_count_label = tk.Label(btn_frame, text="", bg=THEME["card_bg"],
                                           fg=THEME["fg"], font=("Microsoft YaHei", 9))
        self.multi_count_label.pack(side=tk.LEFT, padx=(16, 0))
        
        if not skip_default_rows:
            for _ in range(5):
                self._add_multi_row()

        self.mode_desc_label.config(text="多组模式：分析多组还原，计算平均、波动度等（底色自动识别）")

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

        solution_entry = tk.Entry(self.multi_rows_frame, font=("Consolas", 8),
                                  bg=THEME["input_bg"], fg=THEME["fg"],
                                  relief="flat", borderwidth=0,
                                  highlightthickness=1, highlightbackground=THEME["border"],
                                  highlightcolor=THEME["accent"])
        solution_entry.grid(row=idx + 1, column=2, sticky="ew", padx=(2, 0))

        inp = {
            'num_label': num_label,
            'scramble': scramble_entry,
            'solution': solution_entry
        }
        
        del_btn = tk.Button(self.multi_rows_frame, text="✕", width=2,
                            font=("Microsoft YaHei", 7), fg="#fff", bg=THEME["danger"],
                            activebackground="#d63031", activeforeground="#fff",
                            relief="flat", borderwidth=0, cursor="hand2",
                            command=lambda: self._remove_multi_row_by_inp(inp))
        del_btn.grid(row=idx + 1, column=3, padx=(2, 0))
        inp['del_btn'] = del_btn

        if hasattr(self, 'multi_mousewheel_func'):
            scramble_entry.bind("<MouseWheel>", self.multi_mousewheel_func)
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
            for key in ('num_label', 'scramble', 'solution', 'del_btn'):
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
            inp['solution'].grid(row=i + 1, column=2, sticky="ew", padx=(2, 0))
            inp['del_btn'].grid(row=i + 1, column=3, padx=(2, 0))
    
    def _update_multi_count(self):
        count = len(self.multi_inputs) if hasattr(self, 'multi_inputs') else 0
        self.multi_count_label.config(text=f"当前 {count} 组")

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
            self._load_single_data()
        else:
            self._create_multi_input_ui()
            self._load_multi_data()
    
    def _save_single_data(self):
        try:
            config = load_config()
            config["scramble"] = self.scramble_entry.get().strip()
            config["solution"] = self.solution_text.get().strip()
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
            self._load_multi_data()
        else:
            self._create_single_input_ui()
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

        for w in self.replay_canvas_container.winfo_children():
            w.destroy()
        self.result_text.delete(1.0, tk.END)
        self._solution_summary = ""
        if hasattr(self, '_replay_analyzers'):
            self._replay_analyzers = []

    def _draw_replay_timeline(self):
        """在深度分析的解法复盘区域绘制色块时间轴"""
        from analyzer import CFOPAnalyzer, PHASE_ORDER, COLOR_NAMES
        from config import PHASE_COLORS, PHASE_LABELS as CFG_PHASE_LABELS

        # 清空容器
        for w in self.replay_canvas_container.winfo_children():
            w.destroy()

        if not self._replay_analyzers:
            return

        face_colors = {
            'U': "#0984e3", "U'": "#74b9ff", "U2": "#0984e3",
            'D': "#00b894", "D'": "#55efc4", "D2": "#00b894",
            'F': "#e17055", "F'": "#fab1a0", "F2": "#e17055",
            'R': "#fd79a8", "R'": "#fdcb6e", "R2": "#fd79a8",
            'B': "#6c5ce7", "B'": "#a29bfe", "B2": "#6c5ce7",
            'L': "#fdcb6e", "L'": "#ffeaa7", "L2": "#fdcb6e",
            'M': "#e84393", "M'": "#fd79a8", "M2": "#e84393",
            'E': "#00cec9", "E'": "#81ecec", "E2": "#00cec9",
            'S': "#d63031", "S'": "#ff7675", "S2": "#d63031",
        }

        min_block_width = 12
        y_rotation_width = 16
        bar_height = 18
        label_height = 16
        row_height = bar_height + label_height + 10
        margin_left = 50
        margin_right = 20

        # 使用ScrolledCanvas支持多组时滚动
        outer_frame = tk.Frame(self.replay_canvas_container, bg=THEME["card_bg"])
        outer_frame.pack(fill=tk.BOTH, expand=True)

        # 先计算总高度
        total_canvas_height = 0
        for group_idx, (analyzer, scramble, bottom_name) in enumerate(self._replay_analyzers):
            processed = analyzer.generate_processed_solve()
            parsed = CFOPAnalyzer.parse_processed_solve(processed)
            phase_data = parsed.get("phases", parsed)
            num_rows = sum(1 for p in PHASE_ORDER if phase_data.get(p) and phase_data[p].get("moves"))
            group_header_height = 40 if len(self._replay_analyzers) > 1 else 25
            total_canvas_height += num_rows * row_height + 10 + group_header_height

        scroll_canvas = tk.Canvas(outer_frame, bg=THEME["card_bg"], highlightthickness=0,
                                  height=min(total_canvas_height, 180))
        scrollbar = ttk.Scrollbar(outer_frame, orient=tk.VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner_frame = tk.Frame(scroll_canvas, bg=THEME["card_bg"])
        scroll_canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # 为每组analyzer绘制时间轴
        for group_idx, (analyzer, scramble, bottom_name) in enumerate(self._replay_analyzers):
            group_frame = tk.Frame(inner_frame, bg=THEME["card_bg"])
            group_frame.pack(fill=tk.X, padx=(0, 8), pady=(4, 8))

            # 显示完整信息：打乱、用时、步数、TPS、底色、前色
            front_desc = get_orientation_desc(analyzer.top_color, analyzer.front_color)
            total_time = analyzer.get_total_time()
            stats = analyzer.get_phase_stats()
            total_steps = sum(ps.get("steps", 0) for ps in stats.values())
            total_tps = total_steps / total_time if total_time > 0 else 0

            if len(self._replay_analyzers) > 1:
                header_line1 = f"第 {group_idx + 1} 组"
            else:
                header_line1 = ""
            header_line1 += f"  打乱: {scramble}" if scramble else ""
            if header_line1:
                tk.Label(group_frame, text=header_line1, font=("Consolas", 10),
                         bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 1))

            header_line2 = f"用时: {total_time:.2f}s  步数: {total_steps}  TPS: {total_tps:.1f}  底色: {bottom_name}  前色: {front_desc}"
            tk.Label(group_frame, text=header_line2, font=("Microsoft YaHei", 9),
                     bg=THEME["card_bg"], fg=THEME["fg"]).pack(anchor="w", pady=(0, 2))

            # 解析processed_solve
            processed = analyzer.generate_processed_solve()
            parsed = CFOPAnalyzer.parse_processed_solve(processed)
            phase_data = parsed.get("phases", parsed)

            # 计算每步时间间隔
            phase_step_data = {}
            for phase in PHASE_ORDER:
                pd = phase_data.get(phase)
                if not pd or not pd.get("moves"):
                    continue
                moves = pd["moves"]
                y_rotation = pd.get("y_rotation", "")
                step_times = []
                for i, (move, ts) in enumerate(moves):
                    if i + 1 < len(moves):
                        step_times.append(moves[i + 1][1] - ts)
                    else:
                        if len(step_times) > 0:
                            step_times.append(sum(step_times) / len(step_times))
                        else:
                            step_times.append(100)
                merged_moves = [m for m, _ in moves]
                merged_times = step_times
                total_ms = sum(merged_times)
                phase_step_data[phase] = (merged_moves, y_rotation, merged_times, total_ms)

            min_step_time = float('inf')
            for phase in PHASE_ORDER:
                if phase not in phase_step_data:
                    continue
                _, _, merged_times, _ = phase_step_data[phase]
                for t in merged_times:
                    if t > 0 and t < min_step_time:
                        min_step_time = t
            if min_step_time == float('inf'):
                min_step_time = 100

            time_to_width_ratio = min_block_width / min_step_time
            row_natural_widths = {}
            for phase in PHASE_ORDER:
                if phase not in phase_step_data:
                    continue
                _, y_rotation, merged_times, _ = phase_step_data[phase]
                natural_w = sum(max(min_block_width, t * time_to_width_ratio) for t in merged_times)
                if y_rotation:
                    natural_w += y_rotation_width
                row_natural_widths[phase] = natural_w

            max_natural_width = max(row_natural_widths.values()) if row_natural_widths else 0
            total_rows = sum(1 for p in PHASE_ORDER if p in phase_step_data)
            canvas_height = total_rows * row_height + 10

            timeline_canvas = tk.Canvas(group_frame, height=canvas_height,
                                        bg=THEME["card_bg"], highlightthickness=0)
            timeline_canvas.pack(fill=tk.BOTH, expand=True)

            # tooltip
            tooltip_win = [None]
            tooltip_text = [None]
            step_rects = []
            label_rects = []

            def _show_tooltip(event, text):
                if tooltip_text[0] == text and tooltip_win[0]:
                    tooltip_win[0].wm_geometry(f"+{event.x_root + 12}+{event.y_root + 8}")
                    return
                _hide_tooltip()
                tw = tk.Toplevel(timeline_canvas)
                tw.wm_overrideredirect(True)
                tw.wm_attributes("-topmost", True)
                tw.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 8}")
                lbl = tk.Label(tw, text=text, font=("Microsoft YaHei", 9),
                               bg="#ffffdd", fg="#333333", relief="solid", borderwidth=1,
                               padx=6, pady=4, justify="left")
                lbl.pack()
                tooltip_win[0] = tw
                tooltip_text[0] = text

            def _hide_tooltip():
                if tooltip_win[0]:
                    tooltip_win[0].destroy()
                    tooltip_win[0] = None
                tooltip_text[0] = None

            def _build_phase_tooltip(phase_key, phase_label):
                stats = analyzer.get_phase_stats()
                ps = stats.get(phase_key, {})
                if ps:
                    return (
                        f"{phase_label}\n"
                        f"步数: {ps.get('steps', 0)}\n"
                        f"用时: {ps.get('time', 0):.2f}s\n"
                        f"观察: {ps.get('observation_time', 0):.2f}s\n"
                        f"卡顿: {ps.get('stutter_count', 0)}\n"
                        f"废步: {ps.get('wasted_moves', 0)}\n"
                        f"TPS: {ps.get('tps', 0):.1f}"
                    )
                return f"{phase_label}\n(无阶段数据)"

            def _on_configure(event, tc=timeline_canvas, psd=phase_step_data,
                              rnw=row_natural_widths, mnw=max_natural_width,
                              sr=step_rects, lr=label_rects):
                available_width = event.width - margin_left - margin_right
                if available_width <= 0:
                    return
                scale_ratio = available_width / mnw if mnw > 0 else 1

                if scale_ratio < 1:
                    max_actual_width = 0
                    for phase in PHASE_ORDER:
                        if phase not in psd:
                            continue
                        _, y_rotation, merged_times, _ = psd[phase]
                        actual_w = sum(max(min_block_width, max(min_block_width, t * time_to_width_ratio) * scale_ratio) for t in merged_times)
                        if y_rotation:
                            actual_w += y_rotation_width
                        max_actual_width = max(max_actual_width, actual_w)
                    if max_actual_width > available_width and max_actual_width > 0:
                        scale_ratio *= available_width / max_actual_width

                tc.delete("all")
                sr.clear()
                lr.clear()

                row_idx = 0
                for phase in PHASE_ORDER:
                    if phase not in psd:
                        continue
                    merged_moves, y_rotation, merged_times, total_ms = psd[phase]
                    phase_color = PHASE_COLORS.get(phase, "#b2bec3")
                    phase_label = CFG_PHASE_LABELS.get(phase, phase)

                    y_base = row_idx * row_height + 5

                    # 阶段标签
                    tc.create_text(margin_left - 6, y_base + label_height + bar_height / 2,
                                   text=phase_label, anchor=tk.E,
                                   font=("Microsoft YaHei", 9, "bold"), fill=phase_color)
                    lr.append((0, margin_left, y_base, y_base + row_height,
                               _build_phase_tooltip(phase, phase_label)))

                    x = margin_left
                    if y_rotation:
                        rx_end = x + y_rotation_width
                        tc.create_rectangle(x, y_base + label_height, rx_end,
                                            y_base + label_height + bar_height,
                                            fill="", outline=THEME["border"], width=1, dash=(2, 2))
                        tc.create_text((x + rx_end) / 2, y_base + 6, text=y_rotation,
                                       font=("Consolas", 8, "bold"), fill=THEME["fg"])
                        sr.append((x, rx_end, y_base + label_height,
                                   y_base + label_height + bar_height, f"{y_rotation}"))
                        x = rx_end

                    for i, move in enumerate(merged_moves):
                        st_ms = merged_times[i]
                        natural_w = max(min_block_width, st_ms * time_to_width_ratio)
                        block_width = max(min_block_width, natural_w * scale_ratio)
                        color = face_colors.get(move, face_colors.get(move[0], "#b2bec3"))
                        x_end = x + block_width

                        tc.create_rectangle(x, y_base + label_height, x_end,
                                            y_base + label_height + bar_height,
                                            fill=color, outline="", width=0)
                        mid_x = (x + x_end) / 2
                        tc.create_text(mid_x, y_base + 6, text=move,
                                       font=("Consolas", 11, "bold"), fill=color)

                        step_time_s = st_ms / 1000.0
                        sr.append((x, x_end, y_base + label_height,
                                   y_base + label_height + bar_height,
                                   f"{move}  {step_time_s:.3f}s"))
                        x = x_end

                    row_idx += 1

            timeline_canvas.bind("<Configure>", _on_configure)

            def _on_motion(event, sr=step_rects, lr=label_rects):
                x, y = event.x, event.y
                for rx1, rx2, ry1, ry2, text in lr:
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        _show_tooltip(event, text)
                        return
                for rx1, rx2, ry1, ry2, text in sr:
                    if rx1 <= x <= rx2 and ry1 <= y <= ry2:
                        _show_tooltip(event, text)
                        return
                _hide_tooltip()

            def _on_leave(event):
                _hide_tooltip()

            timeline_canvas.bind("<Motion>", _on_motion)
            timeline_canvas.bind("<Leave>", _on_leave)

        # 更新滚动区域
        inner_frame.update_idletasks()
        scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        # 鼠标滚轮支持
        def _on_replay_mousewheel(event):
            scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        scroll_canvas.bind("<MouseWheel>", _on_replay_mousewheel)
        outer_frame.bind("<MouseWheel>", _on_replay_mousewheel)
        inner_frame.bind("<MouseWheel>", _on_replay_mousewheel)
        # 为inner_frame的所有子控件绑定滚轮
        def _bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_replay_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)
        # 延迟绑定，等子控件创建完成
        self.replay_canvas_container.after(100, lambda: _bind_mousewheel_recursive(inner_frame))
    
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
        # 保存内容包含解法复盘和AI分析报告
        replay_content = self._solution_summary if self._solution_summary else ""
        ai_content = self.result_text.get("1.0", tk.END).strip()
        if not replay_content and not ai_content:
            messagebox.showwarning("警告", "没有可保存的分析结果！")
            return

        content_parts = []
        if replay_content:
            content_parts.append(replay_content)
        if ai_content:
            if content_parts:
                content_parts.append("\n\n---\n")
            content_parts.append(ai_content)
        content = "".join(content_parts)
        
        os.makedirs(RESULT_DIR, exist_ok=True)
        
        default_name = ""
        mode = self.analysis_mode_var.get()
        username = self._current_username or "unknown"
        
        if mode == '单组' and hasattr(self, '_current_analyzer') and self._current_analyzer:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                scramble = self.scramble_entry.get().strip().replace(" ", "")
                total_time = self._current_analyzer.get_total_time()
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

        self._start_ai_status_animation("building")

        try:
            bottom_color, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)
            bottom_name = COLOR_NAMES.get(bottom_color, bottom_color)

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
            self._current_analyzer = analyzer
        except Exception as e:
            log.error(f"构建分析数据失败: {str(e)}")
            self._reset_analysis_ui()
            messagebox.showerror("错误", f"构建分析数据失败:\n{str(e)}")
            return
        
        self._stream_stop = False
        self._stream_buffer = ""
        self._reasoning_buffer = ""
        # 清空旧的解法复盘
        for w in self.replay_canvas_container.winfo_children():
            w.destroy()
        scramble = self.scramble_entry.get().strip()
        self._solution_summary = (
            f"【解法复盘】\n\n"
            f"【打乱】:{scramble}\n"
            f"【底色】:{bottom_name} | 【自动朝向】:{get_orientation_desc(analyzer.top_color, analyzer.front_color)}\n"
            + analyzer.format_output()
        )
        self._replay_analyzers = [(analyzer, scramble, bottom_name)]
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
        # 解法复盘显示到Canvas时间轴（只绘制一次）
        if self._solution_summary and hasattr(self, '_replay_analyzers') and self._replay_analyzers:
            if not self.replay_canvas_container.winfo_children():
                self._draw_replay_timeline()

        # AI分析结果显示
        is_at_bottom = self._is_scroll_at_bottom()

        if not is_at_bottom:
            scroll_pos = self.result_text.yview()

        self.result_text.config(state="normal")
        self.result_text.delete("1.0", tk.END)

        if self._stream_buffer:
            display_text = self._format_tags_in_report(self._stream_buffer)
            render_markdown(self.result_text, display_text)
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
        # 在AI输出末尾追加模型来源
        model = self.model_var.get()
        if model and self._stream_buffer:
            self._stream_buffer += f"\n\n---\n内容来自{model}模型"
        self._render_buffer()
        self.ai_analyze_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self._stream_stop = False
        self._stop_ai_status_animation()
        self._set_status("分析完成")
        self.root.after(3000, self._clear_status)
        self._parse_and_store_tags()
        self._save_to_memory()

    def _parse_and_store_tags(self):
        """解析AI返回的标签并暂存，等待_save_to_memory时一并写入数据库"""
        import re
        from config import STRENGTH_TAGS, WEAKNESS_TAGS
        valid_strength = set(STRENGTH_TAGS)
        valid_weakness = set(WEAKNESS_TAGS)

        mode = self.analysis_mode_var.get()
        text = self._stream_buffer or ""

        if mode == '单组':
            # 查找 <tags>...</tags>
            match = re.search(r'<tags>\s*(\{.*?\})\s*</tags>', text, re.DOTALL)
            if match:
                try:
                    import json
                    tags = json.loads(match.group(1))
                    s_tags = [t for t in tags.get("strength", []) if t in valid_strength][:3]
                    w_tags = [t for t in tags.get("weakness", []) if t in valid_weakness][:3]
                    self._pending_tags = {"strength": s_tags, "weakness": w_tags}
                except (json.JSONDecodeError, Exception):
                    self._pending_tags = None
            else:
                self._pending_tags = None
        else:
            # 多组：查找所有 <tags group="N">...</tags>
            matches = re.finditer(r'<tags\s+group="(\d+)"\s*>\s*(\{.*?\})\s*</tags>', text, re.DOTALL)
            group_tags = {}
            for m in matches:
                try:
                    import json
                    group_idx = int(m.group(1))
                    tags = json.loads(m.group(2))
                    s_tags = [t for t in tags.get("strength", []) if t in valid_strength][:3]
                    w_tags = [t for t in tags.get("weakness", []) if t in valid_weakness][:3]
                    group_tags[group_idx] = {"strength": s_tags, "weakness": w_tags}
                except (json.JSONDecodeError, Exception):
                    pass
            self._pending_multi_tags = group_tags if group_tags else None

    def _format_tags_in_report(self, text: str) -> str:
        """将AI返回的<tags>JSON转为可读格式"""
        import re
        import json

        def replace_single_tag(match):
            try:
                tags = json.loads(match.group(1))
                s = "、".join(tags.get("strength", []))
                w = "、".join(tags.get("weakness", []))
                parts = []
                if s:
                    parts.append(f"**优点**: {s}")
                if w:
                    parts.append(f"**缺点**: {w}")
                return " | ".join(parts) if parts else ""
            except (json.JSONDecodeError, Exception):
                return ""

        def replace_multi_tag(match):
            try:
                group_idx = match.group(1)
                tags = json.loads(match.group(2))
                s = "、".join(tags.get("strength", []))
                w = "、".join(tags.get("weakness", []))
                parts = [f"第{group_idx}组:"]
                if s:
                    parts.append(f"优点:{s}")
                if w:
                    parts.append(f"缺点:{w}")
                return " ".join(parts)
            except (json.JSONDecodeError, Exception):
                return ""

        # 先处理多组标签 <tags group="N">...</tags>
        text = re.sub(r'<tags\s+group="(\d+)"\s*>\s*(\{.*?\})\s*</tags>', replace_multi_tag, text, flags=re.DOTALL)
        # 再处理单组标签 <tags>...</tags>
        text = re.sub(r'<tags>\s*(\{.*?\})\s*</tags>', replace_single_tag, text, flags=re.DOTALL)
        return text

    def _save_ao12_tags(self, ao12_items, raw_text):
        """从Ao12分析结果中解析标签并保存到对应记录的数据库"""
        import re
        import json
        from config import STRENGTH_TAGS, WEAKNESS_TAGS
        valid_strength = set(STRENGTH_TAGS)
        valid_weakness = set(WEAKNESS_TAGS)

        if not ao12_items or not raw_text:
            return

        # 查找所有 <tags group="N">...</tags>
        matches = re.finditer(r'<tags\s+group="(\d+)"\s*>\s*(\{.*?\})\s*</tags>', raw_text, re.DOTALL)
        for m in matches:
            try:
                group_idx = int(m.group(1))
                tags = json.loads(m.group(2))
                s_tags = [t for t in tags.get("strength", []) if t in valid_strength][:3]
                w_tags = [t for t in tags.get("weakness", []) if t in valid_weakness][:3]

                # group_idx从1开始，对应ao12_items列表索引
                idx = group_idx - 1
                if 0 <= idx < len(ao12_items):
                    item = ao12_items[idx]
                    record_id = memory_db.find_record_id(
                        item["scramble"], item["solution"], item["total_time"]
                    )
                    if record_id:
                        memory_db.update_record_tags(record_id, s_tags, w_tags)
            except (json.JSONDecodeError, Exception):
                pass

    def _build_memory_text(self) -> str:
        from config import PHASE_ORDER
        # 使用与水平统计相同的计算方法：近1000次截尾均值
        avg = memory_db.get_averages(limit=1000)
        if not avg:
            return ""
        
        lines = ["【历史平均水平（近1000次）】"]
        
        display_phases = ["cross", "f2l_avg", "oll", "pll"]
        display_labels = {"cross": "Cross", "f2l_avg": "F2L均", "oll": "OLL", "pll": "PLL"}
        
        for phase_key in display_phases:
            label = display_labels[phase_key]
            if phase_key == "f2l_avg":
                f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
                f2l_data = [avg.get(p, {}) for p in f2l_phases]
                f2l_data = [d for d in f2l_data if d]
                if f2l_data:
                    avg_steps = sum(d["steps"] for d in f2l_data) / len(f2l_data)
                    avg_time = sum(d["time"] for d in f2l_data) / len(f2l_data)
                    avg_tps = sum(d["tps"] for d in f2l_data) / len(f2l_data)
                    avg_obs = sum(d["observation_time"] for d in f2l_data) / len(f2l_data)
                    lines.append(f"{label}: {avg_steps:.0f}步{avg_time:.1f}s(TPS{avg_tps:.1f} 观察{avg_obs:.1f}s)")
                else:
                    lines.append(f"{label}: -")
            else:
                d = avg.get(phase_key, {})
                if d:
                    obs_str = f" 观察{d['observation_time']:.1f}s" if phase_key != "cross" else ""
                    lines.append(f"{label}: {d['steps']:.0f}步{d['time']:.1f}s(TPS{d['tps']:.1f}{obs_str})")
                else:
                    lines.append(f"{label}: -")
        
        total_avg = memory_db.get_total_time_avg()
        if total_avg:
            lines.append(f"平均总用时: {total_avg:.2f}s")
        
        return "\n".join(lines) + "\n"

    def _build_comparison_text(self, analyzer) -> str:
        # 使用与水平统计相同的计算方法：近1000次截尾均值
        avg = memory_db.get_averages(limit=1000)
        if not avg:
            return ""
        
        stats = analyzer.get_phase_stats()
        
        lines = ["【本次与历史对比】（基准：近1000次平均）"]
        
        cur = stats["cross"]
        hist = avg.get("cross", {})
        if hist:
            ds = cur["steps"] - hist["steps"]
            dt = cur["time"] - hist["time"]
            dtps = cur["tps"] - hist["tps"]
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            lines.append(f"Cross: 本次 {cur['steps']}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} {tag}")
        
        f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
        cur_f2l = [stats[p] for p in f2l_phases if stats[p]["steps"] > 0]
        hist_f2l = [avg.get(p, {}) for p in f2l_phases]
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
            hist = avg.get(phase_key, {})
            if hist:
                ds = cur["steps"] - hist["steps"]
                dt = cur["time"] - hist["time"]
                dtps = cur["tps"] - hist["tps"]
                tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
                obs_info = ""
                obs_cur = cur.get("observation_time")
                obs_hist = hist.get("observation_time")
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
        # 使用与水平统计相同的计算方法：近1000次截尾均值
        avg = memory_db.get_averages(limit=1000)
        if not avg:
            return ""
        
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
        
        lines = ["【多组平均与历史对比】（基准：近1000次平均）"]
        
        cur = avg_stats.get("cross", {})
        hist = avg.get("cross", {})
        if cur and hist:
            ds = cur["steps"] - hist["steps"]
            dt = cur["time"] - hist["time"]
            dtps = cur["tps"] - hist["tps"]
            tag = "进步" if dt < 0 else ("退步" if dt > 0 else "持平")
            lines.append(f"Cross: 本次均 {cur['steps']:.0f}步{cur['time']:.1f}s(TPS{cur['tps']:.1f}) vs 历史 {hist['steps']:.0f}步{hist['time']:.1f}s(TPS{hist['tps']:.1f}) → 步数{ds:+.0f} 用时{dt:+.1f}s TPS{dtps:+.1f} {tag}")
        
        f2l_phases = ["f2l1", "f2l2", "f2l3", "f2l4"]
        cur_f2l = [avg_stats.get(p, {}) for p in f2l_phases]
        cur_f2l_valid = [d for d in cur_f2l if d]
        hist_f2l = [avg.get(p, {}) for p in f2l_phases]
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
            hist = avg.get(phase_key, {})
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
        mode = self.analysis_mode_var.get()
        try:
            # 无论是否启用记忆保存，都要更新已有记录的标签
            if mode == '单组':
                if not hasattr(self, '_current_analyzer') or not self._current_analyzer:
                    return
                analyzer = self._current_analyzer
                scramble_text = self.scramble_entry.get().strip() if hasattr(self, 'scramble_entry') else ""
                solution_text = self.solution_text.get().strip() if hasattr(self, 'solution_text') else ""
                total_time = analyzer.get_total_time()

                # 保存标签到局部变量，避免被提前清空
                pending = getattr(self, '_pending_tags', None)
                self._pending_tags = None

                # 更新已有记录的标签
                if pending:
                    record_id = memory_db.find_record_id(scramble_text, solution_text, total_time)
                    if record_id:
                        memory_db.update_record_tags(record_id,
                                                      pending["strength"],
                                                      pending["weakness"])

                if not self._use_memory_var.get():
                    self._update_memory_count()
                    if hasattr(self, '_refresh_home_stats'):
                        self._refresh_home_stats()
                    if hasattr(self, '_refresh_data_tab'):
                        self._refresh_data_tab()
                    return
                stats = analyzer.get_phase_stats()
                bottom_name = COLOR_NAMES.get(analyzer.bottom_color, "白")
                total_steps = sum(s.get("steps", 0) for s in stats.values())
                total_time = analyzer.get_total_time()
                total_tps = total_steps / total_time if total_time > 0 else 0
                processed_solve = analyzer.generate_processed_solve()
                record_id = memory_db.save_record(scramble_text, solution_text, total_time, bottom_name, stats,
                                                  total_steps=total_steps, total_tps=total_tps,
                                                  processed_solve=processed_solve)
                if record_id == 0:
                    record_id = memory_db.find_record_id(scramble_text, solution_text, total_time)
                # 新记录也需要写入标签
                if record_id and pending:
                    memory_db.update_record_tags(record_id,
                                                  pending["strength"],
                                                  pending["weakness"])
            else:
                if not hasattr(self, '_last_multi_data') or not self._last_multi_data:
                    return
                # 保存标签到局部变量，避免被提前清空
                multi_tags = getattr(self, '_pending_multi_tags', None) or {}
                self._pending_multi_tags = None

                # 更新已有记录的标签
                for idx, (g, analyzer) in enumerate(self._last_multi_data):
                    total_time = analyzer.get_total_time()
                    group_idx = idx + 1
                    tags = multi_tags.get(group_idx)
                    if tags:
                        record_id = memory_db.find_record_id(g['scramble'], g['solution'], total_time)
                        if record_id:
                            memory_db.update_record_tags(record_id, tags["strength"], tags["weakness"])

                if not self._use_memory_var.get():
                    self._update_memory_count()
                    if hasattr(self, '_refresh_home_stats'):
                        self._refresh_home_stats()
                    if hasattr(self, '_refresh_data_tab'):
                        self._refresh_data_tab()
                    return

                for idx, (g, analyzer) in enumerate(self._last_multi_data):
                    stats = analyzer.get_phase_stats()
                    total_time = analyzer.get_total_time()
                    total_steps = sum(s.get("steps", 0) for s in stats.values())
                    total_tps = total_steps / total_time if total_time > 0 else 0
                    bottom_name = g.get('bottom_name', COLOR_NAMES.get(analyzer.bottom_color, "白"))
                    processed_solve = analyzer.generate_processed_solve()
                    record_id = memory_db.save_record(g['scramble'], g['solution'], total_time, bottom_name, stats,
                                                      total_steps=total_steps, total_tps=total_tps,
                                                      processed_solve=processed_solve)
                    if record_id == 0:
                        record_id = memory_db.find_record_id(g['scramble'], g['solution'], total_time)
                    # 新记录也需要写入标签
                    group_idx = idx + 1
                    tags = multi_tags.get(group_idx)
                    if record_id and tags:
                        memory_db.update_record_tags(record_id, tags["strength"], tags["weakness"])
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

    def _refresh_training_lists(self):
        """刷新OLL/PLL训练列表，显示带标签的case"""
        stats = memory_db.get_oll_pll_stats()

        # OLL训练列表
        oll_data = stats.get("oll", {})
        oll_tags = self._compute_op_case_tags(oll_data, OLL_ALGORITHMS, "oll")
        self._fill_training_frame(self._oll_train_frame, oll_data, oll_tags, "oll")

        # PLL训练列表
        pll_data = stats.get("pll", {})
        pll_tags = self._compute_op_case_tags(pll_data, PLL_ALGORITHMS, "pll")
        self._fill_training_frame(self._pll_train_frame, pll_data, pll_tags, "pll")

    def _fill_training_frame(self, frame, data, tags, op_type):
        """填充训练列表：只显示有标签的case，按标签数和出现次数排序，一行两个"""
        # 清空现有内容
        for w in frame.winfo_children():
            w.destroy()

        # 筛选有标签的case
        tagged_cases = []
        for case_name, case_tags in tags.items():
            if case_tags and case_name != "skip":
                tagged_cases.append((case_name, case_tags))

        if not tagged_cases:
            tk.Label(frame, text="暂无需要重点训练的case", bg=THEME["card_bg"],
                     fg="#888888", font=("Microsoft YaHei", 11)).pack(anchor="w")
            return

        # 排序：标签数多的靠前，标签相同则出现次数多的靠前
        tagged_cases.sort(key=lambda x: (-len(x[1]), -data.get(x[0], {}).get("count", 0)))

        # 图片目录
        img_dir = os.path.join(APP_DIR, "png", "OLL" if op_type == "oll" else "PLL")

        # 加载公式配置
        algo_config = self._load_op_algo_config()
        algo_db = OLL_ALGORITHMS if op_type == "oll" else PLL_ALGORITHMS

        # 保存图片引用防止GC
        photo_refs = []

        def _get_display_algo(case_name):
            key = f"{op_type}_{case_name}"
            selected_idx = algo_config.get(key, 0)
            algos = algo_db.get(case_name, [])
            custom_key = f"{op_type}_{case_name}_custom"
            custom_list = algo_config.get(custom_key, [])
            all_algos = algos + custom_list
            if selected_idx < len(all_algos):
                return all_algos[selected_idx]
            return algos[0] if algos else ""

        def _get_rotation_from_algo(algo_str):
            import re as _re
            m = _re.match(r"^(U2?|U'|y2?|y')\s*", algo_str)
            if not m:
                return 0, algo_str
            prefix = m.group(1).strip()
            rest = algo_str[m.end():]
            rotation_map = {"U": 90, "U'": -90, "U2": 180, "y": 90, "y'": -90, "y2": 180}
            return rotation_map.get(prefix, 0), rest

        def _rotate_image(pil_img, angle):
            if angle == 0:
                return pil_img
            return pil_img.rotate(-angle, expand=True)

        # 一行四个case
        row_frame = None
        for i, (case_name, case_tags) in enumerate(tagged_cases):
            if i % 4 == 0:
                row_frame = tk.Frame(frame, bg=THEME["card_bg"])
                row_frame.pack(fill=tk.X, pady=2)

            case_data = data.get(case_name, {})
            tag_count = len(case_tags)

            # 背景色
            if tag_count >= 3:
                card_bg = "#ffcccc"
            elif tag_count == 2:
                card_bg = "#ffe0e0"
            else:
                card_bg = "#fff8dc"

            # 单个case卡片 - 固定宽度保持对齐
            card = tk.Frame(row_frame, bg=card_bg, padx=6, pady=4,
                            highlightthickness=1, highlightbackground="#ddd",
                            width=160)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
            card.pack_propagate(False)
            card.configure(height=100)

            # 上半部分：图片 + 名称/标签
            top_row = tk.Frame(card, bg=card_bg)
            top_row.pack(fill=tk.X)

            # 图片
            if op_type == "oll":
                img_path = os.path.join(img_dir, f"OLL{case_name}.png")
            else:
                img_path = os.path.join(img_dir, f"PLL {case_name}.png")

            img_loaded = False
            if os.path.isfile(img_path):
                try:
                    from PIL import Image as PILImage, ImageTk
                    pil_img = PILImage.open(img_path)
                    display_algo = _get_display_algo(case_name)
                    angle, _ = _get_rotation_from_algo(display_algo)
                    pil_img = _rotate_image(pil_img, angle)
                    pil_img.thumbnail((60, 60), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(pil_img)
                    photo_refs.append(photo)
                    img_label = tk.Label(top_row, image=photo, bg=card_bg)
                    img_label.pack(side=tk.LEFT, padx=(0, 4))
                    img_loaded = True
                except Exception:
                    img_loaded = False

            if not img_loaded:
                tk.Label(top_row, text=f"OLL\n{case_name}" if op_type == "oll" else f"PLL\n{case_name}",
                         font=("Microsoft YaHei", 10, "bold"), bg=card_bg,
                         fg=THEME["accent"], width=5).pack(side=tk.LEFT, padx=(0, 4))

            # 名称和标签
            name_tag_frame = tk.Frame(top_row, bg=card_bg)
            name_tag_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            case_title = f"OLL-{case_name}" if op_type == "oll" else f"PLL-{case_name}"
            tk.Label(name_tag_frame, text=case_title, font=("Microsoft YaHei", 11, "bold"),
                     bg=card_bg, fg="#2d3436").pack(anchor="w")

            tag_row = tk.Frame(name_tag_frame, bg=card_bg)
            tag_row.pack(anchor="w")
            for tag in case_tags:
                tk.Label(tag_row, text=tag, font=("Microsoft YaHei", 9, "bold"),
                         bg="#ffcccc", fg="#c0392b", padx=2, pady=0).pack(side=tk.LEFT, padx=(0, 2))

            # 下半部分：推荐公式
            display_algo = _get_display_algo(case_name)
            _, algo_clean = _get_rotation_from_algo(display_algo)
            if algo_clean:
                algo_row = tk.Frame(card, bg=card_bg)
                algo_row.pack(fill=tk.X, pady=(2, 0))
                tk.Label(algo_row, text="推荐:", font=("Microsoft YaHei", 9),
                         bg=card_bg, fg="#888888").pack(side=tk.LEFT)
                tk.Label(algo_row, text=algo_clean, font=("Consolas", 10),
                         bg=card_bg, fg="#6c5ce7").pack(side=tk.LEFT, padx=(2, 0))

        # 保存图片引用到frame防止GC
        frame._photo_refs = photo_refs

    def _show_date_range_report(self):
        """按日期范围生成训练总结"""
        import daily_report

        start_date = self._summary_start_var.get().strip()
        end_date = self._summary_end_var.get().strip()

        # 校验日期格式
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("日期格式错误", "请输入正确的日期格式：YYYY-MM-DD")
            return

        if start_date > end_date:
            messagebox.showwarning("日期范围错误", "起始日期不能晚于结束日期")
            return

        stats = daily_report.get_date_range_stats(start_date, end_date)
        if not stats:
            messagebox.showinfo("训练总结", f"{start_date} ~ {end_date} 暂无练习数据。")
            return

        # 复用 _show_daily_report 的弹窗逻辑，但传入自定义stats
        self._show_report_dialog(stats)

    def _show_daily_report(self):
        import daily_report

        stats = daily_report.get_today_stats()
        if not stats:
            messagebox.showinfo("今日总结", "今日暂无练习数据。")
            return

        self._show_report_dialog(stats)

    def _show_report_dialog(self, stats):
        """通用训练总结弹窗，支持今日或日期范围"""
        import daily_report

        win = tk.Toplevel(self.root)
        win.title(f"训练总结 ({stats['date']})")
        win.geometry("720x820")
        win.configure(bg=THEME["bg"])
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()
        self._center_window(win)

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
        scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=report_text.yview)
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
            chart_title = "训练" if "~" in stats.get("date", "") else "今日"
            line_path, hist_path = daily_report.generate_charts(stats["times"], title_prefix=chart_title)
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
            self._center_window(confirm_win)

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

            def _stream_ao12_analysis(api_key, model, ao12_items, which):
                from openai import OpenAI

                # 从字典列表中提取analyzer对象
                analyzers_only = [item["analyzer"] for item in ao12_items]

                memory_text = self._build_memory_text() if self._use_memory_var.get() else ""
                comparison_text = self._build_multi_comparison_text(analyzers_only) if self._use_memory_var.get() else ""
                system_prompt, user_prompt = self._build_multi_analysis_prompts(
                    analyzers_only, memory_text + comparison_text
                )

                count = len(analyzers_only)
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

            # 用于在_on_ai_done中保存标签
            analyzers_best_items = []
            analyzers_worst_items = []
            best_analysis_holder = {"raw": ""}
            worst_analysis_holder = {"raw": ""}

            def _run():
                nonlocal analyzers_best_items, analyzers_worst_items
                try:
                    summary_result = _stream_step(
                        api_key, model,
                        lambda ak, md: daily_report.call_ai_summary_stream(ak, md, stats),
                        "⏳ 正在总结训练数据..."
                    )
                    ai_summary_holder["text"] = summary_result

                    best_analysis = ""
                    worst_analysis = ""

                    if analyze_best:
                        analyzers_best_items = _build_ao12_analyzers(stats, "best")
                        if analyzers_best_items:
                            best_analysis = _stream_step(
                                api_key, model,
                                lambda ak, md, a=analyzers_best_items: _stream_ao12_analysis(ak, md, a, "best"),
                                "🏆 正在分析最佳Ao12..."
                            )
                            best_analysis_holder["raw"] = best_analysis
                        else:
                            best_analysis = "最佳Ao12分析: 无法解析有效数据"
                        ao12_analysis_holder["best"] = best_analysis

                    if analyze_worst:
                        analyzers_worst_items = _build_ao12_analyzers(stats, "worst")
                        if analyzers_worst_items:
                            worst_analysis = _stream_step(
                                api_key, model,
                                lambda ak, md, a=analyzers_worst_items: _stream_ao12_analysis(ak, md, a, "worst"),
                                "📉 正在分析最差Ao12..."
                            )
                            worst_analysis_holder["raw"] = worst_analysis
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
                        analyzers.append({
                            "analyzer": analyzer,
                            "scramble": scramble,
                            "solution": solution,
                            "total_time": analyzer.get_total_time()
                        })
                except Exception:
                    continue

            return analyzers

        def _on_ai_done(result, best_analysis, worst_analysis):
            ai_btn.config(state="normal", text="🤖 AI总结")

            # 格式化Ao12分析结果中的标签，并保存到数据库
            if best_analysis:
                best_analysis = self._format_tags_in_report(best_analysis)
                self._save_ao12_tags(analyzers_best_items, best_analysis_holder.get("raw", ""))
            if worst_analysis:
                worst_analysis = self._format_tags_in_report(worst_analysis)
                self._save_ao12_tags(analyzers_worst_items, worst_analysis_holder.get("raw", ""))

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
            if model:
                report_text.insert(tk.END, f"\n---\n内容来自{model}模型\n", "normal")

            if best_analysis:
                report_text.insert(tk.END, "\n🏆 最佳Ao12 AI分析\n", "section")
                report_text.insert(tk.END, best_analysis + "\n", "ai_summary")
                if model:
                    report_text.insert(tk.END, f"\n---\n内容来自{model}模型\n", "normal")
            if worst_analysis:
                report_text.insert(tk.END, "\n📉 最差Ao12 AI分析\n", "section")
                report_text.insert(tk.END, worst_analysis + "\n", "ai_summary")
                if model:
                    report_text.insert(tk.END, f"\n---\n内容来自{model}模型\n", "normal")

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

    def _show_oll_stats(self):
        stats = memory_db.get_oll_pll_stats()
        oll_data = stats.get("oll", {})
        if not oll_data:
            messagebox.showinfo("OLL统计", "暂无OLL统计数据，请先完成还原分析。")
            return
        self._show_op_stats_dialog("OLL统计", oll_data, "oll")

    def _show_pll_stats(self):
        stats = memory_db.get_oll_pll_stats()
        pll_data = stats.get("pll", {})
        if not pll_data:
            messagebox.showinfo("PLL统计", "暂无PLL统计数据，请先完成还原分析。")
            return
        self._show_op_stats_dialog("PLL统计", pll_data, "pll")

    def _show_op_stats_dialog(self, title: str, data: dict, op_type: str):
        """显示OLL/PLL统计弹窗

        Args:
            title: 弹窗标题
            data: 统计数据 {case_name: {count, avg_steps, avg_time, avg_tps, avg_obs_time, std_steps, std_time}}
            op_type: "oll" 或 "pll"
        """
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("850x700")
        win.configure(bg=THEME["bg"])
        win.resizable(True, True)
        win.transient(self.root)
        win.grab_set()
        self._center_window(win)

        main_frame = tk.Frame(win, bg=THEME["bg"], padx=12, pady=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 加载公式配置
        algo_config = self._load_op_algo_config()
        algo_db = OLL_ALGORITHMS if op_type == "oll" else PLL_ALGORITHMS

        # 计算 Z-score 评分标签
        case_tags = self._compute_op_case_tags(data, algo_db, op_type)

        # 顶部统计概要
        total_count = sum(d["count"] for d in data.values())
        case_count = len(data)
        summary_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=12, pady=8,
                                  highlightthickness=1, highlightbackground=THEME["border"])
        summary_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(summary_frame, text=f"共 {case_count} 种状态 | 总出现 {total_count} 次",
                 font=("Microsoft YaHei", 10), bg=THEME["card_bg"],
                 fg=THEME["fg"]).pack(anchor="w")

        # 排序控制栏
        sort_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=12, pady=6,
                               highlightthickness=1, highlightbackground=THEME["border"])
        sort_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(sort_frame, text="排序:", font=("Microsoft YaHei", 9),
                 bg=THEME["card_bg"], fg=THEME["fg"]).pack(side=tk.LEFT)

        sort_key_var = tk.StringVar(value="出现次数")
        sort_order_var = tk.StringVar(value="降序")

        sort_keys = ["序号", "出现次数", "步数", "用时", "识别时间", "TPS"]
        sort_key_combo = ttk.Combobox(sort_frame, textvariable=sort_key_var,
                                       values=sort_keys, state="readonly", width=8)
        sort_key_combo.pack(side=tk.LEFT, padx=(4, 8))

        sort_orders = ["升序", "降序"]
        sort_order_combo = ttk.Combobox(sort_frame, textvariable=sort_order_var,
                                         values=sort_orders, state="readonly", width=5)
        sort_order_combo.pack(side=tk.LEFT, padx=(0, 8))

        # 获取图片目录
        img_dir = os.path.join(APP_DIR, "png", "OLL" if op_type == "oll" else "PLL")

        # 可滚动的统计内容区域
        canvas = tk.Canvas(main_frame, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=THEME["bg"])

        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 鼠标滚轮支持（Enter/Leave绑定避免冲突）
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        win.protocol("WM_DELETE_WINDOW", lambda: (canvas.unbind_all("<MouseWheel>"), win.destroy()))

        # 保存图片引用防止GC（绑定到窗口对象）
        win._photo_refs = []

        def _get_selected_algo(case_name):
            """获取用户选择的公式索引，默认0（第一个公式）"""
            key = f"{op_type}_{case_name}"
            return algo_config.get(key, 0)

        def _get_display_algo(case_name):
            """获取当前case要显示的公式文本"""
            key = f"{op_type}_{case_name}"
            selected_idx = algo_config.get(key, 0)
            algos = algo_db.get(case_name, [])
            custom_key = f"{op_type}_{case_name}_custom"
            custom_list = algo_config.get(custom_key, [])
            all_algos = algos + custom_list
            if selected_idx < len(all_algos):
                return all_algos[selected_idx]
            return algos[0] if algos else ""

        def _get_rotation_from_algo(algo_str):
            """从公式开头提取旋转操作，返回(旋转角度, 剩余公式)
            U=90°顺时针, U'=90°逆时针, U2=180°, y=90°顺时针, y'=90°逆时针, y2=180°
            """
            import re as _re
            # 匹配开头的 U/U'/U2/y/y'/y2
            m = _re.match(r"^(U2?|U'|y2?|y')\s*", algo_str)
            if not m:
                return 0, algo_str
            prefix = m.group(1).strip()
            rest = algo_str[m.end():]
            rotation_map = {"U": 90, "U'": -90, "U2": 180, "y": 90, "y'": -90, "y2": 180}
            return rotation_map.get(prefix, 0), rest

        def _rotate_image(pil_img, angle):
            """旋转PIL图片"""
            if angle == 0:
                return pil_img
            return pil_img.rotate(-angle, expand=True)  # PIL逆时针为正，所以取反

        def _render_list():
            for w in scroll_frame.winfo_children():
                w.destroy()
            win._photo_refs.clear()

            sort_key = sort_key_var.get()
            reverse = sort_order_var.get() == "降序"

            key_map = {
                "序号": lambda x: (0, int(x[0])) if x[0].isdigit() else (1, x[0]),
                "出现次数": lambda x: x[1]["count"],
                "步数": lambda x: x[1]["avg_steps"],
                "用时": lambda x: x[1]["avg_time"],
                "识别时间": lambda x: x[1]["avg_obs_time"],
                "TPS": lambda x: x[1]["avg_tps"],
            }
            sort_func = key_map.get(sort_key, key_map["出现次数"])
            sorted_cases = sorted(data.items(), key=sort_func, reverse=reverse)

            for case_name, case_data in sorted_cases:
                # 根据标签数量决定背景色
                tags = case_tags.get(case_name, [])
                if len(tags) >= 3:
                    row_bg = "#ffcccc"
                elif len(tags) == 2:
                    row_bg = "#ffe0e0"
                elif len(tags) == 1:
                    row_bg = "#fff8dc"
                else:
                    row_bg = THEME["card_bg"]

                row_frame = tk.Frame(scroll_frame, bg=row_bg, padx=8, pady=6,
                                      highlightthickness=1, highlightbackground=THEME["border"])
                row_frame.pack(fill=tk.X, padx=4, pady=3)

                # 图片区域 - 固定宽度容器确保对齐
                img_container = tk.Frame(row_frame, bg=row_bg, width=70, height=60)
                img_container.pack(side=tk.LEFT, padx=(0, 10))
                img_container.pack_propagate(False)

                if op_type == "oll":
                    img_path = os.path.join(img_dir, f"OLL{case_name}.png")
                else:
                    img_path = os.path.join(img_dir, f"PLL {case_name}.png")

                img_loaded = False
                if os.path.isfile(img_path):
                    try:
                        from PIL import Image as PILImage, ImageTk
                        pil_img = PILImage.open(img_path)
                        # 根据选中公式的旋转操作旋转图片
                        display_algo = _get_display_algo(case_name)
                        angle, _ = _get_rotation_from_algo(display_algo)
                        pil_img = _rotate_image(pil_img, angle)
                        pil_img.thumbnail((60, 60), PILImage.LANCZOS)
                        photo = ImageTk.PhotoImage(pil_img)
                        win._photo_refs.append(photo)
                        img_label = tk.Label(img_container, image=photo, bg=row_bg)
                        img_label.pack(expand=True)
                        img_loaded = True
                    except Exception:
                        img_loaded = False

                if not img_loaded:
                    tk.Label(img_container,
                             text=f"OLL {case_name}" if op_type == "oll" else f"PLL {case_name}",
                             font=("Microsoft YaHei", 10, "bold"), bg=row_bg,
                             fg=THEME["accent"]).pack(expand=True)

                # 中间统计信息
                info_frame = tk.Frame(row_frame, bg=row_bg)
                info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                # 标题行：case名称 + 公式
                title_frame = tk.Frame(info_frame, bg=row_bg)
                title_frame.pack(fill=tk.X)

                case_title = f"OLL-{case_name}" if op_type == "oll" else f"PLL-{case_name}"
                tk.Label(title_frame, text=case_title,
                         font=("Microsoft YaHei", 11, "bold"), bg=row_bg,
                         fg=THEME["fg"]).pack(side=tk.LEFT)

                # 显示选中的公式（去掉开头的U/y旋转步，因为图片已旋转）
                display_algo = _get_display_algo(case_name)
                _, display_algo_clean = _get_rotation_from_algo(display_algo)
                if display_algo_clean:
                    tk.Label(title_frame, text="  推荐公式 ",
                             font=("Microsoft YaHei", 9), bg=row_bg,
                             fg="#888888").pack(side=tk.LEFT)
                    tk.Label(title_frame, text=display_algo_clean,
                             font=("Consolas", 10), bg=row_bg,
                             fg="#6c5ce7").pack(side=tk.LEFT)

                # 统计文本
                stats_text = (
                    f"出现次数: {case_data['count']}    "
                    f"平均步数: {case_data['avg_steps']}(σ{case_data['std_steps']})    "
                    f"平均用时: {case_data['avg_time']:.2f}s(σ{case_data['std_time']:.2f})    "
                    f"平均识别: {case_data['avg_obs_time']:.2f}s    "
                    f"平均TPS: {case_data['avg_tps']}"
                )
                tk.Label(info_frame, text=stats_text,
                         font=("Microsoft YaHei", 9), bg=row_bg,
                         fg="#636e72").pack(anchor="w")

                # 标签行
                if tags:
                    tag_frame = tk.Frame(info_frame, bg=row_bg)
                    tag_frame.pack(fill=tk.X, pady=(2, 0))
                    for tag_text in tags:
                        tk.Label(tag_frame, text=tag_text,
                                 font=("Microsoft YaHei", 8, "bold"),
                                 bg="#ffcccc", fg="#c0392b",
                                 padx=4, pady=1).pack(side=tk.LEFT, padx=(0, 4))

                # 右侧"更多公式"按钮
                btn_container = tk.Frame(row_frame, bg=row_bg)
                btn_container.pack(side=tk.RIGHT, padx=(8, 0))
                ttk.Button(btn_container, text="更多公式",
                           command=lambda cn=case_name: self._show_algo_dialog(
                               win, cn, op_type, algo_db, algo_config, _render_list),
                           style="Accent.TButton").pack()

            canvas.yview_moveto(0)

        # 排序变化时刷新列表
        sort_key_combo.bind("<<ComboboxSelected>>", lambda e: _render_list())
        sort_order_combo.bind("<<ComboboxSelected>>", lambda e: _render_list())

        # 初始渲染
        _render_list()

        # 关闭按钮
        btn_frame = tk.Frame(win, bg=THEME["bg"], padx=12, pady=8)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="关闭",
                   command=lambda: (canvas.unbind_all("<MouseWheel>"), win.destroy()),
                   style="Secondary.TButton").pack(side=tk.RIGHT)

    def _load_op_algo_config(self):
        """加载OP公式选择配置"""
        try:
            if os.path.isfile(OP_ALGO_CONFIG_FILE):
                with open(OP_ALGO_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_op_algo_config(self, config):
        """保存OP公式选择配置"""
        try:
            with open(OP_ALGO_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _show_algo_dialog(self, parent_win, case_name, op_type, algo_db, algo_config, refresh_callback):
        """显示某个case的所有公式弹窗"""
        from PIL import Image as PILImage, ImageTk

        dialog = tk.Toplevel(parent_win)
        case_title = f"OLL-{case_name}" if op_type == "oll" else f"PLL-{case_name}"
        dialog.title(f"{case_title} 公式")
        dialog.geometry("700x600")
        dialog.configure(bg=THEME["bg"])
        dialog.transient(parent_win)
        dialog.grab_set()
        self._center_window(dialog)

        img_dir = os.path.join(APP_DIR, "png", "OLL" if op_type == "oll" else "PLL")

        # 获取公式列表
        base_algos = algo_db.get(case_name, [])
        custom_key = f"{op_type}_{case_name}_custom"
        custom_algos = list(algo_config.get(custom_key, []))
        selected_key = f"{op_type}_{case_name}"
        selected_idx = algo_config.get(selected_key, 0)

        # 按旋转分组
        def _get_rotation_label(algo_str):
            m = re.match(r"^(U2?|U'|y2?|y')\s*", algo_str)
            if not m:
                return 0, "原始图片", algo_str
            prefix = m.group(1).strip()
            label_map = {
                "U": "顺时针旋转90°", "U'": "逆时针旋转90°", "U2": "旋转180°",
                "y": "顺时针旋转90°", "y'": "逆时针旋转90°", "y2": "旋转180°"
            }
            rotation_map = {"U": 90, "U'": -90, "U2": 180, "y": 90, "y'": -90, "y2": 180}
            rest = algo_str[m.end():]
            return rotation_map.get(prefix, 0), label_map.get(prefix, "原始图片"), rest

        # 分组：按旋转角度
        groups = {}  # angle -> {"label": str, "algos": [(idx, algo_str, algo_clean)]}
        for i, algo in enumerate(base_algos):
            angle, label, algo_clean = _get_rotation_label(algo)
            if angle not in groups:
                groups[angle] = {"label": label, "algos": []}
            groups[angle]["algos"].append((i, algo, algo_clean))

        # 主体区域（可滚动 + 底部按钮）
        body_frame = tk.Frame(dialog, bg=THEME["bg"])
        body_frame.pack(fill=tk.BOTH, expand=True)

        # 可滚动区域
        canvas = tk.Canvas(body_frame, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=THEME["bg"])
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        # 鼠标滚轮支持（Enter/Leave绑定避免冲突）
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 图片引用绑定到dialog窗口，防止GC回收
        dialog._photo_refs = []
        check_vars = {}  # idx -> BooleanVar

        # 加载原始图片
        if op_type == "oll":
            img_path = os.path.join(img_dir, f"OLL{case_name}.png")
        else:
            img_path = os.path.join(img_dir, f"PLL {case_name}.png")

        base_pil_img = None
        if os.path.isfile(img_path):
            try:
                base_pil_img = PILImage.open(img_path)
            except Exception:
                base_pil_img = None

        # 按旋转角度分组显示
        for angle in sorted(groups.keys()):
            group = groups[angle]

            group_frame = tk.Frame(scroll_frame, bg=THEME["card_bg"], padx=10, pady=6,
                                    highlightthickness=1, highlightbackground=THEME["border"])
            group_frame.pack(fill=tk.X, padx=4, pady=4)

            # 左侧：旋转后的图片
            left_frame = tk.Frame(group_frame, bg=THEME["card_bg"])
            left_frame.pack(side=tk.LEFT, padx=(0, 10))

            img_loaded = False
            if base_pil_img:
                try:
                    rotated = base_pil_img.rotate(-angle, expand=True) if angle else base_pil_img.copy()
                    rotated.thumbnail((65, 65), PILImage.LANCZOS)
                    photo = ImageTk.PhotoImage(rotated)
                    dialog._photo_refs.append(photo)
                    img_label = tk.Label(left_frame, image=photo, bg=THEME["card_bg"])
                    img_label.pack()
                    img_loaded = True
                except Exception:
                    img_loaded = False

            if not img_loaded:
                tk.Label(left_frame, text=case_title,
                         font=("Microsoft YaHei", 9, "bold"), bg=THEME["card_bg"],
                         fg=THEME["accent"], width=8, height=4).pack()

            # 右侧：公式列表
            right_frame = tk.Frame(group_frame, bg=THEME["card_bg"])
            right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            for idx, algo, algo_clean in group["algos"]:
                row = tk.Frame(right_frame, bg=THEME["card_bg"])
                row.pack(fill=tk.X, pady=1)
                var = tk.BooleanVar(value=(idx == selected_idx))
                check_vars[idx] = var
                tk.Checkbutton(row, variable=var, bg=THEME["card_bg"],
                               activebackground=THEME["card_bg"]).pack(side=tk.LEFT)
                # 推荐公式（第一个）显示蓝色，其他黑色
                algo_fg = "#6c5ce7" if idx == 0 else "#2d3436"
                prefix_text = "★ " if idx == 0 else ""
                # 显示去掉开头U/y旋转步的公式（图片已旋转展示）
                display_text = algo_clean if algo_clean else algo
                tk.Label(row, text=f"{prefix_text}{display_text}", font=("Consolas", 9),
                         bg=THEME["card_bg"], fg=algo_fg).pack(side=tk.LEFT, padx=(4, 0))

        # 自定义公式区域
        custom_frame = tk.Frame(scroll_frame, bg=THEME["card_bg"], padx=10, pady=6,
                                 highlightthickness=1, highlightbackground=THEME["border"])
        custom_frame.pack(fill=tk.X, padx=4, pady=4)

        tk.Label(custom_frame, text="自定义公式",
                 font=("Microsoft YaHei", 10, "bold"), bg=THEME["card_bg"],
                 fg=THEME["fg"]).pack(anchor="w")

        # 显示已有的自定义公式
        custom_check_vars = {}  # idx -> BooleanVar
        custom_start_idx = len(base_algos)

        for ci, custom_algo in enumerate(custom_algos):
            row = tk.Frame(custom_frame, bg=THEME["card_bg"])
            row.pack(fill=tk.X, pady=1)
            var = tk.BooleanVar(value=((custom_start_idx + ci) == selected_idx))
            custom_check_vars[custom_start_idx + ci] = var
            tk.Checkbutton(row, variable=var, bg=THEME["card_bg"],
                           activebackground=THEME["card_bg"]).pack(side=tk.LEFT)
            tk.Label(row, text=custom_algo, font=("Microsoft YaHei", 9),
                     bg=THEME["card_bg"], fg="#2d3436").pack(side=tk.LEFT, padx=(4, 0))

            # 删除按钮
            def _delete_custom(idx=ci):
                custom_algos.pop(idx)
                algo_config[custom_key] = custom_algos
                # 如果选中的索引被删除了，重置为0
                current_selected = algo_config.get(selected_key, 0)
                deleted_global_idx = custom_start_idx + idx
                if current_selected == deleted_global_idx:
                    algo_config[selected_key] = 0
                elif current_selected > deleted_global_idx:
                    algo_config[selected_key] = current_selected - 1
                self._save_op_algo_config(algo_config)
                canvas.unbind_all("<MouseWheel>")
                dialog.destroy()
                self._show_algo_dialog(parent_win, case_name, op_type, algo_db, algo_config, refresh_callback)

            tk.Button(row, text="✕", font=("Microsoft YaHei", 8), bg=THEME["card_bg"],
                      fg="#e74c3c", bd=0, activebackground=THEME["card_bg"],
                      activeforeground="#c0392b", command=_delete_custom).pack(side=tk.RIGHT, padx=(4, 0))

        # 输入新自定义公式
        input_row = tk.Frame(custom_frame, bg=THEME["card_bg"])
        input_row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(input_row, text="新增:", font=("Microsoft YaHei", 9),
                 bg=THEME["card_bg"], fg="#888888").pack(side=tk.LEFT)
        custom_entry = tk.Entry(input_row, font=("Microsoft YaHei", 9), width=30)
        custom_entry.pack(side=tk.LEFT, padx=(4, 4))

        # 校验提示标签
        validate_label = tk.Label(input_row, text="", font=("Microsoft YaHei", 8),
                                   bg=THEME["card_bg"], fg="#e74c3c")
        validate_label.pack(side=tk.LEFT, padx=(4, 0))

        def _validate_algo(algo_str):
            """校验公式是否只包含合法字母"""
            if not algo_str:
                return False
            # 允许的字符：R L U D F B x y z r l u d f b 及其变体（' 2）和括号、空格、M S E
            return bool(re.match(r"^[RULFDBrludfbxyzMSE]'?(2)?(\s*[\(\)]?\s*[RULFDBrludfbxyzMSE]'?(2)?\s*[\(\)]?\s*)*$", algo_str))

        def _add_custom():
            new_algo = custom_entry.get().strip()
            if not new_algo:
                validate_label.config(text="请输入公式")
                return
            if not _validate_algo(new_algo):
                validate_label.config(text="公式包含非法字符")
                return
            custom_algos.append(new_algo)
            algo_config[custom_key] = custom_algos
            self._save_op_algo_config(algo_config)
            custom_entry.delete(0, tk.END)
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()
            self._show_algo_dialog(parent_win, case_name, op_type, algo_db, algo_config, refresh_callback)

        ttk.Button(input_row, text="保存", command=_add_custom,
                   style="Accent.TButton").pack(side=tk.LEFT)

        # 底部确认/取消按钮（放在最下面，不在滚动区域内）
        btn_frame = tk.Frame(dialog, bg=THEME["bg"], padx=12, pady=8)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        def _confirm():
            # 找到勾选的公式索引（只允许选一个）
            chosen_idx = 0
            for idx, var in check_vars.items():
                if var.get():
                    chosen_idx = idx
                    break
            for idx, var in custom_check_vars.items():
                if var.get():
                    chosen_idx = idx
                    break
            algo_config[selected_key] = chosen_idx
            self._save_op_algo_config(algo_config)
            canvas.unbind_all("<MouseWheel>")
            dialog.destroy()
            refresh_callback()

        ttk.Button(btn_frame, text="确认", command=_confirm,
                   style="Accent.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_frame, text="取消",
                   command=lambda: (canvas.unbind_all("<MouseWheel>"), dialog.destroy()),
                   style="Secondary.TButton").pack(side=tk.RIGHT)

    def _compute_op_case_tags(self, data, algo_db, op_type):
        """计算每个OP case的评价标签

        Returns:
            dict: {case_name: [tag1, tag2, ...]}
        """
        if not data:
            return {}

        # 计算全局 baseline
        all_obs = []
        all_tps = []
        for case_data in data.values():
            all_obs.append(case_data["avg_obs_time"])
            all_tps.append(case_data["avg_tps"])

        if len(all_obs) < 2:
            return {cn: [] for cn in data}

        import statistics
        global_recog_mean = statistics.mean(all_obs)
        global_recog_std = statistics.stdev(all_obs) if len(all_obs) > 1 else 1.0
        global_tps_mean = statistics.mean(all_tps)
        global_tps_std = statistics.stdev(all_tps) if len(all_tps) > 1 else 1.0

        # 避免除零
        if global_recog_std == 0:
            global_recog_std = 1.0
        if global_tps_std == 0:
            global_tps_std = 1.0

        result = {}
        for case_name, case_data in data.items():
            tags = []

            # 跳过的case不添加标签
            if case_name == "skip":
                result[case_name] = []
                continue

            # 公式过长：平均步数比公式库中该case最长的公式多5步以上
            algos = algo_db.get(case_name, [])
            if algos:
                # 计算每个公式的步数（简单统计非括号的大写字母移动数）
                max_algo_steps = 0
                for algo in algos:
                    # 去掉括号，统计移动数
                    clean = re.sub(r'[()]', '', algo)
                    moves = len(re.findall(r"[RULFDBrzxy]'?2?", clean))
                    if moves > max_algo_steps:
                        max_algo_steps = moves
                if case_data["avg_steps"] > max_algo_steps + 2:
                    tags.append("公式过长")

            # 识别慢：Z_recog >= 1.5
            z_recog = (case_data["avg_obs_time"] - global_recog_mean) / global_recog_std
            if z_recog >= 1.5:
                tags.append("识别慢")

            # 手速慢：Z_tps >= 1.5
            z_tps = (global_tps_mean - case_data["avg_tps"]) / global_tps_std
            if z_tps >= 1.5:
                tags.append("手速慢")

            result[case_name] = tags

        return result

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

            if not scramble or not solution:
                self._reset_analysis_ui()
                messagebox.showwarning("警告", f"第 {i+1} 组数据不完整，请检查！")
                return

            groups_data.append({
                'index': i + 1,
                'scramble': scramble,
                'solution': solution,
            })
        
        count = len(groups_data)
        log.info(f"开始多组分析, 模型: {model}, 共 {count} 组数据")
        
        self._start_ai_status_animation("building")
        
        analyzers = []
        for g in groups_data:
            try:
                bottom_color, analyzer, _ = CFOPAnalyzer.auto_detect_bottom_color(g['scramble'], g['solution'])
                g['bottom_color'] = bottom_color
                g['bottom_name'] = COLOR_NAMES.get(bottom_color, bottom_color)
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
        # 清空旧的解法复盘
        for w in self.replay_canvas_container.winfo_children():
            w.destroy()
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
            self._replay_analyzers = [(a, g['scramble'], g['bottom_name']) for a, g in zip(analyzers, groups_data)]
        
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
        from prompts import SYSTEM_PROMPT, USER_MULTI_TEMPLATE, AI_PAUSE_THRESHOLD_SEC, STRENGTH_TAGS, WEAKNESS_TAGS
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
        
        system = SYSTEM_PROMPT.format(
            pause_threshold=AI_PAUSE_THRESHOLD_SEC,
        )
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
            memory_info=memory_text,
            strength_tags_str="、".join(STRENGTH_TAGS),
            weakness_tags_str="、".join(WEAKNESS_TAGS),
        )
        
        return (system, user)
