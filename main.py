"""入口 - 解决 PyInstaller 打包后的包导入问题"""
import sys
import os

# PyInstaller 打包后，_MEIPASS 是提取目录
# 需要确保 src 包可被导入
if getattr(sys, 'frozen', False):
    # 打包后的 EXE 运行环境
    base_path = sys._MEIPASS
    if base_path not in sys.path:
        sys.path.insert(0, base_path)

from src.app import main

if __name__ == "__main__":
    main()
