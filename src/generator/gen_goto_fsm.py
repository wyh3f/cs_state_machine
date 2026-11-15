"""风格 1：极简 FSM（goto + 自研宏）

基于参考仓库 rdentato/fsm 的思路修改：保留 goto 结构与防 fall-through 语义，
新增 fsm_begin(state) 以支持任意名称的初始状态。生成代码零依赖、可直接编译。
"""

from generator.base import (
    GenerationResult, GeneratedFile, is_valid_name, indent_lines,
    sanitize_identifier,
)

# 生成到目标工程的宏头文件；基于 MIT 许可的 rdentato/fsm 修改
FSM_HEADER = """\
/*
 * 极简 goto 状态机宏（自动生成，请勿手动修改）
 *
 * 基于 rdentato/fsm 修改（https://repo.dentato.com/fsm）：
 *   1. 新增 fsm_begin(state)，允许任意名称的初始状态（原版固定为 START）
 *   2. 保留原有的 goto 结构与防 fall-through 语义
 *
 * MIT License
 *
 * Copyright (c) 2025 Remo Dentato
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
#ifndef CSM_FSM_H
#define CSM_FSM_H

#define CSM_FSM_VERSION 0x00010000

/* 进入状态机：跳到指定初始状态，同时定义退出标签 */
#define fsm_begin(s)  if (1) { goto fsm_state_ ## s; fsm_exit: ; } else

/* 定义一个状态；顺序流入、break 或 continue 都会退出整个状态机 */
#define fsmstate(s)   for(;;) for(;;) if (1) goto fsm_exit; else fsm_state_ ## s:

/* 跳转到另一个状态 */
#define fsmgoto(s)    goto fsm_state_ ## s

/* 退出状态机 */
#define fsmexit       goto fsm_exit

#endif /* CSM_FSM_H */
"""


def generate_lite(canvas_data, project_name):
    """把画布数据生成为极简 FSM 的 C 代码；返回 GenerationResult"""
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
    source = _render_source(project, nodes, trans, nodes_by_id, initials[0], result)
    header = project + "_fsm.h"
    result.files = [
        GeneratedFile(header, FSM_HEADER),
        GeneratedFile(project + "_fsm.c", source),
    ]
    return result


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
            result.add_error(f"状态「{name}」属于复合状态，极简版不支持层级结构")
        if n.get("internal"):
            result.add_error(f"状态「{name}」存在内部转移，极简版不支持")

    for t in trans:
        if t.get("trigger") == "auto":
            result.add_error("存在自动转移，极简版不支持（请在完整版中改为事件转移）")
        if t.get("from") not in nodes_by_id or t.get("to") not in nodes_by_id:
            result.add_error("存在指向不存在状态的转移")


def _render_source(project, nodes, trans, nodes_by_id, initial, result):
    # 每个状态挂上自己的出边，按优先级升序（同优先级保持创建顺序）
    outgoing = {n.get("id"): [] for n in nodes}
    for index, t in enumerate(trans):
        outgoing.setdefault(t.get("from"), []).append((index, t))
    for items in outgoing.values():
        items.sort(key=lambda pair: (_priority(pair[1]), pair[0]))

    lines = []
    lines.append("/*")
    lines.append(" * 自动生成，请勿手动修改")
    lines.append(f" * 工程：{project}")
    lines.append(" * 生成器：极简版（goto 风格）")
    lines.append(" */")
    lines.append(f'#include "{project}_fsm.h"')
    lines.append("")
    lines.append(f"void {project}_run(void)")
    lines.append("{")
    lines.append("    /* 用户变量可在此处声明，例如：static int count = 0; */")
    lines.append(f"    fsm_begin({initial.get('name')}) {{")

    # 初始状态排第一，其余按画布创建顺序，便于阅读
    ordered = [initial] + [n for n in nodes if n is not initial]
    for node in ordered:
        _render_state(lines, node, outgoing.get(node.get("id"), []),
                      nodes_by_id, result)

    lines.append("    }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _render_state(lines, node, items, nodes_by_id, result):
    name = node.get("name")
    actions = node.get("actions") or {}
    # 执行动作只有开关开启且内容非空时才生成
    do_text = (actions.get("do") or "").strip() if node.get("actions_on") else ""
    if not node.get("actions_on") and (actions.get("do") or "").strip():
        result.add_warning(
            f"状态「{name}」的执行动作未开启，内容不会生成")
    if node.get("is_final"):
        if items:
            result.add_warning(f"最终状态「{name}」的出边已忽略")
        if do_text:
            result.add_warning(f"最终状态「{name}」的执行动作已忽略")
        lines.append(f"        fsmstate({name}) {{            /* 最终状态 */")
        lines.append("            fsmexit;")
        lines.append("        }")
        lines.append("")
        return

    if node.get("actions_on") and (actions.get("entry") or "").strip():
        result.add_warning(f"状态「{name}」的进入动作未生成（极简版不支持）")
    if node.get("actions_on") and (actions.get("exit") or "").strip():
        result.add_warning(f"状态「{name}」的退出动作未生成（极简版不支持）")

    lines.append(f"        fsmstate({name}) {{")
    if do_text:
        if not items:
            result.add_warning(
                f"状态「{name}」有执行动作但没有出边，将在此永久循环")
        lines.append("            for (;;) {")
        lines.append(indent_lines(do_text, "                "))
        _render_transitions(lines, name, items, nodes_by_id, result,
                            "                ")
        lines.append("            }")
    else:
        _render_transitions(lines, name, items, nodes_by_id, result,
                            "            ")
        if not items:
            lines.append("            /* 没有出边：直接退出状态机 */")
        lines.append("            fsmexit;")
    lines.append("        }")
    lines.append("")


def _render_transitions(lines, state_name, items, nodes_by_id, result, pad):
    for position, (_, t) in enumerate(items):
        target = nodes_by_id[t.get("to")].get("name")
        event = (t.get("event") or "").strip()
        comment = f"  /* {event} */" if event else ""
        guard = (t.get("guard") or "").strip() if t.get("guard_on") else ""
        action = (t.get("action") or "").strip() if t.get("action_on") else ""

        if t.get("guard_on") and not guard:
            result.add_warning(f"状态「{state_name}」有一条转移开启了守卫但内容为空")
        if t.get("action_on") and not action:
            result.add_warning(f"状态「{state_name}」有一条转移开启了动作但内容为空")
        if not t.get("action_on") and (t.get("action") or "").strip():
            result.add_warning(
                f"状态「{state_name}」有一条转移的动作未开启，内容不会生成")

        if not guard:
            if position < len(items) - 1:
                result.add_warning(
                    f"状态「{state_name}」的无守卫转移之后的转移不可达")
            if action:
                lines.append(f"{pad}/* 无条件转移{comment} */")
                lines.append(indent_lines(action, pad))
                lines.append(f"{pad}fsmgoto({target});")
            else:
                lines.append(f"{pad}fsmgoto({target});{comment}")
            return

        single_guard = " ".join(guard.split())
        if action:
            lines.append(f"{pad}if ({single_guard}) {{{comment}")
            lines.append(indent_lines(action, pad + "    "))
            lines.append(f"{pad}    fsmgoto({target});")
            lines.append(f"{pad}}}")
        else:
            lines.append(f"{pad}if ({single_guard}) {{ fsmgoto({target}); }}{comment}")


def _priority(t):
    try:
        return int(t.get("priority", 1))
    except (TypeError, ValueError):
        return 1
