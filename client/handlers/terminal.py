# -*- coding: utf-8 -*-
"""终端处理器：使用 PTY（伪终端）管理 cmd/bash 进程，解决管道模式输出缓冲问题。

PTY 让 shell 认为自己在真实终端中运行，从而立即输出命令结果。
"""

import asyncio
import os
import sys
import platform
import threading
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.terminal')

# Windows 使用 pywinpty，Linux/macOS 使用 pty 标准库
if platform.system() == 'Windows':
    try:
        from winpty import PtyProcess
        HAS_PTY = True
    except ImportError:
        HAS_PTY = False
        logger.warning("未安装 pywinpty，终端功能受限")
else:
    import pty
    import fcntl
    import termios
    import struct
    HAS_PTY = True


class PersistentTerminal:
    """持久化终端实例，使用 PTY 管理本地 shell 进程。

    PTY 解决管道模式下 cmd.exe 不立即输出命令结果的缓冲问题。
    """

    def __init__(self, engine):
        self.engine = engine
        self._encoding = 'utf-8' if platform.system() != 'Windows' else 'utf-8'  # pywinpty 返回 UTF-8
        self.pty = None
        self._reader_thread = None
        self._start_terminal()
        self._start_reader()

    def _start_terminal(self):
        """根据操作系统启动 PTY。"""
        current_os = platform.system()
        
        if current_os == 'Windows':
            if not HAS_PTY:
                logger.error("Windows 需要 pywinpty 才能运行终端")
                return
            # Windows: 使用 pywinpty 创建 ConPTY
            # pywinpty 默认使用 UTF-8 编码
            self.pty = PtyProcess.spawn('cmd.exe')
            logger.info("[终端] PTY 已启动 (Windows ConPTY)")
        else:
            # Linux/macOS: 使用标准 pty 模块
            import pty
            import os
            import subprocess
            
            master_fd, slave_fd = pty.openpty()
            # 设置终端大小
            winsize = struct.pack('HHHH', 24, 80, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            
            # 启动 bash
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['LANG'] = 'en_US.UTF-8'
            env['LC_ALL'] = 'en_US.UTF-8'
            
            self.proc = subprocess.Popen(
                ['/bin/bash', '-i'],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                close_fds=True
            )
            os.close(slave_fd)
            self.pty = master_fd  # 保存 master_fd
            logger.info("[终端] PTY 已启动 (Linux/macOS)")

    def _start_reader(self):
        """后台线程持续读取 PTY 输出。"""
        def _read_loop():
            logger.info("[终端输出线程] 已启动")
            try:
                while self.pty:
                    try:
                        if platform.system() == 'Windows':
                            # pywinpty 的 read() 返回 str (UTF-8)
                            chunk = self.pty.read(1024)
                            if not chunk:
                                logger.info("[终端输出线程] PTY 返回空，退出循环")
                                break
                            text = chunk
                        else:
                            # Linux/macOS: 从 master_fd 读取字节
                            import os
                            import select
                            # 使用 select 检查是否有数据可读
                            rlist, _, _ = select.select([self.pty], [], [], 0.1)
                            if self.pty in rlist:
                                chunk = os.read(self.pty, 1024)
                                if not chunk:
                                    logger.info("[终端输出线程] PTY 返回空，退出循环")
                                    break
                                text = chunk.decode('utf-8', errors='replace')
                            else:
                                continue
                        
                        logger.info(f"[终端输出线程] 读取到输出: len={len(text)}, preview={repr(text[:50])}")
                        msg = make_msg(MsgType.TERMINAL_DATA, self.engine.client_id, {'data': text})
                        asyncio.run_coroutine_threadsafe(
                            self.engine.send_msg(msg), self.engine._loop)
                    except Exception as e:
                        logger.error(f"[终端输出线程] 读取异常: {e}")
                        break
            except Exception as e:
                logger.error(f"[终端输出线程] 线程异常: {e}")
            
            logger.info("[终端输出线程] 线程结束")
            # 发送退出消息
            try:
                msg = make_msg(MsgType.TERMINAL_DATA, self.engine.client_id,
                               {'data': '\r\n\x1b[33m[终端进程已退出]\x1b[0m\r\n'})
                asyncio.run_coroutine_threadsafe(
                    self.engine.send_msg(msg), self.engine._loop)
            except Exception as e:
                logger.error(f"[终端输出线程] 发送退出消息失败: {e}")

        self._reader_thread = threading.Thread(target=_read_loop, daemon=True)
        self._reader_thread.start()

    def write(self, data):
        """向 PTY 写入数据。"""
        try:
            if platform.system() == 'Windows':
                # pywinpty 的 write() 接收 str
                if isinstance(data, bytes):
                    data = data.decode('utf-8', errors='replace')
                self.pty.write(data)
            else:
                # Linux/macOS: 写入字节到 master_fd
                if isinstance(data, str):
                    data = data.encode('utf-8', errors='replace')
                os.write(self.pty, data)
        except Exception as e:
            logger.error(f"[终端写入] 异常: {e}")

    def kill(self):
        """关闭 PTY。"""
        try:
            if self.pty:
                if platform.system() == 'Windows':
                    self.pty.close()
                else:
                    os.close(self.pty)
                    if hasattr(self, 'proc'):
                        self.proc.kill()
                self.pty = None
        except Exception:
            pass


# 全局终端实例
_terminal = None


async def handle_terminal(engine, msg):
    """处理终端指令，支持 start、write、kill 和 close 四种 action。"""
    global _terminal
    payload = msg.get('payload', {})
    action = payload.get('action', 'write')
    
    logger.info(f"[终端处理] action={action}, payload={payload}")

    if action == 'start':
        # 启动终端（如果尚未启动）
        if _terminal is None or _terminal.pty is None:
            logger.info("[终端处理] 创建新终端实例")
            _terminal = PersistentTerminal(engine)
        else:
            logger.info("[终端处理] 终端已存在，跳过创建")

    elif action == 'write':
        # 如果终端未启动，则重新创建
        if _terminal is None or _terminal.pty is None:
            logger.info("[终端处理] 终端未启动，创建新实例")
            _terminal = PersistentTerminal(engine)
        data = payload.get('data', '')
        logger.info(f"[终端处理] 写入数据: {repr(data[:50])}")
        _terminal.write(data)

    elif action in ('kill', 'close'):
        if _terminal:
            _terminal.kill()
            _terminal = None
        resp = make_msg(MsgType.TERMINAL, engine.client_id,
                        {'status': 'ok', 'action': action},
                        msg.get('seq', 0))
        await engine.send_msg(resp)

    else:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Unknown action: {action}'},
                        msg.get('seq', 0))
        await engine.send_msg(resp)