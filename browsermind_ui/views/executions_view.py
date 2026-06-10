from uuid import UUID
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QHeaderView, QMessageBox,
    QSplitter, QListWidget, QTabWidget
)
from PySide6.QtCore import Qt
from browsermind_ui.core.app_context import AppContext
import browsermind_ui.core.commands as cmd

class ExecutionsView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.ctx.notifier.entity_mutated.connect(self._on_data_changed)
        
        main_layout = QVBoxLayout(self)
        
        header = QLabel("Executions")
        header.setObjectName("header")
        main_layout.addWidget(header)
        
        controls = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Task Name")
        self.persona_input = QLineEdit()
        self.persona_input.setPlaceholderText("Persona Name")
        
        self.start_btn = QPushButton("Start Execution")
        self.start_btn.clicked.connect(self._start_execution)
        
        controls.addWidget(self.task_input)
        controls.addWidget(self.persona_input)
        controls.addWidget(self.start_btn)
        main_layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left: List of executions
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Task", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.table)
        splitter.addWidget(left_widget)

        # Right: Inspector Tabs
        self.inspector = QTabWidget()
        self.inspector.setVisible(False)
        
        # Tab 1: Overview
        self.tab_overview = QWidget()
        ov_layout = QVBoxLayout(self.tab_overview)
        self.insp_info = QLabel()
        self.insp_info.setWordWrap(True)
        ov_layout.addWidget(self.insp_info)
        
        actions_layout = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("warning")
        self.btn_pause.clicked.connect(lambda: self._do_action("pause"))
        
        self.btn_resume = QPushButton("Resume")
        self.btn_resume.setObjectName("success")
        self.btn_resume.clicked.connect(lambda: self._do_action("resume"))
        
        self.btn_fail = QPushButton("Crash")
        self.btn_fail.setObjectName("danger")
        self.btn_fail.clicked.connect(lambda: self._do_action("fail"))
        
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.clicked.connect(lambda: self._do_action("retry"))

        actions_layout.addWidget(self.btn_pause)
        actions_layout.addWidget(self.btn_resume)
        actions_layout.addWidget(self.btn_fail)
        actions_layout.addWidget(self.btn_retry)
        ov_layout.addLayout(actions_layout)
        ov_layout.addStretch()

        # Tab 2: Context
        self.tab_context = QWidget()
        ctx_layout = QVBoxLayout(self.tab_context)
        self.ctx_info = QLabel()
        self.ctx_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ctx_layout.addWidget(self.ctx_info)
        ctx_layout.addStretch()

        # Tab 3: Snapshots
        self.tab_snaps = QWidget()
        snap_layout = QVBoxLayout(self.tab_snaps)
        self.snap_list = QListWidget()
        snap_layout.addWidget(self.snap_list)

        # Tab 4: Timeline (Entity Ledger)
        self.tab_timeline = QWidget()
        tl_layout = QVBoxLayout(self.tab_timeline)
        self.tl_list = QListWidget()
        tl_layout.addWidget(self.tl_list)

        self.inspector.addTab(self.tab_overview, "Overview")
        self.inspector.addTab(self.tab_context, "Context")
        self.inspector.addTab(self.tab_snaps, "Snapshots")
        self.inspector.addTab(self.tab_timeline, "Timeline")

        splitter.addWidget(self.inspector)
        splitter.setSizes([400, 600])

        self.selected_exec_id = None
        self.refresh()

    def _on_data_changed(self, entity_type: str, entity_id: str):
        if entity_type in ["execution", "execution_index", "ledger", "prompt"]:
            self.refresh()
            if self.selected_exec_id:
                try:
                    self._load_inspector(self.selected_exec_id)
                except Exception:
                    pass

    def refresh(self):
        execs = self.ctx.get_index("execution")
        items = list(execs.items())
        
        # Keep selection if possible
        selected_row = -1
        if self.selected_exec_id:
            for i, (k, v) in enumerate(items):
                if k == self.selected_exec_id:
                    selected_row = i
                    break

        self.table.setRowCount(len(items))
        for i, (k, e) in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(k[:8]))
            self.table.setItem(i, 1, QTableWidgetItem(e.get("task", "")))
            
            st = e.get("status", "")
            status_item = QTableWidgetItem(st)
            if st == "running":
                status_item.setForeground(Qt.green)
            elif st == "paused":
                status_item.setForeground(Qt.yellow)
            elif st == "failed":
                status_item.setForeground(Qt.red)
                
            self.table.setItem(i, 2, status_item)
            self.table.item(i, 0).setData(Qt.UserRole, k)

        if selected_row >= 0:
            self.table.selectRow(selected_row)

    def _on_selection_changed(self):
        items = self.table.selectedItems()
        if not items:
            self.inspector.setVisible(False)
            self.selected_exec_id = None
            return

        row = items[0].row()
        exec_id = self.table.item(row, 0).data(Qt.UserRole)
        self.selected_exec_id = exec_id
        try:
            self._load_inspector(exec_id)
            self.inspector.setVisible(True)
        except Exception as e:
            self.inspector.setVisible(True)
            self.insp_info.setText(f"<font color='red'>Inspector error: {e}</font>")
            self.snap_list.clear()
            self.tl_list.clear()

    @staticmethod
    def _format_ts(dt) -> str:
        if dt is None:
            return "--:--:--"
        return dt.strftime("%H:%M:%S")

    def _load_inspector(self, exec_id: str):
        sess = self.ctx.session
        entry = sess._lookup("execution", exec_id)
        if not entry:
            self.inspector.setVisible(False)
            return

        exc_uuid = UUID(entry["id"])
        exc = sess.execution_engine.rehydrate_execution(exc_uuid)
        if not exc:
            self.inspector.setVisible(False)
            return

        # Overview Tab
        info = (
            f"<h2>Status: <font color='#00BCD4'>{exc.status.upper()}</font></h2>"
            f"<b>Retries:</b> {exc.retry_count}<br/><br/>"
        )
        if exc.failure_reason:
            info += f"<b>Failure Reason:</b> <font color='red'>{exc.failure_reason}</font><br/>"
        self.insp_info.setText(info)

        self.btn_pause.setEnabled(exc.status == "running")
        self.btn_resume.setEnabled(exc.status == "paused")
        self.btn_fail.setEnabled(exc.status in ["running", "paused"])
        self.btn_retry.setEnabled(exc.status == "failed")

        # Context Tab
        if exc.context:
            ctx = exc.context
            ctx_data = (
                f"<b>Execution ID:</b> {exc.id}<br/>"
                f"<b>Task ID:</b> {ctx.task_id}<br/>"
                f"<b>Persona ID:</b> {ctx.persona_id}<br/>"
                f"<b>Workflow Instance ID:</b> {ctx.workflow_instance_id}<br/>"
                f"<b>Template ID:</b> {ctx.template_id or 'None'}<br/>"
                f"<b>Identity ID:</b> {ctx.identity_id or 'None'}<br/>"
                f"<b>Environment ID:</b> {ctx.environment_id or 'None'}<br/>"
            )
        else:
            ctx_data = (
                f"<b>Execution ID:</b> {exc.id}<br/>"
                f"<b>Task ID:</b> {exc.task_id}<br/>"
                f"<b>Workflow Instance ID:</b> {exc.workflow_instance_id}<br/>"
                f"<i>No ExecutionContext snapshot</i><br/>"
            )
        self.ctx_info.setText(ctx_data)

        # Snapshots Tab
        snaps = sess.repo.load_all_snapshots(exc_uuid)
        self.snap_list.clear()
        for snap in snaps:
            st = snap.execution_state.get('status', '?')
            val = "VALID" if snap.is_valid else "INVALID"
            ts = self._format_ts(getattr(snap, "created_at", None))
            self.snap_list.addItem(f"Seq {snap.sequence} | {ts} | {st.upper()} [{val}]")

        # Timeline Tab (Entity Ledger)
        self.tl_list.clear()
        ledger_events = sess.ledger_repo.get_by_entity(exc_uuid)
        for e in ledger_events:
            ts = e.timestamp.strftime('%H:%M:%S')
            old = e.old_value.get("status", "--") if e.old_value else "--"
            new = e.new_value.get("status", "--") if e.new_value else "--"
            self.tl_list.addItem(f"{ts} | {old} -> {new}")

    def _start_execution(self):
        task = self.task_input.text().strip()
        persona = self.persona_input.text().strip()
        if not task or not persona:
            QMessageBox.warning(self, "Error", "Task and Persona required.")
            return
        if cmd.start_execution_command(self.ctx, task, persona):
            self.task_input.clear()
        else:
            QMessageBox.warning(self, "Error", "Task or Persona not found.")

    def _do_action(self, action: str):
        if not self.selected_exec_id:
            return
        
        if action == "pause":
            cmd.pause_execution_command(self.ctx, self.selected_exec_id)
        elif action == "resume":
            cmd.resume_execution_command(self.ctx, self.selected_exec_id)
        elif action == "fail":
            cmd.fail_execution_command(self.ctx, self.selected_exec_id)
        elif action == "retry":
            err = cmd.retry_execution_command(self.ctx, self.selected_exec_id)
            if err:
                QMessageBox.warning(self, "Retry Failed", err)
