"""
cube.py
标准三阶魔方 Cubie Model
方案1：
- Cube State 永远固定坐标系
- xyz 只改变观察坐标系(view)
- 不真正旋转 cube state

适用于：
- CFOP分析
- 智能魔方数据分析
- 固定坐标系公式
- 转体识别
- Kociemba/min2phase风格

作者修复：
- 正确 cubie orientation
- 正确 xyz view rotation
- 正确 CFOP 判断
"""

log = None


def set_logger(logger):
    global log
    log = logger


# =========================================================
# cubie 编号
# =========================================================

# corners
# 0 URF
# 1 UFL
# 2 ULB
# 3 UBR
# 4 DFR
# 5 DLF
# 6 DBL
# 7 DRB

# edges
# 0 UR
# 1 UF
# 2 UL
# 3 UB
# 4 DR
# 5 DF
# 6 DL
# 7 DB
# 8 FR
# 9 FL
# 10 BL
# 11 BR


class Cube:
    CORNER_FACES = [
        ('U', 'R', 'F'),
        ('U', 'F', 'L'),
        ('U', 'L', 'B'),
        ('U', 'B', 'R'),
        ('D', 'F', 'R'),
        ('D', 'L', 'F'),
        ('D', 'B', 'L'),
        ('D', 'R', 'B'),
    ]

    EDGE_FACES = [
        ('U', 'R'),
        ('U', 'F'),
        ('U', 'L'),
        ('U', 'B'),
        ('D', 'R'),
        ('D', 'F'),
        ('D', 'L'),
        ('D', 'B'),
        ('F', 'R'),
        ('F', 'L'),
        ('B', 'L'),
        ('B', 'R'),
    ]

    # =====================================================
    # init
    # =====================================================

    def __init__(self):

        # cubie state
        self.cp = list(range(8))
        self.co = [0] * 8

        self.ep = list(range(12))
        self.eo = [0] * 12

        # 观察坐标系
        # 表示当前观察下：
        # U/F/R/L/B/D 对应真实哪个面
        self.view_map = {
            'U': 'U',
            'D': 'D',
            'F': 'F',
            'B': 'B',
            'L': 'L',
            'R': 'R'
        }

    # =====================================================
    # copy
    # =====================================================

    def copy(self):

        c = Cube()

        c.cp = self.cp.copy()
        c.co = self.co.copy()

        c.ep = self.ep.copy()
        c.eo = self.eo.copy()

        c.view_map = self.view_map.copy()

        return c

    # =====================================================
    # public move
    # =====================================================

    def apply_move(self, move: str):

        if not move:
            return

        face = move[0]

        times = 1

        if len(move) > 1:

            if move[1] == '2':
                times = 2

            elif move[1] == "'":
                times = 3

        # M/E/S 中层旋转需要根据view_map转换为真实坐标系下的等价旋转
        if face in ('M', 'E', 'S'):
            for _ in range(times):
                self._apply_middle_layer_move(face)
        else:
            # 观察坐标系 -> 真实面
            real_face = self.view_map[face]
            for _ in range(times):
                self._apply_single_move(real_face)

    def _apply_middle_layer_move(self, face: str):
        """根据当前view_map将观察坐标系下的M/E/S转换为真实坐标系下的等价旋转

        M沿观察L方向旋转中间层，E沿观察D方向旋转中间层，S沿观察F方向旋转中间层
        """
        if face == 'M':
            # M沿观察L方向 -> 真实view_map['L']方向
            real_l = self.view_map['L']
            # L方向对应的中层旋转映射
            middle_map = {
                'L': 'M', 'R': "M'",   # M/M'
                'F': 'S', 'B': "S'",   # S/S'
            }
            real_move = middle_map[real_l]
        elif face == 'E':
            # E沿观察D方向 -> 真实view_map['D']方向
            real_d = self.view_map['D']
            middle_map = {
                'D': 'E', 'U': "E'",   # E/E'
                'F': "S'", 'B': 'S',   # S'/S
                'L': "M'", 'R': 'M',   # M'/M
            }
            real_move = middle_map[real_d]
        elif face == 'S':
            # S沿观察F方向 -> 真实view_map['F']方向
            real_f = self.view_map['F']
            middle_map = {
                'F': 'S', 'B': "S'",   # S/S'
                'U': "M'", 'D': 'M',   # M'/M
                'L': "E'", 'R': 'E',   # E'/E
            }
            real_move = middle_map[real_f]
        else:
            return

        # 执行真实中层旋转
        if real_move.endswith("'"):
            self._apply_single_move(real_move[0])
            self._apply_single_move(real_move[0])
            self._apply_single_move(real_move[0])
        else:
            self._apply_single_move(real_move)

    def apply_standard_move(self, move: str):
        """Apply a move written in the fixed white-top/green-front coordinate system."""

        if not move:
            return

        face = move[0]
        times = 1

        if len(move) > 1:

            if move[1] == '2':
                times = 2

            elif move[1] == "'":
                times = 3

        for _ in range(times):
            self._apply_single_move(face)

    # =====================================================
    # xyz rotation
    # =====================================================

    def apply_rotation(self, rot: str):

        if not rot:
            return

        axis = rot[0]

        times = 1

        if len(rot) > 1:

            if rot[1] == '2':
                times = 2

            elif rot[1] == "'":
                times = 3

        for _ in range(times):
            self._apply_single_rotation(axis)

    # =====================================================
    # view rotation only
    # =====================================================

    def _apply_single_rotation(self, axis: str):

        old = self.view_map.copy()

        # -------------------------------------------------
        # x
        # -------------------------------------------------

        if axis == 'x':

            self.view_map['U'] = old['F']
            self.view_map['F'] = old['D']
            self.view_map['D'] = old['B']
            self.view_map['B'] = old['U']

            self.view_map['L'] = old['L']
            self.view_map['R'] = old['R']

        # -------------------------------------------------
        # y
        # -------------------------------------------------

        elif axis == 'y':

            self.view_map['F'] = old['R']
            self.view_map['R'] = old['B']
            self.view_map['B'] = old['L']
            self.view_map['L'] = old['F']

            self.view_map['U'] = old['U']
            self.view_map['D'] = old['D']

        # -------------------------------------------------
        # z
        # -------------------------------------------------

        elif axis == 'z':

            self.view_map['U'] = old['L']
            self.view_map['R'] = old['U']
            self.view_map['D'] = old['R']
            self.view_map['L'] = old['D']

            self.view_map['F'] = old['F']
            self.view_map['B'] = old['B']

    # =====================================================
    # cubie move
    # =====================================================

    def _apply_single_move(self, face: str):

        old_cp = self.cp.copy()
        old_co = self.co.copy()

        old_ep = self.ep.copy()
        old_eo = self.eo.copy()

        # =================================================
        # U
        # =================================================

        if face == 'U':

            dst_c = [0, 1, 2, 3]
            src_c = [3, 0, 1, 2]

            dst_e = [0, 1, 2, 3]
            src_e = [3, 0, 1, 2]

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = old_co[s]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s]

        # =================================================
        # D
        # =================================================

        elif face == 'D':

            dst_c = [4, 5, 6, 7]
            src_c = [5, 6, 7, 4]

            dst_e = [4, 5, 6, 7]
            src_e = [5, 6, 7, 4]

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = old_co[s]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s]

        # =================================================
        # R
        # =================================================

        elif face == 'R':

            dst_c = [0, 3, 7, 4]
            src_c = [4, 0, 3, 7]

            twist = {
                0: 2,
                3: 1,
                7: 2,
                4: 1
            }

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = (old_co[s] + twist[d]) % 3

            dst_e = [0, 11, 4, 8]
            src_e = [8, 0, 11, 4]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s]

        # =================================================
        # L
        # =================================================

        elif face == 'L':

            dst_c = [1, 5, 6, 2]
            src_c = [2, 1, 5, 6]

            twist = {
                1: 1,
                5: 2,
                6: 1,
                2: 2
            }

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = (old_co[s] + twist[d]) % 3

            dst_e = [2, 9, 6, 10]
            src_e = [10, 2, 9, 6]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s]

        # =================================================
        # F
        # =================================================

        elif face == 'F':

            dst_c = [0, 4, 5, 1]
            src_c = [1, 0, 4, 5]

            twist = {
                0: 1,
                4: 2,
                5: 1,
                1: 2
            }

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = (old_co[s] + twist[d]) % 3

            dst_e = [1, 8, 5, 9]
            src_e = [9, 1, 8, 5]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s] ^ 1

        # =================================================
        # B
        # =================================================

        elif face == 'B':

            dst_c = [2, 6, 7, 3]
            src_c = [3, 2, 6, 7]

            twist = {
                2: 1,
                6: 2,
                7: 1,
                3: 2
            }

            for d, s in zip(dst_c, src_c):

                self.cp[d] = old_cp[s]
                self.co[d] = (old_co[s] + twist[d]) % 3

            dst_e = [3, 10, 7, 11]
            src_e = [11, 3, 10, 7]

            for d, s in zip(dst_e, src_e):

                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s] ^ 1

        # =================================================
        # M (与L同向，只影响中间层棱块)
        # =================================================
        elif face == 'M':
            # 中间层棱块: UF=1, DF=5, DB=7, UB=3
            # M方向: UF->DF->DB->UB->UF (与L同向)
            dst_e = [5, 7, 3, 1]
            src_e = [1, 5, 7, 3]
            for d, s in zip(dst_e, src_e):
                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s] ^ 1

        # =================================================
        # E (与D同向，只影响中间层棱块)
        # =================================================
        elif face == 'E':
            # 中间层棱块: FR=8, FL=9, BL=10, BR=11
            # E方向: FR->FL->BL->BR->FR (与D同向)
            dst_e = [9, 10, 11, 8]
            src_e = [8, 9, 10, 11]
            for d, s in zip(dst_e, src_e):
                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s] ^ 1

        # =================================================
        # S (与F同向，只影响中间层棱块)
        # =================================================
        elif face == 'S':
            # 中间层棱块: UR=0, DR=4, DL=6, UL=2
            # S方向: UR->DR->DL->UL->UR (与F同向)
            dst_e = [4, 6, 2, 0]
            src_e = [0, 4, 6, 2]
            for d, s in zip(dst_e, src_e):
                self.ep[d] = old_ep[s]
                self.eo[d] = old_eo[s] ^ 1

    # =====================================================
    # solved check
    # =====================================================

    def is_pll_solved(self):

        return (
            self.cp == list(range(8))
            and
            self.co == [0] * 8
            and
            self.ep == list(range(12))
            and
            self.eo == [0] * 12
        )

    def _get_face_edges(self, face: str) -> list:
        """根据view_map获取指定观察面对应的真实棱块编号"""
        real_face = self.view_map.get(face, face)
        face_edges = {
            'U': [0, 1, 2, 3],
            'D': [4, 5, 6, 7],
            'F': [1, 5, 8, 9],
            'B': [3, 7, 10, 11],
            'L': [2, 6, 9, 10],
            'R': [0, 4, 8, 11]
        }
        return face_edges.get(real_face, [])

    def _get_face_corners(self, face: str) -> list:
        """根据view_map获取指定观察面对应的真实角块编号"""
        real_face = self.view_map.get(face, face)
        face_corners = {
            'U': [0, 1, 2, 3],
            'D': [4, 5, 6, 7],
            'F': [0, 1, 4, 5],
            'B': [2, 3, 6, 7],
            'L': [1, 2, 5, 6],
            'R': [0, 3, 4, 7]
        }
        return face_corners.get(real_face, [])

    def _corner_color_on_face(self, corner_pos: int, face: str) -> str:
        """Return the sticker color currently on a real face of a corner position."""
        pos_faces = self.CORNER_FACES[corner_pos]
        cubie_faces = self.CORNER_FACES[self.cp[corner_pos]]
        ori = self.co[corner_pos]

        for color_idx, color in enumerate(cubie_faces):
            pos_face = pos_faces[(color_idx + ori) % 3]
            if pos_face == face:
                return color
        return ""

    def _edge_color_on_face(self, edge_pos: int, face: str) -> str:
        """Return the sticker color currently on a real face of an edge position."""
        pos_faces = self.EDGE_FACES[edge_pos]
        cubie_faces = self.EDGE_FACES[self.ep[edge_pos]]
        ori = self.eo[edge_pos]

        for color_idx, color in enumerate(cubie_faces):
            pos_face = pos_faces[(color_idx + ori) % 2]
            if pos_face == face:
                return color
        return ""

    # =====================================================
    # Cross
    # 动态适配 view_map 的底层Cross检测
    # =====================================================

    def is_cross_solved(self):
        d_edges = self._get_face_edges('D')
        if len(d_edges) != 4:
            return False
        for edge_idx in d_edges:
            if self.ep[edge_idx] != edge_idx or self.eo[edge_idx] != 0:
                return False
        return True

    # =====================================================
    # F2L
    # =====================================================

    def is_f2l_solved(self, slot: int):
        real_d = self.view_map.get('D', 'D')
        real_f = self.view_map.get('F', 'F')
        real_r = self.view_map.get('R', 'R')
        real_l = self.view_map.get('L', 'L')
        real_b = self.view_map.get('B', 'B')

        # 基于真实面的F2L槽位定义
        # 每个槽位由底层角块+同层棱块组成
        slot_definitions = {
            # (底层角块位置, 棱块位置)
            # Slot 1: D面+F面+R面交界处的角块和棱块
            1: self._get_f2l_slot_pieces(real_d, real_f, real_r),
            # Slot 2: D面+F面+L面交界处
            2: self._get_f2l_slot_pieces(real_d, real_f, real_l),
            # Slot 3: D面+B面+L面交界处
            3: self._get_f2l_slot_pieces(real_d, real_b, real_l),
            # Slot 4: D面+B面+R面交界处
            4: self._get_f2l_slot_pieces(real_d, real_b, real_r),
        }

        if slot not in slot_definitions:
            return False

        corner, edge = slot_definitions[slot]

        return (
            self.cp[corner] == corner
            and
            self.co[corner] == 0
            and
            self.ep[edge] == edge
            and
            self.eo[edge] == 0
        )

    def _get_f2l_slot_pieces(self, bottom_face: str, face1: str, face2: str):
        """获取指定F2L槽位的角块和棱块编号"""
        # Cubies are identified by their real face/color set. This works for
        # any CFOP bottom color, including side-color neutral solves.
        corner_map = {
            frozenset(('U', 'F', 'R')): 0,
            frozenset(('U', 'F', 'L')): 1,
            frozenset(('U', 'B', 'L')): 2,
            frozenset(('U', 'B', 'R')): 3,
            frozenset(('D', 'F', 'R')): 4,
            frozenset(('D', 'F', 'L')): 5,
            frozenset(('D', 'B', 'L')): 6,
            frozenset(('D', 'B', 'R')): 7,
        }

        # The F2L edge is the edge between the two side faces of the slot.
        edge_map = {
            frozenset(('U', 'R')): 0,
            frozenset(('U', 'F')): 1,
            frozenset(('U', 'L')): 2,
            frozenset(('U', 'B')): 3,
            frozenset(('D', 'R')): 4,
            frozenset(('D', 'F')): 5,
            frozenset(('D', 'L')): 6,
            frozenset(('D', 'B')): 7,
            frozenset(('F', 'R')): 8,
            frozenset(('F', 'L')): 9,
            frozenset(('B', 'L')): 10,
            frozenset(('B', 'R')): 11,
        }

        corner = corner_map.get(frozenset((bottom_face, face1, face2)))
        edge = edge_map.get(frozenset((face1, face2)))

        if corner is None or edge is None:
            return (0, 8)

        return (corner, edge)

    # =====================================================
    # OLL
    # 动态适配 view_map 的顶层OLL检测
    # =====================================================

    def is_oll_solved(self):
        real_u = self.view_map.get('U', 'U')
        u_corners = self._get_face_corners('U')
        u_edges = self._get_face_edges('U')

        for i in u_corners:
            if self._corner_color_on_face(i, real_u) != real_u:
                return False

        for i in u_edges:
            if self._edge_color_on_face(i, real_u) != real_u:
                return False

        return True

    # =====================================================
    # 获取6面色块颜色
    # =====================================================

    def get_face_colors(self):
        """返回当前观察坐标系下6个面的所有色块颜色

        Returns:
            dict: 键为观察面名称('U','D','F','B','L','R')，
                  值为3x3的颜色列表（按行排列），
                  颜色用面名表示('U','D','F','B','L','R')
        """

        corner_map = {
            frozenset(('U', 'F', 'R')): 0,
            frozenset(('U', 'F', 'L')): 1,
            frozenset(('U', 'B', 'L')): 2,
            frozenset(('U', 'B', 'R')): 3,
            frozenset(('D', 'F', 'R')): 4,
            frozenset(('D', 'F', 'L')): 5,
            frozenset(('D', 'B', 'L')): 6,
            frozenset(('D', 'B', 'R')): 7,
        }

        edge_map = {
            frozenset(('U', 'R')): 0,
            frozenset(('U', 'F')): 1,
            frozenset(('U', 'L')): 2,
            frozenset(('U', 'B')): 3,
            frozenset(('D', 'R')): 4,
            frozenset(('D', 'F')): 5,
            frozenset(('D', 'L')): 6,
            frozenset(('D', 'B')): 7,
            frozenset(('F', 'R')): 8,
            frozenset(('F', 'L')): 9,
            frozenset(('B', 'L')): 10,
            frozenset(('B', 'R')): 11,
        }

        # 每个观察面的3x3布局
        # (type, faces_tuple, display_face)
        # type: 'c'=角块, 'e'=棱块, 'm'=中心
        # faces_tuple: 组成该位置的观察面
        # display_face: 色块所在的观察面
        face_layouts = {
            'U': [
                ('c', ('U', 'B', 'L'), 'U'), ('e', ('U', 'B'), 'U'), ('c', ('U', 'B', 'R'), 'U'),
                ('e', ('U', 'L'), 'U'),       ('m', ('U',), 'U'),     ('e', ('U', 'R'), 'U'),
                ('c', ('U', 'F', 'L'), 'U'), ('e', ('U', 'F'), 'U'), ('c', ('U', 'F', 'R'), 'U'),
            ],
            'D': [
                ('c', ('D', 'F', 'L'), 'D'), ('e', ('D', 'F'), 'D'), ('c', ('D', 'F', 'R'), 'D'),
                ('e', ('D', 'L'), 'D'),       ('m', ('D',), 'D'),     ('e', ('D', 'R'), 'D'),
                ('c', ('D', 'B', 'L'), 'D'), ('e', ('D', 'B'), 'D'), ('c', ('D', 'B', 'R'), 'D'),
            ],
            'F': [
                ('c', ('U', 'F', 'L'), 'F'), ('e', ('U', 'F'), 'F'), ('c', ('U', 'F', 'R'), 'F'),
                ('e', ('F', 'L'), 'F'),       ('m', ('F',), 'F'),     ('e', ('F', 'R'), 'F'),
                ('c', ('D', 'F', 'L'), 'F'), ('e', ('D', 'F'), 'F'), ('c', ('D', 'F', 'R'), 'F'),
            ],
            'B': [
                ('c', ('U', 'B', 'R'), 'B'), ('e', ('U', 'B'), 'B'), ('c', ('U', 'B', 'L'), 'B'),
                ('e', ('B', 'R'), 'B'),       ('m', ('B',), 'B'),     ('e', ('B', 'L'), 'B'),
                ('c', ('D', 'B', 'R'), 'B'), ('e', ('D', 'B'), 'B'), ('c', ('D', 'B', 'L'), 'B'),
            ],
            'L': [
                ('c', ('U', 'L', 'B'), 'L'), ('e', ('U', 'L'), 'L'), ('c', ('U', 'L', 'F'), 'L'),
                ('e', ('L', 'B'), 'L'),       ('m', ('L',), 'L'),     ('e', ('L', 'F'), 'L'),
                ('c', ('D', 'L', 'B'), 'L'), ('e', ('D', 'L'), 'L'), ('c', ('D', 'L', 'F'), 'L'),
            ],
            'R': [
                ('c', ('U', 'R', 'F'), 'R'), ('e', ('U', 'R'), 'R'), ('c', ('U', 'R', 'B'), 'R'),
                ('e', ('R', 'F'), 'R'),       ('m', ('R',), 'R'),     ('e', ('R', 'B'), 'R'),
                ('c', ('D', 'R', 'F'), 'R'), ('e', ('D', 'R'), 'R'), ('c', ('D', 'R', 'B'), 'R'),
            ],
        }

        result = {}

        for obs_face, layout in face_layouts.items():
            colors = []
            for sticker_type, obs_faces, obs_display_face in layout:
                real_faces = tuple(self.view_map[f] for f in obs_faces)
                real_display_face = self.view_map[obs_display_face]

                if sticker_type == 'm':
                    colors.append(real_display_face)
                elif sticker_type == 'c':
                    corner_idx = corner_map.get(frozenset(real_faces))
                    if corner_idx is not None:
                        colors.append(self._corner_color_on_face(corner_idx, real_display_face))
                    else:
                        colors.append('')
                elif sticker_type == 'e':
                    edge_idx = edge_map.get(frozenset(real_faces))
                    if edge_idx is not None:
                        colors.append(self._edge_color_on_face(edge_idx, real_display_face))
                    else:
                        colors.append('')

            result[obs_face] = [
                colors[0:3],
                colors[3:6],
                colors[6:9],
            ]

        return result

    # =====================================================
    # OLL/PLL 编码与识别
    # =====================================================

    # OLL编码表：编号 -> 8位编码字符串
    OLL_TABLE = {
        1: "11111111", 2: "11112211", 3: "11110121", 4: "11111210",
        5: "11002101", 6: "10011012", 7: "11002120", 8: "10010212",
        9: "00111202", 10: "01102021", 11: "01102101", 12: "00111012",
        13: "10102120", 14: "10100212", 15: "10102101", 16: "10101012",
        17: "11110201", 18: "11110220", 19: "11111001", 20: "11110000",
        21: "00002222", 22: "00002211", 23: "00000220", 24: "00000022",
        25: "00002010", 26: "00001202", 27: "00002120", 28: "11000000",
        29: "10010110", 30: "11000110", 31: "01102200", 32: "00110022",
        33: "10100022", 34: "10101001", 35: "00110102", 36: "10010201",
        37: "11000102", 38: "11001020", 39: "10101020", 40: "10100201",
        41: "00112002", 42: "01102002", 43: "01101100", 44: "00110011",
        45: "10100011", 46: "01011100", 47: "10011122", 48: "11002211",
        49: "10012112", 50: "11002112", 51: "10102211", 52: "01011122",
        53: "10012222", 54: "11002222", 55: "01011111", 56: "10101111",
        57: "10100000",
        "skip": "00000000",
    }

    # PLL编码表：名称 -> 8位编码字符串
    PLL_TABLE = {
        "Aa": "01233102", "Ab": "01231320", "E": "01233210",
        "F": "21031023", "Ga": "02310312", "Gb": "31022130",
        "Gc": "03121203", "Gd": "12033021", "H": "23010123",
        "Ja": "31200132", "Jb": "10231023", "Na": "03210321",
        "Nb": "03212103", "Ra": "31200213", "Rb": "10230213",
        "T": "03211023", "Ua": "13200123", "Ub": "30210123",
        "V": "02132103", "Y": "01322103", "Z": "32100123",
        "skip": "01230123",
    }

    # 顶层棱块观察位置到真实棱块编号的映射
    # 顺序: UF, UR, UB, UL
    _OLL_EDGE_OBS = [
        ('U', 'F'),  # UF
        ('U', 'R'),  # UR
        ('U', 'B'),  # UB
        ('U', 'L'),  # UL
    ]

    # 顶层角块观察位置到真实角块编号的映射
    # 顺序: UFR, URB, UBL, ULF
    _OLL_CORNER_OBS = [
        ('U', 'F', 'R'),  # UFR
        ('U', 'R', 'B'),  # URB
        ('U', 'B', 'L'),  # UBL
        ('U', 'L', 'F'),  # ULF
    ]

    def encode_oll(self) -> str:
        """对当前顶层状态进行OLL编码

        编码规则：
        4棱（UF UR UB UL）+ 4角（UFR URB UBL ULF）
        棱块：U面颜色 == 当前观察系U面复原色 → 0，否则 → 1
        角块：U面颜色 == 当前观察系U面复原色 → 0；
              U面复原色在角块的R/L面 → 1；
              U面复原色在角块的F/B面 → 2

        Returns:
            str: 8位编码字符串，如 "11112211"
        """
        real_u = self.view_map.get('U', 'U')
        colors = self.get_face_colors()
        u_face = colors['U']

        # 4棱编码
        edge_codes = []
        # UF, UR, UB, UL 对应 U面的位置: (1,2), (2,2), (1,0), (0,1) → 但用行列更清晰
        # U面3x3布局:
        # [UBL][UB ][UBR]
        # [UL ][U  ][UR ]
        # [UFL][UF ][UFR]
        edge_positions = [
            (2, 1),  # UF
            (1, 2),  # UR
            (0, 1),  # UB
            (1, 0),  # UL
        ]
        for r, c in edge_positions:
            color = u_face[r][c]
            edge_codes.append('0' if color == real_u else '1')

        # 4角编码
        corner_codes = []
        # 角块在U面的位置
        corner_positions = [
            (2, 2),  # UFR
            (0, 2),  # URB
            (0, 0),  # UBL
            (2, 0),  # ULF
        ]
        # 角块对应的观察面组合
        corner_obs_faces = [
            ('U', 'F', 'R'),  # UFR
            ('U', 'R', 'B'),  # URB
            ('U', 'B', 'L'),  # UBL
            ('U', 'L', 'F'),  # ULF
        ]
        # 构建真实面到观察面的反向映射
        inv_view = {}
        for obs, real in self.view_map.items():
            inv_view[real] = obs

        for i, (r, c) in enumerate(corner_positions):
            u_color = u_face[r][c]
            if u_color == real_u:
                corner_codes.append('0')
            else:
                # 需要判断U面复原色在角块的哪个侧面
                obs_faces = corner_obs_faces[i]
                real_faces = tuple(self.view_map[f] for f in obs_faces)
                # 找到该角块的真实编号
                corner_idx = self._corner_map().get(frozenset(real_faces))
                if corner_idx is not None:
                    # 检查U面复原色在角块的哪个面
                    cubie = self.cp[corner_idx]
                    ori = self.co[corner_idx]
                    cubie_faces = self.CORNER_FACES[cubie]
                    pos_faces = self.CORNER_FACES[corner_idx]
                    for color_idx, color in enumerate(cubie_faces):
                        pos_face = pos_faces[(color_idx + ori) % 3]
                        if color == real_u:
                            # 将真实面转换为观察面再判断
                            obs_face = inv_view.get(pos_face, pos_face)
                            if obs_face in ('R', 'L'):
                                corner_codes.append('1')
                            else:
                                corner_codes.append('2')
                            break
                    else:
                        corner_codes.append('0')
                else:
                    corner_codes.append('0')

        return ''.join(edge_codes) + ''.join(corner_codes)

    def encode_pll(self) -> str:
        """对当前顶层状态进行PLL编码

        编码规则：
        UF=0 UR=1 UB=2 UL=3 UFR=0 URB=1 UBL=2 ULF=3
        按位置顺序编码，每个位置记录该位置当前棱块/角块属于哪个目标位置

        Returns:
            str: 8位编码字符串，如 "01233102"
        """
        # 构建真实面到观察面的反向映射
        inv_view = {}
        for obs, real in self.view_map.items():
            inv_view[real] = obs

        # 棱块目标位置映射（观察面）
        edge_target = {
            frozenset(('U', 'F')): 0,
            frozenset(('U', 'R')): 1,
            frozenset(('U', 'B')): 2,
            frozenset(('U', 'L')): 3,
        }

        # 角块目标位置映射（观察面）
        corner_target = {
            frozenset(('U', 'F', 'R')): 0,
            frozenset(('U', 'R', 'B')): 1,
            frozenset(('U', 'B', 'L')): 2,
            frozenset(('U', 'L', 'F')): 3,
        }

        # 4棱编码
        edge_codes = []
        edge_obs_list = [
            ('U', 'F'),  # UF位置
            ('U', 'R'),  # UR位置
            ('U', 'B'),  # UB位置
            ('U', 'L'),  # UL位置
        ]
        for obs_faces in edge_obs_list:
            real_faces = frozenset(self.view_map[f] for f in obs_faces)
            pos_idx = self._edge_map().get(real_faces)
            if pos_idx is not None:
                # 该位置上的棱块属于哪个目标位置
                cubie = self.ep[pos_idx]
                cubie_real_faces = self.EDGE_FACES[cubie]
                # 将棱块的真实面转换为观察面
                cubie_obs_faces = frozenset(inv_view.get(f, f) for f in cubie_real_faces)
                target = edge_target.get(cubie_obs_faces, 0)
                edge_codes.append(str(target))
            else:
                edge_codes.append('0')

        # 4角编码
        corner_codes = []
        corner_obs_list = [
            ('U', 'F', 'R'),  # UFR位置
            ('U', 'R', 'B'),  # URB位置
            ('U', 'B', 'L'),  # UBL位置
            ('U', 'L', 'F'),  # ULF位置
        ]
        for obs_faces in corner_obs_list:
            real_faces = frozenset(self.view_map[f] for f in obs_faces)
            pos_idx = self._corner_map().get(real_faces)
            if pos_idx is not None:
                cubie = self.cp[pos_idx]
                cubie_real_faces = self.CORNER_FACES[cubie]
                # 将角块的真实面转换为观察面
                cubie_obs_faces = frozenset(inv_view.get(f, f) for f in cubie_real_faces)
                target = corner_target.get(cubie_obs_faces, 0)
                corner_codes.append(str(target))
            else:
                corner_codes.append('0')

        return ''.join(edge_codes) + ''.join(corner_codes)

    def identify_oll(self) -> str:
        """识别当前OLL状态

        在4个y旋转方向上分别编码，与OLL编码表对比。

        Returns:
            str: OLL编号（如 "1"~"57"），未识别返回空字符串
        """
        if log:
            log.info("[OLL识别] 开始OLL识别")
            log.info(f"[OLL识别] 当前view_map: {self.view_map}")
            fc = self.get_face_colors()
            for face in ['U', 'D', 'F', 'B', 'L', 'R']:
                rows = [' '.join(r) for r in fc[face]]
                log.info(f"[OLL识别] {face}面: {' | '.join(rows)}")

        cube_copy = self.copy()
        for y_idx in range(4):
            code = cube_copy.encode_oll()
            if log:
                log.info(f"[OLL识别] y*{y_idx}方向: 编码={code}")
            for oll_num, oll_code in self.OLL_TABLE.items():
                if code == oll_code:
                    if log:
                        log.info(f"[OLL识别] ★ 匹配成功: OLL {oll_num} (y*{y_idx}方向)")
                    return str(oll_num)
            cube_copy.apply_rotation('y')

        if log:
            log.info("[OLL识别] 4个y方向均未匹配，OLL未识别")
        return ""

    def identify_pll(self) -> str:
        """识别当前PLL状态

        在4个y旋转方向上分别编码，与PLL编码表对比。
        若y旋转无法匹配，再尝试U旋转+ y旋转的组合。

        Returns:
            str: PLL名称（如 "Aa", "T"），未识别返回空字符串
        """
        if log:
            log.info("[PLL识别] 开始PLL识别")
            log.info(f"[PLL识别] 当前view_map: {self.view_map}")
            fc = self.get_face_colors()
            for face in ['U', 'D', 'F', 'B', 'L', 'R']:
                rows = [' '.join(r) for r in fc[face]]
                log.info(f"[PLL识别] {face}面: {' | '.join(rows)}")

        # 先尝试4个y旋转方向
        cube_copy = self.copy()
        for y_idx in range(4):
            code = cube_copy.encode_pll()
            if log:
                log.info(f"[PLL识别] y*{y_idx}方向: 编码={code}")
            for pll_name, pll_code in self.PLL_TABLE.items():
                if code == pll_code:
                    if log:
                        log.info(f"[PLL识别] ★ 匹配成功: PLL {pll_name} (y*{y_idx}方向)")
                    return pll_name
            cube_copy.apply_rotation('y')

        if log:
            log.info("[PLL识别] 4个y方向均未匹配，尝试U+y组合")

        # y旋转无法匹配时，尝试U旋转 + y旋转的组合
        cube_u = self.copy()
        for u_idx in range(3):  # U, U2, U' (已尝试过U0)
            cube_u.apply_move('U')
            if log:
                log.info(f"[PLL识别] 尝试U*{u_idx + 1}后的组合")
            cube_y = cube_u.copy()
            for y_idx in range(4):
                code = cube_y.encode_pll()
                if log:
                    log.info(f"[PLL识别] U*{u_idx + 1}+y*{y_idx}方向: 编码={code}")
                for pll_name, pll_code in self.PLL_TABLE.items():
                    if code == pll_code:
                        if log:
                            log.info(f"[PLL识别] ★ 匹配成功: PLL {pll_name} (U*{u_idx + 1}+y*{y_idx}方向)")
                        return pll_name
                cube_y.apply_rotation('y')

        if log:
            log.info("[PLL识别] 所有方向均未匹配，PLL未识别")
        return ""

    def _corner_map(self) -> dict:
        """角块面组合到角块编号的映射（缓存）"""
        if not hasattr(self, '_corner_map_cache'):
            self._corner_map_cache = {
                frozenset(('U', 'F', 'R')): 0,
                frozenset(('U', 'F', 'L')): 1,
                frozenset(('U', 'B', 'L')): 2,
                frozenset(('U', 'B', 'R')): 3,
                frozenset(('D', 'F', 'R')): 4,
                frozenset(('D', 'F', 'L')): 5,
                frozenset(('D', 'B', 'L')): 6,
                frozenset(('D', 'B', 'R')): 7,
            }
        return self._corner_map_cache

    def _edge_map(self) -> dict:
        """棱块面组合到棱块编号的映射（缓存）"""
        if not hasattr(self, '_edge_map_cache'):
            self._edge_map_cache = {
                frozenset(('U', 'R')): 0,
                frozenset(('U', 'F')): 1,
                frozenset(('U', 'L')): 2,
                frozenset(('U', 'B')): 3,
                frozenset(('D', 'R')): 4,
                frozenset(('D', 'F')): 5,
                frozenset(('D', 'L')): 6,
                frozenset(('D', 'B')): 7,
                frozenset(('F', 'R')): 8,
                frozenset(('F', 'L')): 9,
                frozenset(('B', 'L')): 10,
                frozenset(('B', 'R')): 11,
            }
        return self._edge_map_cache

    # =====================================================
    # utility
    # =====================================================

    def reset_view(self):

        self.view_map = {

            'U': 'U',
            'D': 'D',
            'F': 'F',
            'B': 'B',
            'L': 'L',
            'R': 'R'
        }

    # =====================================================
    # debug
    # =====================================================

    def dump(self):

        print('cp', self.cp)
        print('co', self.co)

        print('ep', self.ep)
        print('eo', self.eo)

        print('view', self.view_map)
