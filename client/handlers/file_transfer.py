# -*- coding: utf-8 -*-
"""文件传输处理器：处理客户端与服务端之间的文件上传和下载。"""

import asyncio
import base64
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.file_transfer')

CHUNK_SIZE = 1 * 1024 * 1024  # 1MB 每块

# 活动上传传输: transfer_id → {file, file_path, bytes_received, total_bytes}
_active_uploads = {}
# 活动下载传输: transfer_id → {file_path, total_bytes, bytes_sent}
_active_downloads = {}


async def handle_file_transfer(engine, msg):
    """处理文件传输控制指令。"""
    payload = msg.get('payload', {})
    action = payload.get('action', '')
    seq = msg.get('seq', 0)

    try:
        if action == 'upload':
            await _handle_upload(engine, msg, payload, seq)
        elif action == 'download':
            await _handle_download(engine, msg, payload, seq)
        elif action == 'cancel':
            await _handle_cancel(engine, msg, payload, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': f'Unknown file_transfer action: {action}'}, seq)
            await engine.send_msg(resp)
    except Exception as e:
        logger.error("文件传输处理异常: %s", e)
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, seq)
        await engine.send_msg(resp)


async def handle_file_transfer_data(engine, msg):
    """处理文件传输二进制数据块。"""
    payload = msg.get('payload', {})
    seq = msg.get('seq', 0)

    try:
        transfer_id = payload.get('transfer_id')
        if not transfer_id or transfer_id not in _active_uploads:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': f'Invalid transfer_id: {transfer_id}'}, seq)
            await engine.send_msg(resp)
            return

        upload = _active_uploads[transfer_id]
        chunk_index = payload.get('chunk_index', 0)
        data_b64 = payload.get('data_b64', '')
        is_last = payload.get('is_last', False)

        # 解码并写入文件
        raw = base64.b64decode(data_b64)
        upload['file'].write(raw)
        upload['bytes_received'] += len(raw)

        logger.info("上传数据块: transfer_id=%s, chunk=%d, size=%d, is_last=%s",
                     transfer_id, chunk_index, len(raw), is_last)

        if is_last:
            # 最后一块，关闭文件并发送完成消息
            upload['file'].close()
            file_path = upload['file_path']
            total_bytes = upload['bytes_received']
            del _active_uploads[transfer_id]

            resp = make_msg(MsgType.FILE_TRANSFER, engine.client_id,
                            {'action': 'upload_complete',
                             'transfer_id': transfer_id,
                             'file_path': file_path,
                             'total_bytes': total_bytes}, seq)
            await engine.send_msg(resp)
            logger.info("上传完成: transfer_id=%s, file_path=%s, total=%d",
                        transfer_id, file_path, total_bytes)
        else:
            # 发送进度
            resp = make_msg(MsgType.FILE_TRANSFER, engine.client_id,
                            {'action': 'upload_progress',
                             'transfer_id': transfer_id,
                             'bytes_received': upload['bytes_received'],
                             'total_bytes': upload['total_bytes']}, seq)
            await engine.send_msg(resp)

    except Exception as e:
        logger.error("处理上传数据块异常: %s", e)
        # 清理失败的传输
        transfer_id = payload.get('transfer_id')
        if transfer_id and transfer_id in _active_uploads:
            upload = _active_uploads.pop(transfer_id)
            try:
                upload['file'].close()
            except Exception:
                pass
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, seq)
        await engine.send_msg(resp)


async def _handle_upload(engine, msg, payload, seq):
    """处理上传指令：服务端发送文件到客户端。"""
    transfer_id = payload.get('transfer_id')
    file_path = payload.get('file_path')
    file_size = payload.get('file_size', 0)
    offset = payload.get('offset', 0)

    if not transfer_id or not file_path:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': 'Missing transfer_id or file_path'}, seq)
        await engine.send_msg(resp)
        return

    # 确保目标目录存在
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    except OSError as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Cannot create directory: {e}'}, seq)
        await engine.send_msg(resp)
        return

    try:
        # 断点续传：offset > 0 时追加写入
        mode = 'ab' if offset > 0 else 'wb'
        f = open(file_path, mode)
    except PermissionError:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Permission denied: {file_path}'}, seq)
        await engine.send_msg(resp)
        return
    except OSError as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Cannot open file: {e}'}, seq)
        await engine.send_msg(resp)
        return

    # 如果是追加模式，先 seek 到 offset 位置
    if offset > 0:
        f.seek(offset)

    _active_uploads[transfer_id] = {
        'file': f,
        'file_path': file_path,
        'bytes_received': offset,
        'total_bytes': file_size,
    }

    logger.info("开始上传接收: transfer_id=%s, file_path=%s, size=%d, offset=%d",
                transfer_id, file_path, file_size, offset)


