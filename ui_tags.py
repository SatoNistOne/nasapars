from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                               QListWidgetItem, QLabel, QPushButton, QInputDialog, 
                               QMessageBox, QFrame)
from PySide6.QtCore import Qt
from repo import get_all_tags, rename_tag, delete_tag

class TagsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        header = QHBoxLayout()
        lbl_title = QLabel("Теги")
        lbl_title.setObjectName("pageTitle")
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        
        self.list_tags = QListWidget()
        card_layout.addWidget(self.list_tags, 1)
        
        btns = QHBoxLayout()
        self.btn_rename = QPushButton("Переименовать")
        self.btn_rename.clicked.connect(self.rename_tag_action)
        btns.addWidget(self.btn_rename)
        
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self.delete_tag_action)
        btns.addWidget(self.btn_delete)
        
        btns.addStretch()
        card_layout.addLayout(btns)
        
        layout.addWidget(card, 1)
        
        self.load_tags()

    def load_tags(self):
        self.list_tags.clear()
        tags = get_all_tags()
        for t in tags:
            item = QListWidgetItem(t.name)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.list_tags.addItem(item)

    def rename_tag_action(self):
        item = self.list_tags.currentItem()
        if not item:
            return
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        new_name, ok = QInputDialog.getText(self, "Переименовать тег", "Новое название:", text=item.text())
        if ok and new_name:
            rename_tag(tag_id, new_name)
            self.load_tags()
            self.window().show_toast("Тег переименован")

    def delete_tag_action(self):
        item = self.list_tags.currentItem()
        if not item:
            return
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        res = QMessageBox.question(self, "Удаление", "Удалить этот тег?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            delete_tag(tag_id)
            self.load_tags()
            self.window().show_toast("Тег удалён")