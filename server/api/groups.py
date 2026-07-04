# -*- coding: utf-8 -*-
"""分组管理 API：分组列表查询、创建、重命名、删除。"""
from flask import Blueprint, jsonify, request

groups_bp = Blueprint('groups', __name__)


@groups_bp.route('/api/groups')
def api_groups():
    """获取所有分组名称列表。"""
    cm = groups_bp.app.client_manager
    groups = cm.get_groups()
    return jsonify(groups)


@groups_bp.route('/api/groups', methods=['POST'])
def api_group_create():
    """创建新分组。

    请求体：{"name": "分组名"}
    """
    cm = groups_bp.app.client_manager
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '分组名不能为空'}), 400
    ok = cm.create_group(name)
    if not ok:
        return jsonify({'error': '分组已存在'}), 409
    return jsonify({'ok': True}), 201


@groups_bp.route('/api/groups/<name>', methods=['PUT'])
def api_group_rename(name):
    """重命名分组。

    请求体：{"new_name": "新分组名"}
    """
    cm = groups_bp.app.client_manager
    data = request.get_json(silent=True) or {}
    new_name = data.get('new_name', '').strip()
    if not new_name:
        return jsonify({'error': '新分组名不能为空'}), 400
    ok = cm.rename_group(name, new_name)
    if not ok:
        return jsonify({'error': '重命名失败（原分组不存在或新名称已存在）'}), 400
    return jsonify({'ok': True})


@groups_bp.route('/api/groups/<name>', methods=['DELETE'])
def api_group_delete(name):
    """删除分组，同时清除该分组下设备的 group 字段。"""
    cm = groups_bp.app.client_manager
    ok = cm.delete_group(name)
    if not ok:
        return jsonify({'error': '分组不存在'}), 404
    return jsonify({'ok': True})
