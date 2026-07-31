#!/usr/bin/env python3
# wb_mouse_checkin.py  ——  WorkBuddy「Buddy 加油站」每日签到（自动领积分）
# ============================================================================
# 这是一个可分享、零第三方依赖的纯 ctypes 实现（仅依赖 Windows 系统 API + 标准库）。
# 鼠标点击 / 窗口置前 / 窗口截图 全部用 ctypes 完成；
# 若本机恰好装了 desktop-control-win skill，截图会优先用它（更稳），否则回退 PrintWindow。
#
# 【分享版 · 隐私说明】
#   本脚本不含任何个人身份信息、绝对路径或推送目标。所有坐标都是"相对客户区左下角"
#   的通用设计，第一次用请按自己屏幕校准（见下方 CALIBRATION 常量 与 references/calibration.md）。
#
# 用法:
#   python wb_mouse_checkin.py            # 干跑: 打印窗口信息 + 计算好的点击坐标, 不点击
#   python wb_mouse_checkin.py -run       # 执行真实签到
#   python wb_mouse_checkin.py -calibrate # 交互式校准(终端文字): 把鼠标移到三个目标点各按一次回车
#   python wb_mouse_checkin.py -calibrate-gui # 弹窗校准(推荐通用): 悬浮窗倒计时自动采样鼠标, 三步写 calibrate.json
#
# 退出码: 0=成功/已处于[今日已领]   2=失败(未领取/面板异常)   3=未找到 WorkBuddy 窗口
# ============================================================================

import ctypes, sys, time, zlib, struct, subprocess, os, json

if sys.platform != "win32":
    print("ERROR: 本脚本仅支持 Windows (依赖 ctypes.windll / user32 / gdi32)。")
    sys.exit(3)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# ============================== 配置区（按自己屏幕校准） ==============================
# 目标窗口标题（WorkBuddy 桌面客户端固定叫这个；若你的版本不同改这里）。
TARGET_TITLE = "WorkBuddy"

# 三个点击点统一用「相对客户区左下角」表示:
#   x = 距客户区左边缘的像素 (逻辑像素, 自动乘 DPI 缩放)
#   y = 距客户区底边缘的像素
# 这样窗口任意缩放(高/宽变化)都能命中, 校准一次永久复用。
# 校准方法见 references/calibration.md（或先 -calibrate 截一张图用画图量）。
# —— 以下为作者 1080p/常见布局的示例值, 你大概率需要改 ——
AVATAR_LEFT   = 94    # 左下角头像(账户菜单): 距左
AVATAR_BOTTOM = 41    #                     距底
GAS_LEFT      = 140   # "Buddy 加油站"菜单项: 距左
GAS_BOTTOM    = 541   #                     距底
CLAIM_LEFT    = 89    # "立即领取"按钮:      距左
CLAIM_BOTTOM  = 113   #                     距底

# 结果截图保存路径（默认脚本同目录）。
RESULT_NAME = "checkin_result.png"
# =============================================================================================


# ===================== 显式声明 Win32 调用签名（关键！） =====================
# HWND 是 64 位指针, 不声明 argtypes 会被 ctypes 默认按 32 位 c_int 截断,
# 导致 SetForegroundWindow 等静默失败(窗口置不了顶)。这是最容易踩的坑。
HWND  = ctypes.c_void_p
BOOL  = ctypes.c_bool
LONG  = ctypes.c_long
INT   = ctypes.c_int
UINT  = ctypes.c_uint
SHORT = ctypes.c_short

