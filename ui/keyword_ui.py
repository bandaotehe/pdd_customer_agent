# 关键词管理界面

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QWidget, QLabel, 
                            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                            QInputDialog, QMessageBox)
from PyQt6.QtGui import QFont, QIcon
from qfluentwidgets import (SubtitleLabel, CaptionLabel, BodyLabel, 
                           PrimaryPushButton, PushButton, 
                           ScrollArea, FluentIcon as FIF,
                           TableWidget)
from database.db_manager import db_manager


class KeywordTableWidget(TableWidget):
    """关键词表格组件"""
    
    # 定义信号
    edit_clicked = pyqtSignal(str)  # 编辑按钮点击信号，传递关键词
    delete_clicked = pyqtSignal(str)  # 删除按钮点击信号，传递关键词
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupTable()
        
    def setupTable(self):
        """设置表格"""
        # 设置列数和表头
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(['关键词', '操作'])
        
        # 设置表格属性
        self.setAlternatingRowColors(True)  # 交替行颜色
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # 选择整行
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # 单选
        self.verticalHeader().setVisible(False)  # 隐藏行号
        
        # 设置列宽
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 关键词列自动拉伸
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)   # 操作列固定宽度
        
        self.setColumnWidth(1, 250)  # 操作列
        
        # 设置行高
        self.verticalHeader().setDefaultSectionSize(50)
        
    def addKeyword(self, keyword: str):
        """添加关键词到表格"""
        row = self.rowCount()
        self.insertRow(row)
        
        # 关键词
        keyword_item = QTableWidgetItem(keyword)
        keyword_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.setItem(row, 0, keyword_item)
        
        # 操作按钮
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(5, 5, 5, 5)
        action_layout.setSpacing(5)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 编辑按钮
        edit_btn = PushButton("编辑")
        edit_btn.setIcon(FIF.EDIT)
        edit_btn.setFixedSize(100, 30)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(keyword))
        
        # 删除按钮
        delete_btn = PushButton("删除")
        delete_btn.setIcon(FIF.DELETE)
        delete_btn.setFixedSize(100, 30)
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(keyword))
        
        action_layout.addWidget(edit_btn)
        action_layout.addWidget(delete_btn)
        self.setCellWidget(row, 1, action_widget)
        
    def clearTable(self):
        """清空表格"""
        self.setRowCount(0)


