# -*- coding: utf-8 -*-
"""WinConsole 服务端 Flask 应用"""
import os
import sys
import asyncio
import logging
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify
from flask_sock import Sock

from common.config import DEFAULT_HOST, DEFAULT_PORT, HEARTBEAT_INTERVAL
from common.protocol import MsgType, encode_msg, decode_msg, make_msg
from server.client_manager import ClientManager


def get_template_dir():
    """获取模板目录路径，兼容 PyInstaller 打包环境。"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'templates')
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')


def create_app(client_manager=None):
    """创建 Flask 应用实例。

    Args:
        client_manager: ClientManager 实例，为 None 时自动创建

    Returns:
        Flask 应用实例
    """
    app = Flask(__name__, template_folder=get_template_dir())
    sock = Sock(app)
    from server.auth import register_auth
    register_auth(app)

    if client_manager is None:
        client_manager = ClientManager()

    app.client_manager = client_manager
    app.sock = sock

    # 注册蓝图
    from server.api.dashboard import dashboard_bp
    from server.api.devices import devices_bp
    from server.api.groups import groups_bp
    from server.api.remote import register_remote_routes
    from server.api.settings import settings_bp
    from server.api.events import register_events_ws

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(settings_bp)

    # 为需要访问 app 的蓝图设置引用
    dashboard_bp.app = app
    devices_bp.app = app
    groups_bp.app = app
    settings_bp.app = app

    register_remote_routes(app, sock, client_manager)
    register_events_ws(sock, client_manager)

    # 首页
    @app.route('/')
    def index():
        return render_template('index.html')

    # 启动心跳检测线程
    _start_heartbeat_checker(client_manager)

    return app


def _start_heartbeat_checker(cm):
    """后台线程定时检查客户端心跳"""
    def checker():
        while True:
            try:
                cm.check_heartbeats()
            except Exception as e:
                logging.error(f"Heartbeat check error: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

    t = threading.Thread(target=checker, daemon=True)
    t.start()
