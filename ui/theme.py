"""
统一主题系统 — 所有 UI 页面的视觉常量集中管理

配色以米白/奶油白小清新风格为基础（参考 session_ui.py 的原始设计），
扩展覆盖统计仪表盘等需要更强色调的场景。

使用方式:
    from ui.theme import COLORS, FONTS, SPACING, BUTTON, CARD, font, scrollbar_style
"""
from PyQt6.QtGui import QFont

# ==============================================================================
# 调色板 — 米白/奶油白小清新
# ==============================================================================
COLORS = {
    # ── 页面背景 ──
    "page_bg":         "#fffdf9",      # 暖白页面背景
    "page_bg_alt":     "#faf8f4",      # 略深暖白（对比区）
    "panel_bg":        "#f5f0e6",      # 侧边栏 / 左面板
    "panel_bg_alt":    "#faf6ef",      # 面板备选

    # ── 卡片 ──
    "card_bg":         "#ffffff",      # 卡片白色
    "card_hover":      "#f9efdf",      # 卡片悬停
    "card_selected":   "#f5f0e0",      # 卡片选中
    "card_border":     "#f0ebe0",      # 卡片边框

    # ── 文字 ──
    "text_primary":    "#3e3a35",      # 主文字（深暖灰）
    "text_secondary":  "#a6a19b",      # 次要文字（灰褐）
    "text_disabled":   "#c8c3bc",      # 禁用文字
    "text_inverse":    "#ffffff",      # 反白文字

    # ── 强调色（柔和粉彩，用于徽章/标签/装饰） ──
    "accent_green":    "#b0d9b1",      # 成功 / 在线
    "accent_blue":     "#b8e1e6",      # 信息 / AI
    "accent_apricot":  "#f5d9b8",      # 警告 / 转人工
    "accent_error":    "#f4a5a5",      # 错误
    "accent_purple":   "#c4b5d9",      # 知识库

    # ── KPI 强色调（用于数据可视化卡片） ──
    "kpi_blue":        "#4A90D9",
    "kpi_teal":        "#26A69A",
    "kpi_purple":      "#7E57C2",
    "kpi_green":       "#43A047",
    "kpi_orange":      "#EF6C00",
    "kpi_red":         "#E53935",
    "kpi_gray":        "#78909C",

    # ── 聊天气泡 ──
    "user_bubble":     "#e8f5e9",      # 用户气泡（浅绿）
    "agent_bubble":    "#fefef5",      # AI 气泡（米白）
    "agent_border":    "#e8e4d8",      # AI 气泡边框

    # ── 结构/分割 ──
    "divider":         "#f0ebe0",
    "shadow_light":    "rgba(0,0,0,0.03)",
    "shadow_medium":   "rgba(0,0,0,0.05)",
    "scrollbar":       "#e0dbce",
    "scrollbar_hover": "#d0cabe",

    # ── 表格/数据 ──
    "table_alt_row":   "#faf8f4",
    "table_grid":      "#f0ebe0",
    "table_header_bg": "#f5f0e6",
    "table_selection": "#b0d9b1",

    # ── 输入框 ──
    "input_bg":        "#ffffff",
    "input_border":    "#e0dbce",
    "input_focus":     "#b0d9b1",
    "input_placeholder": "#c8c3bc",

    # ── 日志级别（强色，用于 log_ui.py） ──
    "log_debug":       "#8d979e",
    "log_info":        "#43A047",
    "log_warning":     "#EF6C00",
    "log_error":       "#E53935",
    "log_critical":    "#B71C1C",
}

# ==============================================================================
# 字体系统
# ==============================================================================
FONT_FAMILY = "Microsoft YaHei"

FONT_SIZES = {
    "body":    13,       # 正文
    "small":   11,       # 说明/时间戳
    "medium":  14,       # 强调正文
    "large":   18,       # 段落标题
    "xlarge":  24,       # KPI 数值
    "heading": 20,       # 页面标题
}


def font(size_key: str = "body", weight: QFont.Weight = QFont.Weight.Normal,
         italic: bool = False) -> QFont:
    """快捷创建 QFont，使用统一字体族和预设大小"""
    f = QFont(FONT_FAMILY, FONT_SIZES.get(size_key, 13), weight)
    f.setItalic(italic)
    return f

# ==============================================================================
# 间距系统
# ==============================================================================
SPACING = {
    "page_margin":   24,      # 页外边距
    "card_margin":   20,      # 卡片内边距
    "card_gap":      16,      # 卡片间距
    "section_gap":   20,      # 区块间距
    "element_gap":   12,      # 表单元素间距
    "inner_gap":      8,      # 紧凑内间距
    "header_height": 56,      # 页头高度
}

# ==============================================================================
# 按钮尺寸
# ==============================================================================
BUTTON = {
    "sm":  (80,  32),     # 小（表格内操作）
    "md":  (100, 36),     # 中（标准操作）
    "lg":  (120, 40),     # 大（主要操作）
    "xl":  (140, 44),     # 特大
}

# ==============================================================================
# 卡片尺寸
# ==============================================================================
CARD = {
    "account_height":   120,    # 账号/自动回复卡片
    "shop_card_height":  76,    # 会话店铺卡片
    "conv_card_height":  82,    # 会话卡片
    "kpi_min_height":   130,    # KPI 卡片最小高度
    "kpi_min_width":    200,    # KPI 卡片最小宽度
    "border_radius":     14,    # 标准圆角
    "card_padding":      16,    # 标准卡片内边距
}

# ==============================================================================
# 公共 QSS 模板
# ==============================================================================


def scrollbar_style() -> str:
    """统一滚动条样式 — 8px 宽，圆角，米色调"""
    return f"""
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 4px 2px; border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS['scrollbar']}; border-radius: 4px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLORS['scrollbar_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent; height: 8px;
    }}
    QScrollBar::handle:horizontal {{
        background: {COLORS['scrollbar']}; border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {COLORS['scrollbar_hover']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollArea {{
        border: none; background: transparent;
    }}
    """


def scroll_area_style() -> str:
    """ScrollArea 透明无边框样式"""
    return """
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    """


def page_style(extra: str = "") -> str:
    """页面基础 QSS，合并滚动条样式和可选的页面专属样式"""
    base = f"""
    QFrame#{'{page}'} {{
        background-color: {COLORS['page_bg']};
    }}
    """
    return base + scrollbar_style() + extra
