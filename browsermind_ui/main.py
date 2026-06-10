import sys
import os

# Ensure browsermind_core is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication
from browsermind_ui.core.app_context import AppContext
from browsermind_ui.views.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Initialize the core OS context
    ctx = AppContext()
    
    # Load stylesheet
    style_path = os.path.join(os.path.dirname(__file__), "styles.qss")
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())
            
    window = MainWindow(ctx)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
