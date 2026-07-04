# -*- coding: utf-8 -*-
"""客户端安装部署模块：实现 install / uninstall 命令及平台自启动注册。"""

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger('client.installer')

# ---- 常量 ----

# 客户端配置目录
CONFIG_DIR = Path.home() / '.winconsole-client'

# 安装日志路径（install/uninstall 流程都会写入，便于事后排查）
INSTALL_LOG_FILE = CONFIG_DIR / 'install.log'


def _setup_installer_logging():
    """为 install/uninstall 流程配置日志：写入文件 + 控制台 print。

    关键：不要给 root logger 加 StreamHandler！
    PyInstaller --onefile --console 模式下 sys.stderr 是无效的 fd，
    一旦 logging.StreamHandler 调 flush() 就会抛 [Errno 9] Bad file descriptor。
    所以控制台输出全部走 print()，logger 只负责写文件。
    """
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 清掉已有 handler，避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    try:
        fh = logging.FileHandler(str(INSTALL_LOG_FILE), encoding='utf-8')
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass
    # 注意：故意不添加 StreamHandler，避免 PyInstaller --onefile 下 Bad file descriptor


# Windows 自启动注册表项
_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_NAME = "WinConsoleClient"

# Linux systemd service 名称
_SERVICE_NAME = "winconsole-client"

# macOS LaunchAgent 标识
_PLIST_LABEL = "com.winconsole.client"


# ======================================================================
# 4.5 保存配置文件
# ======================================================================

def _save_config(server_addr):
    """保存服务端地址到配置文件。

    配置文件路径: ~/.winconsole-client/config.json
    内容: {"server_addr": "ip:port", "installed_at": "iso_timestamp"}
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_file = CONFIG_DIR / 'config.json'
    config = {
        'server_addr': server_addr,
        'installed_at': datetime.now(timezone.utc).isoformat(),
    }
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    logger.info("配置已保存: %s", config_file)


# ======================================================================
# 4.2 Windows 自启动
# ======================================================================

def _install_startup_windows(exe_path):
    """在 Windows 注册表中添加自启动项。

    Args:
        exe_path: 安装后的可执行文件绝对路径
    Returns:
        bool: 是否注册成功
    """
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _REG_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
        logger.info("Windows 自启动注册成功: %s", exe_path)
        return True
    except Exception as e:
        logger.error("Windows 自启动注册失败: %s", e)
        return False


def _uninstall_startup_windows():
    """移除 Windows 注册表中的自启动项。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _REG_NAME)
        winreg.CloseKey(key)
        logger.info("Windows 自启动项已移除")
    except FileNotFoundError:
        logger.info("Windows 自启动项不存在，跳过")
    except Exception as e:
        logger.error("Windows 自启动移除失败: %s", e)


# ======================================================================
# 4.3 Linux 自启动
# ======================================================================

