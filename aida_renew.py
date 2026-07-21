#!/usr/bin/env python3

import os
import re
import sys
import time
import requests
from datetime import datetime
from seleniumbase import SB

EMAIL = os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("PASSWORD") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

LOGIN_URL = "https://auth.aida0710.work/login"
# 支持通过环境变量传入指定服务器的URL，未配置则默认使用指定的特定服务器 URL
SERVER_URL = os.environ.get("SERVER_URL", "https://hosting.aida0710.work/servers/f7f5ced6-d372-4e6a-b864-b89de741b76d")

if not EMAIL or not PASSWORD:
    print("❌ 请设置环境变量 EMAIL 和 PASSWORD")
    sys.exit(1)

def send_tg(token, chat_id, message):
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        if resp.status_code == 200:
            print("📨 Telegram 通知已发送")
        else:
            print(f"❌ Telegram 发送失败: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram 发送异常: {e}")

def mask_email(email):
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 4:
        masked_local = local[0] + '****' + local[-1] if len(local) > 1 else local
    else:
        masked_local = local[:2] + '****' + local[-2:]
    return f"{masked_local}@{domain}"

def login(sb, email, password):
    print("🌐 打开登录页面...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    time.sleep(2)

    print("📧 填写邮箱...")
    sb.type('#login-id', email, timeout=10)
    print("🔑 填写密码...")
    sb.type('#login-pw', password, timeout=10)

    print("🛡️ 处理 Turnstile...")
    try:
        sb.uc_gui_click_captcha()
        print("✅ Turnstile 验证已处理")
    except Exception as e:
        print(f"⚠️ Turnstile 处理异常: {e}")

    print("🔑 点击登录按钮...")
    sb.uc_click('button:contains("ログイン")')

    for _ in range(30):
        cur = sb.get_current_url()
        if "login" not in cur or "account" in cur:
            print(f"✅ 登录成功，当前 URL: {cur}")
            return True
        time.sleep(1)

    sb.save_screenshot("login_failed.png")
    print(f"❌ 登录超时，当前 URL: {sb.get_current_url()}")
    return False

def get_remaining_time(sb, timeout=15):
    """
    考虑到特定服务器页面异步加载数据，
    增加轮询等待逻辑，确保页面元素完全渲染后再提取时间。
    """
    for _ in range(timeout):
        page_source = sb.get_page_source()
        match = re.search(r'残り\s*(\d{1,2}:\d{2}:\d{2})', page_source)
        if match:
            return match.group(1)
        
        # 备选提取方案
        for xp in ['//*[contains(text(), "残り")]', '//span[contains(@class, "time")]']:
            try:
                elems = sb.find_elements(xp)
                for elem in elems:
                    txt = elem.text.strip()
                    m = re.search(r'(\d{1,2}:\d{2}:\d{2})', txt)
                    if m:
                        return m.group(1)
            except:
                continue
        time.sleep(1)
    return None

def click_extend_button(sb):
    """确保按钮在DOM中可用，并兼容可能出现的 disabled 状态"""
    selectors = [
        'button[title="稼働時間を最大まで延長"]',
        'button[aria-label="稼働時間を延長"]',
        'button:contains("稼働時間を延長")',
        'button[aria-label*="稼働時間"]',
        'button[title*="稼働時間"]',
    ]
    for sel in selectors:
        try:
            # 确保不点击正处于冷却状态 (disabled) 的按钮
            valid_sel = f"{sel}:not([disabled])"
            if sb.is_element_visible(valid_sel):
                print(f"✅ 找到可点击按钮，选择器: {valid_sel}")
                sb.uc_click(valid_sel, timeout=5)
                print("✅ 点击成功")
                return True
        except:
            continue
            
    # 如果常规点击失败，尝试JS强制点击兜底
    try:
        btn = sb.find_element('button[title*="稼働時間"]', timeout=3)
        sb.driver.execute_script("arguments[0].click();", btn)
        print("✅ 通过 JavaScript 点击成功")
        return True
    except:
        pass
    return False

def check_success(time_text):
    """
    放宽时间匹配要求：只要处于23小时30分至24小时区间，均视为续期达标。
    """
    if not time_text:
        return False
    return bool(re.search(r'^(24:00|23:[3-5]\d)', time_text))

def main():
    print("#" * 25)
    print("   Aida 自动登录续期 (特定实例优化版)")
    print("#" * 25)

    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1081"

    # 若检测到CI环境 (如 GitHub Actions) 强制开启 headless
    sb_kwargs = {"uc": True, "headless": True if os.environ.get("CI") else False}
    if IS_PROXY and proxy_str:
        print(f"🔗 挂载代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    print("🚀 启动浏览器")
    with SB(**sb_kwargs) as sb:
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"📍 当前出口IP: {sb.get_text('body')}")
        except Exception:
            print("⚠️ 获取 IP 失败，继续执行")

        if not login(sb, EMAIL, PASSWORD):
            msg = "❌ 登录失败，请检查账号或验证码"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print(f"📄 导航到指定服务器页面: {SERVER_URL} ...")
        sb.open(SERVER_URL)
        sb.wait_for_ready_state_complete()
        
        print("⏳ 等待页面及面板组件加载...")
        time.sleep(5) 

        current_url = sb.get_current_url()
        print(f"✅ 当前 URL: {current_url}")

        time_text = get_remaining_time(sb, timeout=15)
        if not time_text:
            msg = f"❌ 未能在服务器页面找到剩余时间信息，请确认链接: {SERVER_URL} 是否有效。"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print(f"🕒 当前剩余时间: {time_text}")

        if check_success(time_text):
            msg = f"✅ 剩余时间充足，无需续期\n当前剩余: {time_text}\n服务器: {SERVER_URL.split('/')[-1][:8]}..."
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print("🔄 尝试点击延期按钮...")
        if not click_extend_button(sb):
            msg = f"❌ 未找到或无法点击延期按钮，可能仍处于冷却期。\n服务器: {SERVER_URL.split('/')[-1][:8]}..."
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print("⏳ 等待续期请求响应...")
        time.sleep(5)
        
        new_time_text = get_remaining_time(sb, timeout=10)
        if not new_time_text:
            new_time_text = "未获取到"
        print(f"🕒 续期后剩余时间: {new_time_text}")

        success = check_success(new_time_text)

        masked = mask_email(EMAIL)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ 续期成功" if success else "❌ 续期执行完成，但时间未显著刷新"
        
        msg = f"""🇯🇵 Aida 服务器续期通知

{status}
👤 登录账户: {masked}
📅 最新时间: {new_time_text}
⏱️ 续期时间: {now_str}
🔗 目标实例: {SERVER_URL.split('/')[-1][:8]}..."""
        if not success:
            msg += f"\n原剩余时间: {time_text}"

        print(msg)
        send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)

    print("🏁 脚本执行完毕")

if __name__ == "__main__":
    main()
