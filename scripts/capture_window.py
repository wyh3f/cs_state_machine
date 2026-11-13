"""
窗口截图 — 用 Win32 PrintWindow 直接抓窗口内容
优点：不受 DPI 缩放、窗口遮挡、窗口超出屏幕的影响，拿到的一定是完整窗口
"""
import sys
import ctypes
from ctypes import wintypes
from PIL import Image, ImageGrab

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def set_dpi_aware():
    """声明 DPI 感知，避免系统对坐标做缩放虚拟化"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def find_hwnd(title):
    """按标题精确/模糊匹配可见窗口"""
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd

    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(h, _l):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            if title in buf.value:
                found.append(h)
        return True

    user32.EnumWindows(_cb, 0)
    return found[0] if found else 0


def window_rect(hwnd):
    rc = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc


def capture_printwindow(hwnd):
    """PrintWindow 抓整窗（含标题栏），返回 PIL Image"""
    rc = window_rect(hwnd)
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return None

    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)

    # PW_RENDERFULLCONTENT = 2，支持 DirectComposition 渲染的窗口
    user32.PrintWindow(hwnd, mdc, 2)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h  # 负值 = top-down
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0  # BI_RGB

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)

    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()


def capture_screen(hwnd):
    """兜底：置前 + 按窗口矩形截屏"""
    user32.SetForegroundWindow(hwnd)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002)  # NOSIZE|NOMOVE
    rc = window_rect(hwnd)
    return ImageGrab.grab(bbox=(rc.left, rc.top, rc.right, rc.bottom), all_screens=True)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="状态机 C 代码生成器",
                    help="窗口标题（默认内置，避免 PowerShell 传中文编码问题）")
    ap.add_argument("--out", default="_test_screenshot.png")
    args = ap.parse_args()

    set_dpi_aware()
    hwnd = find_hwnd(args.title)
    if not hwnd:
        print(f"FAIL: window not found: {args.title}")
        return 1

    img = capture_printwindow(hwnd)
    # PrintWindow 失败时画面接近全黑，用截屏兜底
    if img is None or _is_blank(img):
        img = capture_screen(hwnd)

    img.save(args.out)
    print(f"OK: {args.out} size={img.size[0]}x{img.size[1]}")
    return 0


def _is_blank(img):
    """判断图像是否接近纯黑（PrintWindow 失败的典型表现）"""
    small = img.convert("L").resize((32, 32))
    return max(small.tobytes()) < 12


if __name__ == "__main__":
    sys.exit(main())
