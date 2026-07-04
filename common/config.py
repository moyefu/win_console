# -*- coding: utf-8 -*-
"""共享配置层：定义 C/S 架构的默认配置常量。"""

import os
import sys

# ---- 网络配置 ----
DEFAULT_HOST = '0.0.0.0'       # 服务端默认监听地址
DEFAULT_PORT = 9081            # 服务端默认监听端口
DEFAULT_WS_PORT = 9082         # 客户端 WebSocket 默认监听端口
CLIENT_WS_PORT_OFFSET = 1     # 客户端 WebSocket 端口偏移量（客户端 WS 端口 = DEFAULT_PORT + 此值）

# ---- 心跳配置 ----
HEARTBEAT_INTERVAL = 10        # 心跳发送间隔（秒）
HEARTBEAT_TIMEOUT = 30         # 心跳超时时间（秒）

# ---- 重连配置 ----
RECONNECT_INTERVAL = 5         # 客户端重连间隔（秒）

# ---- 截图配置 ----
JPEG_QUALITY = 70              # 截图 JPEG 压缩质量（1-100）

# ---- 键盘记录配置 ----
KEYLOG_MAX = 500               # 键盘记录最大条数

# ---- 进程列表配置 ----
PROCESS_LIMIT = 200            # 进程列表最大返回数量

# ---- 文件路径配置 ----
# 配置根目录：~/.winconsole/
_config_root = os.path.join(os.path.expanduser('~'), '.winconsole')

SERVER_CONFIG_FILE = os.path.join(_config_root, 'server_config.json')   # 服务端配置文件路径
DEVICES_FILE = os.path.join(_config_root, 'devices.json')               # 设备信息持久化文件路径
