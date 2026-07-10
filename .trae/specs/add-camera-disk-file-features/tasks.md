# Tasks

- [x] Task 1: 扩展通信协议层
  - [x] 1.1 在 `common/protocol.py` 的 MsgType 枚举中新增 6 个消息类型：CAMERA、CAMERA_DATA、DISK、FILE_TRANSFER、FILE_TRANSFER_DATA、FILE_MANAGER
  - [x] 1.2 验证所有现有消息类型不受影响

- [x] Task 2: 实现客户端摄像头模块
  - [x] 2.1 创建 `client/handlers/camera.py`，实现 handle_camera 异步处理函数
  - [x] 2.2 实现 `list` action：使用 cv2.VideoCapture 枚举可用摄像头列表（索引 0-9），返回设备名和索引
  - [x] 2.3 实现 `open` action：打开指定索引摄像头，设置分辨率/帧率参数，启动后台帧推送任务
  - [x] 2.4 实现 `close` action：关闭摄像头，停止帧推送任务
  - [x] 2.5 实现帧推送循环：从 VideoCapture 读取帧 → JPEG 编码 → base64 → CAMERA_DATA 消息 → engine.send_msg
  - [x] 2.6 实现 `capture` action：截取当前帧返回高画质 JPEG
  - [x] 2.7 实现 `record_start` / `record_stop` action：使用 cv2.VideoWriter 写入临时文件，停止后返回文件路径供下载
  - [x] 2.8 处理摄像头异常：无设备/权限拒绝/被占用 → 返回 ERROR 消息
  - [x] 2.9 在 `client/main.py` 中注册 CAMERA 和 CAMERA_DATA handler

- [x] Task 3: 实现客户端硬盘监控模块
  - [x] 3.1 创建 `client/handlers/disk.py`，实现 handle_disk 异步处理函数
  - [x] 3.2 实现 `list` action：使用 psutil.disk_partitions() + psutil.disk_usage() 返回分区列表（盘符/挂载点、文件系统、总/已用/可用空间、使用率）
  - [x] 3.3 实现 `io_stats` action：使用 psutil.disk_io_counters(perdisk=True) 返回各磁盘读写速率和 IO 时间
  - [x] 3.4 在 `client/main.py` 中注册 DISK handler

- [x] Task 4: 实现客户端文件传输模块
  - [x] 4.1 创建 `client/handlers/file_transfer.py`，实现 handle_file_transfer 异步处理函数
  - [x] 4.2 实现 `upload` action：接收服务端发来的二进制数据块（通过 FILE_TRANSFER_DATA），写入客户端指定路径
  - [x] 4.3 实现 `download` action：读取客户端文件，分块（1MB）发送 FILE_TRANSFER_DATA 到服务端
  - [x] 4.4 实现进度上报：每个数据块发送/接收后，上报已传输字节数和总字节数
  - [x] 4.5 实现断点续传：upload/download 支持从指定 offset 开始传输
  - [x] 4.6 实现 `cancel` action：中止传输，清理临时文件
  - [x] 4.7 在 `client/main.py` 中注册 FILE_TRANSFER 和 FILE_TRANSFER_DATA handler

- [x] Task 5: 实现客户端文件管理模块
  - [x] 5.1 创建 `client/handlers/file_manager.py`，实现 handle_file_manager 异步处理函数
  - [x] 5.2 实现 `list` action：列出指定目录的文件和子目录，返回名称、大小、类型、修改时间、权限属性
  - [x] 5.3 实现 `roots` action：返回根目录列表（Windows: 盘符列表；Linux/macOS: "/"）
  - [x] 5.4 实现 `search` action：递归搜索当前目录下匹配关键词的文件，限制搜索深度和结果数量
  - [x] 5.5 实现 `rename` action：重命名文件/目录
  - [x] 5.6 实现 `delete` action：删除文件/目录（目录递归删除，需二次确认由 Web 端处理）
  - [x] 5.7 实现 `move` action：移动文件/目录到目标路径
  - [x] 5.8 实现 `copy` action：复制文件/目录到目标路径
  - [x] 5.9 实现 `info` action：返回文件详细信息（权限、属性、大小）
  - [x] 5.10 在 `client/main.py` 中注册 FILE_MANAGER handler

- [x] Task 6: 实现服务端摄像头 API 与 WebSocket 路由
  - [x] 6.1 在 `server/api/remote.py` 中添加摄像头 WebSocket 全局映射（_camera_ws_map）和事件回调
  - [x] 6.2 实现 WS `/api/devices/<client_id>/camera/ws`：摄像头帧实时流代理（类似终端代理模式）
  - [x] 6.3 实现 GET `/api/devices/<client_id>/camera/list`：获取摄像头列表
  - [x] 6.4 实现 POST `/api/devices/<client_id>/camera/capture`：截图请求
  - [x] 6.5 实现 POST `/api/devices/<client_id>/camera/record/start` 和 `/record/stop`：录制控制
  - [x] 6.6 在 `server/main.py` 的 handle_client 中添加 CAMERA_DATA 消息路由到事件回调

