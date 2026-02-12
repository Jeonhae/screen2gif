# Screen2GIF — 软件设计文档 (SDD)

版本: 0.1
日期: 2026-02-02
作者: 自动生成

## 1. 概述
本项目实现一个桌面截屏转 GIF 的工具，主要流程：用户触发截图 → 进入选区录制模式 → 开始录制选区内容 → 停止并导出 MP4 → 转 GIF → 复制结果到剪贴板并提示用户。

目标平台：Windows（优先），可扩展到 macOS/Linux。

主要用户场景：快速录制屏幕局部为短动画并粘贴到聊天/文档中。

## 2. 需求摘要
- 录制模式：叠加 60% 透明黑色遮罩与顶部快捷工具栏。
- 选区交互：鼠标拖拽绘制矩形，释放后显示 8 个可拖拽控制点以调整选区。
- 开始/停止：点击“开始”后切换为“停止”，开始按指定帧率捕获选区。
- 视觉提示：录制时选区边框以红色闪烁显示。
- 输出：停止后保存 MP4（./video/{timestamp}.mp4），再转换为同名 GIF（./gif/{timestamp}.gif）。
- 剪贴板：尝试把 GIF 复制到剪贴板（优先写入 GIF 数据；若不可行，则写入文件路径或第一帧位图），弹出提示对话框。

非功能性需求：性能优先，低延迟，内存可控，错误可恢复并向用户给出信息。

## 3. 系统架构（高层）

- GUI 层：Overlay（遮罩选区）、ToolBar（工具栏）、主控制窗口/托盘交互。
- 录制层：ScreenRecorder（捕获线程/进程、帧队列、编码/持久化）。
- 后处理层：MP4 编码（OpenCV）或直接由帧写 MP4 → 调用 ffmpeg 转 GIF。
- 平台集成：剪贴板写入（pywin32 / ctypes）、权限提示。

组件通信方式：Qt 信号/槽或事件回调，录制使用线程 + queue 进行帧传递。

## 4. 目录结构

建议目录：

```
screen2gif/
├── main.py            # 启动脚本（托盘/命令行入口）
├── overlay.py         # 遮罩与选区交互窗口
├── toolbar.py         # 小型工具栏（开始/停止/取消）
├── recorder.py        # 屏幕捕获、帧队列、写入 MP4
├── converter.py       # 使用 ffmpeg 或 imageio 将 MP4 转 GIF
├── clipboard.py       # 剪贴板写入工具（Windows 特定实现）
├── utils.py           # 时间戳、路径管理等
├── video/             # 保存 MP4
├── gif/               # 保存 GIF
└── resources/         # 图标、样式等
```

## 5. 关键模块设计

### 5.1 `OverlayWindow` (QWidget)
职责：显示 60% 黑色遮罩、绘制并管理选区与控制点，响应鼠标交互。

主要属性：
- `selection_rect: QRect | None` 当前选区
- `control_handles: list[QRect]` 8 个控制点区域
- `dragging_handle: int | None` 当前拖拽的控制点（或 -1 表示整体移动）
- `is_recording: bool`

主要方法/事件：
- `paintEvent(event)`: 绘制遮罩、镂空选区、控制点、录制时闪烁边框
- `mousePressEvent(e)`, `mouseMoveEvent(e)`, `mouseReleaseEvent(e)`: 处理绘制与控制点拖拽
- `update_control_points()`: 计算 8 点坐标
- `get_selection() -> QRect`: 返回当前选区（像素坐标）

可实现细节：在 paintEvent 中用透明路径（QPainter.setCompositionMode）将选区“挖出”。控制点大小约 6x6 像素。

### 5.2 `ToolBar` (QWidget / QMainWindow)
职责：显示“开始/停止/取消”按钮，接收用户点击并发出信号。

信号：`start_requested()`, `stop_requested()`, `cancel_requested()`。

### 5.3 `ScreenRecorder` (QObject)
职责：在后台以固定帧率捕获选区帧并写入队列；负责将帧编码为 MP4 文件（或将帧序列交给转换器）。

