# 下载整理助手

一个适用于 **Windows 10 / 11** 的中文桌面小工具。将下载文件夹里的文件分类整理，先看预览，再确认移动，支持关闭软件后撤销。

## 使用方法

### 方式一：下载桌面程序

在 [GitHub Releases](https://github.com/zzy4664zz/-/releases) 下载 **DownloadOrganizer.exe**，双击运行，无需安装 Python。版本标签触发 Windows 构建，只有测试和打包检查通过后才会创建 Release；如果页面暂时没有程序，可先使用源码方式。

这是未签名的个人开源程序，Windows 可能显示 SmartScreen 提示。只从本仓库的 Release 下载，并核对同版本的 `SHA256SUMS.txt`；不要关闭系统保护。可用 PowerShell `Get-FileHash .\DownloadOrganizer.exe -Algorithm SHA256` 核对。

### 方式二：从源码运行

1. 安装 [Python 3.12 或更新版本](https://www.python.org/downloads/windows/)，保留安装器的 **Tcl/Tk** 选项。
2. 下载本仓库源码 ZIP，并**解压整个文件夹**。
3. 双击 `启动整理助手.bat`（或 `start.bat`）。不需要 `pip install`。

也可以在源码文件夹打开终端运行：

```powershell
py -3 main.py
```

## 整理流程

1. 默认选择 Windows 的下载文件夹，也可点击 **选择文件夹**。
2. 点击 **预览分类**，核对每个文件的分类和目标位置。
3. 点击 **开始整理** 并确认。文件移动到所选文件夹下的分类目录。
4. 不满意时点击 **撤销上次整理**；如果满意，点击 **保留结果** 清除该批撤销记录，再开始下一批。

| 分类 | 常见文件 |
| --- | --- |
| 图片 | JPG、PNG、GIF、WebP、HEIC、SVG |
| 文档 | PDF、Word、Excel、PPT、TXT、CSV、Markdown |
| 视频 | MP4、MKV、AVI、MOV、WebM |
| 音频 | MP3、WAV、FLAC、AAC、M4A |
| 压缩包 | ZIP、RAR、7Z、TAR、GZ |
| 安装包 | EXE、MSI、MSIX、APPX、ISO |
| 其他 | 未匹配上述扩展名的普通文件 |

## 文件保护与边界

- **预览不修改文件**。只整理当前层，不扫描子文件夹。
- 同名自动增加 `(1)`、`(2)`；移动和撤销都不覆盖已有文件。预览后文件发生变化会跳过。
- 跳过隐藏文件、符号链接、Windows 重解析点及 `.crdownload`、`.part`、`.tmp` 等未完成下载文件。
- 整理前保存操作记录。撤销前核对 SHA-256；已修改、丢失或原位置有冲突的文件会报告错误，保留记录供重试。
- 一次只保存**一批**可撤销记录。选择“保留结果”后，该批不能再通过本工具撤销。
- Windows 记录位置：`%LOCALAPPDATA%\DownloadOrganizer\last-operation.json`。运行 exe 和源码版共用这份记录。
- 意外退出后重新打开并点击撤销，可恢复已记录的操作；撤销不会删除新建的分类空文件夹。
- 大文件需要读取内容以保存校验值，操作可能较慢。不要同时下载、编辑或移动待整理文件；等待任务完成后再关闭软件。
- 文件被其他软件锁定、只读目录、网络盘和云同步目录可能导致部分操作失败。优先用于本机普通下载文件夹，先用少量副本试用。
- 文件和记录都留在本机，程序没有上传文件、自动联网或后台监控功能。

## 开发与测试

运行所有测试（Windows 包含真实 Tk 窗口测试）：

```powershell
py -3 -m unittest discover -s tests -v
py -3 main.py --smoke-test
```

Linux 图形测试需要显示服务；无显示时 GUI 集成测试会明确跳过，核心测试仍执行。详见 [验证说明](docs/TESTING.md)。

Windows 本机打包：

```powershell
py -3 -m pip install pyinstaller==6.16.0
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name DownloadOrganizer main.py
```

生成文件位于 `dist\DownloadOrganizer.exe`。GitHub Actions 在 Linux 和 Windows 上运行测试；推送 `v*` 标签会测试、打包并发布 Windows 程序。
