# 摄像头与硬盘/文件管理功能 Spec

## Why
当前 WinConsole 已实现屏幕截图、进程管理、终端、键鼠控制、按键记录、系统信息等远程控制功能，但缺少摄像头访问、硬盘监控、文件传输与管理等关键运维能力。这些功能是企业级远程管理工具的标准配置，补齐后将大幅提升系统的远程运维完整度。

## What Changes
- **新增摄像头模块**：客户端采集摄像头画面，通过 MJPEG 流或帧序列实时推送到 Web 面板；支持多摄像头切换、分辨率/帧率调整、截图、录制
- **新增硬盘监控模块**：客户端通过 psutil 采集磁盘分区信息、使用率、IO 统计，服务端汇总并提供趋势数据
- **新增文件传输模块**：客户端/服务端之间通过 WebSocket 二进制帧传输文件，支持上传/下载、进度上报、断点续传
- **新增文件管理模块**：客户端执行目录浏览、文件搜索/重命名/删除/移动/复制等操作，Web 面板提供文件浏览器界面
- **新增协议消息类型**：CAMERA、CAMERA_DATA、DISK、FILE_TRANSFER、FILE_TRANSFER_DATA、FILE_MANAGER
- **新增 Web 前端标签页**：设备详情页新增"摄像头"、"硬盘"、"文件"三个标签页
- **BREAKING**: protocol.py MsgType 枚举新增 6 个值，客户端和服务端需同步更新

## Impact
- Affected specs: 通信协议（MsgType 新增）、客户端 handler 注册、服务端 remote API、Web 前端标签页
- Affected code:
  - `common/protocol.py` — 新增 6 个 MsgType
  - `client/handlers/` — 新增 `camera.py`、`disk.py`、`file_transfer.py`、`file_manager.py`
  - `client/main.py` — 注册新 handler
  - `server/api/remote.py` — 新增 REST + WebSocket 路由
  - `server/main.py` — 处理新消息类型
  - `server/client_manager.py` — 新增摄像头/文件传输 WebSocket 映射
  - `templates/index.html` — 新增 3 个标签页 UI
- 新增客户端依赖: `opencv-python`（摄像头）、`numpy`（帧处理）

---

## 现有功能审查与缺失分析

### 已有功能模块
| 模块 | 客户端 Handler | 服务端 API | Web UI | 完整度 |
|------|---------------|-----------|--------|--------|
| 截图 | screenshot.py | POST /screenshot | 截图标签页 | 完整 |
| 进程 | process.py | GET /processes, POST /kill | 进程标签页 | 完整 |
| 终端 | terminal.py | WS /terminal/ws | 终端标签页 | 完整 |
| 鼠标 | mouse.py | POST /mouse | 鼠标标签页 | 完整 |
| 键盘 | keyboard.py | POST /keyboard | 键盘标签页 | 完整 |
| 按键记录 | keylog.py | WS /keylog/ws | 按键记录标签页 | 完整 |
| 系统信息 | system_info.py | GET /system-info | 资源监控区 | 完整 |

### 功能缺失与改进建议
| 缺失功能 | 优先级 | 说明 |
|----------|--------|------|
| 摄像头画面获取 | 高 | 远程查看被控端摄像头，安全监控核心功能 |
| 硬盘空间监控 | 高 | 运维基础能力，及时发现磁盘满/异常 |
| 文件传输（上传/下载） | 高 | 远程运维必备，分发补丁/收集日志 |
| 文件管理（浏览/操作） | 高 | 远程排查问题必备 |
| 远程桌面（实时屏幕流） | 中 | 当前只有截图，无实时画面流；帧率受限 |
| 远程关机/重启 | 中 | 缺少远程电源操作 |
| 服务/计划任务管理 | 中 | 缺少 Windows Service 和计划任务查看/控制 |
| 网络状态监控 | 中 | 缺少网络连接/流量/网卡信息查看 |
| 远程执行脚本 | 低 | 批量下发脚本执行，当前可部分通过终端实现 |
| 多屏幕支持 | 低 | 截图仅获取主屏幕，多显示器场景未处理 |
| 审计日志 | 低 | 管理员操作审计缺失 |
| 告警规则引擎 | 低 | 当前只有离线告警，无自定义阈值告警 |

---

## ADDED Requirements

### Requirement: 摄像头画面获取
系统 SHALL 提供对客户端设备摄像头的远程访问能力。

#### Scenario: 摄像头列表获取
- **WHEN** 管理员在设备详情页点击"摄像头"标签
- **THEN** Web 面板向客户端请求可用摄像头列表，显示设备名称和索引

#### Scenario: 实时预览
- **WHEN** 管理员选择某摄像头并点击"开始预览"
- **THEN** 客户端打开该摄像头，以 MJPEG 帧序列通过 WebSocket 推送到 Web 面板，页面以 `<img>` 标签实时显示

#### Scenario: 多摄像头切换
- **WHEN** 客户端有多个摄像头设备
- **THEN** 管理员可在下拉列表中切换不同摄像头，切换时关闭旧摄像头并打开新摄像头

#### Scenario: 画面质量调整
- **WHEN** 管理员调整分辨率或帧率参数
- **THEN** 客户端应用新参数重新打开摄像头，推送帧的画面质量相应变化

#### Scenario: 摄像头截图
- **WHEN** 管理员点击"截图"按钮
- **THEN** 客户端截取当前帧并以 JPEG 返回，Web 面板提供下载

#### Scenario: 摄像头录制
- **WHEN** 管理员点击"开始录制"
- **THEN** 客户端在本地将摄像头帧写入视频文件（临时存储），管理员点击"停止录制"后客户端将录制文件上传到服务端，Web 面板提供下载

