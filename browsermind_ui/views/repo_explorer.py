from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
)
from PySide6.QtCore import Qt
from browsermind_ui.core.app_context import AppContext

class StatCard(QFrame):
    def __init__(self, title: str, count: int = 0):
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet("""
            QFrame#statCard {
                background-color: #2D2D30;
                border: 1px solid #3E3E42;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #CCCCCC; font-size: 14px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        
        self.count_label = QLabel(str(count))
        self.count_label.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        self.count_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.count_label)

    def set_count(self, count: int):
        self.count_label.setText(str(count))

class RepoExplorerView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_mutation)

        layout = QVBoxLayout(self)
        
        header = QLabel("Repository Explorer (Developer Panel)")
        header.setObjectName("header")
        layout.addWidget(header)

        grid = QGridLayout()
        layout.addLayout(grid)

        # Initialize cards
        self.cards = {
            "Principals": StatCard("Principals"),
            "Personas": StatCard("Personas"),
            "Identities": StatCard("Identities"),
            "Tasks": StatCard("Tasks"),
            "Executions": StatCard("Executions"),
            "Snapshots": StatCard("Snapshots"),
            "Ledger Entries": StatCard("Ledger Entries")
        }

        # Add to grid
        row, col = 0, 0
        for name, card in self.cards.items():
            grid.addWidget(card, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1

        layout.addStretch()
        self.refresh()

    def _on_mutation(self, entity_type: str, entity_id: str):
        self.refresh()

    def refresh(self):
        sess = self.ctx.session
        
        counts = {
            "Principals": len(sess._load_index("principal")),
            "Personas": len(sess._load_index("persona")),
            "Identities": len(sess._load_index("identity")),
            "Tasks": len(sess._load_index("task")),
            "Executions": len(sess._load_index("execution")),
        }
        
        # Count snapshots across all executions
        snap_count = 0
        for exec_id_str, meta in sess._load_index("execution").items():
            from uuid import UUID
            snaps = sess.repo.load_all_snapshots(UUID(meta["id"]))
            snap_count += len(snaps)
        counts["Snapshots"] = snap_count
        
        # Count ledger
        counts["Ledger Entries"] = sess.ledger_repo.count()

        for name, count in counts.items():
            self.cards[name].set_count(count)
