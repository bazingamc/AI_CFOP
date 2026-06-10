"""
OLL/PLL 编码详细测试程序
以数据库 id=15183 的还原记录为例，打印 OLL 和 PLL 编码的完整计算过程
"""

import memory_db
from cube import Cube
from move_utils import parse_moves
from analyzer import CFOPAnalyzer


def print_separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_u_face(colors):
    """打印U面3x3色块"""
    face = colors['U']
    print("  U面色块布局:")
    print("       F")
    print("    ┌─────┐")
    for i, row in enumerate(face):
        side_labels = {0: "B↑", 1: "  ", 2: "F↓"}
        print(f"  {side_labels[i]}│{' '.join(row)}│")
    print("    └─────┘")
    print("  L←      →R")


def detailed_oll_encode(cube):
    """详细打印OLL编码过程"""
    real_u = cube.view_map.get('U', 'U')
    colors = cube.get_face_colors()
    u_face = colors['U']

    print(f"\n  当前观察坐标系 view_map: {cube.view_map}")
    print(f"  U面真实面: {real_u}")
    print()
    print_u_face(colors)

    # 棱块编码
    print(f"\n  ── OLL棱块编码 ──")
    print(f"  规则: U面颜色 == {real_u}(复原色) → 0, 否则 → 1")
    edge_positions = [
        (2, 1, "UF"),
        (1, 2, "UR"),
        (0, 1, "UB"),
        (1, 0, "UL"),
    ]
    edge_codes = []
    for r, c, name in edge_positions:
        color = u_face[r][c]
        code = '0' if color == real_u else '1'
        edge_codes.append(code)
        print(f"    {name}位置 (行{r},列{c}): 颜色={color}, 编码={code}")

    # 角块编码
    print(f"\n  ── OLL角块编码 ──")
    print(f"  规则: U面颜色 == {real_u} → 0; U面复原色在R/L面 → 1; 在F/B面 → 2")
    corner_positions = [
        (2, 2, "UFR", ('U', 'F', 'R')),
        (0, 2, "URB", ('U', 'R', 'B')),
        (0, 0, "UBL", ('U', 'B', 'L')),
        (2, 0, "ULF", ('U', 'L', 'F')),
    ]
    corner_codes = []
    for r, c, name, obs_faces in corner_positions:
        u_color = u_face[r][c]
        if u_color == real_u:
            code = '0'
            print(f"    {name}位置 (行{r},列{c}): U面颜色={u_color} == {real_u}, 编码=0")
        else:
            # 判断U面复原色在角块的哪个面
            real_faces = tuple(cube.view_map[f] for f in obs_faces)
            corner_idx = cube._corner_map().get(frozenset(real_faces))
            if corner_idx is not None:
                cubie = cube.cp[corner_idx]
                ori = cube.co[corner_idx]
                cubie_faces = cube.CORNER_FACES[cubie]
                pos_faces = cube.CORNER_FACES[corner_idx]
                found = False
                for color_idx, color in enumerate(cubie_faces):
                    pos_face = pos_faces[(color_idx + ori) % 3]
                    if color == real_u:
                        if pos_face in ('R', 'L'):
                            code = '1'
                            detail = f"U面复原色{real_u}在{pos_face}面(R/L类)"
                        else:
                            code = '2'
                            detail = f"U面复原色{real_u}在{pos_face}面(F/B类)"
                        found = True
                        break
                if not found:
                    code = '0'
                    detail = "未找到U面复原色"
            else:
                code = '0'
                detail = "角块未找到"
            print(f"    {name}位置 (行{r},列{c}): U面颜色={u_color} ≠ {real_u}, {detail}, 编码={code}")
        corner_codes.append(code)

    full_code = ''.join(edge_codes) + ''.join(corner_codes)
    print(f"\n  OLL编码结果: 棱{''.join(edge_codes)} + 角{''.join(corner_codes)} = {full_code}")
    return full_code


