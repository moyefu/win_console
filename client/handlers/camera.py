# -*- coding: utf-8 -*-
"""摄像头处理器：接收服务端摄像头指令，采集摄像头画面并推送帧数据。"""

import asyncio
import io
import base64
import sys
import os
import logging
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.camera')

# 模块级状态
_active_cap = None           # cv2.VideoCapture 实例
_active_index = -1           # 当前打开的摄像头索引
_push_task = None            # 帧推送异步任务
_push_fps = 10               # 推送帧率
_is_recording = False        # 是否正在录制
_video_writer = None         # cv2.VideoWriter 实例
_record_file = ''            # 录制文件路径
_frame_width = 640
_frame_height = 480


def _check_cv2():
    """懒加载检查 cv2 是否可用。"""
    try:
        import cv2
        return cv2
    except ImportError:
        return None


async def handle_camera(engine, msg):
    """处理摄像头指令。"""
    payload = msg.get('payload', {})
    action = payload.get('action', '')
    seq = msg.get('seq', 0)

    try:
        if action == 'list':
            await _handle_list(engine, seq)
        elif action == 'open':
            await _handle_open(engine, payload, seq)
        elif action == 'close':
            await _handle_close(engine, seq)
        elif action == 'capture':
            await _handle_capture(engine, seq)
        elif action == 'record_start':
            await _handle_record_start(engine, payload, seq)
        elif action == 'record_stop':
            await _handle_record_stop(engine, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': f'Unknown camera action: {action}'}, seq)
            await engine.send_msg(resp)
    except Exception as e:
        logger.error(f'Camera handler error: {e}')
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, seq)
        await engine.send_msg(resp)


async def _handle_list(engine, seq):
    """枚举可用摄像头（索引 0-9）。"""
    cv2 = _check_cv2()
    if cv2 is None:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error',
                         'error': 'opencv-python is not installed. Run: pip install opencv-python'},
                        seq)
        await engine.send_msg(resp)
        return

    cameras = []
    for idx in range(10):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            name = f'Camera {idx}'
            # 尝试获取后端名称
            try:
                backend = cap.getBackendName()
                if backend:
                    name = f'Camera {idx} ({backend})'
            except Exception:
                pass
            cameras.append({'index': idx, 'name': name})
            cap.release()

    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'list', 'cameras': cameras}, seq)
    await engine.send_msg(resp)


async def _handle_open(engine, payload, seq):
    """打开指定索引的摄像头，启动帧推送任务。"""
    global _active_cap, _active_index, _push_task, _push_fps
    global _frame_width, _frame_height

    cv2 = _check_cv2()
    if cv2 is None:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error',
                         'error': 'opencv-python is not installed. Run: pip install opencv-python'},
                        seq)
        await engine.send_msg(resp)
        return

    index = payload.get('index', 0)
    width = payload.get('width', 640)
    height = payload.get('height', 480)
    fps = payload.get('fps', 10)

    # 先关闭已打开的摄像头
    await _close_internal(engine)

    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        # 尝试判断失败原因
        error_msg = f'Cannot open camera at index {index}'
        # 再次尝试确认
        cap2 = cv2.VideoCapture(index)
        if not cap2.isOpened():
            error_msg = f'Camera index {index} not available (no device / permission denied / in use)'
        else:
            cap2.release()
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': error_msg}, seq)
        await engine.send_msg(resp)
        return

    # 设置分辨率
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # 读取实际分辨率
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    _active_cap = cap
    _active_index = index
    _push_fps = max(1, min(fps, 30))
    _frame_width = actual_w
    _frame_height = actual_h

    # 启动帧推送后台任务
    _push_task = asyncio.ensure_future(_frame_push_loop(engine))

    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'open',
                     'index': index, 'width': actual_w, 'height': actual_h, 'fps': _push_fps},
                    seq)
    await engine.send_msg(resp)


async def _handle_close(engine, seq):
    """关闭当前摄像头，停止帧推送。"""
    await _close_internal(engine)
    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'close'}, seq)
    await engine.send_msg(resp)


async def _close_internal(engine=None):
    """内部关闭逻辑，停止录制、释放摄像头、取消推送任务。"""
    global _active_cap, _active_index, _push_task
    global _is_recording, _video_writer, _record_file

    # 停止录制
    if _is_recording and _video_writer is not None:
        try:
            _video_writer.release()
        except Exception:
            pass
        _video_writer = None
        _is_recording = False
        _record_file = ''

    # 取消帧推送任务
    if _push_task is not None:
        _push_task.cancel()
        try:
            await _push_task
        except asyncio.CancelledError:
            pass
        _push_task = None

    # 释放摄像头
    if _active_cap is not None:
        try:
            _active_cap.release()
        except Exception:
            pass
        _active_cap = None
    _active_index = -1


