#!/usr/bin/env python3
# wb_api_checkin.py —— WorkBuddy「Buddy 加油站」API 直连签到（零 GUI 依赖）
# ============================================================================
# 方案背景(2026-08-18 老板要求补齐):
#   SkillHub 上的 workbuddy-checkin / workbuddy-daily-checkin 都是 API 直连方案,
#   比坐标点击更稳(无窗口位置/DPI/更新横幅遮挡问题)。本脚本实现同款:
#   读 WorkBuddy 桌面端本地登录态(auth .info 文件, 明文 JSON 含 JWT accessToken)
#   -> 调官方接口 POST https://copilot.tencent.com/billing/meter/* 完成签到。
#
# 接口(从 app.asar 逆向确认, 与社区披露一致):
#   POST /billing/meter/checkin-status   查询签到状态(只读)
#   POST /billing/meter/daily-checkin    每日签到(幂等: 已签返回 code 10001)
#   POST /billing/meter/get-user-resource 套餐信息(只读)
# 认证: Authorization: Bearer <accessToken>  (HttpService 拦截器同款)
#
# 用法:
#   python wb_api_checkin.py        # 查询状态+未签则领取, 输出结论, 退出码 0/2
#   python wb_api_checkin.py -status   # 仅查询, 不领取
#
# 退出码: 0=成功/已签过   2=失败(token缺失/接口异常/领取失败)
#
# 【隐私说明】仅读取本机登录态并调用官方接口, 凭据不落盘不外发。
# ============================================================================

import json, os, sys, urllib.request, urllib.error

# WorkBuddy 桌面端登录态文件(2026-08-18 逆向定位: sharedDataPath/auth/<id>.info)
AUTH_FILE = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                         "CodeBuddyExtension", "Data", "Public", "auth",
                         "workbuddy-desktop.info")
# 兜底: 腾讯云登录态(同一账号体系)
AUTH_FILE_FALLBACK = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                                  "CodeBuddyExtension", "Data", "Public", "auth",
                                  "Tencent-Cloud.coding-copilot.info")
# 后端 host(逆向自 app.asar: getFullUrl = window.location.origin + path,
# 前端 origin = https://copilot.tencent.com, 已验证可通)
BASE = "https://copilot.tencent.com"
TIMEOUT = 20
# 服务端按 UA 区分请求来源, 非浏览器 UA 直接裸 400(2026-08-18 实测坑), 必须带浏览器 UA
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get_token():
    """读登录态文件拿 accessToken。返回 (token, 来源路径) 或 (None, None)。"""
    for path in (AUTH_FILE, AUTH_FILE_FALLBACK):
        if os.path.exists(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
                t = (d.get("auth") or {}).get("accessToken")
                if t:
                    return t, path
            except Exception:
                pass
    return None, None


def call(path, token, body=None):
    """POST 官方接口。返回解析后的 JSON dict(含 HTTPError 时读 body 业务码)。"""
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token,
                 "User-Agent": UA,
                 "Accept-Language": "zh"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 业务错误也走 HTTP 400, 但 body 是 JSON 业务码(如 10001=已签到)
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": e.code, "msg": "HTTP " + str(e.code)}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


def main():
    status_only = "-status" in sys.argv
    token, src = get_token()
    if not token:
        print("ERROR: 未找到 WorkBuddy 登录态(auth 文件缺失或无 accessToken)。")
        print(f"  查找路径: {AUTH_FILE}")
        print("  请确认 WorkBuddy 桌面端已登录后重试。")
        return 2
    print(f"[auth] 登录态: {src}")

    st = call("/billing/meter/checkin-status", token)
    if st.get("code") != 0:
        print(f"[status] 查询签到状态失败: {st}")
        return 2
    data = st.get("data") or {}
    today_checked = bool(data.get("today_checked_in"))
    streak = data.get("streak_days") or 0
    print(f"[status] 今日已签: {today_checked} | 连续天数: {streak} | "
          f"今日积分: {data.get('today_credit') or 0} | 活动激活: {data.get('active')}")

    if today_checked:
        print("== 结论: 今日已签到, 无需领取 ==")
        return 0
    if status_only:
        print("== 结论: 今日未签到(-status 仅查询, 未领取) ==")
        return 0

    print("[checkin] 今日未签到, 调用 daily-checkin 领取...")
    r = call("/billing/meter/daily-checkin", token)
    code = r.get("code")
    if code == 0:
        d2 = r.get("data") or {}
        credit = d2.get("credit") or d2.get("today_credit") or 0
        streak2 = d2.get("streakDays") or d2.get("streak_days") or 0
        print(f"== 结论: 签到成功! 积分 {credit}, 连续 {streak2} 天 ==")
        return 0
    if code == 10001:
        print("== 结论: 今日已签到(接口幂等返回) ==")
        return 0
    print(f"== 结论: 签到失败: {r} ==")
    return 2


if __name__ == "__main__":
    sys.exit(main())
