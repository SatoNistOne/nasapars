import sys
from PySide6.QtWidgets import (QApplication, QMessageBox, QMainWindow, QWidget, 
                               QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget, 
                               QLabel, QPushButton, QFrame, QProgressBar)
from PySide6.QtCore import Qt, QSize, QTimer, QThreadPool, Signal
from PySide6.QtGui import QPalette, QColor, QShortcut, QKeySequence
from sqlalchemy import select, func
from db import init_db, SessionLocal, Image
from workers import BaseWorker
from seed import run_full_seed
import config
from ui_gallery import GalleryPage
from ui_collections import CollectionsPage
from ui_asteroids import AsteroidsPage
from ui_tags import TagsPage

def is_db_empty() -> bool:
    with SessionLocal() as s:
        count = s.execute(select(func.count()).select_from(Image)).scalar()
        return count == 0

class MainWindow(QMainWindow):
    seed_progress = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpaceVault")
        self.resize(1200, 750)
        
        self.history = []
        self.menu_visible = True
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        self.top_bar.setFixedHeight(64)
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        self.btn_menu_toggle = QPushButton("☰")
        self.btn_menu_toggle.setObjectName("back")
        self.btn_menu_toggle.setFixedWidth(48)
        self.btn_menu_toggle.clicked.connect(self.toggle_menu)
        top_layout.addWidget(self.btn_menu_toggle)
        
        self.btn_back = QPushButton("← Назад")
        self.btn_back.setObjectName("back")
        self.btn_back.setFixedWidth(120)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setVisible(False)
        top_layout.addWidget(self.btn_back)
        
        self.lbl_title = QLabel("SpaceVault")
        self.lbl_title.setObjectName("pageTitle")
        top_layout.addWidget(self.lbl_title)
        
        top_layout.addStretch()
        
        main_layout.addWidget(self.top_bar)
        
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        
        self.menu = QListWidget()
        self.menu.setFixedWidth(240)
        self.menu.setIconSize(QSize(20, 20))
        self.menu.addItem("  Галерея")
        self.menu.addItem("  Коллекции")
        self.menu.addItem("  Астероиды")
        self.menu.addItem("  Теги")
        self.menu.currentRowChanged.connect(self.change_root_page)
        body_layout.addWidget(self.menu)
        
        self.stack = QStackedWidget()
        
        self.gallery_page = GalleryPage(self)
        self.stack.addWidget(self.gallery_page)
        
        self.collections_page = CollectionsPage(self)
        self.stack.addWidget(self.collections_page)
        
        self.asteroids_page = AsteroidsPage(self)
        self.stack.addWidget(self.asteroids_page)
        
        self.tags_page = TagsPage(self)
        self.stack.addWidget(self.tags_page)
        
        body_layout.addWidget(self.stack, 1)
        
        main_layout.addWidget(body, 1)
        
        self.menu.setCurrentRow(0)
        
        self.setup_shortcuts()
        
        self.toast_label = QLabel(self)
        self.toast_label.setObjectName("toast")
        self.toast_label.setVisible(False)
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_timer = QTimer()
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.hide_toast)
        
        self.seed_overlay = QFrame(self)
        self.seed_overlay.setObjectName("card")
        overlay_layout = QVBoxLayout(self.seed_overlay)
        overlay_layout.setContentsMargins(24, 24, 24, 24)
        overlay_layout.setSpacing(12)
        self.seed_status = QLabel("Загрузка демо-данных...")
        self.seed_status.setObjectName("sectionTitle")
        self.seed_bar = QProgressBar()
        self.seed_bar.setRange(0, 100)
        self.seed_bar.setValue(0)
        overlay_layout.addWidget(self.seed_status)
        overlay_layout.addWidget(self.seed_bar)
        self.seed_overlay.setFixedWidth(420)
        self.seed_overlay.setVisible(False)
        
        QTimer.singleShot(500, self.check_first_run)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.center_seed_overlay()

    def center_seed_overlay(self):
        if self.seed_overlay.isVisible():
            self.seed_overlay.adjustSize()
            x = (self.width() - self.seed_overlay.width()) // 2
            y = (self.height() - self.seed_overlay.height()) // 2
            self.seed_overlay.move(x, y)

    def check_first_run(self):
        if is_db_empty():
            res = QMessageBox.question(
                self, "Пустая база",
                "База данных пуста. Загрузить демо-данные из NASA?\nТребуется подключение к интернету.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                self.start_seed()

    def start_seed(self):
        self.seed_overlay.setVisible(True)
        self.seed_bar.setRange(0, 0)
        self.seed_status.setText("Загрузка демо-данных...")
        self.center_seed_overlay()
        self.seed_overlay.raise_()
        
        worker = BaseWorker(run_full_seed, progress_callback=self.seed_progress.emit, reduced=True)
        self.seed_progress.connect(self.on_seed_progress)
        worker.signals.finished.connect(self.on_seed_finished)
        worker.signals.error.connect(self.on_seed_error)
        self.seed_worker = worker
        QThreadPool.globalInstance().start(worker)

    def on_seed_progress(self, current, total):
        self.seed_bar.setRange(0, total)
        self.seed_bar.setValue(current)
        self.seed_status.setText(f"Загрузка демо-данных: {current} из {total}")

    def on_seed_finished(self):
        self.seed_overlay.setVisible(False)
        self.show_toast("Демо-данные загружены", 5000)
        self.gallery_page.refresh()

    def on_seed_error(self, err):
        self.seed_overlay.setVisible(False)
        self.show_toast(f"Ошибка загрузки данных: {err}", 5000)

    def setup_shortcuts(self):
        shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_search.activated.connect(self.focus_search)
        
        shortcut_menu = QShortcut(QKeySequence("Ctrl+M"), self)
        shortcut_menu.activated.connect(self.toggle_menu)

    def focus_search(self):
        if self.stack.currentWidget() == self.gallery_page:
            self.gallery_page.search_edit.setFocus()
            self.gallery_page.search_edit.selectAll()

    def toggle_menu(self):
        self.menu_visible = not self.menu_visible
        self.menu.setVisible(self.menu_visible)

    def show_toast(self, message, duration=3000):
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        
        x = (self.width() - self.toast_label.width()) // 2
        y = self.height() - self.toast_label.height() - 30
        self.toast_label.move(x, y)
        self.toast_label.setVisible(True)
        self.toast_label.raise_()
        
        self.toast_timer.start(duration)

    def hide_toast(self):
        self.toast_label.setVisible(False)

    def change_root_page(self, index):
        self.history = []
        self.btn_back.setVisible(False)
        self.stack.setCurrentIndex(index)
        titles = ["Галерея", "Коллекции", "Астероиды", "Теги"]
        self.lbl_title.setText(titles[index] if 0 <= index < len(titles) else "SpaceVault")

    def navigate_to(self, widget, title):
        self.history.append((self.stack.currentWidget(), self.lbl_title.text()))
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        self.lbl_title.setText(title)
        self.btn_back.setVisible(True)
        self.menu.setVisible(False)

    def go_back(self):
        if self.history:
            prev_widget, prev_title = self.history.pop()
            current = self.stack.currentWidget()
            self.stack.removeWidget(current)
            current.deleteLater()
            self.stack.setCurrentWidget(prev_widget)
            self.lbl_title.setText(prev_title)
            if not self.history:
                self.btn_back.setVisible(False)
                self.menu.setVisible(self.menu_visible)

def apply_dark_theme(app):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#0f1115"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#e6e8ee"))
    p.setColor(QPalette.ColorRole.Base, QColor("#14161c"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#0f1115"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#e6e8ee"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#e6e8ee"))
    p.setColor(QPalette.ColorRole.Text, QColor("#e6e8ee"))
    p.setColor(QPalette.ColorRole.Button, QColor("#1b1e26"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#e6e8ee"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ff6b6b"))
    p.setColor(QPalette.ColorRole.Link, QColor("#6c7cff"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#6c7cff"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
    
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#6b7080"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6b7080"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6b7080"))
    
    app.setPalette(p)
    
    try:
        with open(config.QSS_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        pass

def show_error(title: str, text_value: str) -> None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(text_value)
    box.exec()

def main() -> None:
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    try:
        init_db()
    except Exception as exc:
        show_error("Ошибка инициализации БД", str(exc))
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()