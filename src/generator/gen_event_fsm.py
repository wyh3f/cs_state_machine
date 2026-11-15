"""风格 2：FSM 完整版（事件驱动 + 统一入口 + 心跳）

独立模板：不引用极简版生成器的任何渲染逻辑，只共用 base 的工具类型。
"""

from generator.base import (
    GenerationResult, GeneratedFile, is_valid_name, indent_lines,
    sanitize_identifier,
)


def generate_full(canvas_data, project_name):
    """把画布数据生成为事件驱动 FSM 的 C 代码；返回 GenerationResult"""
    result = GenerationResult()
    nodes = list(canvas_data.get("nodes") or [])
    trans = list(canvas_data.get("trans") or [])
    if not nodes:
        result.add_error("画布上没有状态，无法生成代码")
        return result

    nodes_by_id = {n.get("id"): n for n in nodes}
    initials = [n for n in nodes if n.get("is_initial")]
    events = _collect_events(trans, nodes)

    _validate(nodes, trans, nodes_by_id, initials, events, result)
    if not result.ok:
        return result

    project = sanitize_identifier(project_name, fallback="fsm")
    result.files = [
        GeneratedFile(project + "_fsm.h", _render_header(project, nodes, events)),
        GeneratedFile(
            project + "_fsm.c",
            _render_source(project, nodes, trans, nodes_by_id, initials[0], result),
        ),
    ]
    return result


# ── 数据准备 ────────────────────────────────────────────────

def _collect_events(trans, nodes):
    """按首次出现顺序汇总事件名（含内部转移；自动转移不带事件）"""
    events = []
    seen = set()

    def add(name):
        name = (name or "").strip()
        if name and name not in seen:
            seen.add(name)
            events.append(name)

    for t in trans:
        if t.get("trigger") == "auto":
            continue
        add(t.get("event"))
    for n in nodes:
        for item in n.get("internal") or []:
            add(item.get("event"))
    return events


def _priority(t):
    try:
        return int(t.get("priority", 1))
    except (TypeError, ValueError):
        return 1


def _guard(t):
    return (t.get("guard") or "").strip() if t.get("guard_on") else ""


def _action(t):
    return (t.get("action") or "").strip() if t.get("action_on") else ""


def _node_text(node, kind):
    actions = node.get("actions") or {}
    return (actions.get(kind) or "").strip() if node.get("actions_on") else ""


# ── 校验 ────────────────────────────────────────────────────

def _validate(nodes, trans, nodes_by_id, initials, events, result):
    if not initials:
        result.add_error("没有初始状态：请把某个状态标记为初始状态")
    elif len(initials) > 1:
        names = "、".join(n.get("name", "?") for n in initials)
        result.add_error(f"存在多个初始状态：{names}")

    seen = {}
    for n in nodes:
        name = n.get("name", "")
        if not is_valid_name(name):
            result.add_error(
                f"状态名「{name}」不是合法的 C 标识符（字母/数字/下划线，且不能用关键字）")
        if name in seen:
            result.add_error(f"状态名「{name}」重复")
        seen[name] = n
        if n.get("parent"):
            result.add_error(f"状态「{name}」属于复合状态，FSM 完整版不支持层级")

    for name in events:
        if not is_valid_name(name):
            result.add_error(f"事件名「{name}」不是合法的 C 标识符")

    for t in trans:
        if t.get("from") not in nodes_by_id or t.get("to") not in nodes_by_id:
            result.add_error("存在指向不存在状态的转移")
            continue
        event = (t.get("event") or "").strip()
        if t.get("trigger") == "auto":
            if event:
                result.add_error("自动转移不应带事件名")
        elif not event:
            result.add_error("事件转移的事件名为空")

    for n in nodes:
        for item in n.get("internal") or []:
            event = (item.get("event") or "").strip()
            if not event:
                result.add_error(f"状态「{n.get('name')}」的内部转移缺少事件名")
            elif not is_valid_name(event):
                result.add_error(f"内部转移的事件名「{event}」不是合法的 C 标识符")

    _check_priority(nodes, trans, result)
    _check_warnings(nodes, trans, nodes_by_id, initials, result)


def _check_priority(nodes, trans, result):
    used = {n.get("id"): set() for n in nodes}
    for t in trans:
        bucket = used.setdefault(t.get("from"), set())
        value = _priority(t)
        if value in bucket:
            name = _state_name(nodes, t.get("from"))
            result.add_error(f"状态「{name}」内存在重复优先级 {value}")
        bucket.add(value)


def _state_name(nodes, nid):
    for n in nodes:
        if n.get("id") == nid:
            return n.get("name", "?")
    return "?"


