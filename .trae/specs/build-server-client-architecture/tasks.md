# Tasks

- [x] Task 1: 搭建项目目录结构与共享协议层
  - [ ] 1.1 创建 `common/` 目录，编写 `common/protocol.py`：定义消息类型枚举（HEARTBEAT/REGISTER/COMMAND/SCREENSHOT/PROCESS/TERMINAL/MOUSE/KEYBOARD/KEYLOG/CONFIG/ERROR）、消息格式（type/client_id/payload/seq）、序列化/反序列化函数
  - [ ] 1.2 创建 `common/crypto.py`：封装 TLS 上下文创建、自签名证书生成工具函数
  - [ ] 1.3 创建 `common/config.py`：定义服务端和客户端共享的默认配置（默认端口 9081、心跳间隔 10s、心跳超时 30s、重连间隔 5s）
  - [ ] 1.4 创建 `server/`、`client/` 目录结构，编写各自的 `__init__.py` 和 `requirements.txt`

- [x] Task 2: 实现客户端核心（连接、心跳、指令执行）
  - [ ] 2.1 编写 `client/core.py`：ClientEngine 类，使用 `websockets` 库建立到服务端的持久 WebSocket 连接，实现自动重连（5 秒间隔）
  - [ ] 2.2 实现客户端注册流程：连接后发送 REGISTER 消息（含 hostname、OS、IP 等设备信息），接收服务端分配的 client_id
  - [ ] 2.3 实现心跳机制：每 10 秒发送 HEARTBEAT 消息，响应服务端 HEARTBEAT_REQUEST
  - [ ] 2.4 实现指令分发：接收服务端 COMMAND 消息，根据 type 分发到对应的 handler（screenshot/process/terminal/mouse/keyboard/keylog/config）

- [x] Task 3: 实现客户端功能模块（从原 app.py 迁移）
  - [ ] 3.1 `client/handlers/screenshot.py`：迁移 capture_screenshot 逻辑，接收截屏指令后执行 ImageGrab.grab()，返回 JPEG 二进制数据
  - [ ] 3.2 `client/handlers/process.py`：迁移 get_process_list 和 kill 逻辑，接收指令后返回进程列表或执行 kill
  - [ ] 3.3 `client/handlers/terminal.py`：迁移 PersistentTerminal 类，实现终端 WebSocket 通道（服务端↔客户端↔cmd/bash）
  - [ ] 3.4 `client/handlers/mouse.py`：迁移 pyautogui 鼠标操作（move/click/doubleClick/rightClick/scroll/drag/getPos）
  - [ ] 3.5 `client/handlers/keyboard.py`：迁移 pyautogui 键盘操作（type/press/hotkey）和 pynput 按键监听
  - [ ] 3.6 `client/handlers/keylog.py`：迁移按键记录逻辑，实时通过 WebSocket 上报按键事件
  - [ ] 3.7 跨平台适配：Linux 使用 pyscreenshot 截图 + bash 终端 + systemd 自启动；macOS 使用 screencapture + bash + LaunchAgent

- [x] Task 4: 实现客户端安装部署机制
  - [ ] 4.1 `client/installer.py`：实现 `install -server=ip:port` 命令，复制自身到安装目录（Windows: `%LOCALAPPDATA%\WinConsoleClient`）
  - [ ] 4.2 Windows 自启动：写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 注册表项
  - [ ] 4.3 Linux 自启动：创建 `~/.config/systemd/user/winconsole-client.service`
  - [ ] 4.4 macOS 自启动：创建 `~/Library/LaunchAgents/com.winconsole.client.plist`
  - [ ] 4.5 保存服务端地址到本地配置文件（`~/.winconsole-client/config.json`），启动时读取并自动连接
  - [ ] 4.6 实现 `uninstall` 命令：移除自启动项、删除安装目录

- [x] Task 5: 实现服务端客户端管理模块
  - [ ] 5.1 `server/client_manager.py`：ClientManager 类，维护已连接客户端字典（client_id → ClientSession），ClientSession 包含 ws 连接、设备信息、在线状态、最后心跳时间、分组等
  - [ ] 5.2 实现客户端注册：接收 REGISTER 消息，生成 client_id，创建 ClientSession，发送 REGISTER_ACK
  - [ ] 5.3 实现心跳检测：后台线程每 10 秒检查所有客户端最后心跳时间，超时 30 秒标记为离线，触发状态变更事件
  - [ ] 5.4 实现指令转发：接收 Web API 请求，根据 client_id 查找对应 WebSocket 连接，转发指令并等待响应
  - [ ] 5.5 实现客户端删除：发送 DISCONNECT 指令，从管理器中移除记录
  - [ ] 5.6 实现分组管理：维护分组列表，支持创建/删除/重命名分组，客户端分配到分组
  - [ ] 5.7 设备信息持久化：使用 JSON 文件（`~/.winconsole/devices.json`）存储设备信息和分组，重启后恢复

