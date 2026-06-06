"""
配置参数、主题样式

提示词模板已迁移至 prompts.py
"""

import os
import json
import sys


def get_app_dir():
    """获取应用程序所在目录，兼容打包后的exe和开发环境"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


APP_DIR = get_app_dir()
CONFIG_FILE = os.path.join(APP_DIR, ".cfop_config.json")
LOG_DIR = os.path.join(APP_DIR, "logs")
RESULT_DIR = os.path.join(APP_DIR, "results")

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

# 从 prompts.py 导入提示词相关常量（保持向后兼容）
from prompts import (
    AI_MAX_RESPONSE_WORDS, AI_PAUSE_THRESHOLD_SEC,
    STRENGTH_TAGS, WEAKNESS_TAGS,
    SYSTEM_PROMPT, USER_SINGLE_TEMPLATE, USER_MULTI_TEMPLATE,
    USER_SUMMARY_TEMPLATE, PHASE_DETAIL_TEMPLATE,
)

ORIENTATION_OPTIONS = [
    ('黄顶绿前', 'Y', 'G'),
    ('白顶绿前', 'W', 'G'),
    ('白顶蓝前', 'W', 'B'),
    ('黄顶蓝前', 'Y', 'B'),
    ('白顶红前', 'W', 'R'),
    ('黄顶红前', 'Y', 'R'),
    ('白顶橙前', 'W', 'O'),
    ('黄顶橙前', 'Y', 'O'),
    ('绿顶白前', 'G', 'W'),
    ('绿顶黄前', 'G', 'Y'),
    ('蓝顶白前', 'B', 'W'),
    ('蓝顶黄前', 'B', 'Y'),
    ('绿顶红前', 'G', 'R'),
    ('绿顶橙前', 'G', 'O'),
    ('蓝顶红前', 'B', 'R'),
    ('蓝顶橙前', 'B', 'O'),
    ('红顶白前', 'R', 'W'),
    ('红顶黄前', 'R', 'Y'),
    ('橙顶白前', 'O', 'W'),
    ('橙顶黄前', 'O', 'Y'),
    ('红顶绿前', 'R', 'G'),
    ('红顶蓝前', 'R', 'B'),
    ('橙顶绿前', 'O', 'G'),
    ('橙顶蓝前', 'O', 'B'),
]

ORIENTATION_NAMES = [opt[0] for opt in ORIENTATION_OPTIONS]

BOTTOM_COLOR_OPTIONS = [
    ('白底', 'W'),
    ('黄底', 'Y'),
    ('红底', 'R'),
    ('橙底', 'O'),
    ('绿底', 'G'),
    ('蓝底', 'B'),
]

BOTTOM_COLOR_NAMES = [opt[0] for opt in BOTTOM_COLOR_OPTIONS]


COLOR_NAMES = {
    'W': '白', 'Y': '黄', 'G': '绿', 'B': '蓝', 'O': '橙', 'R': '红'
}

COLOR_CODES = {
    '白': 'W', '黄': 'Y', '绿': 'G', '蓝': 'B', '橙': 'O', '红': 'R'
}

OPPOSITE_COLORS = {
    'W': 'Y', 'Y': 'W',
    'G': 'B', 'B': 'G',
    'O': 'R', 'R': 'O'
}


FACE_MOVES = {
    'U': ['U', "U'", 'U2'],
    'D': ['D', "D'", 'D2'],
    'F': ['F', "F'", 'F2'],
    'B': ['B', "B'", 'B2'],
    'L': ['L', "L'", 'L2'],
    'R': ['R', "R'", 'R2'],
}

ALL_MOVES = []
for moves in FACE_MOVES.values():
    ALL_MOVES.extend(moves)

ROTATION_MAP = {
    "x": {'U': 'F', 'F': 'D', 'D': 'B', 'B': 'U',
          "U'": "F'", "F'": "D'", "D'": "B'", "B'": "U'",
          'U2': 'F2', 'F2': 'D2', 'D2': 'B2', 'B2': 'U2',
          'L': 'L', "L'": "L'", 'L2': 'L2',
          'R': 'R', "R'": "R'", 'R2': 'R2'},
    "x'": {'U': 'B', 'B': 'D', 'D': 'F', 'F': 'U',
           "U'": "B'", "B'": "D'", "D'": "F'", "F'": "U'",
           'U2': 'B2', 'B2': 'D2', 'D2': 'F2', 'F2': 'U2',
           'L': 'L', "L'": "L'", 'L2': 'L2',
           'R': 'R', "R'": "R'", 'R2': 'R2'},
    "y": {'U': 'R', 'R': 'D', 'D': 'L', 'L': 'U',
          "U'": "R'", "R'": "D'", "D'": "L'", "L'": "U'",
          'U2': 'R2', 'R2': 'D2', 'D2': 'L2', 'L2': 'U2',
          'F': 'F', "F'": "F'", 'F2': 'F2',
          'B': 'B', "B'": "B'", 'B2': 'B2'},
    "y'": {'U': 'L', 'L': 'D', 'D': 'R', 'R': 'U',
           "U'": "L'", "L'": "D'", "D'": "R'", "R'": "U'",
           'U2': 'L2', 'L2': 'D2', 'D2': 'R2', 'R2': 'U2',
           'F': 'F', "F'": "F'", 'F2': 'F2',
           'B': 'B', "B'": "B'", 'B2': 'B2'},
    "z": {'U': 'F', 'F': 'U', 'U': 'B', 'B': 'D',
          "U'": "F'", "F'": "U'", "U'": "B'", "B'": "D'",
          'U2': 'F2', 'F2': 'U2', 'U2': 'B2', 'B2': 'D2',
          'R': 'R', "R'": "R'", 'R2': 'R2',
          'L': 'L', "L'": "L'", 'L2': 'L2'},
    "z'": {'U': 'B', 'B': 'U', 'U': 'F', 'F': 'D',
           "U'": "B'", "B'": "U'", "U'": "F'", "F'": "D'",
           'U2': 'B2', 'B2': 'U2', 'U2': 'F2', 'F2': 'D2',
           'R': 'R', "R'": "R'", 'R2': 'R2',
           'L': 'L', "L'": "L'", 'L2': 'L2'},
}

INVERSE_ROTATION = {"x": "x'", "x'": "x", "y": "y'", "y'": "y", "z": "z'", "z'": "z"}

CROSS_EDGES = {('U', 1): ('F', 1), ('U', 5): ('R', 3), ('U', 7): ('B', 1), ('U', 3): ('L', 3),
               ('D', 1): ('F', 7), ('D', 5): ('R', 7), ('D', 7): ('B', 7), ('D', 3): ('L', 7)}

F2L_SLOTS = [
    {('F', 1): ('U', 7), ('R', 3): ('U', 5), ('F', 3): ('R', 1)},
    {('F', 5): ('U', 3), ('L', 1): ('U', 1), ('F', 7): ('L', 3)},
    {('B', 5): ('U', 1), ('R', 5): ('U', 3), ('B', 3): ('R', 7)},
    {('B', 3): ('U', 5), ('L', 5): ('U', 7), ('B', 7): ('L', 1)},
]

OLL_PATTERNS = {
    'U': ['Y', 'Y', 'Y', 'Y', 'Y', 'Y', 'Y', 'Y', 'Y'],
}

PLL_PATTERNS = {
    'U': ['W', 'G', 'O', 'B', 'R', 'W', 'R', 'O', 'G'],
    'D': ['Y', 'R', 'B', 'O', 'G', 'Y', 'G', 'B', 'R'],
    'F': ['W', 'O', 'Y', 'Y', 'Y', 'Y', 'W', 'R', 'W'],
    'B': ['Y', 'B', 'W', 'Y', 'Y', 'Y', 'W', 'W', 'O'],
    'L': ['W', 'W', 'W', 'G', 'Y', 'Y', 'O', 'Y', 'Y'],
    'R': ['Y', 'Y', 'Y', 'Y', 'Y', 'B', 'Y', 'B', 'W'],
}


THEME = {
    "bg": "#f8f9fa",
    "fg": "#2d3436",
    "accent": "#6c5ce7",
    "accent_hover": "#5f4dd0",
    "success": "#00b894",
    "warning": "#fdcb6e",
    "danger": "#e17055",
    "card_bg": "#ffffff",
    "border": "#dfe6e9",
    "input_bg": "#ffffff",
    "button_bg": "#6c5ce7",
    "button_fg": "#ffffff",
}

HELP_TEXTS = {
    "input": """勾选「智能粘贴」后，从cstimer复制还原数据时自动填入输入框。