user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(BOOL, INT, INT), INT]
user32.EnumWindows.restype = BOOL
user32.GetWindowTextW.argtypes = [HWND, ctypes.c_wchar_p, INT]
user32.GetWindowTextW.restype = INT
user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowTextLengthW.restype = INT
user32.IsWindowVisible.argtypes = [HWND]
user32.IsWindowVisible.restype = BOOL
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = HWND
user32.GetWindowRect.argtypes = [HWND, ctypes.c_void_p]
user32.GetWindowRect.restype = BOOL
user32.GetClientRect.argtypes = [HWND, ctypes.c_void_p]
user32.GetClientRect.restype = BOOL
user32.ClientToScreen.argtypes = [HWND, ctypes.c_void_p]
user32.ClientToScreen.restype = BOOL
user32.IsIconic.argtypes = [HWND]
user32.IsIconic.restype = BOOL
user32.ShowWindow.argtypes = [HWND, INT]
user32.ShowWindow.restype = BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = HWND
user32.SetForegroundWindow.argtypes = [HWND]
user32.SetForegroundWindow.restype = BOOL
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(UINT)]
user32.GetWindowThreadProcessId.restype = UINT
user32.AttachThreadInput.argtypes = [UINT, UINT, BOOL]
user32.AttachThreadInput.restype = BOOL
user32.SetWindowPos.argtypes = [HWND, HWND, INT, INT, INT, INT, UINT]
user32.SetWindowPos.restype = BOOL
user32.SetCursorPos.argtypes = [INT, INT]
user32.SetCursorPos.restype = BOOL
user32.mouse_event.argtypes = [UINT, UINT, UINT, UINT, UINT]
user32.mouse_event.restype = None
user32.GetWindowDC.argtypes = [HWND]
user32.GetWindowDC.restype = HWND
user32.ReleaseDC.argtypes = [HWND, HWND]
user32.ReleaseDC.restype = INT
user32.PrintWindow.argtypes = [HWND, HWND, UINT]
user32.PrintWindow.restype = BOOL

gdi32.CreateCompatibleDC.argtypes = [HWND]
gdi32.CreateCompatibleDC.restype = HWND
gdi32.CreateCompatibleBitmap.argtypes = [HWND, INT, INT]
gdi32.CreateCompatibleBitmap.restype = HWND
gdi32.SelectObject.argtypes = [HWND, HWND]
gdi32.SelectObject.restype = HWND
gdi32.GetDIBits.argtypes = [HWND, HWND, UINT, UINT, ctypes.c_void_p, ctypes.c_void_p, UINT]
gdi32.GetDIBits.restype = INT
gdi32.DeleteObject.argtypes = [HWND]
gdi32.DeleteObject.restype = INT
gdi32.DeleteDC.argtypes = [HWND]
gdi32.DeleteDC.restype = INT

SW_RESTORE  = 9
HWND_TOP    = HWND(0)
SWP_NOMOVE  = 0x0002
SWP_NOSIZE  = 0x0001
PW_CLIENTONLY = 1  # PrintWindow 只画客户区

class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]
class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = BOOL
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", UINT), ("biWidth", INT), ("biHeight", INT),
                ("biPlanes", SHORT), ("biBitCount", SHORT), ("biCompression", UINT),
                ("biSizeImage", UINT), ("biXPelsPerMeter", INT), ("biYPelsPerMeter", INT),
                ("biClrUsed", UINT), ("biClrImportant", UINT)]

# ===================== 找 WorkBuddy 主窗口 =====================
_target = None
def _callback(hwnd, lparam):
    global _target
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    if TARGET_TITLE in buf.value:
        _target = hwnd
        return False
    return True

EnumWindowsProc = ctypes.WINFUNCTYPE(BOOL, INT, INT)
user32.EnumWindows(EnumWindowsProc(_callback), 0)
if not _target:
    _target = user32.FindWindowW(None, TARGET_TITLE)
if not _target:
    print(f"ERROR: 未找到标题含 '{TARGET_TITLE}' 的窗口 (请确认 WorkBuddy 正在运行)")
    sys.exit(3)

wr = RECT(); user32.GetWindowRect(_target, ctypes.byref(wr))
cr = RECT(); user32.GetClientRect(_target, ctypes.byref(cr))
o  = POINT(); user32.ClientToScreen(_target, ctypes.byref(o))
winW = wr.right - wr.left; winH = wr.bottom - wr.top
cliW = cr.right - cr.left; cliH = cr.bottom - cr.top
scaleX = winW / cliW if cliW else 1.0
scaleY = winH / cliH if cliH else 1.0

