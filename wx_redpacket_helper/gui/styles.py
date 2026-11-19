QSS = """
QWidget {
    background: #1a1a1a;
    color: #d4af37;
    font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background: #1a1a1a;
}

QLabel {
    color: #d4af37;
}

QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 14px;
    color: #d4af37;
    font-weight: bold;
    background: #222222;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #f5c842;
    font-size: 13px;
    font-weight: bold;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    border: none;
    background: #2a2a2a;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #4a4a4a;
    min-height: 30px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #d4af37;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QSpinBox, QLineEdit, QComboBox {
    background: #2a2a2a;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 5px 10px;
    color: #d4af37;
    selection-background-color: #d4af37;
    selection-color: #1a1a1a;
    min-height: 22px;
}

QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #f5c842;
}

QSpinBox::up-button, QComboBox::down-arrow {
    width: 18px;
    height: 18px;
    background: #3a3a3a;
    border-radius: 4px;
}

QSpinBox::up-button:hover, QComboBox::down-arrow:hover {
    background: #d4af37;
}

QRadioButton {
    spacing: 8px;
    color: #d4af37;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #5a5a5a;
    border-radius: 8px;
    background: #2a2a2a;
}

QRadioButton::indicator:checked {
    background: qradialgradient(cx:0.5,cy:0.5,radius:0.5, fx:0.25,fy:0.25, stop:0 #f5c842, stop:1 #d4af37);
    border: 2px solid #d4af37;
}

QCheckBox {
    spacing: 8px;
    color: #d4af37;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #5a5a5a;
    border-radius: 4px;
    background: #2a2a2a;
}

QCheckBox::indicator:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #d4af37, stop:1 #f5c842);
    border: 1px solid #f5c842;
}

QButtonGroup {
    border: none;
}

QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #b8941e, stop:1 #f5d442);
    color: #1a1a1a;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 14px;
    min-height: 24px;
}

QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #d4af37, stop:1 #ffe066);
}

QPushButton:pressed {
    background: #9a7a10;
}

QPushButton:disabled {
    background: #3a3a3a;
    color: #6a6a6a;
}

QListWidget {
    background: #222222;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    color: #d4af37;
    padding: 4px;
}

QListWidget::item {
    padding: 6px 10px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background: #3a3000;
    color: #f5c842;
}

QListWidget::item:hover {
    background: #2e2e2e;
}

QTabWidget::pane {
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    background: #222222;
}

QTabBar::tab {
    background: #2a2a2a;
    color: #d4af37;
    border: 1px solid #3a3a3a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 20px;
    margin-right: 2px;
    min-width: 80px;
}

QTabBar::tab:selected {
    background: #d4af37;
    color: #1a1a1a;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background: #3a3a3a;
}

QStatusBar {
    background: #222222;
    color: #888888;
    border-top: 1px solid #3a3a3a;
}

QStatusBar QLabel {
    color: #888888;
}

QFrame#frame_status {
    background: #222222;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
}

QTextBrowser {
    background: #1e1e1e;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    color: #aaaaaa;
    font-family: Consolas, "Courier New", monospace;
    font-size: 11px;
}
"""

LOG_QSS = """
QTextBrowser {
    background: #141414;
    border: 1px solid #2e2e2e;
    border-radius: 6px;
    color: #cccccc;
    font-family: Consolas, "Courier New", "Menlo", monospace;
    font-size: 12px;
    padding: 6px;
    selection-background-color: #d4af37;
    selection-color: #1a1a1a;
}
"""
