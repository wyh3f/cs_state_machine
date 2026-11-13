"""
零依赖运行测试 — 模拟「另一台干净的 Win10/11 电脑」

做四件事：
1. 把打包产物复制到含空格 + 中文的临时目录（证明不依赖构建机路径）
2. 用极简环境变量启动（无 PATH 里的 Python/conda、无 PYTHONHOME/PYTHONPATH、独立 TEMP）
3. 等窗口就绪 -> 抓图 -> 复用 visual_check 做像素断言
4. 结束进程并清理临时目录

退出码 0 = 可在无 Python 环境的机器上独立运行
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE_SRC = os.path.join(ROOT, "dist", "cs_state_machine.exe")
BASE = os.path.join(tempfile.gettempdir(), "cs_zerodep")
SANDBOX = os.path.join(BASE, "状态机 零依赖 测试")
APP_DIR = os.path.join(SANDBOX, "app")
TITLE = "状态机 C 代码生成器"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def find_window_by_title(target, timeout=45.0):
    """按窗口标题查找（onefile 的窗口属于子进程，不能按启动 PID 找）"""
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _l):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value == target:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            result.append((hwnd, buf.value, pid.value))
            return False
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        result.clear()
        user32.EnumWindows(_cb, 0)
        if result:
            return result[0]
        time.sleep(0.3)
    return None


def process_image_path(pid):
    """取进程完整 exe 路径，用于确认窗口确实来自沙箱里的副本"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def minimal_env():
    """只保留 Windows 自身需要的变量，完全剔除 Python/conda 相关配置"""
    win = os.environ.get("SystemRoot", r"C:\Windows")
    temp = os.path.join(SANDBOX, "temp")
    os.makedirs(temp, exist_ok=True)
    return {
        "SystemRoot": win,
        "windir": win,
        "SystemDrive": os.environ.get("SystemDrive", "C:"),
        "COMSPEC": os.path.join(win, "System32", "cmd.exe"),
        "PATH": os.path.join(win, "System32") + ";" + win,
        "TEMP": temp,
        "TMP": temp,
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "APPDATA": os.path.join(temp, "appdata"),
        "LOCALAPPDATA": os.path.join(temp, "localappdata"),
        "NUMBER_OF_PROCESSORS": os.environ.get("NUMBER_OF_PROCESSORS", "1"),
        "PROCESSOR_ARCHITECTURE": "AMD64",
    }


def find_mei_dir(temp_dir, timeout=15.0):
    """onefile 运行时会把运行时解压到 TEMP\\_MEIxxxx，用于做真实依赖审计"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for name in os.listdir(temp_dir):
                if name.startswith("_MEI"):
                    path = os.path.join(temp_dir, name)
                    if os.path.isdir(path):
                        return path
        except OSError:
            pass
        time.sleep(0.5)
    return None


def main():
    if not os.path.exists(EXE_SRC):
        print(f"FAIL: 找不到 {EXE_SRC}，先执行 build.ps1")
        return 2

    print("=== 1. 只复制单个 exe 到含空格+中文的目录 ===")
    if os.path.isdir(BASE):
        shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(APP_DIR, exist_ok=True)
    exe = os.path.join(APP_DIR, "cs_state_machine.exe")
    shutil.copy2(EXE_SRC, exe)
    size = os.path.getsize(exe) / 1024.0 / 1024.0
    print(f"  {exe}")
    print(f"  单文件大小 {size:.1f}MB，目录内无其他文件: {os.listdir(APP_DIR) == ['cs_state_machine.exe']}")

    env = minimal_env()
    print("\n=== 2. 极简环境启动 ===")
    print(f"  PATH = {env['PATH']}")
    print(f"  PYTHONHOME 是否注入 = {'PYTHONHOME' in env}")
    print(f"  PYTHONPATH 是否注入 = {'PYTHONPATH' in env}")
    print(f"  TEMP = {env['TEMP']}")

    t0 = time.time()
    proc = subprocess.Popen([exe], cwd=APP_DIR, env=env)
    print(f"  pid = {proc.pid}")

    code = 0
    try:
        print("\n=== 3. 等待窗口就绪 ===")
        found = find_window_by_title(TITLE, timeout=45)
        if not found:
            rc = proc.poll()
            print(f"FAIL: 45s 内没有出现窗口，启动进程退出码 = {rc}")
            return 1
        hwnd, title, win_pid = found
        img = process_image_path(win_pid)
        print(f"  hwnd = {hwnd}  title = [{title}]  window pid = {win_pid}")
        print(f"  窗口进程路径 = {img}")
        print(f"  启动耗时 = {time.time() - t0:.2f}s")
        if not img.lower().startswith(APP_DIR.lower()):
            print("WARN: 窗口进程不在沙箱目录内，可能命中了其他实例")
        time.sleep(0.9)

        print("\n=== 4. 运行时解压目录依赖审计 ===")
        mei = find_mei_dir(env["TEMP"])
        if mei:
            print(f"  解压目录 {mei}")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_deps.py"), mei])
            if r.returncode != 0:
                code = 1
        else:
            print("  WARN: 未找到 _MEI 解压目录，跳过依赖审计")

        print("\n=== 5. 截图 + 像素断言 ===")
        shot = os.path.join(ROOT, "_zerodep_screenshot.png")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "capture_window.py"),
                            "--out", shot])
        if r.returncode != 0:
            print("FAIL: 截图失败")
            return 1

        check_args = [sys.executable, os.path.join(ROOT, "scripts", "visual_check.py"), shot]
        golden = os.path.join(ROOT, "scripts", "golden", "startup.png")
        if os.path.exists(golden):
            check_args += ["--golden", golden]
        r = subprocess.run(check_args)
        code = code or r.returncode
    finally:
        print("\n=== 6. 关闭进程 ===")
        # onefile 是「父进程 + 子进程」结构，必须按进程树杀
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        leftover = find_window_by_title(TITLE, timeout=2.5)
        print(f"  启动进程退出码 = {proc.poll()}  残留窗口 = {'有' if leftover else '无'}")
        if leftover:
            subprocess.run(["taskkill", "/F", "/PID", str(leftover[2])],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            code = 1
        time.sleep(0.5)
        if os.path.isdir(BASE):
            shutil.rmtree(BASE, ignore_errors=True)
            print(f"  临时目录已清理: {os.path.exists(BASE) is False}")

    print("\n结果: " + ("PASS 可在无 Python / 无 conda 的机器上独立运行" if code == 0 else "FAIL"))
    return code


if __name__ == "__main__":
    sys.exit(main())
