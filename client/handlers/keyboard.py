# -*- coding: utf-8 -*-
"""键盘控制处理器：接收服务端键盘指令，执行文本输入、按键和组合键操作。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

import pyautogui


async def handle_keyboard(engine, msg):
    """处理键盘操作指令。

    支持的 action：
        type - 输入文本
        press - 按下单个键
        hotkey - 组合键
    """
    payload = msg.get('payload', {})
    action = payload.get('action', 'type')

    try:
        if action == 'type':
            text = payload.get('text', '')
            pyautogui.write(text, interval=payload.get('interval', 0.0))
        elif action == 'press':
            key = payload.get('key', '')
            pyautogui.press(key)
        elif action == 'hotkey':
            keys = payload.get('keys', [])
            if keys:
                pyautogui.hotkey(*keys)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': f'Unknown action: {action}'},
                            msg.get('seq', 0))
            await engine.send_msg(resp)
            return

        resp = make_msg(MsgType.KEYBOARD, engine.client_id,
                        {'status': 'ok', 'action': action},
                        msg.get('seq', 0))
    except Exception as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, msg.get('seq', 0))

    await engine.send_msg(resp)