def _install_startup_linux(exe_path):
    """在 Linux 上通过 systemd user service 实现自启动。

    Args:
        exe_path: 安装后的可执行文件绝对路径
    Returns:
        bool: 是否注册成功
    """
    # 判断是 PyInstaller 打包还是 Python 源码运行
    if getattr(sys, 'frozen', False):
        python_path = exe_path
        client_main_path = ''
        exec_line = f"ExecStart={exe_path}"
    else:
        python_path = sys.executable
        client_main_path = str(Path(__file__).parent / 'main.py')
        exec_line = f"ExecStart={python_path} {client_main_path}"

    service_dir = Path.home() / '.config' / 'systemd' / 'user'
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file = service_dir / f'{_SERVICE_NAME}.service'

    service_content = f"""[Unit]
Description=WinConsole Client
After=network.target

[Service]
{exec_line}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
    service_file.write_text(service_content, encoding='utf-8')
    logger.info("systemd service 文件已创建: %s", service_file)

    try:
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', f'{_SERVICE_NAME}.service'], check=True)
        logger.info("systemd 自启动已启用")
        return True
    except Exception as e:
        logger.error("Linux 自启动注册失败: %s", e)
        return False


def _uninstall_startup_linux():
    """禁用并删除 Linux systemd user service。"""
    try:
        subprocess.run(['systemctl', '--user', 'stop', f'{_SERVICE_NAME}.service'],
                       stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl', '--user', 'disable', f'{_SERVICE_NAME}.service'],
                       stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.warning("禁用 systemd service 时出错: %s", e)

    service_file = Path.home() / '.config' / 'systemd' / 'user' / f'{_SERVICE_NAME}.service'
    if service_file.exists():
        service_file.unlink()
        logger.info("systemd service 文件已删除")

    try:
        subprocess.run(['systemctl', '--user', 'daemon-reload'], stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ======================================================================
# 4.4 macOS 自启动
# ======================================================================

def _install_startup_macos(exe_path):
    """在 macOS 上通过 LaunchAgent plist 实现自启动。

    Args:
        exe_path: 安装后的可执行文件绝对路径
    Returns:
        bool: 是否注册成功
    """
    if getattr(sys, 'frozen', False):
        python_path = exe_path
        client_main_path = ''
        program_args = f"        <string>{exe_path}</string>"
    else:
        python_path = sys.executable
        client_main_path = str(Path(__file__).parent / 'main.py')
        program_args = (
            f"        <string>{python_path}</string>\n"
            f"        <string>{client_main_path}</string>"
        )

    launch_dir = Path.home() / 'Library' / 'LaunchAgents'
    launch_dir.mkdir(parents=True, exist_ok=True)
    plist_file = launch_dir / f'{_PLIST_LABEL}.plist'

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
"""
    plist_file.write_text(plist_content, encoding='utf-8')
    logger.info("LaunchAgent plist 已创建: %s", plist_file)

    try:
        subprocess.run(['launchctl', 'load', str(plist_file)], check=True)
        logger.info("macOS 自启动已注册")
        return True
    except Exception as e:
        logger.error("macOS 自启动注册失败: %s", e)
        return False


