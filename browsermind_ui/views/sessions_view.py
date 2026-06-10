from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QComboBox, QHeaderView,
    QMessageBox, QAbstractItemView,
)

from browsermind_ui.core.app_context import AppContext


class _LoginThread(QThread):
    """Run open_for_login in background so the UI stays responsive."""
    finished = Signal(str, str, bool)  # site_key, persona, success

    def __init__(self, store_dir: Path, site_key: str, persona: str, start_url: str | None = None):
        super().__init__()
        self._store_dir = store_dir
        self._site_key = site_key
        self._persona = persona
        self._start_url = start_url

    def run(self):
        try:
            from browsermind_core.session.session_manager import SessionManager
            SessionManager(self._store_dir).open_for_login(
                self._site_key, self._persona, self._start_url
            )
            self.finished.emit(self._site_key, self._persona, True)
        except Exception:
            self.finished.emit(self._site_key, self._persona, False)


class SessionsView(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._login_threads: list[_LoginThread] = []

        layout = QVBoxLayout(self)

        header = QLabel("Accounts & Sessions")
        header.setObjectName("header")
        layout.addWidget(header)

        # Controls row
        controls = QHBoxLayout()

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "logged_in", "unknown", "expired"])
        self._filter_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(QLabel("Filter:"))
        controls.addWidget(self._filter_combo)
        controls.addStretch()

        refresh_btn = QPushButton("Refresh All")
        refresh_btn.clicked.connect(self._refresh_all)
        controls.addWidget(refresh_btn)

        layout.addLayout(controls)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Site", "Persona", "Status", "Last Used", "Cookies", "Storage", "Age", "Actions"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        # Info label
        self._info_label = QLabel("")
        self._info_label.setObjectName("statusbar")
        layout.addWidget(self._info_label)

        self.refresh()

    def refresh(self):
        try:
            from browsermind_core.session.session_manager import SessionManager
        except ImportError:
            self._info_label.setText("SessionManager not available.")
            return

        store_dir = _get_store_dir(self.ctx)
        mgr = SessionManager(store_dir)
        sessions = mgr.list_sessions()

        # Apply filter
        filter_val = self._filter_combo.currentText()
        if filter_val != "All":
            sessions = [s for s in sessions if s.auth_status == filter_val]

        self.table.setRowCount(len(sessions))
        self.table.setColumnCount(8)

        status_colors = {
            "logged_in": QColor("#2d6a2d"),
            "expired":   QColor("#6a2d2d"),
            "unknown":   QColor("#5a5a2d"),
        }

        for row, meta in enumerate(sessions):
            # Site
            self.table.setItem(row, 0, QTableWidgetItem(meta.site_key))
            # Persona
            self.table.setItem(row, 1, QTableWidgetItem(meta.persona))
            # Status (colored)
            status_item = QTableWidgetItem(meta.auth_status)
            bg = status_colors.get(meta.auth_status)
            if bg:
                status_item.setBackground(bg)
                status_item.setForeground(QColor("white"))
            self.table.setItem(row, 2, status_item)
            # Last Used
            self.table.setItem(row, 3, QTableWidgetItem(_fmt_ago(meta.last_used)))
            # Cookies
            self.table.setItem(row, 4, QTableWidgetItem(str(meta.cookies_count) if meta.cookies_count else "—"))
            # Storage
            sz = f"{meta.storage_size_kb:.0f} KB" if meta.storage_size_kb else "—"
            self.table.setItem(row, 5, QTableWidgetItem(sz))
            # Age
            self.table.setItem(row, 6, QTableWidgetItem(_fmt_age(meta.created_at)))
            # Actions button
            btn = QPushButton("Open Browser")
            btn.setProperty("site_key", meta.site_key)
            btn.setProperty("persona", meta.persona)
            btn.clicked.connect(self._on_open_browser)
            self.table.setCellWidget(row, 7, btn)

        total = len(mgr.list_sessions())
        self._info_label.setText(
            f"{total} session(s) total  |  showing {len(sessions)}"
        )

    def _on_open_browser(self):
        btn = self.sender()
        site_key = btn.property("site_key")
        persona = btn.property("persona")

        store_dir = _get_store_dir(self.ctx)

        # Get start URL from site registry
        start_url = None
        try:
            from browsermind_core.mission.site_registry import get_spec
            spec = get_spec(site_key)
            if spec:
                start_url = getattr(spec, "login_url", None) or spec.start_url
        except Exception:
            pass

        btn.setEnabled(False)
        btn.setText("Opening…")

        thread = _LoginThread(store_dir, site_key, persona, start_url)
        thread.finished.connect(self._on_login_done)
        self._login_threads.append(thread)
        thread.start()

    def _on_login_done(self, site_key: str, persona: str, success: bool):
        if success:
            QMessageBox.information(
                self, "Session Saved",
                f"Session for {site_key} / {persona} marked as logged_in.\n\n"
                f"Run 'bm mission resume {site_key}' to continue the mission."
            )
        else:
            QMessageBox.warning(
                self, "Login Cancelled",
                f"Browser for {site_key} was closed without completing login."
            )
        self.refresh()

    def _refresh_all(self):
        try:
            from browsermind_core.session.session_manager import SessionManager
        except ImportError:
            return

        store_dir = _get_store_dir(self.ctx)
        mgr = SessionManager(store_dir)
        sessions = mgr.list_sessions()
        for s in sessions:
            try:
                mgr.refresh_metadata(s.site_key, s.persona)
            except Exception:
                pass
        self.refresh()
        self._info_label.setText(f"Refreshed {len(sessions)} session(s).")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_store_dir(ctx: AppContext) -> Path:
    try:
        from browsermind_core.console.session import DEFAULT_STORE
        return Path(getattr(ctx, "store_dir", None) or DEFAULT_STORE)
    except Exception:
        return Path.home() / ".browsermind"


def _fmt_ago(iso: str | None) -> str:
    if not iso:
        return "never"
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return iso[:10]


def _fmt_age(iso: str | None) -> str:
    if not iso:
        return "—"
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return "today" if days == 0 else f"{days}d"
    except Exception:
        return "—"
