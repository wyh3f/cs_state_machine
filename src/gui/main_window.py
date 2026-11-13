"""
主窗口 — 顶部工具栏 + 左侧画布 + 右侧属性面板 + 底部状态栏
customtkinter 负责整体框架，画布用原生 tk.Canvas（customtkinter 没有 Canvas 控件）
"""
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from canvas_widget import StateCanvas


class HoverTooltip:
    """鼠标悬停后显示的轻量说明，移出或控件销毁时自动关闭"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button-1>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _schedule(self, _event=None):
        self._cancel_pending()
        self._after_id = self.widget.after(350, self.show)

    def _cancel_pending(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def show(self):
        self._after_id = None
        if self.window is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            self.window = tk.Toplevel(self.widget)
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            label = tk.Label(
                self.window, text=self.text, bg="#263746", fg="#ffffff",
                justify="left", wraplength=280, padx=10, pady=7,
                font=("Segoe UI", 9),
            )
            label.pack()
            self.window.update_idletasks()

            width = self.window.winfo_reqwidth()
            height = self.window.winfo_reqheight()
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            screen_w = self.widget.winfo_screenwidth()
            screen_h = self.widget.winfo_screenheight()
            if x + width > screen_w:
                x = self.widget.winfo_rootx() - width - 6
            if y + height > screen_h:
                y = self.widget.winfo_rooty() - height - 4
            self.window.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            self.window = None

    def hide(self, _event=None):
        self._cancel_pending()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


class HelpIcon(tk.Canvas):
    """输入/选择控件后的圆形问号图标"""

    def __init__(self, master, help_text, bg="#ffffff"):
        super().__init__(
            master, width=16, height=16, bg=bg, highlightthickness=0,
            cursor="hand2", takefocus=0,
        )
        self.help_text = help_text
        self.create_oval(
            1, 1, 15, 15, fill="#eef3f8", outline="#8293a5", width=1,
        )
        self.create_text(
            8, 8, text="?", fill="#526575", font=("Segoe UI", 9, "bold"),
        )
        self.tooltip = HoverTooltip(self, help_text)


class CollapsibleInput(ctk.CTkFrame):
    """可折叠的多行输入：▶ 标题 + 文本框（Enter 换行，输入即保存）"""

    def __init__(self, master, title, height=72, bg="#ffffff", help_text=""):
        super().__init__(master, fg_color="transparent")
        # 默认收起，点击三角或标题展开
        self._expanded = False

        head = tk.Frame(self, bg=bg, cursor="hand2")
        head.pack(fill="x")
        self._triangle = tk.Label(
            head, text="▶", bg=bg, fg="#777777",
            font=("Segoe UI", 7), width=2, cursor="hand2",
        )
        self._triangle.pack(side="left")
        self._title = tk.Label(
            head, text=title, bg=bg, fg="#1a1a1a",
            font=("Segoe UI", 10), anchor="w", cursor="hand2",
        )
        self._title.pack(side="left")
        if help_text:
            HelpIcon(head, help_text, bg=bg).pack(side="left", padx=(5, 0))

        for widget in (head, self._triangle, self._title):
            widget.bind("<Button-1>", self._toggle)

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.textbox = ctk.CTkTextbox(
            self.body, height=height, wrap="word",
            border_width=1, border_color="#d5d9e0",
            corner_radius=6, font=ctk.CTkFont(size=11),
        )
        self.textbox.pack(fill="x")

    def _toggle(self, _event=None):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        if self._expanded:
            self._triangle.configure(text="▼")
            self.body.pack(fill="x", pady=(2, 0))
        else:
            self._triangle.configure(text="▶")
            self.body.pack_forget()

    def get(self):
        return self.textbox.get("1.0", "end-1c")

    def set(self, text):
        self.textbox.delete("1.0", "end")
        if text:
            self.textbox.insert("1.0", text)

    def clear(self):
        self.textbox.delete("1.0", "end")


class EventStateMatrix(tk.Toplevel):
    """事件-状态矩阵：现有状态图的可滚动同步视图"""

    EVENT_COLUMN_W = 190
    STATE_COLUMN_W = 120

    def __init__(self, master, model):
        super().__init__(master)
        self.model = model
        self.title("事件-状态矩阵")
        self.minsize(600, 360)
        x = master.winfo_rootx() + 70
        y = master.winfo_rooty() + 70
        self.geometry(f"860x500+{x}+{y}")
        self.transient(master)

        tk.Label(
            self, text="事件-状态矩阵", bg="#ffffff", fg="#1a1a1a",
            font=("Segoe UI", 13, "bold"), anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(
            self,
            text="点击条目可选中对应转移；内部转移会选中所属状态。空白表示未定义。",
            bg="#ffffff", fg="#666666", font=("Segoe UI", 9), anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 10))

        table = tk.Frame(self, bg="#d8dde5")
        table.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        self.view = tk.Canvas(
            table, bg="#f5f7fa", highlightthickness=0,
            xscrollincrement=20, yscrollincrement=20,
        )
        ybar = tk.Scrollbar(table, orient="vertical", command=self.view.yview)
        xbar = tk.Scrollbar(table, orient="horizontal", command=self.view.xview)
        self.view.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.view.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")

        self.content = tk.Frame(self.view, bg="#d8dde5")
        self.content_window = self.view.create_window(
            (0, 0), window=self.content, anchor="nw")
        self._column_count = 0
        self._row_count = 0
        self.content.bind("<Configure>", self._update_scrollregion)
        self.view.bind("<MouseWheel>", self._scroll_vertical)
        self.view.bind("<Shift-MouseWheel>", self._scroll_horizontal)
        self.refresh()

    def _update_scrollregion(self, _event=None):
        bbox = self.view.bbox("all")
        if bbox:
            self.view.configure(scrollregion=bbox)

    def _scroll_vertical(self, event):
        self.view.yview_scroll(int(-event.delta / 120), "units")

    def _scroll_horizontal(self, event):
        self.view.xview_scroll(int(-event.delta / 120), "units")
        return "break"

    @staticmethod
    def _compact(text, limit=38):
        text = " ".join((text or "").split())
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _transition_text(self, t):
        target = self.model.nodes[t["to"]]["name"]
        text = f"[{t.get('priority', 1)}] → {target}"
        guard = " ".join((t.get("guard") or "").split())
        if guard:
            text += f" [{guard}]"
        action = " ".join((t.get("action") or "").split())
        if action:
            text += f" / {action}"
        return self._compact(text)

    def _internal_text(self, item):
        text = "内部处理"
        guard = " ".join((item.get("guard") or "").split())
        if guard:
            text += f" [{guard}]"
        action = " ".join((item.get("action") or "").split())
        if action:
            text += f" / {action}"
        return self._compact(text)

    def _cell(self, row, column, bg="#ffffff"):
        cell = tk.Frame(
            self.content, bg=bg, highlightbackground="#d8dde5",
            highlightthickness=1, bd=0,
        )
        cell.grid(row=row, column=column, sticky="nsew")
        return cell

    def _text_cell(self, row, column, text, **kwargs):
        bg = kwargs.pop("bg", "#ffffff")
        cell = self._cell(row, column, bg)
        kwargs.setdefault("font", ("Segoe UI", 9))
        label = tk.Label(
            cell, text=text, bg=bg, padx=8, pady=7, anchor="center", **kwargs,
        )
        label.pack(fill="both", expand=True)
        return label

    def refresh(self):
        """按当前画布数据重建矩阵；保留滚动位置"""
        if not self.winfo_exists():
            return
        xview, yview = self.view.xview(), self.view.yview()
        for child in self.content.winfo_children():
            child.destroy()

        events = []
        seen = set()
        for t in self.model.transitions.values():
            if t.get("trigger") == "auto":
                continue
            name = (t.get("event") or "").strip()
            if name and name not in seen:
                seen.add(name)
                events.append(name)
        for n in self.model.nodes.values():
            for item in n.get("internal") or []:
                name = (item.get("event") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    events.append(name)
        columns = [(name, "event") for name in events] + [("自动", "auto")]

        # 清除已删除事件/状态遗留的网格尺寸，确保滚动区域同步收缩
        for col in range(self._column_count):
            self.content.grid_columnconfigure(col, minsize=0)
        for row in range(self._row_count):
            self.content.grid_rowconfigure(row, minsize=0)
        self._column_count = len(columns) + 1
        self._row_count = len(self.model.nodes) + 1

        self.content.grid_columnconfigure(0, minsize=self.STATE_COLUMN_W)
        for col in range(1, len(columns) + 1):
            self.content.grid_columnconfigure(col, minsize=self.EVENT_COLUMN_W)

        self._text_cell(
            0, 0, "状态 \\ 事件", bg="#e8eef6", fg="#263746",
            font=("Segoe UI", 9, "bold"),
        )
        for col, (name, _kind) in enumerate(columns, start=1):
            self._text_cell(
                0, col, name, bg="#e8eef6", fg="#263746",
                wraplength=self.EVENT_COLUMN_W - 18,
            )

        for row, (nid, node) in enumerate(self.model.nodes.items(), start=1):
            self.content.grid_rowconfigure(row, minsize=44)
            flags = ""
            if node.get("is_initial"):
                flags += "● "
            state_name = flags + node["name"]
            if node.get("is_final"):
                state_name += " ◉"
            state_label = self._text_cell(
                row, 0, state_name, bg="#f0f3f7", fg="#263746",
                font=("Segoe UI", 9, "bold"), cursor="hand2",
            )
            state_label.bind(
                "<Button-1>", lambda _e, node_id=nid: self._select_node(node_id))

            for col, (name, kind) in enumerate(columns, start=1):
                if kind == "auto":
                    transitions = [
                        (tid, t) for tid, t in self.model.transitions.items()
                        if t["from"] == nid and t.get("trigger") == "auto"
                    ]
                    internal = []
                else:
                    transitions = [
                        (tid, t) for tid, t in self.model.transitions.items()
                        if t["from"] == nid and t.get("trigger") != "auto"
                        and (t.get("event") or "").strip() == name
                    ]
                    internal = [
                        item for item in (node.get("internal") or [])
                        if (item.get("event") or "").strip() == name
                    ]
                transitions.sort(key=lambda pair: pair[1].get("priority", 1))

                if not transitions and not internal:
                    self._text_cell(row, col, "—", bg="#ffffff", fg="#b0b6bf")
                    continue

                cell = self._cell(row, col)
                for tid, t in transitions:
                    label = tk.Label(
                        cell, text=self._transition_text(t), bg="#f4f8fd",
                        fg="#1a6bc5", anchor="w", justify="left",
                        wraplength=self.EVENT_COLUMN_W - 18,
                        padx=8, pady=6, cursor="hand2",
                        font=("Segoe UI", 9),
                    )
                    label.pack(fill="x", expand=True, pady=(0, 1))
                    label.bind(
                        "<Button-1>",
                        lambda _e, trans_id=tid: self._select_transition(trans_id),
                    )
                for item in internal:
                    label = tk.Label(
                        cell, text=self._internal_text(item), bg="#eef7f2",
                        fg="#2e7d32", anchor="w", justify="left",
                        wraplength=self.EVENT_COLUMN_W - 18,
                        padx=8, pady=6, cursor="hand2",
                        font=("Segoe UI", 9),
                    )
                    label.pack(fill="x", expand=True, pady=(0, 1))
                    label.bind(
                        "<Button-1>", lambda _e, node_id=nid: self._select_node(node_id))

        self.view.update_idletasks()
        self.view.xview_moveto(xview[0])
        self.view.yview_moveto(yview[0])

    def _select_transition(self, tid):
        self.model.select_transition(tid)

    def _select_node(self, nid):
        self.model.select_state(nid)


class StatePalette(tk.Frame):
    """左侧组件栏：把「状态」卡片拖到画布上松手即可新建节点"""

    CARD_W = 88
    CARD_H = 42

    def __init__(self, master):
        super().__init__(master, width=140, bg="#f5f5f7")
        self.pack_propagate(False)

        self.canvas = None
        self._ghost = None
        self._drag_kind = "state"

        # 标题行：左侧"组件"，右侧圆形问号按钮切换操作提示
        title_row = tk.Frame(self, bg="#f5f5f7")
        title_row.pack(anchor="w", padx=14, pady=(16, 10))
        tk.Label(
            title_row, text="组件", bg="#f5f5f7", fg="#1a1a1a",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        # 问号按钮：圆形 + 问号，点击切换下方灰色提示文字
        qbtn = tk.Canvas(
            title_row, width=16, height=16, bg="#f5f5f7",
            highlightthickness=0, cursor="hand2", takefocus=0,
        )
        qbtn.pack(side="left", padx=(8, 0))
        qbtn.create_oval(1, 1, 15, 15, fill="#eef3f8", outline="#8293a5", width=1)
        qbtn.create_text(8, 8, text="?", fill="#526575",
                         font=("Segoe UI", 9, "bold"))
        qbtn.bind("<Button-1>", lambda _e: self._toggle_hints())
        self._qbtn = qbtn
        self._hint_shown = False

        # 卡片用原生 tk 组件：CTk 控件的 bind 绑在内部 canvas 上，
        # 在 CTkFrame 上生成的鼠标事件无法触发，拖拽会失效
        card = tk.Frame(
            self, width=self.CARD_W, height=self.CARD_H,
            bg="#e8f0fe", highlightbackground="#3b8ed0",
            highlightthickness=2, bd=0, cursor="hand2",
        )
        card.pack(padx=14, pady=2)
        card.pack_propagate(False)
        self.card = card
        label = tk.Label(
            card, text="状态", bg="#e8f0fe", fg="#1a1a1a",
            font=("Segoe UI", 10, "bold"),
        )
        label.pack(expand=True)

        for widget in (card, label):
            widget.bind("<Button-1>", lambda e: self._start_drag(e, "state"))
            widget.bind("<B1-Motion>", self._move_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

        # 初始状态组件：拖到某个状态上松手，该状态即成为初始状态
        init_card = tk.Frame(
            self, width=self.CARD_W, height=self.CARD_H,
            bg="#f5f5f7", highlightbackground="#2e7d32",
            highlightthickness=2, bd=0, cursor="hand2",
        )
        init_card.pack(padx=14, pady=(6, 2))
        init_card.pack_propagate(False)
        self.init_card = init_card
        circle = tk.Label(
            init_card, text="●", fg="#2e7d32", bg="#f5f5f7",
            font=("Segoe UI", 14),
        )
        circle.pack(side="left", padx=(12, 2))
        init_text = tk.Label(
            init_card, text="初始", bg="#f5f5f7", fg="#1a1a1a",
            font=("Segoe UI", 9, "bold"),
        )
        init_text.pack(side="left")

        for widget in (init_card, circle, init_text):
            widget.bind("<Button-1>", lambda e: self._start_drag(e, "initial"))
            widget.bind("<B1-Motion>", self._move_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

        # 最终状态组件：拖到某个状态上松手，该状态即成为最终状态
        final_card = tk.Frame(
            self, width=self.CARD_W, height=self.CARD_H,
            bg="#f5f5f7", highlightbackground="#333333",
            highlightthickness=2, bd=0, cursor="hand2",
        )
        final_card.pack(padx=14, pady=(6, 2))
        final_card.pack_propagate(False)
        self.final_card = final_card
        final_icon = tk.Label(
            final_card, text="◉", fg="#333333", bg="#f5f5f7",
            font=("Segoe UI", 14),
        )
        final_icon.pack(side="left", padx=(12, 2))
        final_text = tk.Label(
            final_card, text="最终", bg="#f5f5f7", fg="#1a1a1a",
            font=("Segoe UI", 9, "bold"),
        )
        final_text.pack(side="left")

        for widget in (final_card, final_icon, final_text):
            widget.bind("<Button-1>", lambda e: self._start_drag(e, "final"))
            widget.bind("<B1-Motion>", self._move_drag)
            widget.bind("<ButtonRelease-1>", self._end_drag)

        # 操作提示文字，默认隐藏；点击标题旁问号按钮展开
        self._hint_box = tk.Frame(self, bg="#f5f5f7")
        tk.Label(
            self._hint_box,
            text=("拖入画布松手\n即可新建状态\n\n"
                  "选中后拖右下角\n可调整大小\n\n"
                  "拖到已有状态上\n成为子状态\n\n"
                  "拖绿色圆到状态\n可设为初始\n\n"
                  "拖深色圆环到状态\n可设为最终\n\n"
                  "按住 Ctrl 点击\n两个状态即连线\n\n"
                  "Shift/框选 = 多选\n"
                  "Ctrl+A = 全选\n"
                  "Ctrl+C/V = 复制粘贴\n"
                  "Ctrl+D = 复制一份\n"
                  "Ctrl+Z/Y = 撤销重做"),
            bg="#f5f5f7", fg="gray", justify="left", anchor="w",
            wraplength=112,
            font=("Segoe UI", 7),
        ).pack(anchor="w", padx=14, pady=(10, 0))
        self._hint_box.pack_forget()
        self._hint_shown = False

    def _toggle_hints(self):
        if self._hint_shown:
            self._hint_box.pack_forget()
            self._hint_shown = False
        else:
            self._hint_box.pack(anchor="w")
            self._hint_shown = True

    def attach(self, canvas):
        self.canvas = canvas

    # ── 拖拽 ────────────────────────────────────────────────
    def _start_drag(self, _event, kind="state"):
        self._drag_kind = kind
        self._ghost = tk.Toplevel(self)
        self._ghost.overrideredirect(True)
        self._ghost.attributes("-alpha", 0.75)
        self._ghost.attributes("-topmost", True)

        if kind == "initial":
            canvas = tk.Canvas(
                self._ghost, width=40, height=40,
                bg="#ffffff", highlightthickness=0,
            )
            canvas.pack()
            canvas.create_oval(
                6, 6, 34, 34, fill="#2e7d32", outline="#1b5e20", width=2,
            )
            return

        if kind == "final":
            canvas = tk.Canvas(
                self._ghost, width=40, height=40,
                bg="#ffffff", highlightthickness=0,
            )
            canvas.pack()
            canvas.create_oval(
                6, 6, 34, 34, fill="#ffffff", outline="#333333", width=2,
            )
            canvas.create_oval(
                15, 15, 25, 25, fill="#333333", outline="#333333",
            )
            return

        frame = tk.Frame(
            self._ghost, bg="#d4e4fc",
            highlightbackground="#3b8ed0", highlightthickness=2,
        )
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame, text="STATE", bg="#d4e4fc", fg="#1a1a1a",
            font=("Segoe UI", 9, "bold"),
        ).pack(expand=True)

    def _move_drag(self, event):
        if not self._ghost or not self.canvas:
            return
        if self._drag_kind in ("initial", "final"):
            w = h = 40
        else:
            w, h = self.canvas.NODE_W, self.canvas.NODE_H
        self._ghost.geometry(
            f"{w}x{h}+{event.x_root - w // 2}+{event.y_root - h // 2}"
        )

    def _end_drag(self, event):
        if not self._ghost:
            return
        self._ghost.destroy()
        self._ghost = None
        if not self.canvas:
            return

        x = event.x_root - self.canvas.winfo_rootx()
        y = event.y_root - self.canvas.winfo_rooty()
        if not (0 <= x <= self.canvas.winfo_width()
                and 0 <= y <= self.canvas.winfo_height()):
            return

        if self._drag_kind == "initial":
            self.canvas.set_initial_at(x, y)
        elif self._drag_kind == "final":
            self.canvas.set_final_at(x, y)
        else:
            self.canvas.add_state_at(x, y)


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self._table_refresh_pending = False
        self.event_matrix = None
        # 工程文件状态
        self.project_path = None
        self._modified = False
        self._loading = False
        self._last_style = None

        self.title("状态机 C 代码生成器")

        # 按屏幕可用尺寸自适应。customtkinter 会把 geometry 乘以窗口缩放系数，
        # 所以这里先除以缩放，保证最终物理尺寸不超过屏幕
        scaling = ctk.ScalingTracker.get_window_scaling(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1280, int((sw - 80) / scaling))
        h = min(800, int((sh - 120) / scaling))
        x = max(0, int((sw / scaling - w) / 2))
        y = max(0, int((sh / scaling - h) / 2) - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(960, w), min(600, h))

        self._build_toolbar()
        # 状态栏必须先于主体 pack，否则 expand 的主体把底部空间吃光，状态栏高度为 0
        self._build_statusbar()
        self._build_body()

        self._refresh_status_counts()
        self._refresh_zoom_label(self.canvas.zoom)
        self.bind("<Control-s>", self._on_save_key)
        self.bind("<Control-S>", self._on_save_key)

    def _on_save_key(self, _event=None):
        self._on_save()
        return "break"

    def _mark_active_modified(self):
        """把当前画布标记为已修改（标签标题、状态栏同步）"""
        if self._loading:
            return
        doc = self._active_doc()
        if doc is not None and not doc["modified"]:
            doc["modified"] = True
            self._refresh_tab_title(doc)
        self._modified = True
        self._refresh_status_counts()

    def _refresh_status_counts(self):
        nodes = len(self.canvas.nodes) if self.canvas is not None else 0
        trans = len(self.canvas.transitions) if self.canvas is not None else 0
        doc = self._active_doc()
        if doc is not None and doc["path"]:
            name = os.path.basename(doc["path"])
        elif doc is not None:
            name = doc["name"]
        else:
            name = "未命名工程"
        if self._modified:
            state = "已修改"
        elif doc is not None and doc["path"]:
            state = "已保存"
        else:
            state = "未保存"
        self.status_label.configure(
            text=f"{name}  |  {state}  |  状态：{nodes}  转移：{trans}"
        )
        self.node_count_label.configure(text=str(nodes))
        self.trans_count_label.configure(text=str(trans))
        self._schedule_table_refresh()

    def _schedule_table_refresh(self):
        """画布数据变化后延迟合并刷新标签表，保持与图形一致"""
        if self._table_refresh_pending:
            return
        self._table_refresh_pending = True
        self.after(30, self._do_table_refresh)

    def _do_table_refresh(self):
        self._table_refresh_pending = False
        # 控件是复用的，不会打断输入，直接刷新即可
        self._refresh_property_table()
        self._refresh_event_table()
        self._refresh_event_matrix()

    def _style_text(self):
        """两个下拉组合成展示用的风格名，如「极简版 FSM」"""
        return f"{self.level_var.get()} {self.arch_var.get()}"

    def _on_style_changed(self, _value=None):
        self.style_value_label.configure(text=self._style_text())
        doc = self._active_doc() if getattr(self, "docs", None) else None
        if doc is None:
            return
        doc["arch"] = self.arch_var.get()
        doc["level"] = self.level_var.get()
        if not self._loading and (doc["arch"], doc["level"]) != (
                self._last_style or (None, None)):
            self._mark_active_modified()
        self._last_style = (doc["arch"], doc["level"])

    # ── 顶部工具栏 ──────────────────────────────────────────
    def _build_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, height=48, corner_radius=0)
        self.toolbar.pack(side="top", fill="x")
        self.toolbar.pack_propagate(False)

        buttons = [
            ("新建",      self._on_new),
            ("打开",      self._on_open),
            ("保存",      self._on_save),
            ("生成代码",  self._on_generate),
        ]
        for index, (text, cmd) in enumerate(buttons):
            ctk.CTkButton(
                self.toolbar, text=text, command=cmd,
                width=90, height=32, corner_radius=6,
            ).pack(side="left", padx=(12 if index == 0 else 8, 0), pady=8)

        # 分隔
        ctk.CTkLabel(self.toolbar, text="|", width=10).pack(side="left", padx=12, pady=8)

        # 状态机模式：架构类型 + 实现版本两个独立下拉
        ctk.CTkLabel(self.toolbar, text="状态机模式：").pack(side="left", padx=(0, 6), pady=8)
        self.arch_var = ctk.StringVar(value="FSM")
        arch_menu = ctk.CTkOptionMenu(
            self.toolbar,
            variable=self.arch_var,
            values=["FSM", "HSM"],
            width=90, height=32, corner_radius=6,
            command=self._on_style_changed,
        )
        arch_menu.pack(side="left", padx=(0, 4), pady=8)
        HelpIcon(
            self.toolbar,
            "选择代码生成的状态机架构：FSM 为扁平状态机，HSM 为层次状态机。当前画布编辑以 FSM 为主。",
            bg="#e5e5e5",
        ).pack(side="left", padx=(0, 14), pady=8)
        self.level_var = ctk.StringVar(value="极简版")
        level_menu = ctk.CTkOptionMenu(
            self.toolbar,
            variable=self.level_var,
            values=["极简版", "完整版"],
            width=100, height=32, corner_radius=6,
            command=self._on_style_changed,
        )
        level_menu.pack(side="left", padx=(0, 4), pady=8)
        HelpIcon(
            self.toolbar, "选择生成代码的实现版本：极简版或完整版。",
            bg="#e5e5e5",
        ).pack(side="left", pady=8)

        # 标题（居中）
        ctk.CTkLabel(
            self.toolbar, text="cs_state_machine",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="right", padx=16, pady=8)

    # ── 主体：左画布 + 右属性面板 ────────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="top", fill="both", expand=True)

        # 右侧属性面板先 pack，否则左侧 expand 的画布会把宽度/高度占光。
        # 注意：不要对 CTkScrollableFrame 调 pack_propagate(False)——
        # 它作用于内部内容帧，会让高度塌缩成 1px、内部控件全部不可见
        self.right_panel = ctk.CTkScrollableFrame(
            body, width=280, corner_radius=0, fg_color="#f5f5f7",
        )
        self.right_panel.pack(side="right", fill="y")

        # 左侧组件栏（拖入新状态），必须排在画布之前 pack，
        # 否则 expand 的画布会把剩余宽度全部吃掉
        self.palette = StatePalette(body)
        self.palette.pack(side="left", fill="y")

        # 中间画布：上方标签栏（每个标签一份独立画布）+ 下方画布区
        canvas_frame = ctk.CTkFrame(body, corner_radius=0)
        canvas_frame.pack(side="left", fill="both", expand=True)

        self.tab_bar = ctk.CTkFrame(
            canvas_frame, height=34, corner_radius=0, fg_color="#e9edf2")
        self.tab_bar.pack(fill="x")
        self.tab_bar.pack_propagate(False)
        self.add_tab_btn = ctk.CTkButton(
            self.tab_bar, text="＋", width=30, height=24, corner_radius=6,
            fg_color="transparent", hover_color="#d7dee8", text_color="#555",
            command=self._on_new_tab,
        )
        self.add_tab_btn.pack(side="left", padx=(4, 0), pady=4)

        self.canvas_host = ctk.CTkFrame(canvas_frame, corner_radius=0)
        self.canvas_host.pack(fill="both", expand=True)

        # 每个文档 = 一份画布 + 一个 JSON 文件
        self.docs = []
        self.doc_seq = 1
        self.canvas = None
        self._build_property_panel()
        self._create_doc("未命名1", demo=True)

    # ── 多画布文档 ───────────────────────────────────────────
    def _active_doc(self):
        for doc in self.docs:
            if doc["canvas"] is self.canvas:
                return doc
        return None

    def _create_tab(self, doc):
        frame = ctk.CTkFrame(
            self.tab_bar, height=26, corner_radius=6, fg_color="transparent")
        frame.pack(side="left", padx=(4, 0), pady=4, before=self.add_tab_btn)
        btn = ctk.CTkButton(
            frame, text=doc["name"], width=92, height=22, corner_radius=6,
            fg_color="transparent", hover_color="#d7dee8",
            text_color="#333333", anchor="w",
            command=lambda d=doc: self._activate_doc(d),
        )
        btn.pack(side="left", padx=(2, 0))
        close = ctk.CTkLabel(
            frame, text="×", width=16, text_color="#777777", cursor="hand2",
        )
        close.pack(side="left", padx=(0, 4))
        close.bind("<Button-1>", lambda _e, d=doc: self._close_doc(d))
        doc["tab"], doc["btn"], doc["close"] = frame, btn, close
        self._refresh_tab_title(doc)

    def _refresh_tab_title(self, doc):
        if not doc.get("btn"):
            return
        name = doc["name"] + (" *" if doc["modified"] else "")
        doc["btn"].configure(
            text=name, width=max(70, min(180, 14 * len(name) + 18)))

    def _style_tabs(self):
        active = self._active_doc()
        for doc in self.docs:
            is_active = doc is active
            doc["tab"].configure(
                fg_color="#ffffff" if is_active else "transparent")
            doc["btn"].configure(
                text_color="#1a1a1a" if is_active else "#666666")

    def _create_doc(self, name, path=None, data=None, project=None, demo=False):
        canvas = StateCanvas(self.canvas_host)
        project = project or {}
        doc = {
            "canvas": canvas, "path": path, "name": name,
            "project_name": project.get("name") or name,
            "arch": project.get("arch") if project.get("arch") in ("FSM", "HSM")
            else "FSM",
            "level": project.get("level")
            if project.get("level") in ("极简版", "完整版") else "极简版",
            "modified": False, "tab": None, "btn": None, "close": None,
        }
        canvas.on_change = lambda c=canvas: self._on_doc_changed(c)
        canvas.on_select = lambda c=canvas: self._on_doc_select(c)
        canvas.on_zoom = lambda z, c=canvas: self._on_doc_zoom(c, z)
        canvas.active_check = lambda c=canvas: c is self.canvas
        self.docs.append(doc)
        self._create_tab(doc)
        if data is not None:
            canvas.import_state(data)
        elif demo:
            canvas.demo_states()
        else:
            canvas.new_project()
        doc["modified"] = False
        self._activate_doc(doc)
        return doc

    def _activate_doc(self, doc):
        if doc not in self.docs:
            return
        for other in self.docs:
            other["canvas"].pack_forget()
        doc["canvas"].pack(fill="both", expand=True)
        self.canvas = doc["canvas"]
        self.project_path = doc["path"]
        self._modified = doc["modified"]
        self.palette.attach(self.canvas)
        self.canvas.focus_set()
        self._style_tabs()
        self._refresh_tab_title(doc)
        # 工程信息随当前画布同步（不触发“已修改”）
        previous = self._loading
        self._loading = True
        try:
            self.project_entry.delete(0, "end")
            self.project_entry.insert(0, doc["project_name"])
            self.arch_var.set(doc["arch"])
            self.level_var.set(doc["level"])
            self._on_style_changed()
        finally:
            self._loading = previous
        self._set_title()
        self._refresh_property_table()
        self._refresh_status_counts()
        self._refresh_zoom_label(self.canvas.zoom)
        if self.event_matrix is not None and self.event_matrix.winfo_exists():
            self.event_matrix.model = self.canvas
            self.event_matrix.refresh()

    def _on_doc_changed(self, canvas):
        if canvas is self.canvas:
            self._mark_active_modified()

    def _on_doc_select(self, canvas):
        if canvas is self.canvas:
            self._refresh_property_table()

    def _on_doc_zoom(self, canvas, zoom):
        if canvas is self.canvas:
            self._refresh_zoom_label(zoom)

    def _on_new_tab(self):
        self.doc_seq += 1
        self._create_doc(f"未命名{self.doc_seq}")

    def _close_doc(self, doc):
        if doc not in self.docs:
            return
        if doc["modified"] and not messagebox.askyesno(
                "关闭画布",
                f"「{doc['name']}」有未保存的修改，仍要关闭吗？", parent=self):
            return
        was_active = doc["canvas"] is self.canvas
        index = self.docs.index(doc)
        doc["canvas"].destroy()
        doc["tab"].destroy()
        self.docs.remove(doc)
        if not self.docs:
            self.doc_seq += 1
            self._create_doc(f"未命名{self.doc_seq}")
            return
        if was_active:
            self._activate_doc(self.docs[min(index, len(self.docs) - 1)])
        else:
            self._style_tabs()

    def _section_title(self, parent, text):
        """区块标题：左侧蓝色竖条 + 粗体文字"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkFrame(
            row, width=3, height=15, fg_color="#3b8ed0", corner_radius=1,
        ).pack(side="left", pady=1)
        ctk.CTkLabel(
            row, text=text, font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(8, 0))

    def _card(self):
        """右侧面板里的独立卡片：白底圆角边框，让三个区块在视觉上分开"""
        card = ctk.CTkFrame(
            self.right_panel, fg_color="#ffffff", corner_radius=8,
            border_width=1, border_color="#e3e6eb",
        )
        card.pack(fill="x", padx=10, pady=(10, 0))
        return card

    def _build_property_panel(self):
        # 卡片一：属性面板（守卫开关在这里）
        prop_card = self._card()
        self._section_title(prop_card, "属性面板")

        self.guard_hint = ctk.CTkLabel(
            prop_card,
            text="（选中状态可设置内部动作，选中转移可设置守卫和动作）",
            text_color="gray", anchor="w", justify="left", wraplength=236,
        )
        self.guard_hint.pack(fill="x", padx=14, pady=(0, 12))

        self.guard_switch_row = ctk.CTkFrame(prop_card, fg_color="transparent")
        ctk.CTkLabel(
            self.guard_switch_row, text="守卫", width=56, anchor="w",
        ).pack(side="left")
        self.guard_switch_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            self.guard_switch_row, text="", variable=self.guard_switch_var,
            width=46, command=self._on_guard_toggle,
        ).pack(side="left")
        HelpIcon(
            self.guard_switch_row,
            "开启后可填写守卫条件；条件成立时转移才允许发生。关闭会清空条件。",
        ).pack(side="left", padx=(5, 0))

        self.action_switch_row = ctk.CTkFrame(prop_card, fg_color="transparent")
        ctk.CTkLabel(
            self.action_switch_row, text="动作", width=56, anchor="w",
        ).pack(side="left")
        self.action_switch_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            self.action_switch_row, text="", variable=self.action_switch_var,
            width=46, command=self._on_action_toggle,
        ).pack(side="left")
        HelpIcon(
            self.action_switch_row,
            "开启后可填写转移动作；转移发生时执行。关闭会清空动作。",
        ).pack(side="left", padx=(5, 0))

        # 状态内部动作（进入 / 退出 / 执行），仅在选中单个状态时出现
        self.state_action_switch_row = ctk.CTkFrame(
            prop_card, fg_color="transparent")
        ctk.CTkLabel(
            self.state_action_switch_row, text="状态动作", width=64, anchor="w",
        ).pack(side="left")
        self.state_action_switch_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            self.state_action_switch_row, text="",
            variable=self.state_action_switch_var,
            width=46, command=self._on_state_action_toggle,
        ).pack(side="left")
        HelpIcon(
            self.state_action_switch_row,
            "开启后可编辑进入、退出和执行动作；关闭会清空这三项内容。",
        ).pack(side="left", padx=(5, 0))

        # 卡片二：工程信息（静态展示）
        info_card = self._card()
        self._section_title(info_card, "工程信息")

        info = [
            ("工程名称", "untitled"),
            ("状态数量", ""),
            ("转移数量", ""),
            ("模式", self._style_text()),
        ]
        for k, v in info:
            row = ctk.CTkFrame(info_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=k, width=80, anchor="w").pack(side="left")
            if k == "工程名称":
                # 工程名称可编辑
                self.project_entry = ctk.CTkEntry(row, height=26)
                self.project_entry.insert(0, v)
                self.project_entry.pack(
                    side="left", fill="x", expand=True, padx=(8, 0))
                self.project_entry.bind(
                    "<KeyRelease>", self._on_project_name_changed)
                HelpIcon(
                    row, "当前工程名称，用于标识工程以及后续保存和生成代码。",
                ).pack(side="left", padx=(5, 0))
                continue
            value_label = ctk.CTkLabel(row, text=v, anchor="w")
            value_label.pack(side="left", padx=(8, 0))
            if k == "状态数量":
                self.node_count_label = value_label
            elif k == "转移数量":
                self.trans_count_label = value_label
            elif k == "模式":
                self.style_value_label = value_label
        ctk.CTkFrame(info_card, height=10, fg_color="transparent").pack()

        # 卡片三：标签表
        table_card = self._card()
        self._section_title(table_card, "标签表")
        self._build_table(table_card)

        # 卡片四：事件表（独立滚动，只列唯一事件）
        event_card = self._card()
        self._section_title(event_card, "事件表")
        ctk.CTkButton(
            event_card, text="打开事件-状态矩阵", height=28,
            command=self._open_event_matrix,
        ).pack(fill="x", padx=14, pady=(0, 8))
        self._event_hint = ctk.CTkLabel(
            event_card, text="暂无事件", text_color="gray", anchor="w")
        self._event_hint.pack(fill="x", padx=14, pady=(0, 8))
        self.event_rows = {}
        self.event_rows_box = ctk.CTkScrollableFrame(
            event_card, height=110, fg_color="transparent")
        self.event_rows_box.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkFrame(event_card, height=4, fg_color="transparent").pack()

    # ── 标签表 ───────────────────────────────────────────────
    def _build_table(self, parent):
        """预先建好控件，切换选中时只更新内容，避免每次销毁重建造成闪烁"""
        self._table_obj = (None, None)
        self._edit_key = None   # 当前编辑会话，用于合并撤销点

        self.table_hint = ctk.CTkLabel(
            parent, text="未选中任何对象", text_color="gray", anchor="w",
        )

        self.state_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.name_entry = self._row_entry(
            self.state_frame, "名称",
            "状态的唯一名称；不能为空，也不能与其他状态重名。",
        )
        self.init_menu = self._row_menu(
            self.state_frame, "初始", ["否", "是"], self._commit_initial,
            "指定状态机启动时进入的初始状态；一个工程只能有一个初始状态。",
        )
        self.final_menu = self._row_menu(
            self.state_frame, "最终", ["否", "是"], self._commit_final,
            "将状态标记为最终状态；到达后表示状态机执行结束。一个工程最多一个最终状态。",
        )
        self.in_label = self._row_text(self.state_frame, "入边")
        self.out_label = self._row_text(self.state_frame, "出边")
        # 复合状态：显示所属父状态（拖动或右键「移出父状态」可改变）
        parent_row = ctk.CTkFrame(self.state_frame, fg_color="transparent")
        parent_row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(
            parent_row, text="父状态", width=56, anchor="w").pack(side="left")
        self.parent_label = ctk.CTkLabel(parent_row, text="—", anchor="w")
        self.parent_label.pack(side="left", fill="x", expand=True)
        HelpIcon(
            parent_row,
            "该状态所属的复合状态；把状态拖到另一个状态内部即可成为子状态，拖出或右键可移出。",
        ).pack(side="left", padx=(5, 0))

        # 状态内部动作：进入 / 退出 / 执行（开关在属性面板，多行可折叠）
        self.state_action_box = ctk.CTkFrame(
            self.state_frame, fg_color="transparent")
        self.state_action_entries = {}
        action_helps = {
            "entry": "进入该状态时执行一次的动作。",
            "exit": "离开该状态时执行一次的动作。",
            "do": "处于该状态期间执行的活动，可填写周期性或持续执行逻辑。",
        }
        for kind, text in (("entry", "进入"), ("exit", "退出"), ("do", "执行")):
            box = CollapsibleInput(
                self.state_action_box, text, height=68,
                help_text=action_helps[kind],
            )
            box.pack(fill="x", padx=14, pady=3)
            box.textbox.bind(
                "<KeyRelease>", lambda e, k=kind: self._live_state_action(k))
            box.textbox.bind(
                "<FocusOut>", lambda e, k=kind: self._flush_state_action(k))
            box.textbox.bind(
                "<Control-Return>",
                lambda e, k=kind: self._commit_state_action_ctrl(k))
            self.state_action_entries[kind] = box

        # 内部转移：留在当前状态执行，可添加多条
        self.internal_header = ctk.CTkFrame(
            self.state_frame, fg_color="transparent")
        self.internal_header.pack(fill="x", padx=14, pady=(8, 2))
        ctk.CTkLabel(
            self.internal_header, text="内部转移",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            self.internal_header, text="＋ 添加", width=64, height=24,
            command=self._add_internal,
        ).pack(side="right")
        self.internal_box = ctk.CTkFrame(
            self.state_frame, fg_color="transparent")
        self.internal_box.pack(fill="x")
        self.internal_rows = []
        self._internal_nid = None

        self.trans_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.event_entry = self._row_entry(
            self.trans_frame, "事件名",
            "触发该转移的事件名称。自动转移不需要事件名。",
        )
        self.from_label = self._row_text(self.trans_frame, "起点")
        self.to_label = self._row_text(self.trans_frame, "终点")
        self.style_menu = self._row_menu(
            self.trans_frame, "走线", ["直线", "曲线"], self._commit_style,
            "选择连线的显示方式：直线或曲线；不影响状态机运行逻辑。",
        )
        self.trigger_menu = self._row_menu(
            self.trans_frame, "触发方式", ["事件转移", "自动转移"],
            self._commit_trigger,
            "事件转移由指定事件触发；自动转移无需事件，在条件成立或状态完成后触发。",
        )
        # 优先级：默认按画图顺序，同一状态内不可重复
        self.priority_entry = self._row_entry(
            self.trans_frame, "优先级",
            "同一源状态有多条转移时的检查顺序。使用正整数且不能重复，数值小的优先。",
        )
        self.priority_entry.bind(
            "<Return>", lambda e: self._commit_priority_entry())
        self.priority_entry.bind(
            "<FocusOut>", lambda e: self._commit_priority_entry())

        # 条件输入（开关在属性面板，开启后才显示；多行可折叠）
        self.guard_row = CollapsibleInput(
            self.trans_frame, "守卫条件", height=76,
            help_text="转移发生前必须满足的条件，例如 count > 0。可输入多行，留空表示不限制。",
        )
        self.guard_row.textbox.bind("<KeyRelease>", lambda e: self._live_guard())
        self.guard_row.textbox.bind("<FocusOut>", lambda e: self._flush_guard())
        self.guard_row.textbox.bind(
            "<Control-Return>", lambda e: self._commit_guard_ctrl())

        # 转移动作：事件触发时执行（UML：event [guard] / action）
        self.action_row = CollapsibleInput(
            self.trans_frame, "守卫动作", height=76,
            help_text="转移实际发生时执行的动作，例如 motor_stop()。它属于转移，不是状态的进入或退出动作。",
        )
        self.action_row.textbox.bind("<KeyRelease>", lambda e: self._live_action())
        self.action_row.textbox.bind("<FocusOut>", lambda e: self._flush_action())
        self.action_row.textbox.bind(
            "<Control-Return>", lambda e: self._commit_action_ctrl())

        for entry, handler in (
            (self.name_entry, self._commit_name),
            (self.event_entry, self._commit_event),
        ):
            entry.bind(
                "<Return>",
                lambda e, en=entry, h=handler: self._commit_entry(en, h),
            )
            entry.bind(
                "<FocusOut>",
                lambda e, en=entry, h=handler: self._commit_entry(en, h),
            )

        ctk.CTkFrame(parent, height=10, fg_color="transparent").pack()
        self._refresh_property_table()

    def _row_entry(self, parent, label, help_text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(row, text=label, width=56, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, height=28)
        entry.pack(side="left", fill="x", expand=True)
        HelpIcon(row, help_text).pack(side="left", padx=(5, 0))
        return entry

    def _row_text(self, parent, label):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(row, text=label, width=56, anchor="w").pack(side="left")
        value = ctk.CTkLabel(row, text="-", anchor="w")
        value.pack(side="left", fill="x", expand=True)
        return value

    def _row_menu(self, parent, label, values, command, help_text):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(row, text=label, width=56, anchor="w").pack(side="left")
        menu = ctk.CTkOptionMenu(
            row, values=values, width=110, height=28, command=command,
        )
        menu.pack(side="left", fill="x", expand=True)
        HelpIcon(row, help_text).pack(side="left", padx=(5, 0))
        return menu

    def _refresh_property_table(self):
        canvas = self.canvas
        if canvas is None:
            return
        for widget in (self.table_hint, self.state_frame, self.trans_frame):
            widget.pack_forget()

        trans_ids = getattr(canvas, "selected_transes", set())
        if len(trans_ids) > 1:
            # 多选转移：只显示数量，不显示单条属性
            self.guard_switch_row.pack_forget()
            self.action_switch_row.pack_forget()
            self.state_action_switch_row.pack_forget()
            self.guard_row.pack_forget()
            self.action_row.pack_forget()
            if self.guard_hint.winfo_manager() == "":
                self.guard_hint.pack(fill="x", padx=14, pady=(0, 12))
            self._set_table_obj(("trans-multi", None))
            self.table_hint.configure(
                text=f"已选中 {len(trans_ids)} 条转移，可拖动折点整体移动")
            self.table_hint.pack(fill="x", padx=14, pady=(4, 12))
            return

        tid = canvas.selected_trans
        if tid is not None and tid in canvas.transitions:
            t = canvas.transitions[tid]

            # 属性面板：转移的守卫与动作开关
            self.guard_hint.pack_forget()
            self.state_action_switch_row.pack_forget()
            if self.guard_switch_row.winfo_manager() == "":
                self.guard_switch_row.pack(
                    fill="x", padx=14, pady=(0, 12))
            self.guard_switch_var.set(bool(t.get("guard_on")))
            self._set_textbox(self.guard_row, t.get("guard") or "")

            if self.action_switch_row.winfo_manager() == "":
                self.action_switch_row.pack(
                    fill="x", padx=14, pady=(0, 12))
            self.action_switch_var.set(bool(t.get("action_on")))
            self._set_textbox(self.action_row, t.get("action") or "")

            self._set_table_obj(("trans", tid))
            self._set_entry(self.event_entry, t["event"])
            self.from_label.configure(text=canvas.nodes[t["from"]]["name"])
            self.to_label.configure(text=canvas.nodes[t["to"]]["name"])
            self.style_menu.set("曲线" if t.get("style") == "curve" else "直线")
            is_auto = t.get("trigger") == "auto"
            self.trigger_menu.set("自动转移" if is_auto else "事件转移")
            self.event_entry.configure(
                state="disabled" if is_auto else "normal")
            self._set_entry(self.event_entry, "" if is_auto else t["event"])
            self._set_entry(self.priority_entry, str(t.get("priority", 1)))
            self.trans_frame.pack(fill="x")
            self._update_guard_row()
            self._update_transition_action_row()
            return

        # 没选中转移：隐藏转移相关的开关与输入行
        self.guard_switch_row.pack_forget()
        self.action_switch_row.pack_forget()
        self.guard_row.pack_forget()
        self.action_row.pack_forget()

        if len(canvas.selected_nodes) == 1:
            nid = next(iter(canvas.selected_nodes))
            node = canvas.nodes.get(nid)
            if node:
                # 属性面板：状态内部动作开关
                self.guard_hint.pack_forget()
                acts = node.get("actions") or {}
                self.state_action_switch_var.set(
                    bool(node.get("actions_on")))
                for kind, box in self.state_action_entries.items():
                    self._set_textbox(box, acts.get(kind) or "")
                if self.state_action_switch_row.winfo_manager() == "":
                    self.state_action_switch_row.pack(
                        fill="x", padx=14, pady=(0, 12))

                self._set_table_obj(("node", nid))
                self._set_entry(self.name_entry, node["name"])
                self.init_menu.set("是" if node["is_initial"] else "否")
                self.final_menu.set("是" if node.get("is_final") else "否")
                self.in_label.configure(text=str(sum(
                    1 for x in canvas.transitions.values() if x["to"] == nid)))
                self.out_label.configure(text=str(sum(
                    1 for x in canvas.transitions.values() if x["from"] == nid)))
                pid = canvas.parent_of(nid)
                self.parent_label.configure(
                    text=canvas.nodes[pid]["name"]
                    if pid in canvas.nodes else "—")
                self.state_frame.pack(fill="x")
                self._update_state_action_box()
                self._refresh_internal_rows(nid)
                return

        # 多选 / 空白：隐藏所有开关，恢复提示
        self.state_action_switch_row.pack_forget()
        if self.guard_hint.winfo_manager() == "":
            self.guard_hint.pack(fill="x", padx=14, pady=(0, 12))

        if canvas.selected_nodes:
            self._set_table_obj(("multi", None))
            self.table_hint.configure(
                text=f"已选中 {len(canvas.selected_nodes)} 个状态")
            self.table_hint.pack(fill="x", padx=14, pady=(4, 12))
            return

        self._set_table_obj((None, None))
        self.table_hint.configure(text="未选中任何对象")
        self.table_hint.pack(fill="x", padx=14, pady=(4, 12))

    def _set_table_obj(self, obj):
        """切换标签表对象；保留用户手动设置的展开/收起状态"""
        if obj == self._table_obj:
            return
        self._table_obj = obj
        self._edit_key = None

    # ── 事件表 ───────────────────────────────────────────────
    def _refresh_event_table(self):
        """汇总画布上的唯一事件（按首次出现顺序）"""
        if not hasattr(self, "event_rows"):
            return
        names = []
        seen = set()
        for t in self.canvas.transitions.values():
            name = (t.get("event") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        # 状态内部转移的事件也进入事件表
        for n in self.canvas.nodes.values():
            for item in n.get("internal") or []:
                name = (item.get("event") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)

        for name in list(self.event_rows):
            if name not in seen:
                self.event_rows.pop(name)["frame"].destroy()

        for name in names:
            if name not in self.event_rows:
                self.event_rows[name] = self._make_event_row(name)

        for name in names:
            self._set_entry(self.event_rows[name]["entry"], name)

        if names:
            self._event_hint.pack_forget()
        elif self._event_hint.winfo_manager() == "":
            self._event_hint.pack(fill="x", padx=14, pady=(0, 8))

    def _make_event_row(self, name):
        frame = ctk.CTkFrame(self.event_rows_box, fg_color="transparent")
        frame.pack(fill="x", padx=4, pady=2)
        entry = ctk.CTkEntry(frame, height=26)
        entry.pack(side="left", fill="x", expand=True)
        HelpIcon(
            frame,
            "事件的全局名称。修改后会同步所有普通转移和内部转移，且不能与其他事件重名。",
        ).pack(side="left", padx=(5, 0))
        row = {"frame": frame, "entry": entry, "name": name}
        entry.bind("<Return>", lambda e, r=row: self._rename_event_row(r))
        entry.bind("<FocusOut>", lambda e, r=row: self._rename_event_row(r))
        return row

    def _rename_event_row(self, row):
        """事件表改名：同步所有使用该事件的转移，失败则提示并还原"""
        old = row["name"]
        new = row["entry"].get().strip()
        if new == old:
            return
        if not self.canvas.rename_event(old, new):
            messagebox.showwarning(
                "事件名无效",
                "事件名不能为空，也不能与已有事件重名。",
                parent=self,
            )
            self._set_entry(row["entry"], old)
            return
        self.event_rows.pop(old, None)
        row["name"] = new
        self.event_rows[new] = row
        self._refresh_event_table()

    # ── 事件-状态矩阵 ────────────────────────────────────────
    def _open_event_matrix(self):
        if self.event_matrix is not None and self.event_matrix.winfo_exists():
            self.event_matrix.deiconify()
            self.event_matrix.lift()
            self.event_matrix.refresh()
            return
        self.event_matrix = EventStateMatrix(self, self.canvas)
        self.event_matrix.protocol("WM_DELETE_WINDOW", self._close_event_matrix)

    def _close_event_matrix(self):
        if self.event_matrix is not None:
            self.event_matrix.destroy()
            self.event_matrix = None

    def _refresh_event_matrix(self):
        if self.event_matrix is not None and self.event_matrix.winfo_exists():
            self.event_matrix.refresh()

    @staticmethod
    def _set_entry(entry, value):
        if entry.get() == value:
            return
        # 正在输入时不覆盖用户内容
        try:
            if entry.focus_get() is entry._entry:
                return
        except Exception:
            pass
        entry.delete(0, "end")
        entry.insert(0, value)

    @staticmethod
    def _set_textbox(box, value):
        """回填多行输入框；正在编辑时不覆盖用户内容"""
        if box.get() == value:
            return
        try:
            if box.textbox.focus_get() is box.textbox._textbox:
                return
        except Exception:
            pass
        box.set(value)

    def _commit_entry(self, entry, handler):
        text = entry.get().strip()
        if not handler(text):
            # 提交失败：立刻还原成对象当前的值
            kind, obj_id = self._table_obj
            if kind == "node" and obj_id in self.canvas.nodes:
                value = self.canvas.nodes[obj_id]["name"]
            elif kind == "trans" and obj_id in self.canvas.transitions:
                value = self.canvas.transitions[obj_id]["event"]
            else:
                value = ""
            entry.delete(0, "end")
            entry.insert(0, value)
        self.after(20, self._refresh_property_table)

    def _commit_name(self, text):
        kind, obj_id = self._table_obj
        if kind != "node" or obj_id not in self.canvas.nodes or not text:
            return False
        if not self.canvas.rename_state(obj_id, text):
            self.status_label.configure(text=f"状态名「{text}」已存在")
            return False
        return True

    def _commit_event(self, text):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions or not text:
            return False
        if self.canvas.transitions[obj_id].get("trigger") == "auto":
            return False
        return self.canvas.set_event_name(obj_id, text)

    def _commit_initial(self, value):
        kind, obj_id = self._table_obj
        if kind != "node" or obj_id not in self.canvas.nodes:
            return
        self.canvas.set_initial_state(obj_id, value == "是")

    def _commit_final(self, value):
        kind, obj_id = self._table_obj
        if kind != "node" or obj_id not in self.canvas.nodes:
            return
        self.canvas.set_final_state(obj_id, value == "是")

    def _commit_style(self, value):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        self.canvas.set_transition_style(
            obj_id, "curve" if value == "曲线" else "line",
        )

    # ── 状态内部转移 ─────────────────────────────────────────
    def _refresh_internal_rows(self, nid):
        items = self.canvas.nodes[nid].get("internal") or []
        if self._internal_nid != nid or len(self.internal_rows) != len(items):
            for row in self.internal_rows:
                row["frame"].destroy()
            self.internal_rows = []
            self._internal_nid = nid
            for idx in range(len(items)):
                self.internal_rows.append(self._make_internal_row(idx))
        for idx, item in enumerate(items):
            row = self.internal_rows[idx]
            self._set_entry(row["event"], item.get("event") or "")
            self._set_entry(row["guard"], item.get("guard") or "")
            self._set_textbox(row["action"], item.get("action") or "")
            row["up"].configure(state="normal" if idx > 0 else "disabled")
            row["down"].configure(
                state="normal" if idx < len(items) - 1 else "disabled")

    def _make_internal_row(self, idx):
        frame = ctk.CTkFrame(
            self.internal_box, fg_color="#f5f7fa", corner_radius=6,
            border_width=1, border_color="#e3e6eb",
        )
        frame.pack(fill="x", padx=14, pady=2)
        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkLabel(
            head, text=f"#{idx + 1}", width=22, anchor="w",
            text_color="#666",
        ).pack(side="left")
        # 宽度设小，交给 expand 分配剩余空间，避免把右侧按钮挤出卡片
        event = ctk.CTkEntry(
            head, height=26, width=60, placeholder_text="事件名")
        event.pack(side="left", fill="x", expand=True, padx=(2, 4))
        HelpIcon(
            head,
            "触发该内部转移的事件；处理后仍停留在当前状态，不执行退出和进入动作。",
            bg="#f5f7fa",
        ).pack(side="left", padx=(0, 4))
        up = ctk.CTkButton(head, text="↑", width=24, height=24)
        up.pack(side="left", padx=(0, 2))
        down = ctk.CTkButton(head, text="↓", width=24, height=24)
        down.pack(side="left")
        guard_row = ctk.CTkFrame(frame, fg_color="transparent")
        guard_row.pack(fill="x", padx=8, pady=(2, 0))
        guard = ctk.CTkEntry(
            guard_row, height=26, width=60, placeholder_text="守卫（可空）")
        guard.pack(side="left", fill="x", expand=True)
        HelpIcon(
            guard_row, "内部转移的触发条件；条件成立时才执行对应动作。",
            bg="#f5f7fa",
        ).pack(side="left", padx=(5, 0))

        # 动作与删除按钮同一行：折叠时不留整行空白
        tail = ctk.CTkFrame(frame, fg_color="transparent")
        tail.pack(fill="x", padx=8, pady=(2, 4))
        # 删除按钮先 pack，避免展开动作后宽度被文本框挤掉
        delete = ctk.CTkButton(
            tail, text="删除这条", width=76, height=22,
            fg_color="#e57373", hover_color="#d35b5b",
            command=lambda: self._delete_internal_row(row),
        )
        delete.pack(side="right", padx=(8, 0))
        action = CollapsibleInput(
            tail, "动作", height=56, bg="#f5f7fa",
            help_text="事件和守卫满足时执行的动作；不会发生状态切换。",
        )
        action.pack(side="left", fill="x", expand=True)

        row = {
            "frame": frame, "event": event, "guard": guard,
            "action": action, "up": up, "down": down, "delete": delete,
        }
        up.configure(command=lambda: self._move_internal_row(row, -1))
        down.configure(command=lambda: self._move_internal_row(row, 1))
        for entry, field in ((event, "event"), (guard, "guard")):
            entry.bind(
                "<Return>",
                lambda e, r=row, f=field: self._commit_internal_row(r, f),
            )
            entry.bind(
                "<FocusOut>",
                lambda e, r=row, f=field: self._commit_internal_row(r, f),
            )
        action.textbox.bind(
            "<FocusOut>",
            lambda e, r=row: self._commit_internal_row(r, "action"),
        )
        action.textbox.bind(
            "<Control-Return>",
            lambda e, r=row: self._commit_internal_ctrl(r),
        )
        return row

    def _commit_internal_ctrl(self, row):
        self._commit_internal_row(row, "action")
        return "break"

    def _add_internal(self):
        kind, nid = self._table_obj
        if kind != "node" or nid not in self.canvas.nodes:
            return
        self.canvas.add_internal_transition(nid)
        self._internal_nid = None
        self.after(20, self._refresh_property_table)

    def _commit_internal_row(self, row, field):
        kind, nid = self._table_obj
        if kind != "node" or nid not in self.canvas.nodes:
            return
        try:
            idx = self.internal_rows.index(row)
        except ValueError:
            return
        self.canvas.set_internal_field(nid, idx, field, row[field].get())
        self.after(20, self._refresh_property_table)

    def _delete_internal_row(self, row):
        kind, nid = self._table_obj
        if kind != "node" or nid not in self.canvas.nodes:
            return
        try:
            idx = self.internal_rows.index(row)
        except ValueError:
            return
        self.canvas.delete_internal_transition(nid, idx)
        self._internal_nid = None
        self.after(20, self._refresh_property_table)

    def _move_internal_row(self, row, delta):
        kind, nid = self._table_obj
        if kind != "node" or nid not in self.canvas.nodes:
            return
        try:
            idx = self.internal_rows.index(row)
        except ValueError:
            return
        self.canvas.move_internal_transition(nid, idx, delta)
        self._internal_nid = None
        self.after(20, self._refresh_property_table)

    def _commit_trigger(self, value):
        """切换事件/自动触发；自动转移无需事件名"""
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        auto = value == "自动转移"
        self.canvas.set_transition_trigger(
            obj_id, "auto" if auto else "event")
        if auto and not (
                self.canvas.transitions[obj_id].get("guard") or "").strip():
            self.status_label.configure(
                text="提示：自动转移没有守卫，进入状态后会立即触发")
        self.after(20, self._refresh_property_table)

    def _commit_priority_entry(self):
        """确认优先级：非法或冲突时提示并还原输入"""
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        text = self.priority_entry.get().strip()
        if not self.canvas.set_transition_priority(obj_id, text):
            messagebox.showwarning(
                "优先级无效",
                "优先级必须是正整数，且同一状态下的转移不能使用相同优先级。",
                parent=self,
            )
            self.priority_entry.delete(0, "end")
            self.priority_entry.insert(
                0, str(self.canvas.transitions[obj_id].get("priority", 1)))
            return
        self.after(20, self._refresh_property_table)

    # ── 守卫条件 ─────────────────────────────────────────────
    def _update_guard_row(self):
        if not self.guard_switch_var.get():
            self.guard_row.pack_forget()
            return
        action_visible = self.action_row.winfo_manager() == "pack"
        # 重复 pack 会排到末尾，确保守卫行在动作行之前
        self.guard_row.pack(fill="x", padx=14, pady=(0, 6))
        if action_visible:
            self.action_row.pack_forget()
            self.action_row.pack(fill="x", padx=14, pady=(0, 6))

    def _on_guard_toggle(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        enabled = self.guard_switch_var.get()
        if not enabled:
            # 关闭守卫：清空条件
            self.guard_row.clear()
        # 开关状态写入数据，切换选中后再回来仍保持
        self.canvas.set_guard_enabled(obj_id, enabled)
        self._update_guard_row()
        self.after(20, self._refresh_property_table)

    # ── 实时保存（输入即写回，点击别处不会丢失） ──────────────
    def _start_edit(self, key):
        """一次编辑会话只记录一个撤销点"""
        if self._edit_key == key:
            return
        self._edit_key = key
        self.canvas.push_undo()

    def _live_guard(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        if not self.guard_switch_var.get():
            return
        text = self.canvas.normalize_expr(self.guard_row.get())
        if text == (self.canvas.transitions[obj_id].get("guard") or ""):
            return
        self._start_edit(("trans", obj_id, "guard"))
        self.canvas.set_transition_guard(obj_id, text, record=False)

    def _flush_guard(self):
        self._edit_key = None

    def _commit_guard_ctrl(self):
        self._commit_guard_entry()
        return "break"

    def _commit_guard_entry(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        if not self.guard_switch_var.get():
            return
        self.canvas.set_transition_guard(obj_id, self.guard_row.get())
        self.after(20, self._refresh_property_table)

    # ── 转移动作（事件触发时执行） ────────────────────────────
    def _update_transition_action_row(self):
        if not self.action_switch_var.get():
            self.action_row.pack_forget()
            return
        # 重复 pack 排到末尾，确保位于守卫行之后
        self.action_row.pack(fill="x", padx=14, pady=(0, 6))

    def _on_action_toggle(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        enabled = self.action_switch_var.get()
        if not enabled:
            # 关闭动作：清空转移动作
            self.action_row.clear()
        self.canvas.set_action_enabled(obj_id, enabled)
        self._update_transition_action_row()
        self.after(20, self._refresh_property_table)

    def _live_action(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        if not self.action_switch_var.get():
            return
        text = self.canvas.normalize_expr(self.action_row.get())
        if text == (self.canvas.transitions[obj_id].get("action") or ""):
            return
        self._start_edit(("trans", obj_id, "action"))
        self.canvas.set_transition_action(obj_id, text, record=False)

    def _flush_action(self):
        self._edit_key = None

    def _commit_action_ctrl(self):
        self._commit_action()
        return "break"

    def _commit_action(self):
        kind, obj_id = self._table_obj
        if kind != "trans" or obj_id not in self.canvas.transitions:
            return
        if not self.action_switch_var.get():
            return
        self.canvas.set_transition_action(obj_id, self.action_row.get())
        self.after(20, self._refresh_property_table)

    # ── 状态内部动作（进入 / 退出 / 执行） ────────────────────
    def _update_state_action_box(self):
        if not self.state_action_switch_var.get():
            self.state_action_box.pack_forget()
            return
        # 排在状态信息之后（重复 pack 会移到末尾）
        self.state_action_box.pack(fill="x")

    def _on_state_action_toggle(self):
        kind, obj_id = self._table_obj
        if kind != "node" or obj_id not in self.canvas.nodes:
            return
        enabled = self.state_action_switch_var.get()
        if not enabled:
            # 关闭：清空该状态的全部内部动作
            for box in self.state_action_entries.values():
                box.clear()
        self.canvas.set_state_actions_enabled(obj_id, enabled)
        self._update_state_action_box()
        self.after(20, self._refresh_property_table)

    def _live_state_action(self, kind):
        kind_t, obj_id = self._table_obj
        if kind_t != "node" or obj_id not in self.canvas.nodes:
            return
        if not self.state_action_switch_var.get():
            return
        text = self.canvas.normalize_expr(
            self.state_action_entries[kind].get())
        stored = (self.canvas.nodes[obj_id].get("actions") or {}).get(kind) or ""
        if text == stored:
            return
        self._start_edit(("node", obj_id, kind))
        self.canvas.set_state_action(obj_id, kind, text, record=False)

    def _flush_state_action(self, _kind):
        self._edit_key = None

    def _commit_state_action_ctrl(self, kind):
        self._commit_state_action(kind)
        return "break"

    def _commit_state_action(self, kind):
        kind_t, obj_id = self._table_obj
        if kind_t != "node" or obj_id not in self.canvas.nodes:
            return
        if not self.state_action_switch_var.get():
            return
        self.canvas.set_state_action(
            obj_id, kind, self.state_action_entries[kind].get())
        self.after(20, self._refresh_property_table)

    # ── 底部状态栏 ───────────────────────────────────────────
    def _build_statusbar(self):
        self.statusbar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#e8e8ea")
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.statusbar, text="就绪  |  未保存  |  状态：0  转移：0",
            anchor="w", text_color="#555",
        )
        self.status_label.pack(side="left", padx=12)

        # 右侧：画布缩放
        self.zoom_label = ctk.CTkLabel(
            self.statusbar, text="100%", width=48, anchor="e",
            text_color="#555",
        )
        self.zoom_label.pack(side="right", padx=(4, 10))
        ctk.CTkButton(
            self.statusbar, text="+", width=26, height=20, corner_radius=4,
            fg_color="#d0d4da", hover_color="#bfc4cc", text_color="#333",
            command=lambda: self.canvas.set_zoom(
                self.canvas.zoom * self.canvas.ZOOM_STEP),
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            self.statusbar, text="−", width=26, height=20, corner_radius=4,
            fg_color="#d0d4da", hover_color="#bfc4cc", text_color="#333",
            command=lambda: self.canvas.set_zoom(
                self.canvas.zoom / self.canvas.ZOOM_STEP),
        ).pack(side="right", padx=2)
        ctk.CTkButton(
            self.statusbar, text="重置", width=44, height=20, corner_radius=4,
            fg_color="#d0d4da", hover_color="#bfc4cc", text_color="#333",
            command=lambda: self.canvas.set_zoom(1.0),
        ).pack(side="right", padx=(2, 4))

    def _refresh_zoom_label(self, zoom):
        self.zoom_label.configure(text=f"{round(zoom * 100)}%")

    # ── 工程文件：新建 / 打开 / 保存 ─────────────────────────
    def _project_name(self):
        return self.project_entry.get().strip() or "untitled"

    def _on_project_name_changed(self, _event=None):
        if self._loading:
            return
        doc = self._active_doc()
        if doc is None:
            return
        doc["project_name"] = self._project_name()
        self._mark_active_modified()

    def _set_title(self):
        doc = self._active_doc()
        if doc is None:
            name = ""
        elif doc["path"]:
            name = os.path.basename(doc["path"])
        else:
            name = doc["name"]
        base = "状态机 C 代码生成器"
        self.title(f"{base} - {name}" if name else base)

    def _on_new(self):
        self._on_new_tab()

    def _on_open(self):
        path = filedialog.askopenfilename(
            parent=self, title="打开工程",
            filetypes=[("状态机工程", "*.fsmproj"), ("JSON 文件", "*.json"),
                       ("所有文件", "*.*")],
        )
        if not path:
            return
        # 同一个文件已经打开时直接切换到对应标签
        target = os.path.normcase(os.path.abspath(path))
        for doc in self.docs:
            if doc["path"] and os.path.normcase(
                    os.path.abspath(doc["path"])) == target:
                self._activate_doc(doc)
                return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            canvas_data = data.get("canvas") or {}
            if not isinstance(canvas_data.get("nodes"), list):
                raise ValueError("文件内容不是有效的状态机工程")
        except Exception as exc:
            messagebox.showerror("打开失败", f"无法打开工程：\n{exc}", parent=self)
            return
        project = data.get("project") or {}
        name = os.path.splitext(os.path.basename(path))[0] or "未命名"
        self._create_doc(name, path=path, data=canvas_data, project=project)

    def _on_save(self):
        doc = self._active_doc()
        if doc is None:
            return
        if not doc["path"]:
            return self._on_save_as()
        self._write_project(doc, doc["path"])

    def _on_save_as(self):
        doc = self._active_doc()
        if doc is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="保存工程", defaultextension=".fsmproj",
            initialfile=f"{doc['project_name']}.fsmproj",
            filetypes=[("状态机工程", "*.fsmproj"), ("JSON 文件", "*.json")],
        )
        if not path:
            return
        self._write_project(doc, path)

    def _write_project(self, doc, path):
        data = {
            "app": "cs_state_machine",
            "version": 1,
            "project": {
                "name": doc["project_name"],
                "arch": doc["arch"],
                "level": doc["level"],
            },
            "canvas": doc["canvas"].export_state(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            messagebox.showerror("保存失败", f"无法保存工程：\n{exc}", parent=self)
            return
        doc["path"] = path
        doc["name"] = os.path.splitext(os.path.basename(path))[0] or doc["name"]
        doc["modified"] = False
        self._refresh_tab_title(doc)
        if doc is self._active_doc():
            self.project_path = path
            self._modified = False
            self._set_title()
            self._refresh_status_counts()

    def _on_generate(self):
        self.status_label.configure(text="生成代码")
