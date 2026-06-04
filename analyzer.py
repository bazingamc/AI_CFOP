"""
CFOP分析器 - 核心分析逻辑
"""

from typing import List, Dict

from config import (
    AI_MAX_RESPONSE_WORDS, AI_PAUSE_THRESHOLD_SEC,
    PHASE_ORDER, PHASE_NAMES,
    SYSTEM_PROMPT, USER_SINGLE_TEMPLATE, PHASE_DETAIL_TEMPLATE,
    OPPOSITE_COLORS, COLOR_NAMES, STRENGTH_TAGS, WEAKNESS_TAGS
)
from cube import Cube
from move_utils import parse_moves, parse_timed_moves, validate_orientation
from move_utils import get_rotation_for_orientation, get_orientation_desc


log = None

def set_logger(logger):
    global log
    log = logger


class CFOPAnalyzer:
    """CFOP还原过程分析器"""

    COLOR_ORDER = ['W', 'Y', 'G', 'B', 'R', 'O']

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

        original_level = log.level if log else None
        if log:
            log.setLevel(max(log.level, 30))

        scored = []
        for front_color in candidates:
            analyzer = cls(scramble, solution, top_color, front_color)
            analyzer.bottom_color = bottom_color
            analyzer.auto_front_candidates = candidates
            score = analyzer._score_auto_front()
            scored.append((score, analyzer))

        if log and original_level is not None:
            log.setLevel(original_level)

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_analyzer = scored[0]
        best_analyzer.auto_front_score = best_score
        best_analyzer.auto_front_scores = [
            (a.front_color, s) for s, a in scored
        ]

        if log:
            bottom_name = COLOR_NAMES.get(bottom_color, bottom_color)
            front_name = COLOR_NAMES.get(best_analyzer.front_color, best_analyzer.front_color)
            log.info(
                f"[CFOPAnalyzer] 自动前色选择: 底色={bottom_name}, "
                f"前色={front_name}, 候选得分={best_analyzer.auto_front_scores}"
            )

        return best_analyzer

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
        self._analyze_result = None
    
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

    def _score_auto_front(self) -> float:
        result = self.analyze()
        score = 0.0

        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            if not moves:
                score -= 1000
                continue

            if phase != "cross":
                score += self._score_moves_for_ruf(moves)
                timed_moves = self.phase_timed_moves.get(phase, [])
                if timed_moves:
                    score += self._score_phase_start(timed_moves[0][0])

        score -= len(result.get("oll", [])) * 0.3
        score -= len(result.get("pll", [])) * 0.2
        return score

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
        phase_start_time = self.solution[0][1] if self.solution else 0
        self.phase_timestamps = {"cross": {"start": phase_start_time, "end": 0}}
        self.phase_timed_moves = {"cross": []}
        pending_phase_start = None
        
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
            
            if current_phase == "cross" and cube.is_cross_solved():
                self.cross_moves = current_moves.copy()
                self.phase_timestamps["cross"]["end"] = timestamp
                self.phase_timed_moves["cross"] = current_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] Cross完成: {len(self.cross_moves)}步")
                current_moves = []
                current_timed_moves = []
                current_phase = "f2l"
                cross_done = True
                self.phase_timestamps["f2l1"] = {"start": 0, "end": 0}
                self.phase_timed_moves["f2l1"] = []
                pending_phase_start = "f2l1"
            elif current_phase == "f2l":
                slot_found = None
                for i in range(4):
                    if not f2l_done[i] and cube.is_f2l_solved(i + 1):
                        slot_found = i + 1  # 实际完成的槽位号(1-4)
                        break

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

                    current_moves = []
                    current_timed_moves = []

                    if all(f2l_done):
                        current_phase = "oll"
                        self.phase_timestamps["oll"] = {"start": 0, "end": 0}
                        self.phase_timed_moves["oll"] = []
                        pending_phase_start = "oll"
                        log.debug(f"[CFOPAnalyzer] 所有F2L完成，进入OLL阶段")
                    else:
                        next_f2l_num = f2l_num + 1
                        next_key = f"f2l{next_f2l_num}"
                        self.phase_timestamps[next_key] = {"start": 0, "end": 0}
                        self.phase_timed_moves[next_key] = []
                        pending_phase_start = next_key
            elif current_phase == "oll" and cube.is_oll_solved():
                self.oll_moves = current_moves.copy()
                self.phase_timestamps["oll"]["end"] = timestamp
                self.phase_timed_moves["oll"] = current_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] OLL完成: {len(self.oll_moves)}步")
                current_moves = []
                current_timed_moves = []
                current_phase = "pll"
                oll_done = True
                self.phase_timestamps["pll"] = {"start": 0, "end": 0}
                self.phase_timed_moves["pll"] = []
                pending_phase_start = "pll"
            elif current_phase == "pll" and cube.is_pll_solved():
                self.pll_moves = current_moves.copy()
                self.phase_timestamps["pll"]["end"] = timestamp
                self.phase_timed_moves["pll"] = current_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] PLL完成: {len(self.pll_moves)}步")
                current_moves = []
                current_timed_moves = []

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
    
    def format_output(self) -> str:
        result = self.analyze()
        stats = self.get_phase_stats()
        max_pauses = self._calculate_max_pauses()
        output = []
        
        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            if not moves:
                continue
            
            merged = "".join(self._merge_moves(moves))
            s = stats.get(phase, {})
            exec_time = s.get("time", 0)
            obs_time = s.get("observation_time", 0)
            max_pause = max_pauses.get(phase, 0)
            total_time = exec_time + (obs_time if obs_time else 0)
            
            phase_label = {
                "cross": "Cross", "f2l1": "F2L-1", "f2l2": "F2L-2",
                "f2l3": "F2L-3", "f2l4": "F2L-4", "oll": "OLL", "pll": "PLL"
            }.get(phase, phase)
            
            output.append(f"【{phase_label}】:{merged}")
            if obs_time > 0:
                output.append(f"  整体用时:{total_time:.2f}s | 观察时间:{obs_time:.2f}s | 执行时间:{exec_time:.2f}s | 最大卡顿:{max_pause:.2f}s")
            else:
                output.append(f"  整体用时:{total_time:.2f}s | 执行时间:{exec_time:.2f}s | 最大卡顿:{max_pause:.2f}s")
        
        return "\n".join(output)
    
    def get_phase_stats(self) -> Dict:
        result = self.analyze()
        stats = {}
        for phase in PHASE_ORDER:
            moves = result.get(phase, [])
            step_count = len(moves)
            if phase in self.phase_timestamps:
                ts = self.phase_timestamps[phase]
                duration_s = (ts["end"] - ts["start"]) / 1000.0
                tps = step_count / duration_s if duration_s > 0 else 0
            else:
                duration_s = 0
                tps = 0
            stutter_count = self._calculate_stutter_count(phase)
            wasted_moves = self._calculate_wasted_moves(moves)
            stats[phase] = {
                "moves": moves, "steps": step_count, "time": duration_s,
                "tps": tps, "stutter_count": stutter_count, "wasted_moves": wasted_moves,
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
    
    def build_ai_prompt(self, memory_text: str = "") -> tuple:
        stats = self.get_phase_stats()
        result = self.analyze()
        
        total_steps = 0
        total_execution_time = 0.0
        total_observation_time = 0.0
        phase_details = ""
        
        for phase in PHASE_ORDER:
            s = stats[phase]
            total_steps += s["steps"]
            total_execution_time += s["time"]
            if "observation_time" in s:
                total_observation_time += s["observation_time"]
            
            merged = "".join(self._merge_moves(s["moves"]))
            timed_moves_str = self._format_timed_moves(self.phase_timed_moves.get(phase, []))
            
            ts = self.phase_timestamps.get(phase, {})
            start_s = ts.get("start", 0) / 1000.0
            end_s = ts.get("end", 0) / 1000.0
            
            obs_time = s.get("observation_time", None)
            if obs_time is not None:
                observation_info = f"- 观察时间: {obs_time:.2f}s"
            else:
                observation_info = ""
            
            phase_details += PHASE_DETAIL_TEMPLATE.format(
                phase_name=PHASE_NAMES[phase],
                timed_moves=timed_moves_str,
                merged_moves=merged,
                steps=s["steps"],
                time=s["time"],
                start=start_s,
                end=end_s,
                tps=s["tps"],
                observation_info=observation_info
            )
        
        total_time = self.get_total_time()
        total_tps = total_steps / total_time if total_time > 0 else 0
        
        orientation_desc = get_orientation_desc(self.top_color, self.front_color)
        
        system = SYSTEM_PROMPT.format(
            pause_threshold=AI_PAUSE_THRESHOLD_SEC,
            strength_tags_str="、".join(STRENGTH_TAGS),
            weakness_tags_str="、".join(WEAKNESS_TAGS)
        )
        user = USER_SINGLE_TEMPLATE.format(
            max_words=AI_MAX_RESPONSE_WORDS,
            orientation_desc=orientation_desc,
            phase_details=phase_details,
            total_steps=total_steps,
            total_time=total_time,
            total_tps=total_tps,
            memory_info=memory_text
        )
        
        return (system, user)
    
    def build_simple_prompt(self, template: str) -> str:
        stats = self.get_phase_stats()
        
        total_steps = 0
        total_execution_time = 0.0
        phase_details = ""
        
        for phase in PHASE_ORDER:
            s = stats[phase]
            total_steps += s["steps"]
            total_execution_time += s["time"]
            
            tps_str = f"{s['tps']:.1f}" if s['tps'] > 0 else "N/A"
            phase_details += f"- {PHASE_NAMES[phase]}: {s['steps']}步, {s['time']:.2f}s, TPS={tps_str}\n"
        
        total_time = self.get_total_time()
        total_tps = total_steps / total_time if total_time > 0 else 0
        
        orientation_desc = get_orientation_desc(self.top_color, self.front_color)
        
        user = template.format(
            orientation_desc=orientation_desc,
            phase_details=phase_details.strip(),
            total_steps=total_steps,
            total_time=total_time,
            total_tps=total_tps
        )
        
        return user
    
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