# ===================== 读取校准文件（若存在则覆盖默认坐标） =====================
# 移植给别人最易踩的坑: 直接 -run 会用下面这组【作者屏幕的示例默认坐标】,
# 头像在左下角位置稳还能蒙对, 但加油站/领取位置因布局不同而打空 -> 表现为"只点头像"。
# 解决办法: 先 -calibrate 交互记录, 存成本文件, 之后 -run 自动读取覆盖。
_calibrated = False
_CAL_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate.json")
if os.path.exists(_CAL_JSON):
    try:
        _d = json.load(open(_CAL_JSON, encoding="utf-8"))
        if isinstance(_d, dict):
            if "AVATAR" in _d:
                AVATAR_LEFT, AVATAR_BOTTOM = _d["AVATAR"]["left"], _d["AVATAR"]["bottom"]
            if "GAS" in _d:
                GAS_LEFT, GAS_BOTTOM = _d["GAS"]["left"], _d["GAS"]["bottom"]
            if "CLAIM" in _d:
                CLAIM_LEFT, CLAIM_BOTTOM = _d["CLAIM"]["left"], _d["CLAIM"]["bottom"]
            _calibrated = True
            print("[校准] 已读取 calibrate.json, 覆盖默认坐标")
    except Exception as e:
        print(f"[校准] 读取 calibrate.json 失败: {e} (使用默认示例坐标)")

def conv_bl(x_left, y_bottom):
    """相对客户区左下角 (x=距左, y=距底, 逻辑像素) -> 屏幕物理坐标。
       窗口任意缩放都命中: x 只跟左边缘有关, y 只跟底边缘有关。"""
    vx = x_left
    vy = cliH - y_bottom           # 距底 -> 距顶(客户区逻辑坐标)
    return int(o.x + vx * scaleX), int(o.y + vy * scaleY)

sa = conv_bl(AVATAR_LEFT, AVATAR_BOTTOM)    # 头像/账户菜单
sg = conv_bl(GAS_LEFT, GAS_BOTTOM)          # Buddy 加油站
sc = conv_bl(CLAIM_LEFT, CLAIM_BOTTOM)      # 立即领取按钮

def _print_coords():
    print("== WorkBuddy 窗口信息 ==")
    print(f"  窗口矩形: L={wr.left} T={wr.top}  {winW}x{winH}")
    print(f"  客户区:   {cliW}x{cliH}  (逻辑像素)")
    print(f"  DPI缩放:  X={scaleX:.2f} Y={scaleY:.2f}")
    print(f"  客户区左上角屏幕坐标: ({o.x}, {o.y})")
    print("== 点击坐标 (相对客户区左下角: x=距左, y=距底; 窗口缩放自适应) ==")
    print(f"  头像(账户菜单): {sa}   [距左{AVATAR_LEFT}, 距底{AVATAR_BOTTOM}]")
    print(f"  Buddy加油站:    {sg}   [距左{GAS_LEFT}, 距底{GAS_BOTTOM}]")
    print(f"  立即领取按钮:   {sc}   [距左{CLAIM_LEFT}, 距底{CLAIM_BOTTOM}]")
    print()

# ===================== 鼠标点击（纯 ctypes，可靠） =====================
def click_at(sx, sy, name):
    print(f">> 点击 {name} @ 屏幕 ({sx}, {sy})")
    user32.SetCursorPos(sx, sy)
    time.sleep(0.12)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    time.sleep(0.3)

