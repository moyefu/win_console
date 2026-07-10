# -*- coding: utf-8 -*-
"""键盘控制处理器：接收服务端键盘指令，执行文本输入、按键和组合键操作。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

# 延迟导入 pyautogui，避免启动时加载 numpy/cv2
_pyautogui = None

def _get_pyautogui():
    """延迟获取 pyautogui 模块。"""
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        _pyautogui = pyautogui
    return _pyautogui


async def handle_keyboard(engine, msg):
    """处理键盘操作指令。

    支持的 action：
        type - 输入文本
        press - 按下单个键
        hotkey - 组合键
        combo - 组合键（字符串格式，如 'ctrl+c'）
    """
    payload = msg.get('payload', {})
    action = payload.get('action', 'type')

    try:
        pyautogui = _get_pyautogui()

        if action == 'type':
            text = payload.get('text', '')
            pyautogui.write(text, interval=payload.get('interval', 0.0))
        elif action == 'press':
            key = payload.get('key', '')
            if key:
                # 规范化键名
                if key.lower() == 'del':
                    key = 'delete'
                elif key.lower() == 'esc':
                    key = 'escape'
                pyautogui.press(key)
        elif action == 'hotkey':
            keys = payload.get('keys', [])
            if keys:
                pyautogui.hotkey(*keys)
        elif action == 'combo':
            # 组合键字符串格式，如 'ctrl+c'
            combo = payload.get('combo', '')
            if combo:
                # 将加号分隔转换为列表，并规范化键名
                keys = []
                for k in combo.replace('+', ' ').split():
                    k = k.strip().lower()
                    # 规范化键名
                    if k == 'del':
                        k = 'delete'
                    elif k == 'esc':
                        k = 'escape'
                    elif k == 'win':
                        k = 'winleft'
                    keys.append(k)
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
