import os
import sys
import threading
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QSystemTrayIcon, 
                              QMenu, QStyle, QMessageBox, QDialog, QVBoxLayout, 
                              QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                              QGroupBox, QCheckBox, QStatusBar, QTextEdit, QDialogButtonBox,
                              QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction
import requests
import json
import re
import time
import subprocess
import signal
import logging
from datetime import datetime

# 添加资源管理函数
def resource_path(relative_path):
    """获取资源的绝对路径，支持开发环境和PyInstaller打包环境"""
    try:
        # PyInstaller创建临时文件夹，将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# 设置日志
def setup_logging():
    # 获取exe所在目录
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    
    log_file = os.path.join(exe_dir, 'log.txt')
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8', mode='a'),  # 追加模式
            logging.StreamHandler()  # 同时输出到控制台
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

# 动态导入服务器模块的函数
def import_server_module():
    """动态导入服务器模块，支持开发环境和打包环境"""
    try:
        # 首先尝试直接导入（开发环境）
        import server_main
        logger.info("成功导入 server_main 模块")
        return server_main
    except ImportError:
        try:
            # 打包环境：在临时目录中查找
            if hasattr(sys, '_MEIPASS'):
                # 在临时目录中查找 server_main.py
                temp_dir = sys._MEIPASS
                server_main_path = os.path.join(temp_dir, 'server_main.py')
                
                if os.path.exists(server_main_path):
                    # 动态导入模块
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("server_main", server_main_path)
                    server_module = importlib.util.module_from_spec(spec)
                    sys.modules["server_main"] = server_module
                    spec.loader.exec_module(server_module)
                    logger.info("从临时目录成功导入 server_main 模块")
                    return server_module
            
            # 在当前目录中查找
            current_dir = os.path.dirname(os.path.abspath(__file__))
            server_main_path = os.path.join(current_dir, 'server_main.py')
            
            if os.path.exists(server_main_path):
                # 动态导入模块
                import importlib.util
                spec = importlib.util.spec_from_file_location("server_main", server_main_path)
                server_module = importlib.util.module_from_spec(spec)
                sys.modules["server_main"] = server_module
                spec.loader.exec_module(server_module)
                logger.info("从当前目录成功导入 server_main 模块")
                return server_module
            
            # 在exe所在目录中查找
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                server_main_path = os.path.join(exe_dir, 'server_main.py')
                
                if os.path.exists(server_main_path):
                    # 动态导入模块
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("server_main", server_main_path)
                    server_module = importlib.util.module_from_spec(spec)
                    sys.modules["server_main"] = server_module
                    spec.loader.exec_module(server_module)
                    logger.info("从exe目录成功导入 server_main 模块")
                    return server_module
            
            logger.error("找不到 server_main.py 文件")
            return None
            
        except Exception as e:
            logger.error(f"导入 server_main 模块失败: {e}")
            return None

