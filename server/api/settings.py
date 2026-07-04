# -*- coding: utf-8 -*-
"""设置 API：读取和更新服务端配置。"""
import os
import json
import logging

from flask import Blueprint, jsonify, request

from common.config import (
    DEFAULT_HOST, DEFAULT_PORT, DEFAULT_WS_PORT, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT,
    SERVER_CONFIG_FILE,
)

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)

# 默认配置
_DEFAULT_SETTINGS = {
    'host': DEFAULT_HOST,
    'port': DEFAULT_PORT,
    'ws_port': DEFAULT_WS_PORT,
    'heartbeat_interval': HEARTBEAT_INTERVAL,
    'heartbeat_timeout': HEARTBEAT_TIMEOUT,
    'auth_key': '',
    'tls_enabled': False,
    'notification_enabled': True,
}


def _load_settings():
    """从配置文件加载设置，文件不存在时返回默认值。"""
    if not os.path.exists(SERVER_CONFIG_FILE):
        return dict(_DEFAULT_SETTINGS)
    try:
        with open(SERVER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        # 合并：以默认值为底，用文件值覆盖
        result = dict(_DEFAULT_SETTINGS)
        result.update(saved)
        return result
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return dict(_DEFAULT_SETTINGS)


def _save_settings(settings):
    """保存设置到配置文件。"""
    try:
        os.makedirs(os.path.dirname(SERVER_CONFIG_FILE), exist_ok=True)
        with open(SERVER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")


@settings_bp.route('/api/settings')
def api_get_settings():
    """获取当前服务端设置。"""
    settings = _load_settings()
    return jsonify(settings)


@settings_bp.route('/api/settings', methods=['POST'])
def api_update_settings():
    """更新服务端设置。

    请求体：要更新的设置键值对，仅覆盖提供的字段。
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': '请求体不能为空'}), 400

    current = _load_settings()

    # 只允许更新已知的配置键
    updatable_keys = set(_DEFAULT_SETTINGS.keys())
    for key in data:
        if key not in updatable_keys:
            return jsonify({'error': f'未知配置项: {key}'}), 400

    current.update(data)
    _save_settings(current)
    return jsonify({'ok': True, 'settings': current})
