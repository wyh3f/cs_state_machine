"""
视觉检测 — 对窗口截图做多维度像素断言
输入：capture_window.py 生成的整窗截图（不含桌面其它内容）
输出：逐项 PASS/FAIL + 退出码，另支持与基准图做 MSE 回归对比

分区按比例划分，兼容不同 DPI 缩放下的控件尺寸变化
"""
import argparse
import os
import shutil
import sys
from collections import deque

from PIL import Image, ImageChops


# ── 颜色常量（实测自真实截图） ─────────────────────────────
BLUE = (59, 142, 208)        # 按钮 / 节点边框 #3b8ed0
NODE_FILL = (232, 240, 254)  # 节点填充 #e8f0fe
INIT_FILL = (230, 247, 234)  # 初始状态节点填充 #e6f7ea
WHITE = (255, 255, 255)      # 画布底色
ARROW = (102, 102, 102)      # 连线 #666666
PANEL = (245, 245, 247)      # 右侧属性面板 #f5f5f7
STATUSBAR = (232, 232, 234)  # 状态栏 #e8e8ea
GREEN = (46, 125, 50)        # 初始状态标记 #2e7d32


def near(rgb, target, tol):
    return (abs(rgb[0] - target[0]) <= tol
            and abs(rgb[1] - target[1]) <= tol
            and abs(rgb[2] - target[2]) <= tol)


def color_ratio(img, target, tol):
    """目标颜色像素占比"""
    px = img.load()
    w, h = img.size
    hit = 0
    for y in range(h):
        for x in range(w):
            if near(px[x, y], target, tol):
                hit += 1
    return hit / float(w * h) if w * h else 0.0


def color_count(img, target, tol):
    px = img.load()
    w, h = img.size
    hit = 0
    for y in range(h):
        for x in range(w):
            if near(px[x, y], target, tol):
                hit += 1
    return hit


def gray_std(img):
    """灰度标准差，判断是否空白/黑屏"""
    g = img.convert("L").resize((160, 160))
    data = list(g.tobytes())
    mean = sum(data) / len(data)
    return (sum((v - mean) ** 2 for v in data) / len(data)) ** 0.5


def fill_regions(img, targets, tol, min_area=800):
    """统计目标颜色的连通区域（面积过滤），用于数状态框个数
    targets 既可以是单个 RGB 元组，也可以是 RGB 元组列表"""
    if isinstance(targets[0], int):
        targets = [targets]
    px = img.load()
    w, h = img.size
    mask = bytearray(w * h)
    for y in range(h):
        base = y * w
        for x in range(w):
            rgb = px[x, y]
            if any(near(rgb, t, tol) for t in targets):
                mask[base + x] = 1

    seen = bytearray(w * h)
    areas = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not mask[i] or seen[i]:
                continue
            q = deque([i])
            seen[i] = 1
            area = 0
            while q:
                cur = q.popleft()
                area += 1
                cy, cx = divmod(cur, w)
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w:
                        ni = ny * w + nx
                        if mask[ni] and not seen[ni]:
                            seen[ni] = 1
                            q.append(ni)
            if area >= min_area:
                areas.append(area)
    return sorted(areas, reverse=True)


def mse(a, b):
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    data = diff.tobytes()  # 逐通道字节，直接平方求均值
    return sum(v * v for v in data) / len(data)