def _check_warnings(nodes, trans, nodes_by_id, initials, result):
    targets = {t.get("to") for t in trans}
    initial_ids = {n.get("id") for n in initials}
    for n in nodes:
        if n.get("id") not in targets and n.get("id") not in initial_ids:
            result.add_warning(f"状态「{n.get('name')}」没有入边，永远无法进入")

    # 每个状态内按优先级排序后检查不可达转移
    grouped = {}
    for index, t in enumerate(trans):
        grouped.setdefault(t.get("from"), []).append((index, t))
    for nid, items in grouped.items():
        items.sort(key=lambda pair: (_priority(pair[1]), pair[0]))
        name = _state_name(nodes, nid)
        for pos, (_, t) in enumerate(items):
            event = (t.get("event") or "").strip()
            is_auto = t.get("trigger") == "auto"
            later_same = False
            for _, other in items[pos + 1:]:
                other_event = (other.get("event") or "").strip()
                if (other.get("trigger") == "auto") == is_auto and other_event == event:
                    later_same = True
                    break
            if not later_same or _guard(t):
                continue
            if is_auto:
                result.add_warning(
                    f"状态「{name}」存在无守卫的自动转移，其后的自动转移不可达")
            else:
                result.add_warning(
                    f"状态「{name}」中事件「{event}」有无守卫转移，其后同级转移不可达")

    for n in nodes:
        name = n.get("name")
        internal = n.get("internal") or []
        if not internal:
            continue
        if n.get("is_final"):
            result.add_warning(f"最终状态「{name}」的内部转移不会生效")
            continue
        externals = grouped.get(n.get("id"), [])
        for item in internal:
            event = (item.get("event") or "").strip()
            if not event:
                continue
            if any((t.get("event") or "").strip() == event
                   and t.get("trigger") != "auto" and not _guard(t)
                   for _, t in externals):
                result.add_warning(
                    f"状态「{name}」中事件「{event}」的外部转移无守卫，内部转移不可达")

    for n in nodes:
        name = n.get("name")
        if n.get("is_final"):
            if any(t.get("from") == n.get("id") for t in trans):
                result.add_warning(f"最终状态「{name}」的出边不会生效")
            if _node_text(n, "do"):
                result.add_warning(f"最终状态「{name}」的执行动作不会执行")
            if _node_text(n, "exit"):
                result.add_warning(f"最终状态「{name}」的退出动作不会执行")
        if not n.get("actions_on"):
            actions = n.get("actions") or {}
            if any((actions.get(k) or "").strip() for k in ("entry", "exit", "do")):
                result.add_warning(f"状态「{name}」的动作未开启，内容不会生成")

    for t in trans:
        if t.get("action_on") is False and (t.get("action") or "").strip():
            name = _state_name(nodes, t.get("from"))
            result.add_warning(f"状态「{name}」有一条转移的动作未开启，内容不会生成")
        if t.get("guard_on") is False and (t.get("guard") or "").strip():
            name = _state_name(nodes, t.get("from"))
            result.add_warning(f"状态「{name}」有一条转移的守卫未开启，内容不会生成")


# ── 头文件 ──────────────────────────────────────────────────

def _render_header(project, nodes, events):
    up = project.upper()
    lines = [
        "/*",
        " * 自动生成，请勿手动修改",
        f" * 工程：{project}",
        " * 生成器：完整版（事件驱动）",
        " */",
        f"#ifndef {up}_FSM_H",
        f"#define {up}_FSM_H",
        "",
        "typedef enum {",
    ]
    for n in nodes:
        lines.append(f"    {up}_ST_{n.get('name')},")
    lines.append(f"}} {project}_state_t;")
    lines.append("")

    if events:
        lines.append("typedef enum {")
        for name in events:
            lines.append(f"    {up}_EV_{name},")
        lines.append(f"}} {project}_event_t;")
    else:
        lines.append("typedef enum {")
        lines.append(f"    {up}_EV_NONE")
        lines.append(f"}} {project}_event_t;")

    lines.extend([
        "",
        f"void {project}_init(void);",
        f"void {project}_dispatch({project}_event_t evt);",
        f"void {project}_heartbeat(void);",
        "",
        f"#endif /* {up}_FSM_H */",
        "",
    ])
    return "\n".join(lines)


# ── 源文件 ──────────────────────────────────────────────────

