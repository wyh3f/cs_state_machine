# -*- mode: python ; coding: utf-8 -*-
#
# 单文件（onefile）打包配置
# 依据：
#   - customtkinter 官方打包文档要求把整个 customtkinter 目录（含 themes/*.json）加入 datas
#   - PyInstaller 官方建议先用 onedir 验证通过，再切换 onefile（本项目已按此顺序执行）
#   - UPX 压缩会显著提高杀毒软件误报率，这里关闭
#
import os
import customtkinter

ctk_dir = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # 关键：themes/*.json 等数据文件必须随包，否则运行时找不到主题报错
        (ctk_dir, 'customtkinter'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 科学计算 / 数据处理 —— 工程未使用
        "matplotlib", "scipy", "numpy", "pandas", "sympy", "networkx",
        # 重型 GUI 子模块 —— 只用 tkinter / customtkinter
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "PyQt5.QtWebEngineWidgets", "PyQt5.QtQml", "PyQt5.Qt3DCore",
        "PyQt5.QtMultimedia", "PyQt5.QtSql", "PyQt5.QtOpenGL",
        "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.Qt3DCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.Qt3DCore",
        "PySide6.QtMultimedia", "PySide6.QtSql",
        # 多媒体 / 游戏 / 网络 —— 工程未使用
        "pygame", "pyglet", "opencv-python", "cv2",
        "socketio", "websockets", "http.server", "urllib3",
        "xmlrpc", "xmlrpc.client", "xmlrpc.server",
        "asyncio", "concurrent.futures", "multiprocessing",
        # 测试 / 开发 —— 运行时不需要
        "unittest", "pytest", "doctest", "pdb",
        "py_compile", "compileall", "code", "codeop",
        # IPython / Jupyter 相关 —— 体积大
        "IPython", "jupyter", "notebook", "sphinx", "docutils",
        # 大体积第三方 —— 按需继续追加
        "torch", "tensorflow", "sklearn", "statsmodels",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# onefile：binaries / datas 全部塞进 EXE，不再生成 COLLECT 目录
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='cs_state_machine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # 关闭 UPX：降低杀毒误报
    console=False,          # GUI 程序，不弹黑色控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