def check(shot, golden=None, write_golden=False):
    img = Image.open(shot).convert("RGB")
    w, h = img.size

    # 比例分区
    tb_h = int(h * 0.07)                     # 顶部工具栏
    sb_top = h - int(h * 0.05)               # 底部状态栏
    panel_left = int(w * 0.78)               # 右侧属性面板
    canvas_left = int(w * 0.09)              # 左侧组件栏（约占 9%，卡片也是 NODE_FILL 色）
    body = img.crop((canvas_left, tb_h, panel_left, sb_top))
    toolbar = img.crop((0, 0, w, tb_h))
    statusbar = img.crop((0, sb_top, w, h))
    panel = img.crop((panel_left, tb_h, w, sb_top))
    canvas = body

    rows = []
    failures = []

    def add(name, ok, detail, hard=True):
        rows.append(("PASS" if ok else ("FAIL" if hard else "WARN"), name, detail))
        if not ok and hard:
            failures.append(name)

    # 1 非空
    std = gray_std(img)
    add("窗口非空白", std > 5.0, f"灰度标准差 {std:.1f} > 5.0")

    # 2 工具栏按钮（蓝色）
    tb_blue = color_ratio(toolbar, BLUE, 22)
    add("工具栏按钮存在", tb_blue > 0.04, f"按钮蓝占比 {tb_blue*100:.1f}% > 4%")

    # 3 画布白底
    canvas_white = color_ratio(canvas, WHITE, 4)
    add("画布白底", canvas_white > 0.50, f"白色占比 {canvas_white*100:.1f}% > 50%")

    # 4 状态框数量（连通区域，普通填充 + 初始状态填充）
    regions = fill_regions(body, [NODE_FILL, INIT_FILL], 6)
    add("状态框数量 = 4", len(regions) == 4,
        f"检测到 {len(regions)} 个填充区域，面积 {regions[:6]}")

    # 5 状态框边框
    outline = color_count(body, BLUE, 22)
    add("状态框边框绘制", outline > 500, f"边框蓝像素 {outline} > 500")

    # 6 连线箭头
    arrow = color_count(body, ARROW, 26)
    add("转移连线绘制", arrow > 300, f"连线灰像素 {arrow} > 300")

    # 7 初始状态标记
    marker = color_count(body, GREEN, 30)
    add("初始状态标记", marker > 20, f"绿色标记像素 {marker} > 20")

    # 8 右侧属性面板
    panel_ratio = color_ratio(panel, PANEL, 4)
    add("右侧属性面板可见", panel_ratio > 0.10, f"面板色占比 {panel_ratio*100:.1f}% > 10%")

    # 9 状态栏可见
    sb_ratio = color_ratio(statusbar, STATUSBAR, 6)
    add("底部状态栏可见", sb_ratio > 0.25, f"状态栏色占比 {sb_ratio*100:.1f}% > 25%")

    # 10 基准图回归
    if write_golden:
        os.makedirs(os.path.dirname(golden), exist_ok=True)
        shutil.copyfile(shot, golden)
        rows.append(("PASS", "基准图已更新", golden))
    elif golden and os.path.exists(golden):
        score = mse(img, Image.open(golden).convert("RGB"))
        if score < 800:
            rows.append(("PASS", "基准图对比", f"MSE {score:.0f} < 800"))
        elif score < 3000:
            rows.append(("WARN", "基准图对比", f"MSE {score:.0f}，界面有变化"))
        else:
            rows.append(("FAIL", "基准图对比", f"MSE {score:.0f} >= 3000，回归严重"))
            failures.append("基准图对比")
    else:
        rows.append(("SKIP", "基准图对比", "无基准图，跳过"))

    # 输出
    print("\n=== Visual Check ===")
    print(f"截图 {w}x{h}  分区: 工具栏<{tb_h}px 状态栏>{sb_top}px 面板>{panel_left}px")
    icon = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}
    for status, name, detail in rows:
        print(f"  [{icon[status]:4}] {name}: {detail}")

    if failures:
        print(f"\n结果: FAIL ({len(failures)} 项未通过: {', '.join(failures)})")
        return 1
    print("\n结果: PASS")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shot", help="窗口截图路径")
    ap.add_argument("--golden", default=None, help="基准图路径")
    ap.add_argument("--write-golden", action="store_true", help="把当前截图写为基准图")
    args = ap.parse_args()
    if not os.path.exists(args.shot):
        print(f"FAIL: 截图不存在 {args.shot}")
        return 2
    return check(args.shot, args.golden, args.write_golden)


if __name__ == "__main__":
    sys.exit(main())