class UpdateDialog(QDialog):
    def __init__(self, version_info, current_version, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检测到新版本")
        self.setModal(True)
        self.resize(500, 300)
        
        self.version_info = version_info
        
        layout = QVBoxLayout()
        
        # 版本信息
        info_text = f"<b>当前版本:</b> {current_version}<br><br>"
        info_text += f"<b>最新版本:</b> {version_info.get('version', '未知')}<br><br>"
        info_text += f"<b>更新内容:</b> {version_info.get('content', '无')}<br><br>"
        info_text += f"<b>发布时间:</b> {version_info.get('date', '未知')}"
        
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.RichText)
        layout.addWidget(info_label)
        
        # 按钮 - 只显示去更新按钮
        button_layout = QHBoxLayout()
        self.update_btn = QPushButton("去更新")
        
        button_layout.addWidget(self.update_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # 连接信号
        self.update_btn.clicked.connect(self.open_update_url)
    
    def open_update_url(self):
        link = self.version_info.get('link', '')
        if link:
            webbrowser.open(link)
        # 点击更新按钮后直接退出程序，不打开任何窗口
        os._exit(0)
    
    def closeEvent(self, event):
        """重写关闭事件，直接退出程序"""
        os._exit(0)

class VersionHistoryDialog(QDialog):
    def __init__(self, version_list, current_version, parent=None):
        super().__init__(parent)
        self.setWindowTitle("版本历史")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout()
        
        # 当前版本信息
        current_label = QLabel(f"<b>当前版本: {current_version}</b>")
        current_label.setTextFormat(Qt.RichText)
        layout.addWidget(current_label)
        
        # 版本列表
        list_label = QLabel("版本历史:")
        layout.addWidget(list_label)
        
        self.version_list = QListWidget()
        layout.addWidget(self.version_list)
        
        # 填充版本列表
        for version_info in version_list:
            item_text = f"版本: {version_info.get('version', '未知')} - 日期: {version_info.get('date', '未知')}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, version_info)
            self.version_list.addItem(item)
        
        # 详情显示
        detail_label = QLabel("版本详情:")
        layout.addWidget(detail_label)
        
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        layout.addWidget(self.detail_text)
        
        # 按钮
        self.close_btn = QPushButton("关闭")
        layout.addWidget(self.close_btn)
        
        self.setLayout(layout)
        
        # 连接信号
        self.version_list.currentItemChanged.connect(self.show_version_detail)
        self.close_btn.clicked.connect(self.accept)
    
    def show_version_detail(self, current, previous):
        if current:
            version_info = current.data(Qt.UserRole)
            detail_text = f"版本号: {version_info.get('version', '未知')}\n"
            detail_text += f"发布日期: {version_info.get('date', '未知')}\n"
            detail_text += f"更新内容: {version_info.get('content', '无')}\n"
            detail_text += f"链接: {version_info.get('link', '无')}"
            self.detail_text.setPlainText(detail_text)

class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_version="1.0.1"):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(400, 350)
        self.current_version = current_version
        
        layout = QVBoxLayout()
        
        # 版本信息
        version_group = QGroupBox("版本信息")
        version_layout = QVBoxLayout()
        
        version_label = QLabel(f"当前版本: {self.current_version}")
        version_layout.addWidget(version_label)
        
        # 检查更新按钮
        self.check_update_btn = QPushButton("检查更新")
        version_layout.addWidget(self.check_update_btn)
        
        # 查看版本历史按钮
        self.view_history_btn = QPushButton("查看版本历史")
        version_layout.addWidget(self.view_history_btn)
        
        version_group.setLayout(version_layout)
        layout.addWidget(version_group)
        
        # 缓存目录设置
        cache_group = QGroupBox("缓存目录")
        cache_layout = QVBoxLayout()
        
        cache_label = QLabel("歌曲缓存目录:")
        cache_layout.addWidget(cache_label)
        
        cache_edit_layout = QHBoxLayout()
        self.cache_edit = QLineEdit()
        self.cache_edit.setPlaceholderText("请输入缓存目录路径")
        cache_edit_layout.addWidget(self.cache_edit)
        
        self.browse_btn = QPushButton("浏览...")
        cache_edit_layout.addWidget(self.browse_btn)
        cache_layout.addLayout(cache_edit_layout)
        
        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)
        
        # 服务器设置
        server_group = QGroupBox("服务器设置")
        server_layout = QVBoxLayout()
        
        # 主机地址（只读）
        host_layout = QHBoxLayout()
        host_label = QLabel("主机地址:")
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setReadOnly(True)  # 设置为只读
        self.host_edit.setStyleSheet("background-color: #f0f0f0;")  # 灰色背景表示不可编辑
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.host_edit)
        server_layout.addLayout(host_layout)
        
        # 端口设置
        port_layout = QHBoxLayout()
        port_label = QLabel("端口号:")
        self.port_edit = QLineEdit("5000")
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_edit)
        server_layout.addLayout(port_layout)
        
        # 端口警告提示
        port_warning = QLabel("⚠️ 更改端口后，请确保作品中设置的端口号与此一致，否则无法使用！")
        port_warning.setWordWrap(True)
        port_warning.setStyleSheet("color: #ff6b6b; font-size: 10px;")
        server_layout.addWidget(port_warning)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.cancel_btn = QPushButton("取消")
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 连接信号
        self.browse_btn.clicked.connect(self.browse_directory)
        self.save_btn.clicked.connect(self.on_save)
        self.cancel_btn.clicked.connect(self.reject)
        
        # 记录原始端口号
        self.original_port = ""
    
    def browse_directory(self):
        from PySide6.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(self, "选择缓存目录")
        if directory:
            self.cache_edit.setText(directory)
    
    def on_save(self):
        """保存前的端口号检查"""
        new_port = self.port_edit.text().strip()
        
        # 检查端口号是否有效
        try:
            port_num = int(new_port)
            if port_num < 1 or port_num > 65535:
                QMessageBox.warning(self, "端口错误", "端口号必须在 1-65535 范围内！")
                return
        except ValueError:
            QMessageBox.warning(self, "端口错误", "请输入有效的端口号！")
            return
        
        # 如果端口号有变化，显示警告
        if new_port != self.original_port:
            reply = QMessageBox.warning(
                self,
                "端口更改警告",
                "⚠️ 您正在更改端口号！\n\n"
                "更改后请确保在您的作品中设置相同的端口号，否则无法正常使用。\n\n"
                "是否确定要更改端口号？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                # 恢复原来的端口号
                self.port_edit.setText(self.original_port)
                return
        
        self.accept()
    
    def get_settings(self):
        return {
            "cache_dir": self.cache_edit.text(),
            "host": self.host_edit.text(),
            "port": self.port_edit.text()
        }
    
    def set_settings(self, settings):
        self.cache_edit.setText(settings.get("cache_dir", ""))
        self.host_edit.setText(settings.get("host", "127.0.0.1"))
        self.port_edit.setText(settings.get("port", "5000"))
        # 保存原始端口号用于比较
        self.original_port = settings.get("port", "5000")

class MusicMetadataApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tray_icon = None
        self.server_thread = None
        self.server_process = None
        self.settings = {}
        self.current_version = "1.0.1"  # 当前版本号
        self.all_versions = []  # 存储所有版本信息
        self.server_running = False  # 服务器运行状态标志
        self.server_stop_event = threading.Event()  # 用于停止服务器的信号
        self.server_module = None  # 服务器模块
        
        # 记录启动日志
        logger.info("应用程序启动")
        
        # 导入服务器模块
        self.server_module = import_server_module()
        if self.server_module is None:
            logger.error("无法导入服务器模块，应用程序无法启动")
            QMessageBox.critical(None, "错误", "无法加载服务器模块，请确保 server_main.py 文件存在")
            sys.exit(1)
        
        # 检查更新
        if not self.check_for_updates():
            return  # 如果有新版本，更新对话框会处理退出
        
        self.load_settings()
        self.init_ui()
        self.init_tray()
        
        # 启动服务器
        self.start_server()
    
    def check_for_updates(self):
        """检查更新，返回False表示需要更新，True表示不需要更新"""
        try:
            logger.info("开始检查更新...")
            # 请求更新信息
            response = requests.get(
                "https://note.youdao.com/yws/api/note/a6504e3acf68f82cbc84f706fdff52ab?sev=j1&editorType=1&unloginId=a2043894-f5d6-4d93-3ce0-4528f77c1e8f&editorVersion=new-json-editor&sec=v1",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("获取到更新信息响应")
                
                content_str = data.get("content", "{}")
                
                # 解析内容
                content_data = json.loads(content_str)
                
                # 提取所有8的值
                eight_values = []
                
                # 遍历所有包含版本信息的条目
                for item in content_data.get("5", []):
                    if "5" in item:
                        for sub_item in item.get("5", []):
                            if "7" in sub_item:
                                for text_item in sub_item.get("7", []):
                                    if "8" in text_item:
                                        text_content = text_item.get("8", "")
                                        # 去除转义字符
                                        clean_text = text_content.replace("\\\"", "\"").replace("\\\\", "\\")
                                        eight_values.append(clean_text)
                
                # 将所有8的值拼接成一个完整的JSON字符串
                full_json_str = "".join(eight_values)
                
                # 尝试解析为JSON数组
                try:
                    # 使用正则表达式提取所有JSON对象
                    json_pattern = r'\{[^{}]*\}'
                    json_matches = re.findall(json_pattern, full_json_str)
                    
                    for json_str in json_matches:
                        try:
                            version_info = json.loads(json_str)
                            if 'version' in version_info:
                                self.all_versions.append(version_info)
                                logger.info(f"成功解析版本信息: {version_info.get('version')}")
                        except json.JSONDecodeError:
                            # 尝试手动提取键值对
                            try:
                                manual_info = {}
                                # 提取键值对
                                pairs = re.findall(r'\"([^\"]+)\"\s*:\s*\"([^\"]*)\"', json_str)
                                for key, value in pairs:
                                    manual_info[key] = value
                                if 'version' in manual_info:
                                    self.all_versions.append(manual_info)
                                    logger.info(f"手动解析版本信息: {manual_info.get('version')}")
                            except Exception as manual_error:
                                logger.error(f"手动解析失败: {manual_error}")
                
                except Exception as e:
                    logger.error(f"解析完整JSON失败: {e}")
                
                logger.info(f"共找到 {len(self.all_versions)} 个版本条目")
                
                # 获取最后一个条目（最新版本）
                if self.all_versions:
                    # 按版本号排序，确保最后一个是最新版本
                    self.all_versions.sort(key=lambda x: self.version_to_tuple(x.get('version', '0.0.0')))
                    latest_version_info = self.all_versions[-1]
                    latest_version = latest_version_info.get("version", "")
                    
                    logger.info(f"最新版本: {latest_version}, 当前版本: {self.current_version}")
                    
                    # 比较版本
                    if self.compare_versions(latest_version, self.current_version) > 0:
                        logger.info("检测到新版本，显示更新对话框")
                        # 显示更新对话框
                        dialog = UpdateDialog(latest_version_info, self.current_version, self)
                        dialog.exec()
                        # 无论用户点击更新按钮还是关闭按钮，都会退出程序
                        return False
                    else:
                        logger.info("当前已是最新版本")
                        QMessageBox.information(self, "检查更新", "当前已是最新版本！")
                else:
                    logger.warning("未找到有效的版本信息")
                    QMessageBox.warning(self, "检查更新", "未找到有效的版本信息！")
        
        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            QMessageBox.warning(self, "检查更新", f"检查更新失败: {str(e)}")
            # 更新检查失败不影响主程序运行
        
        return True
    
    def version_to_tuple(self, version_str):
        """将版本字符串转换为元组以便比较"""
        try:
            return tuple(map(int, version_str.split('.')))
        except:
            return (0, 0, 0)
    
    def compare_versions(self, v1, v2):
        """比较版本号，返回1表示v1>v2，0表示相等，-1表示v1<v2"""
        try:
            v1_tuple = self.version_to_tuple(v1)
            v2_tuple = self.version_to_tuple(v2)
            
            if v1_tuple > v2_tuple:
                return 1
            elif v1_tuple < v2_tuple:
                return -1
            else:
                return 0
        except:
            return 0
    
    def get_icon(self):
        """获取图标，支持开发环境和打包环境"""
        # 使用资源路径函数获取图标
        icon_path = resource_path("icon.ico")
        
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        
        # 如果都找不到，返回默认图标
        return self.style().standardIcon(QStyle.SP_ComputerIcon)
    
    def load_settings(self):
        # 从配置文件加载设置
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        default_settings = {
            "cache_dir": os.path.join(os.path.expanduser("~"), "MusicCache"),
            "host": "127.0.0.1",  # 固定为本地主机
            "port": "5000",
            "minimize_to_tray": True
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_settings = json.load(f)
                    # 确保host始终为127.0.0.1，不允许更改
                    loaded_settings["host"] = "127.0.0.1"
                    self.settings = loaded_settings
                    logger.info("成功加载配置文件")
            except Exception as e:
                self.settings = default_settings
                logger.error(f"加载配置文件失败: {e}")
        else:
            self.settings = default_settings
            self.save_settings()
            logger.info("创建默认配置文件")
    
    def save_settings(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        # 确保host始终为127.0.0.1
        self.settings["host"] = "127.0.0.1"
        try:
            with open(config_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logger.info("成功保存配置文件")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
    
    def init_ui(self):
        self.setWindowTitle("Metadata Processing Server")
        self.setGeometry(300, 300, 500, 400)
        
        # 设置窗口图标
        self.setWindowIcon(self.get_icon())
        
        # 创建中央部件
        central_widget = QTextEdit()
        central_widget.setReadOnly(True)
        central_widget.setPlaceholderText("服务器日志将显示在这里...")
        self.setCentralWidget(central_widget)
        
        # 创建状态栏
        self.statusBar().showMessage("服务器运行中")
        
        # 创建菜单栏
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        check_update_action = QAction("检查更新", self)
        check_update_action.triggered.connect(self.manual_check_update)
        help_menu.addAction(check_update_action)
        
        version_history_action = QAction("版本历史", self)
        version_history_action.triggered.connect(self.show_version_history)
        help_menu.addAction(version_history_action)
        
        # 添加服务器信息提示
        self.centralWidget().append("服务器已自动启动")
        self.centralWidget().append("如需重启服务器，请重启本程序")
        self.centralWidget().append("主机地址固定为: 127.0.0.1 (localhost)")
        self.centralWidget().append(f"端口号: {self.settings['port']}")
        self.centralWidget().append("请在作品中设置相同的端口号")
        
        logger.info("UI初始化完成")
    
    def init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用")
            return
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.get_icon())
        self.tray_icon.setToolTip("Metadata Processing Server")
        
        # 创建托盘菜单
        tray_menu = QMenu()
        
        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("隐藏", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.show_settings)
        tray_menu.addAction(settings_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
        logger.info("系统托盘初始化完成")
    
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
    
    def toggle_minimize_to_tray(self, checked):
        self.settings["minimize_to_tray"] = checked
        self.save_settings()
    
    def manual_check_update(self):
        """手动检查更新"""
        logger.info("手动检查更新")
        if not self.check_for_updates():
            # 如果检测到更新，直接退出程序
            os._exit(0)
    
    def show_version_history(self):
        """显示版本历史对话框"""
        logger.info("显示版本历史")
        if not self.all_versions:
            QMessageBox.information(self, "版本历史", "暂无版本历史信息")
            return
        
        dialog = VersionHistoryDialog(self.all_versions, self.current_version, self)
        dialog.exec()
    
    def show_settings(self):
        logger.info("显示设置对话框")
        dialog = SettingsDialog(self, self.current_version)
        dialog.set_settings(self.settings)
        
        # 连接设置对话框中的按钮信号
        dialog.check_update_btn.clicked.connect(self.manual_check_update)
        dialog.view_history_btn.clicked.connect(self.show_version_history)
        
        if dialog.exec():
            new_settings = dialog.get_settings()
            self.settings.update(new_settings)
            self.save_settings()
            
            # 显示端口更改成功提示
            if new_settings.get("port") != dialog.original_port:
                logger.info(f"端口号更改为: {new_settings['port']}")
                QMessageBox.information(
                    self,
                    "端口更改成功",
                    f"端口号已更改为: {new_settings['port']}\n\n"
                    "请确保在您的作品中设置相同的端口号，否则无法正常使用。\n\n"
                    "注意：需要重启程序才能使端口更改生效！"
                )
            
            # 添加重启提示到日志
            self.centralWidget().append("设置已保存，请重启程序使更改生效")
    
    def start_server(self):
        # 确保缓存目录存在
        cache_dir = self.settings.get("cache_dir", "")
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            logger.info(f"创建缓存目录: {cache_dir}")
        
        try:
            # 创建新的服务器线程
            self.server_thread = threading.Thread(
                target=self.server_module.run_server,
                args=(self.settings["host"], int(self.settings["port"]), cache_dir),
                daemon=True
            )
            self.server_thread.start()
            
            # 等待一段时间让服务器启动
            time.sleep(2)
            
            # 检查服务器是否成功启动
            if self.check_server_status():
                server_url = f"http://{self.settings['host']}:{self.settings['port']}"
                self.statusBar().showMessage(f"服务器运行在 {server_url}")
                self.server_running = True
                
                # 添加日志
                self.centralWidget().append(f"服务器启动成功 - {server_url}")
                logger.info(f"服务器启动成功: {server_url}")
            else:
                self.statusBar().showMessage("服务器启动失败")
                self.centralWidget().append("错误: 服务器启动失败，端口可能被占用")
                self.server_running = False
                logger.error("服务器启动失败，端口可能被占用")
                
        except Exception as e:
            self.statusBar().showMessage(f"服务器启动失败: {str(e)}")
            self.centralWidget().append(f"错误: {str(e)}")
            self.server_running = False
            logger.error(f"服务器启动失败: {e}")
    
    def check_server_status(self):
        """检查服务器是否正常运行"""
        try:
            url = f"http://{self.settings['host']}:{self.settings['port']}/status"
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"服务器状态检查失败: {e}")
            return False
    
    def closeEvent(self, event):
        if self.settings.get("minimize_to_tray", True) and self.tray_icon:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Metadata Processing Server",
                "应用程序已最小化到系统托盘",
                QSystemTrayIcon.Information,
                2000
            )
            logger.info("应用程序最小化到系统托盘")
        else:
            self.quit_application()
    
    def quit_application(self):
        logger.info("应用程序退出")
        # 停止服务器
        try:
            # 尝试通过HTTP请求优雅停止
            try:
                url = f"http://{self.settings['host']}:{self.settings['port']}/shutdown"
                requests.post(url, timeout=2)
                logger.info("发送服务器关闭请求")
            except Exception as e:
                logger.warning(f"HTTP关闭服务器失败: {e}")
        except Exception as e:
            logger.error(f"停止服务器失败: {e}")
        
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()

def main():
    # 隐藏控制台窗口
    import ctypes
    if hasattr(ctypes, 'windll'):
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 设置应用程序图标
    icon_path = resource_path("icon.ico")
    
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = MusicMetadataApp()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()