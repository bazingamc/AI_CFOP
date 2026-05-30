"""
步骤解析和映射工具
"""

import re
from typing import List, Tuple, Dict

from config import COLOR_NAMES, OPPOSITE_COLORS


def parse_moves(move_str: str) -> List[str]:
    """从字符串中提取魔方步骤列表"""
    return re.findall(r"[UDFBRL][2']?", move_str)


def parse_timed_moves(move_str: str) -> List[Tuple[str, int]]:
    """从字符串中提取带时间戳的魔方步骤列表"""
    pattern = r"([UDFBRL][2']?)@(\d+)"
    matches = re.findall(pattern, move_str)
    return [(m[0], int(m[1])) for m in matches]


def validate_orientation(top_color: str, front_color: str) -> str:
    """校验顶面和前面颜色组合是否合理"""
    if top_color == front_color:
        return "顶面和前面不能是同一个颜色！"
    
    if front_color == OPPOSITE_COLORS.get(top_color):
        top_name = COLOR_NAMES.get(top_color, top_color)
        front_name = COLOR_NAMES.get(front_color, front_color)
        return f"顶面({top_name})和前面({front_name})是相对面，不能同时作为顶面和前面！"
    
    return ""


def get_rotation_for_orientation(top_color: str, front_color: str) -> List[str]:
    """根据目标朝向计算从白顶绿前到目标朝向所需的整体旋转序列"""
    rotations = []
    
    if top_color == 'W':
        if front_color == 'G':
            pass
        elif front_color == 'R':
            rotations.append('y')
        elif front_color == 'B':
            rotations.append('y2')
        elif front_color == 'O':
            rotations.append("y'")
    
    elif top_color == 'Y':
        if front_color == 'G':
            rotations.append('z2')
        elif front_color == 'O':
            rotations.extend(['z2', 'y'])
        elif front_color == 'B':
            rotations.append('x2')
        elif front_color == 'R':
            rotations.extend(['z2', "y'"])
    
    elif top_color == 'G':
        if front_color == 'Y':
            rotations.append('x')
        elif front_color == 'R':
            rotations.extend(['x', 'y'])
        elif front_color == 'W':
            rotations.extend(['x', 'y2'])
        elif front_color == 'O':
            rotations.extend(['x', "y'"])
    
    elif top_color == 'B':
        if front_color == 'W':
            rotations.append("x'")
        elif front_color == 'R':
            rotations.extend(["x'", 'y'])
        elif front_color == 'Y':
            rotations.extend(["x'", 'y2'])
        elif front_color == 'O':
            rotations.extend(["x'", "y'"])
    
    elif top_color == 'R':
        if front_color == 'G':
            rotations.append("z'")
        elif front_color == 'Y':
            rotations.extend(["z'", 'y'])
        elif front_color == 'B':
            rotations.extend(["z'", 'y2'])
        elif front_color == 'W':
            rotations.extend(["z'", "y'"])
    
    elif top_color == 'O':
        if front_color == 'G':
            rotations.append('z')
        elif front_color == 'W':
            rotations.extend(['z', 'y'])
        elif front_color == 'B':
            rotations.extend(['z', 'y2'])
        elif front_color == 'Y':
            rotations.extend(['z', "y'"])
    
    return rotations