- [x] Task 7: 实现服务端硬盘监控 API
  - [x] 7.1 在 `server/api/remote.py` 中实现 GET `/api/devices/<client_id>/disk`：获取分区列表
  - [x] 7.2 实现 GET `/api/devices/<client_id>/disk/io`：获取磁盘 IO 统计
  - [x] 7.3 在 `server/client_manager.py` 中添加磁盘空间告警逻辑：使用率超 90% 时触发 alert 事件

- [x] Task 8: 实现服务端文件传输与文件管理 API
  - [x] 8.1 在 `server/api/remote.py` 中添加文件传输 WebSocket 全局映射（_file_transfer_ws_map）和事件回调
  - [x] 8.2 实现 WS `/api/devices/<client_id>/file-transfer/ws`：文件传输双向代理
  - [x] 8.3 在 `server/main.py` 的 handle_client 中添加 FILE_TRANSFER_DATA 消息路由到事件回调
  - [x] 8.4 实现 GET `/api/devices/<client_id>/files`：文件列表（转发到客户端 FILE_MANAGER handler）
  - [x] 8.5 实现 GET `/api/devices/<client_id>/files/roots`：根目录列表
  - [x] 8.6 实现 POST `/api/devices/<client_id>/files/search`：文件搜索
  - [x] 8.7 实现 POST `/api/devices/<client_id>/files/rename`、`/delete`、`/move`、`/copy`、`/info`：文件操作

- [x] Task 9: 实现 Web 前端摄像头标签页
  - [x] 9.1 在 `templates/index.html` 的 tab-bar 中添加"摄像头"标签
  - [x] 9.2 创建摄像头标签页 UI：摄像头选择下拉框、分辨率/帧率选择、开始/停止预览按钮、截图按钮、录制按钮
  - [x] 9.3 实现摄像头 WebSocket 连接：连接 /camera/ws，接收 base64 帧数据并更新 <img> src
  - [x] 9.4 实现摄像头列表加载和切换
  - [x] 9.5 实现截图下载功能
  - [x] 9.6 实现录制开始/停止和视频下载功能
  - [x] 9.7 实现异常状态提示（无摄像头、权限拒绝等）

- [x] Task 10: 实现 Web 前端硬盘标签页
  - [x] 10.1 在 `templates/index.html` 的 tab-bar 中添加"硬盘"标签
  - [x] 10.2 创建硬盘标签页 UI：分区卡片列表（盘符、文件系统、总/已用/可用、使用率进度条、告警标识）
  - [x] 10.3 实现 IO 统计展示：读写速率、IO 等待时间
  - [x] 10.4 实现存储趋势折线图：使用 Canvas 绘制最近 30 分钟的使用率变化
  - [x] 10.5 实现自动刷新：每 60 秒采集一次数据，折线图追加数据点

- [x] Task 11: 实现 Web 前端文件标签页
  - [x] 11.1 在 `templates/index.html` 的 tab-bar 中添加"文件"标签
  - [x] 11.2 创建文件浏览器 UI：路径导航栏、文件表格（名称/大小/类型/修改时间/权限）、操作按钮
  - [x] 11.3 实现目录浏览：加载文件列表、双击进入子目录、面包屑导航
  - [x] 11.4 实现路径栏输入：输入绝对路径切换目录
  - [x] 11.5 实现文件搜索
  - [x] 11.6 实现文件操作：重命名/删除/移动/复制按钮和对话框
  - [x] 11.7 实现文件上传：选择本地文件 → 通过 WebSocket 分块传输 → 显示进度条
  - [x] 11.8 实现文件下载：点击下载 → 通过 WebSocket 接收 → 提供 HTTP 下载链接 → 显示进度条
  - [x] 11.9 实现传输取消和断点续传重试
  - [x] 11.10 实现文件列表排序（按名称/大小/类型/修改时间）

- [x] Task 12: 更新依赖与构建脚本
  - [x] 12.1 在客户端依赖中添加 opencv-python、numpy
  - [x] 12.2 更新 `build_client.bat` 确保打包时包含新依赖的隐藏导入

# Task Dependencies
- Task 1 → Task 2, Task 3, Task 4, Task 5（协议层是所有模块的前置依赖）
- Task 2 → Task 6（客户端摄像头是服务端 API 的前置依赖）
- Task 3 → Task 7（客户端硬盘是服务端 API 的前置依赖）
- Task 4 + Task 5 → Task 8（文件传输+文件管理客户端是服务端 API 的前置依赖）
- Task 6 → Task 9（服务端摄像头 API 是前端的前置依赖）
- Task 7 → Task 10（服务端硬盘 API 是前端的前置依赖）
- Task 8 → Task 11（服务端文件 API 是前端的前置依赖）
- Task 2-8 → Task 12（所有模块完成后更新构建脚本）

# Parallelizable Work
- Task 2（摄像头客户端）与 Task 3（硬盘客户端）与 Task 4（文件传输客户端）与 Task 5（文件管理客户端）可并行
- Task 6（摄像头 API）与 Task 7（硬盘 API）与 Task 8（文件 API）可并行
- Task 9（摄像头前端）与 Task 10（硬盘前端）与 Task 11（文件前端）可并行
