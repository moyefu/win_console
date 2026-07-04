# WinConsole - 远程控制管理平台

基于 C/S 架构的远程控制工具，一台服务端集中管理多台客户端机器，通过 Web 界面统一监控和操控。

## 功能特性

- **多设备集中管理** — 添加/删除/分组/配置客户端，设备信息持久化
- **在线状态监测** — 实时心跳检测，可视化在线/离线状态指示
- **仪表盘** — 设备统计概览、异常警报、实时事件通知
- **系统资源监控** — 设备详情页实时显示 CPU/内存使用率（每秒刷新）
- **远程屏幕** — 实时屏幕截图，可配置刷新间隔
- **远程进程** — 查看/搜索/排序/结束进程
- **远程终端** — 基于 xterm.js + WebSocket 的交互终端，PTY 模式确保命令输出实时显示
- **鼠标控制** — 移动、点击、双击、右键、滚动、拖拽
- **键盘控制** — 文本输入、单键、组合热键
- **按键记录** — 实时键盘监控，WebSocket 推送
- **TLS 加密** — 服务端与客户端通信加密，支持自签名证书
- **系统托盘** — 服务端支持托盘图标模式运行（`--tray`）
- **开机自启** — 服务端和客户端均支持开机自启动
- **单实例运行** — 服务端自动检测并限制单实例运行
- **一键部署** — `install -server=ip:port` 自动安装并加入开机自启
- **跨平台客户端** — Windows / Linux / macOS

## 快速开始

### 1. 启动服务端

```bash
pip install -r server/requirements.txt
python -m server.main
```

启动后访问：`http://127.0.0.1:9081`

服务端监听 HTTP 端口 9081（Web 面板 + REST API），客户端 WebSocket 端口 9082。

### 2. 安装客户端

在客户端机器上执行：

```bash
pip install -r client/requirements.txt

# 安装并连接服务端（自动注册开机自启）
python -m client.main install -server=192.168.1.100:9082

# 或临时指定服务端地址运行
python -m client.main --server 192.168.1.100:9082
```

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
WinConsoleClient.exe install -server=192.168.1.100:9082
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
| `install -server=ip:port` | 安装客户端，注册开机自启，连接服务端（默认静默安装） |
| `install -server=ip:port -cmd` | 安装客户端，显示控制台窗口并输出安装进度 |
| `install -server=ip:port -no-test` | 安装客户端，跳过连接测试 |
| `uninstall` | 卸载客户端，移除自启和安装目录 |
| `--server ip:port` | 临时指定服务端地址运行 |

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
│   └── requirements.txt
├── client/                    # 客户端
│   ├── main.py                # 入口
│   ├── core.py                # WebSocket 连接、心跳、自动重连
│   ├── installer.py           # 跨平台安装部署
│   ├── handlers/
│   │   ├── screenshot.py      # 截屏（跨平台）
│   │   ├── process.py         # 进程管理
│   │   ├── terminal.py        # 终端代理（PTY 模式）
│   │   ├── mouse.py           # 鼠标控制
│   │   ├── keyboard.py        # 键盘控制
│   │   ├── keylog.py          # 按键记录
│   │   └── system_info.py     # 系统资源信息（CPU/内存）
│   └── requirements.txt
├── templates/
│   └── index.html             # Web 管理面板
├── build_server.bat           # 服务端打包脚本
├── build_client.bat           # 客户端打包脚本
└── requirements.txt           # 合并依赖
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
| GET | `/api/devices/<id>/processes` | 远程进程列表 |
| POST | `/api/devices/<id>/processes/<pid>/kill` | 结束远程进程 |
| POST | `/api/devices/<id>/mouse` | 远程鼠标操作 |
| POST | `/api/devices/<id>/keyboard` | 远程键盘操作 |
| GET | `/api/devices/<id>/system-info` | 获取系统资源信息（CPU/内存使用率） |
| WS | `/api/devices/<id>/terminal/ws` | 远程终端 |
| WS | `/api/devices/<id>/keylog/ws` | 远程按键记录 |

### 设置与事件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/settings` | 服务端配置读写 |
| WS | `/api/events` | 实时事件推送（上下线/警报） |

## 通信架构

- **Web 面板 → 服务端**：HTTP (端口 9081) + Flask-Sock WebSocket
- **客户端 → 服务端**：WebSocket (端口 9082)，JSON 消息协议
- 消息类型：HEARTBEAT / REGISTER / SCREENSHOT / PROCESS / TERMINAL / TERMINAL_DATA / MOUSE / KEYBOARD / KEYLOG / KEYLOG_DATA / SYSTEM_INFO / CONFIG / DISCONNECT 等
- 心跳间隔 10 秒，超时 30 秒判定离线，断线每 5 秒自动重连
- 支持 TLS 加密（`--tls`），无证书时回退 ws:// 并显示安全警告

## 客户端跨平台

| 平台 | 截屏 | 终端 | 自启动 | 备注 |
|------|------|------|--------|------|
| Windows | PIL ImageGrab | cmd.exe (ConPTY) | 注册表 Run 键 | 终端需要 pywinpty |
| Linux | pyscreenshot | /bin/bash (PTY) | systemd user service | 终端使用 pty 标准库 |
| macOS | PIL ImageGrab (screencapture) | /bin/bash (PTY) | LaunchAgent plist | 终端使用 pty 标准库 |

## 日志

- 服务端：
  - 主日志：`%USERPROFILE%\.winconsole\winconsole.log`
  - 错误日志：`%USERPROFILE%\.winconsole\errors.log`
- 客户端：`%USERPROFILE%\.winconsole-client\client.log`

## 注意事项

- 仅限可信网络环境使用，不建议在公网暴露服务端口
- 部分功能（如进程管理）可能需要管理员权限
- 客户端无 GUI、无托盘图标，完全静默运行
- 按键记录依赖 pynput，未安装时自动禁用
- Windows 终端功能依赖 pywinpty（ConPTY），未安装时回退到管道模式（命令输出可能延迟）
- Linux/macOS 终端使用标准 pty 库，无需额外依赖

## 系统要求

- 服务端：Windows / Linux / macOS，Python 3.7+
- 客户端：Windows / Linux / macOS，Python 3.7+
- 管理员权限（部分功能可能需要）

## 许可证

MIT License

## 作者

moyefu
