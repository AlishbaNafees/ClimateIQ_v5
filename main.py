"""
main.py  —  ClimateIQ v5  Entry Point
═══════════════════════════════════════
Run this file to launch the application:
    python main.py
"""

import sys
import os

# ── PyInstaller compatibility ─────────────────────────────────────────────────
# When packaged as an EXE, __file__ points inside the temp _MEIPASS folder.
# We need the project root on sys.path so all imports work correctly.
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle
    _BASE_DIR = sys._MEIPASS
else:
    # Running as normal Python script
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _BASE_DIR)

# Set working directory to base so relative paths (database/) resolve correctly
os.chdir(_BASE_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Global font
    app.setFont(QFont("Segoe UI", 10))

    # Global stylesheet tweaks (scrollbars, tooltips, combo boxes)
    app.setStyleSheet("""
        QToolTip {
            background-color: #0A1C50;
            color: #FFFFFF;
            border: 1px solid #2563EB;
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 9pt;
        }
        QComboBox {
            background: #0A1C50;
            color: #FFFFFF;
            border: 1px solid #2563EB;
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 9pt;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox QAbstractItemView {
            background: #071336;
            color: #FFFFFF;
            selection-background-color: #2563EB;
            border: 1px solid #2563EB;
        }
        QDateEdit {
            background: #0A1C50;
            color: #FFFFFF;
            border: 1px solid #2563EB;
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 9pt;
        }
        QDateEdit::drop-down {
            border: none;
            width: 20px;
        }
        QCalendarWidget {
            background: #071336;
            color: #FFFFFF;
        }
        QCalendarWidget QToolButton {
            color: #FFFFFF;
            background: #0A1C50;
        }
        QCalendarWidget QAbstractItemView:enabled {
            color: #FFFFFF;
            background: #071336;
            selection-background-color: #2563EB;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
