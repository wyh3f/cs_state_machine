"""
画布交互层 —— 用原生 tk.Canvas 实现状态节点和箭头的绘制与编辑
customtkinter 没有 Canvas 控件，这里直接继承 tk.Canvas

交互约定：
    单击            选中（节点高亮 / 转移变蓝）
    拖动节点        移动位置，相连转移实时跟随
    双击节点        重命名
    双击转移标签    编辑事件名
    右键            上下文菜单（重命名 / 设为初始 / 删除 / 编辑事件）
    Delete          删除当前选中项
    按住 Ctrl       进入连接模式：点第一个状态为起点（绿色），
                    之后点其他状态即创建连线，松开 Ctrl 退出
"""

import math
import tkinter as tk
from tkinter import messagebox, simpledialog


class StateCanvas(tk.Canvas):
    """状态机画布：绘制、拖拽、编辑状态节点与转移"""

    # 节点尺寸
    NODE_W = 140
    NODE_H = 60
    # 初始标记默认位置（相对节点中心，沿左上角对角线向外 14px）
    DEFAULT_MARKER_OFFSET = (-NODE_W // 2 - 14, -NODE_H // 2 - 14)
    # 最终标记默认位置（右下角对角线外侧）
    DEFAULT_FINAL_MARKER_OFFSET = (NODE_W // 2 + 14, NODE_H // 2 + 14)
    # 复合状态（状态包容状态）外框
    COMPOSITE_FILL = "#f2f6fb"
    COMPOSITE_OUTLINE = "#8296ad"
    COMPOSITE_PAD = 32        # 子状态到外框的内边距
    COMPOSITE_HEADER = 30     # 标题栏高度
    MIN_NODE_W = 100          # 手动缩放的最小尺寸
    MIN_NODE_H = 48
    RESIZE_HANDLE = 5         # 右下角缩放手柄半径
    # 画布缩放
    ZOOM_MIN = 0.4
    ZOOM_MAX = 2.5
    ZOOM_STEP = 1.1

    # 颜色
    BG_COLOR = "#ffffff"
    NODE_FILL = "#e8f0fe"
    NODE_OUTLINE = "#3b8ed0"
    NODE_SELECTED_FILL = "#d4e4fc"
    NODE_SELECTED_OUTLINE = "#1a6bc5"
    ARROW_COLOR = "#666666"
    ARROW_SELECTED_COLOR = "#1a6bc5"
    LABEL_COLOR = "#555555"
    INIT_MARKER = "#2e7d32"
    INIT_FILL = "#e6f7ea"             # 初始状态节点填充（浅绿）
    INIT_OUTLINE = "#2e7d32"
    LINK_SOURCE_FILL = "#fdecc8"      # 连接起点填充（浅橙，与初始状态的绿区分）
    LINK_SOURCE_OUTLINE = "#e08a00"
    CANVAS_BORDER = "#c9ced6"         # 画布与左右面板的分隔边框
    # 状态内部动作（UML 状态机：进入 / 退出 / 执行）
    STATE_ACTION_KINDS = ("entry", "exit", "do")
    STATE_ACTION_LABELS = {"entry": "进入", "exit": "退出", "do": "执行"}

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            bg=self.BG_COLOR,
            highlightthickness=1,
            highlightbackground=self.CANVAS_BORDER,
            takefocus=1,
            **kwargs,
        )

        # 状态数据：{ node_id: { "name", "x", "y", "is_initial",
        #                       "items": [所有画布元素], "rect_id", "text_id",
        #                       "marker_items": [...] } }
        self.nodes = {}
        # 转移数据：{ trans_id: { "from", "to", "event", "line_id", "label_id" } }
        self.transitions = {}

        # 选中状态（节点与转移都支持多选；selected_trans 为属性面板的主对象）
        self.selected_nodes = set()
        self.selected_transes = set()
        self.selected_trans = None

        self._node_seq = 0
        self._trans_seq = 0
        self._drag = None
        self._rubber = None     # 框选状态
        self._marker_drag = None  # 拖动初始标记状态
        self._line_drag = None    # 拖动连线调整路线状态
        self._label_drag = None   # 拖动事件标签状态
        self._resize_drag = None  # 拖动右下角手柄改变状态尺寸
        self._resize_item = None  # 右下角缩放手柄
        self._resize_nid = None
        self._handle_items = []   # 选中连线时显示的折点手柄
        self._clipboard = None  # 复制缓存
        self._paste_seq = 0     # 连续粘贴的偏移递增
        self._undo_stack = []   # 撤销快照栈
        self._redo_stack = []   # 重做快照栈

        # 连接模式：按住 Ctrl 进入，第一个点中的状态作为起点
        self.link_mode = False
        self.link_source = None
        self._hint_items = []
        self._hint_after = None     # 延迟显示提示的定时器（避免 Ctrl+C 等组合键闪烁）

        # 数据变化回调（供外部刷新状态栏/属性面板）
        self.on_change = None
        # 选中对象变化回调（供外部刷新标签表）
        self.on_select = None
        # 画布缩放（1.0 = 100%）
        self.zoom = 1.0
        self._text_base = {}
        self.on_zoom = None
        # 多画布时由外部提供：返回 True 表示当前画布处于激活状态。
        # 顶层快捷键绑定会在每个画布实例上各挂一份，需要用它过滤。
        self.active_check = None

        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Button-3>", self._on_right_click)
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<BackSpace>", self._on_delete_key)

        # Ctrl 按下/松开：绑定到顶层窗口，焦点在任意子控件都能收到
        top = self.winfo_toplevel()
        for seq in ("<KeyPress-Control_L>", "<KeyPress-Control_R>"):
            top.bind(seq, self._on_ctrl_press, add="+")
        for seq in ("<KeyRelease-Control_L>", "<KeyRelease-Control_R>"):
            top.bind(seq, self._on_ctrl_release, add="+")

        # 常用快捷键（与连接模式共用 Ctrl，组合键会取消提示定时器）
        for seq in ("<Control-a>", "<Control-A>"):
            top.bind(seq, self._on_select_all, add="+")
        for seq in ("<Control-c>", "<Control-C>"):
            top.bind(seq, self._on_copy, add="+")
        for seq in ("<Control-v>", "<Control-V>"):
            top.bind(seq, self._on_paste, add="+")
        for seq in ("<Control-d>", "<Control-D>"):
            top.bind(seq, self._on_duplicate, add="+")
        for seq in ("<Control-z>", "<Control-Z>"):
            top.bind(seq, self._on_undo, add="+")
        for seq in ("<Control-y>", "<Control-Y>"):
            top.bind(seq, self._on_redo, add="+")

        # 画布缩放：Ctrl+滚轮、Ctrl+=/-/0
        self.bind("<Control-MouseWheel>", self._on_zoom_wheel)
        for seq in ("<Control-equal>", "<Control-plus>"):
            top.bind(seq, self._on_zoom_in, add="+")
        for seq in ("<Control-minus>", "<Control-underscore>"):
            top.bind(seq, self._on_zoom_out, add="+")
        top.bind("<Control-Key-0>", self._on_zoom_reset, add="+")

    # ── 工程文件 ────────────────────────────────────────────
    def _reset_canvas(self):
        """清空画布数据与交互状态"""
        self.delete("all")
        self._text_base.clear()
        self.zoom = 1.0
        self.nodes.clear()
        self.transitions.clear()
        self.selected_nodes = set()
        self.selected_transes = set()
        self.selected_trans = None
        self._drag = None
        self._rubber = None
        self._marker_drag = None
        self._line_drag = None
        self._label_drag = None
        self._resize_drag = None
        self._resize_item = None
        self._resize_nid = None
        self._handle_items = []
        self._cancel_hint_timer()
        self._hide_hint()
        self.link_mode = False
        self.link_source = None
        self._node_seq = 0
        self._trans_seq = 0
        self._undo_stack.clear()
        self._redo_stack.clear()

    def new_project(self):
        """新建空白工程：只放一个初始状态"""
        self._reset_canvas()
        nid = self._add_node("IDLE", 220, 200, is_initial=True)
        self._select_node(nid)
        self._notify()
        self._notify_selection()

    def export_state(self):
        """导出画布数据（用于保存工程文件）"""
        data = self._snapshot()
        data.pop("zoom", None)
        return data

    def import_state(self, data):
        """从工程文件恢复画布（缩放重置为 100%）"""
        snap = dict(data)
        snap["zoom"] = 1.0
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._restore(snap)
        self._notify()

    # ── 示例数据 ────────────────────────────────────────────
    def demo_states(self):
        """画几个示例状态和转移，让用户看到效果"""
        self._reset_canvas()

        demo_nodes = [
            ("IDLE",    120, 180, True),   # 初始状态
            ("RUNNING", 380, 120, False),
            ("ERROR",   380, 260, False),
            ("DONE",    640, 180, False),
        ]
        ids = {}
        for name, x, y, is_initial in demo_nodes:
            ids[name] = self._add_node(name, x, y, is_initial)

        demo_trans = [
            ("IDLE",    "RUNNING", "START"),
            ("RUNNING", "ERROR",   "ERROR_OCC"),
            ("RUNNING", "DONE",    "FINISH"),
        ]
        for fr, to, event in demo_trans:
            self._add_transition(ids[fr], ids[to], event)

        self._notify()
        self._notify_selection()

    # ── 缩放 ────────────────────────────────────────────────
    def _u(self, value):
        """把设计尺寸换算成当前缩放下的像素"""
        return value * self.zoom

    def _is_active(self):
        """多画布时只有激活画布响应顶层快捷键"""
        return self.active_check() if self.active_check else True

    def _create_text(self, x, y, text, size=10, bold=False,
                     fill="#1a1a1a", anchor="center"):
        """统一创建文字并记录基准字号，缩放时按比例重设"""
        item = self.create_text(
            x, y, text=text, fill=fill, anchor=anchor,
            font=("Segoe UI", max(1, int(round(size * self.zoom))),
                  "bold" if bold else "normal"),
        )
        self._text_base[item] = (size, bold)
        return item

    def set_zoom(self, zoom, ax=None, ay=None):
        """缩放画布；ax/ay 为缩放锚点（默认画布中心）"""
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, float(zoom)))
        factor = zoom / self.zoom
        if abs(factor - 1) < 1e-6:
            return
        if ax is None:
            ax = self.winfo_width() / 2
        if ay is None:
            ay = self.winfo_height() / 2
        self.scale("all", ax, ay, factor, factor)
        for n in self.nodes.values():
            n["x"] = ax + (n["x"] - ax) * factor
            n["y"] = ay + (n["y"] - ay) * factor
            n["w"] *= factor
            n["h"] *= factor
            for key in ("manual_w", "manual_h"):
                if n.get(key):
                    n[key] *= factor
            for key in ("marker_offset", "final_marker_offset"):
                if n.get(key):
                    n[key] = [v * factor for v in n[key]]
        for t in self.transitions.values():
            t["waypoints"] = [
                (ax + (x - ax) * factor, ay + (y - ay) * factor)
                for x, y in (t.get("waypoints") or [])
            ]
            t["label_offset"] = [
                v * factor for v in (t.get("label_offset") or (0, 0))
            ]
        self.zoom = zoom
        for item in list(self._text_base):
            size, bold = self._text_base[item]
            try:
                self.itemconfigure(
                    item,
                    font=("Segoe UI",
                          max(1, int(round(size * zoom))),
                          "bold" if bold else "normal"),
                )
            except tk.TclError:
                self._text_base.pop(item, None)
        self._hide_hint()
        self._refresh_handles()
        self._refresh_resize_handle()
        if self.on_zoom:
            self.on_zoom(self.zoom)

    def _on_zoom_wheel(self, event):
        self._cancel_hint_timer()
        if self.link_mode:
            self._exit_link_mode()
        factor = self.ZOOM_STEP if event.delta > 0 else 1 / self.ZOOM_STEP
        self.set_zoom(self.zoom * factor, event.x, event.y)
        return "break"

    def _on_zoom_in(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        self.set_zoom(self.zoom * self.ZOOM_STEP)
        return "break"

    def _on_zoom_out(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        self.set_zoom(self.zoom / self.ZOOM_STEP)
        return "break"

    def _on_zoom_reset(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        self.set_zoom(1.0)
        return "break"

    # ── 节点 ────────────────────────────────────────────────
    def _add_node(self, name, cx, cy, is_initial=False, node_id=None,
                  actions=None, actions_on=None, is_final=False,
                  final_marker_offset=None, internal=None):
        if node_id is None:
            node_id = f"n{self._node_seq}"
        self._node_seq = max(self._node_seq, int(node_id[1:]) + 1)

        w0, h0 = self._u(self.NODE_W), self._u(self.NODE_H)
        x0, y0 = cx - w0 / 2, cy - h0 / 2
        x1, y1 = cx + w0 / 2, cy + h0 / 2

        rect_id = self._round_rect(
            x0, y0, x1, y1, r=6,
            fill=self.NODE_FILL, outline=self.NODE_OUTLINE, width=2,
        )
        text_id = self._create_text(
            cx, cy, name, size=11, bold=True, fill="#1a1a1a",
        )

        self.nodes[node_id] = {
            "name": name, "x": cx, "y": cy,
            "is_initial": is_initial,
            "actions": {
                kind: (actions or {}).get(kind, "")
                for kind in self.STATE_ACTION_KINDS
            },
            # 开关状态独立保存：留空时也保持开启，不因内容为空自动关闭
            "actions_on": (
                any((v or "").strip() for v in (actions or {}).values())
                if actions_on is None else bool(actions_on)
            ),
            # 内部转移：事件 + 守卫 + 动作，留在当前状态执行
            "internal": [
                {
                    "event": (item.get("event") or "").strip(),
                    "guard": item.get("guard") or "",
                    "action": item.get("action") or "",
                }
                for item in (internal or [])
            ],
            "is_final": is_final,
            # 复合状态：parent 为所属父状态 id，None 表示顶层状态
            "parent": None,
            "items": [rect_id, text_id],
            "rect_id": rect_id, "text_id": text_id,
            "w": w0, "h": h0,
            # 手动缩放后的最小尺寸（None 表示按内容自动计算）
            "manual_w": None, "manual_h": None,
            "sep_id": None, "sep2_id": None, "action_items": [],
            "marker_items": [],
            "final_marker_items": [],
            "final_marker_offset": list(
                final_marker_offset or self.DEFAULT_FINAL_MARKER_OFFSET),
            # 未手动拖动时，标记随状态尺寸自动贴住角落
            "marker_auto": True,
            "final_marker_auto": True,
        }
        if is_initial:
            self._add_initial_marker(node_id)
        if is_final:
            self._add_final_marker(node_id)
        # 有内部动作时按 UML 分区显示，节点高度随行数变化
        self._refresh_node_actions(node_id, redraw_links=False)
        self._apply_node_style(node_id)
        return node_id

    # ── 复合状态（状态包容状态） ────────────────────────────
    def children_of(self, nid):
        """直接子状态 id 列表"""
        return [mid for mid, m in self.nodes.items()
                if m.get("parent") == nid]

    def is_composite(self, nid):
        """有直接子状态即为复合状态"""
        return any(m.get("parent") == nid for m in self.nodes.values())

    def _descendants(self, nid):
        """所有后代状态 id（不含自身）"""
        out = []
        stack = list(self.children_of(nid))
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(self.children_of(cur))
        return out

    def _node_depth(self, nid):
        """层级深度：顶层为 0"""
        depth = 0
        cur = self.nodes.get(nid)
        while cur and cur.get("parent"):
            depth += 1
            cur = self.nodes.get(cur["parent"])
        return depth

    def parent_of(self, nid):
        return (self.nodes.get(nid) or {}).get("parent")

    def _containment_target(self, nid, x, y, exclude=()):
        """返回应包含 (x, y) 的最内层状态；排除自身、后代与额外排除项"""
        blocked = {nid, *self._descendants(nid), *exclude}
        best, best_area = None, None
        for mid, m in self.nodes.items():
            if mid in blocked:
                continue
            # 落点需在边框内侧 8px，避免边缘擦过就变成包含关系
            if (abs(x - m["x"]) <= m["w"] / 2 - 8
                    and abs(y - m["y"]) <= m["h"] / 2 - 8):
                area = m["w"] * m["h"]
                if best_area is None or area < best_area:
                    best, best_area = mid, area
        return best

    def set_parent(self, nid, parent_id):
        """设置或取消父状态（None 表示移出为顶层）"""
        n = self.nodes.get(nid)
        if not n:
            return False
        if parent_id == nid or parent_id in self._descendants(nid):
            return False
        if parent_id is not None and parent_id not in self.nodes:
            return False
        if n.get("parent") == parent_id:
            return False
        self._push_undo()
        old = n.get("parent")
        n["parent"] = parent_id
        self._resolve_initial_scope(nid)
        for pid in {old, parent_id}:
            if pid in self.nodes:
                self._refresh_node_actions(pid)
        self._notify()
        return True

    def _drag_group_ids(self, nid):
        """拖动时一起处理的状态：多选取被选中的最外层状态"""
        if len(self.selected_nodes) <= 1 or nid not in self.selected_nodes:
            return [nid]
        sel = [x for x in self.selected_nodes if x in self.nodes]
        return [x for x in sel
                if not any(self._is_ancestor(o, x) for o in sel if o != x)]

    def _enter_parent(self, parent_id, nids):
        """把一组状态挂到指定大状态框下，保持原有相对位置"""
        for nid in nids:
            self.nodes[nid]["parent"] = parent_id
            self._resolve_initial_scope(nid)
        self._refresh_node_actions(parent_id)

    def _refresh_containment(self, nid):
        """拖动结束后按落点更新归属；多选时整组一起进入大状态框"""
        n = self.nodes.get(nid)
        if not n:
            return
        group = self._drag_group_ids(nid)
        olds = {self.nodes[x].get("parent") for x in group}
        target = self._containment_target(
            nid, n["x"], n["y"], exclude=set(group))
        if target is not None:
            if not all(self.nodes[x].get("parent") == target for x in group):
                # 拖入时保持整组相对位置，只改归属
                self._enter_parent(target, group)
        else:
            for x in group:
                self.nodes[x]["parent"] = None
                self._resolve_initial_scope(x)
        for pid in {*olds, target}:
            if pid in self.nodes:
                self._refresh_node_actions(pid)

    def _resolve_initial_scope(self, nid):
        """换了父状态后，保证同一层只有一个初始状态"""
        n = self.nodes.get(nid)
        if not n or not n.get("is_initial"):
            return
        scope = n.get("parent")
        for other_id, other in self.nodes.items():
            if (other_id != nid and other.get("is_initial")
                    and other.get("parent") == scope):
                self._remove_initial_marker(other_id)
                other["is_initial"] = False
                self._apply_node_style(other_id)

    def _layout_composite(self, nid, lines):
        """按子状态范围计算复合状态外框：标题在左上，动作在底部"""
        n = self.nodes[nid]
        kids = [self.nodes[cid] for cid in self.children_of(nid)]
        pad = self._u(self.COMPOSITE_PAD)
        header = self._u(self.COMPOSITE_HEADER)
        footer = (len(lines) * self._u(16) + self._u(14)) if lines else 0

        if kids:
            left = min(k["x"] - k["w"] / 2 for k in kids) - pad
            right = max(k["x"] + k["w"] / 2 for k in kids) + pad
            top = min(k["y"] - k["h"] / 2 for k in kids) - header - pad
            bottom = max(k["y"] + k["h"] / 2 for k in kids) + pad + footer
            # 子状态的初始/最终标记也要包进外框，避免压住标题栏
            for k in kids:
                if k.get("marker_items"):
                    mx = k["x"] + k["marker_offset"][0]
                    my = k["y"] + k["marker_offset"][1]
                    left = min(left, mx - self._u(14))
                    top = min(top, my - self._u(52))
                if k.get("final_marker_items"):
                    mx = k["x"] + k["final_marker_offset"][0]
                    my = k["y"] + k["final_marker_offset"][1]
                    right = max(right, mx + self._u(14))
                    bottom = max(bottom, my + self._u(34) + footer)
        else:
            left, right = n["x"] - self._u(110), n["x"] + self._u(110)
            top = n["y"] - self._u(70)
            bottom = n["y"] + self._u(70) + footer

        # 最小尺寸，避免空复合状态被压成一条
        min_w, min_h = self._u(220), self._u(110)
        if right - left < min_w:
            cx = (left + right) / 2
            left, right = cx - min_w / 2, cx + min_w / 2
        if bottom - top < min_h + footer:
            cy = (top + bottom) / 2
            half = (min_h + footer) / 2
            top, bottom = cy - half, cy + half
        # 手动缩放只作为最小尺寸，子状态变多时仍会自动撑开
        mw = n.get("manual_w") or 0
        mh = n.get("manual_h") or 0
        if right - left < mw:
            cx = (left + right) / 2
            left, right = cx - mw / 2, cx + mw / 2
        if bottom - top < mh:
            cy = (top + bottom) / 2
            top, bottom = cy - mh / 2, cy + mh / 2

        n["x"], n["y"] = (left + right) / 2, (top + bottom) / 2
        n["w"], n["h"] = right - left, bottom - top
        if n.get("marker_auto", True) and n["marker_items"]:
            n["marker_offset"] = self._marker_default(n)
        if n.get("final_marker_auto", True) and n.get("final_marker_items"):
            n["final_marker_offset"] = self._marker_default(n, final=True)

        fill, outline, width = self._node_style(nid)
        old_rect = n["rect_id"]
        index = n["items"].index(old_rect)
        self.delete(old_rect)
        rect_id = self._round_rect(
            left, top, right, bottom, r=8,
            fill=fill, outline=outline, width=width,
        )
        n["rect_id"] = rect_id
        n["items"][index] = rect_id
        # 外框保持在所有子状态下方
        self.tag_lower(rect_id)

        self.itemconfigure(n["text_id"], anchor="nw")
        self.coords(n["text_id"], left + self._u(12), top + self._u(9))
        n["sep_id"] = self.create_line(
            left + 1, top + header, right - 1, top + header,
            fill="#b9c4d2", width=1,
        )
        n["items"].append(n["sep_id"])

        if lines:
            fy = bottom - footer
            n["sep2_id"] = self.create_line(
                left + 1, fy, right - 1, fy, fill="#b9c4d2", width=1,
            )
            n["items"].append(n["sep2_id"])
            for i, (line, is_internal) in enumerate(lines):
                item = self._create_text(
                    left + self._u(12),
                    fy + self._u(8) + self._u(16) * i,
                    line, size=8, anchor="nw",
                    fill="#1a6bc5" if is_internal else "#555555",
                )
                n["action_items"].append(item)
                n["items"].append(item)

        if n["marker_items"]:
            self._layout_initial_marker(nid)
        if n.get("final_marker_items"):
            self._layout_final_marker(nid)

        for tid, t in self.transitions.items():
            if t["from"] == nid or t["to"] == nid:
                self._update_transition_coords(tid)

    def _add_initial_marker(self, node_id):
        """初始标记：大实心圆 + 指向节点的粗线 + INIT 文字，可绕节点拖动"""
        n = self.nodes[node_id]
        n["marker_offset"] = list(
            n.get("marker_offset") or self._marker_default(n)
        )
        items = [
            self.create_oval(
                0, 0, 0, 0,
                fill=self.INIT_MARKER, outline="#1b5e20", width=2,
            ),
            self.create_line(0, 0, 0, 0, fill=self.INIT_MARKER, width=3),
            self._create_text(
                0, 0, "INIT", size=8, bold=True, fill=self.INIT_MARKER,
            ),
        ]
        n["marker_items"] = items
        n["items"].extend(items)
        self._layout_initial_marker(node_id)

    def _layout_initial_marker(self, node_id):
        """按 marker_offset 重新摆放初始标记的圆、连线和文字"""
        n = self.nodes.get(node_id)
        if not n or not n["marker_items"]:
            return
        mx = n["x"] + n["marker_offset"][0]
        my = n["y"] + n["marker_offset"][1]
        oval_id, line_id, text_id = n["marker_items"]
        r = self._u(9)
        self.coords(oval_id, mx - r, my - r, mx + r, my + r)

        # 引线指向状态框上离标记最近的点：标记在左上角外侧时正好对准左上角
        ex, ey = self._node_nearest_point(n, mx, my)
        dx, dy = ex - mx, ey - my
        length = math.hypot(dx, dy) or 1.0
        self.coords(
            line_id,
            mx + dx / length * r, my + dy / length * r,
            ex, ey,
        )
        self.coords(text_id, mx, my - self._u(18))

    def _clamp_marker_offset(self, n, x, y):
        """限制标记在状态周围，且不能压进状态框内部"""
        node_w = n.get("w", self._u(self.NODE_W))
        node_h = n.get("h", self._u(self.NODE_H))
        max_dx = node_w / 2 + self._u(80)
        max_dy = node_h / 2 + self._u(70)
        dx = max(-max_dx, min(max_dx, x - n["x"]))
        dy = max(-max_dy, min(max_dy, y - n["y"]))

        inner_x = node_w / 2 + self._u(10)
        inner_y = node_h / 2 + self._u(10)
        if abs(dx) < inner_x and abs(dy) < inner_y:
            if inner_x - abs(dx) <= inner_y - abs(dy):
                dx = inner_x if dx >= 0 else -inner_x
            else:
                dy = inner_y if dy >= 0 else -inner_y
        return dx, dy

    def _marker_default(self, n, final=False):
        """按当前状态尺寸计算角落默认位置"""
        dx = n.get("w", self._u(self.NODE_W)) / 2 + self._u(14)
        dy = n.get("h", self._u(self.NODE_H)) / 2 + self._u(14)
        return [dx, dy] if final else [-dx, -dy]

    def _move_initial_marker(self, node_id, x, y, record=True):
        """把初始标记拖到 (x, y)，限制在状态周围一定范围内"""
        n = self.nodes[node_id]
        n["marker_auto"] = False
        n["marker_offset"] = list(self._clamp_marker_offset(n, x, y))
        self._layout_initial_marker(node_id)
        if record:
            self._notify()

    def _add_final_marker(self, node_id):
        """最终标记：空心圆环 + 实心圆点 + 引线，可绕节点拖动"""
        n = self.nodes[node_id]
        n["final_marker_offset"] = list(
            n.get("final_marker_offset") or self._marker_default(n, final=True)
        )
        items = [
            self.create_line(0, 0, 0, 0, fill="#333333", width=2),
            self.create_oval(
                0, 0, 0, 0, fill="#ffffff", outline="#333333", width=2),
            self.create_oval(0, 0, 0, 0, fill="#333333", outline="#333333"),
            self._create_text(
                0, 0, "FINAL", size=8, bold=True, fill="#333333",
            ),
        ]
        n["final_marker_items"] = items
        n["items"].extend(items)
        self._layout_final_marker(node_id)

    def _layout_final_marker(self, node_id):
        """按 final_marker_offset 重新摆放最终标记"""
        n = self.nodes.get(node_id)
        if not n or not n["final_marker_items"]:
            return
        mx = n["x"] + n["final_marker_offset"][0]
        my = n["y"] + n["final_marker_offset"][1]
        line_id, outer_id, inner_id, text_id = n["final_marker_items"]
        r = self._u(9)
        ri = self._u(4.5)
        self.coords(outer_id, mx - r, my - r, mx + r, my + r)
        self.coords(inner_id, mx - ri, my - ri, mx + ri, my + ri)

        ex, ey = self._node_nearest_point(n, mx, my)
        dx, dy = ex - mx, ey - my
        length = math.hypot(dx, dy) or 1.0
        self.coords(
            line_id,
            mx + dx / length * r, my + dy / length * r,
            ex, ey,
        )
        self.coords(text_id, mx, my + self._u(18))

    def _move_final_marker(self, node_id, x, y, record=True):
        """把最终标记拖到 (x, y)"""
        n = self.nodes[node_id]
        n["final_marker_auto"] = False
        n["final_marker_offset"] = list(self._clamp_marker_offset(n, x, y))
        self._layout_final_marker(node_id)
        if record:
            self._notify()

    def _hit_marker(self, x, y):
        """命中标记时返回 (节点 id, "initial" / "final")"""
        for nid, n in self.nodes.items():
            for kind, key, index in (
                ("initial", "marker_items", 0),
                ("final", "final_marker_items", 1),
            ):
                items = n.get(key) or []
                if not items:
                    continue
                x0, y0, x1, y1 = self.coords(items[index])
                if x0 - 3 <= x <= x1 + 3 and y0 - 3 <= y <= y1 + 3:
                    return nid, kind
        return None, None

    # ── 右下角缩放手柄 ──────────────────────────────────────
    def _refresh_resize_handle(self):
        """只在单选状态时显示右下角缩放手柄"""
        if self._resize_item is not None:
            self.delete(self._resize_item)
            self._resize_item = None
            self._resize_nid = None
        if len(self.selected_nodes) != 1 or self.link_mode:
            return
        nid = next(iter(self.selected_nodes))
        n = self.nodes.get(nid)
        if not n:
            return
        x = n["x"] + n["w"] / 2
        y = n["y"] + n["h"] / 2
        r = self.RESIZE_HANDLE
        self._resize_item = self.create_rectangle(
            x - r, y - r, x + r, y + r,
            fill="#ffffff", outline=self.NODE_SELECTED_OUTLINE, width=2,
        )
        self.tag_raise(self._resize_item)
        self._resize_nid = nid

    def _hit_resize(self, x, y):
        if self._resize_item is None:
            return None
        x0, y0, x1, y1 = self.coords(self._resize_item)
        if x0 - 3 <= x <= x1 + 3 and y0 - 3 <= y <= y1 + 3:
            return self._resize_nid
        return None

    def _is_ancestor(self, a, b):
        """a 是否为 b 的祖先"""
        cur = self.nodes.get(b)
        while cur and cur.get("parent"):
            if cur["parent"] == a:
                return True
            cur = self.nodes.get(cur["parent"])
        return False

    def _move_node_to(self, nid, nx, ny):
        """把状态（含所有后代）移动到指定中心点"""
        n = self.nodes[nid]
        dx, dy = nx - n["x"], ny - n["y"]
        for mid in {nid, *self._descendants(nid)}:
            m = self.nodes[mid]
            for item in m["items"]:
                self.move(item, dx, dy)
            m["x"] += dx
            m["y"] += dy
        for tid, t in self.transitions.items():
            if t["from"] in {nid, *self._descendants(nid)} or \
                    t["to"] in {nid, *self._descendants(nid)}:
                self._update_transition_coords(tid)

    def select_children(self, nid):
        """选中复合状态内部的所有状态"""
        kids = set(self._descendants(nid))
        if not kids:
            return
        self._clear_trans_selection()
        self.selected_nodes = kids
        self._refresh_node_styles()
        self._refresh_resize_handle()
        self._notify_selection()

    def _next_group_name(self):
        i = 1
        while self._name_taken(f"GROUP_{i}"):
            i += 1
        return f"GROUP_{i}"

    def wrap_selected(self, name=None):
        """把选中的状态包进一个新建的大状态框"""
        nids = [nid for nid in self.selected_nodes if nid in self.nodes]
        nids = [nid for nid in nids
                if not any(self._is_ancestor(o, nid)
                           for o in nids if o != nid)]
        if not nids:
            return None
        if name is None:
            name = simpledialog.askstring(
                "新建大状态框", "状态名：",
                initialvalue=self._next_group_name(), parent=self,
            )
            if name is None:
                return None
            name = name.strip()
            if not name:
                return None
            if self._name_taken(name):
                messagebox.showerror("重名", f"已存在状态「{name}」", parent=self)
                return None
        self._push_undo()
        left = min(self.nodes[x]["x"] - self.nodes[x]["w"] / 2 for x in nids)
        right = max(self.nodes[x]["x"] + self.nodes[x]["w"] / 2 for x in nids)
        top = min(self.nodes[x]["y"] - self.nodes[x]["h"] / 2 for x in nids)
        bottom = max(self.nodes[x]["y"] + self.nodes[x]["h"] / 2 for x in nids)
        pid = self._add_node(name, (left + right) / 2, (top + bottom) / 2)
        for nid in nids:
            self.nodes[nid]["parent"] = pid
            self._resolve_initial_scope(nid)
        self._refresh_node_actions(pid)
        self._clear_trans_selection()
        self.selected_nodes = {pid}
        self._refresh_node_styles()
        self._refresh_resize_handle()
        self._notify_selection()
        self._notify()
        return pid

    def _root_of(self, nid):
        """最外层祖先状态 id（含自身）"""
        root = nid
        pid = self.nodes.get(nid, {}).get("parent")
        while pid in self.nodes:
            root = pid
            pid = self.nodes[pid].get("parent")
        return root

    def remove_selected_from_parent(self):
        """把选中的状态一次性移出大状态框，摆到最外层状态右侧"""
        nids = [nid for nid in self.selected_nodes
                if nid in self.nodes and self.nodes[nid].get("parent")]
        if not nids:
            return False
        self._push_undo()
        # 先记下各自原来所属的最外层状态，收缩后再按它摆放
        anchors = {}
        old_parents = set()
        for nid in nids:
            pid = self.nodes[nid].get("parent")
            old_parents.add(pid)
            anchors[nid] = self._root_of(pid) if pid in self.nodes else nid
            self.nodes[nid]["parent"] = None
            self._resolve_initial_scope(nid)
        for pid in old_parents:
            if pid in self.nodes:
                self._refresh_node_actions(pid)
        for i, nid in enumerate(nids):
            root = self.nodes.get(anchors.get(nid))
            if not root:
                continue
            self._move_node_to(
                nid,
                root["x"] + root["w"] / 2 + self._u(110),
                root["y"] + (i - (len(nids) - 1) / 2) * self._u(90),
            )
        self._refresh_resize_handle()
        self._notify()
        return True

    def _remove_initial_marker(self, node_id):
        n = self.nodes[node_id]
        for item in n["marker_items"]:
            self.delete(item)
            if item in n["items"]:
                n["items"].remove(item)
        n["marker_items"] = []

    def _remove_final_marker(self, node_id):
        n = self.nodes[node_id]
        for item in n["final_marker_items"]:
            self.delete(item)
            if item in n["items"]:
                n["items"].remove(item)
        n["final_marker_items"] = []

    # ── 状态内部动作（UML 分区显示） ────────────────────────
    def _node_action_lines(self, n):
        """返回状态框内要显示的行：(文本, 是否为内部转移)"""
        lines = []
        if n.get("actions_on"):
            actions = n.get("actions") or {}
            for kind in self.STATE_ACTION_KINDS:
                text = " ".join((actions.get(kind) or "").split())
                if not text:
                    continue
                if len(text) > 22:
                    text = text[:21] + "…"
                lines.append((f"{kind} / {text}", False))

        # 内部转移独立于 entry/exit/do 开关，始终显示
        for item in n.get("internal") or []:
            event = (item.get("event") or "").strip()
            if not event:
                continue
            text = event
            guard = " ".join((item.get("guard") or "").split())
            if guard:
                text += f" [{guard}]"
            action = " ".join((item.get("action") or "").split())
            if action:
                text += f" / {action}"
            if len(text) > 24:
                text = text[:23] + "…"
            lines.append((text, True))
        return lines

    def _refresh_node_actions(self, nid, redraw_links=True):
        """按内部动作行数调整状态框高度并重排文字（UML 名称区 + 动作区）"""
        n = self.nodes.get(nid)
        if not n:
            return

        # 清掉旧的分隔线和动作文字
        if n.get("sep_id") is not None:
            self.delete(n["sep_id"])
            if n["sep_id"] in n["items"]:
                n["items"].remove(n["sep_id"])
            n["sep_id"] = None
        if n.get("sep2_id") is not None:
            self.delete(n["sep2_id"])
            if n["sep2_id"] in n["items"]:
                n["items"].remove(n["sep2_id"])
            n["sep2_id"] = None
        for item in n.get("action_items") or []:
            self.delete(item)
            if item in n["items"]:
                n["items"].remove(item)
        n["action_items"] = []

        lines = self._node_action_lines(n)
        # 复合状态：按子状态范围自动撑开外框
        if self.is_composite(nid):
            self._layout_composite(nid, lines)
            if nid == self._resize_nid:
                self._refresh_resize_handle()
            if n.get("parent") in self.nodes:
                self._refresh_node_actions(n["parent"], redraw_links=redraw_links)
            return

        h = (self._u(self.NODE_H) if not lines
             else self._u(42) + self._u(18) * len(lines))
        w = max(self._u(self.NODE_W), n.get("manual_w") or 0)
        h = max(h, n.get("manual_h") or 0)
        n["w"] = w
        n["h"] = h
        # 未手动拖动的标记，按新尺寸重新贴角
        if n.get("marker_auto", True) and n["marker_items"]:
            n["marker_offset"] = self._marker_default(n)
        if n.get("final_marker_auto", True) and n.get("final_marker_items"):
            n["final_marker_offset"] = self._marker_default(n, final=True)
        x0 = n["x"] - w / 2
        y0 = n["y"] - h / 2
        x1 = n["x"] + w / 2
        y1 = n["y"] + h / 2

        # 尺寸变化：重建状态框
        fill, outline, width = self._node_style(nid)
        old_rect = n["rect_id"]
        index = n["items"].index(old_rect)
        self.delete(old_rect)
        rect_id = self._round_rect(
            x0, y0, x1, y1, r=6, fill=fill, outline=outline, width=width,
        )
        n["rect_id"] = rect_id
        n["items"][index] = rect_id
        self.tag_lower(rect_id)

        self.itemconfigure(n["text_id"], anchor="center")
        if not lines:
            self.coords(n["text_id"], n["x"], n["y"])
        else:
            self.coords(n["text_id"], n["x"], y0 + self._u(18))
            n["sep_id"] = self.create_line(
                x0 + self._u(8), y0 + self._u(34),
                x1 - self._u(8), y0 + self._u(34),
                fill="#c9ced6", width=1,
            )
            n["items"].append(n["sep_id"])
            for i, (line, is_internal) in enumerate(lines):
                item = self._create_text(
                    x0 + self._u(8),
                    y0 + self._u(46) + self._u(18) * i,
                    line, size=8, anchor="w",
                    fill="#1a6bc5" if is_internal else "#555555",
                )
                n["action_items"].append(item)
                n["items"].append(item)

        if n["marker_items"]:
            self._layout_initial_marker(nid)
        if n.get("final_marker_items"):
            self._layout_final_marker(nid)

        if redraw_links:
            # 节点高度变化后，相连转移的端点需要重新计算
            for tid, t in self.transitions.items():
                if t["from"] == nid or t["to"] == nid:
                    self._update_transition_coords(tid)

        # 自身尺寸变化后，外层复合状态也要重新贴合
        if n.get("parent") in self.nodes:
            self._refresh_node_actions(
                n["parent"], redraw_links=redraw_links)
        if nid == self._resize_nid:
            self._refresh_resize_handle()

    # ── 圆角矩形（tk.Canvas 原生不支持 rx/ry，用多边形近似） ──
    def _round_rect(self, x0, y0, x1, y1, r=6, **kwargs):
        """用 create_polygon + smooth 画圆角矩形"""
        r = min(r, (x1 - x0) // 2, (y1 - y0) // 2)
        points = [
            x0 + r, y0,
            x1 - r, y0,
            x1, y0,          # 右上角圆弧起点
            x1, y0 + r,
            x1, y1 - r,
            x1, y1,          # 右下角圆弧起点
            x1 - r, y1,
            x0 + r, y1,
            x0, y1,          # 左下角圆弧起点
            x0, y1 - r,
            x0, y0 + r,
            x0, y0,          # 左上角圆弧起点
        ]
        return self.create_polygon(
            points, smooth=True, **kwargs,
        )

    # ── 转移箭头 ────────────────────────────────────────────
    def _add_transition(self, from_id, to_id, event="", style="line",
                        waypoints=None, auto_curve=True, guard="", action="",
                        guard_on=None, action_on=None, priority=None,
                        trigger="event"):
        seq = self._trans_seq
        tid = f"t{seq}"
        self._trans_seq += 1
        if priority is None:
            # 优先级只在同一状态内部排序：默认接在该状态已有最大值之后
            priority = 1 + max(
                (o.get("priority", 1) for o in self.transitions.values()
                 if o["from"] == from_id), default=0)
        self.transitions[tid] = {
            "from": from_id, "to": to_id, "event": event,
            "line_id": None, "label_id": None,
            "style": style if style in ("line", "curve") else "curve",
            "waypoints": [tuple(p) for p in (waypoints or [])],
            "guard": guard,
            "action": action,
            # 开关状态独立保存：留空时也保持开启
            "guard_on": bool(guard) if guard_on is None else bool(guard_on),
            "action_on": bool(action) if action_on is None else bool(action_on),
            # 优先级：同一状态内按画图顺序递增，不同状态互不影响
            "priority": int(priority),
            # 触发方式：外部事件 / 自动转移（无事件）
            "trigger": trigger if trigger in ("event", "auto") else "event",
        }
        self._draw_transition(tid)
        # 两个状态互相指向时自动改用曲线，避免两条直线重合
        # 恢复快照时关闭该行为，保持历史状态原样
        reverse = self._find_transition(to_id, from_id) if auto_curve else None
        if reverse:
            self.transitions[tid]["style"] = "curve"
            self.transitions[reverse]["style"] = "curve"
            self._redraw_transition(tid)
            self._redraw_transition(reverse)
        return tid

    @staticmethod
    def _curve_point_on_path(points):
        """取平滑曲线上的一个点作为标签位置

        Tk 的 smooth 曲线不经过中间顶点，而是经过相邻顶点的中点：
        - 三个点（起、折点、终）：二次贝塞尔 t=0.5 处为 (P0+2P1+P2)/4
        - 更多点：中间相邻两点的中点一定在曲线上
        """
        n = len(points)
        if n == 3:
            (x0, y0), (x1, y1), (x2, y2) = points
            return (x0 + 2 * x1 + x2) / 4, (y0 + 2 * y1 + y2) / 4
        i = max(0, (n - 1) // 2 - 1)
        return (
            (points[i][0] + points[i + 1][0]) / 2,
            (points[i][1] + points[i + 1][1]) / 2,
        )

    def _transition_geometry(self, tid):
        """返回 (线坐标, 标签坐标, 是否平滑)；只保留直线和曲线两种"""
        t = self.transitions[tid]
        fr, to = self.nodes[t["from"]], self.nodes[t["to"]]
        waypoints = [tuple(p) for p in t.get("waypoints", [])]
        style = t.get("style", "line")

        # 起点/终点朝向第一个/最后一个折点（没有折点就朝向对方节点）
        aim_start = waypoints[0] if waypoints else (to["x"], to["y"])
        aim_end = waypoints[-1] if waypoints else (fr["x"], fr["y"])
        start_x, start_y = self._node_edge_point(fr, *aim_start)
        end_x, end_y = self._node_edge_point(to, *aim_end)

        if style != "curve":
            return (
                (start_x, start_y, end_x, end_y),
                ((start_x + end_x) / 2,
                 (start_y + end_y) / 2 - self._u(14)),
                False,
            )

        # 曲线：经过所有折点的平滑曲线，标签贴着曲线本体
        if waypoints:
            pts = [(start_x, start_y)] + waypoints + [(end_x, end_y)]
            lx, ly = self._curve_point_on_path(pts)
            return (
                tuple(v for p in pts for v in p),
                (lx, ly - self._u(10)),
                True,
            )

        # 无折点的曲线：默认一侧弯曲
        dx, dy = end_x - start_x, end_y - start_y
        length = math.hypot(dx, dy) or 1.0
        amount = self._u(40)
        ctrl_x = (start_x + end_x) / 2 - dy / length * amount
        ctrl_y = (start_y + end_y) / 2 + dx / length * amount
        return (
            (start_x, start_y, ctrl_x, ctrl_y, end_x, end_y),
            ((start_x + 2 * ctrl_x + end_x) / 4,
             (start_y + 2 * ctrl_y + end_y) / 4 - self._u(12)),
            True,
        )

    @staticmethod
    def _label_text(t):
        """转移标签：[优先级] EVENT/(自动) [guard] / action"""
        if t.get("trigger") == "auto":
            text = f"[{t.get('priority', 1)}] (自动)"
        else:
            text = f"[{t.get('priority', 1)}] {t['event']}"
        # 多行内容在标签上压成一行显示
        guard = " ".join((t.get("guard") or "").split())
        if guard:
            text += f" [{guard}]"
        action = " ".join((t.get("action") or "").split())
        if action:
            text += f" / {action}"
        return text

    def _draw_transition(self, tid):
        """按当前节点位置重画一条转移（先删除旧元素）"""
        t = self.transitions[tid]
        if t["line_id"] is not None:
            self.delete(t["line_id"])
        if t["label_id"] is not None:
            self.delete(t["label_id"])
        if t.get("label_bg_id") is not None:
            self.delete(t["label_bg_id"])
            t["label_bg_id"] = None

        points, label_pos, smooth = self._transition_geometry(tid)
        selected = tid in self.selected_transes
        auto = t.get("trigger") == "auto"
        t["line_id"] = self.create_line(
            *points, smooth=smooth, splinesteps=24,
            fill=self.ARROW_SELECTED_COLOR if selected else self.ARROW_COLOR,
            width=2, arrow=tk.LAST, arrowshape=(14, 16, 4),
            dash=(5, 3) if auto else (),
        )
        t["label_id"] = self._create_text(
            label_pos[0], label_pos[1], self._label_text(t), size=9,
            fill=self.ARROW_SELECTED_COLOR if selected else self.LABEL_COLOR,
        )
        # 白底垫在文字下面，避免和连线混在一起
        bbox = self.bbox(t["label_id"])
        t["label_bg_id"] = self.create_rectangle(
            bbox[0] - self._u(4), bbox[1] - self._u(1),
            bbox[2] + self._u(4), bbox[3] + self._u(1),
            fill="#ffffff", outline="#c9ced6", width=1,
        )
        self.tag_raise(t["label_id"])
        self._place_label(tid)

    def _place_label(self, tid):
        """把标签放到「基础位置 + 手动偏移」，并同步白底尺寸"""
        t = self.transitions.get(tid)
        if not t or t.get("label_id") is None:
            return
        _points, base, _smooth = self._transition_geometry(tid)
        off = t.get("label_offset") or (0, 0)
        self.coords(t["label_id"], base[0] + off[0], base[1] + off[1])
        bbox = self.bbox(t["label_id"])
        if bbox and t.get("label_bg_id") is not None:
            self.coords(
                t["label_bg_id"],
                bbox[0] - self._u(4), bbox[1] - self._u(1),
                bbox[2] + self._u(4), bbox[3] + self._u(1),
            )
            self.tag_raise(t["label_bg_id"])
        self.tag_raise(t["label_id"])

    def _redraw_transition(self, tid):
        t = self.transitions.get(tid)
        if not t:
            return
        if t["line_id"] is not None:
            self.delete(t["line_id"])
            t["line_id"] = None
        if t["label_id"] is not None:
            self.delete(t["label_id"])
            t["label_id"] = None
        if t.get("label_bg_id") is not None:
            self.delete(t["label_bg_id"])
            t["label_bg_id"] = None
        self._draw_transition(tid)

    def _update_transition_coords(self, tid):
        """拖动节点时只改坐标，避免反复删建造成闪烁"""
        t = self.transitions[tid]
        points, _label_pos, _smooth = self._transition_geometry(tid)
        self.coords(t["line_id"], *points)
        self._place_label(tid)

    def _node_nearest_point(self, node, x, y):
        """状态框上离 (x, y) 最近的点（外侧为边或角）"""
        hw = node.get("w", self.NODE_W) / 2
        hh = node.get("h", self.NODE_H) / 2
        nx = min(max(x, node["x"] - hw), node["x"] + hw)
        ny = min(max(y, node["y"] - hh), node["y"] + hh)
        return nx, ny

    def _node_edge_point(self, node, tx, ty):
        """给定一个节点和外部一点，返回节点边缘上的交点"""
        cx, cy = node["x"], node["y"]
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0:
            return cx, cy

        hw = node.get("w", self.NODE_W) / 2
        hh = node.get("h", self.NODE_H) / 2
        scale = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return cx + dx * scale, cy + dy * scale

    # ── 命中测试 ────────────────────────────────────────────
    def _hit_test(self, x, y):
        """返回 ("node", node_id) / ("trans", trans_id) / (None, None)"""
        items = self.find_overlapping(x - 4, y - 4, x + 4, y + 4)
        for item in reversed(items):
            for nid, n in self.nodes.items():
                if item in n["items"]:
                    return "node", nid
            for tid, t in self.transitions.items():
                if item in (t["line_id"], t["label_id"]):
                    return "trans", tid
        return None, None

    # ── 连接模式（按住 Ctrl） ───────────────────────────────
    def _on_ctrl_press(self, _event):
        if not self._is_active():
            return
        # 延迟 220ms 再显示提示：Ctrl+C/V/A/D 等组合键不会闪出提示条
        if self.link_mode or self._hint_after is not None:
            return
        self._hint_after = self.after(220, self._show_hint_delayed)

    def _show_hint_delayed(self):
        self._hint_after = None
        self._enter_link_mode()

    def _on_ctrl_release(self, _event):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        self._exit_link_mode()

    def _cancel_hint_timer(self):
        if self._hint_after is not None:
            self.after_cancel(self._hint_after)
            self._hint_after = None

    def _enter_link_mode(self):
        self._cancel_hint_timer()
        if self.link_mode:
            return
        self.link_mode = True
        self.link_source = None
        self._drag = None
        self._show_hint()

    def _exit_link_mode(self):
        if not self.link_mode:
            return
        self.link_mode = False
        self._clear_link_source()
        self._hide_hint()

    def _handle_link_click(self, nid):
        """连接模式下的点击：第一次选起点，之后每次点击都与起点连线"""
        if self.link_source is None:
            self.link_source = nid
            self._paint_link_source()
            return
        if nid == self.link_source:
            # 再点起点：取消起点选择
            self._clear_link_source()
            return

        existing = self._find_transition(self.link_source, nid)
        if existing:
            self._select_trans(existing)
            return

        self._push_undo()
        tid = self._add_transition(self.link_source, nid, self._next_event_name())
        self._select_trans(tid)
        self._notify()

    def _paint_link_source(self):
        if self.link_source:
            self._apply_node_style(self.link_source)

    def _clear_link_source(self):
        nid = self.link_source
        self.link_source = None
        if nid:
            self._apply_node_style(nid)

    # ── 连接模式提示条 ──────────────────────────────────────
    def _show_hint(self):
        self._hide_hint()
        width = max(self.winfo_width(), 320)
        txt = self.create_text(
            width // 2, 26,
            text="连接模式：先点一个状态作为起点，再点其他状态即可连线（松开 Ctrl 退出）",
            fill="#a15c00",
            font=("Segoe UI", 10, "bold"),
        )
        bbox = self.bbox(txt)
        rect = self.create_rectangle(
            bbox[0] - 14, bbox[1] - 7, bbox[2] + 14, bbox[3] + 7,
            fill="#fff4e0", outline=self.LINK_SOURCE_OUTLINE, width=1,
        )
        self.tag_raise(txt)
        self._hint_items = [rect, txt]

    def _hide_hint(self):
        for item in self._hint_items:
            self.delete(item)
        self._hint_items = []

    def _find_transition(self, from_id, to_id):
        for tid, t in self.transitions.items():
            if t["from"] == from_id and t["to"] == to_id:
                return tid
        return None

    def _next_event_name(self):
        i = len(self.transitions) + 1
        while any(t["event"] == f"EVENT_{i}" for t in self.transitions.values()):
            i += 1
        return f"EVENT_{i}"

    # ── 选中 ────────────────────────────────────────────────
    def _node_style(self, nid):
        """节点配色，优先级：连接起点 > 多选 > 初始状态 > 普通"""
        n = self.nodes[nid]
        if nid == self.link_source:
            return self.LINK_SOURCE_FILL, self.LINK_SOURCE_OUTLINE, 3
        if nid in self.selected_nodes:
            return self.NODE_SELECTED_FILL, self.NODE_SELECTED_OUTLINE, 3
        if n["is_initial"]:
            return self.INIT_FILL, self.INIT_OUTLINE, 3
        if self.is_composite(nid):
            return self.COMPOSITE_FILL, self.COMPOSITE_OUTLINE, 2
        return self.NODE_FILL, self.NODE_OUTLINE, 2

    def _apply_node_style(self, nid):
        """统一刷新节点配色"""
        n = self.nodes.get(nid)
        if not n:
            return
        fill, outline, width = self._node_style(nid)
        self.itemconfigure(n["rect_id"], fill=fill, outline=outline, width=width)

    def _refresh_node_styles(self):
        for nid in self.nodes:
            self._apply_node_style(nid)

    def _refresh_trans_styles(self):
        """按选中集合刷新所有转移的颜色"""
        for tid, t in self.transitions.items():
            if tid in self.selected_transes:
                line_color = label_color = self.ARROW_SELECTED_COLOR
            else:
                line_color, label_color = self.ARROW_COLOR, self.LABEL_COLOR
            self.itemconfigure(t["line_id"], fill=line_color)
            self.itemconfigure(t["label_id"], fill=label_color)

    def _clear_trans_selection(self):
        """只清掉转移的选中态（选中节点时用）"""
        if not self.selected_transes:
            return
        self.selected_transes.clear()
        self.selected_trans = None
        self._refresh_trans_styles()
        self._refresh_handles()

    def _select_node(self, nid, additive=False):
        self._clear_trans_selection()
        if additive:
            if nid in self.selected_nodes:
                self.selected_nodes.discard(nid)
            else:
                self.selected_nodes.add(nid)
            self._apply_node_style(nid)
            self._refresh_resize_handle()
            self._notify_selection()
            return
        if self.selected_nodes == {nid}:
            return
        self.selected_nodes = {nid}
        self._refresh_node_styles()
        self._refresh_resize_handle()
        self._notify_selection()

    def _select_trans(self, tid, additive=False):
        """选中转移；additive=True 为 Shift 多选，再次点击可取消"""
        if tid not in self.transitions:
            return
        if additive:
            if self.selected_nodes:
                self.selected_nodes = set()
                self._refresh_node_styles()
            if tid in self.selected_transes:
                self.selected_transes.discard(tid)
                if self.selected_trans == tid:
                    self.selected_trans = next(iter(self.selected_transes), None)
            else:
                self.selected_transes.add(tid)
                self.selected_trans = tid
            self._refresh_trans_styles()
            self._refresh_handles()
            self._refresh_resize_handle()
            self._notify_selection()
            return
        if self.selected_transes == {tid} and not self.selected_nodes:
            return
        self._clear_selection(notify=False)
        self.selected_transes = {tid}
        self.selected_trans = tid
        self._refresh_trans_styles()
        self._refresh_handles()
        self._refresh_resize_handle()
        self._notify_selection()

    def _clear_selection(self, notify=True):
        if self.selected_nodes:
            self.selected_nodes = set()
            self._refresh_node_styles()
        if self.selected_transes:
            self.selected_transes.clear()
            self.selected_trans = None
            self._refresh_trans_styles()
        self._refresh_handles()
        self._refresh_resize_handle()
        if notify:
            self._notify_selection()

    def _notify_selection(self):
        if self.on_select:
            self.on_select()

    # ── 鼠标事件 ────────────────────────────────────────────
    def _on_click(self, event):
        self.focus_set()
        # 以点击事件里的 Ctrl 状态为准，避免漏掉 KeyRelease 后卡在连接模式
        ctrl_down = bool(event.state & 0x0004)
        if ctrl_down:
            self._enter_link_mode()
        elif self.link_mode:
            self._exit_link_mode()

        kind, ident = self._hit_test(event.x, event.y)

        if self.link_mode:
            if kind == "node":
                self._handle_link_click(ident)
            return

        shift_down = bool(event.state & 0x0001)

        # 右下角缩放手柄优先于节点本体
        resize_id = self._hit_resize(event.x, event.y)
        if resize_id is not None:
            self._select_node(resize_id)
            self._drag = None
            self._rubber = None
            self._marker_drag = None
            self._line_drag = None
            self._label_drag = None
            self._resize_drag = {
                "id": resize_id, "x": event.x, "y": event.y,
                "w": self.nodes[resize_id]["w"],
                "h": self.nodes[resize_id]["h"],
            }
            return

        # 初始/最终标记优先于节点本体：按住它可以绕着状态拖动
        marker_node, marker_kind = self._hit_marker(event.x, event.y)
        if marker_node is not None:
            self._select_node(marker_node)
            self._drag = None
            self._rubber = None
            self._marker_drag = {
                "id": marker_node, "kind": marker_kind, "pushed": False,
            }
            return

        # 折点手柄：按住可移动已有拐点
        wp_tid, wp_idx = self._hit_waypoint(event.x, event.y)
        if wp_tid is not None:
            self._line_drag = {
                "tid": wp_tid, "pushed": False, "wp_index": wp_idx,
                "x": event.x, "y": event.y,
            }
            return

        # 事件标签：按住可拖动位置
        label_tid = self._hit_label(event.x, event.y)
        if label_tid is not None:
            if shift_down:
                self._select_trans(label_tid, additive=True)
                self._drag = None
                self._line_drag = None
                return
            if (label_tid in self.selected_transes
                    and len(self.selected_transes) > 1):
                # 已选中多条：拖动任意一条（含标签）都整体移动
                self._drag = None
                self._label_drag = None
                self._line_drag = {
                    "group": list(self.selected_transes),
                    "pushed": False, "x": event.x, "y": event.y,
                }
                return
            self._select_trans(label_tid)
            lt = self.transitions[label_tid]
            self._label_drag = {
                "tid": label_tid, "pushed": False,
                "px": event.x, "py": event.y,
                "off": list(lt.get("label_offset") or (0, 0)),
            }
            self._drag = None
            self._line_drag = None
            return

        if kind == "node":
            n = self.nodes[ident]
            # 复合状态内部空白：单击选中父状态，拖动则框选内部状态
            if (self.is_composite(ident) and not shift_down
                    and event.y > n["y"] - n["h"] / 2
                    + self._u(self.COMPOSITE_HEADER)):
                if ident not in self.selected_nodes or len(self.selected_nodes) > 1:
                    self._select_node(ident)
                self._drag = None
                self._line_drag = None
                self._label_drag = None
                self._rubber = {
                    "x0": event.x, "y0": event.y, "rect_id": None,
                }
                return
            drag_start = {
                "id": ident, "dx": event.x - n["x"], "dy": event.y - n["y"],
            }
            if shift_down:
                self._select_node(ident, additive=True)
                self._drag = None
            elif ident in self.selected_nodes and len(self.selected_nodes) > 1:
                # 已有多选：保持整组，直接拖动
                self._drag = drag_start
            else:
                self._select_node(ident)
                self._drag = drag_start
        elif kind == "trans":
            if shift_down:
                self._select_trans(ident, additive=True)
                self._drag = None
                self._line_drag = None
            elif ident in self.selected_transes and len(self.selected_transes) > 1:
                # 已选中多条转移：一起拖动折点
                self._drag = None
                self._label_drag = None
                self._line_drag = {
                    "group": list(self.selected_transes),
                    "pushed": False, "x": event.x, "y": event.y,
                }
            else:
                self._select_trans(ident)
                self._drag = None
                self._line_drag = {
                    "tid": ident, "pushed": False, "wp_index": None,
                    "x": event.x, "y": event.y,
                }
        else:
            self._clear_selection()
            self._drag = None
            # 空白处按下：可能是点击取消选择，也可能是框选起点
            self._rubber = {"x0": event.x, "y0": event.y, "rect_id": None}

    def _on_drag(self, event):
        if self.link_mode:
            return
        if self._resize_drag is not None:
            rd = self._resize_drag
            n = self.nodes.get(rd["id"])
            if not n:
                self._resize_drag = None
                return
            if not rd.get("pushed"):
                self._push_undo()
                rd["pushed"] = True
            # 中心保持不动，右下角跟随鼠标
            n["manual_w"] = max(
                self._u(self.MIN_NODE_W), rd["w"] + 2 * (event.x - rd["x"]))
            n["manual_h"] = max(
                self._u(self.MIN_NODE_H), rd["h"] + 2 * (event.y - rd["y"]))
            self._refresh_node_actions(rd["id"])
            self._refresh_resize_handle()
            return
        if self._marker_drag is not None:
            if not self._marker_drag["pushed"]:
                self._push_undo()
                self._marker_drag["pushed"] = True
            move = (self._move_final_marker
                    if self._marker_drag.get("kind") == "final"
                    else self._move_initial_marker)
            move(self._marker_drag["id"], event.x, event.y, record=False)
            return
        if self._label_drag is not None:
            self._drag_label(event.x, event.y)
            return
        if self._rubber is not None:
            self._update_rubber(event.x, event.y)
            return
        if self._line_drag is not None:
            self._drag_line(event.x, event.y)
            return
        if not self._drag:
            return
        nid = self._drag["id"]
        n = self.nodes[nid]
        nx = event.x - self._drag["dx"]
        ny = event.y - self._drag["dy"]
        dx, dy = nx - n["x"], ny - n["y"]
        if dx == 0 and dy == 0:
            return
        if not self._drag.get("pushed"):
            self._push_undo()
            self._drag["pushed"] = True
        self._drag["moved"] = True
        # 多选时整组一起移动；复合状态要带着所有后代一起走
        targets = set(self.selected_nodes) if self.selected_nodes else {nid}
        moving = set()
        for target in targets:
            moving.add(target)
            moving.update(self._descendants(target))
        for target in moving:
            node = self.nodes[target]
            for item in node["items"]:
                self.move(item, dx, dy)
            node["x"] += dx
            node["y"] += dy
        for tid, t in self.transitions.items():
            if t["from"] in moving or t["to"] in moving:
                self._update_transition_coords(tid)
        if self._resize_item is not None:
            self._refresh_resize_handle()

    def _on_release(self, _event):
        if self.link_mode:
            self._drag = None
            return
        if self._resize_drag is not None:
            self._resize_drag = None
            self._refresh_resize_handle()
            self._notify()
            return
        if self._marker_drag is not None:
            self._marker_drag = None
            self._notify()
            return
        if self._label_drag is not None:
            self._label_drag = None
            self._notify()
            return
        if self._rubber is not None:
            self._finish_rubber()
            return
        if self._line_drag is not None:
            self._line_drag = None
            self._notify()
            return
        if self._drag:
            dragged = self._drag["id"]
            moved = bool(self._drag.get("moved"))
            self._drag = None
            # 真正移动过才重新判断包含关系，单纯点击不改变层级
            if moved:
                self._refresh_containment(dragged)
            self._notify()

    # ── 拖动连线调整路线（折点模型） ────────────────────────
    def _drag_line(self, x, y):
        """第一次拖动在鼠标处插入折点，之后拖动折点本身"""
        if self._line_drag.get("group"):
            self._drag_line_group(x, y)
            return
        tid = self._line_drag["tid"]
        t = self.transitions.get(tid)
        if not t:
            return
        if not self._line_drag["pushed"]:
            if self._line_drag["wp_index"] is None:
                px, py = self._line_drag["x"], self._line_drag["y"]
                if abs(x - px) < 4 and abs(y - py) < 4:
                    return
            self._push_undo()
            self._line_drag["pushed"] = True

        if self._line_drag["wp_index"] is None:
            idx = self._insert_waypoint_index(t, x, y)
            t["waypoints"].insert(idx, (x, y))
            self._line_drag["wp_index"] = idx
            t["style"] = "curve"
        else:
            t["waypoints"][self._line_drag["wp_index"]] = (x, y)

        self._redraw_transition(tid)
        self._refresh_handles()

    def _drag_line_group(self, x, y):
        """多选转移整体拖动：所选线的折点一起平移"""
        d = self._line_drag
        dx, dy = x - d["x"], y - d["y"]
        if not d["pushed"]:
            if abs(dx) < 4 and abs(dy) < 4:
                return
            self._push_undo()
            d["pushed"] = True
            d["orig"] = {}
            for tid in d["group"]:
                t = self.transitions.get(tid)
                if not t:
                    continue
                pts = [tuple(p) for p in t["waypoints"]]
                if not pts:
                    # 没有折点的线：在自己的线身上取最近点，使其能整体弯折
                    pts = [self._closest_point_on_transition(
                        tid, d["x"], d["y"])]
                    t["style"] = "curve"
                d["orig"][tid] = pts
        for tid, pts in d.get("orig", {}).items():
            t = self.transitions.get(tid)
            if not t:
                continue
            t["waypoints"] = [(px + dx, py + dy) for px, py in pts]
            self._redraw_transition(tid)
        self._refresh_handles()

    def _closest_point_on_transition(self, tid, x, y):
        """返回转移折线（控制多边形）上离 (x, y) 最近的点"""
        points, _label, _smooth = self._transition_geometry(tid)
        pts = list(zip(points[0::2], points[1::2]))
        best, best_d = pts[0], float("inf")
        for a, b in zip(pts, pts[1:]):
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                p = a
            else:
                t = ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)
                t = max(0.0, min(1.0, t))
                p = (ax + dx * t, ay + dy * t)
            dist = math.hypot(x - p[0], y - p[1])
            if dist < best_d:
                best, best_d = p, dist
        return best

    def _drag_label(self, x, y):
        """拖动事件标签：按位移更新手动偏移，限制在连线附近"""
        d = self._label_drag
        dx, dy = x - d["px"], y - d["py"]
        if not d["pushed"]:
            if abs(dx) < 3 and abs(dy) < 3:
                return
            self._push_undo()
            d["pushed"] = True
        t = self.transitions.get(d["tid"])
        if not t:
            return

        off_x = d["off"][0] + dx
        off_y = d["off"][1] + dy
        # 范围限制：标签不能离基础位置太远
        limit = 100.0
        length = math.hypot(off_x, off_y)
        if length > limit:
            off_x = off_x / length * limit
            off_y = off_y / length * limit

        t["label_offset"] = [off_x, off_y]
        self._place_label(d["tid"])

    def _insert_waypoint_index(self, t, x, y):
        """找出鼠标最近的一段，把新折点插到这一段之后"""
        fr, to = self.nodes[t["from"]], self.nodes[t["to"]]
        pts = [(fr["x"], fr["y"])]
        pts += [tuple(p) for p in t["waypoints"]]
        pts.append((to["x"], to["y"]))
        best_i, best_d = 0, float("inf")
        for i in range(len(pts) - 1):
            d = self._point_segment_distance(x, y, pts[i], pts[i + 1])
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    @staticmethod
    def _point_segment_distance(px, py, a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return math.hypot(px - (ax + dx * t), py - (ay + dy * t))

    # ── 折点手柄 ────────────────────────────────────────────
    def _refresh_handles(self):
        for item in self._handle_items:
            self.delete(item)
        self._handle_items = []
        # 多选时不显示折点手柄，避免视觉干扰
        t = (self.transitions.get(self.selected_trans)
             if len(self.selected_transes) == 1 else None)
        if not t:
            return
        for wx, wy in t["waypoints"]:
            item = self.create_oval(
                wx - 4, wy - 4, wx + 4, wy + 4,
                fill="#ffffff", outline=self.ARROW_SELECTED_COLOR, width=2,
            )
            self.tag_raise(item)
            self._handle_items.append(item)

    def _hit_waypoint(self, x, y):
        if len(self.selected_transes) != 1:
            return None, None
        t = self.transitions.get(self.selected_trans)
        if not t:
            return None, None
        for i, (wx, wy) in enumerate(t["waypoints"]):
            if abs(wx - x) <= 7 and abs(wy - y) <= 7:
                return self.selected_trans, i
        return None, None

    def _hit_label(self, x, y):
        """命中任意转移的事件标签（含白底范围）"""
        for tid, t in self.transitions.items():
            bg = t.get("label_bg_id")
            if bg is None:
                continue
            x0, y0, x1, y1 = self.coords(bg)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return tid
        return None

    def _delete_waypoint(self, tid, idx):
        """删除指定折点"""
        t = self.transitions.get(tid)
        if not t or idx < 0 or idx >= len(t["waypoints"]):
            return
        self._push_undo()
        t["waypoints"].pop(idx)
        self._redraw_transition(tid)
        self._refresh_handles()
        self._notify()

    # ── 框选 ────────────────────────────────────────────────
    def _update_rubber(self, x, y):
        r = self._rubber
        if r["rect_id"] is None:
            if abs(x - r["x0"]) < 4 and abs(y - r["y0"]) < 4:
                return
            r["rect_id"] = self.create_rectangle(
                r["x0"], r["y0"], x, y,
                outline=self.NODE_SELECTED_OUTLINE, dash=(4, 3), width=1,
            )
        else:
            self.coords(r["rect_id"], r["x0"], r["y0"], x, y)

    def _finish_rubber(self):
        r = self._rubber
        self._rubber = None
        if not r or r["rect_id"] is None:
            return

        x0, y0, x1, y1 = self.coords(r["rect_id"])
        self.delete(r["rect_id"])
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))

        hit = {
            nid for nid, n in self.nodes.items()
            if x0 <= n["x"] - n.get("w", self.NODE_W) / 2
            and n["x"] + n.get("w", self.NODE_W) / 2 <= x1
            and y0 <= n["y"] - n.get("h", self.NODE_H) / 2
            and n["y"] + n.get("h", self.NODE_H) / 2 <= y1
        }
        if hit:
            self.selected_nodes = hit
            self._refresh_node_styles()
            self._refresh_resize_handle()
            self._notify_selection()

    def _on_double_click(self, event):
        if self.link_mode:
            return
        self._drag = None
        self._line_drag = None
        self._label_drag = None

        # 双击折点：删除该折点
        wp_tid, wp_idx = self._hit_waypoint(event.x, event.y)
        if wp_tid is not None:
            self._delete_waypoint(wp_tid, wp_idx)
            return

        kind, ident = self._hit_test(event.x, event.y)
        if kind == "node":
            self._rename_node(ident)
        elif kind == "trans":
            self._edit_event(ident)

    def _on_delete_key(self, _event):
        if self.selected_nodes:
            self._push_undo()
            for nid in list(self.selected_nodes):
                self._delete_node(nid, record=False)
            return "break"
        if self.selected_transes:
            self._push_undo()
            for tid in list(self.selected_transes):
                self._delete_transition(tid, notify=False, record=False)
            self._notify()
            return "break"

    # ── 常用快捷键 ──────────────────────────────────────────
    def _on_select_all(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        if self.nodes:
            self._clear_trans_selection()
            self.selected_nodes = set(self.nodes)
            self._refresh_node_styles()
            self._refresh_resize_handle()
            self._notify_selection()
        return "break"

    def _on_copy(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        if not self.selected_nodes:
            return "break"
        ids = list(self.selected_nodes)
        nodes = [
            {
                "name": self.nodes[nid]["name"],
                "x": self.nodes[nid]["x"], "y": self.nodes[nid]["y"],
                "actions": dict(self.nodes[nid].get("actions") or {}),
                "actions_on": bool(self.nodes[nid].get("actions_on")),
                "internal": [
                    dict(item) for item in
                    (self.nodes[nid].get("internal") or [])
                ],
                # 一起复制的父状态，粘贴时重新映射；未复制则置为顶层
                "parent": self.nodes[nid].get("parent"),
                "manual_w": self.nodes[nid].get("manual_w"),
                "manual_h": self.nodes[nid].get("manual_h"),
            }
            for nid in ids
        ]
        trans = [
            {
                "from": t["from"], "to": t["to"], "event": t["event"],
                "guard": t.get("guard", ""),
                "action": t.get("action", ""),
                "guard_on": bool(t.get("guard_on")),
                "action_on": bool(t.get("action_on")),
                "trigger": t.get("trigger", "event"),
            }
            for t in self.transitions.values()
            if t["from"] in self.selected_nodes and t["to"] in self.selected_nodes
        ]
        self._clipboard = {"ids": ids, "nodes": nodes, "trans": trans}
        self._paste_seq = 0
        return "break"

    def _on_paste(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        if not self._clipboard:
            return "break"
        self._push_undo()
        offset = 30 * (self._paste_seq + 1)
        self._paste_seq += 1

        id_map = {}
        for old_id, data in zip(self._clipboard["ids"], self._clipboard["nodes"]):
            nid = self._add_node(
                self._unique_name(data["name"]),
                data["x"] + offset, data["y"] + offset,
                actions=data.get("actions"),
                actions_on=data.get("actions_on"),
                internal=data.get("internal"),
            )
            id_map[old_id] = nid
        # 只在父子都被一起复制时恢复包含关系
        for old_id, data in zip(self._clipboard["ids"], self._clipboard["nodes"]):
            node = self.nodes[id_map[old_id]]
            node["manual_w"] = data.get("manual_w")
            node["manual_h"] = data.get("manual_h")
            pid = data.get("parent")
            if pid in id_map:
                node["parent"] = id_map[pid]
        for nid in id_map.values():
            self._refresh_node_actions(nid, redraw_links=False)
        for t in self._clipboard["trans"]:
            self._add_transition(
                id_map[t["from"]], id_map[t["to"]], t["event"],
                guard=t.get("guard", ""),
                action=t.get("action", ""),
                guard_on=t.get("guard_on"),
                action_on=t.get("action_on"),
                trigger=t.get("trigger", "event"),
            )

        self.selected_nodes = set(id_map.values())
        self._refresh_node_styles()
        self._notify()
        return "break"

    def _on_duplicate(self, _event=None):
        self._on_copy()
        self._on_paste()
        return "break"

    # ── 撤销 / 重做 ─────────────────────────────────────────
    def _snapshot(self):
        """把当前画布数据序列化成可恢复的快照"""
        return {
            "zoom": self.zoom,
            "nodes": [
                {
                    "id": nid, "name": n["name"],
                    "x": n["x"], "y": n["y"],
                    "is_initial": n["is_initial"],
                    "is_final": bool(n.get("is_final")),
                    "parent": n.get("parent"),
                    "manual_w": n.get("manual_w"),
                    "manual_h": n.get("manual_h"),
                    "actions": dict(n.get("actions") or {}),
                    "actions_on": bool(n.get("actions_on")),
                    "internal": [
                        dict(item) for item in (n.get("internal") or [])
                    ],
                    "marker_offset": list(
                        n.get("marker_offset") or self.DEFAULT_MARKER_OFFSET
                    ),
                    "final_marker_offset": list(
                        n.get("final_marker_offset")
                        or self.DEFAULT_FINAL_MARKER_OFFSET
                    ),
                    "marker_auto": bool(n.get("marker_auto", True)),
                    "final_marker_auto": bool(n.get("final_marker_auto", True)),
                }
                for nid, n in self.nodes.items()
            ],
            "trans": [
                {
                    "from": t["from"], "to": t["to"], "event": t["event"],
                    "style": t.get("style", "line"),
                    "waypoints": [tuple(p) for p in t.get("waypoints", [])],
                    "label_offset": list(t.get("label_offset") or (0, 0)),
                    "guard": t.get("guard", ""),
                    "action": t.get("action", ""),
                    "guard_on": bool(t.get("guard_on")),
                    "action_on": bool(t.get("action_on")),
                    "priority": t.get("priority", 1),
                    "trigger": t.get("trigger", "event"),
                }
                for t in self.transitions.values()
            ],
        }

    def push_undo(self):
        """供外部在编辑会话开始时记录一次撤销点"""
        self._push_undo()

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore(self, snap):
        keep_nodes = set(self.selected_nodes)
        keep_trans = set(self.selected_transes)

        self.delete("all")
        self._text_base.clear()
        self.zoom = snap.get("zoom", 1.0)
        self.nodes.clear()
        self.transitions.clear()
        self.selected_nodes = set()
        self.selected_transes = set()
        self.selected_trans = None
        self._drag = None
        self._rubber = None
        self._marker_drag = None
        self._line_drag = None
        self._label_drag = None
        self._resize_drag = None
        self._resize_item = None
        self._resize_nid = None
        self._handle_items = []
        self._cancel_hint_timer()
        self._hide_hint()
        self.link_mode = False
        self.link_source = None
        self._node_seq = 0
        self._trans_seq = 0

        for data in snap["nodes"]:
            self._add_node(
                data["name"], data["x"], data["y"], data["is_initial"],
                node_id=data["id"], actions=data.get("actions"),
                actions_on=data.get("actions_on"),
                internal=data.get("internal"),
                is_final=data.get("is_final", False),
                final_marker_offset=data.get("final_marker_offset"),
            )
            node = self.nodes[data["id"]]
            node["manual_w"] = data.get("manual_w")
            node["manual_h"] = data.get("manual_h")
            node["marker_auto"] = data.get("marker_auto", True)
            node["final_marker_auto"] = data.get("final_marker_auto", True)
            if data.get("marker_offset"):
                node["marker_offset"] = list(data["marker_offset"])
                self._layout_initial_marker(data["id"])
            if data.get("final_marker_offset"):
                node["final_marker_offset"] = list(
                    data["final_marker_offset"])
                self._layout_final_marker(data["id"])
        # 先恢复包含关系，再由内向外重新贴合复合状态外框
        for data in snap["nodes"]:
            pid = data.get("parent")
            if pid in self.nodes:
                self.nodes[data["id"]]["parent"] = pid
        for data in sorted(
            snap["nodes"], key=lambda d: self._node_depth(d["id"]),
            reverse=True,
        ):
            self._refresh_node_actions(data["id"], redraw_links=False)
        for t in snap["trans"]:
            if t["from"] in self.nodes and t["to"] in self.nodes:
                tid = self._add_transition(
                    t["from"], t["to"], t["event"],
                    style=t.get("style", "line"),
                    waypoints=t.get("waypoints", []),
                    auto_curve=False,
                    guard=t.get("guard", ""),
                    action=t.get("action", ""),
                    guard_on=t.get("guard_on"),
                    action_on=t.get("action_on"),
                    priority=t.get("priority"),
                    trigger=t.get("trigger", "event"),
                )
                off = t.get("label_offset")
                if off and (off[0] or off[1]):
                    self.transitions[tid]["label_offset"] = list(off)
                    self._place_label(tid)

        # 尽量保留撤销前的选中对象
        self.selected_nodes = {nid for nid in keep_nodes if nid in self.nodes}
        if keep_trans:
            self.selected_transes = {
                tid for tid in keep_trans if tid in self.transitions}
            self.selected_trans = next(iter(self.selected_transes), None)
            self._refresh_trans_styles()
        self._refresh_node_styles()
        self._refresh_handles()
        self._refresh_resize_handle()
        self._notify_selection()

    def _on_undo(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        if not self._undo_stack:
            return "break"
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self._notify()
        return "break"

    def _on_redo(self, _event=None):
        if not self._is_active():
            return
        self._cancel_hint_timer()
        if not self._redo_stack:
            return "break"
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self._notify()
        return "break"

    def _unique_name(self, base):
        if not self._name_taken(f"{base}_COPY"):
            return f"{base}_COPY"
        i = 2
        while self._name_taken(f"{base}_COPY{i}"):
            i += 1
        return f"{base}_COPY{i}"

    # ── 右键菜单 ────────────────────────────────────────────
    def _on_right_click(self, event):
        self.focus_set()

        # 右键折点手柄：删除折点
        wp_tid, wp_idx = self._hit_waypoint(event.x, event.y)
        if wp_tid is not None:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(
                label="删除折点",
                command=lambda: self._delete_waypoint(wp_tid, wp_idx),
            )
            menu.tk_popup(event.x_root, event.y_root)
            return

        kind, ident = self._hit_test(event.x, event.y)
        menu = tk.Menu(self, tearoff=0)
        if kind == "node":
            selection = set(self.selected_nodes)
            # 已有多个状态被选中时右键别处：保留多选，直接合成新的大状态框
            if ident not in selection and len(selection) >= 2:
                menu.add_command(
                    label=f"把选中的 {len(selection)} 个状态合成大状态框",
                    command=self.wrap_selected,
                )
                menu.add_separator()
                menu.add_command(
                    label="取消选择", command=self._clear_selection)
                menu.tk_popup(event.x_root, event.y_root)
                return

            if ident not in selection:
                self._select_node(ident)
            count = len(self.selected_nodes)
            if count == 1:
                menu.add_command(
                    label="重命名", command=lambda: self._rename_node(ident),
                )
            menu.add_command(
                label="设为初始状态", command=lambda: self._set_initial(ident),
            )
            if self.nodes[ident].get("is_final"):
                menu.add_command(
                    label="取消最终状态",
                    command=lambda: self.set_final_state(ident, False),
                )
            else:
                menu.add_command(
                    label="设为最终状态",
                    command=lambda: self._set_final(ident),
                )
            if any(self.nodes[nid].get("parent")
                   for nid in self.selected_nodes if nid in self.nodes):
                label = ("移出父状态" if count == 1
                         else f"把选中的 {count} 个状态移出父状态")
                menu.add_command(
                    label=label, command=self.remove_selected_from_parent,
                )
            if self.is_composite(ident):
                menu.add_command(
                    label="全选内部状态",
                    command=lambda: self.select_children(ident),
                )
            # 用选中的状态新建一个大状态框
            menu.add_command(
                label=("新建大状态框" if count == 1
                       else f"把选中的 {count} 个状态合成大状态框"),
                command=self.wrap_selected,
            )
            menu.add_separator()
            if count > 1:
                menu.add_command(
                    label=f"删除选中的 {count} 个状态",
                    command=self._delete_selected_nodes,
                )
            else:
                menu.add_command(
                    label="删除状态", command=lambda: self._delete_node(ident),
                )
        elif kind == "trans":
            self._select_trans(ident)
            menu.add_command(label="编辑事件名", command=lambda: self._edit_event(ident))
            menu.add_separator()
            menu.add_command(
                label="直线", command=lambda: self._set_trans_style(ident, "line"),
            )
            menu.add_command(
                label="曲线", command=lambda: self._set_trans_style(ident, "curve"),
            )
            menu.add_separator()
            menu.add_command(
                label="删除转移", command=lambda: self._delete_transition(ident),
            )
        else:
            # 空白处右键：可用当前多选新建大状态框，或新建状态
            if len(self.selected_nodes) >= 2:
                menu.add_command(
                    label=(f"把选中的 {len(self.selected_nodes)} 个状态"
                           "合成大状态框"),
                    command=self.wrap_selected,
                )
                menu.add_separator()
            menu.add_command(
                label="新建状态",
                command=lambda: self._create_node_at(event.x, event.y),
            )
        menu.tk_popup(event.x_root, event.y_root)

    def _create_node_at(self, x, y):
        name = simpledialog.askstring(
            "新建状态", "状态名：",
            initialvalue=f"STATE_{len(self.nodes) + 1}", parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        if self._name_taken(name):
            messagebox.showerror("重名", f"已存在状态「{name}」", parent=self)
            return
        self.add_state_at(x, y, name=name)

    def _delete_selected_nodes(self):
        self._push_undo()
        for nid in list(self.selected_nodes):
            self._delete_node(nid, record=False)

    # ── 编辑操作 ────────────────────────────────────────────
    def add_state_at(self, x, y, name=None):
        """在画布坐标 (x, y) 新建一个状态（供左侧组件栏拖放调用）"""
        self._push_undo()
        if name is None:
            name = self._next_state_name()
        nid = self._add_node(name, x, y)
        # 拖到已有状态内部松手，直接成为它的子状态
        parent = self._containment_target(nid, x, y)
        if parent:
            self.nodes[nid]["parent"] = parent
            self._refresh_node_actions(parent)
        self._select_node(nid)
        self._notify()
        return nid

    def set_initial_at(self, x, y):
        """把 (x, y) 处的状态设为初始状态（供绿色圆组件拖放调用）"""
        kind, nid = self._hit_test(x, y)
        if kind != "node":
            return False
        self._set_initial(nid)
        return True

    def set_final_at(self, x, y):
        """把 (x, y) 处的状态设为最终状态（供圆环组件拖放调用）"""
        kind, nid = self._hit_test(x, y)
        if kind != "node":
            return False
        self._set_final(nid)
        return True

    def _set_trans_style(self, tid, style):
        """切换转移走法：line 直线 / curve 曲线"""
        t = self.transitions.get(tid)
        if not t:
            return
        self._push_undo()
        t["style"] = "curve" if style == "curve" else "line"
        if t["style"] == "line":
            t["waypoints"].clear()
        self._redraw_transition(tid)
        self._refresh_handles()
        self._notify()

    # ── 供右侧标签表和事件-状态矩阵调用的接口 ────────────────
    def select_state(self, nid):
        """从矩阵等外部视图选中状态"""
        if nid in self.nodes:
            self._select_node(nid)

    def select_transition(self, tid):
        """从矩阵等外部视图选中转移"""
        if tid in self.transitions:
            self._select_trans(tid)

    def rename_state(self, nid, name):
        """修改状态名，重名或为空返回 False"""
        name = (name or "").strip()
        if nid not in self.nodes or not name:
            return False
        if name == self.nodes[nid]["name"]:
            return True
        if self._name_taken(name, exclude=nid):
            return False
        self._apply_rename(nid, name)
        return True

    def set_event_name(self, tid, event):
        """修改转移事件名，空值返回 False"""
        event = (event or "").strip()
        t = self.transitions.get(tid)
        if not t or not event or t.get("trigger") == "auto":
            return False
        if t["event"] == event:
            return True
        self._push_undo()
        t["event"] = event
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()
        return True

    def set_transition_guard(self, tid, guard, record=True):
        """设置 / 清空守卫条件（内容不做校验，原样保存）"""
        t = self.transitions.get(tid)
        if not t:
            return False
        guard = self.normalize_expr(guard)
        if (t.get("guard") or "") == guard:
            return True
        if record:
            self._push_undo()
        t["guard"] = guard
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()
        return True

    @staticmethod
    def normalize_expr(text):
        """统一换行、去掉每行尾部空白"""
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in text.split("\n")).strip()

    def set_state_action(self, nid, kind, text, record=True):
        """设置状态内部动作（entry/exit/do），内容不做校验"""
        n = self.nodes.get(nid)
        if not n or kind not in self.STATE_ACTION_KINDS:
            return False
        text = self.normalize_expr(text)
        actions = n.setdefault(
            "actions", {k: "" for k in self.STATE_ACTION_KINDS})
        actions.setdefault(kind, "")
        if actions[kind] == text:
            return True
        if record:
            self._push_undo()
        actions[kind] = text
        self._refresh_node_actions(nid)
        self._notify()
        return True

    def clear_state_actions(self, nid):
        """清空该状态的全部内部动作"""
        n = self.nodes.get(nid)
        if not n:
            return
        actions = n.get("actions") or {}
        if not any((v or "").strip() for v in actions.values()):
            return
        self._push_undo()
        n["actions"] = {k: "" for k in self.STATE_ACTION_KINDS}
        self._refresh_node_actions(nid)
        self._notify()

    def set_state_actions_enabled(self, nid, enabled, kinds=None):
        """开关状态内部动作：关闭时清空指定动作（默认进入/退出/执行），开关状态随对象保存"""
        n = self.nodes.get(nid)
        if not n:
            return
        enabled = bool(enabled)
        if bool(n.get("actions_on")) == enabled:
            return
        self._push_undo()
        n["actions_on"] = enabled
        if not enabled:
            if kinds is None:
                n["actions"] = {k: "" for k in self.STATE_ACTION_KINDS}
            else:
                actions = n.setdefault(
                    "actions", {k: "" for k in self.STATE_ACTION_KINDS})
                for k in kinds:
                    if k in actions:
                        actions[k] = ""
        self._refresh_node_actions(nid)
        self._notify()

    # ── 内部转移（留在当前状态执行） ────────────────────────
    def add_internal_transition(self, nid):
        """新增一条内部转移，返回索引；事件留空待填写"""
        n = self.nodes.get(nid)
        if not n:
            return -1
        self._push_undo()
        n.setdefault("internal", []).append(
            {"event": "", "guard": "", "action": ""})
        self._notify()
        return len(n["internal"]) - 1

    def set_internal_field(self, nid, index, field, text):
        """设置内部转移的 event / guard / action"""
        n = self.nodes.get(nid)
        if not n or field not in ("event", "guard", "action"):
            return False
        items = n.get("internal") or []
        if not 0 <= index < len(items):
            return False
        if field == "event":
            value = (text or "").strip()
        else:
            value = self.normalize_expr(text)
        if (items[index].get(field) or "") == value:
            return True
        self._push_undo()
        items[index][field] = value
        self._refresh_node_actions(nid)
        self._notify()
        return True

    def delete_internal_transition(self, nid, index):
        n = self.nodes.get(nid)
        if not n:
            return
        items = n.get("internal") or []
        if not 0 <= index < len(items):
            return
        self._push_undo()
        items.pop(index)
        self._refresh_node_actions(nid)
        self._notify()

    def move_internal_transition(self, nid, index, delta):
        n = self.nodes.get(nid)
        if not n:
            return
        items = n.get("internal") or []
        target = index + delta
        if not (0 <= index < len(items) and 0 <= target < len(items)):
            return
        self._push_undo()
        items[index], items[target] = items[target], items[index]
        self._refresh_node_actions(nid)
        self._notify()

    def set_transition_trigger(self, tid, trigger):
        """切换转移触发方式：event 事件 / auto 自动"""
        t = self.transitions.get(tid)
        if not t or trigger not in ("event", "auto"):
            return False
        if t.get("trigger", "event") == trigger:
            return True
        self._push_undo()
        t["trigger"] = trigger
        if trigger == "auto":
            t["event"] = ""
        elif not (t.get("event") or "").strip():
            t["event"] = self._next_event_name()
        self._redraw_transition(tid)
        self._refresh_handles()
        self._notify()
        return True

    def set_transition_action(self, tid, text, record=True):
        """设置转移动作（事件触发时执行，内容不做校验）"""
        t = self.transitions.get(tid)
        if not t:
            return False
        text = self.normalize_expr(text)
        if (t.get("action") or "") == text:
            return True
        if record:
            self._push_undo()
        t["action"] = text
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()
        return True

    def clear_transition_action(self, tid):
        """清空该转移的动作（不影响状态的 entry/exit/do）"""
        t = self.transitions.get(tid)
        if not t or not (t.get("action") or "").strip():
            return
        self._push_undo()
        t["action"] = ""
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()

    def set_guard_enabled(self, tid, enabled):
        """开关守卫：关闭时清空条件；开关状态随对象保存，留空也保持开启"""
        t = self.transitions.get(tid)
        if not t:
            return
        enabled = bool(enabled)
        if bool(t.get("guard_on")) == enabled:
            return
        self._push_undo()
        t["guard_on"] = enabled
        if not enabled:
            t["guard"] = ""
            self.itemconfigure(t["label_id"], text=self._label_text(t))
            self._place_label(tid)
        self._notify()

    def set_action_enabled(self, tid, enabled):
        """开关转移动作：关闭时清空动作，开关状态随对象保存"""
        t = self.transitions.get(tid)
        if not t:
            return
        enabled = bool(enabled)
        if bool(t.get("action_on")) == enabled:
            return
        self._push_undo()
        t["action_on"] = enabled
        if not enabled:
            t["action"] = ""
            self.itemconfigure(t["label_id"], text=self._label_text(t))
            self._place_label(tid)
        self._notify()

    # ── 事件表 / 优先级 ─────────────────────────────────────
    def set_transition_priority(self, tid, value):
        """设置优先级：正整数，且同一状态内不能重复"""
        t = self.transitions.get(tid)
        if not t:
            return False
        try:
            priority = int(str(value).strip())
        except (TypeError, ValueError):
            return False
        if priority <= 0:
            return False
        if any(
            other is not t and other["from"] == t["from"]
            and other.get("priority") == priority
            for other in self.transitions.values()
        ):
            return False
        if t.get("priority") == priority:
            return True
        self._push_undo()
        t["priority"] = priority
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()
        return True

    def rename_event(self, old, new):
        """重命名事件并同步所有转移与内部转移"""
        new = (new or "").strip()
        if not new:
            return False
        if old == new:
            return True
        if any(t["event"] == new for t in self.transitions.values()):
            return False
        if any(
            (item.get("event") or "").strip() == new
            for n in self.nodes.values()
            for item in (n.get("internal") or [])
        ):
            return False
        targets = [t for t in self.transitions.values() if t["event"] == old]
        internal_targets = [
            (nid, item)
            for nid, n in self.nodes.items()
            for item in (n.get("internal") or [])
            if (item.get("event") or "").strip() == old
        ]
        if not targets and not internal_targets:
            return False
        self._push_undo()
        for t in targets:
            t["event"] = new
        for _nid, item in internal_targets:
            item["event"] = new
        for tid, t in self.transitions.items():
            if t["event"] == new:
                self.itemconfigure(t["label_id"], text=self._label_text(t))
                self._place_label(tid)
        for nid in {nid for nid, _item in internal_targets}:
            self._refresh_node_actions(nid)
        self._notify()
        return True

    def set_transition_style(self, tid, style):
        if tid not in self.transitions:
            return False
        if self.transitions[tid].get("style") == (
                "curve" if style == "curve" else "line"):
            return True
        self._set_trans_style(tid, style)
        return True

    def set_initial_state(self, nid, is_initial=True):
        """设置 / 取消初始状态"""
        n = self.nodes.get(nid)
        if not n:
            return False
        if bool(n["is_initial"]) == bool(is_initial):
            return True
        if is_initial:
            self._set_initial(nid)
        else:
            self._push_undo()
            self._remove_initial_marker(nid)
            n["is_initial"] = False
            self._apply_node_style(nid)
            self._notify()
        return True

    def set_final_state(self, nid, is_final=True):
        """设置 / 取消最终状态（与初始状态一样保持唯一）"""
        n = self.nodes.get(nid)
        if not n:
            return False
        if bool(n.get("is_final")) == bool(is_final):
            return True
        if is_final:
            self._set_final(nid)
        else:
            self._push_undo()
            self._remove_final_marker(nid)
            n["is_final"] = False
            self._notify()
        return True

    def _next_state_name(self):
        i = len(self.nodes) + 1
        while self._name_taken(f"STATE_{i}"):
            i += 1
        return f"STATE_{i}"

    def _rename_node(self, nid):
        n = self.nodes[nid]
        name = simpledialog.askstring(
            "重命名状态", "状态名：", initialvalue=n["name"], parent=self,
        )
        if name is None:
            return
        name = name.strip()
        if not name or name == n["name"]:
            return
        if self._name_taken(name, exclude=nid):
            messagebox.showerror("重名", f"已存在状态「{name}」", parent=self)
            return
        self._apply_rename(nid, name)

    def _apply_rename(self, nid, name):
        """改节点名并刷新画布文字（供重命名/测试复用）"""
        self._push_undo()
        self.nodes[nid]["name"] = name
        self.itemconfigure(self.nodes[nid]["text_id"], text=name)
        self._notify()

    def _edit_event(self, tid):
        t = self.transitions[tid]
        event = simpledialog.askstring(
            "编辑转移", "事件名：", initialvalue=t["event"], parent=self,
        )
        if event is None:
            return
        event = event.strip()
        if not event:
            return
        self._push_undo()
        t["event"] = event
        self.itemconfigure(t["label_id"], text=self._label_text(t))
        self._place_label(tid)
        self._notify()

    def _set_initial(self, nid):
        self._push_undo()
        n = self.nodes[nid]
        scope = n.get("parent")
        # 初始状态按层唯一：不影响其他复合状态内部的初始状态
        for other_id, other in self.nodes.items():
            if (other_id != nid and other["is_initial"]
                    and other.get("parent") == scope):
                self._remove_initial_marker(other_id)
                other["is_initial"] = False
                self._apply_node_style(other_id)
        if n["is_initial"]:
            self._remove_initial_marker(nid)
        n["is_initial"] = True
        self._add_initial_marker(nid)
        self._apply_node_style(nid)
        self._notify()

    def _set_final(self, nid):
        self._push_undo()
        for other_id, other in self.nodes.items():
            if other.get("is_final"):
                self._remove_final_marker(other_id)
                other["is_final"] = False
        n = self.nodes[nid]
        n["is_final"] = True
        self._add_final_marker(nid)
        self._notify()

    def _delete_node(self, nid, record=True):
        # 多选批量删除时，子状态可能已被父状态带着删掉
        if nid not in self.nodes:
            return
        if record:
            self._push_undo()
        parent = self.nodes[nid].get("parent")
        # 复合状态：连同内部所有子状态一起删除
        for cid in self.children_of(nid):
            self._delete_node(cid, record=False)
        related = [
            tid for tid, t in self.transitions.items()
            if t["from"] == nid or t["to"] == nid
        ]
        for tid in related:
            self._delete_transition(tid, notify=False, record=False)
        n = self.nodes.pop(nid)
        for item in n["items"]:
            self.delete(item)
        self.selected_nodes.discard(nid)
        if self.link_source == nid:
            self.link_source = None
        if parent in self.nodes:
            self._refresh_node_actions(parent)
        self._notify()
        self._notify_selection()

    def _delete_transition(self, tid, notify=True, record=True):
        if record:
            self._push_undo()
        t = self.transitions.pop(tid, None)
        if not t:
            return
        items = [t["line_id"], t["label_id"]]
        if t.get("label_bg_id") is not None:
            items.append(t["label_bg_id"])
        self.delete(*items)
        if tid in self.selected_transes:
            self.selected_transes.discard(tid)
            if self.selected_trans == tid:
                self.selected_trans = next(iter(self.selected_transes), None)
            self._refresh_handles()
            self._notify_selection()
        # 反向转移若存在，需要从弧线重画回直线
        reverse = self._find_transition(t["to"], t["from"])
        if reverse:
            self._redraw_transition(reverse)
        if notify:
            self._notify()

    def _name_taken(self, name, exclude=None):
        return any(
            n["name"] == name and nid != exclude
            for nid, n in self.nodes.items()
        )

    def _notify(self):
        if self.on_change:
            self.on_change()
