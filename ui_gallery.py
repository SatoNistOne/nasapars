from datetime import datetime

import requests as http_requests

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                               QComboBox, QCheckBox, QListWidget, QListWidgetItem, 
                               QLabel, QPushButton, QFormLayout, 
                               QSpinBox, QMessageBox, QScrollArea, QProgressBar, 
                               QInputDialog, QFrame, QGridLayout, QDateEdit, QMenu,
                               QFileDialog, QPlainTextEdit)
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QUrl, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon, QDesktopServices
from db import SessionLocal, Image
from repo import (get_filters_data, get_images, get_image_by_id, update_image, 
                  delete_image, add_tag_to_image, remove_tag_from_image, get_tags_for_image,
                  get_collections, add_image_to_collection, create_collection)
from workers import BaseWorker
from nasa import search_nasa, process_image_item, process_video_item, save_to_db
from config import IMAGES_DIR
from sqlalchemy import select

def translate_description(text: str) -> str | None:
    if not text:
        return None
    try:
        resp = http_requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "en|ru"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("responseData", {}).get("translatedText")
    except Exception:
        return None

class GalleryPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.pool = QThreadPool()
        self.current_offset = 0
        self.page_limit = 60
        self.total_items = 0
        
        self.init_ui()
        self.load_filters()
        self.apply_default_filter()
        self.load_images()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        header = QHBoxLayout()
        lbl_title = QLabel("Галерея снимков")
        lbl_title.setObjectName("pageTitle")
        header.addWidget(lbl_title)
        header.addStretch()
        
        self.btn_import = QPushButton("+ Импорт из NASA")
        self.btn_import.setObjectName("primary")
        self.btn_import.clicked.connect(self.open_import)
        header.addWidget(self.btn_import)
        
        layout.addLayout(header)
        
        search_panel = QFrame()
        search_panel.setObjectName("card")
        search_layout = QVBoxLayout(search_panel)
        search_layout.setSpacing(12)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию, описанию и тегам (на английском)...")
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.load_images)
        self.search_edit.textChanged.connect(lambda: self.search_timer.start())
        search_layout.addWidget(self.search_edit)
        
        filters_row = QHBoxLayout()
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Дата ↓", "Дата ↑", "Название", "Рейтинг", "Размер", "Миссия"])
        self.sort_combo.currentIndexChanged.connect(self.load_images)
        filters_row.addWidget(self.sort_combo)
        
        self.mission_combo = QComboBox()
        self.mission_combo.addItem("Все миссии", None)
        self.mission_combo.currentIndexChanged.connect(self.load_images)
        filters_row.addWidget(self.mission_combo)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Все типы", "Фото", "Видео"])
        self.type_combo.currentIndexChanged.connect(self.load_images)
        filters_row.addWidget(self.type_combo)
        
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("Все теги", None)
        self.tag_combo.currentIndexChanged.connect(self.load_images)
        filters_row.addWidget(self.tag_combo)
        
        filters_row.addWidget(QLabel("От:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setSpecialValueText("Любая")
        self.date_from.setMinimumDate(self.date_from.minimumDate())
        self.date_from.setDate(self.date_from.minimumDate())
        self.date_from.dateChanged.connect(self.load_images)
        filters_row.addWidget(self.date_from)
        
        filters_row.addWidget(QLabel("До:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setSpecialValueText("Любая")
        self.date_to.setMinimumDate(self.date_to.minimumDate())
        self.date_to.setDate(self.date_to.minimumDate())
        self.date_to.dateChanged.connect(self.load_images)
        filters_row.addWidget(self.date_to)
        
        self.fav_check = QCheckBox("Только избранное")
        self.fav_check.stateChanged.connect(self.load_images)
        filters_row.addWidget(self.fav_check)
        
        btn_reset = QPushButton("Сбросить фильтры")
        btn_reset.clicked.connect(self.reset_filters)
        filters_row.addWidget(btn_reset)
        
        filters_row.addStretch()
        search_layout.addLayout(filters_row)
        
        layout.addWidget(search_panel)
        
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(220, 220))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSpacing(16)
        self.list_widget.setGridSize(QSize(260, 280))
        self.list_widget.itemDoubleClicked.connect(self.open_card)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget, 1)
        
        pag_panel = QFrame()
        pag_panel.setObjectName("card")
        pag_layout = QHBoxLayout(pag_panel)
        pag_layout.setContentsMargins(16, 8, 16, 8)
        
        self.btn_prev = QPushButton("← Назад")
        self.btn_prev.clicked.connect(self.prev_page)
        pag_layout.addWidget(self.btn_prev)
        
        pag_layout.addStretch()
        self.lbl_page = QLabel()
        self.lbl_page.setObjectName("muted")
        pag_layout.addWidget(self.lbl_page)
        pag_layout.addStretch()
        
        self.btn_next = QPushButton("Вперёд →")
        self.btn_next.clicked.connect(self.next_page)
        pag_layout.addWidget(self.btn_next)
        
        layout.addWidget(pag_panel)

    def load_filters(self):
        missions, tags = get_filters_data()
        
        self.mission_combo.blockSignals(True)
        self.mission_combo.clear()
        self.mission_combo.addItem("Все миссии", None)
        for m in missions:
            self.mission_combo.addItem(m.name, m.id)
        self.mission_combo.blockSignals(False)
        
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("Все теги", None)
        for t in tags:
            self.tag_combo.addItem(t.name, t.id)
        self.tag_combo.blockSignals(False)

    def apply_default_filter(self):
        for i in range(self.mission_combo.count()):
            if self.mission_combo.itemText(i) == "Hubble":
                self.mission_combo.setCurrentIndex(i)
                return

    def reset_filters(self):
        self.search_edit.clear()
        self.sort_combo.setCurrentIndex(0)
        self.mission_combo.setCurrentIndex(0)
        self.type_combo.setCurrentIndex(0)
        self.tag_combo.setCurrentIndex(0)
        self.date_from.setDate(self.date_from.minimumDate())
        self.date_to.setDate(self.date_to.minimumDate())
        self.fav_check.setChecked(False)
        self.load_images()
        self.main_window.show_toast("Фильтры сброшены")

    def get_sort_key(self):
        idx = self.sort_combo.currentIndex()
        return ["date_desc", "date_asc", "title", "rating", "file_size", "mission"][idx]

    def get_media_type(self):
        idx = self.type_combo.currentIndex()
        if idx == 1: return "image"
        if idx == 2: return "video"
        return None

    def get_date_filter(self):
        date_from = None
        date_to = None
        
        if self.date_from.date() != self.date_from.minimumDate():
            date_from = datetime.combine(self.date_from.date().toPython(), datetime.min.time())
        
        if self.date_to.date() != self.date_to.minimumDate():
            date_to = datetime.combine(self.date_to.date().toPython(), datetime.max.time())
        
        return date_from, date_to

    def load_images(self):
        search = self.search_edit.text()
        sort = self.get_sort_key()
        mission_id = self.mission_combo.currentData()
        media_type = self.get_media_type()
        fav = self.fav_check.isChecked()
        tag_id = self.tag_combo.currentData()
        date_from, date_to = self.get_date_filter()
        
        images, total = get_images(
            search=search, sort=sort, mission_id=mission_id, media_type=media_type,
            favorite_only=fav, tag_id=tag_id, date_from=date_from, date_to=date_to,
            offset=self.current_offset, limit=self.page_limit
        )
        
        self.total_items = total
        self.list_widget.clear()
        
        for img in images:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, img.id)
            
            if img.thumbnail:
                qimg = QImage.fromData(img.thumbnail)
                pix = QPixmap.fromImage(qimg)
                scaled = pix.scaled(QSize(220, 220), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                item.setIcon(QIcon(scaled))
            else:
                item.setIcon(QIcon())
                
            title = img.title[:35]
            if len(img.title) > 35:
                title += "..."
            
            badges = []
            if img.is_favorite:
                badges.append("★")
            if img.media_type == "video":
                badges.append("▶")
            
            if badges:
                item.setText(" ".join(badges) + " " + title)
            else:
                item.setText(title)
            
            item.setSizeHint(QSize(260, 280))
            self.list_widget.addItem(item)
            
        self.update_pagination()

    def update_pagination(self):
        current_page = (self.current_offset // self.page_limit) + 1
        total_pages = max(1, (self.total_items + self.page_limit - 1) // self.page_limit)
        self.lbl_page.setText(f"Страница {current_page} из {total_pages} · всего {self.total_items}")
        self.btn_prev.setEnabled(self.current_offset > 0)
        self.btn_next.setEnabled(self.current_offset + self.page_limit < self.total_items)

    def prev_page(self):
        self.current_offset = max(0, self.current_offset - self.page_limit)
        self.load_images()

    def next_page(self):
        self.current_offset += self.page_limit
        self.load_images()

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        image_id = item.data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        action_open = menu.addAction("Открыть карточку")
        action_fav = menu.addAction("Переключить избранное")
        menu.addSeparator()
        action_collection = menu.addAction("Добавить в коллекцию")
        menu.addSeparator()
        action_delete = menu.addAction("Удалить")
        
        selected = menu.exec(self.list_widget.mapToGlobal(pos))
        
        if selected == action_open:
            self.open_card(item)
        elif selected == action_fav:
            self.toggle_favorite(image_id)
        elif selected == action_collection:
            self.add_to_collection_from_context(image_id)
        elif selected == action_delete:
            self.delete_from_context(image_id)

    def toggle_favorite(self, image_id):
        img = get_image_by_id(image_id)
        if img:
            update_image(image_id, is_favorite=not img.is_favorite)
            self.load_images()
            self.main_window.show_toast("Избранное обновлено")

    def add_to_collection_from_context(self, image_id):
        collections = get_collections()
        if not collections:
            res = QMessageBox.question(
                self, "Нет коллекций", 
                "Коллекции не найдены. Создать новую коллекцию?", 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                name, ok = QInputDialog.getText(self, "Новая коллекция", "Название коллекции:")
                if ok and name:
                    new_id = create_collection(name)
                    add_image_to_collection(new_id, image_id)
                    self.main_window.show_toast(f"Коллекция «{name}» создана, снимок добавлен")
            return
        
        names = [c.name for c in collections]
        name, ok = QInputDialog.getItem(self, "Выберите коллекцию", "Коллекция:", names, 0, False)
        if ok and name:
            for c in collections:
                if c.name == name:
                    add_image_to_collection(c.id, image_id)
                    self.main_window.show_toast("Снимок добавлен в коллекцию")
                    break

    def delete_from_context(self, image_id):
        res = QMessageBox.question(self, "Удаление", "Удалить этот снимок?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            delete_image(image_id)
            self.load_images()
            self.main_window.show_toast("Снимок удалён")

    def open_card(self, item):
        image_id = item.data(Qt.ItemDataRole.UserRole)
        card = ImageCardWidget(image_id, self)
        card.saved.connect(self.refresh)
        card.deleted.connect(self.refresh)
        self.main_window.navigate_to(card, "Карточка снимка")

    def open_import(self):
        imp = ImportWidget(self)
        imp.finished.connect(self.refresh)
        self.main_window.navigate_to(imp, "Импорт из NASA")

    def refresh(self):
        self.load_filters()
        self.load_images()


class ImageCardWidget(QWidget):
    saved = Signal()
    deleted = Signal()
    
    def __init__(self, image_id, gallery):
        super().__init__()
        self.image_id = image_id
        self.gallery = gallery
        self.img = get_image_by_id(image_id)
        self.rating_value = self.img.rating or 0
        self.show_translation = False
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)
        
        left = QVBoxLayout()
        left.setSpacing(16)
        
        image_frame = QFrame()
        image_frame.setObjectName("card")
        image_layout = QVBoxLayout(image_frame)
        image_layout.setContentsMargins(12, 12, 12, 12)
        
        self.lbl_image = QLabel("Загрузка...")
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setMinimumHeight(420)
        self.lbl_image.setObjectName("imageBox")
        image_layout.addWidget(self.lbl_image)
        left.addWidget(image_frame, 1)
        
        media_row = QHBoxLayout()
        media_row.setSpacing(12)
        
        if self.img.media_type == "video" and self.img.video_url and self.img.video_url != "unavailable":
            btn_video = QPushButton("▶ Открыть видео")
            btn_video.setObjectName("primary")
            btn_video.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.img.video_url)))
            media_row.addWidget(btn_video)
        
        source_url = self.get_source_url()
        if source_url:
            btn_source = QPushButton("Страница на сайте NASA")
            btn_source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(source_url)))
            media_row.addWidget(btn_source)
        
        if self.img.media_type == "image" and self.img.file_path:
            btn_export = QPushButton("Сохранить фото как...")
            btn_export.clicked.connect(self.export_image)
            media_row.addWidget(btn_export)
        
        media_row.addStretch()
        left.addLayout(media_row)
        
        layout.addLayout(left, 3)
        
        right = QVBoxLayout()
        right.setSpacing(16)
        
        lbl_title = QLabel(self.img.title)
        lbl_title.setObjectName("pageTitle")
        lbl_title.setWordWrap(True)
        right.addWidget(lbl_title)
        
        badges = QHBoxLayout()
        badges.setSpacing(8)
        
        type_badge = QLabel("ВИДЕО" if self.img.media_type == "video" else "ФОТО")
        type_badge.setObjectName("badgeVideo" if self.img.media_type == "video" else "badgeImage")
        badges.addWidget(type_badge)
        
        if self.img.mission:
            m_badge = QLabel(self.img.mission.name.upper())
            m_badge.setObjectName("badgeMission")
            badges.addWidget(m_badge)
        
        if self.img.is_favorite:
            f_badge = QLabel("★ ИЗБРАННОЕ")
            f_badge.setObjectName("badgeFav")
            badges.addWidget(f_badge)
        
        badges.addStretch()
        right.addLayout(badges)
        
        info_frame = QFrame()
        info_frame.setObjectName("card")
        info_layout = QGridLayout(info_frame)
        info_layout.setHorizontalSpacing(16)
        info_layout.setVerticalSpacing(8)
        
        size_text = f"{self.img.file_size / 1024 / 1024:.1f} МБ" if self.img.file_size else "—"
        
        info_rows = [
            ("Дата:", self.img.date_created.strftime('%d.%m.%Y') if self.img.date_created else "—"),
            ("Автор:", self.img.credit or "—"),
            ("Тип:", "Видео" if self.img.media_type == "video" else "Фото"),
            ("Размер:", size_text),
            ("ID NASA:", self.img.nasa_id),
        ]
        
        for row, (label, value) in enumerate(info_rows):
            l1 = QLabel(label)
            l1.setObjectName("muted")
            l2 = QLabel(str(value))
            l2.setWordWrap(True)
            info_layout.addWidget(l1, row, 0)
            info_layout.addWidget(l2, row, 1)
        
        right.addWidget(info_frame)
        
        desc_frame = QFrame()
        desc_frame.setObjectName("card")
        desc_layout = QVBoxLayout(desc_frame)
        desc_layout.setSpacing(8)
        
        desc_header = QHBoxLayout()
        lbl_desc_title = QLabel("Описание")
        lbl_desc_title.setObjectName("sectionTitle")
        desc_header.addWidget(lbl_desc_title)
        desc_header.addStretch()
        self.btn_translate = QPushButton("Перевести")
        self.btn_translate.setObjectName("link")
        self.btn_translate.clicked.connect(self.toggle_translation)
        desc_header.addWidget(self.btn_translate)
        desc_layout.addLayout(desc_header)
        
        self.lbl_desc = QLabel(self.img.description or "Нет описания")
        self.lbl_desc.setWordWrap(True)
        desc_layout.addWidget(self.lbl_desc)
        
        right.addWidget(desc_frame)
        
        tags_frame = QFrame()
        tags_frame.setObjectName("card")
        tags_layout_outer = QVBoxLayout(tags_frame)
        tags_layout_outer.setSpacing(8)
        
        lbl_tags_title = QLabel("Теги")
        lbl_tags_title.setObjectName("sectionTitle")
        tags_layout_outer.addWidget(lbl_tags_title)
        
        self.tags_grid = QGridLayout()
        self.tags_grid.setSpacing(8)
        tags_layout_outer.addLayout(self.tags_grid)
        
        right.addWidget(tags_frame)
        self.refresh_tags()
        
        rate_frame = QFrame()
        rate_frame.setObjectName("card")
        rate_layout = QHBoxLayout(rate_frame)
        rate_layout.setSpacing(8)
        
        rate_layout.addWidget(QLabel("Рейтинг:"))
        
        self.star_buttons = []
        for i in range(1, 6):
            b = QPushButton("☆")
            b.setObjectName("star")
            b.setFixedWidth(40)
            b.clicked.connect(lambda checked, v=i: self.set_rating(v))
            rate_layout.addWidget(b)
            self.star_buttons.append(b)
        
        rate_layout.addSpacing(16)
        self.chk_fav = QCheckBox("В избранном")
        self.chk_fav.setChecked(bool(self.img.is_favorite))
        rate_layout.addWidget(self.chk_fav)
        rate_layout.addStretch()
        
        right.addWidget(rate_frame)
        self.update_stars()
        
        notes_frame = QFrame()
        notes_frame.setObjectName("card")
        notes_layout = QVBoxLayout(notes_frame)
        notes_layout.setSpacing(8)
        
        lbl_notes = QLabel("Заметка")
        lbl_notes.setObjectName("sectionTitle")
        notes_layout.addWidget(lbl_notes)
        
        self.edit_notes = QPlainTextEdit(self.img.notes or "")
        self.edit_notes.setPlaceholderText("Личная заметка к снимку...")
        self.edit_notes.setMaximumHeight(100)
        notes_layout.addWidget(self.edit_notes)
        
        right.addWidget(notes_frame)
        
        actions = QHBoxLayout()
        actions.setSpacing(12)
        
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self.save)
        actions.addWidget(self.btn_save)
        
        collection_btn = QPushButton("Добавить в коллекцию")
        collection_btn.clicked.connect(self.add_to_collection)
        actions.addWidget(collection_btn)
        
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self.delete)
        actions.addWidget(self.btn_delete)
        
        actions.addStretch()
        right.addLayout(actions)
        
        layout.addLayout(right, 2)
        
        scroll.setWidget(content)
        outer.addWidget(scroll)
        
        QTimer.singleShot(50, self.load_image)

    def load_image(self):
        if self.img.media_type == "image" and self.img.file_path:
            path = IMAGES_DIR / self.img.file_path
            if path.exists():
                pix = QPixmap(str(path))
                self.lbl_image.setPixmap(pix.scaled(700, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                return
        if self.img.thumbnail:
            qimg = QImage.fromData(self.img.thumbnail)
            self.lbl_image.setPixmap(QPixmap.fromImage(qimg).scaled(700, 560, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            return
        self.lbl_image.setText("Нет изображения")

    def set_rating(self, value):
        if self.rating_value == value:
            self.rating_value = 0
        else:
            self.rating_value = value
        self.update_stars()

    def update_stars(self):
        for idx, b in enumerate(self.star_buttons):
            b.setText("★" if idx < self.rating_value else "☆")

    def toggle_translation(self):
        if self.show_translation:
            self.show_translation = False
            self.lbl_desc.setText(self.img.description or "Нет описания")
            self.btn_translate.setText("Перевести")
            return
        
        self.btn_translate.setText("Переводим...")
        self.btn_translate.setEnabled(False)
        worker = BaseWorker(translate_description, self.img.description or "")
        worker.signals.result.connect(self.on_translated)
        worker.signals.error.connect(self.on_translate_error)
        QThreadPool.globalInstance().start(worker)

    def on_translated(self, text):
        self.btn_translate.setEnabled(True)
        if text:
            self.show_translation = True
            self.lbl_desc.setText(text)
            self.btn_translate.setText("Оригинал")
        else:
            self.btn_translate.setText("Перевести")
            self.window().show_toast("Не удалось перевести описание")

    def on_translate_error(self, err):
        self.btn_translate.setEnabled(True)
        self.btn_translate.setText("Перевести")
        self.window().show_toast("Ошибка перевода")

    def export_image(self):
        if not self.img.file_path:
            return
        source = IMAGES_DIR / self.img.file_path
        if not source.exists():
            return
        
        default_name = f"{self.img.nasa_id}{source.suffix}"
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить изображение", default_name, "Images (*.jpg *.jpeg *.png)")
        if file_path:
            import shutil
            shutil.copy2(source, file_path)
            self.window().show_toast("Изображение сохранено")

    def get_source_url(self) -> str | None:
        nasa_id = self.img.nasa_id
        if not nasa_id:
            return None
        
        if nasa_id.startswith("apod-"):
            try:
                date_part = nasa_id.replace("apod-", "")
                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                yy = str(date_obj.year)[2:]
                mm = str(date_obj.month).zfill(2)
                dd = str(date_obj.day).zfill(2)
                return f"https://apod.nasa.gov/apod/ap{yy}{mm}{dd}.html"
            except Exception:
                return None
        else:
            return f"https://images.nasa.gov/details/{nasa_id}"

    def refresh_tags(self):
        while self.tags_grid.count():
            item = self.tags_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        tags = get_tags_for_image(self.image_id)
        for i, t in enumerate(tags):
            btn = QPushButton(f"× {t.name}")
            btn.setObjectName("chip")
            btn.clicked.connect(lambda checked, tid=t.id: self.remove_tag(tid))
            self.tags_grid.addWidget(btn, i // 3, i % 3)
        
        add = QPushButton("+ тег")
        add.setObjectName("chipAdd")
        add.clicked.connect(self.add_tag)
        self.tags_grid.addWidget(add, len(tags) // 3, len(tags) % 3)

    def add_tag(self):
        text, ok = QInputDialog.getText(self, "Новый тег", "Название тега:")
        if ok and text:
            add_tag_to_image(self.image_id, text)
            self.refresh_tags()
            self.gallery.load_filters()
            self.window().show_toast("Тег добавлен")

    def remove_tag(self, tag_id):
        res = QMessageBox.question(self, "Удаление тега", "Удалить этот тег из снимка?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            remove_tag_from_image(self.image_id, tag_id)
            self.refresh_tags()
            self.gallery.load_filters()
            self.window().show_toast("Тег удалён")

    def add_to_collection(self):
        collections = get_collections()
        if not collections:
            res = QMessageBox.question(
                self, "Нет коллекций", 
                "Коллекции не найдены. Создать новую коллекцию?", 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                name, ok = QInputDialog.getText(self, "Новая коллекция", "Название коллекции:")
                if ok and name:
                    new_id = create_collection(name)
                    add_image_to_collection(new_id, self.image_id)
                    self.window().show_toast(f"Коллекция «{name}» создана, снимок добавлен")
            return
        
        names = [c.name for c in collections]
        name, ok = QInputDialog.getItem(self, "Выберите коллекцию", "Коллекция:", names, 0, False)
        if ok and name:
            for c in collections:
                if c.name == name:
                    add_image_to_collection(c.id, self.image_id)
                    self.window().show_toast("Снимок добавлен в коллекцию")
                    break

    def save(self):
        update_image(
            self.image_id,
            rating=self.rating_value,
            is_favorite=self.chk_fav.isChecked(),
            notes=self.edit_notes.toPlainText()
        )
        self.saved.emit()
        self.window().show_toast("Изменения сохранены")

    def delete(self):
        res = QMessageBox.question(self, "Удаление", "Удалить этот снимок?", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            delete_image(self.image_id)
            self.deleted.emit()
            self.window().go_back()


class ImportWidget(QWidget):
    finished = Signal()
    
    def __init__(self, gallery):
        super().__init__()
        self.gallery = gallery
        self.pool = QThreadPool()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        
        lbl_title = QLabel("Импорт из NASA")
        lbl_title.setObjectName("pageTitle")
        card_layout.addWidget(lbl_title)
        
        lbl_sub = QLabel("Загрузите снимки или видео из библиотеки изображений NASA")
        lbl_sub.setObjectName("muted")
        card_layout.addWidget(lbl_sub)
        
        form = QFormLayout()
        form.setSpacing(12)
        
        self.edit_query = QLineEdit("hubble")
        form.addRow("Поисковый запрос:", self.edit_query)
        
        self.combo_type = QComboBox()
        self.combo_type.addItems(["image", "video"])
        form.addRow("Тип медиа:", self.combo_type)
        
        self.spin_count = QSpinBox()
        self.spin_count.setRange(10, 100)
        self.spin_count.setValue(20)
        form.addRow("Количество:", self.spin_count)
        
        card_layout.addLayout(form)
        
        btns = QHBoxLayout()
        self.btn_start = QPushButton("Начать импорт")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start_import)
        btns.addWidget(self.btn_start)
        btns.addStretch()
        card_layout.addLayout(btns)
        
        layout.addWidget(card)
        
        self.progress_card = QFrame()
        self.progress_card.setObjectName("card")
        self.progress_card.setVisible(False)
        pc_layout = QVBoxLayout(self.progress_card)
        pc_layout.setSpacing(12)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        pc_layout.addWidget(self.progress)
        
        self.lbl_status = QLabel("Загрузка...")
        self.lbl_status.setObjectName("muted")
        pc_layout.addWidget(self.lbl_status)
        
        layout.addWidget(self.progress_card)
        
        layout.addStretch()

    def start_import(self):
        query = self.edit_query.text()
        mtype = self.combo_type.currentText()
        count = self.spin_count.value()
        
        self.progress_card.setVisible(True)
        self.btn_start.setEnabled(False)
        self.lbl_status.setText("Загрузка данных...")
        
        worker = BaseWorker(self.do_import, query, mtype, count)
        worker.signals.result.connect(self.on_success)
        worker.signals.error.connect(self.on_error)
        self.pool.start(worker)

    def do_import(self, query, mtype, count):
        items = search_nasa(query, mtype, page_size=count)
        added = 0
        skipped = 0
        for item in items:
            if mtype == "image":
                res = process_image_item(item)
            else:
                res = process_video_item(item)
            if res:
                with SessionLocal() as s:
                    existing = s.execute(select(Image).where(Image.nasa_id == res["nasa_id"])).scalar_one_or_none()
                    if existing:
                        skipped += 1
                        continue
                save_to_db(res)
                added += 1
            else:
                skipped += 1
        return added, skipped

    def on_success(self, result):
        added, skipped = result
        self.lbl_status.setText(f"Готово: добавлено {added}, пропущено {skipped}")
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)
        self.finished.emit()
        self.window().show_toast(f"Импорт завершён: {added} добавлено, {skipped} пропущено")

    def on_error(self, err):
        self.lbl_status.setText(f"Ошибка: {err}")
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)