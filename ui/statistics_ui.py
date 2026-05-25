"""数据统计面板"""
from datetime import datetime, timedelta
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QSizePolicy,
)
from qfluentwidgets import (
    CardWidget, ElevatedCardWidget, SubtitleLabel, CaptionLabel,
    StrongBodyLabel, BodyLabel, PushButton, ScrollArea, FluentIcon as FIF,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from config import get_config
from utils.logger_loguru import get_logger
from ui.theme import COLORS, SPACING, scrollbar_style

logger = get_logger("StatisticsUI")

# ── KPI 强调色别名（引用主题系统） ──
ACCENT = {
    "blue":    COLORS["kpi_blue"],
    "teal":    COLORS["kpi_teal"],
    "purple":  COLORS["kpi_purple"],
    "green":   COLORS["kpi_green"],
    "orange":  COLORS["kpi_orange"],
    "red":     COLORS["kpi_red"],
    "gray":    COLORS["kpi_gray"],
}


class StatsDataProvider:
    """统计数据提供者"""

    def __init__(self):
        db_path = get_config("db_path", "./temp/channel_shop.db")
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)

    def _count(self, table: str, where: str = "", params: dict | None = None) -> int:
        try:
            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                val = result.scalar()
                return int(val) if val is not None else 0
        except SQLAlchemyError:
            return 0

    def _today_bounds(self) -> tuple[datetime, datetime]:
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    def get_today_assistant_messages(self) -> int:
        s, e = self._today_bounds()
        return self._count(
            "agent_messages",
            "role = :role AND timestamp >= :s AND timestamp < :e",
            {"role": "assistant", "s": s, "e": e},
        )

    def get_today_user_messages(self) -> int:
        s, e = self._today_bounds()
        return self._count(
            "agent_messages",
            "role = :role AND timestamp >= :s AND timestamp < :e",
            {"role": "user", "s": s, "e": e},
        )

    def get_today_new_sessions(self) -> int:
        s, e = self._today_bounds()
        return self._count(
            "sessions",
            "created_at >= :s AND created_at < :e",
            {"s": s, "e": e},
        )

    def get_today_transfers(self) -> int:
        s, e = self._today_bounds()
        return self._count(
            "sessions",
            "needs_human = 1 AND last_activity_at >= :s AND last_activity_at < :e",
            {"s": s, "e": e},
        )

    def get_today_errors(self) -> int:
        s, e = self._today_bounds()
        return self._count(
            "sessions",
            "is_error = 1 AND last_activity_at >= :s AND last_activity_at < :e",
            {"s": s, "e": e},
        )

    def get_today_ai_success_rate(self) -> float:
        assistant = self.get_today_assistant_messages()
        errors = self.get_today_errors()
        if assistant == 0:
            return 100.0
        return max(0.0, round((assistant - errors) / assistant * 100, 1))

    def get_total_sessions(self) -> int:
        return self._count("sessions")

    def get_total_messages(self) -> int:
        return self._count("agent_messages")

    def get_active_sessions_24h(self) -> int:
        cutoff = datetime.now() - timedelta(days=1)
        return self._count(
            "sessions",
            "last_activity_at >= :cutoff",
            {"cutoff": cutoff},
        )

    def get_knowledge_counts(self) -> dict[str, int]:
        return {
            "products": self._count("product_knowledge"),
            "customer_service": self._count("customer_service_knowledge"),
            "custom": self._count("custom_knowledge"),
        }

    def get_account_counts(self) -> dict[str, int]:
        try:
            sql = text("SELECT status, COUNT(*) AS cnt FROM accounts GROUP BY status")
            with self.engine.connect() as conn:
                rows = conn.execute(sql).fetchall()
            result = {"total": 0, "online": 0, "offline": 0, "rest": 0, "unverified": 0}
            for status, cnt in rows:
                cnt = int(cnt)
                result["total"] += cnt
                if status == 1:
                    result["online"] += cnt
                elif status == 3:
                    result["offline"] += cnt
                elif status == 0:
                    result["rest"] += cnt
                else:
                    result["unverified"] += cnt
            return result
        except SQLAlchemyError:
            return {"total": 0, "online": 0, "offline": 0, "rest": 0, "unverified": 0}

    def get_7day_trend(self) -> list[dict[str, Any]]:
        now = datetime.now()
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

        try:
            sql = text(
                "SELECT date(timestamp) AS day, role, COUNT(*) AS cnt "
                "FROM agent_messages "
                "WHERE timestamp >= :start "
                "GROUP BY date(timestamp), role "
                "ORDER BY day"
            )
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"start": start.isoformat()}).fetchall()
        except SQLAlchemyError:
            return []

        day_map: dict[str, dict[str, int]] = {}
        for day, role, cnt in rows:
            if day not in day_map:
                day_map[day] = {"assistant": 0, "user": 0}
            if role in ("assistant", "user"):
                day_map[day][role] += int(cnt)

        result = []
        for i in range(7):
            d = start + timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            roles = day_map.get(key, {"assistant": 0, "user": 0})
            result.append({
                "date": d.strftime("%m/%d"),
                "assistant": roles.get("assistant", 0),
                "user": roles.get("user", 0),
                "total": roles.get("assistant", 0) + roles.get("user", 0),
            })
        return result


