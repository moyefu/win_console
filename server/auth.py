# -*- coding: utf-8 -*-
"""Web 管理端认证。

提供首次本机初始化、登录、登出，以及 Flask 请求保护。
"""

from functools import wraps

from flask import (
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from server.config_store import load_settings, save_settings

SESSION_KEY = 'winconsole_admin'

LOGIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WinConsole 登录</title>
<style>
body{margin:0;height:100vh;display:grid;place-items:center;background:#1a1b26;color:#c0caf5;font-family:'Microsoft YaHei','Segoe UI',system-ui,sans-serif}
.box{width:min(360px,calc(100vw - 32px));background:#16171e;border:1px solid #2f3044;border-radius:8px;padding:24px}
h1{margin:0 0 6px;color:#7aa2f7;font-size:22px}
p{margin:0 0 18px;color:#565f89;font-size:13px}
label{display:block;color:#9aa5ce;font-size:13px;margin-bottom:6px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #2f3044;border-radius:4px;background:#1f2130;color:#c0caf5;font-size:14px}
button{width:100%;margin-top:16px;padding:10px 14px;border:0;border-radius:4px;background:#7aa2f7;color:#1a1b26;font-weight:700;cursor:pointer}
.err{margin:0 0 14px;padding:9px 10px;border:1px solid #4a2d2d;border-radius:4px;background:#2e1e1e;color:#f7768e;font-size:13px}
</style>
</head>
<body>
<form class="box" method="post">
  <h1>WinConsole</h1>
  <p>{{ subtitle }}</p>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  {% if setup %}
  <label>设置管理员密码</label>
  {% else %}
  <label>管理员密码</label>
  {% endif %}
  <input name="password" type="password" minlength="8" autocomplete="current-password" autofocus required>
  {% if setup %}
  <button type="submit">完成初始化</button>
  {% else %}
  <button type="submit">登录</button>
  {% endif %}
</form>
</body>
</html>"""


def setup_required():
    """是否还没有设置管理员密码。"""
    return not bool(load_settings(create=True).get('admin_password_hash'))


def is_authenticated():
    """当前请求是否已通过 Web 管理员认证。"""
    return bool(session.get(SESSION_KEY))


def _is_local_request():
    remote = request.remote_addr or ''
    return (
        remote == '::1' or
        remote == 'localhost' or
        remote.startswith('127.')
    )


def _auth_response(status=401, message='未登录'):
    if request.path.startswith('/api/'):
        return jsonify({'error': message, 'code': 'AUTH_REQUIRED'}), status
    return redirect(url_for('login', next=request.full_path or request.path))


def _forbidden_response(message):
    if request.path.startswith('/api/'):
        return jsonify({'error': message, 'code': 'FORBIDDEN'}), 403
    return message, 403


def require_ws_auth(ws):
    """校验 WebSocket 请求的 session；失败时关闭连接。"""
    if setup_required() or not is_authenticated():
        try:
            ws.close()
        except Exception:
            pass
        return False
    return True


def require_admin(view_func):
    """装饰器形式的 Web/API 管理员保护。"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if setup_required():
            return _auth_response(403, '请先在服务端本机完成初始化')
        if not is_authenticated():
            return _auth_response()
        return view_func(*args, **kwargs)
    return wrapper


def register_auth(app):
    """为 Flask app 注册登录、初始化和全局访问保护。"""
    settings = load_settings(create=True)
    app.secret_key = settings.get('session_secret')
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
    )

    @app.before_request
    def _protect_requests():
        allowed_paths = {'/login', '/setup', '/logout', '/favicon.ico'}
        if request.path in allowed_paths:
            return None

        if setup_required():
            if not _is_local_request():
                return _forbidden_response('请先在服务端本机完成初始化')
            if request.path.startswith('/api/'):
                return jsonify({'error': '请先完成初始化', 'code': 'SETUP_REQUIRED'}), 403
            return redirect(url_for('setup'))

        if not is_authenticated():
            return _auth_response()
        return None

    @app.route('/setup', methods=['GET', 'POST'])
    def setup():
        if not setup_required():
            return redirect(url_for('login'))
        if not _is_local_request():
            return _forbidden_response('首次初始化只允许从服务端本机访问')

        error = ''
        if request.method == 'POST':
            password = request.form.get('password', '')
            if len(password) < 8:
                error = '密码至少需要 8 位'
            else:
                settings = load_settings(create=True)
                settings['admin_password_hash'] = generate_password_hash(password)
                save_settings(settings)
                session.clear()
                session[SESSION_KEY] = True
                return redirect(url_for('index'))

        return render_template_string(
            LOGIN_HTML,
            setup=True,
            error=error,
            subtitle='首次使用，请在服务端本机设置管理员密码。',
        )

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if setup_required():
            return redirect(url_for('setup'))

        error = ''
        if request.method == 'POST':
            password = request.form.get('password', '')
            password_hash = load_settings(create=True).get('admin_password_hash', '')
            if password_hash and check_password_hash(password_hash, password):
                session.clear()
                session[SESSION_KEY] = True
                next_url = request.args.get('next') or url_for('index')
                return redirect(next_url)
            error = '密码不正确'

        return render_template_string(
            LOGIN_HTML,
            setup=False,
            error=error,
            subtitle='请输入管理员密码。',
        )

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
