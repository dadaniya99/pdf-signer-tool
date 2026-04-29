"""签名图元 - QGraphicsItem 子类，支持拖拽/缩放/旋转"""
import math
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsObject,
    QGraphicsTextItem
)
from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QSizeF, pyqtSignal, QObject,
    QPropertyAnimation, QEasingCurve
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QTransform, QCursor, QColor, QPen,
    QBrush, QPainterPath, QImage
)


class SignatureGraphicsItem(QGraphicsObject):
    """
    可拖拽、缩放、旋转的签名图元。
    
    签名数据全部存储在属性中，重绘时从数据渲染，
    不会因窗口操作而丢失。
    """
    
    # 信号
    placement_changed = pyqtSignal()
    deleted = pyqtSignal(object)  # 发送自身引用
    
    HANDLE_SIZE = 8
    
    def __init__(self, image_data: bytes, sig_id: str = "", parent=None):
        super().__init__(parent)
        
        self._sig_id = sig_id
        self._rotation_angle = 0.0
        self._pixmap = QPixmap()
        self._pixmap_data = image_data  # 保留原始 bytes，翻页恢复用
        self._base_width = 150.0
        self._base_height = 150.0
        
        # 加载图片
        img = QImage()
        img.loadFromData(image_data)
        if not img.isNull():
            self._pixmap = QPixmap.fromImage(img)
            aspect = self._pixmap.width() / max(self._pixmap.height(), 1)
            if aspect >= 1:
                self._base_height = self._base_width / aspect
            else:
                self._base_width = self._base_height * aspect
        
        # 交互设置
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        
        # 操作状态
        self._resizing = False
        self._rotating = False
        self._resize_start_dist = 0
        self._resize_start_scale = 1.0
        self._rotate_start_angle = 0
        
        # 缩放
        self._scale_factor = 1.0
        
        self.setZValue(100)
    
    @property
    def sig_id(self):
        return self._sig_id
    
    @property
    def rotation_angle(self):
        return self._rotation_angle
    
    @rotation_angle.setter
    def rotation_angle(self, value):
        self._rotation_angle = value
        self.setRotation(value)
        self.placement_changed.emit()
    
    @property
    def scale_factor(self):
        return self._scale_factor
    
    @property
    def base_width(self):
        return self._base_width
    
    @property
    def base_height(self):
        return self._base_height
    
    @scale_factor.setter
    def scale_factor(self, value):
        self._scale_factor = max(0.1, min(5.0, value))
        self.update()
        self.placement_changed.emit()
    
    def current_width(self):
        return self._base_width * self._scale_factor
    
    def current_height(self):
        return self._base_height * self._scale_factor
    
    def boundingRect(self) -> QRectF:
        """必须包含所有绘制内容（包括控制点）"""
        margin = self.HANDLE_SIZE + 20
        w = self.current_width()
        h = self.current_height()
        return QRectF(-margin, -margin, w + 2 * margin, h + 2 * margin)
    
    def _signature_rect(self) -> QRectF:
        w = self.current_width()
        h = self.current_height()
        return QRectF(0, 0, w, h)
    
    def _handles(self):
        """返回8个缩放手柄位置"""
        rect = self._signature_rect()
        hs = self.HANDLE_SIZE / 2
        positions = {
            'top_left': QPointF(rect.left() - hs, rect.top() - hs),
            'top_right': QPointF(rect.right() - hs, rect.top() - hs),
            'bottom_left': QPointF(rect.left() - hs, rect.bottom() - hs),
            'bottom_right': QPointF(rect.right() - hs, rect.bottom() - hs),
            'top_mid': QPointF(rect.center().x() - hs, rect.top() - hs),
            'bottom_mid': QPointF(rect.center().x() - hs, rect.bottom() - hs),
            'left_mid': QPointF(rect.left() - hs, rect.center().y() - hs),
            'right_mid': QPointF(rect.right() - hs, rect.center().y() - hs),
        }
        return positions
    
    def _rotate_handle(self):
        """旋转手柄位置"""
        rect = self._signature_rect()
        return QPointF(rect.center().x(), rect.top() - 20)
    
    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        rect = self._signature_rect()
        
        # 绘制签名图片
        if not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
        
        # 选中时绘制控制框
        if self.isSelected():
            # 边框
            pen = QPen(QColor(0, 120, 215), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(rect)
            
            # 缩放手柄
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            for name, pos in self._handles().items():
                painter.drawRect(QRectF(pos.x(), pos.y(), self.HANDLE_SIZE, self.HANDLE_SIZE))
            
            # 旋转手柄
            rh = self._rotate_handle()
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.setBrush(QBrush(QColor(0, 120, 215)))
            painter.drawEllipse(rh, 5, 5)
            
            # 旋转手柄连线
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(rect.center().x(), rect.top()), rh)
    
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        """项目变化通知 - 确保移动后同步数据"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.placement_changed.emit()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)
    
    def _hit_test(self, pos: QPointF) -> str:
        """检测点击位置命中了什么"""
        if not self.isSelected():
            return ''
        
        # 旋转手柄
        rh = self._rotate_handle()
        if (pos - rh).manhattanLength() < 12:
            return 'rotate'
        
        # 缩放手柄
        rect = self._signature_rect()
        hs = self.HANDLE_SIZE + 4
        for name, hp in self._handles().items():
            handle_rect = QRectF(hp.x() - 2, hp.y() - 2, hs, hs)
            if handle_rect.contains(pos):
                return name
        
        # 签名区域
        if rect.contains(pos):
            return 'move'
        
        return ''
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.pos())
            if hit == 'rotate':
                self._rotating = True
                rect = self._signature_rect()
                center = rect.center()
                self._rotate_start_angle = math.degrees(
                    math.atan2(event.pos().y() - center.y(), event.pos().x() - center.x())
                )
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
                event.accept()
                return
            elif hit and hit != 'move':
                self._resizing = True
                rect = self._signature_rect()
                center = rect.center()
                self._resize_start_dist = math.sqrt(
                    (event.pos().x() - center.x()) ** 2 + (event.pos().y() - center.y()) ** 2
                )
                self._resize_start_scale = self._scale_factor
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
                event.accept()
                return
            else:
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._rotating:
            rect = self._signature_rect()
            center = rect.center()
            angle = math.degrees(
                math.atan2(event.pos().y() - center.y(), event.pos().x() - center.x())
            )
            delta = angle - self._rotate_start_angle
            self._rotation_angle += delta
            self._rotate_start_angle = angle
            self.setRotation(self._rotation_angle)
            self.placement_changed.emit()
            event.accept()
            return
        
        if self._resizing:
            rect = self._signature_rect()
            center = rect.center()
            dist = math.sqrt(
                (event.pos().x() - center.x()) ** 2 + (event.pos().y() - center.y()) ** 2
            )
            if self._resize_start_dist > 0:
                ratio = dist / self._resize_start_dist
                self._scale_factor = max(0.1, min(5.0, self._resize_start_scale * ratio))
                self.prepareGeometryChange()
                self.update()
                self.placement_changed.emit()
            event.accept()
            return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._rotating = False
        hit = self._hit_test(event.pos())
        if hit == 'move' or hit == '':
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().mouseReleaseEvent(event)
    
    def hoverMoveEvent(self, event):
        if self.isSelected():
            hit = self._hit_test(event.pos())
            if hit == 'rotate':
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            elif hit in ('top_left', 'bottom_right'):
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            elif hit in ('top_right', 'bottom_left'):
                self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
            elif hit in ('top_mid', 'bottom_mid'):
                self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
            elif hit in ('left_mid', 'right_mid'):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().hoverMoveEvent(event)
    
    def wheelEvent(self, event):
        """滚轮缩放"""
        delta = event.angleDelta().y()
        if delta > 0:
            self._scale_factor = min(5.0, self._scale_factor * 1.05)
        else:
            self._scale_factor = max(0.1, self._scale_factor / 1.05)
        self.prepareGeometryChange()
        self.update()
        self.placement_changed.emit()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            scene = self.scene()
            if scene:
                scene.removeItem(self)
            self.deleted.emit(self)
            event.accept()
        elif event.key() == Qt.Key.Key_R:
            # R 键旋转 90 度
            self._rotation_angle += 90
            self.setRotation(self._rotation_angle)
            self.placement_changed.emit()
            event.accept()
        super().keyPressEvent(event)
    
    def get_placement_data(self, page_height: float, page_width: float):
        """
        获取签名的位置数据（用于 PDF 导出）。
        将 QGraphicsScene 坐标转为 PDF 坐标系。
        
        Args:
            page_height: PDF 页面高度
            page_width: PDF 页面宽度（可能暂时不用）
        
        Returns:
            dict with x, y, width, height, rotation
        """
        scene_pos = self.scenePos()
        return {
            'scene_x': scene_pos.x(),
            'scene_y': scene_pos.y(),
            'width': self.current_width(),
            'height': self.current_height(),
            'rotation': self._rotation_angle,
            'scale': self._scale_factor,
        }
