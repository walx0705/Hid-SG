#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, time, random, requests
from playwright.sync_api import sync_playwright

# --- 环境变量 ---
COOKIE_VALUE = os.environ.get('COOKIE_VALUE') or ""
EMAIL        = os.environ.get('EMAIL') or ""
PASSWORD     = os.environ.get('PASSWORD') or ""
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN') or ""
TG_CHAT_ID   = os.environ.get('TG_CHAT_ID') or ""

BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"

IS_PROXY      = os.environ.get('IS_PROXY', 'false').lower() == 'true'
PROXY_SERVER  = os.environ.get('PROXY_SERVER') or "socks5://127.0.0.1:1080"
REQUESTS_PROXIES = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def get_current_ip(proxy=None):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except:
        pass
    return "获取失败"

def send_telegram_photo(caption, path):
    if not TG_BOT_TOKEN or not TG_CHAT_ID or not os.path.exists(path):
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    try:
        with open(path, 'rb') as f:
            r = requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': caption},
                              files={'photo': f}, timeout=30, proxies=REQUESTS_PROXIES)
        if r.status_code == 200:
            log("✅ TG 截图发送成功")
            return True
        else:
            log(f"❌ TG 截图发送失败: {r.text}")
    except Exception as e:
        log(f"❌ TG 截图异常: {e}")
    return False

def send_telegram_notification(status, old_due, new_due):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    masked = EMAIL[:2] + "****" if EMAIL else "未知"
    text = (f"🎉 HidenCloud 续期通知\n\n{status}\n"
            f"👤 账号: {masked}\n"
            f"📅 续期前到期：{old_due}\n"
            f"📅 续期后到期：{new_due}\n"
            f"🕒 时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time()+8*3600))}")
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT_ID, "text": text},
                          timeout=10, proxies=REQUESTS_PROXIES)
        if r.status_code == 200:
            log("✅ TG 文本通知发送成功")
        else:
            log(f"❌ TG 文本通知失败: {r.text}")
    except Exception as e:
        log(f"❌ TG 文本通知异常: {e}")

def handle_cloudflare(page):
    iframe = 'iframe[src*="challenges.cloudflare.com"]'
    if page.locator(iframe).count() == 0:
        return True
    log("⚠️ 处理 Cloudflare 验证...")
    start = time.time()
    while time.time() - start < 60:
        if page.locator(iframe).count() == 0:
            log("✅ 验证通过")
            return True
        try:
            cb = page.frame_locator(iframe).locator('input[type="checkbox"]')
            if cb.is_visible():
                cb.click()
                time.sleep(5)
        except:
            time.sleep(1)
    log("❌ 验证超时")
    return False

def login(page):
    if COOKIE_VALUE:
        log("📇 尝试 Cookie 登录")
        try:
            page.context.add_cookies([{
                'name': 'remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d',
                'value': COOKIE_VALUE,
                'domain': 'dash.hidencloud.com',
                'path': '/',
                'expires': int(time.time()) + 86400*365,
                'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
            }])
            page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page)
            if "auth/login" not in page.url:
                log("✅ Cookie 登录成功")
                return True
            log("❌ Cookie 失效")
        except:
            pass
    if EMAIL and PASSWORD:
        log("💣 尝试账号密码登录")
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page)
            page.fill('input[name="email"]', EMAIL)
            page.fill('input[name="password"]', PASSWORD)
            page.click('button[type="submit"]')
            time.sleep(3)
            handle_cloudflare(page)
            page.wait_for_url(f"{BASE_URL}/*", timeout=30000)
            page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=60000)
            handle_cloudflare(page)
            if "auth/login" in page.url:
                log("❌ 登录失败")
                return False
            log("✅ 账号密码登录成功")
            return True
        except Exception as e:
            log(f"❌ 登录异常: {e}")
            page.screenshot(path="login_fail.png")
            return False
    return False

def get_server_id(page):
    try:
        time.sleep(3)
        html = page.content()
        ids = re.findall(r'/service/(\d+)/manage', html)
        if ids: return ids[0]
        ids = re.findall(r'#(\d{4,})', html)
        if ids: return ids[0]
    except Exception as e:
        log(f"❌ 获取 Server ID 异常: {e}")
        page.screenshot(path="server_id_error.png")
    return None