class KeywordManagerWidget(QFrame):
    """关键词管理主界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.keywords_data = []  # 存储关键词数据
        self.setupUI()
        self.loadKeywordsFromDB()
        
    def setupUI(self):
        """设置主界面UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        
        # 创建头部区域
        header_widget = self.createHeaderWidget()
        
        # 创建内容区域（表格）
        self.table_widget = KeywordTableWidget()
        
        # 连接表格信号
        self.table_widget.edit_clicked.connect(self.onEditKeyword)
        self.table_widget.delete_clicked.connect(self.onDeleteKeyword)
        
        # 连接按钮信号
        self.add_btn.clicked.connect(self.onAddKeyword)
        self.import_btn.clicked.connect(self.onImportKeywords)
        
        # 添加到主布局
        main_layout.addWidget(header_widget)
        main_layout.addWidget(self.table_widget, 1)
        
        # 设置对象名
        self.setObjectName("关键词管理")
    
    def createHeaderWidget(self):
        """创建头部区域"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(20)
        
        # 标题
        title_label = SubtitleLabel("关键词管理")
        
        # 统计信息
        self.stats_label = CaptionLabel("共 0 个关键词")
        
        # 左侧标题区域
        title_area = QWidget()
        title_layout = QVBoxLayout(title_area)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(5)
        title_layout.addWidget(title_label)
        title_layout.addWidget(self.stats_label)
        
        # 添加关键词按钮
        self.add_btn = PrimaryPushButton("添加关键词")
        self.add_btn.setIcon(FIF.ADD)
        self.add_btn.setFixedSize(120, 40)
        
        # 批量导入按钮
        self.import_btn = PushButton("批量导入")
        self.import_btn.setIcon(FIF.FOLDER_ADD)
        self.import_btn.setFixedSize(120, 40)
        
        # 按钮容器
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(self.import_btn)
        buttons_layout.addWidget(self.add_btn)
        
        # 添加到头部布局
        header_layout.addWidget(title_area)
        header_layout.addStretch()
        header_layout.addWidget(buttons_widget)
        
        return header_widget
    

    
    def loadKeywordsFromDB(self):
        """从数据库加载关键词数据"""
        try:
            # 从数据库获取所有关键词
            keywords = db_manager.get_all_keywords()
            self.keywords_data = [{"keyword": kw["keyword"]} for kw in keywords]
            
            # 如果数据库为空，初始化示例关键词
            if not self.keywords_data:
                self.initializeSampleKeywords()
            
            self.refreshKeywordList()
        except Exception as e:
            print(f"加载关键词失败: {e}")
            # 如果数据库加载失败，使用示例数据
            self.initializeSampleKeywords()
    
    def initializeSampleKeywords(self):
        """初始化示例关键词到数据库"""
        sample_keywords = [
            "转人工", "人工客服", "真人", "客服", "人工", "工单", "好评",
            "取消订单", "改地址", "转售后客服", "转售后", "返现", "过敏",
            "退款", "没有效果", "骗人", "投诉", "纠纷", "开发票", "开票",
            "烂", "取消", "备注"
        ]
        
        # 将示例关键词添加到数据库
        for keyword in sample_keywords:
            if db_manager.add_keyword(keyword):
                self.keywords_data.append({"keyword": keyword})
        
        self.refreshKeywordList()
    
    def refreshKeywordList(self):
        """刷新关键词列表"""
        # 清空表格
        self.table_widget.clearTable()
        
        # 添加关键词到表格
        for keyword_data in self.keywords_data:
            self.table_widget.addKeyword(keyword_data["keyword"])
        
        # 更新统计信息
        self.updateStats()
    
    def updateStats(self):
        """更新统计信息"""
        total_count = len(self.keywords_data)
        self.stats_label.setText(f"共 {total_count} 个关键词")
    
    def onEditKeyword(self, keyword: str):
        """编辑关键词回调"""
        text, ok = QInputDialog.getText(
            self, '编辑关键词', 
            '请修改关键词:', 
            text=keyword  # 预填充当前关键词
        )
        
        if ok and text.strip():
            new_keyword = text.strip()
            
            # 如果没有修改，直接返回
            if new_keyword == keyword:
                return
                
            # 使用统一的更新方法
            if self.updateKeyword(keyword, new_keyword):
                QMessageBox.information(self, '成功', f'关键词修改成功!\n"{keyword}" -> "{new_keyword}"')
            else:
                QMessageBox.warning(self, '失败', f'关键词修改失败!\n新关键词 "{new_keyword}" 可能已存在或为空')
    
    def onDeleteKeyword(self, keyword: str):
        """删除关键词回调"""
        # 确认删除
        reply = QMessageBox.question(
            self, '确认删除', 
            f'确定要删除关键词 "{keyword}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 从数据库删除关键词
                if db_manager.delete_keyword(keyword):
                    print(f"成功删除关键词: {keyword}")
                    # 从本地数据中移除
                    self.keywords_data = [k for k in self.keywords_data if k["keyword"] != keyword]
                    self.refreshKeywordList()
                    QMessageBox.information(self, '成功', f'关键词 "{keyword}" 删除成功!')
                else:
                    print(f"删除关键词失败: {keyword}")
                    QMessageBox.warning(self, '失败', f'删除关键词 "{keyword}" 失败!')
            except Exception as e:
                print(f"删除关键词出错: {e}")
                QMessageBox.critical(self, '错误', f'删除关键词时出错: {str(e)}')
        
    def addKeyword(self, keyword: str):
        """添加新关键词"""
        try:
            # 检查关键词是否为空
            if not keyword.strip():
                print("关键词不能为空")
                return False
                
            # 添加到数据库
            if db_manager.add_keyword(keyword.strip()):
                print(f"成功添加关键词: {keyword}")
                # 添加到本地数据
                self.keywords_data.append({"keyword": keyword.strip()})
                self.refreshKeywordList()
                return True
            else:
                print(f"添加关键词失败: {keyword} (可能已存在)")
                return False
        except Exception as e:
            print(f"添加关键词出错: {e}")
            return False
    
    def removeKeyword(self, keyword: str):
        """移除关键词"""
        try:
            # 从数据库删除
            if db_manager.delete_keyword(keyword):
                # 从本地数据中移除
                self.keywords_data = [k for k in self.keywords_data if k["keyword"] != keyword]
                self.refreshKeywordList()
                return True
            else:
                return False
        except Exception as e:
            print(f"移除关键词出错: {e}")
            return False
            
    def updateKeyword(self, old_keyword: str, new_keyword: str):
        """更新关键词"""
        try:
            # 检查关键词是否为空
            if not new_keyword.strip():
                print("新关键词不能为空")
                return False
                
            # 如果没有修改，直接返回成功
            if old_keyword == new_keyword.strip():
                return True
                
            # 更新数据库
            if db_manager.update_keyword(old_keyword, new_keyword.strip()):
                print(f"成功更新关键词: {old_keyword} -> {new_keyword}")
                
                # 更新本地数据
                for i, kw_data in enumerate(self.keywords_data):
                    if kw_data["keyword"] == old_keyword:
                        self.keywords_data[i]["keyword"] = new_keyword.strip()
                        break
                
                # 刷新界面
                self.refreshKeywordList()
                return True
            else:
                print(f"更新关键词失败: {old_keyword} -> {new_keyword} (可能已存在)")
                return False
        except Exception as e:
            print(f"更新关键词出错: {e}")
            return False
    
    def reloadKeywords(self):
        """重新加载关键词数据"""
        self.loadKeywordsFromDB()
        
    def onAddKeyword(self):
        """添加关键词按钮点击事件"""
        text, ok = QInputDialog.getText(self, '添加关键词', '请输入关键词:')
        if ok and text.strip():
            if self.addKeyword(text.strip()):
                QMessageBox.information(self, '成功', f'关键词 "{text.strip()}" 添加成功!')
            else:
                QMessageBox.warning(self, '失败', f'关键词 "{text.strip()}" 添加失败，可能已存在!')
    
    def onImportKeywords(self):
        """批量导入关键词按钮点击事件"""
        text, ok = QInputDialog.getMultiLineText(
            self, '批量导入关键词', 
            '请输入关键词，每行一个:\n(空行将被忽略)'
        )
        if ok and text.strip():
            keywords = [line.strip() for line in text.split('\n') if line.strip()]
            success_count = 0
            duplicate_count = 0
            
            for keyword in keywords:
                if self.addKeyword(keyword):
                    success_count += 1
                else:
                    duplicate_count += 1
            
            message = f'导入完成!\n成功: {success_count} 个\n重复/失败: {duplicate_count} 个'
            QMessageBox.information(self, '导入结果', message)
