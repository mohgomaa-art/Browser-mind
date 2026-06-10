from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QHeaderView, QMessageBox
)
from browsermind_ui.core.app_context import AppContext
import browsermind_ui.core.commands as cmd

class TasksView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_data_changed)

        layout = QVBoxLayout(self)
        
        header = QLabel("Tasks")
        header.setObjectName("header")
        layout.addWidget(header)

        controls = QHBoxLayout()
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("Task Goal (e.g. Apply to Greenhouse)")
        self.persona_input = QLineEdit()
        self.persona_input.setPlaceholderText("Persona Name")
        
        self.create_btn = QPushButton("Create Task")
        self.create_btn.clicked.connect(self._create_task)
        
        controls.addWidget(self.goal_input)
        controls.addWidget(self.persona_input)
        controls.addWidget(self.create_btn)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Persona", "Goal", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.refresh()

    def _on_data_changed(self, entity_type: str, entity_id: str):
        if entity_type in ("task", "prompt"):
            self.refresh()

    def refresh(self):
        tasks = self.ctx.get_index("task")
        items = list(tasks.items())
        self.table.setRowCount(len(items))
        for i, (k, t) in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(t.get("persona", "")))
            self.table.setItem(i, 2, QTableWidgetItem(t.get("goal", "")))
            self.table.setItem(i, 3, QTableWidgetItem(t["id"][:8] + "..."))

    def _create_task(self):
        goal = self.goal_input.text().strip()
        persona = self.persona_input.text().strip()
        
        if not goal or not persona:
            QMessageBox.warning(self, "Error", "All fields are required.")
            return
            
        success = cmd.create_task_command(self.ctx, goal, persona)
        if success:
            self.goal_input.clear()
        else:
            QMessageBox.warning(self, "Error", "Persona not found.")