def _render_source(project, nodes, trans, nodes_by_id, initial, result):
    up = project.upper()
    external = {n.get("id"): [] for n in nodes}
    autos = {n.get("id"): [] for n in nodes}
    for index, t in enumerate(trans):
        bucket = autos if t.get("trigger") == "auto" else external
        bucket.setdefault(t.get("from"), []).append((index, t))
    for group in (external, autos):
        for items in group.values():
            items.sort(key=lambda pair: (_priority(pair[1]), pair[0]))

    lines = [
        "/*",
        " * 自动生成，请勿手动修改",
        f" * 工程：{project}",
        " * 生成器：完整版（事件驱动）",
        " */",
        f'#include "{project}_fsm.h"',
        "",
        f"static {project}_state_t {project}_state;",
        f"static int {project}_done;",
        "",
    ]

    _render_prototypes(lines, project, nodes, external, autos)
    _render_state_actions(lines, project, nodes)
    has_leave = any(external.values()) or any(autos.values())
    _render_enter_leave(lines, project, nodes, has_leave)
    _render_state_dispatch(lines, project, up, nodes, external, nodes_by_id,
                           result)
    if any(autos.values()):
        _render_auto_check(lines, project, up, nodes, autos, nodes_by_id,
                           result)
    _render_public(lines, project, up, nodes, external, autos, initial)
    return "\n".join(lines)


def _render_prototypes(lines, project, nodes, external, autos):
    for n in nodes:
        name = n.get("name")
        if _node_text(n, "entry"):
            lines.append(f"static void EN_{name}(void);")
        if _node_text(n, "exit") and not n.get("is_final"):
            lines.append(f"static void EX_{name}(void);")
        if _node_text(n, "do") and not n.get("is_final"):
            lines.append(f"static void DO_{name}(void);")
        if not n.get("is_final") and (external.get(n.get("id")) or n.get("internal")):
            lines.append(f"static void st_{name}({project}_event_t evt);")
    lines.append(f"static void {project}_enter({project}_state_t next);")
    if any(external.values()) or any(autos.values()):
        lines.append(f"static void {project}_leave(void);")
    if any(autos.values()):
        lines.append(f"static int {project}_auto_check(void);")
    lines.append("")


def _render_state_actions(lines, project, nodes):
    for n in nodes:
        name = n.get("name")
        for kind, title in (("entry", "进入"), ("exit", "退出"), ("do", "执行")):
            # 最终状态只执行进入动作，退出和执行动作不会发生
            if kind != "entry" and n.get("is_final"):
                continue
            text = _node_text(n, kind)
            if not text:
                continue
            func = {"entry": "EN", "exit": "EX", "do": "DO"}[kind]
            lines.append(f"static void {func}_{name}(void)")
            lines.append("{")
            lines.append(f"    /* {title}动作 */")
            lines.append(indent_lines(text, "    "))
            lines.append("}")
            lines.append("")


def _render_enter_leave(lines, project, nodes, has_leave):
    up = project.upper()
    entry_states = [n for n in nodes if _node_text(n, "entry")]
    if entry_states:
        lines.append(f"static void {project}_enter({project}_state_t next)")
        lines.append("{")
        lines.append(f"    {project}_state = next;")
        lines.append("    switch (next) {")
        for n in entry_states:
            lines.append(f"    case {up}_ST_{n.get('name')}:")
            lines.append(f"        EN_{n.get('name')}();")
            lines.append("        break;")
        lines.append("    default:")
        lines.append("        break;")
        lines.append("    }")
        finals = [n for n in nodes if n.get("is_final")]
        for n in finals:
            lines.append(f"    if (next == {up}_ST_{n.get('name')}) {{")
            lines.append(f"        {project}_done = 1;")
            lines.append("    }")
        lines.append("}")
    else:
        lines.append(f"static void {project}_enter({project}_state_t next)")
        lines.append("{")
        lines.append(f"    {project}_state = next;")
        finals = [n for n in nodes if n.get("is_final")]
        for n in finals:
            lines.append(f"    if (next == {up}_ST_{n.get('name')}) {{")
            lines.append(f"        {project}_done = 1;")
            lines.append("    }")
        lines.append("}")
    lines.append("")

    exit_states = [n for n in nodes if _node_text(n, "exit") and not n.get("is_final")]
    if not has_leave:
        return
    lines.append(f"static void {project}_leave(void)")
    lines.append("{")
    if exit_states:
        lines.append(f"    switch ({project}_state) {{")
        for n in exit_states:
            lines.append(f"    case {up}_ST_{n.get('name')}:")
            lines.append(f"        EX_{n.get('name')}();")
            lines.append("        break;")
        lines.append("    default:")
        lines.append("        break;")
        lines.append("    }")
    lines.append("}")
    lines.append("")


