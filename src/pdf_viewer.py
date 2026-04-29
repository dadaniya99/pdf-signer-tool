"""PDF 预览组件 - 使用 QGraphicsView/QGraphicsScene 显示 PDF 页面并放置签名"""
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QSizePolicy, QMenu
)
from PyQt6.QtCore import (
    Qt, QRectF, QSizeF, QPointF, pyqtSignal, QTimer
)
from PyQt6.QtGui import (
    QPixmap, QImage, QWheelEvent, QMouseEvent, QKeyEvent,
    QAction, QKeySequence, QShortcut, QBrush, QPainter
)


class PDFViewer(QGraphicsView):
    """PDF 预览和签名放置区域"""

    page_changed = pyqtSignal(int)  # 页码变化信号 (0-based)
    signature_placed = pyqtSignal(object)  # 签名放置信号
    file_dropped = pyqtSignal(str)  # 文件拖入信号
    signature_dropped = pyqtSignal(str, object)  # 签名拖入信号 (sig_id, scene_pos)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._doc = None  # fitz.Document
        self._current_page = 0
        self._page_pixmap_item = None

        # 签名数据:{page_num: [SignatureGraphicsItem, ...]}
        self._signatures = {}

        # 待放置的签名数据
        self._pending_signature_data = None

        # 显示设置
        self._zoom = 1.0
        self._fit_mode = True

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 500)

        self.setBackgroundBrush(QBrush())

        # 启用拖拽
        self.setAcceptDrops(True)

    def load_pdf(self, path: str) -> bool:
        """加载 PDF 文件"""
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(path)
            self._current_page = 0
            self._signatures.clear()
            self._scene.clear()  # 先清场景,防止 _render_page 里的 _save 又把旧签名存回来
            self._page_pixmap_item = None
            self._render_page()
            self.page_changed.emit(0)
            return True
        except Exception as e:
            print(f"加载 PDF 失败: {e}")
            return False

    def load_pdf_from_bytes(self, data: bytes) -> bool:
        """从 bytes 加载 PDF"""
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(stream=data, filetype="pdf")
            self._current_page = 0
            self._signatures.clear()
            self._scene.clear()
            self._page_pixmap_item = None
            self._render_page()
            self.page_changed.emit(0)
            return True
        except Exception as e:
            print(f"加载 PDF 失败: {e}")
            return False

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    @property
    def current_page(self) -> int:
        return self._current_page

    def _render_page(self):
        """渲染当前页"""
        if not self._doc:
            return

        self._scene.clear()
        self._page_pixmap_item = None

        page = self._doc[self._current_page]

        # 高分辨率渲染
        mat = fitz.Matrix(2.0, 2.0)  # 2x 渲染
        pix = page.get_pixmap(matrix=mat)

        img = QImage(pix.samples, pix.width, pix.height,
                     pix.stride, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(img)
        self._page_pixmap_item = self._scene.addPixmap(pixmap)

        # 设置场景大小
        self._scene.setSceneRect(QRectF(0, 0, pix.width, pix.height))

        # 恢复当前页签名
        self._restore_current_page_signatures()

        # 适应窗口
        if self._fit_mode:
            QTimer.singleShot(10, self.fit_to_view)

    def _save_current_page_signatures(self):
        """保存当前页面的签名数据(序列化,不保留 item 引用)
        关键：用 base_width/base_height 算中心点，不受旋转影响"""
        from src.signature_item import SignatureGraphicsItem

        saved = []
        for item in self._scene.items():
            if isinstance(item, SignatureGraphicsItem):
                pos = item.scenePos()
                # 用原始尺寸算中心点，旋转后视觉中心不变
                center_x = pos.x() + item.base_width * item.scale_factor / 2
                center_y = pos.y() + item.base_height * item.scale_factor / 2
                saved.append({
                    'image_data': item._pixmap_data,  # 原始图片 bytes
                    'sig_id': item.sig_id,
                    'x': pos.x(),
                    'y': pos.y(),
                    'center_x': center_x,
                    'center_y': center_y,
                    'scale': item.scale_factor,
                    'rotation': item.rotation_angle,
                })

        self._signatures[self._current_page] = saved

    def _restore_current_page_signatures(self):
        """从数据字典恢复当前页面的签名"""
        from src.signature_item import SignatureGraphicsItem

        saved_list = self._signatures.get(self._current_page, [])
        for data in saved_list:
            item = SignatureGraphicsItem(data['image_data'], data.get('sig_id', ''))
            # 优先使用 center_x/center_y 恢复位置（旋转后位置更准确）
            if 'center_x' in data and 'center_y' in data:
                cx = data['center_x']
                cy = data['center_y']
                w = item.current_width()
                h = item.current_height()
                item.setPos(cx - w / 2, cy - h / 2)
            else:
                item.setPos(data['x'], data['y'])
            item.scale_factor = data.get('scale', 1.0)
            item.rotation_angle = data.get('rotation', 0.0)
            item.setRotation(item.rotation_angle)
            self._scene.addItem(item)

    def go_to_page(self, page_num: int):
        """跳转到指定页"""
        if not self._doc:
            return
        page_num = max(0, min(page_num, self._doc.page_count - 1))
        if page_num == self._current_page:
            return
        # 先保存当前页签名(在修改 _current_page 之前!)
        self._save_current_page_signatures()
        self._current_page = page_num
        self._render_page()
        self.page_changed.emit(page_num)

    def next_page(self):
        self.go_to_page(self._current_page + 1)

    def prev_page(self):
        self.go_to_page(self._current_page - 1)

    def set_pending_signature(self, image_data: bytes, sig_id: str = ""):
        """设置待放置的签名"""
        self._pending_signature_data = (image_data, sig_id)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def place_signature_at(self, scene_pos: QPointF):
        """在指定位置放置签名"""
        if not self._pending_signature_data:
            return

        image_data, sig_id = self._pending_signature_data
        from src.signature_item import SignatureGraphicsItem

        item = SignatureGraphicsItem(image_data, sig_id)
        # 放置在点击位置(居中)
        w = item.current_width()
        h = item.current_height()
        item.setPos(scene_pos.x() - w / 2, scene_pos.y() - h / 2)
        item.setSelected(True)

        self._scene.addItem(item)

        # 记录到签名数据(也存一份序列化数据)
        # 关键：用 base_width/base_height 算中心点，不受旋转影响
        if self._current_page not in self._signatures:
            self._signatures[self._current_page] = []
        self._signatures[self._current_page].append({
            'image_data': image_data,
            'sig_id': sig_id,
            'x': item.scenePos().x(),
            'y': item.scenePos().y(),
            'center_x': item.scenePos().x() + item.base_width * item.scale_factor / 2,
            'center_y': item.scenePos().y() + item.base_height * item.scale_factor / 2,
            'scale': item.scale_factor,
            'rotation': item.rotation_angle,
        })

        self._pending_signature_data = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.signature_placed.emit(item)

    def dragEnterEvent(self, event):
        """拖拽进入 - 接受文件和签名"""
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasFormat("application/x-signature-id"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """拖拽移动 - 必须也接受,否则显示禁止符号"""
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasFormat("application/x-signature-id"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """拖拽放下 - 处理文件打开和签名放置"""
        mime = event.mimeData()

        if mime.hasFormat("application/x-signature-id"):
            sig_id = bytes(mime.data("application/x-signature-id")).decode()
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            scene_pos = self.mapToScene(pos)
            # 通过信号让主窗口处理(主窗口有 SignatureLibrary)
            self.signature_dropped.emit(sig_id, scene_pos)
            event.acceptProposedAction()
            return

        if mime.hasUrls():
            url = mime.urls()[0]
            file_path = url.toLocalFile()
            if file_path:
                self.file_dropped.emit(file_path)
                event.acceptProposedAction()
                return

        super().dropEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """处理点击放置签名"""
        if self._pending_signature_data and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.place_signature_at(scene_pos)
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """滚轮:Ctrl+滚轮缩放视图,普通滚轮翻页"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self._zoom *= factor
            self.scale(factor, factor)
            self._fit_mode = False
            event.accept()
        elif self._doc:
            # 普通滚轮翻页
            if event.angleDelta().y() > 0:
                self.prev_page()
            else:
                self.next_page()
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        """窗口大小变化时重新适应"""
        super().resizeEvent(event)
        if self._fit_mode and self._page_pixmap_item:
            self.fit_to_view()

    def fit_to_view(self):
        """适应窗口大小"""
        if not self._page_pixmap_item:
            return
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_mode = True
        self._zoom = 1.0

    def get_all_signatures(self):
        """获取所有页面的签名数据"""
        # 先保存当前页
        self._save_current_page_signatures()
        # 返回的已经是序列化数据,直接返回
        return dict(self._signatures)

    def get_page_render_scale(self):
        """获取页面渲染缩放比例(用于坐标转换)"""
        return 2.0  # 渲染时用的 2x

    def remove_selected_signature(self):
        """删除选中的签名"""
        from src.signature_item import SignatureGraphicsItem
        for item in self._scene.selectedItems():
            if isinstance(item, SignatureGraphicsItem):
                self._scene.removeItem(item)
        # 同步更新签名数据(从序列化列表中移除)
        self._save_current_page_signatures()

    def rotate_selected_signature(self, degrees: float = 15.0):
        """旋转选中的签名"""
        from src.signature_item import SignatureGraphicsItem
        for item in self._scene.selectedItems():
            if isinstance(item, SignatureGraphicsItem):
                item.rotation_angle += degrees

    def contextMenuEvent(self, event):
        """右键菜单"""
        from src.signature_item import SignatureGraphicsItem

        has_selected = any(
            isinstance(item, SignatureGraphicsItem)
            for item in self._scene.selectedItems()
        )

        menu = QMenu(self)

        if has_selected:
            action_delete = menu.addAction("删除签名")
            action_delete.triggered.connect(self.remove_selected_signature)

            action_rotate_cw = menu.addAction("顺时针旋转 90°")
            action_rotate_cw.triggered.connect(lambda: self.rotate_selected_signature(90))

            action_rotate_ccw = menu.addAction("逆时针旋转 90°")
            action_rotate_ccw.triggered.connect(lambda: self.rotate_selected_signature(-90))

            menu.addSeparator()

        if self._pending_signature_data:
            action_cancel = menu.addAction("取消放置签名")
            action_cancel.triggered.connect(self._cancel_pending_signature)

        menu.exec(event.globalPos())

    def _cancel_pending_signature(self):
        self._pending_signature_data = None
        self.setCursor(Qt.CursorShape.ArrowCursor)


# 需要的 import(已在顶部导入 QBrush)