# ===================== PNG 解码（stdlib，用于校验，支持所有 filter） =====================
def load_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8; w = h = color_type = 0; idat = b""
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+ln]
        if typ == b"IHDR":
            w, h, _, color_type = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    ch = 4 if color_type == 6 else 3
    stride = w * ch
    out = bytearray(w * h * ch)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i-ch]) & 0xff
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xff
        elif f == 3:
            for i in range(stride):
                a = line[i-ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xff
        elif f == 4:
            for i in range(stride):
                a = line[i-ch] if i >= ch else 0
                b = prev[i]; c = prev[i-ch] if i >= ch else 0
                pp = a + b - c
                pa = abs(pp-a); pb = abs(pp-b); pc = abs(pp-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xff
        out[y*stride:(y+1)*stride] = line
        prev = line
    return w, h, ch, out

# ===================== PNG 编码（stdlib，用于 PrintWindow 回退截图） =====================
def save_png(path, w, h, rgba):
    """rgba: 长度 w*h*4 的 bytes, top-down RGBA。"""
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)  # filter type 0 (None)
        raw += rgba[y*stride:(y+1)*stride]
    comp = zlib.compress(bytes(raw), 9)
    def chunk(typ, cdata):
        c = typ + cdata
        return struct.pack(">I", len(cdata)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit, color type 6 (RGBA)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", comp))
        f.write(chunk(b"IEND", b""))

# ===================== 截图：优先 desktop-control，回退 PrintWindow =====================
def _find_desktop_control_ps1():
    cand = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills",
                        "desktop-control-win", "scripts", "screen-info.ps1")
    return cand if os.path.exists(cand) else None

def _screenshot_pw(hwnd, out_path):
    """PrintWindow 抓客户区 -> PNG。成功返回 True。"""
    rc = RECT(); user32.GetClientRect(hwnd, ctypes.byref(rc))
    w = rc.right - rc.left; h = rc.bottom - rc.top
    if w <= 0 or h <= 0:
        return False
    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mem_dc, bmp)
    ok = user32.PrintWindow(hwnd, mem_dc, PW_CLIENTONLY)
    if not ok:
        gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem_dc); user32.ReleaseDC(hwnd, hwnd_dc)
        return False
    buf = ctypes.create_string_buffer(w * h * 4)
    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h          # 负 = top-down 输出, 省去翻转
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0
    got = gdi32.GetDIBits(mem_dc, bmp, 0, h, ctypes.cast(buf, ctypes.c_void_p),
                          ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem_dc); user32.ReleaseDC(hwnd, hwnd_dc)
    if not got:
        return False
    # BGRA -> RGBA
    rgba = bytearray(w * h * 4)
    for i in range(w * h):
        b = buf[i*4]; g = buf[i*4+1]; r = buf[i*4+2]; a = buf[i*4+3]
        rgba[i*4] = r; rgba[i*4+1] = g; rgba[i*4+2] = b; rgba[i*4+3] = a
    save_png(out_path, w, h, bytes(rgba))
    return os.path.exists(out_path)

def take_screenshot(hwnd, out_path):
    """截图窗口客户区到 out_path。优先 desktop-control, 否则 PrintWindow。"""
    ps = _find_desktop_control_ps1()
    if ps:
        try:
            env = dict(os.environ)
            env.pop("ACC_PRODUCT_CONFIG_V3", None)  # 防超大环境块撑爆 PowerShell Add-Type
            r = subprocess.run(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps,
                 "-Action", "screenshot", "-Target", TARGET_TITLE, "-OutputPath", out_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=env, timeout=60)
            if r.returncode == 0 and os.path.exists(out_path):
                return True
        except Exception:
            pass
    return _screenshot_pw(hwnd, out_path)

# ===================== 领取结果验证（定点采样，主题无关） =====================
# 领取位置只有两种终态:
#   - 未领取: 仍是黑底白字[立即领取]按钮 -> 按钮内大量**近黑像素**(r,g,b<70)
#   - 已领取: 变成灰底[今日已领]按钮      -> 近黑像素≈0, 但灰填充像素多(95~220 的灰)
# 用"近黑像素数"区分(灰按钮也有白字, 不能用白字数判定)。
# 屏幕->图像坐标按客户区原点 o + 客户区尺寸 cliW/cliH 换算, 自适应 DPI。
def verify_claimed(path, sx, sy, radius=22):
    """返回 'claimed' | 'unclaimed' | 'unknown'"""
    w, h, ch, buf = load_png(path)
    cw = cliW if cliW else w
    chh = cliH if cliH else h
    ix = int((sx - o.x) * w / cw)
    iy = int((sy - o.y) * h / chh)
    dark = gray = 0
    for dy in range(-radius, radius + 1, 2):
        for dx in range(-radius, radius + 1, 2):
            x, y = ix + dx, iy + dy
            if 0 <= x < w and 0 <= y < h:
                i = (y * w + x) * ch
                r, g, b = buf[i], buf[i+1], buf[i+2]
                if r < 70 and g < 70 and b < 70:
                    dark += 1
                elif abs(r-g) < 28 and abs(g-b) < 28 and 95 <= r <= 220:
                    gray += 1
    if dark >= 30:
        return "unclaimed"   # 黑按钮还在 -> 没领上
    if gray >= 60:
        return "claimed"     # 灰按钮 -> 已领
    return "unknown"         # 既不是黑也不是灰 -> 面板可能没正常打开