async def _handle_download(engine, msg, payload, seq):
    """处理下载指令：客户端发送文件到服务端。"""
    transfer_id = payload.get('transfer_id')
    file_path = payload.get('file_path')
    offset = payload.get('offset', 0)

    if not transfer_id or not file_path:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': 'Missing transfer_id or file_path'}, seq)
        await engine.send_msg(resp)
        return

    if not os.path.isfile(file_path):
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'File not found: {file_path}'}, seq)
        await engine.send_msg(resp)
        return

    try:
        total_bytes = os.path.getsize(file_path)
        f = open(file_path, 'rb')
    except PermissionError:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Permission denied: {file_path}'}, seq)
        await engine.send_msg(resp)
        return
    except OSError as e:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Cannot open file: {e}'}, seq)
        await engine.send_msg(resp)
        return

    # 断点续传：跳过已发送部分
    if offset > 0:
        f.seek(offset)

    _active_downloads[transfer_id] = {
        'file': f,
        'file_path': file_path,
        'total_bytes': total_bytes,
        'bytes_sent': offset,
    }

    logger.info("开始下载发送: transfer_id=%s, file_path=%s, total=%d, offset=%d",
                transfer_id, file_path, total_bytes, offset)

    # 启动异步任务逐块发送
    asyncio.create_task(_send_download_chunks(engine, transfer_id))


async def _send_download_chunks(engine, transfer_id):
    """逐块读取文件并发送到服务端。"""
    try:
        upload = _active_downloads.get(transfer_id)
        if not upload:
            return

        f = upload['file']
        file_path = upload['file_path']
        total_bytes = upload['total_bytes']
        chunk_index = 0

        while True:
            # 检查传输是否仍活跃（可能已被取消）
            if transfer_id not in _active_downloads:
                logger.info("下载传输已取消: transfer_id=%s", transfer_id)
                return

            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            is_last = (f.tell() >= total_bytes)
            data_b64 = base64.b64encode(chunk).decode('ascii')
            bytes_sent = f.tell()

            data_msg = make_msg(
                MsgType.FILE_TRANSFER_DATA, engine.client_id,
                {'transfer_id': transfer_id,
                 'chunk_index': chunk_index,
                 'data_b64': data_b64,
                 'is_last': is_last,
                 'bytes_sent': bytes_sent,
                 'total_bytes': total_bytes}
            )
            await engine.send_msg(data_msg)

            upload['bytes_sent'] = bytes_sent
            chunk_index += 1

            # 让出控制权，避免阻塞事件循环
            await asyncio.sleep(0)

        # 发送下载完成消息
        complete_msg = make_msg(
            MsgType.FILE_TRANSFER, engine.client_id,
            {'action': 'download_complete',
             'transfer_id': transfer_id,
             'file_path': file_path,
             'total_bytes': total_bytes}
        )
        await engine.send_msg(complete_msg)

        # 清理
        f.close()
        _active_downloads.pop(transfer_id, None)

        logger.info("下载发送完成: transfer_id=%s, file_path=%s, total=%d",
                    transfer_id, file_path, total_bytes)

    except Exception as e:
        logger.error("下载发送异常: transfer_id=%s, error=%s", transfer_id, e)
        # 清理
        upload = _active_downloads.pop(transfer_id, None)
        if upload:
            try:
                upload['file'].close()
            except Exception:
                pass
        # 发送错误
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Download failed: {e}'})
        await engine.send_msg(resp)


async def _handle_cancel(engine, msg, payload, seq):
    """处理取消传输指令。"""
    transfer_id = payload.get('transfer_id')

    if not transfer_id:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': 'Missing transfer_id'}, seq)
        await engine.send_msg(resp)
        return

    cancelled = False

    # 取消上传传输
    if transfer_id in _active_uploads:
        upload = _active_uploads.pop(transfer_id)
        try:
            upload['file'].close()
        except Exception:
            pass
        # 删除部分文件
        try:
            if os.path.isfile(upload['file_path']):
                os.remove(upload['file_path'])
                logger.info("已删除部分上传文件: %s", upload['file_path'])
        except Exception as e:
            logger.warning("删除部分文件失败: %s, error=%s", upload['file_path'], e)
        cancelled = True

    # 取消下载传输
    if transfer_id in _active_downloads:
        download = _active_downloads.pop(transfer_id)
        try:
            download['file'].close()
        except Exception:
            pass
        cancelled = True

    if not cancelled:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Invalid transfer_id: {transfer_id}'}, seq)
        await engine.send_msg(resp)
        return

    resp = make_msg(MsgType.FILE_TRANSFER, engine.client_id,
                    {'action': 'cancel_complete',
                     'transfer_id': transfer_id}, seq)
    await engine.send_msg(resp)
    logger.info("已取消传输: transfer_id=%s", transfer_id)
