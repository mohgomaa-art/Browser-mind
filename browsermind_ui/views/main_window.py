from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QStackedWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt

from browsermind_ui.core.app_context import AppContext
from browsermind_ui.views.repo_explorer import RepoExplorerView
from browsermind_ui.views.personas_view import PersonasView
from browsermind_ui.views.sessions_view import SessionsView
from browsermind_ui.views.identities_view import IdentitiesView
from browsermind_ui.views.tasks_view import TasksView
from browsermind_ui.views.executions_view import ExecutionsView
from browsermind_ui.views.ledger_view import LedgerView
from browsermind_ui.widgets.prompt_bar import PromptBar

class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.setWindowTitle("BrowserMind Operator Console")
        self.resize(1100, 750)

        self.ctx = ctx

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        outer = QVBoxLayout(central_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QWidget()
        main_layout = QHBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        main_layout.addWidget(self.sidebar)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)

        outer.addWidget(body, 1)

        # Initialize Views
        self.views = {
            "Dev Panel": RepoExplorerView(self.ctx),
            "Executions": ExecutionsView(self.ctx),
            "Personas": PersonasView(self.ctx),
            "Sessions": SessionsView(self.ctx),
            "Tasks": TasksView(self.ctx),
            "Global Ledger": LedgerView(self.ctx),
            "Identities": IdentitiesView(self.ctx),
        }

        # Add items to sidebar and stacked widget
        for name, view in self.views.items():
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.sidebar.addItem(item)
            self.stacked_widget.addWidget(view)

        self.sidebar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        self.prompt_bar = PromptBar(self.ctx)
        self.prompt_bar.submitted.connect(self._on_prompt_submitted)
        outer.addWidget(self.prompt_bar)

    def _on_prompt_submitted(self, _msg: str, tab_name: str):
        for view in self.views.values():
            if hasattr(view, "refresh"):
                view.refresh()
        if tab_name and tab_name in self.views:
            names = list(self.views.keys())
            self.sidebar.setCurrentRow(names.index(tab_name))
