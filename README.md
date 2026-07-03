# WinConsole - Windows 远程控制面板

一个基于 Flask 的 Windows 远程控制工具，提供 Web 界面进行远程管理和监控。

## 功能特性

- 📸 **屏幕监控** - 实时屏幕截图，支持自动刷新和手动截屏
- 🔧 **进程管理** - 查看、搜索、排序进程列表，支持结束进程
- 💻 **远程终端** - 通过 WebSocket 实时交互的 cmd.exe 终端
- 🖱️ **鼠标控制** - 移动、点击、双击、右键、滚动、拖拽
- ⌨️ **键盘控制** - 文本输入、单键按下、组合热键
- 🎹 **按键记录** - 实时键盘输入监控和记录

## 快速开始

### 直接运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
python app.py
```

启动后访问：`http://127.0.0.1:9081`

### 编译为 EXE

```bash
# 运行构建脚本
build.bat
```

生成的可执行文件位于 `dist/WinConsole.exe`

## 使用方式

### 基本命令

```bash
# 启动服务
WinConsole.exe

# 添加开机自启动
WinConsole.exe --install

# 移除开机自启动
WinConsole.exe --uninstall

# 指定端口
WinConsole.exe --port 8080
```

### 环境变量配置

- `WINC_HOST` - 监听地址（默认：0.0.0.0）
- `WINC_PORT` - 监听端口（默认：9081）
- `WINC_INTERVAL` - 截屏间隔秒数（默认：3）
- `WINC_LOG_DIR` - 日志目录（默认：~/.winconsole）

## 界面说明

启动后通过浏览器访问控制面板，左侧导航栏包含：

1. **屏幕** - 实时查看远程桌面截图
2. **进程** - 管理系统进程，支持按 CPU/内存/名称/PID 排序
3. **终端** - 实时交互的命令行终端（基于 xterm.js）
4. **鼠标** - 控制鼠标移动、点击、滚动等操作
5. **键盘** - 发送文本、按键和组合键
6. **按键记录** - 实时监控键盘输入

## 技术栈

- **后端**: Flask + Flask-Sock (WebSocket)
- **前端**: 纯 HTML/CSS/JavaScript + xterm.js
- **依赖库**:
  - psutil - 进程管理
  - pyautogui - 鼠标键盘控制
  - pynput - 键盘监听
  - Pillow - 截图和图像处理
  - pystray - 系统托盘图标

## 注意事项

⚠️ **安全警告**：此工具提供远程控制功能，请谨慎使用：

- 仅在可信网络环境中使用
- 建议配置防火墙限制访问
- 不要在公网环境暴露服务端口
- 适用于本地开发、测试、远程管理个人设备等场景

## 日志文件

运行日志保存在：`%USERPROFILE%\.winconsole\winconsole.log`

## 系统要求

- Windows 操作系统
- Python 3.7+（如直接运行）
- 管理员权限（部分功能如进程管理可能需要）

## 许可证

MIT License

## 作者

moyefu