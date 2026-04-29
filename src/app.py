"""主窗口 - PDF 签名工具"""
import os
import sys
import tempfile

# 确保项目根目录在 sys.path 中（支持直接 python src/app.py 运行）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QFileDialog, QMessageBox, QListWidget,
    QListWidgetItem, QInputDialog, QToolBar, QStatusBar,
    QSpinBox, QGroupBox, QSlider, QSizePolicy, QDockWidget,
    QApplication, QAbstractItemView
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSignal, QByteArray, QBuffer, QIODevice,
    QMimeData, QTimer, QFileInfo
)
from PyQt6.QtGui import (
    QAction, QIcon, QPixmap, QImage, QDrag, QPainter, QFont,
    QKeySequence, QShortcut
)
from PyQt6.QtCore import QPoint

from src.pdf_viewer import PDFViewer
from src.signature_lib import SignatureLibrary
from src.signature_item import SignatureGraphicsItem
from src.image_utils import remove_white_background, image_to_qpixmap
from src.export import export_pdf_with_signatures, suggest_output_path


class SignatureListWidget(QListWidget):
    """签名库列表组件，支持拖拽"""
    
    signature_selected = pyqtSignal(bytes, str)  # image_data, sig_id
    
    def __init__(self, sig_lib: SignatureLibrary, parent=None):
        super().__init__(parent)
        self.sig_lib = sig_lib
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIconSize(QSize(60, 60))
        self.setMinimumWidth(150)
        self.setMaximumWidth(220)
        self._load_signatures()
    
    def _load_signatures(self):
        """加载签名库"""
        self.clear()
        for entry in self.sig_lib.entries:
            image_data = self.sig_lib.get_image_data(entry.id)
            if image_data:
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                icon = pixmap.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio, 
                                      Qt.TransformationMode.SmoothTransformation)
                item = QListWidgetItem(QIcon(icon), entry.name)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, image_data)
                item.setSizeHint(QSize(0, 70))
                self.addItem(item)
    
    def startDrag(self, supportedActions):
        """拖拽开始"""
        item = self.currentItem()
        if not item:
            return
        
        sig_id = item.data(Qt.ItemDataRole.UserRole)
        image_data = item.data(Qt.ItemDataRole.UserRole + 1)
        
        # 创建拖拽
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-signature-id", QByteArray(sig_id.encode()))
        drag.setMimeData(mime_data)
        
        # 设置拖拽缩略图
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        drag_pixmap = pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(50, 50))
        
        drag.exec(Qt.DropAction.CopyAction)
    
    def refresh(self):
        """刷新列表"""
        self._load_signatures()


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 签名工具")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        
        # 状态
        self._pdf_path = None
        self._pdf_data = None  # 如果是从 bytes 加载
        self._sig_lib = SignatureLibrary()
        self._modified = False
        
        self._setup_ui()
        self._setup_toolbar()
        self._setup_shortcuts()
        self._setup_statusbar()
        self._connect_signals()
        
        # 初始状态
        self._update_ui_state()
    
    def _setup_ui(self):
        """设置 UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        
        # 左侧：签名库
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(2, 2, 2, 2)
        
        lib_label = QLabel("📋 签名库")
        lib_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        left_layout.addWidget(lib_label)
        
        self.sig_list = SignatureListWidget(self._sig_lib, self)
        left_layout.addWidget(self.sig_list)
        
        # 签名库按钮
        btn_layout = QHBoxLayout()
        self.btn_add_sig = QPushButton("➕ 添加")
        self.btn_add_sig.setToolTip("上传签名图片")
        self.btn_del_sig = QPushButton("🗑️ 删除")
        self.btn_del_sig.setToolTip("删除选中的签名")
        btn_layout.addWidget(self.btn_add_sig)
        btn_layout.addWidget(self.btn_del_sig)
        left_layout.addLayout(btn_layout)
        
        self.btn_use_sig = QPushButton("📝 使用此签名")
        self.btn_use_sig.setToolTip("选择签名后在 PDF 上点击放置")
        self.btn_use_sig.setEnabled(False)
        left_layout.addWidget(self.btn_use_sig)
        
        left_panel.setMaximumWidth(220)
        left_panel.setMinimumWidth(160)
        
        # 中间：PDF 预览
        self.pdf_viewer = PDFViewer()
        
        # 右侧：签名属性面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(2, 2, 2, 2)
        
        prop_label = QLabel("⚙️ 签名属性")
        prop_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        right_layout.addWidget(prop_label)
        
        # 旋转控制
        rotate_group = QGroupBox("旋转")
        rotate_layout = QHBoxLayout(rotate_group)
        self.btn_rotate_ccw = QPushButton("↶ -90°")
        self.btn_rotate_cw = QPushButton("↷ +90°")
        rotate_layout.addWidget(self.btn_rotate_ccw)
        rotate_layout.addWidget(self.btn_rotate_cw)
        right_layout.addWidget(rotate_group)
        
        # 缩放控制
        scale_group = QGroupBox("缩放")
        scale_layout = QVBoxLayout(scale_group)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(10, 500)
        self.scale_slider.setValue(100)
        self.scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.scale_slider.setTickInterval(50)
        self.scale_label = QLabel("100%")
        scale_layout.addWidget(self.scale_label)
        scale_layout.addWidget(self.scale_slider)
        right_layout.addWidget(scale_group)
        
        # 操作按钮
        self.btn_delete_sig_on_page = QPushButton("🗑️ 删除页面上的签名")
        self.btn_delete_sig_on_page.setEnabled(False)
        right_layout.addWidget(self.btn_delete_sig_on_page)
        
        # 快捷键提示
        tips_group = QGroupBox("快捷键")
        tips_layout = QVBoxLayout(tips_group)
        tips = [
            "R - 旋转选中签名 90°",
            "Delete - 删除选中签名",
            "Ctrl+O - 打开文件",
            "Ctrl+S - 保存 PDF",
            "← → - 翻页",
            "Ctrl+滚轮 - 缩放视图",
        ]
        for tip in tips:
            lbl = QLabel(tip)
            lbl.setStyleSheet("font-size: 11px; color: #666;")
            tips_layout.addWidget(lbl)
        right_layout.addWidget(tips_group)
        
        right_layout.addStretch()
        right_panel.setMaximumWidth(200)
        right_panel.setMinimumWidth(160)
        
        # 布局
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.pdf_viewer)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        
        main_layout.addWidget(splitter)
    
    def _setup_toolbar(self):
        """设置工具栏"""
        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)
        
        # 文件操作
        action_open = QAction("📂 打开", self)
        action_open.setToolTip("打开 PDF 或 Word 文档 (Ctrl+O)")
        action_open.triggered.connect(self._on_open_file)
        toolbar.addAction(action_open)
        
        action_save = QAction("💾 保存", self)
        action_save.setToolTip("导出签名的 PDF (Ctrl+S)")
        action_save.triggered.connect(self._on_save_pdf)
        toolbar.addAction(action_save)
        
        toolbar.addSeparator()
        
        # 导航
        action_prev = QAction("◀ 上一页", self)
        action_prev.triggered.connect(self._on_prev_page)
        toolbar.addAction(action_prev)
        
        # 页码显示
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setPrefix("第 ")
        self.page_spin.setSuffix(" 页")
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        toolbar.addWidget(self.page_spin)
        
        action_next = QAction("下一页 ▶", self)
        action_next.triggered.connect(self._on_next_page)
        toolbar.addAction(action_next)
        
        toolbar.addSeparator()
        
        # 视图
        action_fit = QAction("🔍 适应窗口", self)
        action_fit.triggered.connect(self.pdf_viewer.fit_to_view)
        toolbar.addAction(action_fit)
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        QShortcut(QKeySequence("Ctrl+O"), self, self._on_open_file)
        QShortcut(QKeySequence("Ctrl+S"), self, self._on_save_pdf)
        QShortcut(QKeySequence("Left"), self, self._on_prev_page)
        QShortcut(QKeySequence("Right"), self, self._on_next_page)
    
    def _setup_statusbar(self):
        """设置状态栏"""
        self.statusBar().showMessage("就绪 - 拖入或打开 PDF/Word 文件开始")
        
        self.status_file = QLabel()
        self.status_page = QLabel()
        self.status_zoom = QLabel()
        
        self.statusBar().addPermanentWidget(self.status_file)
        self.statusBar().addPermanentWidget(self.status_page)
        self.statusBar().addPermanentWidget(self.status_zoom)
    
    def _connect_signals(self):
        """连接信号"""
        self.btn_add_sig.clicked.connect(self._on_add_signature)
        self.btn_del_sig.clicked.connect(self._on_del_signature)
        self.btn_use_sig.clicked.connect(self._on_use_signature)
        self.btn_rotate_ccw.clicked.connect(lambda: self.pdf_viewer.rotate_selected_signature(-90))
        self.btn_rotate_cw.clicked.connect(lambda: self.pdf_viewer.rotate_selected_signature(90))
        self.btn_delete_sig_on_page.clicked.connect(self.pdf_viewer.remove_selected_signature)
        
        self.sig_list.itemSelectionChanged.connect(self._on_sig_list_selection_changed)
        
        self.pdf_viewer.page_changed.connect(self._on_page_changed)
        self.pdf_viewer.signature_placed.connect(self._on_signature_placed)
        self.pdf_viewer.file_dropped.connect(self._load_file)
        self.pdf_viewer.signature_dropped.connect(self._on_signature_dropped)
        
        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        
        # 场景选择变化
        self.pdf_viewer.scene().selectionChanged.connect(self._on_scene_selection_changed)
    
    def _update_ui_state(self):
        """更新 UI 状态"""
        has_pdf = self.pdf_viewer.page_count > 0
        
        # 状态栏
        if self._pdf_path:
            self.status_file.setText(f"📄 {os.path.basename(self._pdf_path)}")
        else:
            self.status_file.setText("📄 未加载文件")
        
        if has_pdf:
            self.status_page.setText(f"  第 {self.pdf_viewer.current_page + 1}/{self.pdf_viewer.page_count} 页  ")
        else:
            self.status_page.setText("")
    
    def _load_file(self, file_path: str):
        """加载文件（PDF 或 Word）"""
        from src.word_converter import is_word_file, is_pdf_file, word_to_pdf
        import tempfile
        
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "错误", f"文件不存在: {file_path}")
            return
        
        if is_word_file(file_path):
            # Word 转 PDF - 使用 QThread 避免界面卡死
            if sys.platform != 'win32':
                QMessageBox.warning(
                    self, "不支持",
                    "Word 转 PDF 仅支持 Windows 系统。\n请先将 Word 另存为 PDF 后打开。"
                )
                return
            
            # 显示进度对话框
            from PyQt6.QtWidgets import QProgressDialog
            self.progress_dialog = QProgressDialog("正在转换 Word 文档...", "取消", 0, 100, self)
            self.progress_dialog.setWindowTitle("转换中")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.setValue(0)
            self.progress_dialog.setCancelButton(None)  # 不允许取消，COM 操作中途取消不安全
            self.progress_dialog.show()
            
            def on_progress(value, message):
                if hasattr(self, 'progress_dialog') and self.progress_dialog:
                    self.progress_dialog.setValue(value)
                    self.progress_dialog.setLabelText(message)
                    QApplication.processEvents()
            
            try:
                pdf_path = word_to_pdf(file_path, progress_callback=on_progress)
                self._pdf_path = pdf_path
                self._pdf_data = None
                success = self.pdf_viewer.load_pdf(pdf_path)
            except Exception as e:
                if hasattr(self, 'progress_dialog') and self.progress_dialog:
                    self.progress_dialog.close()
                    self.progress_dialog = None
                QMessageBox.critical(self, "转换失败", f"Word 转 PDF 失败:\n{e}")
                return
            
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.setValue(100)
                self.progress_dialog.close()
                self.progress_dialog = None
        elif is_pdf_file(file_path):
            self._pdf_path = file_path
            self._pdf_data = None
            success = self.pdf_viewer.load_pdf(file_path)
        else:
            QMessageBox.warning(self, "不支持", "仅支持 PDF 和 Word (.docx) 文件")
            return
        
        if success:
            self.page_spin.setMaximum(self.pdf_viewer.page_count)
            self.page_spin.setValue(1)
            self._modified = False
            self.statusBar().showMessage(f"已加载: {os.path.basename(file_path)}", 3000)
        
        self._update_ui_state()
    
    def _on_open_file(self):
        """打开文件对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开文件", "",
            "PDF 文件 (*.pdf);;Word 文档 (*.docx *.doc);;所有文件 (*)"
        )
        if file_path:
            self._load_file(file_path)
    
    def _on_save_pdf(self):
        """保存/导出 PDF"""
        if not self._pdf_path:
            QMessageBox.information(self, "提示", "请先打开一个 PDF 文件")
            return
        
        all_sigs = self.pdf_viewer.get_all_signatures()
        total_sigs = sum(len(v) for v in all_sigs.values())
        
        if total_sigs == 0:
            QMessageBox.information(self, "提示", "当前没有放置任何签名")
            return
        
        # 建议输出路径
        if self._pdf_data:
            # 从 bytes 加载的，用临时路径
            suggest = os.path.join(os.path.expanduser("~"), "Desktop", "signed.pdf")
        else:
            suggest = suggest_output_path(self._pdf_path)
        
        output_path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF", suggest,
            "PDF 文件 (*.pdf)"
        )
        
        if not output_path:
            return
        
        try:
            self.statusBar().showMessage("正在导出 PDF...")
            QApplication.processEvents()
            
            export_pdf_with_signatures(
                source_pdf_path=self._pdf_path,
                output_path=output_path,
                all_signatures=all_sigs,
                render_scale=self.pdf_viewer.get_page_render_scale(),
                source_is_bytes=self._pdf_data is not None,
                source_data=self._pdf_data,
            )
            
            self._modified = False
            self.statusBar().showMessage(f"✅ 已导出: {output_path}", 5000)
            QMessageBox.information(self, "导出成功", f"PDF 已保存到:\n{output_path}")
        
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 PDF 失败:\n{e}")
    
    def _on_add_signature(self):
        """添加签名到签名库"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择签名图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        try:
            # 去白底
            processed_data = remove_white_background(file_path)
            
            # 命名
            name, ok = QInputDialog.getText(
                self, "签名命名",
                "请输入签名名称:",
                text=f"签名 {self._sig_lib.count() + 1}"
            )
            
            if not ok or not name.strip():
                name = f"签名 {self._sig_lib.count() + 1}"
            
            self._sig_lib.add(name.strip(), processed_data)
            self.sig_list.refresh()
            self.statusBar().showMessage(f"已添加签名: {name}", 3000)
        
        except Exception as e:
            QMessageBox.critical(self, "添加失败", f"处理签名图片失败:\n{e}")
    
    def _on_del_signature(self):
        """从签名库删除签名"""
        item = self.sig_list.currentItem()
        if not item:
            return
        
        sig_id = item.data(Qt.ItemDataRole.UserRole)
        sig_name = item.text()
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从签名库中删除 \"{sig_name}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._sig_lib.remove(sig_id)
            self.sig_list.refresh()
    
    def _on_use_signature(self):
        """使用选中的签名"""
        item = self.sig_list.currentItem()
        if not item:
            return
        
        sig_id = item.data(Qt.ItemDataRole.UserRole)
        image_data = item.data(Qt.ItemDataRole.UserRole + 1)
        
        if image_data:
            self.pdf_viewer.set_pending_signature(image_data, sig_id)
            self.statusBar().showMessage("点击 PDF 页面放置签名，右键取消", 10000)
    
    def _on_sig_list_selection_changed(self):
        """签名库选择变化"""
        item = self.sig_list.currentItem()
        self.btn_use_sig.setEnabled(item is not None)
    
    def _on_page_changed(self, page_num):
        """页码变化"""
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_num + 1)
        self.page_spin.blockSignals(False)
        self._update_ui_state()
    
    def _on_page_spin_changed(self, value):
        """页码 spin 变化"""
        self.pdf_viewer.go_to_page(value - 1)
    
    def _on_prev_page(self):
        self.pdf_viewer.prev_page()
    
    def _on_next_page(self):
        self.pdf_viewer.next_page()
    
    def _on_signature_placed(self, item):
        """签名放置完成"""
        self._modified = True
        self.statusBar().showMessage("签名已放置，拖拽移动 / 滚轮缩放 / R 旋转", 5000)
    
    def _on_signature_dropped(self, sig_id, scene_pos):
        """签名从签名库拖入 PDF"""
        image_data = self._sig_lib.get_image_data(sig_id)
        if image_data:
            self.pdf_viewer.set_pending_signature(image_data, sig_id)
            self.pdf_viewer.place_signature_at(scene_pos)
            self._modified = True
    
    def _on_scene_selection_changed(self):
        """场景选择变化 - 更新属性面板"""
        from src.signature_item import SignatureGraphicsItem
        selected = [item for item in self.pdf_viewer.scene().selectedItems()
                    if isinstance(item, SignatureGraphicsItem)]
        
        has_selection = len(selected) > 0
        self.btn_delete_sig_on_page.setEnabled(has_selection)
        
        if has_selection:
            sig = selected[0]
            self.scale_slider.blockSignals(True)
            self.scale_slider.setValue(int(sig.scale_factor * 100))
            self.scale_slider.blockSignals(False)
            self.scale_label.setText(f"{int(sig.scale_factor * 100)}%")
    
    def _on_scale_changed(self, value):
        """缩放滑条变化"""
        from src.signature_item import SignatureGraphicsItem
        selected = [item for item in self.pdf_viewer.scene().selectedItems()
                    if isinstance(item, SignatureGraphicsItem)]
        
        for sig in selected:
            sig.scale_factor = value / 100.0
        
        self.scale_label.setText(f"{value}%")
    
    def dragEnterEvent(self, event):
        """窗口级拖拽"""
        mime = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """窗口级拖放"""
        mime = event.mimeData()
        if mime.hasUrls():
            url = mime.urls()[0]
            file_path = url.toLocalFile()
            if file_path:
                self._load_file(file_path)
                event.acceptProposedAction()
    
    def closeEvent(self, event):
        """关闭窗口"""
        if self._modified:
            reply = QMessageBox.question(
                self, "确认关闭",
                "有未保存的签名修改，确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        event.accept()


def main():
    """程序入口"""
    app = QApplication(sys.argv)
    app.setApplicationName("PDF 签名工具")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
