# -*- coding: utf-8 -*-
import PyInstaller.__main__
import sys, os, shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")

if __name__ == "__main__":
    # 清理旧构建（可选）
    for d in (DIST_DIR, BUILD_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)

    opts = [
        os.path.join(PROJECT_ROOT, "gui", "app.py"),
        "--name=FundPoolGUI",
        "--noconfirm",
        "--onefile",                 # 单文件 .exe；若运行慢可改为目录模式
        "--windowed",                # 无控制台窗口
        "--add-data=assets;gui/assets",  # 如果有图标/样式，注意分号与分隔
        "--hidden-import=PySide6",
        "--hidden-import=pandas",
        "--hidden-import=numpy",
        "--hidden-import=matplotlib",
    ]

    # Windows 下建议指定图标（可选）
    icon_path = os.path.join(PROJECT_ROOT, "gui", "assets", "app.ico")
    if os.path.exists(icon_path):
        opts.append(f"--icon={icon_path}")

    PyInstaller.__main__.run(opts)
    print("打包完成：dist/FundPoolGUI.exe")
