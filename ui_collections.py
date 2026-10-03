from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                               QListWidgetItem, QLabel, QPushButton, QInputDialog, 
                               QMessageBox, QFrame, QFileDialog, QDialog, QLineEdit)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QPixmap, QImage, QIcon, QTextDocument, QPageSize, QPdfWriter
from repo import (get_collections, create_collection, rename_collection, delete_collection,
                  get_collection_images, add_image_to_collection, remove_image_from_collection,
                  get_all_images_for_dialog, get_collection_count)
from config import IMAGES_DIR

class CollectionsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_collection_id = None
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        
        left_panel = QFrame()
        left_panel.setObjectName("card")
        left_layout = QVBoxLayout(left_panel)
        
        lbl_title = QLabel("Коллекции")
        lbl_title.setObjectName("pageTitle")
        left_layout.addWidget(lbl_title)
        
        self.list_collections = QListWidget()
        self.list_collections.itemSelectionChanged.connect(self.on_collection_selected)
        left_layout.addWidget(self.list_collections, 1)
        
        btns = QHBoxLayout()
        self.btn_create = QPushButton("+ Создать")
        self.btn_create.setObjectName("primary")
        self.btn_create.clicked.connect(self.create_collection)
        btns.addWidget(self.btn_create)
        
        self.btn_rename = QPushButton("Переименовать")
        self.btn_rename.clicked.connect(self.rename_collection_action)
        btns.addWidget(self.btn_rename)
        
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self.delete_collection_action)
        btns.addWidget(self.btn_delete)
        
        left_layout.addLayout(btns)
        
        layout.addWidget(left_panel, 1)
        
        right_panel = QFrame()
        right_panel.setObjectName("card")
        right_layout = QVBoxLayout(right_panel)
        
        self.lbl_collection_name = QLabel("Выберите коллекцию")
        self.lbl_collection_name.setObjectName("pageTitle")
        right_layout.addWidget(self.lbl_collection_name)
        
        actions = QHBoxLayout()
        self.btn_add_image = QPushButton("+ Добавить снимок")
        self.btn_add_image.clicked.connect(self.add_image)
        self.btn_add_image.setEnabled(False)
        actions.addWidget(self.btn_add_image)
        
        self.btn_export_pdf = QPushButton("Экспорт в PDF")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_export_pdf.setEnabled(False)
        actions.addWidget(self.btn_export_pdf)
        
        actions.addStretch()
        right_layout.addLayout(actions)
        
        self.list_images = QListWidget()
        self.list_images.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_images.setIconSize(QSize(180, 180))
        self.list_images.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_images.setMovement(QListWidget.Movement.Static)
        self.list_images.setSpacing(12)
        self.list_images.setGridSize(QSize(220, 240))
        right_layout.addWidget(self.list_images, 1)
        
        self.btn_remove_image = QPushButton("Удалить выбранный снимок из коллекции")
        self.btn_remove_image.setObjectName("danger")
        self.btn_remove_image.clicked.connect(self.remove_image)
        self.btn_remove_image.setEnabled(False)
        right_layout.addWidget(self.btn_remove_image)
        
        layout.addWidget(right_panel, 2)
        
        self.load_collections()

    def load_collections(self):
        self.list_collections.clear()
        collections = get_collections()
        for c in collections:
            count = get_collection_count(c.id)
            item = QListWidgetItem(f"{c.name} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self.list_collections.addItem(item)
        if collections:
            self.list_collections.setCurrentRow(0)

    def on_collection_selected(self):
        item = self.list_collections.currentItem()
        if item:
            self.current_collection_id = item.data(Qt.ItemDataRole.UserRole)
            self.lbl_collection_name.setText(item.text())
            self.btn_add_image.setEnabled(True)
            self.btn_export_pdf.setEnabled(True)
            self.btn_remove_image.setEnabled(True)
            self.load_collection_images()
        else:
            self.current_collection_id = None
            self.lbl_collection_name.setText("Выберите коллекцию")
            self.btn_add_image.setEnabled(False)
            self.btn_export_pdf.setEnabled(False)
            self.btn_remove_image.setEnabled(False)
            self.list_images.clear()

    def load_collection_images(self):
        self.list_images.clear()
        images = get_collection_images(self.current_collection_id)
        for img in images:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, img.id)
            if img.thumbnail:
                qimg = QImage.fromData(img.thumbnail)
                pix = QPixmap.fromImage(qimg)
                item.setIcon(QIcon(pix.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            title = img.title[:25]
            if len(img.title) > 25:
                title += "..."
            item.setText(title)
            item.setSizeHint(QSize(220, 240))
            self.list_images.addItem(item)

    def create_collection(self):
        name, ok = QInputDialog.getText(self, "Новая коллекция", "Название:")
        if ok and name:
            create_collection(name)
            self.load_collections()

    def rename_collection_action(self):
        if not self.current_collection_id:
            return
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое название:")
        if ok and name:
            rename_collection(self.current_collection_id, name)
            self.load_collections()

    def delete_collection_action(self):
        if not self.current_collection_id:
            return
        res = QMessageBox.question(self, "Удаление", "Удалить коллекцию?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            delete_collection(self.current_collection_id)
            self.load_collections()

    def add_image(self):
        dialog = AddImageDialog(self)
        if dialog.exec():
            self.load_collection_images()
            self.load_collections()

    def remove_image(self):
        item = self.list_images.currentItem()
        if item:
            image_id = item.data(Qt.ItemDataRole.UserRole)
            res = QMessageBox.question(self, "Удаление", "Удалить снимок из коллекции?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res == QMessageBox.StandardButton.Yes:
                remove_image_from_collection(self.current_collection_id, image_id)
                self.load_collection_images()
                self.load_collections()

    def export_pdf(self):
        if not self.current_collection_id:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить PDF", "collection.pdf", "PDF Files (*.pdf)")
        if file_path:
            self.generate_pdf(file_path)
            self.window().show_toast("Коллекция экспортирована в PDF")

    def generate_pdf(self, file_path):
        images = get_collection_images(self.current_collection_id)
        if not images:
            return
            
        writer = QPdfWriter(file_path)
        writer.setPageSize(QPageSize(QPageSize.Id.A4))
        writer.setResolution(96)
        
        document = QTextDocument()
        html = f"<h1>{self.lbl_collection_name.text()}</h1><hr>"
        
        for img in images:
            img_html = ""
            if img.media_type == "image" and img.file_path:
                path = IMAGES_DIR / img.file_path
                if path.exists():
                    pix = QPixmap(str(path))
                    document.addResource(QTextDocument.ImageResource, QUrl(f"img_{img.id}"), pix)
                    img_html = f'<img src="img_{img.id}" width="300" />'
            elif img.thumbnail:
                qimg = QImage.fromData(img.thumbnail)
                pix = QPixmap.fromImage(qimg)
                document.addResource(QTextDocument.ImageResource, QUrl(f"img_{img.id}"), pix)
                img_html = f'<img src="img_{img.id}" width="300" />'
            
            date_str = img.date_created.strftime('%d.%m.%Y') if img.date_created else "—"
            credit = img.credit or "—"
            desc = img.description or ""
            
            html += f"""
            <div style="margin-bottom: 20px; page-break-inside: avoid;">
                {img_html}
                <h3>{img.title}</h3>
                <p><b>Дата:</b> {date_str}</p>
                <p><b>Автор:</b> {credit}</p>
                <p>{desc}</p>
            </div>
            <hr>
            """
            
        document.setHtml(html)
        document.print(writer)


class AddImageDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Добавить снимок")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию...")
        self.search_edit.textChanged.connect(self.load_images)
        layout.addWidget(self.search_edit)
        
        self.list_images = QListWidget()
        self.list_images.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.list_images)
        
        btns = QHBoxLayout()
        btn_add = QPushButton("Добавить")
        btn_add.setObjectName("primary")
        btn_add.clicked.connect(self.add_selected)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_add)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)
        
        self.load_images()

    def load_images(self):
        self.list_images.clear()
        search = self.search_edit.text()
        images = get_all_images_for_dialog(search)
        for img in images:
            item = QListWidgetItem(img.title)
            item.setData(Qt.ItemDataRole.UserRole, img.id)
            self.list_images.addItem(item)

    def add_selected(self):
        selected = self.list_images.selectedItems()
        for item in selected:
            image_id = item.data(Qt.ItemDataRole.UserRole)
            add_image_to_collection(self.parent().current_collection_id, image_id)
        self.accept()