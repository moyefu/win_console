# -*- coding: utf-8 -*-
"""仪表盘 API：提供系统概览统计和最近警报。"""
from flask import Blueprint, jsonify

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/dashboard')
def api_dashboard():
    """获取仪表盘统计数据和最近警报。"""
    cm = dashboard_bp.app.client_manager
    stats = cm.get_dashboard_stats()
    alerts = cm.get_alerts(limit=20)
    return jsonify({
        'stats': stats,
        'alerts': alerts
    })
