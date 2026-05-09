"""PDF签名工具 - 入口文件"""
import sys
import os

# PyInstaller 打包后，确保 src 包在 sys.path 中
if getattr(sys, 'frozen', False):
    # 运行时 _MEIPASS 是 PyInstaller 提取的临时目录
    base_path = sys._MEIPASS
    if base_path not in sys.path:
        sys.path.insert(0, base_path)

from src.app import main

if __name__ == "__main__":
    main()
