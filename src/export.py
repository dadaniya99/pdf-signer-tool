"""PDF 导出模块 - 将签名嵌入 PDF"""
import fitz  # PyMuPDF
import math
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice


def export_pdf_with_signatures(
    source_pdf_path: str,
    output_path: str,
    all_signatures: dict,
    render_scale: float = 2.0,
    source_is_bytes: bool = False,
    source_data: bytes = None,
):
    """
    导出带签名的 PDF。
    
    Args:
        source_pdf_path: 源 PDF 文件路径
        output_path: 输出路径
        all_signatures: {page_num: [dict, ...]} 每个dict含 image_data/sig_id/x/y/scale/rotation
        render_scale: PDF 页面渲染缩放比例（用于坐标转换）
        source_is_bytes: 源是否为 bytes
        source_data: bytes 数据（当 source_is_bytes=True 时使用）
    """
    if source_is_bytes and source_data:
        doc = fitz.open(stream=source_data, filetype="pdf")
    else:
        doc = fitz.open(source_pdf_path)
    
    for page_num, sig_list in all_signatures.items():
        if page_num >= doc.page_count:
            continue
        
        page = doc[page_num]
        page_rect = page.rect
        
        for sig_data in sig_list:
            if isinstance(sig_data, dict):
                _insert_signature_from_dict(page, sig_data, render_scale)
            else:
                # 兼容旧格式（SignatureGraphicsItem）
                from src.signature_item import SignatureGraphicsItem
                if isinstance(sig_data, SignatureGraphicsItem):
                    _insert_signature_from_item(page, sig_data, render_scale)
    
    doc.save(output_path, deflate=True, garbage=4)
    doc.close()
    return output_path


def _qpixmap_to_bytes(pixmap: QPixmap) -> bytes:
    """QPixmap 转 PNG bytes"""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, 'PNG')
    return bytes(ba.data())


def _insert_signature_from_dict(page, sig_data: dict, render_scale: float):
    """从序列化数据插入签名"""
    image_data = sig_data.get('image_data')
    if not image_data:
        return
    
    # 场景坐标转 PDF 坐标
    pdf_x = sig_data['x'] / render_scale
    pdf_y = sig_data['y'] / render_scale
    
    # 用 base 尺寸 * scale 计算
    scale = sig_data.get('scale', 1.0)
    
    # 从图片数据计算尺寸
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(image_data))
    img_w, img_h = img.size
    aspect = img_w / max(img_h, 1)
    
    base_width = 150.0
    base_height = base_width / aspect if aspect >= 1 else 150.0 * aspect
    w = base_width * scale / render_scale
    h = base_height * scale / render_scale
    
    rotation = sig_data.get('rotation', 0.0)
    
    _place_image_on_page(page, image_data, pdf_x, pdf_y, w, h, rotation)


def _insert_signature_from_item(page, sig_item, render_scale: float):
    """从 SignatureGraphicsItem 插入签名（兼容旧格式）"""
    scene_pos = sig_item.scenePos()
    w = sig_item.current_width() / render_scale
    h = sig_item.current_height() / render_scale
    rotation = sig_item.rotation_angle
    
    pdf_x = scene_pos.x() / render_scale
    pdf_y = scene_pos.y() / render_scale
    
    sig_pixmap = sig_item._pixmap
    if sig_pixmap.isNull():
        return
    
    image_data = _qpixmap_to_bytes(sig_pixmap)
    _place_image_on_page(page, image_data, pdf_x, pdf_y, w, h, rotation)


def _place_image_on_page(page, image_data: bytes, x: float, y: float, 
                          w: float, h: float, rotation: float = 0.0):
    """在 PDF 页面上放置签名图片
    
    旋转角度取整到最近的 90 度，用 PIL 预旋转图片。
    """
    from PIL import Image
    import io
    
    try:
        # 旋转角度取整到 90 度步进
        rotation_int = int(round(rotation / 90) * 90) % 360
        
        if rotation_int != 0:
            # 用 PIL 预旋转图片（取反方向）
            img = Image.open(io.BytesIO(image_data))
            img_rotated = img.rotate(
                -rotation_int,
                expand=True,
                resample=Image.Resampling.LANCZOS,
                fillcolor=0
            )
            
            buf = io.BytesIO()
            img_rotated.save(buf, format='PNG')
            rotated_data = buf.getvalue()
            
            # 旋转后的尺寸
            new_w = w * img_rotated.width / img.width
            new_h = h * img_rotated.height / img.height
            
            # 以中心点定位
            center_x = x + w / 2
            center_y = y + h / 2
            
            new_rect = fitz.Rect(
                center_x - new_w / 2,
                center_y - new_h / 2,
                center_x + new_w / 2,
                center_y + new_h / 2,
            )
            
            page.insert_image(new_rect, stream=rotated_data, overlay=True)
        else:
            page.insert_image(
                fitz.Rect(x, y, x + w, y + h),
                stream=image_data,
                overlay=True,
            )
    except Exception as e:
        print(f"插入签名失败: {e}")
        try:
            page.insert_image(
                fitz.Rect(x, y, x + w, y + h),
                stream=image_data,
                overlay=True,
            )
        except:
            pass


def suggest_output_path(source_path: str) -> str:
    """建议输出路径（原名_signed.pdf）"""
    import os
    base, ext = os.path.splitext(source_path)
    return f"{base}_signed{ext}"