def get_move_mapping_for_rotation(rotations: List[str]) -> Dict[str, str]:
    """根据整体旋转序列计算步骤映射（用户视角→标准坐标系）

    基于cube.py的view_map机制：
    - view_map[观察面] = 真实面
    - 用户在旋转后的视角下输入步骤，需要映射到标准坐标系
    """
    mapping = {
        'U': 'U', "U'": "U'", 'U2': 'U2',
        'D': 'D', "D'": "D'", 'D2': 'D2',
        'F': 'F', "F'": "F'", 'F2': 'F2',
        'B': 'B', "B'": "B'", 'B2': 'B2',
        'L': 'L', "L'": "L'", 'L2': 'L2',
        'R': 'R', "R'": "R'", 'R2': 'R2',
    }

    # 旋转效果：与cube.py的_apply_single_rotation完全一致
    # 语义：rotation后，观察面X对应真实面Y
    rotation_effects = {
        'x':  {'U': 'F', 'F': 'D', 'D': 'B', 'B': 'U', 'L': 'L', 'R': 'R'},
        "x'": {'U': 'B', 'B': 'D', 'D': 'F', 'F': 'U', 'L': 'L', 'R': 'R'},
        'x2': {'U': 'D', 'D': 'U', 'F': 'B', 'B': 'F', 'L': 'L', 'R': 'R'},
        'y':  {'F': 'R', 'R': 'B', 'B': 'L', 'L': 'F', 'U': 'U', 'D': 'D'},
        "y'": {'F': 'L', 'L': 'B', 'B': 'R', 'R': 'F', 'U': 'U', 'D': 'D'},
        'y2': {'F': 'B', 'B': 'F', 'L': 'R', 'R': 'L', 'U': 'U', 'D': 'D'},
        'z':  {'U': 'L', 'L': 'D', 'D': 'R', 'R': 'U', 'F': 'F', 'B': 'B'},
        "z'": {'U': 'R', 'R': 'D', 'D': 'L', 'L': 'U', 'F': 'F', 'B': 'B'},
        'z2': {'U': 'D', 'D': 'U', 'L': 'R', 'R': 'L', 'F': 'F', 'B': 'B'},
    }

    for rotation in rotations:
        if rotation not in rotation_effects:
            continue
        effect = rotation_effects[rotation]
        new_mapping = {}

        for move, mapped in mapping.items():
            face = mapped[0]
            suffix = mapped[1:] if len(mapped) > 1 else ''
            new_face = effect.get(face, face)
            new_mapping[move] = new_face + suffix

        mapping = new_mapping

    return mapping


def get_inverse_move_mapping(rotations: List[str]) -> Dict[str, str]:
    """根据整体旋转序列计算逆向步骤映射（标准坐标系→用户视角）

    用于将分析结果转换回用户视角显示
    """
    mapping = {
        'U': 'U', "U'": "U'", 'U2': 'U2',
        'D': 'D', "D'": "D'", 'D2': 'D2',
        'F': 'F', "F'": "F'", 'F2': 'F2',
        'B': 'B', "B'": "B'", 'B2': 'B2',
        'L': 'L', "L'": "L'", 'L2': 'L2',
        'R': 'R', "R'": "R'", 'R2': 'R2',
    }

    # 逆向旋转效果：真实面 → 观察面
    # 与get_move_mapping_for_rotation的rotation_effects互逆
    inverse_rotation_effects = {
        'x':  {'F': 'U', 'D': 'F', 'B': 'D', 'U': 'B', 'L': 'L', 'R': 'R'},
        "x'": {'B': 'U', 'D': 'B', 'F': 'D', 'U': 'F', 'L': 'L', 'R': 'R'},
        'x2': {'D': 'U', 'U': 'D', 'B': 'F', 'F': 'B', 'L': 'L', 'R': 'R'},
        'y':  {'R': 'F', 'B': 'R', 'L': 'B', 'F': 'L', 'U': 'U', 'D': 'D'},
        "y'": {'L': 'F', 'B': 'L', 'R': 'B', 'F': 'R', 'U': 'U', 'D': 'D'},
        'y2': {'B': 'F', 'F': 'B', 'R': 'L', 'L': 'R', 'U': 'U', 'D': 'D'},
        'z':  {'L': 'U', 'D': 'L', 'R': 'D', 'U': 'R', 'F': 'F', 'B': 'B'},
        "z'": {'R': 'U', 'D': 'R', 'L': 'D', 'U': 'L', 'F': 'F', 'B': 'B'},
        'z2': {'D': 'U', 'U': 'D', 'R': 'L', 'L': 'R', 'F': 'F', 'B': 'B'},
    }

    for rotation in rotations:
        if rotation not in inverse_rotation_effects:
            continue
        effect = inverse_rotation_effects[rotation]
        new_mapping = {}
        for move, mapped in mapping.items():
            face = move[0]
            suffix = move[1:] if len(move) > 1 else ''
            new_face = effect.get(face, face)
            new_mapping[move] = new_face + suffix
        mapping = new_mapping

    return mapping


def get_orientation_desc(top_color: str, front_color: str) -> str:
    """返回朝向的中文描述"""
    top_name = COLOR_NAMES.get(top_color, top_color)
    front_name = COLOR_NAMES.get(front_color, front_color)
    return f"{top_name}顶{front_name}前（即U面={top_name}色，F面={front_name}色）"
