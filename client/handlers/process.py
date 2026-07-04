# -*- coding: utf-8 -*-
"""进程管理处理器：接收服务端进程指令，支持进程列表查询和进程终止。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

import psutil
from datetime import datetime


async def handle_process(engine, msg):
    """处理进程管理指令，支持 list 和 kill 两种 action。"""
    payload = msg.get('payload', {})
    action = payload.get('action', 'list')

    if action == 'list':
        sort_by = payload.get('sort', 'cpu')
        limit = min(payload.get('limit', 100), 500)
        procs = _get_process_list(sort_by, limit)
        resp = make_msg(MsgType.PROCESS, engine.client_id,
                        {'status': 'ok', 'processes': procs},
                        msg.get('seq', 0))
    elif action == 'kill':
        pid = payload.get('pid')
        result = _kill_process(pid)
        resp = make_msg(MsgType.PROCESS, engine.client_id,
                        result, msg.get('seq', 0))
    else:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Unknown action: {action}'},
                        msg.get('seq', 0))

    await engine.send_msg(resp)


def _get_process_list(sort_by='cpu', limit=50):
    """获取进程列表，按指定字段排序并限制返回数量。

    Args:
        sort_by: 排序字段，支持 cpu / memory / name / pid
        limit: 最大返回数量
    """
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'create_time']):
        try:
            info = proc.info
            info['cpu_percent'] = info['cpu_percent'] or 0.0
            info['memory_percent'] = info['memory_percent'] or 0.0
            info['create_time'] = datetime.fromtimestamp(info['create_time']).isoformat() if info['create_time'] else ''
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sort_by == 'cpu':
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
    elif sort_by == 'memory':
        procs.sort(key=lambda x: x['memory_percent'], reverse=True)
    elif sort_by == 'name':
        procs.sort(key=lambda x: x['name'].lower() if x['name'] else '')
    elif sort_by == 'pid':
        procs.sort(key=lambda x: x['pid'])

    return procs[:limit]


def _kill_process(pid):
    """终止指定 PID 的进程。

    Args:
        pid: 进程 ID

    Returns:
        包含操作结果的字典
    """
    try:
        p = psutil.Process(pid)
        p.terminate()
        return {'status': 'ok', 'action': 'kill', 'pid': pid, 'result': 'terminated'}
    except psutil.NoSuchProcess:
        return {'status': 'error', 'error': 'Process not found', 'pid': pid}
    except psutil.AccessDenied:
        return {'status': 'error', 'error': 'Access denied', 'pid': pid}
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'pid': pid}
