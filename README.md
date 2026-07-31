# wb-buddy-checkin

自动完成 **WorkBuddy 桌面客户端**「Buddy 加油站」每日签到、领取 100 积分的 Windows 脚本。

无需 OCR、主题无关（亮色/暗色都能正确判定），纯 `ctypes` 调用 Windows 系统 API，
**零第三方 Python 依赖**，自带悬浮窗/终端两种校准方式。

---

## ✨ 特性

- 🖱️ **纯系统 API**：窗口置前、坐标点击、窗口截图全部用 `user32`/`gdi32`/`kernel32`，不装任何包。
- 🎯 **坐标自适应**：用「相对客户区左下角」定位，窗口任意缩放都命中，校准一次长期复用。
- 🪟 **三种校准**（见下）：弹窗悬浮窗（推荐）、终端交互、改代码常量。
- 🌗 **主题无关校验**：用「近黑像素数」区分黑底「立即领取」与灰底「今日已领」，亮/暗色都正确。
- 🔒 **零隐私绑定**：脚本不含任何个人身份、绝对路径或通知目标，可直接分享给任何人。

---

## 📦 安装

```bash
# 方式一：从 GitHub 克隆
git clone https://github.com/NoahEleven/wb-buddy-checkin.git
cp -r wb-buddy-checkin ~/.workbuddy/skills/

# 方式二：直接把整个 skill 目录放进 ~/.workbuddy/skills/
```

放进 `~/.workbuddy/skills/` 后，WorkBuddy 会自动识别为可用 skill。

---

## 🚀 快速开始

> ⚠️ **第一次用必须先校准**，否则脚本用的是内置示例坐标，后续点击会打空（看起来像"只点头像"）。

```bash
cd ~/.workbuddy/skills/wb-buddy-checkin

# 1) 校准（推荐弹窗方式）
python scripts/wb_mouse_checkin.py -calibrate-gui

# 2) 签到
python scripts/wb_mouse_checkin.py -run
```

---

## 🎯 校准（移植给别人 / 第一次用的必做项）

脚本内置的坐标是**作者屏幕的占位示例**，别人的屏幕大概率对不上。校准会读取你鼠标的真实位置并保存到 `calibrate.json`，`-run` 自动读取覆盖默认坐标。

### 方法一：弹窗校准（推荐，最省事）

```bash
python scripts/wb_mouse_checkin.py -calibrate-gui
```

脚本弹出一个**右上角半透明悬浮窗**，显示当前步骤、实时鼠标坐标和倒计时，每步倒计时结束**自动采样**鼠标位置，三步写 `calibrate.json`：

1. **头像**：鼠标移到左下角【头像】→ 保持不动，倒计时结束自动记录。
2. **Buddy 加油站**：点开头像菜单，鼠标移到菜单里的【Buddy 加油站】项 → 保持不动，自动记录。
3. **立即领取**：点开加油站打开积分面板，鼠标移到【立即领取】按钮 → 保持不动，自动记录。

> 依赖 Python 标准库 `tkinter`（绝大多数 Windows Python 自带）。没有 tkinter 时脚本会提示改用方法二。

### 方法二：终端校准（无 GUI 时）

```bash
python scripts/wb_mouse_checkin.py -calibrate
```

把鼠标移到三个目标点，各按一次回车，坐标自动记录。

---

## 🔧 其他命令

```bash
python scripts/wb_mouse_checkin.py            # 干跑：打印窗口信息 + 计算坐标 + 校准状态，不点击
python scripts/wb_mouse_checkin.py -run       # 真实签到
python scripts/wb_mouse_checkin.py -calibrate-gui   # 弹窗校准
python scripts/wb_mouse_checkin.py -calibrate      # 终端校准
python scripts/wb_mouse_checkin.py -sample         # 即时采样当前鼠标位置（调试用）
```

**退出码**：`0`=成功（已处于「今日已领」） / `2`=失败（未领取或面板异常，报错会指明该校准哪个点） / `3`=未找到 WorkBuddy 窗口。

结果截图保存在脚本同目录 `checkin_result.png`。

---

## ⏰ 配置定时任务

在 WorkBuddy 自动化里建一个每日任务，prompt 大致为：

> 运行 `python scripts/wb_mouse_checkin.py -run`（脚本内置窗口置前与灰度校验）。
> 读 `checkin_result.png` 确认结果：灰色「今日已领」= 完成；黑底「立即领取」仍在 = 失败。
> 按你的通知偏好（微信/钉钉等）把结果发给本人。

cwd 设为该 skill 的 `scripts/` 所在目录。

---

## 🛠️ 关键实现要点（避免重踩坑）

1. **Win32 调用必须显式声明 `argtypes`**，`HWND` 按 `c_void_p`（64 位指针）传。不声明会被 ctypes 默认按 32 位 `c_int` 截断，导致 `SetForegroundWindow` 静默失败——表现为「窗口没置顶、点击打空」。本脚本已统一声明。
2. **可靠置前三步**：最小化先 `ShowWindow(SW_RESTORE)` → `AttachThreadInput` 线程绑定绕过系统前台锁 → `SetWindowPos(HWND_TOP)` 置顶 z 序。
3. **坐标用「相对客户区左下角」**（x=距左, y=距底），窗口任意缩放都命中。
4. **校验用「近黑像素数」而非白字数**：灰底「今日已领」按钮也含白字，不能靠白字判定；黑底「立即领取」有大量近黑像素（r,g,b<70），灰按钮近黑像素≈0。
5. **截图优先 desktop-control-win 的 `screen-info.ps1`**（若存在），否则回退 `PrintWindow` 客户区截图；PNG 编解码全用标准库手写（支持所有 filter），无外部依赖。

---

## ❓ 常见问题

- **只会点头像 / 后续点击打空**：没校准，用的是默认示例坐标。先 `-calibrate-gui` 记录三个点。
- **点击打空 / 窗口没被置前**：Win32 调用未声明 `argtypes` 导致 HWND 被截断的典型症状，本脚本已修复。仍无效则确认 WorkBuddy 未被最小化到托盘且未被其他全屏窗口遮挡。
- **暗色主题误判**：校验用「近黑像素数」而非白字数，主题无关，亮/暗色都正确。
- **截图失败**：优先用 desktop-control-win，否则回退 `PrintWindow`；两者都失败则签到仍会执行但无法自动校验（退出码 2）。

---

## 🔒 隐私

本 skill **不包含任何个人身份信息、绝对路径或通知目标**。脚本只负责「签到 + 截图」，
若要把结果推送给某人，由调用方在 skill 之外自行配置通知通道。

---

## 📄 License

MIT
