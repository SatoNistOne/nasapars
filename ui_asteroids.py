from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QCheckBox, QDateEdit, QTableWidget, 
                               QTableWidgetItem, QFrame)
from PySide6.QtCore import Qt, QDate, QThreadPool
from PySide6.QtGui import QColor
from PySide6.QtCharts import (QChart, QChartView, QBarSeries, QBarSet, 
                              QBarCategoryAxis, QValueAxis, QScatterSeries)
from repo import get_asteroids
from workers import BaseWorker
from nasa import import_neows_range

class AsteroidsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.pool = QThreadPool()
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        header = QHBoxLayout()
        lbl_title = QLabel("Астероиды")
        lbl_title.setObjectName("pageTitle")
        header.addWidget(lbl_title)
        header.addStretch()
        layout.addLayout(header)
        
        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QHBoxLayout(controls)
        
        controls_layout.addWidget(QLabel("Начало:"))
        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate().addDays(-7))
        controls_layout.addWidget(self.date_start)
        
        controls_layout.addWidget(QLabel("Конец:"))
        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        controls_layout.addWidget(self.date_end)
        
        self.btn_load = QPushButton("Загрузить данные")
        self.btn_load.setObjectName("primary")
        self.btn_load.clicked.connect(self.load_from_api)
        controls_layout.addWidget(self.btn_load)
        
        self.chk_hazardous = QCheckBox("Только потенциально опасные")
        self.chk_hazardous.stateChanged.connect(self.refresh_table)
        controls_layout.addWidget(self.chk_hazardous)
        
        controls_layout.addStretch()
        layout.addWidget(controls)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Название", "Диаметр (м)", "Опасный", "Дата сближения", 
            "Скорость (км/с)", "Расстояние (км)", "Neo ID"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)
        
        charts_layout = QHBoxLayout()
        
        self.chart_bar = self.create_bar_chart()
        self.chart_scatter = self.create_scatter_chart()
        
        charts_layout.addWidget(QChartView(self.chart_bar), 1)
        charts_layout.addWidget(QChartView(self.chart_scatter), 1)
        
        layout.addLayout(charts_layout, 1)
        
        self.refresh_table()

    def load_from_api(self):
        start = datetime.combine(self.date_start.date().toPython(), datetime.min.time())
        end = datetime.combine(self.date_end.date().toPython(), datetime.max.time())
        
        self.btn_load.setEnabled(False)
        self.btn_load.setText("Загрузка...")
        
        worker = BaseWorker(import_neows_range, start_date=start, end_date=end)
        worker.signals.finished.connect(self.on_load_finished)
        worker.signals.error.connect(self.on_load_error)
        self.pool.start(worker)

    def on_load_finished(self):
        self.btn_load.setEnabled(True)
        self.btn_load.setText("Загрузить данные")
        self.refresh_table()

    def on_load_error(self, err):
        self.btn_load.setEnabled(True)
        self.btn_load.setText("Загрузить данные")

    def refresh_table(self):
        start = datetime.combine(self.date_start.date().toPython(), datetime.min.time())
        end = datetime.combine(self.date_end.date().toPython(), datetime.max.time())
        hazardous_only = self.chk_hazardous.isChecked()
        
        asteroids = get_asteroids(start, end, hazardous_only)
        
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(asteroids))
        
        danger_color = QColor(255, 107, 107)
        
        for row, a in enumerate(asteroids):
            self.table.setItem(row, 0, QTableWidgetItem(a.name))
            self.table.setItem(row, 1, QTableWidgetItem(f"{a.diameter_max_m:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem("Да" if a.is_hazardous else "Нет"))
            self.table.setItem(row, 3, QTableWidgetItem(a.approach_date.strftime('%Y-%m-%d')))
            self.table.setItem(row, 4, QTableWidgetItem(f"{a.velocity_kms:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{a.miss_distance_km:.0f}"))
            self.table.setItem(row, 6, QTableWidgetItem(a.neo_id))
            
            if a.is_hazardous:
                for col in range(7):
                    item = self.table.item(row, col)
                    item.setForeground(danger_color)
        
        self.table.setSortingEnabled(True)
        self.update_charts(asteroids)

    def create_bar_chart(self):
        chart = QChart()
        chart.setTitle("Сближения по дням")
        chart.setBackgroundBrush(QColor("#14161c"))
        chart.setTitleBrush(QColor("#e6e8ee"))
        return chart

    def create_scatter_chart(self):
        chart = QChart()
        chart.setTitle("Диаметр против расстояния")
        chart.setBackgroundBrush(QColor("#14161c"))
        chart.setTitleBrush(QColor("#e6e8ee"))
        return chart

    def update_charts(self, asteroids):
        self.update_bar_chart(asteroids)
        self.update_scatter_chart(asteroids)

    def update_bar_chart(self, asteroids):
        counts = {}
        for a in asteroids:
            date_key = a.approach_date.strftime('%Y-%m-%d')
            counts[date_key] = counts.get(date_key, 0) + 1
        
        categories = sorted(counts.keys())
        values = [counts[c] for c in categories]
        
        bar_set = QBarSet("Сближения")
        bar_set.append(values)
        bar_set.setColor(QColor("#6c7cff"))
        
        series = QBarSeries()
        series.append(bar_set)
        
        self.chart_bar.removeAllSeries()
        for axis in self.chart_bar.axes():
            self.chart_bar.removeAxis(axis)
        self.chart_bar.addSeries(series)
        
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor("#e6e8ee"))
        self.chart_bar.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)
        
        axis_y = QValueAxis()
        axis_y.setRange(0, max(values) + 1 if values else 1)
        axis_y.setLabelsColor(QColor("#e6e8ee"))
        self.chart_bar.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

    def update_scatter_chart(self, asteroids):
        series = QScatterSeries()
        series.setName("Астероиды")
        series.setColor(QColor("#6c7cff"))
        series.setMarkerSize(10)
        
        for a in asteroids:
            series.append(a.miss_distance_km, a.diameter_max_m)
        
        self.chart_scatter.removeAllSeries()
        for axis in self.chart_scatter.axes():
            self.chart_scatter.removeAxis(axis)
        self.chart_scatter.addSeries(series)
        
        axis_x = QValueAxis()
        axis_x.setTitleText("Расстояние (км)")
        axis_x.setTitleBrush(QColor("#e6e8ee"))
        axis_x.setLabelsColor(QColor("#e6e8ee"))
        if asteroids:
            max_x = max(a.miss_distance_km for a in asteroids)
            axis_x.setRange(0, max_x * 1.1)
        self.chart_scatter.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)
        
        axis_y = QValueAxis()
        axis_y.setTitleText("Диаметр (м)")
        axis_y.setTitleBrush(QColor("#e6e8ee"))
        axis_y.setLabelsColor(QColor("#e6e8ee"))
        if asteroids:
            max_y = max(a.diameter_max_m for a in asteroids)
            axis_y.setRange(0, max_y * 1.1)
        self.chart_scatter.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)