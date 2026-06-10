from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QHeaderView, QMessageBox
)
from browsermind_ui.core.app_context import AppContext
import browsermind_ui.core.commands as cmd

class PersonasView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_data_changed)

        layout = QVBoxLayout(self)
        
        header = QLabel("Personas")
        header.setObjectName("header")
        layout.addWidget(header)

        controls = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Persona Name (e.g. AI Founder)")
        self.prin_input = QLineEdit()
        self.prin_input.setPlaceholderText("Principal Name (optional)")
        
        self.create_btn = QPushButton("Create Persona")
        self.create_btn.clicked.connect(self._create_persona)
        
        controls.addWidget(self.name_input)
        controls.addWidget(self.prin_input)
        controls.addWidget(self.create_btn)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Principal", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.refresh()

    def _on_data_changed(self, entity_type: str, entity_id: str):
        if entity_type == "persona":
            self.refresh()

    def refresh(self):
        personas = self.ctx.get_index("persona")
        items = list(personas.items())
        self.table.setRowCount(len(items))
        for i, (k, p) in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(p.get("principal", "")))
            self.table.setItem(i, 2, QTableWidgetItem(p["id"][:8] + "..."))

    def _create_persona(self):
        name = self.name_input.text().strip()
        prin = self.prin_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Persona name is required.")
            return
        
        success = cmd.create_persona_command(self.ctx, name, prin)
        if success:
            self.name_input.clear()
            self.prin_input.clear()
        else:
            QMessageBox.warning(self, "Error", "Failed to create persona.")
