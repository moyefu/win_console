# 服务端-客户端架构重构 Spec

## Why
当前 WinConsole 是单机模式——Flask 服务直接在本机执行截图、进程管理、终端、键鼠控制等操作。需要重构为 C/S 架构，实现一台服务端集中管理多台客户端机器，通过 Web 界面统一监控和操控。

## What Changes
- **新增独立客户端程序** (`client/`)：从当前 `app.py` 中剥离远程控制能力（截图、进程、终端、键鼠、按键记录），改为连接服务端并接收指令执行
- **重构服务端程序** (`server/`)：保留 Flask Web 面板，新增客户端管理模块（设备注册/心跳/指令转发），原单机功能 API 改为向指定客户端代理转发
- **新增通信协议层** (`common/protocol.py`)：基于 WebSocket 的 JSON 消息协议，单端口复用（控制指令 + 数据流），TLS 加密
- **新增客户端安装机制**：`install -server=ip:port` 命令，自动注册开机自启动，自动连接服务端
- **新增 Web 管理界面模块**：仪表盘、设备管理、设备详情、设置面板
- **BREAKING**: 服务端不再直接执行本机操作，所有操作通过客户端代理完成；原单机模式不再保留

## Impact
- Affected specs: 全部现有功能模块（截图、进程、终端、键鼠、按键记录）均需重构为 C/S 代理模式
- Affected code: `app.py`（拆分为 server + client + common）、`templates/index.html`（新增管理模块、设备选择器）
- 新增依赖: `websockets`（客户端异步通信）、`cryptography`（TLS/加密）

## ADDED Requirements

### Requirement: 客户端管理
系统 SHALL 提供对多台客户端机器的集中管理能力。

#### Scenario: 添加客户端
- **WHEN** 用户在客户端机器上运行 `WinConsoleClient.exe install -server=ip:port`
- **THEN** 客户端程序安装到系统路径，注册为开机自启动服务，自动与指定服务端建立持久连接

#### Scenario: 删除客户端
- **WHEN** 管理员在 Web 面板中删除某台客户端
- **THEN** 该客户端记录从服务端移除，已连接的客户端收到断开指令并停止重连

#### Scenario: 客户端分组
- **WHEN** 管理员在 Web 面板中创建分组并将客户端分配到分组
- **THEN** 设备列表可按分组筛选，支持批量操作同一分组的设备

#### Scenario: 客户端配置
- **WHEN** 管理员在设置面板中修改某客户端的截屏间隔等参数
- **THEN** 服务端通过控制通道下发配置变更，客户端实时生效

### Requirement: 在线状态监测
系统 SHALL 实时监测所有已连接客户端的在线状态，并提供可视化指示。

#### Scenario: 客户端上线
- **WHEN** 客户端成功连接服务端并通过认证
- **THEN** 仪表盘和设备列表中该设备状态变为"在线"（绿色指示器）

#### Scenario: 客户端离线
- **WHEN** 心跳超时（默认 30 秒无心跳响应）或连接断开
- **THEN** 设备状态变为"离线"（红色指示器），仪表盘异常计数 +1

#### Scenario: 心跳检测
- **WHEN** 服务端运行中
- **THEN** 服务端每 10 秒向所有已连接客户端发送心跳请求，客户端必须回应；连续 3 次未响应则判定离线

### Requirement: 客户端安装部署
系统 SHALL 提供便捷的客户端安装与部署机制。

#### Scenario: 安装命令
- **WHEN** 用户执行 `WinConsoleClient.exe install -server=192.168.1.100:9081`
- **THEN** 客户端复制自身到安装目录，写入注册表/启动项，以静默方式启动并连接服务端

#### Scenario: 开机自启动
- **WHEN** 客户端安装完成
- **THEN** Windows 下写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，Linux 下创建 systemd service，macOS 下创建 LaunchAgent

#### Scenario: 自动连接
- **WHEN** 客户端启动
- **THEN** 自动使用安装时保存的服务端地址发起 WebSocket 连接，断线后每 5 秒自动重连

#### Scenario: 无托盘图标
- **WHEN** 客户端运行
- **THEN** 不显示任何 GUI 窗口或系统托盘图标，完全静默运行

### Requirement: 仪表盘
系统 SHALL 在 Web 面板提供仪表盘页面。

#### Scenario: 状态概览
- **WHEN** 管理员访问仪表盘
- **THEN** 显示设备总数、在线数、离线数、异常警报数的统计卡片

#### Scenario: 异常警报
- **WHEN** 某客户端离线或心跳异常
- **THEN** 仪表盘异常警报区域显示该事件，包含设备名称、时间、异常类型

### Requirement: 设备管理
系统 SHALL 提供 Web 面板设备管理页面。

