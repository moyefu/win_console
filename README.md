# WinConsole - 远程控制管理平台

基于 C/S 架构的远程控制工具，一台服务端集中管理多台客户端机器，通过 Web 界面统一监控和操控。

## 功能特性

- **多设备集中管理** — 添加/删除/分组/配置客户端，设备信息持久化
- **在线状态监测** — 实时心跳检测，可视化在线/离线状态指示
- **仪表盘** — 设备统计概览、异常警报、实时事件通知
- **系统资源监控** — 设备详情页实时显示 CPU/内存使用率（每秒刷新）
- **远程屏幕实时流** — WebSocket 实时屏幕画面推送，支持全屏显示、控制模式、FPS/质量调节
- **屏幕控制模式** — 鼠标点击/拖拽/滚轮、键盘输入同步，特殊按键悬浮窗（Ctrl+Alt+Del等）
- **远程进程** — 查看/搜索/排序/结束进程
- **远程终端** — 基于 xterm.js + WebSocket 的交互终端，PTY 模式确保命令输出实时显示
- **鼠标控制** — 移动、点击、双击、右键、滚动、拖拽
- **键盘控制** — 文本输入、单键、组合热键
- **按键记录** — 实时键盘监控，WebSocket 推送
- **摄像头实时预览** — 多摄像头切换、分辨率调节、截图、视频录制（WebSocket 实时流）
- **硬盘监控** — 分区空间使用率可视化、磁盘 IO 统计、存储趋势图表（30分钟）
- **文件管理** — 文件浏览、上传/下载、断点续传、新建文件夹、重命名、删除、搜索
- **TLS 加密** — 服务端与客户端通信加密，支持自签名证书
- **系统托盘** — 服务端支持托盘图标模式运行（`--tray`）
- **开机自启** — 服务端和客户端均支持开机自启动
- **单实例运行** — 服务端自动检测并限制单实例运行
- **一键部署** — `install -server=ip:port` 自动安装并加入开机自启
- **跨平台客户端** — Windows / Linux / macOS

## 快速开始

### 1. 启动服务端

```bash
pip install -e ".[server]"
python -m server.main
```

启动后访问：`http://127.0.0.1:9081`

服务端监听 HTTP 端口 9081（Web 面板 + REST API），客户端 WebSocket 端口 9082。

首次访问需要在服务端本机完成初始化，设置管理员密码。初始化完成后，Web 面板和 API 都需要登录才能访问。

客户端认证密钥会自动生成，可在 Web 面板「设置 → 客户端认证密钥」查看或重新生成。

### 2. 安装客户端

在客户端机器上执行：

```bash
pip install -e ".[client]"

# 安装并连接服务端（自动注册开机自启）
python -m client.main install -server=192.168.1.100:9082 -auth-key=从设置页复制的客户端认证密钥

# 或临时指定服务端地址运行
python -m client.main --server 192.168.1.100:9082 -auth-key=从设置页复制的客户端认证密钥
```

如果服务端启用了 TLS，客户端也需要加上 `--tls`。使用项目自动生成的自签名证书时，可在可信内网中临时加 `--tls-insecure`；更推荐分发证书并通过 `--ca-cert <证书路径>` 校验服务端证书。

### 3. 编译为 EXE

```bash
# 打包服务端
build_server.bat
# 生成 dist\server\WinConsoleServer.exe (约 32MB)

# 打包客户端
build_client.bat
# 生成 dist\client\WinConsoleClient.exe (约 34MB)
```

打包优化说明：
- 已启用 UPX 压缩减小体积
- 已排除不必要的模块（tkinter、test、unittest等）
- 已启用 Python 字节码优化（`optimize=2`）
- 使用单文件模式（`--onefile`），方便部署

客户端部署示例：
```bash
WinConsoleClient.exe install -server=192.168.1.100:9082 -auth-key=从设置页复制的客户端认证密钥
```

## 命令行参数

### 服务端 (WinConsoleServer)

| 参数 | 说明 |
|------|------|
| `--port <端口>` | HTTP 监听端口（默认 9081） |
| `--host <地址>` | 监听地址（默认 0.0.0.0） |
| `--tray` | 以托盘图标模式运行 |
| `--install` | 添加开机自启动 |
| `--uninstall` | 移除开机自启动 |
| `--tls` | 启用 TLS 加密通信 |
| `--gen-cert` | 生成自签名 TLS 证书 |

### 客户端 (WinConsoleClient)

