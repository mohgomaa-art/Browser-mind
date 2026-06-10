from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel, QVBoxLayout,
    QMessageBox,
)
from PySide6.QtCore import Signal

from browsermind_ui.core.app_context import AppContext
from browsermind_ui.core.prompt import handle_prompt_safe
from browsermind_ui.core.prompt_parse import is_browser_intent


class PromptBar(QWidget):
    """Bottom prompt box — goals, pilot, train, verify."""

    submitted = Signal(str, str)  # message, optional tab name

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("promptBar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)

        hint = QLabel("Prompt")
        hint.setObjectName("subheader")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "open facebook  |  record facebook  |  help  (emails OK; use ' @ pilot' only for persona)"
        )
        self.input.returnPressed.connect(self._submit)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.clicked.connect(self._submit)

        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

        self.status = QLabel("Ready. Type help for commands.")
        self.status.setObjectName("promptStatus")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(28)
        layout.addWidget(self.status)

    def _submit(self):
        text = self.input.text()
        if not text.strip():
            self.status.setText("Type a goal or command (try: help).")
            return

        msg, tab = handle_prompt_safe(self.ctx, text)
        self.status.setText(msg.replace("\n", " | "))
        self.submitted.emit(msg, tab or "")

        lower = text.strip().lower()
        if lower not in ("help", "?"):
            self.input.clear()

        show_box = (
            lower.startswith(("open ", "browse ", "record", "go "))
            or is_browser_intent(text)
            or "Opening browser" in msg
            or msg.startswith(("Error", "Failed", "Not found"))
            or "Task saved" in msg
        )
        if show_box:
            if msg.startswith(("Error", "Failed", "Not found")):
                QMessageBox.warning(self, "BrowserMind", msg)
            else:
                QMessageBox.information(self, "BrowserMind", msg)

        self.ctx.notifier.entity_mutated.emit("prompt", "")
