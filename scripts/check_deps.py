"""
依赖扫描 — 逐个解析 dist 目录下所有 PE 文件的导入表
判断每个被导入的 DLL 是「已随包携带」/「Windows 系统自带」/「缺失（需外部安装）」

用法: python scripts/check_deps.py [dist目录]
退出码: 0 无缺失；1 存在需外部安装的依赖
"""
import os
import sys

import pefile


# Windows 10/11 系统自带（无需随包、无需安装）
SYSTEM_DLLS = {
    "kernel32.dll", "kernelbase.dll", "user32.dll", "gdi32.dll", "gdi32full.dll",
    "advapi32.dll", "shell32.dll", "shlwapi.dll", "ole32.dll", "oleaut32.dll",
    "comdlg32.dll", "comctl32.dll", "winmm.dll", "ws2_32.dll", "wsock32.dll",
    "mpr.dll", "netapi32.dll", "userenv.dll", "version.dll", "imm32.dll",
    "uxtheme.dll", "dwmapi.dll", "bcrypt.dll", "bcryptprimitives.dll",
    "crypt32.dll", "ncrypt.dll", "ncryptsslp.dll", "secur32.dll", "sspicli.dll",
    "setupapi.dll", "psapi.dll", "rpcrt4.dll", "iphlpapi.dll", "mswsock.dll",
    "dnsapi.dll", "winspool.drv", "winhttp.dll", "wininet.dll", "urlmon.dll",
    "msimg32.dll", "opengl32.dll", "glu32.dll", "gdiplus.dll", "dwrite.dll",
    "d3d11.dll", "d3d9.dll", "dxgi.dll", "d2d1.dll", "windowscodecs.dll",
    "propsys.dll", "authz.dll", "wtsapi32.dll", "powrprof.dll", "dbghelp.dll",
    "ntdll.dll", "mscoree.dll", "msacm32.dll", "odbc32.dll", "comsvcs.dll",
    "credui.dll", "wintrust.dll", "cabinet.dll", "tapi32.dll", "rasapi32.dll",
    "oleacc.dll", "uiautomationcore.dll", "shcore.dll", "twinapi.dll",
    "msctf.dll", "sechost.dll", "cfgmgr32.dll", "wlanapi.dll", "normaliz.dll",
    "dcomp.dll", "dxcore.dll", "directml.dll", "hid.dll", "dinput8.dll",
}

SYSTEM_PREFIXES = ("api-ms-win-", "ext-ms-win-", "ext-ms-")


def collect_bundled(root):
    """收集随包携带的所有文件名（小写，不含扩展名路径）"""
    names = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            names.add(fn.lower())
    return names


def iter_pe_files(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "rb") as f:
                    if f.read(2) != b"MZ":
                        continue
            except OSError:
                continue
            yield path


def imports_of(path):
    """返回该 PE 导入的 DLL 名（小写）"""
    try:
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
    except Exception:
        return set()

    found = set()
    for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
        for entry in getattr(pe, attr, []) or []:
            try:
                name = entry.dll.decode("ascii", "ignore").lower()
            except Exception:
                continue
            if name:
                found.add(name)
    pe.close()
    return found


def classify(dll, bundled):
    if dll in bundled:
        return "bundled"
    if dll in SYSTEM_DLLS or dll.startswith(SYSTEM_PREFIXES):
        return "system"
    return "missing"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dist", "cs_state_machine")
    if not os.path.isdir(root):
        print(f"目录不存在: {root}")
        return 2

    bundled = collect_bundled(root)
    missing = {}
    pe_count = 0

    for path in iter_pe_files(root):
        pe_count += 1
        rel = os.path.relpath(path, root)
        for dll in imports_of(path):
            kind = classify(dll, bundled)
            if kind == "missing":
                missing.setdefault(dll, []).append(rel)

    print(f"扫描 PE 文件 {pe_count} 个，随包文件 {len(bundled)} 个")
    if not missing:
        print("\n结果: PASS  所有导入项均为随包 DLL 或 Windows 系统 DLL")
        return 0

    print(f"\n结果: FAIL  发现 {len(missing)} 个需外部安装的依赖\n")
    for dll, users in sorted(missing.items()):
        print(f"  [缺失] {dll}")
        for u in users[:4]:
            print(f"          被 {u} 引用")
        if len(users) > 4:
            print(f"          ... 共 {len(users)} 处")
    return 1


if __name__ == "__main__":
    sys.exit(main())
