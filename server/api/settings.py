# -*- coding: utf-8 -*-
"""设置 API：读取和更新服务端配置。"""
import logging

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from server.config_store import DEFAULT_SETTINGS, load_settings, public_settings, save_settings

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/api/settings')
def api_get_settings():
    """获取当前服务端设置。"""
    return jsonify(public_settings())


@settings_bp.route('/api/settings', methods=['POST'])
def api_update_settings():
    """更新服务端设置。

    请求体：要更新的设置键值对，仅覆盖提供的字段。
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': '请求体不能为空'}), 400

    current = load_settings(create=True)

    # 只允许更新已知的配置键
    updatable_keys = set(DEFAULT_SETTINGS.keys()) - {'admin_password_hash', 'session_secret'}
    updatable_keys.add('admin_password')

    for key in data:
        if key not in updatable_keys:
            return jsonify({'error': f'未知配置项: {key}'}), 400

    admin_password = data.pop('admin_password', '')
    if admin_password:
        if len(admin_password) < 8:
            return jsonify({'error': '管理员密码至少需要 8 位'}), 400
        current['admin_password_hash'] = generate_password_hash(admin_password)

    current.update(data)
    save_settings(current)
    return jsonify({'ok': True, 'settings': public_settings()})