def detailed_pll_encode(cube):
    """详细打印PLL编码过程"""
    # 构建真实面到观察面的反向映射
    inv_view = {}
    for obs, real in cube.view_map.items():
        inv_view[real] = obs

    edge_target = {
        frozenset(('U', 'F')): 0,
        frozenset(('U', 'R')): 1,
        frozenset(('U', 'B')): 2,
        frozenset(('U', 'L')): 3,
    }
    corner_target = {
        frozenset(('U', 'F', 'R')): 0,
        frozenset(('U', 'R', 'B')): 1,
        frozenset(('U', 'B', 'L')): 2,
        frozenset(('U', 'L', 'F')): 3,
    }

    print(f"\n  当前观察坐标系 view_map: {cube.view_map}")
    print(f"  反向映射 inv_view: {inv_view}")
    colors = cube.get_face_colors()
    print_u_face(colors)

    # 棱块编码
    print(f"\n  ── PLL棱块编码 ──")
    print(f"  规则: UF=0 UR=1 UB=2 UL=3, 按位置记录该位置棱块属于哪个目标位置")
    edge_obs_list = [
        ('U', 'F', "UF"),
        ('U', 'R', "UR"),
        ('U', 'B', "UB"),
        ('U', 'L', "UL"),
    ]
    edge_codes = []
    for obs_f1, obs_f2, name in edge_obs_list:
        real_faces = frozenset(cube.view_map[f] for f in (obs_f1, obs_f2))
        pos_idx = cube._edge_map().get(real_faces)
        if pos_idx is not None:
            cubie = cube.ep[pos_idx]
            cubie_real_faces = cube.EDGE_FACES[cubie]
            cubie_obs_faces = frozenset(inv_view.get(f, f) for f in cubie_real_faces)
            target = edge_target.get(cubie_obs_faces, 0)
            cubie_real_name = '/'.join(cubie_real_faces)
            cubie_obs_name = '/'.join(sorted(cubie_obs_faces))
            edge_codes.append(str(target))
            print(f"    {name}位置: 真实面={set(real_faces)}, 棱块编号={pos_idx}, "
                  f"棱块真实面={cubie_real_name}, 棱块观察面={cubie_obs_name}, 目标位置={target}")
        else:
            edge_codes.append('0')
            print(f"    {name}位置: 未找到棱块")

    # 角块编码
    print(f"\n  ── PLL角块编码 ──")
    print(f"  规则: UFR=0 URB=1 UBL=2 ULF=3, 按位置记录该位置角块属于哪个目标位置")
    corner_obs_list = [
        ('U', 'F', 'R', "UFR"),
        ('U', 'R', 'B', "URB"),
        ('U', 'B', 'L', "UBL"),
        ('U', 'L', 'F', "ULF"),
    ]
    corner_codes = []
    for obs_f1, obs_f2, obs_f3, name in corner_obs_list:
        real_faces = frozenset(cube.view_map[f] for f in (obs_f1, obs_f2, obs_f3))
        pos_idx = cube._corner_map().get(real_faces)
        if pos_idx is not None:
            cubie = cube.cp[pos_idx]
            cubie_real_faces = cube.CORNER_FACES[cubie]
            cubie_obs_faces = frozenset(inv_view.get(f, f) for f in cubie_real_faces)
            target = corner_target.get(cubie_obs_faces, 0)
            cubie_real_name = '/'.join(cubie_real_faces)
            cubie_obs_name = '/'.join(sorted(cubie_obs_faces))
            corner_codes.append(str(target))
            print(f"    {name}位置: 真实面={set(real_faces)}, 角块编号={pos_idx}, "
                  f"角块真实面={cubie_real_name}, 角块观察面={cubie_obs_name}, 目标位置={target}")
        else:
            corner_codes.append('0')
            print(f"    {name}位置: 未找到角块")

    full_code = ''.join(edge_codes) + ''.join(corner_codes)
    print(f"\n  PLL编码结果: 棱{''.join(edge_codes)} + 角{''.join(corner_codes)} = {full_code}")
    return full_code


