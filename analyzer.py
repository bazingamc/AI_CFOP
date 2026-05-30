"""
CFOP分析器 - 核心分析逻辑
"""

from typing import List, Dict

from config import (
    AI_MAX_RESPONSE_WORDS, AI_PAUSE_THRESHOLD_SEC,
    PHASE_ORDER, PHASE_NAMES,
    SYSTEM_PROMPT, USER_SINGLE_TEMPLATE, PHASE_DETAIL_TEMPLATE,
    OPPOSITE_COLORS, COLOR_NAMES
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

    @classmethod
    def from_bottom_color(cls, scramble: str, solution: str, bottom_color: str):
        top_color = OPPOSITE_COLORS.get(bottom_color)
        if not top_color:
            raise ValueError(f"无效底色: {bottom_color}")

        candidates = [
            color for color in cls.COLOR_ORDER
            if color not in (bottom_color, top_color)
        ]

        scored = []
        for front_color in candidates:
            analyzer = cls(scramble, solution, top_color, front_color)
            analyzer.bottom_color = bottom_color
            analyzer.auto_front_candidates = candidates
            score = analyzer._score_auto_front()
            scored.append((score, analyzer))

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
        log.info(f"[CFOPAnalyzer] 初始化分析器")
        log.info(f"[CFOPAnalyzer] 输入参数: top_color={top_color}, front_color={front_color}")
        
        orientation_error = validate_orientation(top_color, front_color)
        if orientation_error:
            raise ValueError(orientation_error)
        
        log.info(f"[CFOPAnalyzer] 打乱公式原文: {scramble}")
        log.info(f"[CFOPAnalyzer] 还原步骤原文: {solution[:200]}{'...' if len(solution) > 200 else ''}")
        
        self.scramble = parse_moves(scramble)
        self.solution = parse_timed_moves(solution)
        log.info(f"[CFOPAnalyzer] 解析后打乱步骤({len(self.scramble)}步): {' '.join(self.scramble)}")
        parsed_moves = [m for m, _ in self.solution]
        log.info(f"[CFOPAnalyzer] 解析后还原步骤({len(parsed_moves)}步): {' '.join(parsed_moves)}")
        
        self.cube = Cube()
        self.top_color = top_color
        self.front_color = front_color
        self.bottom_color = OPPOSITE_COLORS.get(top_color)
        self.auto_front_score = None
        self.auto_front_scores = []
        self.auto_front_candidates = []
        
        self.rotations = get_rotation_for_orientation(top_color, front_color)
        log.info(f"[CFOPAnalyzer] 朝向旋转序列: {self.rotations if self.rotations else '(无旋转，白顶绿前)'}")
        
        self.analysis_view_map = self._build_analysis_view_map()
        self.output_mapping = self._build_output_mapping()
        log.info(f"[CFOPAnalyzer] CFOP判定观察view_map: {self.analysis_view_map}")
        log.info(f"[CFOPAnalyzer] 输出步骤映射表: {self.output_mapping}")

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
        """将打乱公式按固定白顶绿前坐标系应用到魔方"""
        log.info(f"[CFOPAnalyzer] 开始应用打乱步骤...")
        for move in self.scramble:
            self.cube.apply_standard_move(move)
        log.info(f"[CFOPAnalyzer] 打乱步骤应用完成")

        self.cube.view_map = self.analysis_view_map.copy()
        
        # log.info(f"[CFOPAnalyzer] 当前复原色定义: {self.cube.solved_colors}")

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
        
        log.info(f"[CFOPAnalyzer] ========== 开始阶段分析 ==========")
        
        mapped_solution = [self._map_move(m) for m, _ in self.solution]
        log.info(f"[CFOPAnalyzer] 输出视角下的还原步骤({len(mapped_solution)}步): {' '.join(mapped_solution)}")
        
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
            
            if step_count <= 25:
                log.debug(f"[CFOPAnalyzer] 步骤{step_count}: 输入={original_move}, 映射={mapped_move}, 当前阶段={current_phase}")
            
            if current_phase == "cross" and cube.is_cross_solved():
                self.cross_moves = current_moves.copy()
                self.phase_timestamps["cross"]["end"] = timestamp
                self.phase_timed_moves["cross"] = current_timed_moves.copy()
                log.info(f"[CFOPAnalyzer] ✓ Cross完成! 步数={len(self.cross_moves)}, 步骤={' '.join(self.cross_moves)}")
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

                    log.info(f"[CFOPAnalyzer] ✓ F2L-{f2l_num}({slot_names[slot_found]})完成! "
                            f"步数={len(current_moves)}, 步骤={' '.join(current_moves)}")

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
                        log.info(f"[CFOPAnalyzer] 所有F2L完成，进入OLL阶段")
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
                log.info(f"[CFOPAnalyzer] ✓ OLL完成! 步数={len(self.oll_moves)}, 步骤={' '.join(self.oll_moves)}")
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
                log.info(f"[CFOPAnalyzer] ✓ PLL完成! 步数={len(self.pll_moves)}, 步骤={' '.join(self.pll_moves)}")
                current_moves = []
                current_timed_moves = []

        log.info(f"[CFOPAnalyzer] 总步骤数: {step_count}")

        f2l_result_summary = [slot_data[1] for slot_data in completed_f2l_slots]
        log.info(f"[CFOPAnalyzer] 阶段识别结果: Cross={len(self.cross_moves)}步, "
                f"F2L={[len(m) for m in f2l_result_summary]}步, "
                f"OLL={len(self.oll_moves)}步, PLL={len(self.pll_moves)}步")
        
        result = {"cross": self.cross_moves, "oll": self.oll_moves, "pll": self.pll_moves}
        # 按完成顺序输出F2L（F2L-1是第一个完成的，不一定是FR槽位）
        for i, slot_data in enumerate(completed_f2l_slots):
            result[f"f2l{i+1}"] = slot_data[1]  # slot_data = (slot_num, moves, timed_moves)
        for i in range(len(completed_f2l_slots), 4):
            result[f"f2l{i+1}"] = []
        
        log.info(f"[CFOPAnalyzer] ========== 阶段分析完成 ==========")
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
            stats[phase] = {"moves": moves, "steps": step_count, "time": duration_s, "tps": tps}
        
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
    
    def _format_timed_moves(self, timed_moves: List[tuple]) -> str:
        parts = []
        for move, ts in timed_moves:
            ts_s = ts / 1000.0
            parts.append(f"{move}@{ts_s:.2f}")
        return " ".join(parts)
    
    def build_ai_prompt(self) -> tuple:
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
        
        system = SYSTEM_PROMPT.format(pause_threshold=AI_PAUSE_THRESHOLD_SEC)
        user = USER_SINGLE_TEMPLATE.format(
            max_words=AI_MAX_RESPONSE_WORDS,
            orientation_desc=orientation_desc,
            phase_details=phase_details,
            total_steps=total_steps,
            total_time=total_time,
            total_tps=total_tps
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