实现要点：
- 使用 `mss` 进行屏幕抓取（高性能）；返回 BGRA 或 RGB 数组
- 捕获线程使用 `threading.Thread`，帧通过 `queue.Queue(maxsize=N)` 传输
- 采用 OpenCV `VideoWriter` 写 MP4，或先缓存到临时目录再合成
- 提供 `start(rect: QRect, fps: int)`, `stop()` 接口
- 发出信号：`recording_started()`, `recording_stopped(mp4_path)`

内存控制：队列满时可丢帧或阻塞（优先选择丢帧并记录统计）。

### 5.4 `converter.py`
职责：把 MP4 转为 GIF（优先使用 ffmpeg 命令行以保证质量与速度）。

示例命令：
```
ffmpeg -y -framerate {fps} -i {mp4} -vf "fps={fps},scale={w}:{h}:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 {gif}
```
如用户未安装 ffmpeg，可回退到 `imageio.mimsave`（慢且内存占用高）。

### 5.5 `clipboard.py`（Windows-specific）
职责：将 GIF 文件作为“文件对象”写入剪贴板，即使用 CF_HDROP 格式。

## 6. 数据流与序列（简化）

1. 用户触发：`main` → 显示 `OverlayWindow` + `ToolBar`。
2. 用户绘制 `selection_rect`。
3. 用户点击 `start`：`ToolBar` 发 `start_requested()` → `MainApp` 调用 `ScreenRecorder.start(rect, fps)`。
4. `ScreenRecorder` 在后台抓取帧并写入 `VideoWriter` 或临时帧缓存。
5. 用户点击 `stop`：`ScreenRecorder.stop()` → 写入最终 MP4 path。
6. `MainApp` 调用 `converter.convert(mp4_path)` 生成 GIF。
7. `clipboard.copy_gif_to_clipboard(gif_path)`。
8. `MainApp` 弹窗提示用户并返回空闲状态。

## 7. 错误处理与回退策略

- 捕获权限/抓屏失败：提示用户（权限不足时引导至设置），放弃录制并清理临时资源。
- 磁盘空间不足：在写入前检查可用空间，若不足，提示并中止。
- ffmpeg 不可用：回退到 `imageio` 实现并提示性能差异。
- 剪贴板写入失败：写入 GIF 文件路径到剪贴板并告知用户位置。
- 异常日志记录：所有关键操作在本地记录到 `logs/`，包含时间、错误栈与简短用户可读消息。

## 8. 性能考虑

- 使用 `mss` 进行高效抓取；使用线程避免阻塞 UI 主线程。
- 避免在内存中保存大量帧；优先写入临时文件或直接写 `VideoWriter`。
- 限制最大捕获分辨率与默认帧率（建议默认 10–15 fps），并允许用户配置。
- 在高清分辨率下自动降低帧率或缩放以控制 GIF 大小。

## 9. 测试计划

- 单元测试：核心 util（时间戳、路径）、converter 接口（用小样例视频）、clipboard 单元行为（模拟）。
- 集成测试：从绘制选区到最终 GIF 生成的端到端流程（在受控环境中），检测文件存在、大小与形式。
- 手工验收：在目标应用（微信、Word、浏览器）中粘贴 GIF，检查动画保真度。
- 性能测试：在 1080p 与 4K 屏幕上测量 CPU/内存占用、落帧率与 GIF 生成时间。

## 10. 部署与打包

- Windows 打包建议：使用 PyInstaller，将 `ffmpeg.exe` 一并打包或要求用户安装 ffmpeg 并将其列入 PATH。
- 需要包含 `pywin32`、`mss`、`opencv-python`、`imageio` 等依赖。

## 11. 里程碑建议（MVP）
1. 实现 `OverlayWindow` 与 `ToolBar`，支持绘制与调整选区。
2. 实现 `ScreenRecorder`（mss 抓取 + VideoWriter 写 MP4）。
3. 实现 `converter`（使用 ffmpeg），并保存 GIF。
4. 实现简单的 `clipboard`：先写入 GIF 文件路径并提示。
5. 优化：剪贴板 GIF 数据写入、拖动控制点优化、异常/日志完善。

## 12. 其他备注

- 剪贴板方案在不同应用间行为差异很大，应在文档中明确支持和已测试的目标应用。
- 考虑在设置中提供导出质量（分辨率、帧率、色彩）与文件大小估算。

---
文档生成于本地自动化流程，若需把此 `SDD.md` 转为 `SDD.txt` 或 `SDD.pdf`，我可继续处理。