def get_due_date(page, service_url):
    try:
        if page.url != service_url:
            page.goto(service_url, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        body = page.locator("body").inner_text()
        m = re.search(r"Due date\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})", body, re.I)
        if m:
            return m.group(1).strip()
    except Exception as e:
        log(f"❌ 获取到期日异常: {e}")
    return "未知"

def renew_service(page, service_url):
    try:
        if page.url != service_url:
            page.goto(service_url, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        renew_btn = page.locator('button:has-text("Renew")')
        create_btn = page.locator('button:has-text("Create Invoice")')
        for i in range(3):
            try:
                renew_btn.wait_for(state="visible", timeout=10000)
                renew_btn.scroll_into_view_if_needed()
                renew_btn.click()
                time.sleep(2)
                if "can only renew" in page.locator("body").inner_text().lower():
                    log("⏳ 未到续期时间")
                    page.screenshot(path="renew_not_allowed.png")
                    return "NOT_TIME"
                create_btn.wait_for(state="visible", timeout=5000)
                break
            except:
                time.sleep(2)
        else:
            log("❌ 续费弹窗未出现")
            page.screenshot(path="renew_modal_failed.png")
            return False
        create_btn.click()
        start = time.time()
        while time.time() - start < 90:
            if "/payment/invoice/" in page.url:
                break
            handle_cloudflare(page)
            time.sleep(1)
        else:
            log("❌ 未跳转发票页面")
            page.screenshot(path="renew_stuck_invoice.png")
            return False
        pay_btn = page.locator('a:has-text("Pay"):visible, button:has-text("Pay"):visible').first
        pay_btn.wait_for(state="visible", timeout=30000)
        pay_btn.click()
        time.sleep(5)
        page.goto(service_url, wait_until="domcontentloaded", timeout=60000)
        handle_cloudflare(page)
        return True
    except Exception as e:
        log(f"❌ 续费异常: {e}")
        page.screenshot(path="renew_error.png")
        return False

def main():
    global IS_PROXY, REQUESTS_PROXIES
    if not COOKIE_VALUE and not (EMAIL and PASSWORD):
        log("❌ 缺少凭证")
        sys.exit(1)

    # 代理连通性检测（关键回退点）
    if IS_PROXY:
        log(f"⚙️ 代理启用: {PROXY_SERVER}，测试连通性...")
        ip = get_current_ip(PROXY_SERVER)
        if ip == "获取失败":
            log("❌ 代理不可用，切换为直连模式")
            IS_PROXY = False
            REQUESTS_PROXIES = None
        else:
            log(f"✅ 代理正常，出口IP: {ip}")
    else:
        log("🌐 直连模式")

    current_ip = get_current_ip(PROXY_SERVER if IS_PROXY else None)
    log(f"🎯 最终出口IP: {current_ip}")

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=False,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                proxy={"server": PROXY_SERVER} if IS_PROXY else None
            )
            page = context.new_page()
            page.add_init_script(STEALTH_JS)

            if not login(page):
                page.screenshot(path="login_fail_final.png")
                send_telegram_photo("❌ 登录失败", "login_fail_final.png")
                sys.exit(1)

            server_id = get_server_id(page)
            if not server_id:
                page.screenshot(path="server_id_error_final.png")
                send_telegram_photo("❌ 获取 Server ID 失败", "server_id_error_final.png")
                sys.exit(1)

            service_url = f"{BASE_URL}/service/{server_id}/manage"
            old_due = get_due_date(page, service_url)
            log(f"📆 续期前到期: {old_due}")

            result = renew_service(page, service_url)
            new_due = old_due
            if result == "NOT_TIME":
                status = "⏳ 未到续期时间"
                send_telegram_photo(status, "renew_not_allowed.png")
            elif result is False:
                status = "❌ 续期失败"
                send_telegram_photo(status, "renew_error.png")
            else:
                new_due = get_due_date(page, service_url)
                status = "✅ 续期成功"
                page.screenshot(path="renew_success.png")
                send_telegram_photo(status, "renew_success.png")

            send_telegram_notification(status, old_due, new_due)
            sys.exit(0 if result != False else 1)

        except Exception as e:
            log(f"❌ 致命错误: {e}")
            if 'page' in locals():
                try:
                    page.screenshot(path="fatal_error.png")
                    send_telegram_photo(f"❌ 致命错误: {str(e)[:200]}", "fatal_error.png")
                except:
                    pass
            sys.exit(1)
        finally:
            if browser:
                browser.close()

if __name__ == "__main__":
    main()
