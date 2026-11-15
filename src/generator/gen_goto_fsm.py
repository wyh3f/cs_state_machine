"""风格 1：极简 FSM（单步推进）

每次调用只执行当前状态一次：跑执行动作、检查转移、切换后立即返回。
生成代码不含任何循环，不会阻塞调用方。
"""

from generator.base import (
    GenerationResult, GeneratedFile, is_valid_name, indent_lines,
    sanitize_identifier,
)


def generate_lite(canvas_data, project_name):
    """把画布数据生成为单步推进的 C 代码；返回 GenerationResult"""
    result = GenerationResult()
    nodes = list(canvas_data.get("nodes") or [])
    trans = list(canvas_data.get("trans") or [])
    if not nodes:
        result.add_error("画布上没有状态，无法生成代码")
        return result

    nodes_by_id = {n.get("id"): n for n in nodes}
    initials = [n for n in nodes if n.get("is_initial")]

    _validate(nodes, trans, nodes_by_id, initials, result)
    if not result.ok:
        return result

    project = sanitize_identifier(project_name, fallback="fsm")
    result.files = [
        GeneratedFile(project + "_fsm.h", _render_header(project)),
        GeneratedFile(
            project + "_fsm.c",
            _render_source(project, nodes, trans, nodes_by_id, initials[0],
                           result),
        ),
    ]
    return result


# ── 数据准备 ────────────────────────────────────────────────

def _priority(t):
    try:
        return int(t.get("priority", 1))
    except (TypeError, ValueError):
        return 1


def _guard(t):
    return (t.get("guard") or "").strip() if t.get("guard_on") else ""


def _action(t):
    return (t.get("action") or "").strip() if t.get("action_on") else ""


def _do_text(node):
    actions = node.get("actions") or {}
    return (actions.get("do") or "").strip() if node.get("actions_on") else ""


# ── 校验 ────────────────────────────────────────────────────

def _validate(nodes, trans, nodes_by_id, initials, result):
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
            result.add_error(f"状态「{name}」属于复合状态，极简版不支持层级")
        if n.get("internal"):
            result.add_error(f"状态「{name}」存在内部转移，极简版不支持")

    for t in trans:
        if t.get("trigger") == "auto":
            result.add_error("存在自动转移，极简版不支持（请改用完整版）")
        if t.get("from") not in nodes_by_id or t.get("to") not in nodes_by_id:
            result.add_error("存在指向不存在状态的转移")

    _check_warnings(nodes, trans, result)


def _state_name(nodes, nid):
    for n in nodes:
        if n.get("id") == nid:
            return n.get("name", "?")
    return "?"


def _check_warnings(nodes, trans, result):
    targets = {t.get("to") for t in trans}
    initial_ids = {n.get("id") for n in nodes if n.get("is_initial")}
    for n in nodes:
        if n.get("id") not in targets and n.get("id") not in initial_ids:
            result.add_warning(f"状态「{n.get('name')}」没有入边，永远无法进入")

    grouped = {}
    for index, t in enumerate(trans):
        grouped.setdefault(t.get("from"), []).append((index, t))
    for nid, items in grouped.items():
        items.sort(key=lambda pair: (_priority(pair[1]), pair[0]))
        name = _state_name(nodes, nid)
        for pos, (_, t) in enumerate(items):
            if pos < len(items) - 1 and not _guard(t):
                result.add_warning(
                    f"状态「{name}」有无守卫转移，其后的转移不可达")
                break

    for n in nodes:
        name = n.get("name")
        if n.get("is_final"):
            if any(t.get("from") == n.get("id") for t in trans):
                result.add_warning(f"最终状态「{name}」的出边不会生效")
            if _do_text(n):
                result.add_warning(f"最终状态「{name}」的执行动作不会执行")
        if n.get("actions_on"):
            actions = n.get("actions") or {}
            if (actions.get("entry") or "").strip():
                result.add_warning(f"状态「{name}」的进入动作未生成（极简版不支持）")
            if (actions.get("exit") or "").strip():
                result.add_warning(f"状态「{name}」的退出动作未生成（极简版不支持）")
        else:
            actions = n.get("actions") or {}
            if any((actions.get(k) or "").strip() for k in ("entry", "exit", "do")):
                result.add_warning(f"状态「{name}」的动作未开启，内容不会生成")

    for t in trans:
        name = _state_name(nodes, t.get("from"))
        if t.get("guard_on") is False and (t.get("guard") or "").strip():
            result.add_warning(f"状态「{name}」有一条转移的守卫未开启，内容不会生成")
        if t.get("action_on") is False and (t.get("action") or "").strip():
            result.add_warning(f"状态「{name}」有一条转移的动作未开启，内容不会生成")