- [x] Task 6: 实现服务端 Web API
  - [ ] 6.1 重构 `server/app.py`：Flask 应用入口，挂载 Flask-Sock，注册蓝图
  - [ ] 6.2 `server/api/dashboard.py`：GET /api/dashboard 返回设备统计（总数/在线/离线/异常警报）
  - [ ] 6.3 `server/api/devices.py`：GET /api/devices 设备列表（支持 ?status=online&group=xxx&search=xxx 筛选）；GET /api/devices/<id> 设备详情；DELETE /api/devices/<id> 删除设备；POST /api/devices/<id>/group 设置分组
  - [ ] 6.4 `server/api/groups.py`：GET/POST/PUT/DELETE /api/groups 分组 CRUD
  - [ ] 6.5 `server/api/remote.py`：代理转发原有功能 API——POST /api/devices/<id>/screenshot、GET /api/devices/<id>/processes、POST /api/devices/<id>/mouse、POST /api/devices/<id>/keyboard、WS /api/devices/<id>/terminal/ws、WS /api/devices/<id>/keylog/ws
  - [ ] 6.6 `server/api/settings.py`：GET/POST /api/settings 服务端配置（端口/心跳间隔/认证密钥/TLS 开关/通知开关）
  - [ ] 6.7 `server/api/events.py`：WS /api/events WebSocket 事件推送通道，推送设备上下线、异常警报等实时事件给 Web 面板

- [x] Task 7: 实现服务端托盘与启动
  - [ ] 7.1 `server/main.py`：入口文件，解析命令行参数（--port/--tray/--install/--uninstall），初始化日志、ClientManager、Flask
  - [ ] 7.2 保留托盘图标功能（--tray），菜单包含"打开浏览器"和"退出"

- [x] Task 8: 重构 Web 前端界面
  - [ ] 8.1 新增仪表盘页面：统计卡片（设备总数/在线/离线/异常）、异常警报列表、设备状态概览图表
  - [ ] 8.2 新增设备管理页面：设备表格（名称/IP/OS/分组/状态/最后在线时间）、筛选栏（按状态/分组/搜索）、分组管理侧栏
  - [ ] 8.3 新增设备详情页面：设备信息卡片、连接历史、资源监控、远程控制子页面（屏幕/进程/终端/鼠标/键盘/按键记录，复用原有 UI 组件但 API 改为 /api/devices/<id>/xxx）
  - [ ] 8.4 新增设置页面：服务端参数配置表单、认证密钥管理、TLS 证书配置、通知开关
  - [ ] 8.5 实现实时事件通知：连接 /api/events WebSocket，设备状态变化时右上角弹出 Toast 通知
  - [ ] 8.6 重构侧边栏导航：仪表盘/设备管理/设备详情（动态）/设置，移除原一级屏幕/进程/终端/鼠标/键盘/按键记录导航

- [x] Task 9: 构建与打包脚本
  - [ ] 9.1 `build_server.bat`：PyInstaller 打包服务端为 WinConsoleServer.exe
  - [ ] 9.2 `build_client.bat`：PyInstaller 打包客户端为 WinConsoleClient.exe（--onefile --noconsole，无托盘依赖）
  - [ ] 9.3 更新根目录 `requirements.txt`，拆分为 `server/requirements.txt` 和 `client/requirements.txt`

# Task Dependencies
- Task 1 → Task 2, Task 5（共享协议是客户端和服务端的前置依赖）
- Task 2 → Task 3（客户端连接核心是功能模块的前置依赖）
- Task 3 → Task 4（功能模块完成后才能实现安装部署）
- Task 5 → Task 6（客户端管理模块是 Web API 的前置依赖）
- Task 6 → Task 8（Web API 是前端的前置依赖）
- Task 2 + Task 5 → Task 7（客户端和服务端核心就绪后整合入口）
- Task 3 + Task 6 → Task 8（功能模块和 API 就绪后重构前端）
- Task 3 + Task 5 → Task 9（功能就绪后编写构建脚本）

# Parallelizable Work
- Task 3（客户端功能模块）与 Task 5（服务端客户端管理）可并行
- Task 8.1-8.4（前端各页面）在 API 定义后可并行
- Task 4（安装部署）与 Task 6（Web API）可并行
