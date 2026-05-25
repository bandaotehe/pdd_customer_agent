import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QFont, QIcon, QPixmap, QAction
from qfluentwidgets import FluentWindow,qrouter, NavigationItemPosition
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import SubtitleLabel, TeachingTip, TeachingTipTailPosition, InfoBadge
from qfluentwidgets import Action
from utils.logger_loguru import get_logger
import time

class Widget(QFrame):

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        # 创建标题标签
        self.label = SubtitleLabel(text, self)
        # 创建水平布局
        self.hBoxLayout = QHBoxLayout(self)
        # 设置标签文本居中对齐
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 将标签添加到布局中,设置居中对齐和拉伸因子1
        self.hBoxLayout.addWidget(self.label, 1, Qt.AlignmentFlag.AlignCenter)
        # 必须给子界面设置全局唯一的对象名
        self.setObjectName(text.replace(' ', '-'))

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        t = time.perf_counter()
        self.setWindowTitle('拼多多AI客服助手')
        self.setWindowIcon(QIcon("icon/icon.ico"))
        self.logger = get_logger("MainWindow")
        self.logger.info(f"  基础属性初始化: {time.perf_counter()-t:.2f}s")

        # 提前连接 Agent 错误信号（确保不会因时序问题丢失通知）
        from ui.error_notifier import error_notifier
        error_notifier.agent_error.connect(self._on_agent_error_global)
        error_notifier.session_updated.connect(self._on_session_updated)
        error_notifier.transfer_to_human.connect(self._on_transfer_to_human)

        # 延迟加载的视图
        self.knowledge_view = None
        self.account_service_view = None
        self.log_view = None
        self.session_view = None
        self.settingInterface = None
        self.statistics_view = None
        self._pending_session_update = None  # 缓存视图加载前的信号
        self._session_nav_item = None  # 会话管理导航项引用
        self._transfer_badge_count = 0  # 转人工待处理计数

        t = time.perf_counter()
        # 立即初始化导航和窗口
        self.initWindow()
        self.logger.info(f"  initWindow: {time.perf_counter()-t:.2f}s")

        # 初始化系统托盘
        self._init_system_tray()

        # 监听导航切换，点击「会话管理」时清除转人工角标
        self.stackedWidget.currentChanged.connect(self._on_navigation_changed)

        # 延迟加载各个视图，让窗口先显示
        QTimer.singleShot(200, self.lazy_load_views)

    def lazy_load_views(self):
        """延迟加载各个视图，提高启动速度"""
        t0 = time.perf_counter()
        # 局部按需导入，减少启动时的重依赖加载
        t = time.perf_counter()
        from ui.account_service_ui import AccountServiceUI
        self.logger.info(f"  import AccountServiceUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        from ui.log_ui import LogUI
        self.logger.info(f"  import LogUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        from ui.setting_ui import SettingUI
        self.logger.info(f"  import SettingUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        from ui.Knowledge_ui import KnowledgeUI
        self.logger.info(f"  import KnowledgeUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        from ui.session_ui import SessionManagementWidget
        self.logger.info(f"  import SessionManagementWidget: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        from ui.statistics_ui import StatisticsUI
        self.logger.info(f"  import StatisticsUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        self.account_service_view = AccountServiceUI(self)
        self.logger.info(f"  AccountServiceUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        self.log_view = LogUI(self)
        self.logger.info(f"  LogUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        self.knowledge_view = KnowledgeUI(self)
        self.logger.info(f"  KnowledgeUI: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        self.session_view = SessionManagementWidget(self)
        self.logger.info(f"  SessionManagementWidget: {time.perf_counter()-t:.2f}s")
        t = time.perf_counter()
        self.statistics_view = StatisticsUI(self)
        self.logger.info(f"  StatisticsUI: {time.perf_counter()-t:.2f}s")
        # 回放视图加载前缓存的会话更新信号
        if self._pending_session_update is not None:
            sid, sp_id = self._pending_session_update
            self.session_view._on_message_updated(sid, sp_id)
            self._pending_session_update = None
        t = time.perf_counter()
        self.settingInterface = SettingUI(self)
        self.logger.info(f"  SettingUI: {time.perf_counter()-t:.2f}s")

        # 初始化导航
        self.initNavigation()
        self.logger.info(f"延迟视图初始化耗时: {time.perf_counter() - t0:.2f}s")

    # 初始化导航栏
    def initNavigation(self):
        self.navigationInterface.setExpandWidth(200)
        self.navigationInterface.setMinimumWidth(200)
        self.addSubInterface(self.statistics_view, FIF.PIE_SINGLE, '数据统计')
        self.addSubInterface(self.account_service_view, FIF.PEOPLE, '账号与客服')
        self._session_nav_item = self.addSubInterface(self.session_view, FIF.MESSAGE, '会话管理')
        self.addSubInterface(self.knowledge_view, FIF.DOCUMENT, '知识管理')
        self.addSubInterface(self.log_view, FIF.HISTORY, '日志管理', NavigationItemPosition.BOTTOM)
        # 添加二维码按钮
        # self.navigationInterface.addItem(
        #     routeKey='contact_us',
        #     icon=FIF.QRCODE,
        #     text='联系我们',
        #     onClick=self.showQRCode,
        #     selectable=False,
        #     position=NavigationItemPosition.BOTTOM
        # )
        self.addSubInterface(self.log_view, FIF.HISTORY, '日志管理', NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.settingInterface, FIF.SETTING, '设置', NavigationItemPosition.BOTTOM)


    # 初始化窗口
    def initWindow(self):
        # 先设置最小尺寸
        self.setMinimumWidth(1280)
        self.setMinimumHeight(720)

        # 设置默认尺寸（避免几何冲突）
        self.resize(1400, 800)

        # 最后最大化显示
        self.showMaximized()

    def _init_system_tray(self):
        """初始化系统托盘：最小化时也能通过托盘消息提醒管理员"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.logger.warning("系统托盘不可用")
            self._tray_icon = None
            return

        self._tray_icon = QSystemTrayIcon(QIcon("icon/icon.ico"), self)
        self._tray_icon.setToolTip("拼多多AI客服助手")

        # 托盘右键菜单
        tray_menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_and_focus)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(tray_menu)

        # 双击托盘图标显示窗口
        self._tray_icon.activated.connect(self._on_tray_activated)

        self._tray_icon.show()
        self.logger.info("系统托盘初始化成功")

    def _show_and_focus(self):
        """显示窗口并置顶"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        """托盘图标双击 → 显示窗口"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_and_focus()

    def _on_navigation_changed(self, index):
        """导航切换时：如果切到会话管理页，清除转人工角标"""
        widget = self.stackedWidget.widget(index)
        if widget is self.session_view:
            self._clear_transfer_badge()

    def _clear_transfer_badge(self):
        """清除侧边栏「会话管理」上的转人工红点角标"""
        self._transfer_badge_count = 0
        if self._session_nav_item is not None and hasattr(self._session_nav_item, 'setInfoBadge'):
            self._session_nav_item.setInfoBadge(None)


    # def showQRCode(self):
    #     """显示二维码TeachingTip"""
    #     try:
    #         tip = TeachingTip.create(
    #             target=self.navigationInterface,
    #             image="icon/Customer-Agent-qr.png",
    #             icon=FIF.PEOPLE,
    #             title="联系我们",
    #             content="扫码关注获取更多信息和支持",
    #             isClosable=True,
    #             duration=-1,
    #             tailPosition=TeachingTipTailPosition.LEFT,
    #             parent=self
    #         )
            
    #         # 显示TeachingTip
    #         tip.show()
            
    #     except Exception as e:
    #         self.logger.error(f"显示二维码失败: {e}")

    def _on_agent_error_global(self, shop_name: str, error_msg: str, session_id: str):
        """全局 Agent 错误通知：弹窗提示 + 刷新会话管理页面"""
        try:
            shop_info = f"店铺「{shop_name}」" if shop_name else "某个店铺"
            self.logger.error(f"Agent 出错 - {shop_info}: {error_msg}")

            # 使用 TeachingTip 非阻塞提示
            from qfluentwidgets import TeachingTip, TeachingTipTailPosition, InfoBar, InfoBarPosition
            InfoBar.error(
                title="AI 回复异常",
                content=f"{shop_info} 的 AI 自动回复出现异常，已停止向客户返回错误信息。\n错误：{error_msg}",
                orient=Qt.Orientation.Vertical,
                isClosable=True,
                duration=10000,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )

            # 刷新会话管理页面（触发时会重新加载数据，错误会话标红）
            if self.session_view is not None:
                QTimer.singleShot(500, self.session_view._load_data)
        except Exception as e:
            self.logger.error(f"全局错误通知失败: {e}")

    def _on_session_updated(self, session_id: str, shop_id: str):
        """实时会话更新：来自成功 AI 回复后的信号"""
        try:
            if self.session_view is not None:
                self.session_view._on_message_updated(session_id, shop_id)
            else:
                self._pending_session_update = (session_id, shop_id)
        except Exception as e:
            self.logger.error(f"处理会话更新通知失败: {e}")

    def _on_transfer_to_human(self, shop_id: str, shop_name: str, customer_id: str,
                               cs_name: str, session_id: str):
        """转人工通知：侧边栏红点 + 托盘消息 + InfoBar 弹窗 + 任务栏闪烁"""
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            shop_label = f"「{shop_name}」" if shop_name else f"店铺 {shop_id}"

            # 1. InfoBar 弹窗（窗口可见时能看到）
            InfoBar.warning(
                title="转人工提醒",
                content=f"{shop_label} 的客户 {customer_id} 触发了转人工\n"
                        f"已转接给客服: {cs_name}\n"
                        f"会话: {session_id}",
                orient=Qt.Orientation.Vertical,
                isClosable=True,
                duration=-1,  # 不自动关闭，需要管理员手动关闭
                position=InfoBarPosition.TOP_RIGHT,
                parent=self,
            )

            # 2. 侧边栏「会话管理」红点角标
            self._update_transfer_badge()

            # 3. 系统托盘消息（窗口最小化时也能看到）
            if self._tray_icon is not None and QSystemTrayIcon.supportsMessages():
                self._tray_icon.showMessage(
                    "转人工提醒",
                    f"{shop_label} 的客户 {customer_id} 触发了转人工\n已转接给客服: {cs_name}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    5000,  # 5 秒后自动消失
                )

            # 4. 窗口最小化时闪烁任务栏
            if self.isMinimized():
                QApplication.alert(self, 0)  # 持续闪烁直到窗口获得焦点

            # 刷新会话管理页面
            if self.session_view is not None:
                QTimer.singleShot(500, lambda: self._refresh_session_ui_for_transfer(shop_id, session_id))
        except Exception as e:
            self.logger.error(f"处理转人工通知失败: {e}")

    def _update_transfer_badge(self):
        """更新侧边栏「会话管理」转人工计数角标"""
        self._transfer_badge_count += 1
        if self._session_nav_item is not None and hasattr(self._session_nav_item, 'setInfoBadge'):
            badge = InfoBadge.error(
                str(self._transfer_badge_count) if self._transfer_badge_count > 1 else '●',
                parent=self._session_nav_item,
            )
            self._session_nav_item.setInfoBadge(badge)

    def _refresh_session_ui_for_transfer(self, shop_id: str, session_id: str):
        """转人工后智能刷新会话 UI，保持当前视图状态"""
        try:
            view = self.session_view
            if view is None:
                return

            # 始终刷新店铺卡片计数和转人工标记
            view._load_data()

            current_idx = view.right_stack.currentIndex()
            if current_idx >= 1 and view._current_shop_id == shop_id:
                # 正在查看该店铺的会话列表，刷新会话列表
                view._load_sessions_into_conv_layout(shop_id)

            if current_idx == 2 and view._current_session_id == session_id:
                # 正在查看该会话的聊天详情，刷新聊天
                view._load_messages_into_chat_layout(session_id)
                QTimer.singleShot(100, view._scroll_chat_to_bottom)
        except Exception as e:
            self.logger.error(f"刷新会话 UI 失败: {e}")

    def closeEvent(self, a0):
        """ 重写窗口关闭事件，确保后台线程安全退出 """

        # 停止所有自动回复线程
        try:
            from ui.auto_reply_ui import auto_reply_manager
            auto_reply_manager.stop_all()
        except Exception:
            pass

        # 清理系统托盘图标
        if hasattr(self, '_tray_icon') and self._tray_icon is not None:
            self._tray_icon.hide()
            self._tray_icon = None

        super().closeEvent(a0) 
