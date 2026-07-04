# -*- coding: utf-8 -*-
"""事件推送 WebSocket：将服务端事件实时推送到 Web 前端。"""
import json
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def register_events_ws(sock, cm):
    """注册事件推送 WebSocket。

    当 ClientManager 触发事件（设备上线/离线/警报等）时，
    将事件数据推送到所有已连接的 WebSocket 客户端。

    Args:
        sock: Sock 实例
        cm: ClientManager 实例
    """
    _event_ws_clients = set()
    _event_ws_lock = threading.Lock()

    def _on_event(event_type, client_id, data):
        """ClientManager 事件回调，推送到所有 WebSocket 客户端。"""
        msg = json.dumps({
            'type': event_type,
            'client_id': client_id,
            'data': data,
            'time': datetime.now().isoformat(),
        }, ensure_ascii=False)
        with _event_ws_lock:
            dead = []
            for ws in _event_ws_clients:
                try:
                    ws.send(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _event_ws_clients.discard(ws)

    cm.on_event(_on_event)

    @sock.route('/api/events')
    def events_ws(ws):
        """事件推送 WebSocket 端点。

        客户端连接后可持续接收服务端事件推送；
        仅接收，不处理客户端发送的数据。
        """
        with _event_ws_lock:
            _event_ws_clients.add(ws)
        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
        finally:
            with _event_ws_lock:
                _event_ws_clients.discard(ws)
