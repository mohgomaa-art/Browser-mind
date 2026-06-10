from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QHeaderView, QMessageBox
)
from browsermind_ui.core.app_context import AppContext
import browsermind_ui.core.commands as cmd

class IdentitiesView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_data_changed)

        layout = QVBoxLayout(self)
        
        header = QLabel("Identities")
        header.setObjectName("header")
        layout.addWidget(header)

        controls = QHBoxLayout()
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Identifier (e.g. john_github)")
        self.persona_input = QLineEdit()
        self.persona_input.setPlaceholderText("Persona Name")
        self.secret_input = QLineEdit()
        self.secret_input.setPlaceholderText("Secret / Token")
        self.secret_input.setEchoMode(QLineEdit.Password)
        
        self.create_btn = QPushButton("Create Identity")
        self.create_btn.clicked.connect(self._create_identity)
        
        controls.addWidget(self.id_input)
        controls.addWidget(self.persona_input)
        controls.addWidget(self.secret_input)
        controls.addWidget(self.create_btn)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Identifier", "Persona", "Env ID", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.refresh()

    def _on_data_changed(self, entity_type: str, entity_id: str):
        if entity_type == "identity":
            self.refresh()

    def refresh(self):
        idents = self.ctx.get_index("identity")
        items = list(idents.items())
        self.table.setRowCount(len(items))
        for i, (k, idx) in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(idx.get("persona", "")))
            self.table.setItem(i, 2, QTableWidgetItem(idx.get("env", "")[:8] + "..."))
            self.table.setItem(i, 3, QTableWidgetItem(idx["id"][:8] + "..."))

    def _create_identity(self):
        ident = self.id_input.text().strip()
        persona = self.persona_input.text().strip()
        secret = self.secret_input.text().strip()
        
        if not ident or not persona or not secret:
            QMessageBox.warning(self, "Error", "All fields are required.")
            return
            
        success = cmd.create_identity_command(self.ctx, ident, persona, secret)
        if success:
            self.id_input.clear()
            self.secret_input.clear()
        else:
            QMessageBox.warning(self, "Error", "Persona not found.")
