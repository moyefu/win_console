# -*- coding: utf-8 -*-
"""系统信息处理器：获取 CPU、内存使用率等系统资源信息。"""

import psutil
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.system_info')


async def handle_system_info(engine, msg):
    """处理系统信息请求，返回 CPU 和内存使用率。"""
    payload = msg.get('payload', {})
    action = payload.get('action', 'get')
    
    if action == 'get':
        # 获取 CPU 使用率（非阻塞，interval=None 返回自上次调用以来的值）
        # 首次调用返回0.0，后续调用返回实际值
        cpu_percent = psutil.cpu_percent(interval=None)
        # 如果是首次调用（返回0.0），快速采样一次
        if cpu_percent == 0.0:
            cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # 获取内存使用率（不阻塞）
        mem_info = psutil.virtual_memory()
        mem_percent = mem_info.percent
        
        logger.info(f"[系统信息] CPU={cpu_percent}%, 内存={mem_percent}%")
        
        resp = make_msg(MsgType.SYSTEM_INFO, engine.client_id, {
            'cpu_percent': cpu_percent,
            'mem_percent': mem_percent,
            'mem_total': mem_info.total,
            'mem_used': mem_info.used,
            'mem_available': mem_info.available,
        }, msg.get('seq', 0))
        await engine.send_msg(resp)
    else:
        resp = make_msg(MsgType.ERROR, engine.client_id, {
            'error': f'Unknown action: {action}'
        }, msg.get('seq', 0))
        await engine.send_msg(resp)