# ===================== 窗口置前（可靠三步） =====================
def focus():
    """可靠把目标窗口置前(最小化先恢复, 线程绑定绕过前台锁, z序置顶)。
       原实现漏了 argtypes 声明导致 HWND 截断、SetForegroundWindow 静默失败,
       是"窗口没在最上方"导致点击打空的真凶。"""
    hwnd = _target
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    if fg and fg != hwnd:
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        my_tid = kernel32.GetCurrentThreadId()
        if fg_tid and fg_tid != my_tid:
            user32.AttachThreadInput(fg_tid, my_tid, True)
        user32.SetForegroundWindow(hwnd)
        if fg_tid and fg_tid != my_tid:
            user32.AttachThreadInput(fg_tid, my_tid, False)
    else:
        user32.SetForegroundWindow(hwnd)
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    time.sleep(0.5)

# ===================== 运行前自检 =====================
def _preflight():
    """返回告警列表(空=无告警)。重点防止'用默认坐标直接跑'导致只点头像。"""
    warns = []
    if not _calibrated:
        warns.append("未检测到 calibrate.json, 当前用的是脚本内置【示例默认坐标】(作者屏幕校准值)。"
                     "若你的屏幕/布局不同, 点击基本会打空 —— 这正是最常见'只点头像'的原因!"
                     "请先运行 `python wb_mouse_checkin.py -calibrate` 交互校准一次。")
    for nm, (x, y) in [("头像", sa), ("加油站", sg), ("领取", sc)]:
        if not (o.x <= x <= o.x + winW and o.y <= y <= o.y + winH):
            warns.append(f"{nm} 计算坐标 ({x},{y}) 落在 WorkBuddy 窗口之外, 坐标严重偏移, 请重新校准。")
    return warns

# ===================== 主流程 =====================
def do_checkin():
    """执行签到。返回 (status, screenshot_path)
       status: 'success' | 'failed'
       流程: 头像->加油站->直接点领取位置, 只验证最终是否处于灰底[今日已领]。"""
    RESULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), RESULT_NAME)

    focus()
    click_at(*sa, "头像/账户菜单"); time.sleep(0.8)
    click_at(*sg, "Buddy 加油站"); time.sleep(1.6)
    click_at(*sc, "立即领取"); time.sleep(2.0)
    if not take_screenshot(_target, RESULT):
        print("== 截图失败, 无法校验 ==")
        return "failed", RESULT
    state = verify_claimed(RESULT, sc[0], sc[1])
    if state == "claimed":
        print("== 校验通过: 领取位置已是灰底[今日已领], 领取成功 ==")
        return "success", RESULT
    if state == "unclaimed":
        print("== 校验失败: 领取位置仍是黑底[立即领取], 没点中 ==")
        print(f"   → 面板已打开但[立即领取]按钮没点中, 请重新校准 CLAIM_LEFT/CLAIM_BOTTOM (当前 {CLAIM_LEFT}/{CLAIM_BOTTOM})")
        return "failed", RESULT
    print("== 校验异常: 领取位置既无黑按钮也无灰按钮 ==")
    print("   → 多半是【Buddy 加油站】菜单项没点中, 面板根本没打开 (或打开了但不在预期位置)。")
    print(f"     请重点重新校准 GAS_LEFT/GAS_BOTTOM (当前 {GAS_LEFT}/{GAS_BOTTOM}); 也可先 -calibrate 重新记录。")
    print(f"     参考坐标: 头像{sa}  加油站{sg}  领取{sc}")
    return "failed", RESULT

