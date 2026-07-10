# -*- coding: utf-8 -*-
"""屏幕实时流处理器：通过 WebSocket 推送屏幕帧数据，也支持单次截图。"""

import asyncio
import base64
import logging
from io import BytesIO
from PIL import ImageGrab

from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.screen_stream')

# 屏幕流状态
_active = False
_fps = 5  # 默认帧率
_quality = 75  # JPEG 质量
_task = None


async def handle_screen_stream(engine, msg):
    """处理屏幕流控制指令和单次截图。

    payload:
        - action: 'start' | 'stop' | 'config' | 'capture'
        - fps: 帧率（可选）
        - quality: JPEG 质量（可选）
    """
    global _fps, _quality  # 需要声明 global，因为 config 分支会修改
    payload = msg.get('payload', {})
    seq = msg.get('seq', 0)
    action = payload.get('action', 'capture')  # 默认为单次截图

    if action == 'start':
        fps = payload.get('fps', 5)
        quality = payload.get('quality', 75)
        await _start_stream(engine, fps, quality, seq)
    elif action == 'stop':
        await _stop_stream(engine, seq)
    elif action == 'config':
        fps = payload.get('fps', _fps)
        quality = payload.get('quality', _quality)
        _fps = fps
        _quality = quality
        resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                        {'action': 'config', 'fps': fps, 'quality': quality, 'success': True}, seq)
        await engine.send_msg(resp)
    elif action == 'capture':
        # 单次截图
        await _capture_once(engine, seq)


async def _capture_once(engine, seq):
    """单次截图。"""
    loop = asyncio.get_event_loop()

    try:
        img = await loop.run_in_executor(None, _capture_screen)
        if img:
            data_b64 = await loop.run_in_executor(None, _encode_frame, img, _quality)
            resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                            {'action': 'capture', 'data_b64': data_b64, 'success': True}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': 'Screenshot failed', 'code': 'CAPTURE_FAILED'}, seq)
        await engine.send_msg(resp)
    except Exception as e:
        logger.error(f'[截图] 失败: {e}')
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e), 'code': 'CAPTURE_FAILED'}, seq)
        await engine.send_msg(resp)


async def _start_stream(engine, fps, quality, seq):
    """启动屏幕帧推送循环。"""
    global _active, _fps, _quality, _task

    if _active:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': 'Screen stream already active', 'code': 'ALREADY_ACTIVE'}, seq)
        await engine.send_msg(resp)
        return

    _active = True
    _fps = fps
    _quality = quality

    # 获取屏幕尺寸
    try:
        screen_size = _get_screen_size()
    except Exception:
        screen_size = {'width': 1920, 'height': 1080}

    # 启动帧推送任务
    _task = asyncio.create_task(_frame_loop(engine))

    resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                    {'action': 'start', 'fps': fps, 'quality': quality, 'screen': screen_size, 'success': True}, seq)
    await engine.send_msg(resp)
    logger.info(f'[屏幕流] 启动成功，帧率={fps}，质量={quality}，屏幕={screen_size}')


async def _stop_stream(engine, seq):
    """停止屏幕帧推送。"""
    global _active, _task

    if not _active:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': 'Screen stream not active', 'code': 'NOT_ACTIVE'}, seq)
        await engine.send_msg(resp)
        return

    _active = False
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None

    resp = make_msg(MsgType.SCREENSHOT, engine.client_id,
                    {'action': 'stop', 'success': True}, seq)
    await engine.send_msg(resp)
    logger.info('[屏幕流] 已停止')


async def _frame_loop(engine):
    """屏幕帧推送循环。"""
    loop = asyncio.get_event_loop()

    while _active:
        try:
            # 检查 engine 是否有效
            if engine is None or not hasattr(engine, 'send_msg'):
                logger.warning('[屏幕帧推送] engine 无效，停止推送')
                break

            # 在线程池中执行截图（避免阻塞）
            img = await loop.run_in_executor(None, _capture_screen)

            if img:
                # 编码为 JPEG
                data_b64 = await loop.run_in_executor(None, _encode_frame, img, _quality)

                # 发送帧数据
                msg = make_msg(MsgType.SCREEN_DATA, engine.client_id,
                               {'data_b64': data_b64, 'fps': _fps, 'quality': _quality})
                await engine.send_msg(msg)

            # 控制帧率
            await asyncio.sleep(1.0 / _fps)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f'[屏幕帧推送] 错误: {e}')
            await asyncio.sleep(0.5)


def _capture_screen():
    """截取屏幕图像。"""
    try:
        img = ImageGrab.grab()
        return img
    except Exception as e:
        logger.error(f'[截图] 失败: {e}')
        return None


def _get_screen_size():
    """获取屏幕尺寸。"""
    try:
        img = ImageGrab.grab()
        return {'width': img.width, 'height': img.height}
    except Exception as e:
        logger.error(f'[获取屏幕尺寸] 失败: {e}')
        return {'width': 1920, 'height': 1080}


def _encode_frame(img, quality):
    """将图像编码为 JPEG base64。"""
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    data = buf.getvalue()
    return base64.b64encode(data).decode('utf-8')


# 注册到 handlers 模块
HANDLER_MAP = {
    MsgType.SCREENSHOT: handle_screen_stream,
}