async def _handle_capture(engine, seq):
    """截取当前帧，返回高质量 JPEG base64。"""
    cv2 = _check_cv2()
    if cv2 is None:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error',
                         'error': 'opencv-python is not installed. Run: pip install opencv-python'},
                        seq)
        await engine.send_msg(resp)
        return

    if _active_cap is None or not _active_cap.isOpened():
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'No camera is open'}, seq)
        await engine.send_msg(resp)
        return

    ret, frame = _active_cap.read()
    if not ret or frame is None:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'Failed to capture frame'}, seq)
        await engine.send_msg(resp)
        return

    # 高质量 JPEG 编码
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
    ok, buf = cv2.imencode('.jpg', frame, encode_params)
    if not ok:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'Failed to encode frame'}, seq)
        await engine.send_msg(resp)
        return

    data_b64 = base64.b64encode(buf.tobytes()).decode('ascii')
    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'capture', 'data_b64': data_b64}, seq)
    await engine.send_msg(resp)


async def _handle_record_start(engine, payload, seq):
    """开始录制到临时文件。"""
    global _is_recording, _video_writer, _record_file

    cv2 = _check_cv2()
    if cv2 is None:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error',
                         'error': 'opencv-python is not installed. Run: pip install opencv-python'},
                        seq)
        await engine.send_msg(resp)
        return

    if _active_cap is None or not _active_cap.isOpened():
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'No camera is open'}, seq)
        await engine.send_msg(resp)
        return

    if _is_recording:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'Already recording'}, seq)
        await engine.send_msg(resp)
        return

    # 获取帧率
    fps = payload.get('fps', _push_fps)
    fps = max(1, min(fps, 30))

    # 创建临时文件
    fd, path = tempfile.mkstemp(suffix='.avi', prefix='camera_rec_')
    os.close(fd)

    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(path, fourcc, fps, (_frame_width, _frame_height))

    if not writer.isOpened():
        os.remove(path)
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'Failed to create video writer'}, seq)
        await engine.send_msg(resp)
        return

    _video_writer = writer
    _record_file = path
    _is_recording = True

    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'record_start',
                     'file': path, 'fps': fps}, seq)
    await engine.send_msg(resp)


async def _handle_record_stop(engine, seq):
    """停止录制，返回文件路径供下载。"""
    global _is_recording, _video_writer, _record_file

    if not _is_recording:
        resp = make_msg(MsgType.CAMERA, engine.client_id,
                        {'status': 'error', 'error': 'Not recording'}, seq)
        await engine.send_msg(resp)
        return

    file_path = _record_file

    if _video_writer is not None:
        try:
            _video_writer.release()
        except Exception:
            pass
        _video_writer = None

    _is_recording = False
    _record_file = ''

    # 检查文件是否存在
    file_size = 0
    if os.path.isfile(file_path):
        file_size = os.path.getsize(file_path)

    resp = make_msg(MsgType.CAMERA, engine.client_id,
                    {'status': 'ok', 'action': 'record_stop',
                     'file': file_path, 'size': file_size}, seq)
    await engine.send_msg(resp)


async def _frame_push_loop(engine):
    """帧推送协程：持续读取帧，JPEG 编码后以 CAMERA_DATA 消息推送。"""
    global _is_recording, _video_writer

    cv2 = _check_cv2()
    if cv2 is None:
        return

    interval = 1.0 / _push_fps

    while True:
        try:
            if _active_cap is None or not _active_cap.isOpened():
                break

            ret, frame = _active_cap.read()
            if not ret or frame is None:
                await asyncio.sleep(interval)
                continue

            # 录制写入
            if _is_recording and _video_writer is not None:
                try:
                    _video_writer.write(frame)
                except Exception:
                    pass

            # JPEG 编码
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 70]
            ok, buf = cv2.imencode('.jpg', frame, encode_params)
            if ok:
                data_b64 = base64.b64encode(buf.tobytes()).decode('ascii')
                msg = make_msg(MsgType.CAMERA_DATA, engine.client_id,
                               {'index': _active_index,
                                'width': _frame_width,
                                'height': _frame_height,
                                'data_b64': data_b64})
                try:
                    await engine.send_msg(msg)
                except Exception:
                    pass

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f'Frame push error: {e}')
            await asyncio.sleep(interval)
