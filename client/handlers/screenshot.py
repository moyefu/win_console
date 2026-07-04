# -*- coding: utf-8 -*-
"""截屏处理器：接收服务端截屏指令，截取屏幕并返回 JPEG base64 数据。"""

import asyncio
import io
import base64
import sys
import os
import platform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg
from common.config import JPEG_QUALITY


async def handle_screenshot(engine, msg):
    """处理截屏指令，截取当前屏幕并以 base64 编码返回。"""
    try:
        img = _capture_screenshot()
        if img is None:
            resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                            {'status': 'error', 'error': 'capture failed'},
                            msg.get('seq', 0))
        else:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=JPEG_QUALITY)
            data_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
            resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                            {'status': 'ok', 'data_b64': data_b64},
                            msg.get('seq', 0))
    except Exception as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, msg.get('seq', 0))
    await engine.send_msg(resp)


def _capture_screenshot():
    """跨平台截屏，返回 PIL Image 对象或 None。"""
    current_os = platform.system()
    try:
        if current_os == 'Windows':
            from PIL import ImageGrab
            return ImageGrab.grab()
        elif current_os == 'Darwin':  # macOS
            from PIL import ImageGrab
            return ImageGrab.grab()
        else:  # Linux
            try:
                import pyscreenshot as ImageGrab
                return ImageGrab.grab()
            except ImportError:
                from PIL import ImageGrab
                return ImageGrab.grab()
    except Exception:
        return None