# ──────────────────────────────────────────────
#  UI Components
# ──────────────────────────────────────────────

class KpiCard(ElevatedCardWidget):
    """关键指标卡片 — 顶部彩色条 + 图标 + 数值"""

    def __init__(self, title: str, color: str, icon: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(200, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Color accent bar at top
        bar = QFrame(self)
        bar.setFixedHeight(3)
        bar.setStyleSheet(f"background-color: {color}; border-radius: 0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)

        inner = QVBoxLayout()
        inner.setContentsMargins(20, 14, 20, 18)
        inner.setSpacing(6)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setFixedWidth(24)
        title_label = CaptionLabel(title)
        title_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch()
        inner.addLayout(title_row)

        # Value
        self._value_label = StrongBodyLabel("—")
        font = self._value_label.font()
        font.setPointSize(32)
        font.setBold(True)
        self._value_label.setFont(font)
        self._value_label.setStyleSheet(f"color: {color};")
        inner.addWidget(self._value_label)

        layout.addLayout(inner)

    def set_value(self, value: str):
        self._value_label.setText(value)


class MetricRow(QWidget):
    """单行指标 — 用于分组卡片内部的小指标"""

    def __init__(self, label: str, dot_color: str = ACCENT["gray"], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setFixedWidth(16)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        layout.addWidget(dot)

        name = BodyLabel(label)
        name.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(name, 1)

        self._value_label = BodyLabel("—")
        self._value_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._value_label)

    def set_value(self, value: str):
        self._value_label.setText(value)


class SectionCard(CardWidget):
    """分组卡片 — 包含标题 + 多行指标"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._metrics: dict[str, MetricRow] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(10)

        header = SubtitleLabel(title)
        layout.addWidget(header)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(6)
        layout.addLayout(self._content_layout)

        layout.addStretch()

    def add_row(self, key: str, label: str, color: str = ACCENT["gray"]) -> MetricRow:
        row = MetricRow(label, color)
        self._content_layout.addWidget(row)
        self._metrics[key] = row
        return row


class TrendCard(CardWidget):
    """趋势表格卡片"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("近 7 天消息趋势"))

        # Table
        self._table_layout = QVBoxLayout()
        self._table_layout.setSpacing(0)
        layout.addLayout(self._table_layout)

        self._build_table_header()

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(0)
        self._table_layout.addLayout(self._rows_layout)

        self._empty_label = CaptionLabel("暂无趋势数据")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 24px;")
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

    def _build_table_header(self):
        header = QWidget()
        header.setStyleSheet(f"background-color: {COLORS['table_header_bg']}; border-radius: 6px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(0)

        cols = [("日期", 100), ("助手消息", 120), ("用户消息", 120), ("总计", 120)]
        for text, width in cols:
            label = CaptionLabel(text)
            label.setFixedWidth(width)
            label.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(label)
        header_layout.addStretch()
        self._table_layout.addWidget(header)

    def update_data(self, data: list[dict]):
        # Clear
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not data:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)
        for i, row in enumerate(data):
            row_w = QWidget()
            if i == 0:
                row_w.setStyleSheet("margin-top: 4px;")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(16, 7, 16, 7)
            row_layout.setSpacing(0)

            date_label = BodyLabel(row["date"])
            date_label.setFixedWidth(100)
            row_layout.addWidget(date_label)

            is_today = (i == len(data) - 1)
            for key in ("assistant", "user", "total"):
                val_label = BodyLabel(str(row[key]))
                val_label.setFixedWidth(120)
                if is_today:
                    val_label.setStyleSheet("font-weight: bold;")
                row_layout.addWidget(val_label)

            row_layout.addStretch()
            self._rows_layout.addWidget(row_w)


class AlertCard(CardWidget):
    """异常监控卡片"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(SubtitleLabel("异常监控"))

        row_layout = QHBoxLayout()
        row_layout.setSpacing(32)

        self._transfer_row = MetricRow("转人工", ACCENT["orange"])
        row_layout.addWidget(self._transfer_row, 1)

        self._error_row = MetricRow("AI 错误", ACCENT["red"])
        row_layout.addWidget(self._error_row, 1)

        layout.addLayout(row_layout)

    def set_transfer(self, value: str):
        self._transfer_row.set_value(value)

    def set_error(self, value: str):
        self._error_row.set_value(value)


# ──────────────────────────────────────────────
#  Main Panel
# ──────────────────────────────────────────────

class StatisticsUI(QFrame):
    """数据统计主面板"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statistics-view")

        self._loaded_once = False
        self._refresh_pending = False
        self._provider: StatsDataProvider | None = None

        # KPI cards
        self._kpi_assistant: KpiCard | None = None
        self._kpi_user: KpiCard | None = None
        self._kpi_sessions: KpiCard | None = None
        self._kpi_rate: KpiCard | None = None

        # Section cards
        self._overview_card: SectionCard | None = None
        self._kb_card: SectionCard | None = None
        self._acct_card: SectionCard | None = None

        # Alert & trend
        self._alert_card: AlertCard | None = None
        self._trend_card: TrendCard | None = None
        self._last_update_label: CaptionLabel | None = None

        self._build_ui()

        from ui.error_notifier import error_notifier
        error_notifier.session_updated.connect(self._on_data_changed)
        error_notifier.agent_error.connect(self._on_data_changed)
        error_notifier.transfer_to_human.connect(self._on_data_changed)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_data)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            QTimer.singleShot(100, self._init_and_refresh)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._refresh_timer.stop()

    def closeEvent(self, event):
        self._refresh_timer.stop()
        super().closeEvent(event)

    # ── Build UI ──

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setViewportMargins(0, 0, 0, 0)

        content = QWidget()
        content.setObjectName("stats-content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(SPACING["page_margin"], 20, SPACING["page_margin"], SPACING["page_margin"])
        layout.setSpacing(20)

        # ── Row 1: KPI cards ──
        layout.addLayout(self._build_kpi_row())

        # ── Row 2: Three section cards ──
        layout.addLayout(self._build_section_row())

        # ── Row 3: Trend table ──
        self._trend_card = TrendCard()
        layout.addWidget(self._trend_card)

        # ── Row 4: Alert monitoring ──
        self._alert_card = AlertCard()
        layout.addWidget(self._alert_card)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background-color: {COLORS['page_bg_alt']}; border-bottom: 1px solid {COLORS['divider']};")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 0, 28, 0)

        title = SubtitleLabel("数据统计")
        layout.addWidget(title)

        self._last_update_label = CaptionLabel("上次更新: —")
        self._last_update_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._last_update_label)

        layout.addStretch()

        refresh_btn = PushButton(FIF.SYNC, "刷新")
        refresh_btn.clicked.connect(self._on_manual_refresh)
        layout.addWidget(refresh_btn)

        return header

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        self._kpi_assistant = KpiCard("今日处理消息", ACCENT["blue"], "\U0001f4e8")
        self._kpi_user = KpiCard("今日用户消息", ACCENT["teal"], "\U0001f464")
        self._kpi_sessions = KpiCard("今日新增会话", ACCENT["purple"], "\U0001f4ac")
        self._kpi_rate = KpiCard("AI 处理成功率", ACCENT["green"], "✅")

        for card in [self._kpi_assistant, self._kpi_user, self._kpi_sessions, self._kpi_rate]:
            row.addWidget(card, 1)

        return row

    def _build_section_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        # Overview
        self._overview_card = SectionCard("总体概况")
        self._overview_card.add_row("total_sessions", "总会话数")
        self._overview_card.add_row("total_messages", "总消息数")
        self._overview_card.add_row("active_sessions", "活跃会话 (24h)")
        row.addWidget(self._overview_card, 1)

        # Knowledge base
        self._kb_card = SectionCard("知识库概况")
        self._kb_card.add_row("kb_products", "产品知识", ACCENT["blue"])
        self._kb_card.add_row("kb_cs", "客服知识", ACCENT["teal"])
        self._kb_card.add_row("kb_custom", "自定义知识", ACCENT["purple"])
        row.addWidget(self._kb_card, 1)

        # Account
        self._acct_card = SectionCard("账号状态")
        self._acct_card.add_row("acct_online", "在线", ACCENT["green"])
        self._acct_card.add_row("acct_offline", "离线", ACCENT["gray"])
        self._acct_card.add_row("acct_rest", "休息", ACCENT["orange"])
        self._acct_card.add_row("acct_total", "总计")
        row.addWidget(self._acct_card, 1)

        return row

    # ── Data Refresh ──

    def _init_and_refresh(self):
        if self._provider is None:
            self._provider = StatsDataProvider()
        self._refresh_data()
        self._refresh_timer.start(30_000)

    def _refresh_data(self):
        if self._provider is None:
            return

        try:
            p = self._provider

            # KPI cards
            self._kpi_assistant.set_value(self._fmt(p.get_today_assistant_messages()))
            self._kpi_user.set_value(self._fmt(p.get_today_user_messages()))
            self._kpi_sessions.set_value(self._fmt(p.get_today_new_sessions()))
            self._kpi_rate.set_value(f"{p.get_today_ai_success_rate()}%")

            # Overview
            self._overview_card._metrics["total_sessions"].set_value(self._fmt(p.get_total_sessions()))
            self._overview_card._metrics["total_messages"].set_value(self._fmt(p.get_total_messages()))
            self._overview_card._metrics["active_sessions"].set_value(self._fmt(p.get_active_sessions_24h()))

            # Knowledge base
            kb = p.get_knowledge_counts()
            self._kb_card._metrics["kb_products"].set_value(self._fmt(kb["products"]))
            self._kb_card._metrics["kb_cs"].set_value(self._fmt(kb["customer_service"]))
            self._kb_card._metrics["kb_custom"].set_value(self._fmt(kb["custom"]))

            # Account
            acct = p.get_account_counts()
            self._acct_card._metrics["acct_online"].set_value(self._fmt(acct["online"]))
            self._acct_card._metrics["acct_offline"].set_value(self._fmt(acct["offline"]))
            self._acct_card._metrics["acct_rest"].set_value(self._fmt(acct["rest"]))
            self._acct_card._metrics["acct_total"].set_value(self._fmt(acct["total"]))

            # Trend
            self._trend_card.update_data(p.get_7day_trend())

            # Alert
            self._alert_card.set_transfer(self._fmt(p.get_today_transfers()))
            self._alert_card.set_error(self._fmt(p.get_today_errors()))

            now_str = datetime.now().strftime("%H:%M:%S")
            if self._last_update_label:
                self._last_update_label.setText(f"上次更新: {now_str}")
        except Exception:
            logger.exception("刷新统计数据失败")

    def _on_data_changed(self, *args):
        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(500, self._do_deferred_refresh)

    def _do_deferred_refresh(self):
        self._refresh_pending = False
        self._refresh_data()

    def _on_manual_refresh(self):
        self._refresh_data()

    @staticmethod
    def _fmt(n: int) -> str:
        return f"{n:,}"