#### Scenario: 设备列表
- **WHEN** 管理员访问设备管理页面
- **THEN** 以表格展示所有设备，列包含：设备名、IP、操作系统、分组、在线状态、最后在线时间，支持按状态/分组筛选和搜索

#### Scenario: 设备详情
- **WHEN** 管理员点击某台设备
- **THEN** 进入设备详情页，显示设备系统信息、连接历史时间线、当前资源使用（CPU/内存/磁盘），以及原有的远程控制功能（屏幕/进程/终端/键鼠/按键记录）

### Requirement: 设置面板
系统 SHALL 提供 Web 面板设置页面。

#### Scenario: 服务端参数配置
- **WHEN** 管理员在设置面板修改监听端口、心跳间隔等参数
- **THEN** 参数写入配置文件，部分参数需重启生效时给出提示

#### Scenario: 客户端连接策略
- **WHEN** 管理员配置客户端连接策略（认证密钥、黑白名单等）
- **THEN** 新连接的客户端必须通过认证才能注册

#### Scenario: 通知机制
- **WHEN** 管理员启用设备上下线通知
- **THEN** 设备状态变化时，Web 面板右上角弹出通知提示

### Requirement: 通信协议
系统 SHALL 使用稳定可靠的通信协议确保服务端与客户端的实时数据交互。

#### Scenario: 单端口通信
- **WHEN** 客户端连接服务端
- **THEN** 所有通信（心跳、控制指令、数据流）通过同一 WebSocket 端口完成，使用消息类型字段区分

#### Scenario: 消息格式
- **WHEN** 服务端与客户端交换数据
- **THEN** 使用 JSON 格式消息，包含 `type`（消息类型）、`client_id`（客户端标识）、`payload`（数据体）、`seq`（序列号）字段

#### Scenario: 通信加密
- **WHEN** 服务端与客户端通信
- **THEN** 使用 TLS 加密 WebSocket 连接（wss://）；如未配置证书则回退到 ws:// 并在面板中显示安全警告

### Requirement: 跨平台客户端
客户端 SHALL 支持 Windows、Linux、macOS 安装与运行。

#### Scenario: Windows 客户端
- **WHEN** 在 Windows 上运行客户端
- **THEN** 截图使用 Pillow ImageGrab，终端使用 cmd.exe，自启动使用注册表 Run 键

#### Scenario: Linux 客户端
- **WHEN** 在 Linux 上运行客户端
- **THEN** 截图使用 Pillow + pyscreenshot，终端使用 /bin/bash，自启动使用 systemd user service

#### Scenario: macOS 客户端
- **WHEN** 在 macOS 上运行客户端
- **THEN** 截图使用 Pillow ImageGrab（screencapture），终端使用 /bin/bash，自启动使用 LaunchAgent plist

### Requirement: 远程控制代理
原有的远程控制功能（屏幕、进程、终端、键鼠、按键记录）SHALL 通过服务端向指定客户端代理转发执行。

#### Scenario: 查看远程屏幕
- **WHEN** 管理员在设备详情页点击"屏幕"
- **THEN** 服务端向该客户端发送截屏指令，客户端执行后返回截图数据，Web 面板实时显示

#### Scenario: 远程终端
- **WHEN** 管理员在设备详情页打开终端
- **THEN** 服务端与该客户端建立终端 WebSocket 通道，键盘输入转发至客户端执行，输出回传至 Web 面板

#### Scenario: 远程键鼠控制
- **WHEN** 管理员在设备详情页执行鼠标/键盘操作
- **THEN** 服务端将操作指令转发至对应客户端，客户端本地执行 pyautogui 操作

## MODIFIED Requirements

### Requirement: 项目结构（原单文件架构改为多模块）
原 `app.py` 单文件架构拆分为：
- `server/` — 服务端程序（Flask Web + 客户端管理 + 指令转发）
- `client/` — 客户端程序（连接服务端 + 执行指令 + 心跳上报）
- `common/` — 共享协议定义、消息格式、加密工具

### Requirement: Web 界面（原单页面改为多页面/模块化）
原单页应用侧边栏改为：
- 仪表盘（新增，默认首页）
- 设备管理（新增）
- 设备详情（新增，含原 6 个功能模块作为子页面）
- 设置（新增）

## REMOVED Requirements

### Requirement: 单机模式
**Reason**: 架构升级为 C/S 模式，服务端不再直接执行本机操作
**Migration**: 原单机功能的代码逻辑移至客户端程序，服务端仅负责 Web 面板和指令转发

### Requirement: 系统托盘
**Reason**: 客户端不需要托盘图标；服务端可选保留托盘
**Migration**: 服务端保留 `--tray` 托盘模式；客户端完全静默无 GUI
