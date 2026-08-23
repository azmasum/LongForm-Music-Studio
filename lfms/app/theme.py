"""Dark application theme (Tokyo-night inspired palette + QSS)."""
from __future__ import annotations

BG_DARK = "#1a1b26"
BG_PANEL = "#16161e"
BG_ELEVATED = "#24283b"
BORDER = "#2f334d"
TEXT = "#c0caf5"
TEXT_DIM = "#565f89"
ACCENT = "#7aa2f7"
ACCENT_HOVER = "#89ddff"
POSITIVE = "#9ece6a"
WARNING = "#e0af68"
DANGER = "#f7768e"

FONT_FAMILY = '"Segoe UI", "Inter", sans-serif'

DARK_QSS = f"""
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QMainWindow::separator {{
    background: {BORDER};
    width: 3px;
}}
QListWidget#sidebar {{
    background-color: {BG_PANEL};
    border: none;
    border-right: 1px solid {BORDER};
    font-size: 14px;
    outline: 0;
}}
QListWidget#sidebar::item {{
    padding: 12px 16px;
    border-left: 3px solid transparent;
}}
QListWidget#sidebar::item:selected {{
    background: {BG_ELEVATED};
    border-left: 3px solid {ACCENT};
    color: {ACCENT_HOVER};
}}
QListWidget#sidebar::item:hover:!selected {{
    background: {BG_ELEVATED};
}}
QPushButton {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background-color: {BG_PANEL}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    color: {BG_DARK};
    font-weight: 600;
    border: none;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HOVER}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QLabel#page-title {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#muted {{ color: {TEXT_DIM}; }}
QStatusBar {{
    background: {BG_PANEL};
    border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
}}
QFrame#transport {{
    background: {BG_PANEL};
    border-top: 1px solid {BORDER};
}}
QFrame#card {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QProgressBar {{
    background: {BG_ELEVATED};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {TEXT_DIM};
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
"""
