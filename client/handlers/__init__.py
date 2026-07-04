# -*- coding: utf-8 -*-
"""客户端功能模块处理器包，导出所有 handler 函数。"""

from .screenshot import handle_screenshot
from .process import handle_process
from .terminal import handle_terminal
from .mouse import handle_mouse
from .keyboard import handle_keyboard
from .keylog import handle_keylog
from .system_info import handle_system_info

__all__ = ['handle_screenshot', 'handle_process', 'handle_terminal',
           'handle_mouse', 'handle_keyboard', 'handle_keylog', 'handle_system_info']
