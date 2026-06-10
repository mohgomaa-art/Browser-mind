from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
)
from browsermind_ui.core.app_context import AppContext

class LedgerView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_data_changed)

        layout = QVBoxLayout(self)
        
        header = QLabel("Global Mutation Ledger Timeline")
        header.setObjectName("header")
        layout.addWidget(header)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.refresh()

    def _on_data_changed(self, entity_type: str, entity_id: str):
        if entity_type == "ledger":
            self.refresh()

    def refresh(self):
        self.list_widget.clear()
        entries = self.ctx.session.ledger_repo.tail(50)
        # Display newest at the top
        for e in reversed(entries):
            ts = e.timestamp.strftime('%H:%M:%S')
            
            ent_type = e.entity_type
            ent_id = str(e.entity_id)[:8]
            
            old = e.old_value
            new = e.new_value
            
            old_st = old.get("status", "--") if old else "--"
            new_st = new.get("status", "--") if new else "--"
            
            actor = e.actor or "system"
            
            text = f"{ts} | {ent_type} [{ent_id}...] | {old_st} -> {new_st} | by {actor}"
            
            item = QListWidgetItem(text)
            self.list_widget.addItem(item)
