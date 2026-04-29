"""图片处理工具模块 - 白底去背景等"""
from PIL import Image
import io


def remove_white_background(image_path: str, threshold: int = 240) -> bytes:
    """
    将白色背景转为透明（适用于白底黑字/蓝字签名图片）。
    
    Args:
        image_path: 图片文件路径
        threshold: 白色阈值 (0-255)，RGB 三个通道都大于此值则视为背景
    
    Returns:
        PNG 图片的 bytes 数据（带透明通道）
    """
    img = Image.open(image_path)
    
    # 如果没有 alpha 通道，先转换
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    pixels = img.load()
    width, height = img.size
    
    for x in range(width):
        for y in range(height):
            r, g, b, a = pixels[x, y]
            # 如果 RGB 三通道都大于阈值，认为是白色背景
            if r > threshold and g > threshold and b > threshold:
                # 根据与纯白的距离设置透明度，实现抗锯齿
                distance = max(r - threshold, g - threshold, b - threshold)
                alpha = min(255, distance * 8)  # 平滑过渡
                if alpha < 30:
                    alpha = 0
                pixels[x, y] = (r, g, b, alpha)
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def remove_white_background_from_bytes(data: bytes, threshold: int = 240) -> bytes:
    """从 bytes 数据去白底"""
    img = Image.open(io.BytesIO(data))
    
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    pixels = img.load()
    width, height = img.size
    
    for x in range(width):
        for y in range(height):
            r, g, b, a = pixels[x, y]
            if r > threshold and g > threshold and b > threshold:
                distance = max(r - threshold, g - threshold, b - threshold)
                alpha = min(255, distance * 8)
                if alpha < 30:
                    alpha = 0
                pixels[x, y] = (r, g, b, alpha)
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def image_to_qpixmap(data: bytes):
    """将图片 bytes 转为 QPixmap"""
    from PyQt6.QtGui import QPixmap, QImage
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
    
    qimage = QImage()
    qimage.loadFromData(data)
    return QPixmap.fromImage(qimage)
