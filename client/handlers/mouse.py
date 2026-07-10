# -*- coding: utf-8 -*-
"""鼠标控制处理器：接收服务端鼠标指令，执行移动、点击、滚动等操作。"""

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
        pyautogui.FAILSAFE = False
        _pyautogui = pyautogui
    return _pyautogui


async def handle_mouse(engine, msg):
    """处理鼠标操作指令。"""
    payload = msg.get('payload', {})
    action = payload.get('action', 'move')
    x = payload.get('x')
    y = payload.get('y')

    try:
        pyautogui = _get_pyautogui()
        screen_w, screen_h = pyautogui.size()
        result = _execute_mouse_action(action, x, y, payload, screen_w, screen_h, pyautogui)
        resp = make_msg(MsgType.MOUSE, engine.client_id, result, msg.get('seq', 0))
    except Exception as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, msg.get('seq', 0))

    await engine.send_msg(resp)


def _execute_mouse_action(action, x, y, payload, screen_w, screen_h, pyautogui):
    """执行具体的鼠标操作。

    支持的 action：
        move - 移动鼠标
        click - 单击
        doubleClick - 双击
        rightClick - 右键点击
        scroll - 滚轮滚动
        drag - 拖拽
        getPos - 获取当前鼠标位置
        down - 按下鼠标键
        up - 释放鼠标键
        wheel - 滚轮（用于屏幕控制）
    """
    # 确保坐标在屏幕范围内
    x = max(0, min(x, screen_w)) if x is not None else 0
    y = max(0, min(y, screen_h)) if y is not None else 0

    if action == 'move':
        pyautogui.moveTo(x, y)
        return {'status': 'ok', 'action': action}

    elif action == 'down':
        # 按下鼠标键（用于拖动起点）
        btn = payload.get('button', 0)
        btn_map = {0: 'left', 1: 'middle', 2: 'right'}
        pyautogui.moveTo(x, y)  # 先移动到起点
        pyautogui.mouseDown(button=btn_map.get(btn, 'left'))
        return {'status': 'ok', 'action': action}

    elif action == 'up':
        # 释放鼠标键（用于拖动终点）
        btn = payload.get('button', 0)
        btn_map = {0: 'left', 1: 'middle', 2: 'right'}
        pyautogui.moveTo(x, y)  # 移动到终点
        pyautogui.mouseUp(button=btn_map.get(btn, 'left'))
        return {'status': 'ok', 'action': action}

    elif action == 'wheel':
        # 滚轮滚动
        delta = payload.get('button', 0)  # button 字段存储滚轮方向
        pyautogui.scroll(delta * 100, x, y)  # 放大滚动幅度
        return {'status': 'ok', 'action': action}

    elif action == 'click':
        pyautogui.click(x, y, button='left')
        return {'status': 'ok', 'action': action}

    elif action == 'doubleClick':
        pyautogui.doubleClick(x, y)
        return {'status': 'ok', 'action': action}

    elif action == 'rightClick':
        pyautogui.rightClick(x, y)
        return {'status': 'ok', 'action': action}

    elif action == 'scroll':
        clicks = payload.get('clicks', -1)
        pyautogui.scroll(clicks, x, y)
        return {'status': 'ok', 'action': action}

    elif action == 'drag':
        pyautogui.drag(x, y)
        return {'status': 'ok', 'action': action}

    elif action == 'getPos':
        pos = pyautogui.position()
        return {'status': 'ok', 'action': action, 'x': pos.x, 'y': pos.y}

    else:
        return {'status': 'error', 'error': f'Unknown action: {action}'}
