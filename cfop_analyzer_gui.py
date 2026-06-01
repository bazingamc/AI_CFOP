"""
AI_CFOP - 魔方CFOP还原分析工具（GUI版本，含AI分析功能）

程序入口文件，负责初始化日志系统并启动GUI应用。

代码结构：
  config.py        - 配置参数、提示词模板、主题样式
  cube.py          - 三阶魔方状态模拟器
  move_utils.py    - 步骤解析和映射工具
  analyzer.py      - CFOP还原过程分析器
  api_utils.py     - API与配置工具（模型获取）
  markdown_renderer.py - Markdown渲染工具
  user_manager.py  - 用户管理模块
  memory_db.py     - 记忆数据库
  daily_report.py  - 今日练习总结
  gui.py           - GUI应用主类
"""

import os
import logging
from datetime import datetime

from config import LOG_DIR, APP_DIR


def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("cfop")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"cfop_{today}.log")
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.debug("Logger initialized")
    return logger


log = setup_logger()


def main():
    try:
        import tkinter as tk

        from cube import set_logger as cube_set_logger
        from analyzer import set_logger as analyzer_set_logger
        from gui import set_logger as gui_set_logger

        cube_set_logger(log)
        analyzer_set_logger(log)
        gui_set_logger(log)

        import user_manager
        user_manager.generate_default_avatar()

        from gui import CFOPAnalyzerGUI

        root = tk.Tk()
        app = CFOPAnalyzerGUI(root)
        root.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("按回车键退出...")


if __name__ == "__main__":
    main()
