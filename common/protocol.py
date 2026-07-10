# -*- coding: utf-8 -*-
"""共享协议层：定义 C/S 架构的消息类型、消息结构与编解码函数。"""

import json
import base64
from enum import Enum, unique
from typing import Dict, Any, Optional


@unique
class MsgType(Enum):
    """消息类型枚举，涵盖心跳、注册、命令、屏幕、进程、终端、鼠标、键盘、键盘记录、配置、错误等。"""
    HEARTBEAT = "heartbeat"           # 心跳响应
    HEARTBEAT_REQ = "heartbeat_req"   # 心跳请求
    REGISTER = "register"             # 客户端注册
    REGISTER_ACK = "register_ack"     # 注册确认
    DISCONNECT = "disconnect"         # 断开连接
    COMMAND = "command"               # 执行命令
    SCREENSHOT = "screenshot"         # 截图
    SCREEN_DATA = "screen_data"       # 屏幕帧数据推送（实时流）
    PROCESS = "process"               # 进程列表
    TERMINAL = "terminal"             # 终端会话
    TERMINAL_DATA = "terminal_data"   # 终端数据
    MOUSE = "mouse"                   # 鼠标操作
    KEYBOARD = "keyboard"             # 键盘操作
    KEYLOG = "keylog"                 # 键盘记录请求
    KEYLOG_DATA = "keylog_data"       # 键盘记录数据
    SYSTEM_INFO = "system_info"       # 系统信息（CPU/内存使用率）
    CAMERA = "camera"                 # 摄像头控制指令
    CAMERA_DATA = "camera_data"       # 摄像头帧数据推送
    DISK = "disk"                     # 硬盘信息请求/响应
    FILE_TRANSFER = "file_transfer"   # 文件传输控制
    FILE_TRANSFER_DATA = "file_transfer_data"  # 文件传输二进制数据块
    FILE_MANAGER = "file_manager"     # 文件管理操作
    CONFIG = "config"                 # 配置
    ERROR = "error"                   # 错误


def make_msg(msg_type: MsgType, client_id: str = '', payload: Optional[Dict] = None,
             seq: int = 0) -> Dict[str, Any]:
    """便捷构造函数，创建消息字典。

    Args:
        msg_type: 消息类型
        client_id: 客户端标识
        payload: 消息负载，二进制数据应使用 data_b64 字段（base64 编码字符串）
        seq: 消息序号

    Returns:
        消息字典
    """
    return {
        'type': msg_type.value,
        'client_id': client_id,
        'payload': payload if payload is not None else {},
        'seq': seq,
    }


def encode_msg(msg: Dict[str, Any]) -> str:
    """将消息字典序列化为 JSON 字符串。

    Args:
        msg: 消息字典，包含 type、client_id、payload、seq 字段

    Returns:
        JSON 字符串
    """
    return json.dumps(msg, ensure_ascii=False)


def decode_msg(data: str) -> Dict[str, Any]:
    """将 JSON 字符串反序列化为消息字典。

    Args:
        data: JSON 字符串

    Returns:
        消息字典，包含 type(str)、client_id(str)、payload(dict)、seq(int) 字段
    """
    msg = json.loads(data)
    # 确保 type 字段转换为 MsgType 枚举值（字符串形式）
    # 调用方可根据需要进一步将 msg['type'] 转为 MsgType 枚举
    return msg