| 参数 | 说明 |
|------|------|
| `install -server=ip:port -auth-key=密钥` | 安装客户端，注册开机自启，连接服务端（默认静默安装） |
| `install -server=ip:port -auth-key=密钥 -cmd` | 安装客户端，显示控制台窗口并输出安装进度 |
| `install -server=ip:port -auth-key=密钥 -no-test` | 安装客户端，跳过连接测试 |
| `uninstall` | 卸载客户端，移除自启和安装目录 |
| `--server ip:port -auth-key=密钥` | 临时指定服务端地址运行 |
| `--tls` | 使用 `wss://` 连接服务端 |
| `--tls-insecure` | 使用 TLS 但不校验证书（仅限可信内网自签名场景） |
| `--ca-cert <路径>` | 使用指定 CA/证书文件校验服务端证书 |

## 项目结构

```
win_console/
├── common/                    # 共享协议层
│   ├── protocol.py            # 消息类型、序列化/反序列化
│   ├── crypto.py              # TLS 证书生成、SSL 上下文
│   └── config.py              # 共享默认配置
├── server/                    # 服务端
│   ├── main.py                # 入口（Flask + WebSocket 服务端）
│   ├── app.py                 # Flask 应用工厂
│   ├── client_manager.py      # 客户端管理（注册/心跳/转发/分组/持久化）
│   ├── api/
│   │   ├── dashboard.py       # 仪表盘统计
│   │   ├── devices.py         # 设备管理 CRUD
│   │   ├── groups.py          # 分组管理
│   │   ├── remote.py          # 远程控制代理
│   │   ├── settings.py        # 服务端配置
│   │   └── events.py          # 实时事件推送
│   └── (依赖见根 requirements.txt [server])
├── client/                    # 客户端
│   ├── main.py                # 入口
│   ├── core.py                # WebSocket 连接、心跳、自动重连
│   ├── installer.py           # 跨平台安装部署
│   ├── handlers/
│   │   ├── screenshot.py      # 截屏（跨平台）
│   │   ├── screen_stream.py   # 屏幕实时流（WebSocket）
│   │   ├── process.py         # 进程管理
│   │   ├── terminal.py        # 终端代理（PTY 模式）
│   │   ├── mouse.py           # 鼠标控制（支持down/up/wheel）
│   │   ├── keyboard.py        # 键盘控制（支持press/combo）
│   │   ├── keylog.py          # 按键记录
│   │   ├── system_info.py     # 系统资源信息（CPU/内存）
│   │   ├── camera.py          # 摄像头实时预览、截图、录制
│   │   ├── disk.py            # 硬盘分区监控、IO统计
│   │   ├── file_manager.py    # 文件浏览、搜索、重命名、删除、新建文件夹
│   │   └── file_transfer.py   # 文件上传/下载、断点续传
│   └── (依赖见根 requirements.txt [client])
├── templates/
│   └── index.html             # Web 管理面板
├── build_server.bat           # 服务端打包脚本
├── build_client.bat           # 客户端打包脚本
├── pyproject.toml             # 项目配置 + 依赖分组
└── requirements.txt           # 统一依赖（extras: [server] / [client]）
```

## API 接口

### 仪表盘

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard` | 设备统计 + 异常警报 |

### 设备管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 设备列表，支持 `?status=&group=&search=` 筛选 |
| GET | `/api/devices/<id>` | 设备详情 |
| DELETE | `/api/devices/<id>` | 删除设备 |
| POST | `/api/devices/<id>/group` | 设置设备分组 |

### 分组管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/groups` | 获取所有分组 |
| POST | `/api/groups` | 创建分组 |
| PUT | `/api/groups/<name>` | 重命名分组 |
| DELETE | `/api/groups/<name>` | 删除分组 |

### 远程控制

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/devices/<id>/screenshot` | 远程截屏（返回 base64） |
| GET | `/api/devices/<id>/screenshot/image` | 远程截屏（返回 JPEG） |
| WS | `/api/devices/<id>/screen/ws` | 屏幕实时流（推送帧数据） |
| WS | `/api/devices/<id>/control/ws` | 屏幕控制（鼠标/键盘操作） |
| GET | `/api/devices/<id>/processes` | 远程进程列表 |
| POST | `/api/devices/<id>/processes/<pid>/kill` | 结束远程进程 |
| POST | `/api/devices/<id>/mouse` | 远程鼠标操作 |
| POST | `/api/devices/<id>/keyboard` | 远程键盘操作 |
| GET | `/api/devices/<id>/system-info` | 获取系统资源信息（CPU/内存使用率） |
| WS | `/api/devices/<id>/terminal/ws` | 远程终端 |
| WS | `/api/devices/<id>/keylog/ws` | 远程按键记录 |

### 摄像头

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices/<id>/camera/list` | 获取摄像头列表 |
| POST | `/api/devices/<id>/camera/capture` | 摄像头截图（返回 base64） |
| POST | `/api/devices/<id>/camera/record/start` | 开始录制 |
| POST | `/api/devices/<id>/camera/record/stop` | 停止录制（返回 AVI base64） |
| WS | `/api/devices/<id>/camera/ws` | 摄像头实时预览（推送帧数据） |