# ── 头文件 ──────────────────────────────────────────────────

def _render_header(project):
    up = project.upper()
    return "\n".join([
        "/*",
        " * 自动生成，请勿手动修改",
        f" * 工程：{project}",
        " * 生成器：极简版（单步推进）",
        " */",
        f"#ifndef {up}_FSM_H",
        f"#define {up}_FSM_H",
        "",
        f"void {project}_run(void);",
        "",
        f"#endif /* {up}_FSM_H */",
        "",
    ])


# ── 源文件 ──────────────────────────────────────────────────

def _render_source(project, nodes, trans, nodes_by_id, initial, result):
    up = project.upper()
    grouped = {n.get("id"): [] for n in nodes}
    for index, t in enumerate(trans):
        grouped.setdefault(t.get("from"), []).append((index, t))
    for items in grouped.values():
        items.sort(key=lambda pair: (_priority(pair[1]), pair[0]))

    lines = [
        "/*",
        " * 自动生成，请勿手动修改",
        f" * 工程：{project}",
        " * 生成器：极简版（单步推进，无循环）",
        " */",
        f'#include "{project}_fsm.h"',
        "",
        "typedef enum {",
    ]
    for n in nodes:
        lines.append(f"    {up}_ST_{n.get('name')},")
    lines.append(f"}} {project}_state_t;")
    lines.append("")
    lines.append(
        f"static {project}_state_t {project}_state = "
        f"{up}_ST_{initial.get('name')};")
    lines.append("")

    lines.append(f"void {project}_run(void)")
    lines.append("{")
    lines.append(f"    switch ({project}_state) {{")
    for n in nodes:
        name = n.get("name")
        lines.append(f"    case {up}_ST_{name}:")
        lines.append(f"        goto st_{name};")
    lines.append("    default:")
    lines.append("        return;")
    lines.append("    }")
    lines.append("")
    lines.append("    return;")
    lines.append("")

    for n in nodes:
        _render_state(lines, project, up, n, grouped.get(n.get("id")) or [],
                      nodes_by_id, result)

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _render_state(lines, project, up, node, items, nodes_by_id, result):
    name = node.get("name")
    lines.append(f"st_{name}:")
    if node.get("is_final"):
        lines.append("    /* 最终状态：不再推进 */")
        lines.append("    return;")
        lines.append("")
        return
    do_text = _do_text(node)
    if do_text:
        lines.append("    /* 执行动作 */")
        lines.append(indent_lines(do_text, "    "))
    if not items:
        lines.append("    /* 没有出边：保持当前状态 */")
        lines.append("    return;")
        lines.append("")
        return

    emitted = 0
    for _, t in items:
        event = (t.get("event") or "").strip()
        guard = " ".join(_guard(t).split())
        action = _action(t)
        target = nodes_by_id[t.get("to")].get("name")
        comment = f"  /* {event} */" if event else ""
        if guard:
            lines.append(f"    if ({guard}) {{{comment}")
            if action:
                lines.append(indent_lines(action, "        "))
            lines.append(f"        {project}_state = {up}_ST_{target};")
            lines.append("        return;")
            lines.append("    }")
            emitted += 1
        else:
            lines.append(f"    /* 无条件转移{comment} */")
            if action:
                lines.append(indent_lines(action, "    "))
            lines.append(f"    {project}_state = {up}_ST_{target};")
            lines.append("    return;")
            emitted += 1
            break
    lines.append("    /* 没有转移成立：保持当前状态 */")
    lines.append("    return;")
    lines.append("")
