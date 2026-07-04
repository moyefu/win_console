# -*- coding: utf-8 -*-
"""设备管理 API：设备列表查询、详情获取、删除、分组设置。"""
from flask import Blueprint, jsonify, request

devices_bp = Blueprint('devices', __name__)


@devices_bp.route('/api/devices')
def api_devices():
    """获取设备列表，支持按状态、分组、关键词筛选。

    查询参数：
        status: online / offline，可选
        group: 分组名称，可选
        search: 搜索 hostname 或 ip，可选
    """
    cm = devices_bp.app.client_manager
    status = request.args.get('status')
    group = request.args.get('group')
    search = request.args.get('search')
    devices = cm.get_device_list(status=status, group=group, search=search)
    return jsonify(devices)


@devices_bp.route('/api/devices/<client_id>')
def api_device_detail(client_id):
    """获取设备详情。"""
    cm = devices_bp.app.client_manager
    device = cm.get_device(client_id)
    if not device:
        return jsonify({'error': '设备不存在'}), 404
    return jsonify({
        'client_id': device.client_id,
        'hostname': device.hostname,
        'ip': device.ip,
        'os_name': device.os_name,
        'os_version': device.os_version,
        'arch': device.arch,
        'group': device.group,
        'remark': device.remark,
        'online': device.online,
        'last_online_at': device.last_online_at,
        'connected_at': device.connected_at,
        'connection_history': device.connection_history,
    })


@devices_bp.route('/api/devices/<client_id>', methods=['DELETE'])
def api_device_delete(client_id):
    """删除设备记录。"""
    cm = devices_bp.app.client_manager
    ok = cm.delete_device(client_id)
    if not ok:
        return jsonify({'error': '设备不存在'}), 404
    return jsonify({'ok': True})


@devices_bp.route('/api/devices/<client_id>/group', methods=['POST'])
def api_device_set_group(client_id):
    """设置设备分组。

    请求体：{"group": "分组名"}
    """
    cm = devices_bp.app.client_manager
    data = request.get_json(silent=True) or {}
    group = data.get('group', '')
    ok = cm.set_device_group(client_id, group)
    if not ok:
        return jsonify({'error': '设备不存在'}), 404
    return jsonify({'ok': True})


@devices_bp.route('/api/devices/<client_id>/remark', methods=['POST'])
def api_device_set_remark(client_id):
    """设置设备备注。

    请求体：{"remark": "备注内容"}
    """
    cm = devices_bp.app.client_manager
    data = request.get_json(silent=True) or {}
    remark = data.get('remark', '')
    ok = cm.set_device_remark(client_id, remark)
    if not ok:
        return jsonify({'error': '设备不存在'}), 404
    return jsonify({'ok': True})
