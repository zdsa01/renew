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
DASH_URL = "https://hosting.aida0710.work/dashboard"

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

def get_remaining_time(sb):
    """
    从页面提取剩余时间，返回纯时间字符串（如 '23:10:23'）
    若找不到则返回 None
    """
    page_source = sb.get_page_source()
    # 匹配 "残り 23:10:23" 或 "残り 24:00:46"
    match = re.search(r'残り\s*(\d{1,2}:\d{2}:\d{2})', page_source)
    if match:
        return match.group(1)  # 只返回时间部分

    # 备选：从元素中提取
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
    return None

def click_extend_button(sb):
    """尝试多种选择器点击延期按钮，返回是否成功"""
    selectors = [
        'button[title="稼働時間を最大まで延長"]',
        'button[aria-label="稼働時間を延長"]',
        'button[aria-label*="稼働時間"]',
        'button[title*="稼働時間"]',
    ]
    for sel in selectors:
        try:
            if sb.find_element(sel, timeout=2):
                print(f"✅ 找到按钮，选择器: {sel}")
                sb.uc_click(sel, timeout=5)
                print("✅ 点击成功")
                return True
        except:
            continue
    try:
        btn = sb.find_element('button[title*="稼働時間"]', timeout=2)
        sb.driver.execute_script("arguments[0].click();", btn)
        print("✅ 通过 JavaScript 点击成功")
        return True
    except:
        pass
    return False

def main():
    print("#" * 25)
    print("   Aida 自动登录续期")
    print("#" * 25)

    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1081"

    sb_kwargs = {"uc": True, "headless": False}
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

        print("📄 导航到 Dashboard...")
        sb.open(DASH_URL)
        sb.wait_for_ready_state_complete()
        time.sleep(3)

        current_url = sb.get_current_url()
        current_title = sb.get_title() or ""
        print(f"✅ 当前 URL: {current_url}")
        if "Mochi Hosting｜Minecraft" in current_title:
            print(f"✅ 标题匹配: {current_title}")
        else:
            print(f"⚠️ 标题不包含预期内容，当前: {current_title}")

        time_text = get_remaining_time(sb)
        if not time_text:
            msg = "❌ 未找到剩余时间信息"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print(f"🕒 当前剩余时间: {time_text}")

        # 成功条件：时间为 23:59 或 24:00 开头（续期后满24小时）
        if re.search(r'^(23:59|24:00)', time_text):
            msg = f"✅ 已自动续期（时间已是 23:59 或 24:00）\n{time_text}"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        print("🔄 尝试点击延期按钮...")
        if not click_extend_button(sb):
            msg = "❌ 未找到或无法点击延期按钮"
            print(msg)
            send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)
            return

        time.sleep(3)
        new_time_text = get_remaining_time(sb)
        if not new_time_text:
            new_time_text = "未获取到"
        print(f"🕒 续期后剩余时间: {new_time_text}")

        success = bool(re.search(r'^(23:59|24:00)', new_time_text))

        masked = mask_email(EMAIL)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ 续期成功" if success else "❌ 续期失败,时间未变为23:59或24:00"
        msg = f"""🇯🇵  Aida续期通知

{status}
👤 登录账户: {masked}
📅 到期时间: {new_time_text}
⏱️ 续期时间: {now_str}"""
        if not success:
            msg += f"\n原剩余时间: {time_text}"

        print(msg)
        send_tg(TG_BOT_TOKEN, TG_CHAT_ID, msg)

    print("🏁 脚本执行完毕")

if __name__ == "__main__":
    main()