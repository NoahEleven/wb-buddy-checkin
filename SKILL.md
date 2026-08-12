---
name: wb-buddy-checkin
description: 自动完成 WorkBuddy 桌面客户端「Buddy 加油站」每日签到、领取积分。当用户需要在 Windows 上自动点击头像→Buddy加油站→立即领取，并通过截图灰度校验是否成功（灰底「今日已领」）时使用。基于纯 ctypes 实现窗口置前、坐标点击与窗口截图，零第三方 Python 依赖，仅依赖 Windows 系统 API（可选复用 desktop-control-win skill 的截图）。
agent_created: true
---

# wb-buddy-checkin —— WorkBuddy 每日签到

在 Windows 上自动给 WorkBuddy 桌面客户端的「Buddy 加油站」签到领积分（每日 100 积分）。
脚本用相对坐标点击 + 截图灰度校验，无需 OCR，主题无关（亮/暗色都能正确判定）。

## 何时使用

- 用户说「自动签到」「每天领 WorkBuddy 积分」「Buddy 加油站签到」。
- 配置定时任务，让它在每天固定时间（如 9:00）自动跑。
- 注意：这是**通用、可分享**的实现，**不包含任何个人身份、路径或通知目标**；若要把结果推送给某人（微信/钉钉等），由调用方在 skill 之外自行配置。

## 前置条件

- Windows 系统（脚本依赖 `ctypes.windll` / `user32` / `gdi32`）。
- Python 3（标准库即可，无需 `pip install` 任何包）。
- WorkBuddy 桌面客户端正在运行。
- 首次使用**必须校准坐标**（见 `references/calibration.md`），因为不同屏幕/布局下点击点不同。**这步跳过是移植后"只会点头像"的头号原因。**

## ⚠️ 移植给别人 / 第一次用：先做这件事

**先跑一次校准，再 `-run`**。脚本内置的坐标是作者屏幕的校准值，别人的屏幕八成对不上——头像在左下角还能蒙对，但加油站/领取位置一偏，后续点击全打空，看起来就像"只点了头像"。

校准有两种，**推荐用弹窗校准（通用、傻瓜、零依赖）**：

```bash
# 弹窗校准（推荐）：自动弹出一个悬浮窗，按提示把鼠标移到三个目标点，
# 每步倒计时结束自动记录，三步写 calibrate.json。无需终端/微信/任何外部通道。
python scripts/wb_mouse_checkin.py -calibrate-gui
```

无 GUI 环境（如某些精简 Python 没带 tkinter）时，退而用终端文字校准：

```bash
# 终端校准：把鼠标依次移到 头像 / Buddy加油站 / 立即领取 三个点，各按一次回车
python scripts/wb_mouse_checkin.py -calibrate
```

校准后直接：

```bash
python scripts/wb_mouse_checkin.py -run
```

> 没校准就 `-run`，脚本会红字警告"用的是示例默认坐标，大概率打空"，并打印算出的三个屏幕坐标供你对照。

## 使用方法

脚本位于 `scripts/wb_mouse_checkin.py`，三种模式：

```bash
# 1) 干跑：打印窗口信息 + 计算好的点击坐标 + 校准状态告警，不点击
python scripts/wb_mouse_checkin.py

# 2) 真实签到（自动读取 calibrate.json；无则告警并退回示例坐标）
python scripts/wb_mouse_checkin.py -run

# 3) 弹窗校准（推荐）：悬浮窗倒计时自动采样鼠标，三步写 calibrate.json
python scripts/wb_mouse_checkin.py -calibrate-gui

# 3b) 终端校准（无 GUI 时）：鼠标移到三个目标点各按回车
python scripts/wb_mouse_checkin.py -calibrate
```

退出码：`0`=成功（已处于「今日已领」） / `2`=失败（未领取或面板异常，报错会指明该校准哪个点） / `3`=未找到 WorkBuddy 窗口。

结果截图保存在脚本同目录 `checkin_result.png`，可用于人工确认或后续通知。

## 关键实现要点（避免重踩坑）