在cstimer中打乱并还原智能魔方，点击成绩列表中的还原时间，复制弹窗中的内容即可。
也可手动粘贴到对应输入框。
底色用于指定CFOP底面颜色；程序会在不改变底色/顶色的4个前色中自动匹配最合适的观察坐标。""",

    "ai": """【API Key获取】
- 从硅基流动平台获取API密钥
- 注册并完成实名认证后可获得价值16元的token（使用GLM5.1可分析约180次，使用deepseek-v3.2可分析约2000次）
- 注册链接：https://cloud.siliconflow.cn/i/k2AMkh34
- 邀请码：k2AMkh34

【模型选择】
- 点击"刷新"按钮获取可用模型列表
- 不同模型分析结果可能有较大差异，性能越高的模型分析结果越准确
- 高性能模型推荐GLM系列，性价比模型推荐DeepSeek系列

【分析说明】
AI将分析您的CFOP还原过程，提供：
- 各阶段技术水平评估
- TPS稳定性分析
- 卡顿点定位
- 训练建议""",

    "smart_paste": """勾选后自动监听剪贴板，从cstimer复制数据时自动填入输入框。
支持识别cstimer弹窗中的"打乱公式"和"回顾"内容。
多组模式下：先复制打乱再复制回顾，会自动配对到同一组。
已存在的数据不会重复粘贴。
便捷操作：点击弹窗中的"打乱公式"或"回顾"，依次按下ctrl+a+c，即可自动粘贴到对应输入框。""",

    "memory": """勾选后分析时将历史平均水平作为参考输入给AI，分析完成后自动记录本次数据。
不勾选则不使用记忆，分析数据也不存入记忆。
数据存储在本地SQLite数据库中，可点击"水平统计"旁的导出/清除按钮管理。"""
}

PHASE_COLORS = {
    "cross": "#00b894", "f2l1": "#0984e3", "f2l2": "#6c5ce7",
    "f2l3": "#e17055", "f2l4": "#fdcb6e", "oll": "#fd79a8", "pll": "#e84393",
}
PHASE_LABELS = {
    "cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
    "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL",
}

PHASE_NAMES = {
    "cross": "Cross（底十字）",
    "f2l1": "F2L-1（第一组棱角对）",
    "f2l2": "F2L-2（第二组棱角对）",
    "f2l3": "F2L-3（第三组棱角对）",
    "f2l4": "F2L-4（第四组棱角对）",
    "oll": "OLL（顶层朝向）",
    "pll": "PLL（顶层排列）"
}

PHASE_ORDER = ["cross", "f2l1", "f2l2", "f2l3", "f2l4", "oll", "pll"]

TAG_LIBRARIES_JSON = json.dumps({
    "strength": STRENGTH_TAGS,
    "weakness": WEAKNESS_TAGS,
}, ensure_ascii=False)