#### Scenario: 权限异常处理
- **WHEN** 客户端摄像头不可用（无设备、权限拒绝、被占用）
- **THEN** 客户端返回错误信息，Web 面板显示友好的错误提示

### Requirement: 硬盘空间监控
系统 SHALL 提供客户端设备的硬盘分区使用状态监控能力。

#### Scenario: 磁盘分区列表
- **WHEN** 管理员在设备详情页点击"硬盘"标签
- **THEN** 显示客户端所有磁盘分区的信息：盘符/挂载点、文件系统类型、总容量、已用/可用空间、使用率百分比

#### Scenario: 存储趋势分析
- **WHEN** 硬盘标签页处于活跃状态
- **THEN** 每分钟采集一次磁盘使用率数据，Web 面板以折线图展示最近 30 分钟的使用率趋势

#### Scenario: 磁盘 IO 统计
- **WHEN** 管理员查看硬盘详情
- **THEN** 显示各分区的读写速率、IO 等待时间（通过 psutil.disk_io_counters 获取）

#### Scenario: 空间告警
- **WHEN** 某分区使用率超过 90%
- **THEN** 在仪表盘和硬盘标签页显示告警标识

### Requirement: 文件传输
系统 SHALL 提供客户端与服务端之间的文件上传和下载能力。

#### Scenario: 上传文件到客户端
- **WHEN** 管理员在文件管理器中选择文件并点击"上传"
- **THEN** 文件通过 WebSocket 二进制帧分块传输到客户端，客户端写入指定路径，Web 面板显示进度条

#### Scenario: 从客户端下载文件
- **WHEN** 管理员在文件管理器中选择文件并点击"下载"
- **THEN** 客户端读取文件并通过 WebSocket 二进制帧分块传输到服务端，服务端暂存后提供 HTTP 下载，Web 面板显示进度条

#### Scenario: 传输进度显示
- **WHEN** 文件正在传输
- **THEN** Web 面板显示进度百分比、已传输大小、传输速率、预估剩余时间

#### Scenario: 断点续传
- **WHEN** 文件传输因网络中断而失败
- **THEN** 管理员可重新发起传输，系统根据已传输的偏移量自动续传，而非从头开始

#### Scenario: 大文件处理
- **WHEN** 传输文件超过 100MB
- **THEN** 系统使用 1MB 分块传输，避免单帧过大导致 WebSocket 内存问题

#### Scenario: 传输取消
- **WHEN** 管理员点击"取消"按钮
- **THEN** 传输立即中止，客户端/服务端清理已写入的部分文件

### Requirement: 文件管理
系统 SHALL 提供对客户端文件系统的远程浏览和操作能力。

#### Scenario: 目录浏览
- **WHEN** 管理员在设备详情页点击"文件"标签
- **THEN** 显示客户端根目录（Windows 为各盘符，Linux/macOS 为 `/`）的文件列表，包含名称、大小、类型、修改时间、权限

#### Scenario: 进入子目录
- **WHEN** 管理员双击某目录
- **THEN** 进入该目录并显示其内容，导航栏更新路径

#### Scenario: 文件搜索
- **WHEN** 管理员在搜索框输入关键词
- **THEN** 客户端在当前目录递归搜索匹配文件名，返回结果列表

#### Scenario: 文件操作（重命名/删除/移动/复制）
- **WHEN** 管理员右键点击文件或选择文件后点击操作按钮
- **THEN** 对应操作在客户端执行，成功后刷新文件列表；删除操作需二次确认

#### Scenario: 文件排序与分类
- **WHEN** 管理员点击列标题
- **THEN** 文件列表按该列排序（名称/大小/类型/修改时间），支持升序/降序

#### Scenario: 文件权限查看
- **WHEN** 管理员查看文件详情
- **THEN** 显示文件权限信息（Windows: 只读/隐藏/系统属性；Linux: rwx 权限位）

#### Scenario: 路径导航
- **WHEN** 管理员在路径栏输入绝对路径并回车
- **THEN** 客户端切换到指定路径并显示文件列表；路径不存在时显示错误

## MODIFIED Requirements

### Requirement: 通信协议（MsgType 枚举扩展）
在原有 MsgType 枚举基础上新增：
- `CAMERA = "camera"` — 摄像头控制指令（列表/开启/关闭/参数调整/截图/录制）
- `CAMERA_DATA = "camera_data"` — 摄像头帧数据推送
- `DISK = "disk"` — 硬盘信息请求/响应
- `FILE_TRANSFER = "file_transfer"` — 文件传输控制（上传/下载/取消/续传）
- `FILE_TRANSFER_DATA = "file_transfer_data"` — 文件传输二进制数据块
- `FILE_MANAGER = "file_manager"` — 文件管理操作（浏览/搜索/重命名/删除/移动/复制）

### Requirement: 客户端 Handler 注册
`client/main.py` 需注册 4 个新 handler：handle_camera、handle_disk、handle_file_transfer、handle_file_manager

### Requirement: 服务端消息路由
`server/main.py` 的 `handle_client` 中需处理 CAMERA_DATA、FILE_TRANSFER_DATA 消息类型，通过事件回调转发到对应 WebSocket

### Requirement: Web 设备详情标签页
在原有 6 个远程控制标签页基础上新增 3 个：
- 摄像头（摄像头实时预览、切换、截图、录制）
- 硬盘（分区列表、趋势图、IO 统计）
- 文件（文件浏览器、上传/下载、文件操作）

## REMOVED Requirements
无
