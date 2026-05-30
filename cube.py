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

        # 观察坐标系 -> 真实面
        real_face = self.view_map[face]

        times = 1

        if len(move) > 1:

            if move[1] == '2':
                times = 2

            elif move[1] == "'":
                times = 3

        for _ in range(times):
            self._apply_single_move(real_face)

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
