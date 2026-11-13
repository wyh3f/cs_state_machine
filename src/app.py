"""
cs_state_machine — 状态机 C 代码生成器
入口：创建 CTk 根窗口，启动主窗口
"""
import ctypes

import customtkinter as ctk

from gui.main_window import MainWindow


def _enable_dpi_awareness():
    """声明 DPI 感知，否则 125% 缩放下 1280x800 会被放大成 1600x1000 超出屏幕"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _enable_dpi_awareness()
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
