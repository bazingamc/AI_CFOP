"""
CFOP分析器 - 核心分析逻辑
"""

from typing import List, Dict

from config import (
    PHASE_ORDER, PHASE_NAMES,
    OPPOSITE_COLORS, COLOR_NAMES,
)
from prompts import (
    AI_MAX_RESPONSE_WORDS, AI_PAUSE_THRESHOLD_SEC,
    SYSTEM_PROMPT, USER_SINGLE_TEMPLATE, PHASE_DETAIL_TEMPLATE,
    STRENGTH_TAGS, WEAKNESS_TAGS,
)
from cube import Cube
from move_utils import parse_moves, parse_timed_moves, validate_orientation
from move_utils import get_rotation_for_orientation, get_orientation_desc


import logging

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

def set_logger(logger):
    global log
    log = logger


class CFOPAnalyzer:
    """CFOP还原过程分析器"""

    COLOR_ORDER = ['W', 'Y', 'G', 'B', 'R', 'O']

    # 颜色代码到标准面名的映射（白顶绿前标准坐标系下）
    COLOR_TO_STANDARD_FACE = {
        'W': 'U', 'Y': 'D', 'G': 'F', 'B': 'B', 'R': 'R', 'O': 'L'
    }

    # 自动底色识别的高分阈值，超过此分数即认为底色确定，不再尝试后续颜色
    AUTO_BOTTOM_HIGH_SCORE_THRESHOLD = 500.0

    @classmethod
    def auto_detect_bottom_color(cls, scramble: str, solution: str) -> tuple:
        """自动识别底色，返回 (bottom_color, analyzer, all_scores)

        按照白黄绿蓝红橙的顺序，依次尝试每种底色进行CFOP还原步骤识别，
        对各阶段步数分配进行合理性评分，找到最合理的一种底色。
        如果先识别到一个合理性评分很高的底色，就不再识别后续的底色。

        Returns:
            tuple: (bottom_color, best_analyzer, all_scores)
                bottom_color: 识别到的底色代码 (如 'W')
                best_analyzer: 最佳分析器实例
                all_scores: [(bottom_color, score), ...] 所有尝试过的底色评分
        """
        bottom_candidates = ['W', 'Y', 'G', 'B', 'R', 'O']

        original_level = log.level if log else None
        if log:
            log.setLevel(max(log.level, 30))

        all_scores = []
        best_score = float('-inf')
        best_analyzer = None
        best_bottom = None

        for bottom_color in bottom_candidates:
            try:
                analyzer = cls.from_bottom_color(scramble, solution, bottom_color)
            except (ValueError, Exception):
                continue

            score = cls._score_bottom_color(analyzer)
            all_scores.append((bottom_color, score))

            if log:
                bn = COLOR_NAMES.get(bottom_color, bottom_color)
                log.debug(f"[auto_detect] 底色={bn}, 评分={score:.1f}")

            if score > best_score:
                best_score = score
                best_analyzer = analyzer
                best_bottom = bottom_color

            # 高分阈值：如果评分很高，提前终止
            if score >= cls.AUTO_BOTTOM_HIGH_SCORE_THRESHOLD:
                if log:
                    bn = COLOR_NAMES.get(bottom_color, bottom_color)
                    log.info(f"[auto_detect] 底色={bn} 评分 {score:.1f} 超过阈值，提前确定")
                break

        if log and original_level is not None:
            log.setLevel(original_level)

        if best_analyzer is None:
            # 全部失败，默认白色
            try:
                best_analyzer = cls.from_bottom_color(scramble, solution, 'W')
            except Exception:
                pass
            best_bottom = best_bottom or 'W'

        if log:
            bn = COLOR_NAMES.get(best_bottom, best_bottom)
            log.info(f"[auto_detect] 最终底色={bn}, 评分={best_score:.1f}, 候选评分={all_scores}")

        return best_bottom, best_analyzer, all_scores

    @classmethod
    def _score_bottom_color(cls, analyzer) -> float:
        """对给定底色的分析结果进行合理性评分

        评分依据：
        1. 阶段完整性：7个阶段全部识别到得分最高
        2. 各阶段步数合理性：步数在合理范围内加分，异常步数扣分
        3. R/U/F动作偏好：CFOP还原中R/U/F面动作应占主导
        """
        result = analyzer.analyze()
        score = 0.0

        # 阶段完整性评分
        phase_count = 0
        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            if moves:
                phase_count += 1

        # 7个阶段全部识别到，大幅加分
        if phase_count == 7:
            score += 1000.0
        elif phase_count >= 6:
            score += 600.0
        elif phase_count >= 5:
            score += 300.0
        elif phase_count >= 4:
            score += 100.0
        elif phase_count >= 3:
            score += 0.0
        else:
            # 阶段太少，严重扣分
            score -= 2000.0

        # 各阶段步数合理性评分
        phase_step_ranges = {
            "cross": (1, 12),
            "f2l1": (2, 14), "f2l2": (2, 14),
            "f2l3": (2, 14), "f2l4": (2, 14),
            "oll": (4, 16),
            "pll": (4, 20),
        }

        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            if not moves:
                continue

            step_count = len(moves)
            min_steps, max_steps = phase_step_ranges.get(phase, (1, 30))

            if min_steps <= step_count <= max_steps:
                score += 50.0
            elif step_count > max_steps:
                # 步数过多，逐步扣分
                excess = step_count - max_steps
                score -= excess * 20.0
            else:
                # 步数过少
                score -= 30.0

        # R/U/F动作偏好评分（CFOP还原中R/U/F面动作应占主导）
        total_moves = 0
        ruf_count = 0
        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            for m in moves:
                total_moves += 1
                if m[0] in ('R', 'U', 'F'):
                    ruf_count += 1

        if total_moves > 0:
            ruf_ratio = ruf_count / total_moves
            # R/U/F占比越高越合理
            if ruf_ratio >= 0.6:
                score += 100.0
            elif ruf_ratio >= 0.5:
                score += 50.0
            elif ruf_ratio >= 0.4:
                score += 0.0
            else:
                score -= 100.0

        return score

    @classmethod
    def from_bottom_color(cls, scramble: str, solution: str, bottom_color: str):
        top_color = OPPOSITE_COLORS.get(bottom_color)
        if not top_color:
            raise ValueError(f"无效底色: {bottom_color}")

        candidates = [
            color for color in cls.COLOR_ORDER
            if color not in (bottom_color, top_color)
        ]

        # 使用默认前色进行分析（前色不影响CFOP阶段切分，仅影响步骤映射）
        analyzer = cls(scramble, solution, top_color, candidates[0])
        analyzer.bottom_color = bottom_color
        analyzer.auto_front_candidates = candidates

        # 通过Cross阶段的朝向检测确定初始前色
        orientations = analyzer.detect_phase_orientations()
        initial_front = orientations.get("cross", candidates[0])

        if initial_front != candidates[0]:
            # 重新用检测到的前色构建分析器
            analyzer = cls(scramble, solution, top_color, initial_front)
            analyzer.bottom_color = bottom_color
            analyzer.auto_front_candidates = candidates

        analyzer.auto_front_score = 0
        analyzer.auto_front_scores = [(f, 0) for f in candidates]

        if log:
            bottom_name = COLOR_NAMES.get(bottom_color, bottom_color)
            front_name = COLOR_NAMES.get(analyzer.front_color, analyzer.front_color)
            log.info(
                f"[CFOPAnalyzer] 初始前色选择: 底色={bottom_name}, "
                f"前色={front_name}（Cross朝向检测）"
            )

        return analyzer

    @staticmethod
    def _score_moves_for_cross(moves: List[str]) -> float:
        """Cross专用RUF评分：D面动作为中性

        Cross还原中D面操作是自然的（在底面放置棱块），
        不应像其他阶段那样扣分。
        评分前先消除逆步骤对（如R R'），避免噪声干扰。
        """
        simplified = CFOPAnalyzer._simplify_moves(moves)
        face_weights = {
            'R': 3.0, 'U': 1.4, 'F': 1.8,
            'L': -2.4, 'B': -1.4, 'D': 0.0,
        }
        score = 0.0
        for move in simplified:
            face = move[0]
            score += face_weights.get(face, 0)
            if len(move) > 1 and move[1] == '2':
                score -= 0.2
        return score

    @staticmethod
    def _simplify_moves(moves: List[str]) -> List[str]:
        """消除相邻的逆步骤对（如R R'、F F'、U2 U2等）

        反复扫描直到无法继续消除，处理非相邻但抵消的情况。
        """
        if not moves:
            return []

        def _inverse(move: str) -> str:
            if len(move) == 1:
                return move + "'"
            elif move[1] == "'":
                return move[0]
            elif move[1] == "2":
                return move  # X2的逆还是X2
            return move

        result = list(moves)
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(result) - 1:
                if result[i] == _inverse(result[i + 1]):
                    result.pop(i + 1)
                    result.pop(i)
                    changed = True
                else:
                    i += 1
        return result

    def __init__(self, scramble: str, solution: str, top_color: str = 'W', front_color: str = 'G'):
        orientation_error = validate_orientation(top_color, front_color)
        if orientation_error:
            raise ValueError(orientation_error)
        
        self.scramble = parse_moves(scramble)
        self.solution = parse_timed_moves(solution)
        parsed_moves = [m for m, _ in self.solution]
        log.info(f"[CFOPAnalyzer] 初始化: 打乱={len(self.scramble)}步, 还原={len(parsed_moves)}步, 朝向={top_color}{front_color}")
        
        self.cube = Cube()
        self.top_color = top_color
        self.front_color = front_color
        self.bottom_color = OPPOSITE_COLORS.get(top_color)
        self.auto_front_score = None
        self.auto_front_scores = []
        self.auto_front_candidates = []
        
        self.rotations = get_rotation_for_orientation(top_color, front_color)
        log.debug(f"[CFOPAnalyzer] 朝向旋转序列: {self.rotations if self.rotations else '(无旋转，白顶绿前)'}")
        
        self.analysis_view_map = self._build_analysis_view_map()
        self.output_mapping = self._build_output_mapping()
        log.debug(f"[CFOPAnalyzer] CFOP判定观察view_map: {self.analysis_view_map}")
        log.debug(f"[CFOPAnalyzer] 输出步骤映射表: {self.output_mapping}")

        self._apply_scramble()
        
        self.cross_moves = []
        self.f2l_moves = [[], [], [], []]
        self.f2l_order = []
        self.oll_moves = []
        self.pll_moves = []
        self.phase_timestamps = {}
        self.phase_timed_moves = {}
        self.phase_standard_moves = {}
        self.phase_standard_timed_moves = {}
        self._analyze_result = None
        self._phase_orientations = None
        self._phase_rotations = None
    
    def _apply_scramble(self):
        for move in self.scramble:
            self.cube.apply_standard_move(move)
        self.cube.view_map = self.analysis_view_map.copy()

    def _build_analysis_view_map(self) -> Dict[str, str]:
        view_cube = Cube()
        for rotation in self.rotations:
            view_cube.apply_rotation(rotation)
        return view_cube.view_map.copy()

    def _build_output_mapping(self) -> Dict[str, str]:
        real_to_view = {real: view for view, real in self.analysis_view_map.items()}
        mapping = {}
        for face in "UDFBRL":
            view_face = real_to_view.get(face, face)
            mapping[face] = view_face
            mapping[face + "'"] = view_face + "'"
            mapping[face + "2"] = view_face + "2"
        return mapping
    
    def _map_move(self, move: str) -> str:
        return self.output_mapping.get(move, move)

    def _score_moves_for_ruf(self, moves: List[str]) -> float:
        face_weights = {
            'R': 3.0, 'U': 1.4, 'F': 1.8,
            'L': -2.4, 'B': -1.4, 'D': -3.0,
        }
        score = 0.0
        for move in moves:
            face = move[0]
            score += face_weights.get(face, 0)
            if len(move) > 1 and move[1] == '2':
                score -= 0.2

        r_count = sum(1 for m in moves if m[0] == 'R')
        l_count = sum(1 for m in moves if m[0] == 'L')
        score += (r_count - l_count) * 1.2
        return score

    def _score_phase_start(self, move: str) -> float:
        if not move:
            return 0.0
        return {
            'R': 4.0, 'U': 1.0, 'F': 2.0,
            'L': -3.0, 'B': -2.0, 'D': -4.0,
        }.get(move[0], 0.0)

    def _build_output_mapping_for_front(self, front_color: str) -> Dict[str, str]:
        """为指定前色构建输出映射（标准坐标系→用户视角）"""
        rotations = get_rotation_for_orientation(self.top_color, front_color)
        view_cube = Cube()
        for rotation in rotations:
            view_cube.apply_rotation(rotation)
        view_map = view_cube.view_map.copy()

        real_to_view = {real: view for view, real in view_map.items()}
        mapping = {}
        for face in "UDFBRL":
            view_face = real_to_view.get(face, face)
            mapping[face] = view_face
            mapping[face + "'"] = view_face + "'"
            mapping[face + "2"] = view_face + "2"
        return mapping

    @staticmethod
    def _get_y_rotation_between_fronts(bottom_color: str, front1: str, front2: str) -> str:
        """计算从前色front1到前色front2所需的y转体

        底色确定后，还原过程中只能进行y/y2/y'转体。
        通过构建front1的观察坐标系，找到front2对应的观察面位置，
        从而确定所需的y转体。

        Returns:
            str: 'y', 'y2', "y'" 或 ''（无转体）
        """
        if front1 == front2:
            return ''

        top_color = OPPOSITE_COLORS[bottom_color]

        # 构建front1朝向的view_map
        rotations1 = get_rotation_for_orientation(top_color, front1)
        view_cube = Cube()
        for r in rotations1:
            view_cube.apply_rotation(r)

        # 将front2颜色转换为标准面名
        standard_face2 = CFOPAnalyzer.COLOR_TO_STANDARD_FACE.get(front2, front2)

        # 在front1的观察坐标系中，找到front2对应的观察面位置
        target_view_face = None
        for view_face, real_face in view_cube.view_map.items():
            if real_face == standard_face2 and view_face in ('F', 'R', 'B', 'L'):
                target_view_face = view_face
                break

        if target_view_face is None:
            return ''

        # 观察面位置到y转体的映射
        # y: 将R面转到F位置（观察者向右转，右面变前面）
        # y': 将L面转到F位置（观察者向左转，左面变前面）
        # y2: 将B面转到F位置
        y_map = {'F': '', 'R': 'y', 'B': 'y2', 'L': "y'"}
        return y_map.get(target_view_face, '')

    def detect_phase_orientations(self) -> Dict[str, str]:
        """检测每个CFOP阶段的最佳前色（独立于其他阶段）

        对每个阶段的标准步骤，分别尝试4个候选前色，
        通过RUF偏好评分找到最合理的观察朝向，
        从而识别还原过程中的转体。

        Returns:
            Dict[str, str]: 阶段名→最佳前色代码
        """
        if self._phase_orientations is not None:
            return self._phase_orientations

        self.analyze()

        candidates = [
            color for color in self.COLOR_ORDER
            if color not in (self.bottom_color, self.top_color)
        ]

        orientations = {}

        for phase in PHASE_ORDER:
            standard_moves = self.phase_standard_moves.get(phase, [])
            if not standard_moves:
                # 无步骤的阶段，沿用前一阶段的前色或默认前色
                if orientations:
                    prev_phase = PHASE_ORDER[PHASE_ORDER.index(phase) - 1]
                    orientations[phase] = orientations.get(prev_phase, self.front_color)
                else:
                    orientations[phase] = self.front_color
                continue

            # 步骤太少（≤2步）时RUF评分不可靠，沿用上一阶段前色
            if len(standard_moves) <= 2:
                if orientations:
                    prev_phase = PHASE_ORDER[PHASE_ORDER.index(phase) - 1]
                    orientations[phase] = orientations.get(prev_phase, self.front_color)
                else:
                    orientations[phase] = self.front_color
                continue

            best_front = self.front_color
            best_score = float('-inf')

            # 获取上一阶段的前色，用于计算转体惩罚
            prev_front = orientations.get(
                PHASE_ORDER[PHASE_ORDER.index(phase) - 1], self.front_color
            ) if orientations else self.front_color

            for front_color in candidates:
                mapping = self._build_output_mapping_for_front(front_color)
                mapped_moves = [mapping.get(m, m) for m in standard_moves]

                # Cross阶段使用专用评分（D面中性，先简化消除逆步骤对）
                # Cross首步不代表朝向，不使用_score_phase_start
                if phase == "cross":
                    score = self._score_moves_for_cross(mapped_moves)
                else:
                    score = self._score_moves_for_ruf(mapped_moves)
                    if mapped_moves:
                        score += self._score_phase_start(mapped_moves[0])

                # 转体惩罚：如果此朝向与上一阶段不同，需要转体，减分
                if front_color != prev_front:
                    # 计算转体量（y/y'/y2），不同转体量惩罚不同
                    y_rot = self._get_y_rotation_between_fronts(
                        self.bottom_color, prev_front, front_color
                    )
                    if y_rot == 'y2':
                        score -= 8.0  # y2转体成本最高
                    elif y_rot in ('y', "y'"):
                        score -= 5.0  # y/y'转体成本中等
                    else:
                        score -= 3.0  # 其他转体

                if score > best_score:
                    best_score = score
                    best_front = front_color

            orientations[phase] = best_front

        self._phase_orientations = orientations

        # 计算相邻阶段之间的y转体
        self._phase_rotations = {}
        prev_front = orientations.get(PHASE_ORDER[0], self.front_color)
        for phase in PHASE_ORDER:
            current_front = orientations.get(phase, self.front_color)
            self._phase_rotations[phase] = self._get_y_rotation_between_fronts(
                self.bottom_color, prev_front, current_front
            )
            prev_front = current_front

        if log:
            rotation_summary = []
            for phase in PHASE_ORDER:
                front = orientations.get(phase, self.front_color)
                rot = self._phase_rotations.get(phase, '')
                front_name = COLOR_NAMES.get(front, front)
                rotation_summary.append(f"{phase}={front_name}前{('(' + rot + ')') if rot else ''}")
            log.info(f"[转体识别] 各阶段朝向: {', '.join(rotation_summary)}")

        return orientations

    def get_phase_oriented_moves(self) -> Dict[str, tuple]:
        """获取按阶段朝向映射后的步骤和转体信息

        Returns:
            Dict[str, tuple]: 阶段名→(oriented_moves, y_rotation, front_color)
                oriented_moves: 按该阶段最佳前色映射后的步骤列表
                y_rotation: 从上一阶段到本阶段的y转体（如 'y', "y'", 'y2', ''）
                front_color: 本阶段的最佳前色
        """
        orientations = self.detect_phase_orientations()
        result = {}

        for phase in PHASE_ORDER:
            standard_moves = self.phase_standard_moves.get(phase, [])
            front_color = orientations.get(phase, self.front_color)
            y_rotation = self._phase_rotations.get(phase, '')

            if standard_moves:
                mapping = self._build_output_mapping_for_front(front_color)
                oriented_moves = [mapping.get(m, m) for m in standard_moves]
            else:
                oriented_moves = []

            result[phase] = (oriented_moves, y_rotation, front_color)

        return result

    def get_phase_oriented_timed_moves(self) -> Dict[str, tuple]:
        """获取按阶段朝向映射后的带时间戳步骤

        Returns:
            Dict[str, tuple]: 阶段名→(oriented_timed_moves, y_rotation, front_color)
                oriented_timed_moves: [(mapped_move, timestamp), ...]
        """
        orientations = self.detect_phase_orientations()
        result = {}

        for phase in PHASE_ORDER:
            standard_timed_moves = self.phase_standard_timed_moves.get(phase, [])
            front_color = orientations.get(phase, self.front_color)
            y_rotation = self._phase_rotations.get(phase, '')

            if standard_timed_moves:
                mapping = self._build_output_mapping_for_front(front_color)
                oriented_timed_moves = [
                    (mapping.get(m, m), ts) for m, ts in standard_timed_moves
                ]
            else:
                oriented_timed_moves = []

            result[phase] = (oriented_timed_moves, y_rotation, front_color)

        return result

    def analyze(self) -> Dict:
        if self._analyze_result is not None:
            return self._analyze_result

        mapped_solution = [self._map_move(m) for m, _ in self.solution]
        log.debug(f"[CFOPAnalyzer] 还原步骤({len(mapped_solution)}步): {' '.join(mapped_solution)}")

        cube = self.cube.copy()
        cross_done = False
        completed_f2l_slots = []  # 按完成顺序存储: [(slot_num, moves, timed_moves), ...]
        f2l_done = [False, False, False, False]
        oll_done = False
        current_phase = "cross"
        current_moves = []
        current_timed_moves = []
        current_standard_moves = []
        current_standard_timed_moves = []
        phase_start_time = self.solution[0][1] if self.solution else 0
        self.phase_timestamps = {"cross": {"start": phase_start_time, "end": 0}}
        self.phase_timed_moves = {"cross": []}
        self.phase_standard_moves = {"cross": []}
        self.phase_standard_timed_moves = {"cross": []}
        pending_phase_start = None

        # F2L物理槽位：基于初始view_map计算4个物理F2L槽位的角块/棱块索引
        # 物理槽位不随y转体变化，避免view_map不同步导致的检测错误
        physical_f2l_slots = None

        step_count = 0
        for original_move, timestamp in self.solution:
            step_count += 1
            if pending_phase_start is not None:
                self.phase_timestamps[pending_phase_start]["start"] = timestamp
                pending_phase_start = None

            mapped_move = self._map_move(original_move)
            cube.apply_standard_move(original_move)
            current_moves.append(mapped_move)
            current_timed_moves.append((mapped_move, timestamp))
            current_standard_moves.append(original_move)
            current_standard_timed_moves.append((original_move, timestamp))

            if current_phase == "cross" and cube.is_cross_solved():
                self.cross_moves = current_moves.copy()
                self.phase_timestamps["cross"]["end"] = timestamp
                self.phase_timed_moves["cross"] = current_timed_moves.copy()
                self.phase_standard_moves["cross"] = current_standard_moves.copy()
                self.phase_standard_timed_moves["cross"] = current_standard_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] Cross完成: {len(self.cross_moves)}步")
                current_moves = []
                current_timed_moves = []
                current_standard_moves = []
                current_standard_timed_moves = []
                current_phase = "f2l"
                cross_done = True
                # 计算F2L物理槽位（基于初始view_map，不随y转体变化）
                real_d = self.analysis_view_map.get('D', 'D')
                real_f = self.analysis_view_map.get('F', 'F')
                real_r = self.analysis_view_map.get('R', 'R')
                real_l = self.analysis_view_map.get('L', 'L')
                real_b = self.analysis_view_map.get('B', 'B')
                physical_f2l_slots = [
                    cube._get_f2l_slot_pieces(real_d, real_f, real_r),  # 物理槽1: FR
                    cube._get_f2l_slot_pieces(real_d, real_f, real_l),  # 物理槽2: FL
                    cube._get_f2l_slot_pieces(real_d, real_b, real_l),  # 物理槽3: BL
                    cube._get_f2l_slot_pieces(real_d, real_b, real_r),  # 物理槽4: BR
                ]
                log.debug(f"[CFOPAnalyzer] F2L物理槽位: {physical_f2l_slots}")
                self.phase_timestamps["f2l1"] = {"start": 0, "end": 0}
                self.phase_timed_moves["f2l1"] = []
                self.phase_standard_moves["f2l1"] = []
                self.phase_standard_timed_moves["f2l1"] = []
                pending_phase_start = "f2l1"
            elif current_phase == "f2l":
                # 直接检查物理F2L槽位（不依赖view_map，避免y转体导致检测错误）
                slot_found = None
                for i in range(4):
                    if not f2l_done[i]:
                        corner, edge = physical_f2l_slots[i]
                        if (cube.cp[corner] == corner and cube.co[corner] == 0 and
                                cube.ep[edge] == edge and cube.eo[edge] == 0):
                            slot_found = i + 1
                            break

                # 验证：新槽位完成时，所有已完成的槽位必须仍然处于完成状态
                # 防止某步骤暂时完成一个槽位但破坏了之前已完成的槽位
                if slot_found is not None:
                    all_prev_solved = True
                    for i in range(4):
                        if f2l_done[i]:
                            corner, edge = physical_f2l_slots[i]
                            if not (cube.cp[corner] == corner and cube.co[corner] == 0 and
                                    cube.ep[edge] == edge and cube.eo[edge] == 0):
                                all_prev_solved = False
                                log.debug(f"[CFOPAnalyzer] 物理槽{slot_found}已解决，但物理槽{i+1}被破坏，暂不标记完成")
                                break
                    if not all_prev_solved:
                        slot_found = None

                if slot_found is not None:
                    slot_idx = slot_found - 1  # 转为0-based索引
                    f2l_done[slot_idx] = True

                    # 记录到按完成顺序的列表
                    completed_f2l_slots.append((
                        slot_found,
                        current_moves.copy(),
                        current_timed_moves.copy()
                    ))

                    f2l_num = len(completed_f2l_slots)  # 第几个完成的F2L（1-based）
                    slot_names = {1: 'FR', 2: 'FL', 3: 'BL', 4: 'BR'}

                    log.info(f"[CFOPAnalyzer] F2L-{f2l_num}({slot_names[slot_found]})完成: {len(current_moves)}步")

                    # 记录时间戳（使用动态的f2l序号）
                    phase_key = f"f2l{f2l_num}"
                    self.phase_timestamps[phase_key]["end"] = timestamp
                    self.phase_timed_moves[phase_key] = current_timed_moves.copy()
                    self.phase_standard_moves[phase_key] = current_standard_moves.copy()
                    self.phase_standard_timed_moves[phase_key] = current_standard_timed_moves.copy()

                    current_moves = []
                    current_timed_moves = []
                    current_standard_moves = []
                    current_standard_timed_moves = []

                    if all(f2l_done):
                        # 检查是否跳O：F2L-4完成的同时OLL也完成了
                        if cube.is_oll_solved():
                            # 跳O：OLL步数为0，直接进入PLL
                            current_phase = "pll"
                            self.oll_moves = []
                            self.phase_timestamps["oll"] = {"start": timestamp, "end": timestamp}
                            self.phase_timed_moves["oll"] = []
                            self.phase_standard_moves["oll"] = []
                            self.phase_standard_timed_moves["oll"] = []
                            self.phase_timestamps["pll"] = {"start": 0, "end": 0}
                            self.phase_timed_moves["pll"] = []
                            self.phase_standard_moves["pll"] = []
                            self.phase_standard_timed_moves["pll"] = []
                            pending_phase_start = "pll"
                            log.info(f"[CFOPAnalyzer] 跳O: F2L-4完成时OLL已完成，OLL为0步，直接进入PLL")
                        else:
                            current_phase = "oll"
                            self.phase_timestamps["oll"] = {"start": 0, "end": 0}
                            self.phase_timed_moves["oll"] = []
                            self.phase_standard_moves["oll"] = []
                            self.phase_standard_timed_moves["oll"] = []
                            pending_phase_start = "oll"
                            log.debug(f"[CFOPAnalyzer] 所有F2L完成，进入OLL阶段")
                    else:
                        next_f2l_num = f2l_num + 1
                        next_key = f"f2l{next_f2l_num}"
                        self.phase_timestamps[next_key] = {"start": 0, "end": 0}
                        self.phase_timed_moves[next_key] = []
                        self.phase_standard_moves[next_key] = []
                        self.phase_standard_timed_moves[next_key] = []
                        pending_phase_start = next_key
            elif current_phase == "oll" and cube.is_oll_solved():
                self.oll_moves = current_moves.copy()
                self.phase_timestamps["oll"]["end"] = timestamp
                self.phase_timed_moves["oll"] = current_timed_moves.copy()
                self.phase_standard_moves["oll"] = current_standard_moves.copy()
                self.phase_standard_timed_moves["oll"] = current_standard_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] OLL完成: {len(self.oll_moves)}步")
                current_moves = []
                current_timed_moves = []
                current_standard_moves = []
                current_standard_timed_moves = []
                oll_done = True
                # 检查是否跳P：OLL完成的同时PLL也完成了
                if cube.is_pll_solved():
                    # 跳P：PLL步数为0
                    current_phase = "pll"
                    self.pll_moves = []
                    self.phase_timestamps["pll"] = {"start": timestamp, "end": timestamp}
                    self.phase_timed_moves["pll"] = []
                    self.phase_standard_moves["pll"] = []
                    self.phase_standard_timed_moves["pll"] = []
                    log.info(f"[CFOPAnalyzer] 跳P: OLL完成时PLL已完成，PLL为0步")
                else:
                    current_phase = "pll"
                    self.phase_timestamps["pll"] = {"start": 0, "end": 0}
                    self.phase_timed_moves["pll"] = []
                    self.phase_standard_moves["pll"] = []
                    self.phase_standard_timed_moves["pll"] = []
                    pending_phase_start = "pll"
            elif current_phase == "pll" and cube.is_pll_solved():
                self.pll_moves = current_moves.copy()
                self.phase_timestamps["pll"]["end"] = timestamp
                self.phase_timed_moves["pll"] = current_timed_moves.copy()
                self.phase_standard_moves["pll"] = current_standard_moves.copy()
                self.phase_standard_timed_moves["pll"] = current_standard_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] PLL完成: {len(self.pll_moves)}步")
                current_moves = []
                current_timed_moves = []
                current_standard_moves = []
                current_standard_timed_moves = []

        f2l_result_summary = [slot_data[1] for slot_data in completed_f2l_slots]
        log.info(f"[CFOPAnalyzer] 分析完成: Cross={len(self.cross_moves)}步, F2L={[len(m) for m in f2l_result_summary]}步, OLL={len(self.oll_moves)}步, PLL={len(self.pll_moves)}步")

        result = {"cross": self.cross_moves, "oll": self.oll_moves, "pll": self.pll_moves}
        # 按完成顺序输出F2L（F2L-1是第一个完成的，不一定是FR槽位）
        for i, slot_data in enumerate(completed_f2l_slots):
            result[f"f2l{i+1}"] = slot_data[1]  # slot_data = (slot_num, moves, timed_moves)
        for i in range(len(completed_f2l_slots), 4):
            result[f"f2l{i+1}"] = []

        self._analyze_result = result
        return result

    @staticmethod
    def _apply_y_to_view_map(view_map: Dict[str, str], times: int = 1) -> Dict[str, str]:
        """对view_map应用y旋转（不改变cube状态，只改变观察坐标系）

        Args:
            view_map: 当前的观察面→真实面映射
            times: y旋转次数（1=y, 2=y2, 3=y'）

        Returns:
            新的view_map
        """
        result = view_map.copy()
        for _ in range(times):
            old = result.copy()
            result['F'] = old['R']
            result['R'] = old['B']
            result['B'] = old['L']
            result['L'] = old['F']
        return result

    def _try_f2l_with_y_rotations(self, cube: Cube, f2l_done: List[bool],
                                   current_view_map: Dict[str, str]):
        """尝试4个y方向的view_map来检测F2L槽位完成

        当固定view_map下没有检测到新槽位完成时，尝试y/y'/y2方向，
        因为用户可能做了y转体。

        Args:
            cube: 当前魔方状态
            f2l_done: 各槽位是否已完成
            current_view_map: 当前的view_map

        Returns:
            (slot_found, best_view_map) 或 (None, None)
        """
        original_view_map = cube.view_map.copy()

        for y_times in range(1, 4):  # y, y2, y'
            rotated_map = self._apply_y_to_view_map(current_view_map, y_times)
            cube.view_map = rotated_map

            for i in range(4):
                if not f2l_done[i] and cube.is_f2l_solved(i + 1):
                    best_view_map = rotated_map
                    cube.view_map = original_view_map
                    log.debug(f"[CFOPAnalyzer] F2L槽位{i+1}在y*{y_times}方向检测到完成")
                    return i + 1, best_view_map

        cube.view_map = original_view_map
        return None, None

    def _merge_moves(self, moves: List[str]) -> List[str]:
        if not moves:
            return []
        result = []
        i = 0
        while i < len(moves):
            if i + 1 < len(moves) and moves[i] == moves[i + 1]:
                face = moves[i][0]
                result.append(face + '2')
                i += 2
            else:
                result.append(moves[i])
                i += 1
        return result

    @staticmethod
    def merge_timed_moves(timed_moves: List[tuple], gap_threshold_ms: float = 300.0,
                          middle_gap_threshold_ms: float = 100.0) -> List[tuple]:
        """合并带时间戳的步骤，相同相邻步骤在间隔<=gap_threshold_ms时合并为X2

        注意：不对面步骤合并为中层旋转(M/S/E)，因为 L' R ≠ M（L'R旋转两个外层面，M只旋转中间层）

        Args:
            timed_moves: [(move, timestamp_ms), ...]
            gap_threshold_ms: 同面合并间隔阈值（毫秒），默认300ms
            middle_gap_threshold_ms: 未使用，保留参数兼容性

        Returns:
            [(merged_move, timestamp_ms), ...]
        """
        if not timed_moves:
            return []

        result = []
        i = 0
        while i < len(timed_moves):
            move, ts = timed_moves[i]

            # 尝试同面合并 (R R → R2)
            if i + 1 < len(timed_moves):
                next_move, next_ts = timed_moves[i + 1]
                gap = next_ts - ts
                if move == next_move and gap <= gap_threshold_ms:
                    result.append((move[0] + '2', ts))
                    i += 2
                    continue

            result.append((move, ts))
            i += 1
        return result
    
    def format_output(self, include_timing: bool = True, include_orientation: bool = False) -> str:
        oriented_timed = self.get_phase_oriented_timed_moves()
        output = []

        if include_orientation:
            bottom_name = COLOR_NAMES.get(self.bottom_color, self.bottom_color)
            front_name = COLOR_NAMES.get(self.front_color, self.front_color)
            output.append(f"底色：{bottom_name} 前色：{front_name}")

        for phase in PHASE_ORDER:
            oriented_moves_list, y_rotation, front_color = oriented_timed.get(phase, ([], '', self.front_color))
            if not oriented_moves_list:
                continue

            # 使用带时间间隔判断的合并
            merged_timed = self.merge_timed_moves(oriented_moves_list)
            merged = "".join(m for m, _ in merged_timed)
            # 在公式前插入转体标识
            if y_rotation:
                merged = y_rotation + ' ' + merged

            phase_label = {
                "cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
                "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL"
            }.get(phase, phase)

            output.append(f"【{phase_label}】:{merged}")

            if include_timing:
                stats = self.get_phase_stats()
                max_pauses = self._calculate_max_pauses()
                s = stats.get(phase, {})
                exec_time = s.get("time", 0)
                obs_time = s.get("observation_time", 0)
                max_pause = max_pauses.get(phase, 0)
                total_time = exec_time + (obs_time if obs_time else 0)
                if obs_time > 0:
                    output.append(f"  整体用时:{total_time:.2f}s | 观察时间:{obs_time:.2f}s | 执行时间:{exec_time:.2f}s | 最大卡顿:{max_pause:.2f}s")
                else:
                    output.append(f"  整体用时:{total_time:.2f}s | 执行时间:{exec_time:.2f}s | 最大卡顿:{max_pause:.2f}s")

        return "\n".join(output)
    
    def get_phase_stats(self) -> Dict:
        oriented_timed = self.get_phase_oriented_timed_moves()
        stats = {}
        for phase in PHASE_ORDER:
            oriented_moves_list, y_rotation, front_color = oriented_timed.get(phase, ([], '', self.front_color))
            # 使用带时间间隔判断的合并
            merged_timed = self.merge_timed_moves(oriented_moves_list)
            oriented_moves = [m for m, _ in merged_timed]
            step_count = len(oriented_moves)
            if phase in self.phase_timestamps:
                ts = self.phase_timestamps[phase]
                duration_s = (ts["end"] - ts["start"]) / 1000.0
                tps = step_count / duration_s if duration_s > 0 else 0
            else:
                duration_s = 0
                tps = 0
            stutter_count = self._calculate_stutter_count(phase)
            wasted_moves = self._calculate_wasted_moves(oriented_moves)
            stats[phase] = {
                "moves": oriented_moves, "steps": step_count, "time": duration_s,
                "tps": tps, "stutter_count": stutter_count, "wasted_moves": wasted_moves,
                "y_rotation": y_rotation, "front_color": front_color,
            }

        observation_times = self._calculate_observation_times()
        for phase, obs_time in observation_times.items():
            if phase in stats:
                stats[phase]["observation_time"] = obs_time

        return stats
    
    def _calculate_observation_times(self) -> Dict[str, float]:
        observation_times = {}
        phase_order_with_prev = [
            ("f2l1", "cross"), ("f2l2", "f2l1"), ("f2l3", "f2l2"),
            ("f2l4", "f2l3"), ("oll", "f2l4"), ("pll", "oll"),
        ]
        
        for current_phase, prev_phase in phase_order_with_prev:
            if current_phase in self.phase_timestamps and prev_phase in self.phase_timestamps:
                current_start = self.phase_timestamps[current_phase]["start"]
                prev_end = self.phase_timestamps[prev_phase]["end"]
                obs_time = (current_start - prev_end) / 1000.0
                observation_times[current_phase] = obs_time if obs_time > 0 else 0
            else:
                observation_times[current_phase] = 0
        
        return observation_times
    
    def _calculate_max_pauses(self) -> Dict[str, float]:
        max_pauses = {}
        for phase in PHASE_ORDER:
            timed_moves = self.phase_timed_moves.get(phase, [])
            if len(timed_moves) < 2:
                max_pauses[phase] = 0
                continue
            
            max_pause = 0
            for i in range(1, len(timed_moves)):
                pause = (timed_moves[i][1] - timed_moves[i-1][1]) / 1000.0
                if pause > max_pause:
                    max_pause = pause
            max_pauses[phase] = max_pause
        
        return max_pauses
    
    def _calculate_stutter_count(self, phase: str) -> int:
        timed_moves = self.phase_timed_moves.get(phase, [])
        if len(timed_moves) < 2:
            return 0
        count = 0
        for i in range(1, len(timed_moves)):
            pause = (timed_moves[i][1] - timed_moves[i-1][1]) / 1000.0
            if pause > AI_PAUSE_THRESHOLD_SEC:
                count += 1
        return count
    
    def _calculate_wasted_moves(self, moves: List[str]) -> int:
        if not moves:
            return 0
        count = 0
        i = 0
        while i < len(moves) - 1:
            cur = moves[i]
            nxt = moves[i + 1]
            if cur[0] == nxt[0]:
                cur_mod = cur[1:] if len(cur) > 1 else ""
                nxt_mod = nxt[1:] if len(nxt) > 1 else ""
                opposites = {("", "'"), ("'", ""), ("2", "2")}
                if (cur_mod, nxt_mod) in opposites:
                    count += 2
                    i += 2
                    continue
            i += 1
        return count
    
    def _format_timed_moves(self, timed_moves: List[tuple]) -> str:
        parts = []
        for move, ts in timed_moves:
            ts_s = ts / 1000.0
            parts.append(f"{move}@{ts_s:.2f}")
        return " ".join(parts)
    
    def build_phase_details_text(self) -> str:
        """构建阶段详情文本（单组/多组分析共用）"""
        stats = self.get_phase_stats()
        oriented_timed = self.get_phase_oriented_timed_moves()

        phase_details = ""

        for phase in PHASE_ORDER:
            s = stats[phase]

            oriented_moves = s["moves"]
            merged = "".join(self._merge_moves(oriented_moves))
            y_rotation = s.get("y_rotation", "")
            if y_rotation:
                merged = y_rotation + ' ' + merged

            # 使用按阶段朝向映射的带时间戳步骤
            oriented_timed_moves, _, _ = oriented_timed.get(phase, ([], '', self.front_color))
            timed_moves_str = self._format_timed_moves(oriented_timed_moves)

            ts = self.phase_timestamps.get(phase, {})
            start_s = ts.get("start", 0) / 1000.0
            end_s = ts.get("end", 0) / 1000.0

            obs_time = s.get("observation_time", None)
            if obs_time is not None:
                observation_info = f"- 观察时间: {obs_time:.2f}s"
            else:
                observation_info = ""

            # 转体信息
            rotation_info = ""
            if y_rotation:
                front_name = COLOR_NAMES.get(s.get("front_color", self.front_color), '')
                rotation_info = f"- 转体: {y_rotation}（{front_name}前）\n"

            phase_details += PHASE_DETAIL_TEMPLATE.format(
                phase_name=PHASE_NAMES[phase],
                timed_moves=timed_moves_str,
                merged_moves=merged,
                steps=s["steps"],
                time=s["time"],
                start=start_s,
                end=end_s,
                tps=s["tps"],
                observation_info=observation_info,
                rotation_info=rotation_info
            )

        return phase_details

    def build_ai_prompt(self, memory_text: str = "") -> tuple:
        stats = self.get_phase_stats()

        total_steps = 0
        total_execution_time = 0.0
        total_observation_time = 0.0

        for phase in PHASE_ORDER:
            s = stats[phase]
            total_steps += s["steps"]
            total_execution_time += s["time"]
            if "observation_time" in s:
                total_observation_time += s["observation_time"]

        phase_details = self.build_phase_details_text()

        total_time = self.get_total_time()
        total_tps = total_steps / total_time if total_time > 0 else 0

        orientation_desc = get_orientation_desc(self.top_color, self.front_color)

        system = SYSTEM_PROMPT.format(
            pause_threshold=AI_PAUSE_THRESHOLD_SEC,
        )
        user = USER_SINGLE_TEMPLATE.format(
            max_words=AI_MAX_RESPONSE_WORDS,
            orientation_desc=orientation_desc,
            phase_details=phase_details,
            total_steps=total_steps,
            total_time=total_time,
            total_tps=total_tps,
            memory_info=memory_text,
            strength_tags_str="、".join(STRENGTH_TAGS),
            weakness_tags_str="、".join(WEAKNESS_TAGS),
        )

        return (system, user)

    def get_total_time(self) -> float:
        all_times = []
        for phase in self.phase_timestamps.values():
            all_times.extend([phase["start"], phase["end"]])
        if all_times:
            return (max(all_times) - min(all_times)) / 1000.0
        return 0.0

    def is_solve_complete(self) -> bool:
        if not self._analyze_result:
            return False
        if not self.cross_moves:
            return False
        f2l_all_empty = all(len(self._analyze_result.get(f"f2l{i}", [])) == 0 for i in range(1, 5))
        if f2l_all_empty:
            return False
        late_phase_empty = (
            len(self._analyze_result.get("f2l4", [])) == 0
            and len(self._analyze_result.get("oll", [])) == 0
            and len(self._analyze_result.get("pll", [])) == 0
        )
        if late_phase_empty:
            return False
        cube = self.cube.copy()
        for move, _ in self.solution:
            cube.apply_standard_move(move)
        return cube.is_pll_solved()

    def identify_oll_pll(self) -> tuple:
        """识别本次还原的OLL和PLL初始状态

        根据打乱和processed solve，回放到OLL和PLL开始前的状态，
        然后调用Cube的identify_oll/identify_pll进行识别。

        Returns:
            tuple: (oll_case, pll_case)
                oll_case: OLL编号字符串（如 "1"~"57"），未识别返回空字符串
                pll_case: PLL名称字符串（如 "Aa", "T"），未识别返回空字符串
        """
        self.analyze()

        oll_case = ""
        pll_case = ""

        # 使用processed_solve回放（包含y旋转信息）
        processed = self.generate_processed_solve()
        parsed = self.parse_processed_solve(processed)
        phases = parsed.get("phases", {})

        if log:
            log.info("[OLL/PLL识别] ========== 开始识别 ==========")
            log.info(f"[OLL/PLL识别] processed_solve: {processed}")
            log.info(f"[OLL/PLL识别] analysis_view_map: {self.analysis_view_map}")

        # 回放到OLL开始前的状态（Cross + 4组F2L完成）
        cube = Cube()
        for move in self.scramble:
            cube.apply_standard_move(move)
        cube.view_map = self.analysis_view_map.copy()

        # 应用 cross + f2l1~f2l4 的步骤
        if log:
            log.info("[OLL识别] 回放 cross + f2l1~f2l4 阶段:")
        for phase_name in ["cross", "f2l1", "f2l2", "f2l3", "f2l4"]:
            phase_data = phases.get(phase_name, {})
            y_rot = phase_data.get("y_rotation", "")
            if y_rot:
                cube.apply_rotation(y_rot)
                if log:
                    log.info(f"[OLL识别]   {phase_name}阶段转体: {y_rot}")
            moves = phase_data.get("moves", [])
            if log:
                move_strs = [m for m, _ in moves]
                log.info(f"[OLL识别]   {phase_name}阶段步骤({len(moves)}步): {' '.join(move_strs)}")
            for move, ts_ms in moves:
                cube.apply_move(move)

        if log:
            log.info(f"[OLL识别] F2L完成后状态验证: Cross={cube.is_cross_solved()}, "
                      f"F2L1={cube.is_f2l_solved(1)}, F2L2={cube.is_f2l_solved(2)}, "
                      f"F2L3={cube.is_f2l_solved(3)}, F2L4={cube.is_f2l_solved(4)}, "
                      f"OLL完成={cube.is_oll_solved()}")
            log.info(f"[OLL识别] F2L完成后view_map: {cube.view_map}")

        if not cube.is_oll_solved():
            oll_case = cube.identify_oll()
        else:
            oll_case = "skip"
            if log:
                log.info("[OLL识别] OLL已完成（跳O）")

        # 回放到PLL开始前的状态（OLL完成）
        cube2 = Cube()
        for move in self.scramble:
            cube2.apply_standard_move(move)
        cube2.view_map = self.analysis_view_map.copy()

        # 应用 cross + f2l1~f2l4 + oll 的步骤
        if log:
            log.info("[PLL识别] 回放 cross + f2l1~f2l4 + oll 阶段:")
        for phase_name in ["cross", "f2l1", "f2l2", "f2l3", "f2l4", "oll"]:
            phase_data = phases.get(phase_name, {})
            y_rot = phase_data.get("y_rotation", "")
            if y_rot:
                cube2.apply_rotation(y_rot)
                if log:
                    log.info(f"[PLL识别]   {phase_name}阶段转体: {y_rot}")
            moves = phase_data.get("moves", [])
            if log:
                move_strs = [m for m, _ in moves]
                log.info(f"[PLL识别]   {phase_name}阶段步骤({len(moves)}步): {' '.join(move_strs)}")
            for move, ts_ms in moves:
                cube2.apply_move(move)

        if log:
            log.info(f"[PLL识别] OLL完成后状态验证: OLL完成={cube2.is_oll_solved()}, PLL完成={cube2.is_pll_solved()}")
            log.info(f"[PLL识别] OLL完成后view_map: {cube2.view_map}")

        if not cube2.is_pll_solved():
            pll_case = cube2.identify_pll()
        else:
            pll_case = "skip"
            if log:
                log.info("[PLL识别] PLL已完成（跳P）")

        if log:
            log.info(f"[OLL/PLL识别] ========== 识别结果: OLL={oll_case or '未识别'}, PLL={pll_case or '未识别'} ==========")

        return (oll_case, pll_case)

    def generate_processed_solve(self) -> str:
        """生成处理后的还原数据字符串

        格式: 底色W前色R|C[R@0.00U@0.24R'@0.63]F1[y'U'@0.80...]F2[...]F3[...]F4[...]O[...]P[...]
        - 已完成CFOP阶段拆解、转体识别、底色/前色确定
        - 步骤已转换为最终观察坐标系
        - 相邻相同步骤已合并（间隔<=0.3s时合并为X2）
        - 转体步骤插入在各阶段开头
        """
        oriented_timed = self.get_phase_oriented_timed_moves()
        phase_key_map = {
            "cross": "C", "f2l1": "F1", "f2l2": "F2",
            "f2l3": "F3", "f2l4": "F4", "oll": "O", "pll": "P"
        }
        # 头部：底色和初始前色，如 [WG]
        header = f"[{self.bottom_color}{self.front_color}]"
        parts = []
        for phase in PHASE_ORDER:
            oriented_moves_list, y_rotation, front_color = oriented_timed.get(phase, ([], '', ''))
            if not oriented_moves_list and not y_rotation:
                continue
            # 构建带时间戳的步骤列表（含转体）
            timed_list = []
            if y_rotation:
                # 转体步骤：使用该阶段第一步的时间戳
                first_ts = oriented_moves_list[0][1] if oriented_moves_list else 0
                timed_list.append((y_rotation, first_ts))
            timed_list.extend(oriented_moves_list)
            # 合并相邻相同步骤
            merged = self.merge_timed_moves(timed_list)
            # 格式化为 move@time
            phase_str = "".join(f"{m}@{ts / 1000.0:.2f}" for m, ts in merged)
            key = phase_key_map.get(phase, phase)
            parts.append(f"{key}[{phase_str}]")
        return header + "".join(parts)

    @staticmethod
    def parse_processed_solve(processed: str) -> Dict:
        """解析处理后的还原数据字符串

        Args:
            processed: generate_processed_solve()生成的字符串

        Returns:
            {
                "phases": {
                    "cross": {"moves": [(move, ts_ms), ...], "y_rotation": ""},
                    "f2l1": {...}, ...
                },
                "bottom_color": "...",
                "front_color": "..."
            }
        """
        import re
        phase_key_rmap = {
            "C": "cross", "F1": "f2l1", "F2": "f2l2",
            "F3": "f2l3", "F4": "f2l4", "O": "oll", "P": "pll"
        }
        # 解析头部：底色前色（如 "[WG]"）
        bottom_color = ""
        front_color = ""
        body = processed
        # 新格式 [WG]
        header_match = re.match(r'^\[([A-Z])([A-Z])\]', processed)
        if header_match:
            bottom_color = header_match.group(1)
            front_color = header_match.group(2)
            body = processed[header_match.end():]
        elif "|" in processed:
            # 兼容旧格式 WG|
            header, body = processed.split("|", 1)
            if len(header) >= 2:
                bottom_color = header[0]
                front_color = header[1]

        phases = {}
        # 匹配 key[content] 模式：C, F1-F4, O, P
        pattern = r'([CF][1-4]|[COP])\[([^\]]*)\]'
        for match in re.finditer(pattern, body):
            key = match.group(1)
            content = match.group(2)
            phase_name = phase_key_rmap.get(key, key)
            # 解析 move@time
            timed_moves = []
            y_rotation = ""
            move_pattern = r"([UDFBRLMSEy][2']?)@(\d+\.?\d*)"
            for m in re.finditer(move_pattern, content):
                move = m.group(1)
                ts_s = float(m.group(2))
                ts_ms = ts_s * 1000.0
                if move.startswith('y'):
                    y_rotation = move
                else:
                    timed_moves.append((move, ts_ms))
            phases[phase_name] = {"moves": timed_moves, "y_rotation": y_rotation}
        return {"phases": phases, "bottom_color": bottom_color, "front_color": front_color}