def do_sample():
    """即时采样: 把 WorkBuddy 置前, 读取当前鼠标屏幕坐标, 反算成[相对客户区左下角]
       的 left/bottom 并打印 JSON。不交互, 供外部(如微信分步引导)分步调用。"""
    focus()
    p = POINT(); user32.GetCursorPos(ctypes.byref(p))
    if cliW and cliH:
        rel_left = (p.x - o.x) / scaleX
        rel_topc = (p.y - o.y) / scaleY
        rel_bottom = cliH - rel_topc
        print(json.dumps({"screen": [p.x, p.y],
                          "left": round(rel_left, 1), "bottom": round(rel_bottom, 1)},
                         ensure_ascii=False))
        return 0
    print("ERROR: 窗口尺寸为0, 无法换算")
    return 2

def do_calibrate_gui():
    """弹窗校准(通用 GUI, 零依赖): tkinter 悬浮窗显示步骤 + 实时鼠标坐标 + 倒计时,
       每步自动采样鼠标位置, 三步写 calibrate.json。无需终端 / 微信 / 外部通道, 跨用户通用。
       无 GUI 环境(tkinter 缺失)时提示改用 -calibrate 终端文字版。"""
    try:
        import tkinter as tk
    except Exception:
        print("ERROR: 当前 Python 未安装 tkinter (GUI 库), 无法弹窗校准。")
        print("       请改用终端文字校准: python wb_mouse_checkin.py -calibrate")
        return 2
    OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate.json")
    steps = [
        ("第 1 步 / 共 3 步", "把鼠标移到左下角【头像】(账户菜单)\n移到后保持不动，倒计时结束自动记录", "AVATAR"),
        ("第 2 步 / 共 3 步", "点击头像展开菜单，把鼠标移到菜单里的【Buddy 加油站】\n移到后保持不动，倒计时结束自动记录", "GAS"),
        ("第 3 步 / 共 3 步", "点击加油站打开积分面板，把鼠标移到【立即领取】按钮\n移到后保持不动，倒计时结束自动记录", "CLAIM"),
    ]
    pts = {}
    focus()  # 先把 WorkBuddy 置前, 方便用户把鼠标移到目标
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)
    sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
    w, h = 384, 172
    root.geometry(f"{w}x{h}+{sw - w - 24}+{24}")   # 右上角, 不挡左下/中部的目标
    bg = "#1f4e79"
    title = tk.Label(root, text="", font=("Microsoft YaHei", 13, "bold"), fg="white", bg=bg)
    title.pack(fill="x", pady=(8, 2))
    hint = tk.Label(root, text="", font=("Microsoft YaHei", 11), fg="#e8eef5", bg=bg,
                    wraplength=344, justify="left")
    hint.pack(fill="x", padx=14, pady=(2, 6))
    cd = tk.Label(root, text="", font=("Microsoft YaHei", 30, "bold"), fg="#ffd966", bg=bg)
    cd.pack(pady=(0, 2))
    coord = tk.Label(root, text="", font=("Consolas", 10), fg="#a9c7e8", bg=bg)
    coord.pack(pady=(0, 8))

    def refresh_coord():
        p = POINT(); user32.GetCursorPos(ctypes.byref(p))
        coord.config(text=f"当前鼠标: ({p.x}, {p.y})")
        root.after(100, refresh_coord)

    def start_step(i):
        if i >= len(steps):
            finish()
            return
        nm, htext, key = steps[i]
        title.config(text=nm)
        hint.config(text=htext)
        cd.config(text="6")
        cnt = {"v": 6}
        def countdown():
            cd.config(text=str(cnt["v"]))
            if cnt["v"] <= 0:
                p = POINT(); user32.GetCursorPos(ctypes.byref(p))
                if cliW and cliH:
                    left = (p.x - o.x) / scaleX
                    bottom = cliH - (p.y - o.y) / scaleY
                    pts[key] = {"left": round(left, 1), "bottom": round(bottom, 1)}
                    print(f"[GUI校准] 记录 {key}: 距左 {pts[key]['left']}, 距底 {pts[key]['bottom']} (屏幕 {p.x},{p.y})")
                root.after(350, lambda: start_step(i + 1))
                return
            cnt["v"] -= 1
            root.after(1000, countdown)
        countdown()

    def finish():
        if pts:
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(pts, f, ensure_ascii=False, indent=2)
            title.config(text="✅ 校准完成")
            hint.config(text=f"已保存: {os.path.basename(OUT)}\n下次直接 -run 即可")
            cd.config(text="")
            coord.config(text=json.dumps(pts, ensure_ascii=False))
            root.after(2800, root.destroy)
        else:
            root.destroy()

    root.after(300, lambda: start_step(0))
    refresh_coord()
    root.mainloop()
    return 0