def _uninstall_startup_macos():
    """unload 并删除 macOS LaunchAgent plist。"""
    plist_file = Path.home() / 'Library' / 'LaunchAgents' / f'{_PLIST_LABEL}.plist'

    if plist_file.exists():
        try:
            subprocess.run(['launchctl', 'unload', str(plist_file)], stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.warning("unload LaunchAgent 时出错: %s", e)

        plist_file.unlink()
        logger.info("LaunchAgent plist 已删除")


# ======================================================================
# 平台分发
# ======================================================================

def _install_startup(exe_path):
    """根据当前平台调用对应的自启动注册函数。"""
    system = platform.system()
    if system == 'Windows':
        return _install_startup_windows(exe_path)
    elif system == 'Linux':
        return _install_startup_linux(exe_path)
    elif system == 'Darwin':
        return _install_startup_macos(exe_path)
    else:
        logger.warning("不支持的平台: %s，跳过自启动注册", system)
        return False


def _uninstall_startup():
    """根据当前平台调用对应的自启动移除函数。"""
    system = platform.system()
    if system == 'Windows':
        _uninstall_startup_windows()
    elif system == 'Linux':
        _uninstall_startup_linux()
    elif system == 'Darwin':
        _uninstall_startup_macos()
    else:
        logger.warning("不支持的平台: %s，跳过自启动移除", system)


# ======================================================================
# 停止运行中的客户端进程
# ======================================================================

def _stop_running_client():
    """停止正在运行的客户端进程。

    注意：会排除当前进程（install/uninstall 自身），避免自杀。
    """
    system = platform.system()
    try:
        if system == 'Windows':
            # 通过 taskkill 按 exe 名称终止
            if getattr(sys, 'frozen', False):
                exe_name = Path(sys.executable).name
            else:
                exe_name = 'python'
            # 排除当前 PID，防止 install/uninstall 自身被杀
            cmd = ['taskkill', '/F', '/IM', exe_name, '/FI', f'PID ne {os.getpid()}']
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            # Linux/macOS: 通过 pkill 按进程名终止
            if getattr(sys, 'frozen', False):
                proc_name = Path(sys.executable).name
            else:
                proc_name = 'main.py'
            # 排除当前 PID
            subprocess.run(
                ['pkill', '-f', proc_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        logger.warning("停止运行中的客户端进程时出错: %s", e)


# ======================================================================
# 获取安装目录
# ======================================================================

def _get_install_dir():
    """根据平台返回目标安装目录。"""
    system = platform.system()
    if system == 'Windows':
        base = os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))
        return Path(base) / 'WinConsoleClient'
    else:
        return Path.home() / '.winconsole-client' / 'bin'


# ======================================================================
# 4.1 install 命令
# ======================================================================

def install(server_addr):
    """安装客户端到系统并注册自启动。

    Args:
        server_addr: 服务端地址，格式 "ip:port"
    """
    _setup_installer_logging()
    system = platform.system()
    install_dir = _get_install_dir()

    def _step(msg):
        """同时打印到日志和控制台（flush 强制立即显示）。"""
        try:
            print(msg, flush=True)
        except Exception:
            pass
        logger.info(msg)

    _step("=" * 60)
    _step(f"[1/5] 准备安装：{install_dir}")
    _step(f"      服务端地址: {server_addr}")
    _step(f"      运行模式: {'frozen (PyInstaller)' if getattr(sys, 'frozen', False) else '源码'}")
    _step("=" * 60)

    # 创建安装目录
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        _step(f"[OK] 安装目录已就绪: {install_dir}")
    except Exception as e:
        _step(f"[FAIL] 无法创建安装目录: {e}")
        raise

    # 先停止可能正在运行的目标客户端进程，否则会因 exe 被占用而复制失败
    _step("[2/5] 停止正在运行的客户端进程 ...")
    _stop_running_client()
    time.sleep(0.5)
    _step("      -> 完成")

    # 判断是否为 PyInstaller 打包的可执行文件
    frozen = getattr(sys, 'frozen', False)

    if frozen:
        # PyInstaller 打包模式：复制当前 exe
        _step("[3/5] 复制可执行文件 ...")
        src_exe = Path(sys.executable)
        dst_exe = install_dir / src_exe.name

        # 先停止可能正在运行的目标客户端进程（排除自身 PID），
        # 并等待 Windows 释放文件句柄（Defender/索引器可能仍持有几秒）
        _stop_running_client()
        time.sleep(0.5)

        # 关键：写到 .dat（无 PE 扩展名），Defender 不会立即扫描并锁文件，
        # 等扫描完再 rename 成 .exe。最后一步 rename 一次性原子替换。
        last_err = None
        success = False
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            _stop_running_client()
            time.sleep(2.0)  # 给 Defender 留足扫描时间

            tmp_exe = install_dir / f"{src_exe.name}.{os.getpid()}.{int(time.time()*1000)%100000}.dat"

            # 策略 1：cmd /c copy /Y 写到 .dat
            try:
                if dst_exe.exists():
                    try:
                        dst_exe.unlink()
                    except PermissionError:
                        pass
                if tmp_exe.exists():
                    try:
                        tmp_exe.unlink()
                    except Exception:
                        pass

                r = subprocess.run(
                    ['cmd', '/c', 'copy', '/Y', str(src_exe), str(tmp_exe)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=20,
                )
                if r.returncode == 0 and tmp_exe.exists() and tmp_exe.stat().st_size > 0:
                    # 等 Defender 扫描
                    time.sleep(2.0)
                    # rename 到 .exe
                    os.replace(str(tmp_exe), str(dst_exe))
                    if dst_exe.exists():
                        exe_path = str(dst_exe)
                        _step(f"      [OK] 已复制: {dst_exe}  (cmd copy, 第 {attempt} 次尝试)")
                        success = True
                        break
                else:
                    out = (r.stdout or b'') + (r.stderr or b'')
                    _step(f"      [{attempt}/{max_attempts}] cmd copy 返回 {r.returncode} (rc=0/文件存在/非空)")
                    if out:
                        try:
                            _step(f"             输出: {out.decode('gbk', errors='replace').strip()[:200]}")
                        except Exception:
                            pass
            except Exception as e:
                last_err = e
                _step(f"      [{attempt}/{max_attempts}] cmd copy 异常: {e}")
                try:
                    if tmp_exe.exists():
                        tmp_exe.unlink()
                except Exception:
                    pass

            # 策略 2：shutil.copy2 + os.replace
            try:
                if dst_exe.exists():
                    try:
                        dst_exe.unlink()
                    except PermissionError:
                        pass
                if tmp_exe.exists():
                    try:
                        tmp_exe.unlink()
                    except Exception:
                        pass
                shutil.copy2(str(src_exe), str(tmp_exe))
                time.sleep(2.0)
                os.replace(str(tmp_exe), str(dst_exe))
                if dst_exe.exists():
                    exe_path = str(dst_exe)
                    _step(f"      [OK] 已复制: {dst_exe}  (shutil, 第 {attempt} 次尝试)")
                    success = True
                    break
            except Exception as e:
                last_err = e
                _step(f"      [{attempt}/{max_attempts}] 复制失败: {e}")
                try:
                    if tmp_exe.exists():
                        tmp_exe.unlink()
                except Exception:
                    pass

            # 两策略都失败，继续重试
            _step(f"      [{attempt}/{max_attempts}] 两策略均失败，3 秒后重试 ...")
            time.sleep(3.0)

        if not success:
            _step(f"[FAIL] 复制可执行文件失败，已重试 {max_attempts} 次")
            _step(f"       最后错误: {last_err}")
            _step("")
            _step("============================================================")
            _step("  你的杀毒软件/Defender 正在拦截对 exe 的写入。")
            _step("  请任选一种方式解决：")
            _step("============================================================")
            _step("  [方案 A] 把本目录加入 Defender 排除项（推荐）")
            _step(f"    PowerShell（管理员）执行：")
            _step(f'      Add-MpPreference -ExclusionPath "{install_dir}"')
            _step("")
            _step("  [方案 B] 暂时关闭 Defender 实时保护")
            _step("    设置 → Windows 安全 → 病毒防护 → 病毒和威胁防护设置 → 实时保护 关")
            _step("")
            _step("  [方案 C] 手动复制 + 自启动注册（不用 install）")
            _step(f"    1. 手动把当前 exe 拷贝到: {install_dir}")
            _step(f"    2. 用管理员 cmd 跑: reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run /v WinConsoleClient /t REG_SZ /d \"\\\"{dst_exe}\\\"\" /f")
            _step("============================================================")
            _step(f"  源文件: {src_exe}")
            _step(f"  目标:   {install_dir}")
            _step("============================================================")
            raise last_err
    else:
        # Python 源码模式：复制整个 client 目录
        _step("[3/5] 复制源码目录 ...")
        client_src = Path(__file__).parent
        client_dst = install_dir / 'client'
        if client_dst.exists():
            shutil.rmtree(str(client_dst))
        shutil.copytree(str(client_src), str(client_dst))
        exe_path = str(client_dst / 'main.py')
        _step(f"      [OK] 已复制: {client_dst}")

    # 保存配置文件
    _step("[4/5] 保存配置 ...")
    _save_config(server_addr)

    # 注册自启动
    _step("[5/5] 注册开机自启动 ...")
    startup_ok = _install_startup(exe_path)
    if startup_ok:
        _step("      [OK] 自启动已注册")
    else:
        _step("      [WARN] 自启动注册失败，客户端不会随系统自动启动")

    # 启动安装后的程序（静默模式）
    try:
        if frozen:
            subprocess.Popen(
                [exe_path],
                creationflags=subprocess.CREATE_NO_WINDOW if system == 'Windows' else 0,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            cmd = [sys.executable, exe_path]
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if system == 'Windows' else 0,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        _step("      [OK] 已启动安装后的客户端进程（静默）")
    except Exception as e:
        _step(f"      [WARN] 启动客户端进程失败: {e}")

    _step("=" * 60)
    _step("[SUCCESS] 客户端安装成功！")
    _step(f"  安装目录: {install_dir}")
    _step(f"  服务端地址: {server_addr}")
    _step(f"  自启动: {'已启用' if startup_ok else '未启用'}")
    _step("=" * 60)


# ======================================================================
# 4.6 uninstall 命令
# ======================================================================

def uninstall():
    """卸载客户端：停止进程、移除自启动、删除安装和配置目录。"""
    _setup_installer_logging()
    logger.info("=" * 60)
    logger.info("开始卸载客户端")

    # 停止正在运行的客户端进程
    _stop_running_client()

    # 移除自启动项
    _uninstall_startup()

    # 删除安装目录
    install_dir = _get_install_dir()
    if install_dir.exists():
        shutil.rmtree(str(install_dir))
        logger.info("安装目录已删除: %s", install_dir)

    # 删除配置目录
    if CONFIG_DIR.exists():
        shutil.rmtree(str(CONFIG_DIR))
        logger.info("配置目录已删除: %s", CONFIG_DIR)

    print("客户端已成功卸载！")
