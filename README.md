# Port Manager

Windows 端口可视化管理工具。替代 `netstat + findstr + taskkill` 命令行操作，提供图形界面查看端口占用、搜索过滤、一键终止进程。

![light-theme](https://img.shields.io/badge/theme-light-blue) ![python](https://img.shields.io/badge/python-3.8+-green) ![platform](https://img.shields.io/badge/platform-Windows-lightgrey)

## 功能

- **端口列表** — 显示所有 TCP/UDP 连接（协议、地址、端口、状态、PID、进程名）
- **实时搜索** — 输入端口号、PID 或进程名即时过滤，搜索关键字高亮
- **列排序** — 点击表头按任意列排序
- **一键 Kill** — 每行 Kill 按钮，带确认弹窗，终止占用端口的进程
- **自动刷新** — 可开启 3 秒自动刷新
- **快捷键** — `Ctrl+R` 刷新，`Ctrl+F` 聚焦搜索，`Esc` 清空搜索

## 快速开始

### 方式一：直接运行 Python 脚本

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python port_manager.py
```

### 方式二：使用打包好的 .exe

下载 `dist/PortManager.exe`，双击运行即可，无需 Python 环境。

> Kill 进程需要权限，建议右键「以管理员身份运行」。

## 打包 .exe

```bash
# 安装打包工具
pip install pyinstaller

# 打包为单文件 exe（带图标）
pyinstaller --onefile --windowed --name PortManager --icon=icon.ico port_manager.py
```

生成的 `.exe` 在 `dist/PortManager.exe`。

## 技术栈

- **Python** — 后端逻辑
- **pywebview** — 原生桌面窗口（基于 Edge WebView2）
- **netstat** — 获取端口连接数据
- **psutil** — 获取进程名、终止进程
- **PyInstaller** — 打包为 .exe
