# -*- coding: utf-8 -*-
"""鼠标控制处理器：接收服务端鼠标指令，执行移动、点击、滚动等操作。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

import pyautogui
pyautogui.FAILSAFE = False


async def handle_mouse(engine, msg):
    """处理鼠标操作指令。"""
    payload = msg.get('payload', {})
    action = payload.get('action', 'move')
    x = payload.get('x')
    y = payload.get('y')

    try:
        screen_w, screen_h = pyautogui.size()
        result = _execute_mouse_action(action, x, y, payload, screen_w, screen_h)
        resp = make_msg(MsgType.MOUSE, engine.client_id, result, msg.get('seq', 0))
    except Exception as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, msg.get('seq', 0))

    await engine.send_msg(resp)


def _execute_mouse_action(action, x, y, payload, screen_w, screen_h):
    """执行具体的鼠标操作。

    支持的 action：
        move - 移动鼠标
        click - 单击
        doubleClick - 双击
        rightClick - 右键点击
        scroll - 滚轮滚动
        drag - 拖拽
        getPos - 获取当前鼠标位置
    """
    if action == 'move':
        if x is not None and y is not None:
            pyautogui.moveTo(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        return {'status': 'ok', 'action': action}

    elif action == 'click':
        btn = payload.get('button', 'left')
        if x is not None and y is not None:
            pyautogui.click(max(0, min(x, screen_w)), max(0, min(y, screen_h)), button=btn)
        else:
            pyautogui.click(button=btn)
        return {'status': 'ok', 'action': action}

    elif action == 'doubleClick':
        if x is not None and y is not None:
            pyautogui.doubleClick(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        else:
            pyautogui.doubleClick()
        return {'status': 'ok', 'action': action}

    elif action == 'rightClick':
        if x is not None and y is not None:
            pyautogui.rightClick(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        else:
            pyautogui.rightClick()
        return {'status': 'ok', 'action': action}

    elif action == 'scroll':
        clicks = payload.get('clicks', -1)
        pyautogui.scroll(clicks)
        return {'status': 'ok', 'action': action}

    elif action == 'drag':
        if x is not None and y is not None:
            pyautogui.drag(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        return {'status': 'ok', 'action': action}

    elif action == 'getPos':
        pos = pyautogui.position()
        return {'status': 'ok', 'action': action, 'x': pos.x, 'y': pos.y}

    else:
        return {'status': 'error', 'error': f'Unknown action: {action}'}