def match_oll_table(code):
    """在OLL编码表中查找匹配"""
    print(f"\n  在OLL编码表中查找 '{code}':")
    found = []
    for oll_num, oll_code in Cube.OLL_TABLE.items():
        if code == oll_code:
            found.append(oll_num)
            print(f"    ★ 匹配 OLL {oll_num}: {oll_code}")
    if not found:
        print(f"    未找到直接匹配")
    return found


def match_pll_table(code):
    """在PLL编码表中查找匹配"""
    print(f"\n  在PLL编码表中查找 '{code}':")
    found = []
    for pll_name, pll_code in Cube.PLL_TABLE.items():
        if code == pll_code:
            found.append(pll_name)
            print(f"    ★ 匹配 PLL {pll_name}: {pll_code}")
    if not found:
        print(f"    未找到直接匹配")
    return found


def main():
    memory_db.init_db()

    # 获取记录
    detail = memory_db.get_record_detail(15183)
    if not detail:
        print("记录 id=15183 不存在")
        return

    scramble = detail['scramble']
    solution = detail['solution']

    print_separator("原始数据")
    print(f"  ID: 15183")
    print(f"  日期: {detail['date']}")
    print(f"  打乱: {scramble}")
    print(f"  总用时: {detail['total_time']:.2f}s")
    print(f"  底色: {detail['bottom_color']}")
    print(f"  数据库中 OLL: {detail.get('oll_case', '(空)')}")
    print(f"  数据库中 PLL: {detail.get('pll_case', '(空)')}")

    # 分析
    print_separator("CFOP 分析")
    bottom_color, analyzer, scores = CFOPAnalyzer.auto_detect_bottom_color(scramble, solution)
    result = analyzer.analyze()

    from config import COLOR_NAMES
    print(f"  识别底色: {COLOR_NAMES.get(bottom_color, bottom_color)} ({bottom_color})")
    print(f"  顶色: {COLOR_NAMES.get(analyzer.top_color, analyzer.top_color)} ({analyzer.top_color})")
    print(f"  前色: {COLOR_NAMES.get(analyzer.front_color, analyzer.front_color)} ({analyzer.front_color})")
    print(f"  分析view_map: {analyzer.analysis_view_map}")

    for phase in ['cross', 'f2l1', 'f2l2', 'f2l3', 'f2l4', 'oll', 'pll']:
        moves = result.get(phase, [])
        ts = analyzer.phase_timestamps.get(phase, {})
        print(f"  {phase}: {len(moves)}步, 时间戳 start={ts.get('start',0):.0f}ms end={ts.get('end',0):.0f}ms")

    # =============================================
    # OLL 编码详细过程
    # =============================================
    print_separator("OLL 编码详细过程")
    print("  步骤: 回放到 F2L4 完成时刻，检查顶层状态")

    # 构建OLL状态
    cube_oll = Cube()
    for move in parse_moves(scramble):
        cube_oll.apply_standard_move(move)
    cube_oll.view_map = analyzer.analysis_view_map.copy()

    # 构建完整步骤序列（含y旋转），从processed_solve解析
    processed = analyzer.generate_processed_solve()
    parsed = analyzer.parse_processed_solve(processed)
    ps_phases = parsed.get("phases", {})

    f2l4_end_ts = analyzer.phase_timestamps.get("f2l4", {}).get("end", 0)
    print(f"\n  F2L4结束时间戳: {f2l4_end_ts}ms")

    # 回放到F2L4完成（使用processed_solve中的步骤和y旋转）
    for phase_name in ["cross", "f2l1", "f2l2", "f2l3", "f2l4"]:
        phase_data = ps_phases.get(phase_name, {})
        y_rot = phase_data.get("y_rotation", "")
        if y_rot:
            print(f"  应用转体: {y_rot} (在{phase_name}阶段)")
            cube_oll.apply_rotation(y_rot)
        for move, ts_ms in phase_data.get("moves", []):
            cube_oll.apply_move(move)  # 观察坐标系步骤，用apply_move
    print(f"  已回放 cross+f2l1~f2l4 阶段")

    # 验证F2L状态
    print(f"\n  验证: Cross完成={cube_oll.is_cross_solved()}")
    for i in range(1, 5):
        print(f"  验证: F2L-{i}完成={cube_oll.is_f2l_solved(i)}")
    print(f"  验证: OLL完成={cube_oll.is_oll_solved()}")

    # 详细OLL编码
    oll_code = detailed_oll_encode(cube_oll)

    # 在4个y方向上匹配
    print(f"\n  ── 4方向y旋转匹配OLL ──")
    cube_copy = cube_oll.copy()
    for y_idx in range(4):
        code = cube_copy.encode_oll()
        matches = match_oll_table(code)
        if matches:
            print(f"  ★★★ y*{y_idx}方向: 编码={code} → 匹配 OLL {matches} ★★★")
        else:
            print(f"  y*{y_idx}方向: 编码={code} → 无匹配")
        cube_copy.apply_rotation('y')

    # =============================================
    # PLL 编码详细过程
    # =============================================
    print_separator("PLL 编码详细过程")
    print("  步骤: 回放到 OLL 完成时刻，检查顶层状态")

    cube_pll = Cube()
    for move in parse_moves(scramble):
        cube_pll.apply_standard_move(move)
    cube_pll.view_map = analyzer.analysis_view_map.copy()

    oll_end_ts = analyzer.phase_timestamps.get("oll", {}).get("end", 0)
    print(f"\n  OLL结束时间戳: {oll_end_ts}ms")

    # 回放到OLL完成（使用processed_solve中的步骤和y旋转）
    for phase_name in ["cross", "f2l1", "f2l2", "f2l3", "f2l4", "oll"]:
        phase_data = ps_phases.get(phase_name, {})
        y_rot = phase_data.get("y_rotation", "")
        if y_rot:
            print(f"  应用转体: {y_rot} (在{phase_name}阶段)")
            cube_pll.apply_rotation(y_rot)
        for move, ts_ms in phase_data.get("moves", []):
            cube_pll.apply_move(move)  # 观察坐标系步骤，用apply_move
    print(f"  已回放 cross+f2l1~f2l4+oll 阶段")

    # 验证状态
    print(f"\n  验证: OLL完成={cube_pll.is_oll_solved()}")
    print(f"  验证: PLL完成={cube_pll.is_pll_solved()}")

    # 详细PLL编码
    pll_code = detailed_pll_encode(cube_pll)

    # 在4个y方向上匹配
    print(f"\n  ── 4方向y旋转匹配PLL ──")
    cube_copy2 = cube_pll.copy()
    for y_idx in range(4):
        code = cube_copy2.encode_pll()
        matches = match_pll_table(code)
        if matches:
            print(f"  ★★★ y*{y_idx}方向: 编码={code} → 匹配 PLL {matches} ★★★")
        else:
            print(f"  y*{y_idx}方向: 编码={code} → 无匹配")
        cube_copy2.apply_rotation('y')

    # =============================================
    # 最终结果
    # =============================================
    print_separator("最终识别结果")
    oll_result = cube_oll.identify_oll()
    pll_result = cube_pll.identify_pll()
    print(f"  OLL: {oll_result or '未识别'}")
    print(f"  PLL: {pll_result or '未识别'}")
    print(f"  数据库中 OLL: {detail.get('oll_case', '(空)')}")
    print(f"  数据库中 PLL: {detail.get('pll_case', '(空)')}")


if __name__ == '__main__':
    main()