### 硬盘监控

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices/<id>/disk` | 获取分区列表、使用率、剩余空间 |
| GET | `/api/devices/<id>/disk/io` | 获取磁盘 IO 统计、读写速率 |

### 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices/<id>/files/roots` | 获取根目录列表（Windows 驱动器、Linux 挂载点） |
| GET | `/api/devices/<id>/files` | 文件列表（`?path=<路径>`） |
| POST | `/api/devices/<id>/files/search` | 文件搜索 |
| POST | `/api/devices/<id>/files/rename` | 重命名 |
| POST | `/api/devices/<id>/files/delete` | 删除 |
| POST | `/api/devices/<id>/files/mkdir` | 新建文件夹 |
| WS | `/api/devices/<id>/file-transfer/ws` | 文件上传/下载（分块传输、断点续传） |

### 设置与事件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/settings` | 服务端配置读写 |
| WS | `/api/events` | 实时事件推送（上下线/警报） |

## 通信架构

- **Web 面板 → 服务端**：HTTP (端口 9081) + Flask-Sock WebSocket
- **客户端 → 服务端**：WebSocket (端口 9082)，JSON 消息协议
- 消息类型：HEARTBEAT / REGISTER / SCREENSHOT / SCREEN_DATA / SCREEN_CONFIG / PROCESS / TERMINAL / TERMINAL_DATA / MOUSE / KEYBOARD / KEYLOG / KEYLOG_DATA / SYSTEM_INFO / CONFIG / CAMERA / CAMERA_DATA / DISK / FILE_MANAGER / FILE_TRANSFER / FILE_TRANSFER_DATA / DISCONNECT 等
- 心跳间隔 10 秒，超时 30 秒判定离线，断线每 5 秒自动重连
- 支持 TLS 加密（`--tls`），无证书时回退 ws:// 并显示安全警告
- 文件传输：分块传输（1MB/chunk），支持断点续传（offset 参数）

## 客户端跨平台

| 平台 | 截屏 | 终端 | 摄像头 | 自启动 | 备注 |
|------|------|------|--------|--------|------|
| Windows | PIL ImageGrab | cmd.exe (ConPTY) | cv2 (OpenCV) | 注册表 Run 键 | 终端需要 pywinpty |
| Linux | pyscreenshot | /bin/bash (PTY) | cv2 (OpenCV) | systemd user service | 终端使用 pty 标准库 |
| macOS | PIL ImageGrab (screencapture) | /bin/bash (PTY) | cv2 (OpenCV) | LaunchAgent plist | 终端使用 pty 标准库 |

## 日志

- 服务端：
  - 主日志：`%USERPROFILE%\.winconsole\winconsole.log`
  - 错误日志：`%USERPROFILE%\.winconsole\errors.log`
- 客户端：`%USERPROFILE%\.winconsole-client\client.log`

## 注意事项

- 首次使用必须在服务端本机设置管理员密码；之后 Web 面板、REST API 和 WebSocket 管理通道都需要登录。
- 客户端连接必须携带服务端生成的 `auth_key`，密钥错误会被拒绝注册。
- 启用 TLS 后，服务端会自动准备自签名证书；正式或跨网段部署建议分发证书并使用 `--ca-cert` 校验，避免长期使用 `--tls-insecure`。
- 仅限可信网络环境使用，不建议在公网暴露服务端口
- 部分功能（如进程管理、文件管理）可能需要管理员权限
- 客户端无 GUI、无托盘图标，完全静默运行
- 按键记录依赖 pynput，未安装时自动禁用
- 摄像头功能依赖 OpenCV (cv2)，未安装时自动禁用
- 文件传输使用 WebSocket 分块传输，每块 1MB，支持断点续传
- Windows 终端功能已内置 pywinpty（打包时包含），无需手动安装
- Linux/macOS 终端使用标准 pty 库，无需额外依赖

## 系统要求

- 服务端：Windows / Linux / macOS，Python 3.7+
- 客户端：Windows / Linux / macOS，Python 3.7+
- 管理员权限（部分功能可能需要）

## 许可证

MIT License

## 作者

moyefu
