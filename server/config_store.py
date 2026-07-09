# -*- coding: utf-8 -*-
"""服务端配置读写。

集中管理服务端设置，避免入口、API、认证和客户端注册校验各读各的。
"""

import json
import logging
import os
import secrets
from copy import deepcopy

from common.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_WS_PORT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    SERVER_CONFIG_FILE,
)

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    'host': DEFAULT_HOST,
    'port': DEFAULT_PORT,
    'ws_port': DEFAULT_WS_PORT,
    'heartbeat_interval': HEARTBEAT_INTERVAL,
    'heartbeat_timeout': HEARTBEAT_TIMEOUT,
    'auth_key': '',
    'tls_enabled': False,
    'notification_enabled': True,
    'admin_password_hash': '',
    'session_secret': '',
}

PUBLIC_SECRET_FIELDS = {
    'admin_password_hash',
    'session_secret',
}


def _with_generated_secrets(settings):
    """补齐运行必需的随机密钥，返回 (settings, changed)。"""
    changed = False
    result = deepcopy(settings)

    if not result.get('auth_key'):
        result['auth_key'] = secrets.token_urlsafe(32)
        changed = True

    if not result.get('session_secret'):
        result['session_secret'] = secrets.token_urlsafe(32)
        changed = True

    return result, changed


def load_settings(create=True):
    """读取服务端设置。

    Args:
        create: 为 True 时会自动创建配置文件并补齐随机密钥。
    """
    settings = deepcopy(DEFAULT_SETTINGS)
    changed = False

    if os.path.exists(SERVER_CONFIG_FILE):
        try:
            with open(SERVER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception as e:
            logger.error("加载配置文件失败: %s", e)
    else:
        changed = True

    settings, generated = _with_generated_secrets(settings)
    changed = changed or generated

    if create and changed:
        save_settings(settings)

    return settings


def save_settings(settings):
    """保存服务端设置到磁盘。"""
    try:
        os.makedirs(os.path.dirname(SERVER_CONFIG_FILE), exist_ok=True)
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(settings)
        with open(SERVER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("保存配置文件失败: %s", e)


def public_settings():
    """返回可给已登录 Web 管理员查看的设置。"""
    settings = load_settings(create=True)
    for field in PUBLIC_SECRET_FIELDS:
        settings.pop(field, None)
    settings['admin_password_set'] = bool(load_settings(create=True).get('admin_password_hash'))
    return settings
