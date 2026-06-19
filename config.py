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
    "input": """推荐方式：在「csTimer」标签页连接蓝牙智能魔方练习，然后在「数据管理」中点击「同步csTimer数据」一键导入。

也可手动输入：勾选「智能粘贴」后，从csTimer复制还原数据时自动填入输入框。
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

    "smart_paste": """勾选后自动监听剪贴板，从csTimer复制数据时自动填入输入框。
支持识别csTimer弹窗中的"打乱公式"和"回顾"内容。
多组模式下：先复制打乱再复制回顾，会自动配对到同一组。
已存在的数据不会重复粘贴。
便捷操作：点击弹窗中的"打乱公式"或"回顾"，依次按下ctrl+a+c，即可自动粘贴到对应输入框。
提示：也可通过内嵌csTimer一键同步数据，无需手动复制。""",

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

# ═══ OLL/PLL 公式库 ═══
# 每个 case 的公式列表，第一个为默认显示公式
# 公式开头若含 U/U'/U2/y/y'/y2 操作，表示需要旋转图片
OLL_ALGORITHMS = {
    "1": ["RU2R2'FRF'U2'R'FRF'", "RU'2R2'FRF'U2R'FRF", "RUB'RBR'2U'R'FRF'", "zUR2U'd'RUR'F2U'RUR'", "L'U2L2F'L'FU'2LF'L'F"],
    "2": ["FRUR'U'F'fRUR'U'f'", "U'2F'L'ULUFf'L'U'LUf", "UrUr'U2rU2R'U2RU'r'", "FRUR'U'SRUR'U'f'", "yrUr'U2RU2R'U2rU'r'", "FRUr'U'RUR'M'U'F'", "y2FUr'R2U'R'UrU'R'F'"],
    "3": ["fRUR'U'f'U'FRUR'U'F'", "Ur'R2UR'UrU2r'UR'r", "UfRUR'U'f'U'fRUR'U'2f'", "U'zu'U'2RU'RuR'2u'RuU'", "f'L'U'LUfUF'L'U'LUF", "UMRUR'UrU2r'UM'", "y2FURU'R'F'UFRUR'U'F'"],
    "4": ["fRUR'U'f'UFRUR'U'F'", "R'U2xR'URU'yR'U'R'UR'F", "yr'RU'rU2r'U'RU'R2'r", "UlL'U'rU'2r'U'RU'R'2r", "fRUR'U'yxR'FRUR'U'F'", "UzuU'2R'UR'u'R2uR'u'U", "UMU'rU2r'U'RU'RM'", "y2FURU'R'F'U'FRUR'U'F'"],
    "5": ["r'U2RUR'Ur", "U2zu'R'2URU'Ru", "U2l'U2LUL'Ul", "U2R'F2rUr'FR", "L'U'L2F'L'F2U'F'"],
    "6": ["rU2R'U'RU'r'", "U2zuR2U'R'UR'u'", "U2lU2L'U'LU'l'", "U2RUR2FRF2UF", "y'x'DR2U'R'UR'D'x"],
    "7": ["rUR'URU2r'", "U2R'U2RU2lU'R'U", "L'U2LU2LF'L'F", "U2lUL'ULU'2l'", "U2zuRU'RUR'2u'", "rUr'URU'R'rU'r'"],
    "8": ["U2RU2R'U2R'FRF'", "LU2L'U2L'B'LB", "r'U'RU'R'U2r", "U2zu'R'UR'U'R2u", "y2R'F'rU'r'F2R", "y2R'F'RU'L'ULR'FR"],
    "9": ["RUR'U'R'FR2UR'U'F'", "U2zU'R'UyRU'R'FRUR'", "U2L'U'Lx'zRU'R'FRUR'", "R'U'Ry'x'RU'R'FRUR'x", "R'U'Rr'f'RU'R'rUr'RUR'", "R'U'lz'RU'R'FRUR'", "yF'U'FrU'r'UrUr'", "R'U'F'UFU'RU'R'U2R", "R'U'RyrU'r'UrUr'"],
    "10": ["yFUF'R'FRU'R'F'R", "RUR'UR'FRF'RU'U'R'", "RUR'UR'FRF'RU'U'R'", "RUR'yR'FRU'R'F'R", "U2zURU'yL'ULF'L'U'L", "U2L'U'LULF'L2U'LUF"],
    "11": ["U2M'LUL'ULU2L'EM", "r'R2UR'URU'2R'UrR'", "U2rUR'UR'FRF'RU2r'", "MRUR'URU'2R'UM'", "U2rUR'FRF'RU'2rU2", "U2rUR'UR'FRF'RU2r'"],
    "12": ["M'R'U'RU'R'U2RU'M", "U2lL'2U'LU'L'U2LU'rR'", "rR'2U'RU'R'U2RU'Rr'", "UFRUR'U'F'yFRUR'U'F'", "FRUR2FRy'R2URU2R'", "yFRUR'U'F'yFRUR'U'F'"],
    "13": ["U2fRUR2U'R'URU'f'", "rU'r'U'rUr'F'dR", "rU'r'U'rUr'F'UF", "FURU'R2F'RURU'R'", "UzURF'R2F'R'FRF'U'", "FURU'2R'U'RUR'F'"],
    "14": ["U2f'L'U'L2ULU'L'Uf", "R'FRUR'F'RFU'F'", "R'FRUR'F'Ry'RU'R'", "UzU'R'B'RlURU'R'UF", "U2r'UrUr'U'ryRU'R'", "y2r'UrUr'U'ryRU'R'"],
    "15": ["U2l'U'lL'U'LUl'Ul", "U2R'F'RL'U'LUR'FR", "r'U'rR'U'RUr'Ur", "U2zu'R'uU'R'URu'Ru", "r'U'M'U'RUr'Ur", "U2R'F'RL'U'LUR'FR"],
    "16": ["rUr'RUR'U'rU'r'", "rUMUR'U'rU'r'", "U2R'FRUR'U'F'RU'R'U2R", "U2lUl'LUL'U'lU'l'", "U2zuRu'URU'R'uR'u'", "U2lUl'LUL'U'lU'l'"],
    "17": ["RUR'UR'FRF'U2R'FRF'", "fRUR'U'f'U'RUR'U'R'FRF'", "U2FR'F'R2r'URU'R'U'M'", "y'F'rUr'U'Sr'FrS'", "UzU'R'UR'dR'd'R'U'R", "U2FUR'U'F'UFR2UR'U'F'", "lU'l'f'R2BR'UR'U'f'"],
    "18": ["U2rUR'URU2r2U'RU'R'U2r", "U'RU2R2FRF'U2M'URU'r'", "FRUR'Uy'R'U2R'FRF'", "FRUR'dR'U2R'FRF", "FRUR'dR'U2R'FRF", "zF'U'R'Ul'UR2dR'U'R", "U'rU'r'FUFU'RUR'U'F'", "y2FR'F'RURU'R'UFRUR'U'F'"],
    "19": ["MURUR'U'M'R'FRF'", "r'RURUR'U'rR'2FRF'", "r'U2RUR'Ur2U2R'U'RU'r'", "R'U2FRUR'U'y'R2U2", "r'RURUR'U'rR'2FRF'", "U2zUu'RURU'R'uU'd'RUR'", "R'U2FRUR'U'F2U2FR", "y2FURU'R'2F'U'FURU'F'"],
    "20": ["r'RURUR'U'r2R'2URU'r'", "zuRU'R'E2RUR'U'R'uU'", "MURUR'U'M2URU'r'", "rUR'U'M2URU'R'U'M", "M'UM'UM'UM'U'M'UM'UM'UM'", "M'U'R'U'RUM2'U'R'Ur"],
    "21": ["RU2R'U'RUR'U'RU'R'", "FRUR'U'RUR'U'RUR'U'F'", "URUR'URU'R'URU2R'", "UR'U'RU'R'URU'R'U2R", "zUR2U'R'URU'R'UR'U'", "FRUR'U'3F'"],
    "22": ["RU2R2U'R2U'R2U2R", "R'U2R2UR2UR2U2R'", "RU2'R2'U'R2U'R2'U2R", "zD'RUR'DR'U'R'UR'U'", "fRUR'U'f'FRUR'U'F'", "U2L'U2L2UL2UL2U2L'", "U2FURU'R'F2L'U'LUF"],
    "23": ["x'RUR'DRU'R'D'x", "U'rUR'U'r'FRF'", "Ul'U'LURU'r'F", "U'LFR'F'L'FRF'", "R2D'RU'2R'DRU'2R", "l2U'RD2R'URD2R", "R'U2RFU'R'U'RUF'"],
    "24": ["rUR'U'r'FRF'", "U2l'U'LURU'r'F", "LFR'F'L'FRF'", "rUR'U'L'URU'x'", "U'lUR'DRU'l'F'", "y2R'F'rURU'r'F", "y'x'DRU'R'D'RUR'", "yxD'R'URDR'U'R", "yxR'U'RD'R'URD"],
    "25": ["F'rUR'U'r'FR", "U'R'FRB'R'F'RB", "U'FR'F'rURU'r'", "x'U'R'D'RUl'FR", "U'xUR'U'LURU'r'", "U2R'F'L'FRF'LF", "y2x'RU'R'DRUR'D'", "y'xR'URD'R'U'RD", "xD'R'U'RDR'UR", "yx'DRUR'D'RU'R'"],
    "26": ["U'R'ULU'RUL'", "RU2R'U'RU'R'", "U'R'U'RU'R'U2R", "UL'U'LU'L'U2L", "U2zUR2U'R'UR'U'", "UL'URU'LUR'"],
    "27": ["URUR'URU2R'", "R'U2RUR'UR", "URU'L'UR'U'L", "U2L'U2LUL'UL", "U2zU'R'2URU'RU", "U'LU'R'UL'U'R"],
    "28": ["rUR'U'MURU'R'", "U2M'UMU2M'UM", "y'M'U'MU2M'U'M", "MUM'U2MUM'", "y'r'U'RUM'U'R'UR"],
    "29": ["URUR'U'RU'R'F'U'FRUR'", "MURUR'U'R'FRF'M'", "r2D'rUr'Dr2U'r'U'r", "U2R'FRF'RU2R'U'F'U'F"],
    "30": ["U'L'U'LUL'ULFUF'L'U'L", "MU'L'U'LULF'L'FM'", "y'r'D'rU'r'Dr2U'r'UrUr'", "y2FR'FR2U'R'U'RUR'F2", "R2UR'B'RU'R2URBR'", "fRUR2U'R'UR2U'R'f'", "y2RUR'URU'R'F'U'FURU2R'"],
    "31": ["rF'UFrU'r'U'r", "U2R'U'FURU'R'F'R", "S'L'U'LULF'L'f", "UFR'F'RURUR'U'RU'R'", "U'SRUR'U'f'U'F", "L'U'x'UFrU'r'U'r", "L'd'RdLU'L'B'L", "yxUR'U'lURUR'U'RU'R'", "R'FRUR'U'F2UFR", "yM'URU'r'U'2F'U'2F", "yM'URU'r'y'U2R'U'2R", "R'FRUR'U'y'R2URB"],
    "32": ["RUB'U'R'URBR'", "SRUR'U'R'FRf'", "U2LUF'U'L'ULFL'", "RdL'd'R'UlUl'", "lFU'F'R'FRUl'", "F'fRUR'U'R'FRf"],
    "33": ["RUR'U'R'FRF'", "U2zURU'R'd'RUR'", "FRU'R'URUR'F'", "U2L'U'LULF'L'F", "y'r'U'r'D'rUr'Dr2", "RUR'F'U'FRU'R'"],
    "34": ["F'L'U'LUrUR'U'r'FR", "U2RUR'U'B'R'FRF'B", "U2RUR2U'R'FRURU'F'", "FRUR'U'R'F'rURU'r'", "U2RUR'U'y'r'U'RUM'", "LUL'U'yr'U'RUM'", "R'U'RUyrUR'U'M", "Ur'U'FURU'R'F'RUM'"],
    "35": ["RU'2R2'FRF'RU'2R'", "fRUR'U'f'RUR'URU2R'", "y'R'U2RlU'R'Ul'U2R", "U2zUR2U'd'RUR'dR2U'", "y'R'U'FR'F'R2U'R'U2R"],
    "36": ["R'U'RU'R'URURyR'F'R", "R'U'RU'R'URUlU'R'Ux", "U2L'U'LU'L'ULULF'L'F", "R'U'RU'R'URURB'R'B", "yB'R'U'R2yURU'R'F'R", "y2R'F'U'F2URU'R'F'R", "RUR'U'F'U2FURUR'"],
    "37": ["FRU'R'U'RUR'F'", "FR'F'RURU'R'", "R'FRF'U'F'UF", "y'RU2R'FR'F'R2U2R'", "y'x'U'RUl'U'R'UR", "y'lU'R'Uy'RUR'U'z'", "y2FRU'R'U'RUR'F'", "y'RUR'F'UFRU'R'"],
    "38": ["RUR'URU'R'U'R'FRF'", "U2LUL'ULU'L'U'L'BLB'", "U2LUL'ULU'L'U'L'BLB'"],
    "39": ["yLF'L'U'LUFU'L'", "y'RUR'F'U'FURU2R'", "y'RB'R'U'RUBU'R'", "R'r'D'rU'r'DrUR", "U'LF'L'U'LUFU'L'", "U'f'LFL'U'L'ULS", "U2RB'R'U'RUBU'R'", "rU'r'U'ryRUR'f'", "yrU'r'U'rfRf'r'"],
    "40": ["R'FRUR'U'F'UR", "U2fR'F'RURU'R'S'", "U2L'BLUL'U'B'UL", "U'RrDr'UrD'r'U'R'", "FRUR'U'F'RUR'URU2R", "zu'RuRu'x'U'R'UB", "y2r'UrUr'F'U'Fr"],
    "41": ["U2RUR'URU'2R'FRUR'U'F'", "RU'R'U2RUyRU'R'U'F'", "y'LF'L'FLF'L'FL'U'LUL'U'L", "fRUR'U'f'U'RUR'URU2R'", "U2zUR'U'R2URxUR'U'R'B'", "yRU2'R'U'RU'R2yL'U'LUF", "y2FURU'R'F'R'U2RUR'UR", "y2FUR2DR'U'RD'R2'F'"],
    "42": ["U2R'URU'2R'U'F'UFUR", "R'U'RU'R'U2RFRUR'U'F'", "yR'FRF'R'FRF'RUR'U'RUR'", "MUFRUR'U'F'M'", "L'ULU2L'U'y'L'ULUF", "r'R2yRUR'U'R'UR'r", "yR'U2RUR'UR2yRUR'U'F'", "zU'RUR2U'R'x'U'RURF", "URFR'F'2RUR'U'RUR'"],
    "43": ["f'L'U'LUf", "B'U'R'URB", "U2F'U'L'ULF", "yR'U'F'UFR", "B'U'R'URB", "zF'R'U'Rdl", "y2R'U'FR'F'RUR", "L'U'Br'U'rUL", "y'RUR'F'U'2FRU'R'", "r'U'R'FRF'Ur", "U2F'U'L'ULF"],
    "44": ["fRUR'U'f'", "U2FURU'R'F'", "U2rUx'RU'R'UxU'r'", "y'LdRU'R'F'", "y2LUF'rUr'U'L'", "y'FRU'R'F'L'UL", "y'FRU'R'U'2RUR'F'"],
    "45": ["FRUR'U'F'", "U2fURU'R'f'", "U2F'L'U'LUF", "FR2DR'URD'R2U'F'", "RuRUR'U'rU'", "U2zF'U'R'URb", "yR'F'U'FUR"],
    "46": ["R'U'R'FRF'UR", "yFRUR'y'R'URU2R'", "U2r'F'L'ULU'Fr", "R'U'l'UlF'UR", "RUlU'R'UF'l'", "U2LFU'RUR'F'L'"],
    "47": ["U2zF'U'R'UR2b", "U2F'L'U'LUL'U'LUF", "U2R'U'R'FRF'R'FRF'UR", "U2R'U'l'URU'R'URU'x'UR", "B'R'U'RUR'U'RUB", "U2F'L'U'LUL'U'LUF", "B'R'U'RU2B"],
    "48": ["FRUR'U'2F'", "RU2R'U'RUR'U2R'FRF'", "U2fURU'R'URU'R'f'", "RuRUR'U'RUR'U'rU'", "U2fURU'R'URU'R'f'", "U2zfRz'RU'R'URU'R'f"],
    "49": ["lU'l'2Ul2Ul'2U'l", "RB'R'2FR2BR'2F'R", "U2rU'r2Ur2Ur2U'r", "U2R'FR'F'R2d2y'R'FRF'", "U2R'FR'F'R2U2B'RBR'", "UzU'R'2URU'RzlU"],
    "50": ["r'Ur2U'r'2U'r2Ur'", "U2R'FR2B'R2F'R2BR'", "U2l'Ul2U'l2U'l2Ul'", "RB'RBR'2U2FR'F'R", "U2l'Ul2U'l2U'l2Ul'", "L'BL2F'L2B'L2FL'"],
    "51": ["fRUR'U'RUR'U'f'", "U2FURU'R'URU'R'F'", "yR'U'R'FRF'RU'R'U2R", "U2f'L'U'LUL'U'LUf", "FURU'R'URU'R'F'", "U2fRUR'U'RUR'U'f'"],
    "52": ["RUR'URd'RU'R'F'", "R'U'RU'R'dR'URB", "R'U'RU'R'UF'UFR", "RUR'URU'yRU'R'F'", "R'U'RU'R'dR'UlU", "y2R'F'U'FU'RUR'UR", "y2R'U'xUR'U'R2x'UR"],
    "53": ["r'U2RUR'U'RUR'Ur", "U'r'U'RU'R'URU'R'U2r", "Ul'U'LU'L'ULU'L'U2l", "yr'U2RUR'U'RUR'Ur", "UFRUR'U'F'RUR'U'R'FRF'", "l'U'LU'L'ULU'L'U2l", "r'U'rR'U'RU2r'Ur", "UFRUR'U'RU'R'U'F'L'UL"],
    "54": ["U2lU2L'U'LUL'U'LU'l'", "UrUR'URU'R'URU2r'", "rU2R'U'RUR'U'RU'r'", "rUr'RUR'U'RUR'U'rU'r'", "UF'L'U'LUL'ULU'L'U'LF"],
    "55": ["zUR'2U2R'UR'U'R'2yRUR'", "RU2R2U'RU'R'U2FRF'", "yR'FRURU'R2F'R2U'R'URUR'", "rU2R2FRF'U2r'FRF'", "R'U2R2UR'URU2yR'F'R", "UR'FRURU'R2F'R2U'R'URUR'"],
    "56": ["rUr'URU'R'URU'R'rU'r'", "FRUR'U'RF'rUR'U'r'", "r'U'rU'R'URU'R'URr'Ur", "yfRUR'U'f'FRUR'U'RUR'U'F'", "RBR'ULU'L'ULU'L'RB'R'", "zfRz'RU'R'UB'uRU'R'u'", "fRUR'U'F'RUR'U'R'FRf'"],
    "57": ["RUR'U'M'URU'r'", "M'UM'UM'U2MUMUM", "RUR'U'rR'URU'r'", "zURU'R'uU'RUR'u'", "R'U'RUMU'R'Ur"],
}

PLL_ALGORITHMS = {
    "Ua": [
        "U2RU'RURURU'R'U'R2",
        "U2F2U'LR'F2L'RU'F2",
        "M2UM'U2MUM2",
        "U2M2UMU2M'UM2",
        "R2U'R'U'RURURU'R",
        "U2L2U'L'U'LULULU'L",
        "B2U'M'U2MU'B2",
        "M2UM'U2MU2M'U2MUM2",
        "UR2U'yrU2r'RU2R'y'U'R2",
        "RUR'U'L'U'LU2RU'R'U'L'UL",
    ],
    "Ub": [
        "U2R2URUR'U'R'U'R'UR'",
        "U2F2UR'LF2RL'UF2",
        "M2U'M'U2MU'M2RU'R",
        "U2M2U'MU2M'U'M2",
        "R'UR'U'R'U'R'URUR2",
        "B2UM'U2MUB2",
        "L2ULUL'U'L'U'L'UL'",
        "RU'RURUR'U'R'U'R'U2R'",
        "M2U'M'U2MU2M'U2MU'M2",
        "L'U'LURUR'U2L'ULURU'R'",
        "U2L'UL'U'L'U'L'ULUL2",
    ],
    "H": [
        "M'2UM'2U2M'2UM'2",
        "U'M2U2M2UM2U2M2",
        "F2M2F2U'F2M2F2U",
        "xU2M2U2B'U2M2U2B",
        "R2U2R2U2R2UR2U2R2U2R2U'",
        "LRU2L'R'F'B'U2FB",
        "R2U2RU2R2U2R2U2RU2R2",
        "M2UM2UM2UM2UM2UM2U'",
    ],
    "Z": [
        "UUR'U'RU'RURU'R'URUR2U'R'U",
        "Ux'RU'R'UDR'DU'R'URD2'Fx",
        "UM2UM2UM'U2M2U2M'U2",
        "UM2'U'M'U2'M2'U2'M'UM2'",
        "R2UR2U'R2F2R2U'F2UR2F2",
        "U'M2U2M'U'M2U'M2U'M'U",
        "R'UL'U2D2RU'LR'UL'U2D2RU'L",
        "R'UL'E2LU'RL'UR'E2RU'L'",
        "UR2U'R2UR2x'U2R2FU2F'R2U2",
        "M'UM2UM2UM'U2M2U'",
        "U'l'URU'D'RUD'RU'R'D2",
        "dRUR2U'R'FRURU'RU'R'U'RUR'F'",
        "F2M2F2M2UM2UM2U2",
        "URUR'UR'U'R'URU'R'0U'R2URU2",
        "U'RURB'R'BU'R'fRUR'U'f'",
        "x2yM2US2U'S'M2S",
        "M2UF2M2F2M2U'M2",
        "M2U'M2U'M'U2M2U2M'U2",
        "U'R'U'R'FRF'URU'R'U'F'UFRU2",
        "M2U'M2UM'E2M'E2",
        "y'M2UM2U'M'E2M'E2",
        "yM2UM2UM'E2Mu2M2",
        "M2U'M2U'M'E2Mu2M2",
        "M2U'M2U'ME2M'u2M2",
        "yM2UM2UME2M'u2M2",
    ],
    "Aa": [
        "yx'R2D2R'U'RD2R'UR'",
        "R'FR'B2RF'R'B2R2",
        "x'R'DR'U2RD'R'U2R2",
        "xR'UR'D2RU'R'D2R2",
        "U'xL2D2L'U'LD2L'UL'",
        "U2L'BL'F2LB'L'F2L2",
        "U2zF2RU2R'U2F2L'U2LU2",
        "Uz'U2RU2R'F2U2L'U2LF2",
        "R'U2R2U'L'UR'U'LUR'U2R",
        "UR2F2R'B'RF2R'BR'",
        "y2r'Ur'B'2rU'r'B'2r2",
        "y'RUR'F'rUR'U'r'FR2U'R'",
    ],
    "Ab": [
        "x'RU'RD2R'URD2R2",
        "RB'RF2R'BRF2R2",
        "xRD'RU2R'DRU2R2",
        "U'xR2D2RUR'D2RU'R",
        "U2xLU'LD2L'ULD2L2",
        "UzU2L'U2LF2U2RU2R'F2",
        "z'F2L'U2LU2F2RU2R'U2",
        "U'R'U2RU'L'URU'LUR2U2R",
        "zUR'Dr2U'RUr2'U'D'",
    ],
    "E": [
        "Ux'RU'R'DRUR'D2L'ULDL'U'L",
        "R2UR'U'yRUR'U'*2RUR'y'RU'R2'",
        "xUR'U'LURU'L'URU'LUR'U'L'",
        "xUR'U'LURU'r2'U'RULU'R'U",
        "UxRU'R'DRUR'u2R'URDR'U'R",
        "l'U'L'URU'lUR'U'LURU'l'U",
        "r'R'U'LD'L'ULRU'R'DRU",
        "r2Ur2Dx'RU'R'U3xD'r2U'r2",
        "x'U'RUL'U'R'Ur2UR'U'r'FRF'",
        "U'z'R'FR2UR'B'RU'R2F'RzRBR'",
        "R'UL'D2LU'RL'UR'D2RU'L",
        "RBLB'R'yRLyLB'R'BL'y'R'L'",
        "l'U'r'FRF'RUR'U'LURU'R'F",
        "F'RUR'U'L'URU'l'UR'U'rFR",
    ],
    "T": [
        "RUR'U'R'FR2U'R'U'RUR'F'",
        "U2L'U'LULF'L2ULUL'U'LF",
        "FRU'R'URUR2F'RURU'R'",
        "L2U'L2DF2R2UR2D'F2",
        "R2U'R2DB2L2UL2D'B2",
        "R2'u'R2UR2'yR2uR2'U'R2",
        "R2UR2'U'R2U'DR2'U'R2UR2'D'",
        "zx2U2r'U2rU2xU2rU2r'U2",
    ],
    "F": [
        "UR'U'F'RUR'U'R'FR2U'R'U'RUR'UR",
        "U2RU'R'UR2yRUR'U'xU'R'URU2",
        "R'URU'R2F'U'FUxRUR'U'R2B'",
        "R'URU'R2'F'U'FURU'x'R2U'R'U",
        "R'URU'R2y'R'U'RUyxRUR'U'R2x'",
        "R'U2R'd'R'F'R2U'R'UR'FRU'F",
        "U2R'URU'R'2F'U'FURxUR'U'R2",
        "U2MU2r'Ul'U2rU'R2rU2R2",
    ],
    "V": [
        "R'UR'd'R'F'R2U'R'UR'FRF",
        "R'UR'U'yxR'U'R2x'U'R'UR'FRF",
        "R'UR'U'B'DB'D'B2R'B'RBR",
        "R'UR'U'x2y'R'UR'U'lRU'R'URU",
        "UL'URU'LUL'UR'U'LU2RU2R'",
        "U2RU'L'UR'U'RU'LUR'U2L'U2L",
        "U'R'ULU'RUR'UL'U'RU2LU2L'",
        "LU'R'UL'U'LU'RUL'U2R'U2R",
        "R'UR'U'yz'U'RU'R'U2y'R'U'RUR",
        "R'UR'U'yR'F'R2U'R'UR'FRF",
        "R'UR'U'yR'DR'D'R2F'R'FRF",
        "R'U2RU2LU'R'UL'ULU'RUL'",
        "R'U2RU2LU'R'Ur'FrU'RUr'",
        "RU2R'DRU'RU'RUR2DR'U'RD2",
    ],
    "Y": [
        "FRU'R'U'RUR'F'RUR'U'R'FRF'",
        "R2uR2'UR2D'R'U'RF2'R'UR",
        "FR'FR2U'R'U'RUR'F'RUR'U'F'",
        "R'U'RF2R'URdR2U'R2'U'R2",
        "R2U'R'URU'z'y'L'U'RU'R'U'LUyz",
        "UF'L'ULUL'U'LFL'U'LUL'F'LF",
        "FRU'R'FDR'yxR'U'RzR2yL'd2",
        "z'U2L'U'LUL'y'L'U'RU'R'U'LU",
        "FR'F'RURU'R2U'RUlU'R'U",
        "zU2RUR'U'RyRUL'ULUR'U'",
        "FRU'R'U'RdRUR'B'RU'R2",
        "R'FRF'y'U'R'UR2UR'U'R'FRF'U'",
        "U2zU2R'U2R'U2RBRB'U2BR'B'",
    ],
    "Ja": [
        "U2R'U2RUR'z'R2'UR'DRU'",
        "U2L'R'U2RUR'U2LU'RU",
        "U2F2L'U'rU2l'UR'U'R2",
        "U2R'U2RUR'U2'LU'RUL'",
        "U2xU2r'U'rU2l'UR'U'R2",
        "UR'UL'U2RU'R'U2LRU'",
        "B2'R2U'R2'uR2D'R2'UR2",
        "RU'L'UR'U2LU'L'U2'L",
        "RLd2R'U'Rd2R'UL'",
        "L'UR'U2LU'RUL'UR'U2LU'R",
        "L'UR'U2LU'RUL'UR'U2LU'R",
        "L'U2LUL'U2RU'LUR'",
        "L'U'LFL'U'LULF'L2ULU",
        "xR2FR.F'RU'2r'UrU'2",
    ],
    "Jb": [
        "RU2R'U'RU2L'UR'U'L",
        "RU2R'U'Rd2'R'UL'U'R",
        "U2RLU2L'U'LU2R'UL'U'",
        "RUR'F'RUR'U'R'FR2U'R'U'",
        "U'L'U'RU2L'ULU2L'RU",
        "U2F2'RUR'yr2y'RU'RUR2'",
        "L'URU'LU2R'URU2'R'",
        "U2r2U'L'Ur'U2RB'R'U2",
        "RU'LU2R'ULU'RU'LU2R'UL",
        "L'UR'U2LU'L'U2RL",
    ],
    "Rb": [
        "R'U2RU2R'FRUR'U'R'F'R2'U'",
        "UR2B2U'R'U'RURUB2RU'RU",
        "R'U2RU'y'R'FRB'R'F'Rzx'R'UR'",
        "R'U2R'D'RU'R'DRURU'R'U'RU'",
        "UxR2UlURU'l'U'lU2R'U2R",
    ],
    "Ra": [
        "U2zUR2U'R2UF'U'R'URUFU2R",
        "U'R2B'R'U'R'URBR'U2RU2R'",
        "RU2R'U2RB'R'U'RURBR2'U",
        "RU2R'U2RB'R'U'RUlUR2F",
        "U2R'U'RU2RU2L'R2URU'RLU2R'",
        "U'RUR'F'RU2R'U2R'FRURU2R'U'",
        "RU2R'U'R'F'RU2RU2R'FRU'R'U",
        "RU2RDR'URD'R'U'R'URUR'U",
        "U2LU2L'U2LF'L'U'LULFL2U",
        "RlU'l'U'R'UlUl'U2RU2'R'",
    ],
    "Gc": [
        "UR2'u'RU'RUR'uR2yRU'R'",
        "UR2'u'RU'RUR'uR2BU'B'",
        "UR2'D'FU'FUF'DR2BU'B'",
        "U2F2'D'LU'LUL'DF2RU'R'",
        "L'R'U2LRyLU'RU2L'UR'",
        "U'l'U'U'L'UlF'U'LUFR'FR",
    ],
    "Gd": [
        "U2RUR'y'R2u'RU'R'UR'uR2",
        "U2RUR'F2D'LU'L'UL'DF2",
        "U2l2U'L2U'F2L'U'RU2L'Ulx",
        "ULU'RU2L'UR'yR'L'U2RL",
        "ULU'RU2L'UR'y'L'R'U2LR",
        "U'R'F'RF'U'L'UFR'F'LF2R",
    ],
    "Ga": [
        "UR2'uR'UR'U'Ru'R2y'R'UR",
        "UR2DB'UB'U'BD'R2F'UF",
        "U2F2'DR'UR'U'RD'F2L'UL",
        "RLU2R'L'y'R'UL'U2RU'L",
    ],
    "Gb": [
        "R'U'RyR2uR'URU'Ru'R2",
        "R'U'RB2DL'ULU'LD'B2",
        "U2L'U'Ly'R2'uR'URU'Ru'R2",
        "U'R'UL'U2RU'LyRLU2L'R'",
    ],
    "Nb": [
        "RU'R2'F2U'RF2'R'UF2R2UR'",
        "zU'RD'R2'UR'U'DRD'R2UR'D",
        "zD'RU'R2'DR3U*2",
        "L'UR'U2'LU'L'RUR'U2'LU'RU'",
        "R'URU'R'F'U'FRUR'FR'F'RU'R",
        "zU'RD'R2UR'U'z'RUR'zR2UR'z'RU'",
        "L'UR'zR2UR'Uz'RUR'zR2UR'z'RU'",
        "L'ULU'r'U'F'ULFL'UL'U'rU'L",
        "LU'RU2L'UR'LU'RU2L'UR'U'",
        "R'URU'R'F'U'FRUR'U'R'dRUR'",
    ],
    "Na": [
        "R'UR2B2UR'B2'RU'B2R2'U'R",
        "zDR'UR2D'RU'DR'UR2D'RU'R",
        "U'LU'RU2L'UR'LU'RU2L'UR'",
        "RU'R'UlUFU'R'F'RU'RUl'UR'",
        "LU'L'ULFUF'L'U'LF'LFL'UL'",
        "R'UL'U2RU'LR'UL'U2RU'L",
        "RU'Ld2L'ULR'U'RU2r'Fl'U'y2",
        "LU'RU2L'UR'LU'RU2L'UR'U'",
        "UzR'UR'DR2'U'RUD'R'DR2'U'RD'",
        "RU'Ld2L'ULR'U'RU2L'URU'",
        "F'RUR'U'R'FR2FU'R'U'RUF'R'",
    ],
}

# 公式选择配置文件路径（保存用户选择的公式和自定义公式）
OP_ALGO_CONFIG_FILE = os.path.join(APP_DIR, ".cfop_op_algo.json")