1. **所有 Win32 调用必须显式声明 `argtypes`**，`HWND` 按 `c_void_p`（64 位指针）传，回调签名用 `WINFUNCTYPE(BOOL, HWND, c_void_p)`。不声明会被 ctypes 默认按 32 位 `c_int` 截断，导致 `SetForegroundWindow`/`EnumWindows` 静默失败——表现为「窗口没置顶、点击打空」。
2. **可靠置前 = 解决"窗口不在前台"**：最小化先 `ShowWindow(SW_RESTORE)`（恢复后验证 `GetWindowRect` 已脱离 -32000 幽灵坐标，最多重试 3 次）→ `AttachThreadInput` 线程绑定绕过系统前台锁 → `SetForegroundWindow`。**不要用 `SetWindowPos(HWND_TOP)` 钉死窗口位置**——WorkBuddy 会主动把它移回原位置/改尺寸（实测移到 (831,411) 之类），反而导致坐标全乱。
3. **窗口枚举必须精确匹配标题**：本机可能同时存在「WorkBuddy」(主窗口) 与「WorkBuddy - 个人中心 - xxx」等子窗口。`if TARGET_TITLE in buf.value` 子串匹配会命中 z 序最前的子窗口（可能是最小化/未显示的幽灵窗口）→ 所有点击打空。修复：`if title == TARGET_TITLE` 精确匹配优先，找不到再兜底子串匹配。
4. **坐标原点用 `GetWindowRect` 的 left/top，不用 `ClientToScreen`**：实测点击头像弹出菜单后 `ClientToScreen` 返回 2× 错误值（`GetWindowRect` 正常 (619,169) 时它返回 (1238,338)），导致全部坐标翻倍打空——这是 2026-08-04 的**真正根因**。WorkBuddy 是无边框窗口（`Chrome_WidgetWin_1`，客户区 = 整个窗口），客户区原点 = 窗口左上角，用 `GetWindowRect` 永远稳定。**窗口被移去哪坐标就跟随到哪，天然免疫"窗口不在前台/被移动"**，根本不需要钉窗。
5. **脚本开头设置 DPI 感知**：`SetProcessDpiAwareness(2)`（per-monitor DPI aware），失败则回退 `SetProcessDPIAware()`。避免 Windows DPI 虚拟化导致 GetWindowRect/SetCursorPos 坐标系不一致（备用保险）。
6. **坐标用「相对客户区左下角」**（x=距左, y=距底），窗口任意缩放都命中，校准一次永久复用。
7. **校验用「近黑像素数」而非白字数**：灰底「今日已领」按钮也含白字，不能靠白字判定；黑底「立即领取」有大量近黑像素（r,g,b<70），灰按钮近黑像素≈0。用此区分，主题无关。
8. **中段校验防假阳性（必须保留）**：点完「Buddy 加油站」后先截图，`verify_claimed` 要求按钮位置是**黑像素**（`unclaimed`，即面板已打开、黑底「立即领取」按钮存在）才继续点领取。否则若面板没打开，最终截图是 WorkBuddy 主界面，`verify_claimed` 会在按钮位置采样到主界面灰色背景误判 `claimed` → 假阳性签到成功。
9. **截图优先 desktop-control-win 的 `screen-info.ps1`**（若存在），否则回退 `PrintWindow` 客户区截图；`PNG` 编解码全用标准库手写（支持所有 filter），无外部依赖。
10. **幽灵矩形防御（2026-08-06）**：点完加油站后窗口可能短暂进入最小化/恢复动画态，`GetWindowRect` 返回 `(-32000,-32000,160x28)` 幽灵矩形，直接把坐标算飞（立即领取点到屏幕外）。检测到 `wr.left < -10000` 时先 `IsIconic → SW_RESTORE` 重读一次，仍异常则保留上次有效坐标不更新全局。
11. **防"撞用户操作"三件套（2026-08-12）**：定时任务在用户正用电脑时跑，脚本点击会和用户实时鼠标操作打架（用户反馈"你控制鼠标时我在用，移动不到正确位置"）。解法不是更用力抢鼠标（`SetCursorPos` 本来就能强制移动），而是：
    - **`wait_mouse_idle()`**：接管前纯读取鼠标位置（`GetCursorPos` 不碰鼠标）连续采样，静止 2s 才接管（最多等 60s 超时不阻塞）。用户在用电脑时安静等待，绝不抢。
    - **`announce_move()`**：点头像前鼠标「飞向目标 → 移开右上角 → 飞回目标」两次可见位移（各停 0.5s），用户看到鼠标自己动就知道脚本要操作了，提前松手。
    - **`click_at()` 点击前停顿 0.4s**：`SetCursorPos` 后多留反应时间。
    - 调用顺序：`wait_mouse_idle()` → `focus()` → `announce_move(sa,...)` → `click_at(*sa,...)`

## 配置定时任务（示例）

在 WorkBuddy 自动化里建一个每日任务，prompt 大致为：

> 运行 `python scripts/wb_mouse_checkin.py -run`（脚本内置：窗口精确匹配 + 最小化恢复置前 + 固定坐标点击 + 中段校验面板是否打开 + 灰度校验是否已领）。
> 读 `checkin_result.png` 确认结果：灰色「今日已领」=完成；黑底「立即领取」仍在=失败。
> 按你的通知偏好（微信/钉钉等）把结果发给本人。**通知目标和通道由你自己的配置决定，本 skill 不内置任何推送。**

cwd 设为该 skill 的 `scripts/` 所在目录（或脚本实际位置）。

## 参考

- 坐标校准与常见问题：`references/calibration.md`
