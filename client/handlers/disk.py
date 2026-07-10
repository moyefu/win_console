# -*- coding: utf-8 -*-
"""硬盘监控处理器：接收服务端硬盘信息请求，返回磁盘分区和IO统计数据。"""

import asyncio
import sys
import os
import logging
import time

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.disk')


async def handle_disk(engine, msg):
    """处理硬盘信息请求。"""
    payload = msg.get('payload', {})
    action = payload.get('action', 'list')
    seq = msg.get('seq', 0)

    try:
        if action == 'list':
            await _handle_list(engine, seq)
        elif action == 'io_stats':
            await _handle_io_stats(engine, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': f'Unknown disk action: {action}'}, seq)
            await engine.send_msg(resp)
    except Exception as e:
        logger.error(f'Disk handler error: {e}')
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': str(e)}, seq)
        await engine.send_msg(resp)


async def _handle_list(engine, seq):
    """返回磁盘分区信息及各分区使用量。"""
    loop = asyncio.get_event_loop()

    def _collect():
        partitions = psutil.disk_partitions()
        result = []
        for part in partitions:
            info = {
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype,
                'opts': part.opts,
            }
            try:
                usage = psutil.disk_usage(part.mountpoint)
                info['total'] = usage.total
                info['used'] = usage.used
                info['free'] = usage.free
                info['percent'] = usage.percent
            except (PermissionError, OSError):
                # Windows 下 CD-ROM 等不可访问的分区会抛异常，跳过 usage 字段
                info['total'] = 0
                info['used'] = 0
                info['free'] = 0
                info['percent'] = 0.0
            result.append(info)
        return result

    partitions = await loop.run_in_executor(None, _collect)
    resp = make_msg(MsgType.DISK, engine.client_id,
                    {'action': 'list', 'partitions': partitions}, seq)
    await engine.send_msg(resp)


async def _handle_io_stats(engine, seq):
    """返回磁盘IO统计及两次采样间的读写速度。"""
    loop = asyncio.get_event_loop()

    def _sample():
        counters = psutil.disk_io_counters(perdisk=True)
        stats = {}
        for name, c in counters.items():
            stats[name] = {
                'read_count': c.read_count,
                'write_count': c.write_count,
                'read_bytes': c.read_bytes,
                'write_bytes': c.write_bytes,
                'read_time': c.read_time,
                'write_time': c.write_time,
            }
        return stats

    # 第一次采样
    sample1 = await loop.run_in_executor(None, _sample)
    t1 = time.monotonic()

    # 等待1秒
    await asyncio.sleep(1.0)

    # 第二次采样
    sample2 = await loop.run_in_executor(None, _sample)
    t2 = time.monotonic()
    elapsed = t2 - t1

    # 计算读写速度
    speeds = {}
    for name in sample2:
        if name in sample1:
            s1 = sample1[name]
            s2 = sample2[name]
            speeds[name] = {
                'read_bytes_per_sec': (s2['read_bytes'] - s1['read_bytes']) / elapsed,
                'write_bytes_per_sec': (s2['write_bytes'] - s1['write_bytes']) / elapsed,
            }

    resp = make_msg(MsgType.DISK, engine.client_id, {
        'action': 'io_stats',
        'io_stats': sample2,
        'speeds': speeds,
        'interval': round(elapsed, 2),
    }, seq)
    await engine.send_msg(resp)
