"""
Modern GUI Styling Module for TCKR
Provides a dark, modern theme for all dialogs with neon blue accents
"""

from PyQt5 import QtWidgets

# Modern dark theme stylesheet for dialogs
MODERN_DIALOG_STYLE = """
    QDialog {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a1d23, stop:1 #0f1115);
        border: 2px solid #2a2f38;
        border-radius: 12px;
    }
    
    QLabel {
        color: #e0e0e0;
        font-size: 11px;
        font-weight: 500;
        background: transparent;
    }
    
    QLineEdit, QSpinBox, QComboBox {
        background: #23272f;
        border: 1px solid #3a3f4a;
        border-radius: 6px;
        padding: 6px 10px;
        color: #ffffff;
        font-size: 11px;
        min-height: 20px;
    }
    
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border: 1px solid #00b3ff;
        background: #2a2f38;
    }
    
    QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
        background: #2a2f38;
        border: 1px solid #4a5160;
    }
    
    QCheckBox {
        color: #e0e0e0;
        font-size: 11px;
        spacing: 8px;
        background: transparent;
    }
    
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 2px solid #3a3f4a;
        border-radius: 4px;
        background: #23272f;
    }
    
    QCheckBox::indicator:hover {
        border: 2px solid #00b3ff;
        background: #2a2f38;
    }
    
    QCheckBox::indicator:checked {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #00b3ff, stop:1 #0088cc);
        border: 2px solid #00b3ff;
    }
    
    QGroupBox {
        color: #00b3ff;
        font-size: 12px;
        font-weight: 600;
        border: 1px solid #2a2f38;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 16px;
        background: #1a1d23;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 4px 12px;
        background: #23272f;
        border: 1px solid #3a3f4a;
        border-radius: 4px;
        left: 10px;
    }
    
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #2a2f38, stop:1 #23272f);
        border: 1px solid #3a3f4a;
        border-radius: 6px;
        padding: 6px 16px;
        color: #ffffff;
        font-size: 11px;
        font-weight: 500;
        min-width: 70px;
    }
    
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #3a3f4a, stop:1 #2a2f38);
        border: 1px solid #00b3ff;
    }
    
    QPushButton:pressed {
        background: #1a1d23;
        border: 1px solid #00b3ff;
    }
"""

# Accent button style (neon blue - for primary actions like OK, Save, Close)
ACCENT_BUTTON_STYLE = """
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #00b3ff, stop:1 #0088cc);
        border: 1px solid #00b3ff;
        border-radius: 6px;
        padding: 6px 16px;
        color: #ffffff;
        font-size: 11px;
        font-weight: 600;
        min-width: 70px;
    }
    
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #00d4ff, stop:1 #00b3ff);
        border: 1px solid #00d4ff;
    }
    
    QPushButton:pressed {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #0088cc, stop:1 #006699);
    }
"""

# Danger button style (red - for delete/remove actions)
DANGER_BUTTON_STYLE = """
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff4444, stop:1 #cc0000);
        border: 1px solid #ff4444;
        border-radius: 6px;
        padding: 6px 16px;
        color: #ffffff;
        font-size: 11px;
        font-weight: 600;
        min-width: 70px;
    }
    
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ff6666, stop:1 #ff4444);
        border: 1px solid #ff6666;
    }
    
    QPushButton:pressed {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #cc0000, stop:1 #990000);
    }
"""

# Success button style (green - for add/create actions)
SUCCESS_BUTTON_STYLE = """
    QPushButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #00cc66, stop:1 #009944);
        border: 1px solid #00cc66;
        border-radius: 6px;
        padding: 6px 16px;
        color: #ffffff;
        font-size: 11px;
        font-weight: 600;
        min-width: 70px;
    }
    
    QPushButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #00ff88, stop:1 #00cc66);
        border: 1px solid #00ff88;
    }
    
    QPushButton:pressed {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #009944, stop:1 #006633);
    }
"""


def apply_modern_theme(dialog):
    """Apply modern dark theme to a dialog"""
    dialog.setStyleSheet(MODERN_DIALOG_STYLE)


def make_accent_button(button):
    """Style a button with accent color (blue) for primary actions"""
    button.setStyleSheet(ACCENT_BUTTON_STYLE)


def make_danger_button(button):
    """Style a button with danger color (red) for destructive actions"""
    button.setStyleSheet(DANGER_BUTTON_STYLE)


def make_success_button(button):
    """Style a button with success color (green) for positive actions"""
    button.setStyleSheet(SUCCESS_BUTTON_STYLE)
