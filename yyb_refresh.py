#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YYB_GO 刷新存活前置任务（方案 A）
================================
功能：在每日 YYB_GO 脚本窗口（08:00）之前运行，
      1) 检测 yyb-go 账号状态 / 探测 getCode 是否可用（即「token 是否过期」）
      2) 全部健康 -> 直接跳过（「不过期不刷新」）
      3) 任一账号过期/失效 -> 调用 yyb-go 的「刷新存活」接口 POST /accounts/refresh
         （即「过期了再自动刷新 Code 来重新获取 token」）
      4) 刷新后复探，若仍 409 re-scan required -> 明确提示需人工重新扫码

说明：
- 目标地址默认 http://172.18.0.1:8002（qinglong 容器内访问宿主 yyb-go 的桥接地址）。
  可通过环境变量 YYB_GO_BASE 覆盖（容器内运行 cron 时建议保持默认）。
- 小程序 app_id 默认 wx5dbc7b1ca99bca9c（与脚本内 MINI_APP_ID 一致），可用 YYB_GO_APP_ID 覆盖。
- 刷新是幂等的：刷新健康账号不会造成副作用，仅重签 Code/Token 维持存活。

注意：当账号「彻底过期」（login_buffer 失效）时，/accounts/refresh 也无法恢复，
      getCode 会返回 409 re-scan required，此时必须人工在 yyb-go 控制台重新扫码。
      本脚本会如实打印该告警，但不会自行中断其它健康账号的刷新。
"""

import os
import sys
import json
import urllib.request
import urllib.error

BASE = os.environ.get("YYB_GO_BASE", "http://172.18.0.1:8002").rstrip("/")
APP_ID = os.environ.get("YYB_GO_APP_ID", "wx5dbc7b1ca99bca9c")

# yyb-go 视为「健康」的账号 status 取值（实测到过 "expired" 为非健康）
HEALTHY_STATUS = {"active", "ok", "valid", "normal", "healthy", "alive"}


def _request(method, path, payload=None):
    url = BASE + path
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_accounts():
    return _request("GET", "/accounts")


def refresh_accounts():
    return _request("POST", "/accounts/refresh")


def probe_getcode(openid):
    """探测该账号当前能否拿到 code（即 Code/Token 是否有效）。返回 (ok, detail)。"""
    try:
        r = _request("POST", "/wxapp/getCode", {"ref": openid, "app_id": APP_ID})
        code = r.get("code")
        result = (r.get("data") or {}).get("result") or {}
        if code == 0 and result.get("code"):
            return True, r
        return False, r
    except urllib.error.HTTPError as e:
        # 例如 409 re-scan required
        body = e.read().decode("utf-8", "ignore")
        try:
            return False, json.loads(body)
        except Exception:
            return False, {"code": e.code, "msg": body}
    except Exception as e:  # noqa: BLE001
        return False, {"error": str(e)}


def is_healthy(acc):
    status = (acc.get("status") or "").lower()
    if status in HEALTHY_STATUS:
        return True
    return False


def main():
    print(f"[YYB_GO 刷新存活] BASE={BASE} APP_ID={APP_ID}")
    # 1) 拉取账号列表
    try:
        acc_resp = get_accounts()
    except Exception as e:  # noqa: BLE001
        print(f"[检测] 获取账号列表失败: {e}")
        return 1

    accounts = acc_resp.get("data") or []
    if not accounts:
        print("[检测] 未获取到任何账号，跳过")
        return 0
    print(f"[检测] 共 {len(accounts)} 个账号")

    need_refresh = []
    for acc in accounts:
        openid = acc.get("openid") or ""
        nick = acc.get("nickname") or openid[:12]
        status = acc.get("status")
        # 先按 status 判断
        if is_healthy(acc):
            # status 健康，再实测 getCode 是否真能拿码（防止 status 未翻转但 Code 已过期）
            ok, detail = probe_getcode(openid)
            if ok:
                print(f"  - {nick}: status={status}, getCode 正常 -> 健康")
                continue
            reason = (detail.get("msg") or json.dumps(detail, ensure_ascii=False))
            print(f"  - {nick}: status={status}, 但 getCode 失败({reason}) -> 需刷新")
            need_refresh.append(acc)
        else:
            print(f"  - {nick}: status={status} -> 需刷新")
            need_refresh.append(acc)

    if not need_refresh:
        print("[结果] 全部账号健康，无需刷新，直接退出")
        return 0

    print(f"[刷新] 对 {len(need_refresh)} 个账号执行 POST /accounts/refresh ...")
    try:
        rref = refresh_accounts()
        print(f"[刷新] refresh 返回: {json.dumps(rref, ensure_ascii=False)}")
    except Exception as e:  # noqa: BLE001
        print(f"[刷新] refresh 调用失败: {e}")
        return 1

    # 2) 复探，确认是否恢复
    print("[校验] 刷新后复探:")
    still_bad = 0
    for acc in need_refresh:
        openid = acc.get("openid") or ""
        nick = acc.get("nickname") or openid[:12]
        ok, detail = probe_getcode(openid)
        if ok:
            print(f"  - {nick}: 已恢复")
        else:
            still_bad += 1
            msg = detail.get("msg") if isinstance(detail, dict) else str(detail)
            if detail.get("code") == 409 or "re-scan" in str(msg).lower():
                print(f"  - {nick}: 仍失败 -> 需人工重新扫码 (re-scan required)")
            else:
                print(f"  - {nick}: 仍失败({json.dumps(detail, ensure_ascii=False)})")

    if still_bad:
        print(f"[告警] {still_bad} 个账号刷新后仍不可用，若为 re-scan required 需人工在 yyb-go 控制台重新扫码登录")
        return 2
    print("[结果] 刷新完成，全部账号已恢复")
    return 0


if __name__ == "__main__":
    sys.exit(main())
