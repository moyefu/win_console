# -*- coding: utf-8 -*-
"""服务端客户端管理模块：管理客户端连接、心跳、指令转发、持久化等。"""

import asyncio
import json
import uuid
import time
import threading
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Set, Callable, List, Any

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import MsgType, encode_msg, decode_msg, make_msg
from common.config import *

logger = logging.getLogger(__name__)


@dataclass
class ClientSession:
    """客户端会话数据类，保存单个客户端的所有状态信息。"""
    client_id: str
    ws: object  # WebSocket 连接对象
    hostname: str = ''
    ip: str = ''
    os_name: str = ''
    os_version: str = ''
    arch: str = ''
    group: str = ''
    remark: str = ''
    online: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    connected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_online_at: str = field(default_factory=lambda: datetime.now().isoformat())
    connection_history: list = field(default_factory=list)
    pending_requests: dict = field(default_factory=dict)  # seq → asyncio.Future


class ClientManager:
    """客户端管理器，负责客户端注册/注销、心跳检测、指令转发、持久化等。"""

    def __init__(self):
        self.clients: Dict[str, ClientSession] = {}  # client_id → session
        self.groups: list = []                        # 分组名称列表
        self.alerts: list = []                        # 异常警报列表
        self._lock = threading.Lock()
        self._event_callbacks: list = []              # 状态变更回调
        self._load_persistent_data()

    # ======================== 客户端注册 / 注销 ========================

    async def register_client(self, ws, device_info: dict) -> str:
        """注册客户端连接。

        如果是已知设备（按 hostname+ip 匹配），则复用原有 client_id 并保留分组、历史等信息；
        否则创建新会话。

        Args:
            ws: WebSocket 连接对象
            device_info: 客户端上报的设备信息字典，含 hostname/ip/os_name/os_version/arch 等

        Returns:
            client_id: 客户端唯一标识
        """
        hostname = device_info.get('hostname', '')
        ip = device_info.get('ip', '')

        # 按 hostname+ip 弹性匹配已知设备
        matched_id = None
        with self._lock:
            for cid, session in self.clients.items():
                if session.hostname == hostname and session.ip == ip:
                    matched_id = cid
                    break

        now_iso = datetime.now().isoformat()

        if matched_id:
            # 已知设备重新上线：复用 client_id，保留分组和历史
            session = self.clients[matched_id]
            session.ws = ws
            session.online = True
            session.last_heartbeat = time.time()
            session.connected_at = now_iso
            session.last_online_at = now_iso
            # 更新设备信息（可能系统升级等）
            session.os_name = device_info.get('os_name', session.os_name)
            session.os_version = device_info.get('os_version', session.os_version)
            session.arch = device_info.get('arch', session.arch)
            # 记录连接历史
            session.connection_history.append({
                'event': 'online',
                'time': now_iso,
            })
            client_id = matched_id
            logger.info(f"已知设备重新上线: {client_id} ({hostname}/{ip})")
        else:
            # 新设备
            client_id = uuid.uuid4().hex[:16]
            session = ClientSession(
                client_id=client_id,
                ws=ws,
                hostname=hostname,
                ip=ip,
                os_name=device_info.get('os_name', ''),
                os_version=device_info.get('os_version', ''),
                arch=device_info.get('arch', ''),
                online=True,
                last_heartbeat=time.time(),
                connected_at=now_iso,
                last_online_at=now_iso,
                connection_history=[{'event': 'online', 'time': now_iso}],
            )
            with self._lock:
                self.clients[client_id] = session
            logger.info(f"新设备注册: {client_id} ({hostname}/{ip})")

        # 触发 online 事件
        self._fire_event('online', client_id, {'hostname': hostname, 'ip': ip})
        self._save_persistent_data()
        return client_id

    async def unregister_client(self, client_id: str):
        """注销客户端连接，标记为离线但保留设备信息。

        Args:
            client_id: 客户端唯一标识
        """
        with self._lock:
            session = self.clients.get(client_id)
            if not session:
                return

            now_iso = datetime.now().isoformat()
            session.online = False
            session.ws = None
            session.pending_requests.clear()
            session.last_online_at = now_iso
            session.connection_history.append({
                'event': 'offline',
                'time': now_iso,
            })

        # 添加离线警报
        self._add_alert(client_id, session.hostname, 'offline', f"设备 {session.hostname} 已离线")
        # 触发 offline 事件
        self._fire_event('offline', client_id, {'hostname': session.hostname, 'ip': session.ip})
        self._save_persistent_data()
        logger.info(f"设备离线: {client_id} ({session.hostname})")

    # ======================== 心跳 ========================

    def update_heartbeat(self, client_id: str):
        """更新客户端心跳时间。

        Args:
            client_id: 客户端唯一标识
        """
        with self._lock:
            session = self.clients.get(client_id)
            if session:
                session.last_heartbeat = time.time()
                session.last_online_at = datetime.now().isoformat()

    def check_heartbeats(self) -> list:
        """检查所有在线客户端的心跳，将超时的标记为离线。

        Returns:
            新离线的 client_id 列表
        """
        now = time.time()
        offline_ids = []

        with self._lock:
            for client_id, session in list(self.clients.items()):
                if not session.online:
                    continue
                if now - session.last_heartbeat > HEARTBEAT_TIMEOUT:
                    session.online = False
                    session.ws = None
                    session.pending_requests.clear()
                    now_iso = datetime.now().isoformat()
                    session.last_online_at = now_iso
                    session.connection_history.append({
                        'event': 'offline',
                        'time': now_iso,
                    })
                    offline_ids.append(client_id)

        # 在锁外触发事件和警报，避免死锁
        for client_id in offline_ids:
            session = self.clients.get(client_id)
            if session:
                self._add_alert(client_id, session.hostname, 'heartbeat_timeout',
                                f"设备 {session.hostname} 心跳超时")
                self._fire_event('offline', client_id, {
                    'hostname': session.hostname,
                    'ip': session.ip,
                    'reason': 'heartbeat_timeout',
                })
                logger.warning(f"心跳超时，设备离线: {client_id} ({session.hostname})")

        if offline_ids:
            self._save_persistent_data()

        return offline_ids

    # ======================== 指令转发 ========================

    async def forward_command(self, client_id: str, msg: dict) -> dict:
        """向指定客户端转发指令并等待响应。

        Args:
            client_id: 目标客户端 ID
            msg: 要发送的消息字典

        Returns:
            客户端的响应字典；如果客户端不在线或超时，返回错误响应

        Note:
            此方法需要运行在 asyncio 事件循环中。Flask 同步 API 层调用时
            需通过 asyncio.run_coroutine_threadsafe 等方式桥接。
        """
        with self._lock:
            session = self.clients.get(client_id)

        if not session or not session.online or session.ws is None:
            return make_msg(MsgType.ERROR, client_id, {
                'error': '客户端不在线',
                'code': 'CLIENT_OFFLINE',
            })

        # 生成唯一 seq 编号
        seq = int(time.time() * 1000) % (10 ** 9) + id(msg) % 1000
        msg['seq'] = seq

        # 创建 Future 用于等待响应
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        with self._lock:
            session = self.clients.get(client_id)
            if not session or not session.online:
                return make_msg(MsgType.ERROR, client_id, {
                    'error': '客户端不在线',
                    'code': 'CLIENT_OFFLINE',
                })
            session.pending_requests[seq] = future

        # 发送消息
        try:
            await session.ws.send(encode_msg(msg))
        except Exception as e:
            # 发送失败，清理 Future
            with self._lock:
                session.pending_requests.pop(seq, None)
            logger.error(f"发送指令到客户端 {client_id} 失败: {e}")
            return make_msg(MsgType.ERROR, client_id, {
                'error': f'发送失败: {e}',
                'code': 'SEND_FAILED',
            })

        # 等待响应（超时 30 秒）
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            with self._lock:
                session.pending_requests.pop(seq, None)
            logger.warning(f"等待客户端 {client_id} 响应超时 (seq={seq})")
            return make_msg(MsgType.ERROR, client_id, {
                'error': '响应超时',
                'code': 'TIMEOUT',
            })
        except Exception as e:
            with self._lock:
                session.pending_requests.pop(seq, None)
            logger.error(f"等待客户端 {client_id} 响应异常: {e}")
            return make_msg(MsgType.ERROR, client_id, {
                'error': f'等待响应异常: {e}',
                'code': 'WAIT_ERROR',
            })

    def resolve_command_response(self, client_id: str, seq: int, response: dict):
        """解析客户端的命令响应，将结果设置到对应的 Future 中。

        Args:
            client_id: 客户端唯一标识
            seq: 消息序号
            response: 客户端响应字典
        """
        with self._lock:
            session = self.clients.get(client_id)
            if not session:
                return
            future = session.pending_requests.pop(seq, None)

        if future and not future.done():
            future.set_result(response)

    async def send_to_client(self, client_id: str, msg: dict):
        """直接发送消息到客户端，不等待响应（用于终端输入等实时流场景）。

        Args:
            client_id: 目标客户端 ID
            msg: 消息字典
        """
        with self._lock:
            session = self.clients.get(client_id)
            if not session or not session.online or session.ws is None:
                return False

        try:
            await session.ws.send(encode_msg(msg))
            return True
        except Exception as e:
            logger.error(f"发送消息到客户端 {client_id} 失败: {e}")
            return False

    # ======================== 设备查询 ========================

    def get_device_list(self, status: str = None, group: str = None,
                        search: str = None) -> list:
        """获取设备列表，支持按状态、分组、关键词筛选。

        Args:
            status: 'online' / 'offline' / None（全部）
            group: 分组名称 / None（全部）
            search: 搜索 hostname 或 ip / None（不搜索）

        Returns:
            匹配的设备信息字典列表
        """
        result = []
        with self._lock:
            for client_id, session in self.clients.items():
                # 状态筛选
                if status == 'online' and not session.online:
                    continue
                if status == 'offline' and session.online:
                    continue
                # 分组筛选
                if group is not None and session.group != group:
                    continue
                # 关键词搜索
                if search:
                    search_lower = search.lower()
                    if (search_lower not in session.hostname.lower() and
                            search_lower not in session.ip.lower()):
                        continue

                result.append(self._session_to_dict(session))

        return result

    def get_device(self, client_id: str) -> Optional[ClientSession]:
        """获取指定设备的会话信息。

        Args:
            client_id: 客户端唯一标识

        Returns:
            ClientSession 对象，不存在则返回 None
        """
        with self._lock:
            return self.clients.get(client_id)

    def delete_device(self, client_id: str) -> bool:
        """从管理器中完全删除设备记录。

        Args:
            client_id: 客户端唯一标识

        Returns:
            是否删除成功
        """
        with self._lock:
            if client_id not in self.clients:
                return False
            del self.clients[client_id]

        self._save_persistent_data()
        logger.info(f"设备记录已删除: {client_id}")
        return True

    def set_device_group(self, client_id: str, group: str) -> bool:
        """设置设备所属分组。

        Args:
            client_id: 客户端唯一标识
            group: 分组名称

        Returns:
            是否设置成功
        """
        with self._lock:
            session = self.clients.get(client_id)
            if not session:
                return False
            session.group = group

        self._save_persistent_data()
        return True

    def set_device_remark(self, client_id: str, remark: str) -> bool:
        """设置设备备注。

        Args:
            client_id: 客户端唯一标识
            remark: 备注内容

        Returns:
            是否设置成功
        """
        with self._lock:
            session = self.clients.get(client_id)
            if not session:
                return False
            session.remark = remark

        self._save_persistent_data()
        return True

    # ======================== 分组管理 ========================

    def get_groups(self) -> list:
        """获取所有分组名称列表。"""
        with self._lock:
            return list(self.groups)

    def create_group(self, name: str) -> bool:
        """创建新分组。

        Args:
            name: 分组名称

        Returns:
            是否创建成功（已存在返回 False）
        """
        with self._lock:
            if name in self.groups:
                return False
            self.groups.append(name)

        self._save_persistent_data()
        logger.info(f"分组已创建: {name}")
        return True

    def delete_group(self, name: str) -> bool:
        """删除分组，并将该分组下设备的 group 字段清空。

        Args:
            name: 分组名称

        Returns:
            是否删除成功
        """
        with self._lock:
            if name not in self.groups:
                return False
            self.groups.remove(name)
            # 清除该分组下设备的 group 字段
            for session in self.clients.values():
                if session.group == name:
                    session.group = ''

        self._save_persistent_data()
        logger.info(f"分组已删除: {name}")
        return True

    def rename_group(self, old_name: str, new_name: str) -> bool:
        """重命名分组，并更新该分组下设备的 group 字段。

        Args:
            old_name: 原分组名
            new_name: 新分组名

        Returns:
            是否重命名成功
        """
        with self._lock:
            if old_name not in self.groups:
                return False
            if new_name in self.groups:
                return False
            idx = self.groups.index(old_name)
            self.groups[idx] = new_name
            # 更新该分组下设备的 group 字段
            for session in self.clients.values():
                if session.group == old_name:
                    session.group = new_name

        self._save_persistent_data()
        logger.info(f"分组已重命名: {old_name} → {new_name}")
        return True

    # ======================== 统计 / 警报 ========================

    def get_dashboard_stats(self) -> dict:
        """获取仪表盘统计数据。"""
        with self._lock:
            total = len(self.clients)
            online = sum(1 for s in self.clients.values() if s.online)
        return {
            'total': total,
            'online': online,
            'offline': total - online,
            'alert_count': len(self.alerts),
        }

    def get_alerts(self, limit: int = 50) -> list:
        """获取最近的警报列表。

        Args:
            limit: 返回的最大条数

        Returns:
            警报字典列表，按时间倒序
        """
        return list(reversed(self.alerts[-limit:]))

    # ======================== 事件回调 ========================

    def on_event(self, callback: Callable):
        """注册事件回调。

        回调签名: callback(event_type: str, client_id: str, data: dict)
        event_type: 'online' / 'offline' / 'alert'

        Args:
            callback: 回调函数
        """
        self._event_callbacks.append(callback)

    def _fire_event(self, event_type: str, client_id: str, data: dict = None):
        """触发事件，通知所有注册的回调。"""
        for cb in self._event_callbacks:
            try:
                cb(event_type, client_id, data or {})
            except Exception as e:
                logger.error(f"事件回调执行异常: {e}")

    # ======================== 持久化 ========================

    def _load_persistent_data(self):
        """从 DEVICES_FILE 加载设备信息和分组。"""
        if not os.path.exists(DEVICES_FILE):
            logger.info("持久化文件不存在，跳过加载")
            return

        try:
            with open(DEVICES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.groups = data.get('groups', [])
            self.alerts = data.get('alerts', [])

            # 恢复客户端信息（不含 ws 和 pending_requests）
            clients_data = data.get('clients', {})
            with self._lock:
                for cid, info in clients_data.items():
                    session = ClientSession(
                        client_id=cid,
                        ws=None,
                        hostname=info.get('hostname', ''),
                        ip=info.get('ip', ''),
                        os_name=info.get('os_name', ''),
                        os_version=info.get('os_version', ''),
                        arch=info.get('arch', ''),
                        group=info.get('group', ''),
                        online=False,  # 加载时一律标记为离线
                        last_heartbeat=info.get('last_heartbeat', 0),
                        connected_at=info.get('connected_at', ''),
                        last_online_at=info.get('last_online_at', ''),
                        connection_history=info.get('connection_history', []),
                    )
                    self.clients[cid] = session

            logger.info(f"已加载持久化数据: {len(self.clients)} 个设备, {len(self.groups)} 个分组")
        except Exception as e:
            logger.error(f"加载持久化数据失败: {e}")

    def _save_persistent_data(self):
        """保存设备信息和分组到 DEVICES_FILE。"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)

            clients_data = {}
            with self._lock:
                for cid, session in self.clients.items():
                    clients_data[cid] = {
                        'hostname': session.hostname,
                        'ip': session.ip,
                        'os_name': session.os_name,
                        'os_version': session.os_version,
                        'arch': session.arch,
                        'group': session.group,
                        'online': session.online,
                        'last_heartbeat': session.last_heartbeat,
                        'connected_at': session.connected_at,
                        'last_online_at': session.last_online_at,
                        'connection_history': session.connection_history,
                    }

            data = {
                'clients': clients_data,
                'groups': self.groups,
                'alerts': self.alerts,
            }

            with open(DEVICES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug("持久化数据已保存")
        except Exception as e:
            logger.error(f"保存持久化数据失败: {e}")

    # ======================== 辅助方法 ========================

    def get_all_online_ws(self) -> dict:
        """获取所有在线客户端的 WebSocket 连接。

        Returns:
            {client_id: ws} 字典
        """
        result = {}
        with self._lock:
            for cid, session in self.clients.items():
                if session.online and session.ws is not None:
                    result[cid] = session.ws
        return result

    def _session_to_dict(self, session: ClientSession) -> dict:
        """将 ClientSession 转换为可序列化的字典（排除 ws 和 pending_requests）。"""
        return {
            'client_id': session.client_id,
            'hostname': session.hostname,
            'ip': session.ip,
            'os_name': session.os_name,
            'os_version': session.os_version,
            'arch': session.arch,
            'group': session.group,
            'remark': session.remark,
            'online': session.online,
            'last_heartbeat': session.last_heartbeat,
            'connected_at': session.connected_at,
            'last_online_at': session.last_online_at,
            'connection_history': session.connection_history,
        }

    def _add_alert(self, client_id: str, hostname: str, alert_type: str, message: str):
        """添加一条警报记录。"""
        alert = {
            'time': datetime.now().isoformat(),
            'client_id': client_id,
            'hostname': hostname,
            'type': alert_type,
            'message': message,
        }
        self.alerts.append(alert)
        # 限制警报列表最大长度，避免无限增长
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-500:]
        # 触发 alert 事件
        self._fire_event('alert', client_id, alert)