def _render_state_dispatch(lines, project, up, nodes, external, nodes_by_id,
                           result):
    for n in nodes:
        if n.get("is_final"):
            continue
        items = external.get(n.get("id")) or []
        internal = n.get("internal") or []
        if not items and not internal:
            continue
        name = n.get("name")
        lines.append(f"static void st_{name}({project}_event_t evt)")
        lines.append("{")
        body = 0
        saturated = set()
        for _, t in items:
            event = (t.get("event") or "").strip()
            if event in saturated:
                continue
            guard = " ".join(_guard(t).split())
            action = _action(t)
            target = nodes_by_id[t.get("to")].get("name")
            cond = f"evt == {up}_EV_{event}"
            if guard:
                lines.append(f"    if ({cond} && ({guard})) {{")
            else:
                lines.append(f"    if ({cond}) {{")
            if action:
                lines.append(indent_lines(action, "        "))
            lines.append(f"        {project}_leave();")
            lines.append(f"        {project}_enter({up}_ST_{target});")
            lines.append("        return;")
            lines.append("    }")
            body += 1
            if not guard:
                saturated.add(event)

        for item in internal:
            event = (item.get("event") or "").strip()
            if not event or event in saturated:
                continue
            guard = " ".join((item.get("guard") or "").split())
            action = (item.get("action") or "").strip()
            cond = f"evt == {up}_EV_{event}"
            if guard:
                lines.append(f"    if ({cond} && ({guard})) {{")
            else:
                lines.append(f"    if ({cond}) {{")
            if action:
                lines.append(indent_lines(action, "        "))
            lines.append("        return;")
            lines.append("    }")
            body += 1
            if not guard:
                saturated.add(event)

        if not body:
            lines.append("    (void)evt;")
        lines.append("}")
        lines.append("")


def _render_auto_check(lines, project, up, nodes, autos, nodes_by_id, result):
    lines.append(f"static int {project}_auto_check(void)")
    lines.append("{")
    lines.append(f"    switch ({project}_state) {{")
    for n in nodes:
        items = autos.get(n.get("id")) or []
        if not items:
            continue
        name = n.get("name")
        lines.append(f"    case {up}_ST_{name}:")
        saturated = False
        for _, t in items:
            guard = " ".join(_guard(t).split())
            action = _action(t)
            target = nodes_by_id[t.get("to")].get("name")
            if guard:
                lines.append(f"        if ({guard}) {{")
            else:
                lines.append("        {")
            if action:
                lines.append(indent_lines(action, "            "))
            lines.append(f"            {project}_leave();")
            lines.append(f"            {project}_enter({up}_ST_{target});")
            lines.append("            return 1;")
            lines.append("        }")
            if not guard:
                break
        lines.append("        break;")
    lines.append("    default:")
    lines.append("        break;")
    lines.append("    }")
    lines.append("    return 0;")
    lines.append("}")
    lines.append("")


def _render_public(lines, project, up, nodes, external, autos, initial):
    lines.append(f"void {project}_init(void)")
    lines.append("{")
    lines.append(f"    {project}_done = 0;")
    lines.append(f"    {project}_enter({up}_ST_{initial.get('name')});")
    lines.append("}")
    lines.append("")

    dispatch_states = [
        n for n in nodes
        if not n.get("is_final")
        and ((external.get(n.get("id")) or []) or n.get("internal"))
    ]
    lines.append(f"void {project}_dispatch({project}_event_t evt)")
    lines.append("{")
    lines.append(f"    if ({project}_done) {{")
    lines.append("        return;")
    lines.append("    }")
    if dispatch_states:
        lines.append(f"    switch ({project}_state) {{")
        for n in dispatch_states:
            lines.append(f"    case {up}_ST_{n.get('name')}:")
            lines.append(f"        st_{n.get('name')}(evt);")
            lines.append("        break;")
        lines.append("    default:")
        lines.append("        break;")
        lines.append("    }")
    else:
        lines.append("    (void)evt;")
    lines.append("}")
    lines.append("")

    do_states = [n for n in nodes if _node_text(n, "do") and not n.get("is_final")]
    has_auto = any(autos.values())
    lines.append(f"void {project}_heartbeat(void)")
    lines.append("{")
    lines.append(f"    if ({project}_done) {{")
    lines.append("        return;")
    lines.append("    }")
    if do_states:
        lines.append(f"    switch ({project}_state) {{")
        for n in do_states:
            lines.append(f"    case {up}_ST_{n.get('name')}:")
            lines.append(f"        DO_{n.get('name')}();")
            lines.append("        break;")
        lines.append("    default:")
        lines.append("        break;")
        lines.append("    }")
    if has_auto:
        lines.append(f"    {project}_auto_check();")
    lines.append("}")
    lines.append("")
