# AI 编程建议 — cs_state_machine

> 本文档记录项目的软件分层和目录结构，AI 编程助手在后续生成代码时必须严格遵守。

---

## 一、软件分层

```
┌─────────────────────────────────────┐
│           ① GUI 层（customtkinter）    │
│   主窗口 + 画布 + 属性面板 + 工具栏     │
├─────────────────────────────────────┤
│        ② 画布交互层（tk.Canvas 封装）   │
│   状态节点拖拽 / 箭头绘制 / 选中删除    │
├─────────────────────────────────────┤
│          ③ 数据模型层（纯 Python）      │
│   状态 / 转移 / 事件 / 层级关系         │
├─────────────────────────────────────┤
│         ④ 存储层（自动保存 JSON）       │
│   model → JSON 读写                   │
├─────────────────────────────────────┤
│         ⑤ 代码生成层（4 种风格）        │
│   遍历 model → 按模板生成 .c / .h     │
└─────────────────────────────────────┘
```

### 分层原则

- **上一层可以依赖下一层，下一层完全不知道上一层存在**
- GUI 层（①）只操作数据模型层（③），不知道存储和生成的实现细节
- 代码生成层（⑤）只需要数据模型层（③），不知道 GUI 的存在
- 各层之间只通过参数和返回值交互，不直接修改其他层的内部逻辑

---

## 二、目录结构

```
cs_state_machine/
│
├── src/
│   ├── app.py                      # 入口：创建 CTk + 启动主窗口
│   │
│   ├── gui/                        # ① GUI 层
│   │   ├── main_window.py          # 主窗口（CTk frame 布局）
│   │   └── panels.py               # 属性面板 + 工具栏（右侧/顶部 CTk 组件）
│   │
│   ├── canvas_widget.py            # ② 画布交互层（单文件封装 tk.Canvas）
│   │                               #   - 状态节点的绘制、拖拽、选中
│   │                               #   - 箭头的绘制、点击
│   │                               #   - 网格背景、连线高亮
│   │
│   ├── model/                      # ③ 数据模型层（纯 dataclass 或普通类）
│   │   ├── node.py                 # StateNode：id, name, x, y, parent_id, is_initial, entries, exits
│   │   ├── transition.py           # Transition：id, from_id, to_id, event_id, conditions[], action, priority
│   │   ├── event.py                # Event：id, name, has_data
│   │   └── machine.py              # StateMachine：nodes[], transitions[], events[], style（顶层聚合）
│   │
│   ├── storage.py                  # ④ 存储层（单文件）
│   │                               #   - save(project_path, machine) → JSON
│   │                               #   - load(project_path) → StateMachine
│   │                               #   - 每次 model 变化自动调 save
│   │
│   └── generator/                  # ⑤ 代码生成层（每个风格一个文件）
│       ├── base.py                 # 基类/接口：generate(machine) → (.c, .h)
│       ├── gen_goto_fsm.py         # 风格 1：极简 FSM（rdentato/fsm 思路 → 纯 goto + 宏）
│       ├── gen_event_fsm.py        # 风格 2：功能完整 FSM（endurodave 思路 → 事件驱动 + 转移表）
│       ├── gen_hsm.py              # 风格 3：极简 HSM（Ye-Zenghui/hsm 思路 → 事件上抛 + 父子状态）
│       └── gen_uml_hsm.py          # 风格 4：完整 UML HSM（ufsm 思路 → LCA + history + Fork/Join）
│
├── assets/
│   └── icon.ico                    # 程序图标
│
├── cs_state_machine.spec           # PyInstaller 打包配置
├── cs_state_machine.manifest       # DPI 声明
├── version_info.txt                # FileVersion / ProductName
├── requirements.txt                # customtkinter
├── .gitignore
└── AI编程建议.md                    # 本文档
```

---

## 三、参考代码清单（学习用，不直接复用）

以下仓库是设计思路参考，生成的 C 代码不包含它们的任何 copyrighted 代码：

| 风格 | 参考仓库 | 参考路径 |
| --- | --- | --- |
| 极简 FSM（goto + 宏） | rdentato/fsm | `C代码参考/状态机/fsm` |
| 功能完整 FSM（事件驱动 + 转移表 + Guard/Entry/Exit） | endurodave/C_StateMachine | `C代码参考/状态机/endurodave_C_StateMachine` |
| 极简 HSM（事件上抛 + 父子状态） | Ye-Zenghui/hsm | `C代码参考/状态机/Ye-Zenghui_hsm` |
| 完整 UML HSM（LCA + history + Fork/Join） | elcritch/ufsm | `C代码参考/状态机/ufsm` |

---

## 四、4 种状态机风格核心差异

| 维度 | gen_goto_fsm | gen_event_fsm | gen_hsm | gen_uml_hsm |
| --- | --- | --- | --- | --- |
| 类型 | 扁平 FSM | 扁平 FSM | HSM（嵌套） | 完整 UML HSM |
| 核心机制 | goto + 宏 | 事件驱动 + 转移表 | 事件上抛 + parent 指针 | LCA + 结构体数组 |
| 状态存储 | CPU PC | 枚举变量 | 枚举变量 | 运行时 struct 链表 |
| 转移条件在哪 | 状态代码里的 if | 事件函数里的转移表 | 状态 handler 里的 switch-case | struct 里的 guard 函数 |
| Guard/Entry/Exit | ❌ | ✅ | ❌（通过 HSM_ENTRY_SIG 实现） | ✅ |
| 嵌套状态 | ❌ | ❌ | ✅ | ✅ + 并行区域 |
| 历史状态 | ❌ | ❌ | ❌ | ✅ 浅/深历史 |
| 需要运行时引擎 | ❌ | ❌ | ❌ | ✅ 必须 |
| 51 单片机 Flash | 最小 | 小 | 极小 | 较大（几 KB） |
| 对代码生成器友好度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