def do_calibrate():
    """交互式校准: 引导用户把鼠标移到三个目标点, 按回车记录真实屏幕坐标,
       自动换算成[相对客户区左下角]并保存到 calibrate.json (下次 -run 自动读取)。
       彻底免去'用画图量像素'的误差, 是移植后最稳的校准方式。"""
    OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate.json")
    steps = [
        ("AVATAR", "【步骤1】请让 WorkBuddy 在前台、账户菜单处于收起状态。\n         把鼠标移到左下角的【头像】上, 然后切到本终端按回车记录。"),
        ("GAS",    "【步骤2】点击头像展开账户菜单。把鼠标移到菜单里的【Buddy 加油站】项上,\n         切到本终端按回车记录。"),
        ("CLAIM",  "【步骤3】点击【Buddy 加油站】打开积分面板。把鼠标移到面板里的【立即领取】按钮上,\n         切到本终端按回车记录。"),
    ]
    pts = {}
    for key, prompt in steps:
        focus()
        print("\n" + prompt)
        input("         （移动鼠标到目标后，回车记录；Ctrl+C 取消）")
        p = POINT(); user32.GetCursorPos(ctypes.byref(p))
        if cliW and cliH:
            rel_left = (p.x - o.x) / scaleX
            rel_topc = (p.y - o.y) / scaleY
            rel_bottom = cliH - rel_topc
            pts[key] = {"left": round(rel_left, 1), "bottom": round(rel_bottom, 1)}
            print(f"         ✅ 记录 {key}: 距左 {pts[key]['left']}, 距底 {pts[key]['bottom']}  (屏幕 {p.x},{p.y})")
        else:
            print("         ❌ 窗口尺寸为0, 无法换算, 跳过")
    if pts:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(pts, f, ensure_ascii=False, indent=2)
        print(f"\n== 已保存校准到 {OUT} ==")
        print("   下次直接 `python wb_mouse_checkin.py -run` 即可, 脚本自动读取此文件覆盖默认坐标。")
        try:
            take_screenshot(_target, os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate_ref.png"))
            print("   参考截图已存 calibrate_ref.png")
        except Exception:
            pass
        return 0
    print("== 未记录到任何点 ==")
    return 2

# ===================== 入口 =====================
if __name__ == "__main__":
    if "-sample" in sys.argv:
        _print_coords()
        sys.exit(do_sample())

    if "-calibrate-gui" in sys.argv:
        _print_coords()
        sys.exit(do_calibrate_gui())

    if "-calibrate" in sys.argv:
        _print_coords()
        sys.exit(do_calibrate())

    if "-run" not in sys.argv:
        _print_coords()
        for w in _preflight():
            print("⚠️ " + w)
        print("[DryRun] 仅打印坐标, 未点击。加 -run 执行真实签到, -calibrate 交互校准。")
        sys.exit(0)

    _print_coords()
    for w in _preflight():
        print("⚠️ " + w)
    status, shot = do_checkin()
    print(f"\n== 结论: {status.upper()} | 截图: {shot} ==")
    code = {"success": 0, "failed": 2}.get(status, 2)
    sys.exit(code)
