import os
import sys
import time
import shutil
import glob
import subprocess
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"
DOWNLOAD_DIR = os.path.abspath("output")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_chrome_info():
    paths = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]
    for p in paths:
        if os.path.exists(p):
            try:
                result = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=10)
                version_str = result.stdout.strip()
                print(f"Found Chrome: {p} -> {version_str}")
                match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', version_str)
                if match:
                    major = int(match.group(1))
                    return p, major
            except Exception as e:
                print(f"Failed to get version from {p}: {e}")
                continue
    return None, None

def navigate_and_wait(driver, url, timeout=120):
    """导航到 URL 并等待页面加载完成"""
    print(f"Navigating to: {url}")
    driver.get(url)
    
    # 等待页面不再处于新标签页或 about:blank
    for i in range(timeout):
        time.sleep(1)
        current_url = driver.current_url
        title = (driver.title or "").lower()
        
        # 如果还在新标签页，尝试重新导航
        if current_url in ("about:blank", "chrome://newtab/", "chrome://new-tab-page/"):
            if i % 5 == 0 and i > 0:
                print(f"  Still on blank page ({i}s), retrying navigation...")
                driver.get(url)
            continue
        
        # 检查是否还在 CF challenge 中
        if "moment" in title or "checking" in title or "challenge" in title:
            if (i + 1) % 10 == 0:
                print(f"  Still in CF challenge ({i+1}s), title: {driver.title}")
            continue
        
        # 页面已加载且不是 challenge
        print(f"Page loaded after {i+1}s (url: {current_url}, title: {driver.title})")
        return True
    
    print(f"Navigation timeout. URL: {driver.current_url}, Title: {driver.title}")
    return False

def main():
    chrome_path, chrome_major = get_chrome_info()
    if not chrome_path:
        print("ERROR: No Chrome found")
        sys.exit(1)

    options = uc.ChromeOptions()
    options.headless = False
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = chrome_path

    proxy = os.environ.get("PROXY")
    if proxy:
        print(f"Using proxy: {proxy}")
        options.add_argument(f'--proxy-server={proxy}')

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "profile.default_content_settings.popups": 0,
    }
    options.add_experimental_option("prefs", prefs)

    print(f"Launching undetected Chrome {chrome_major} in HEADED mode...")
    driver = uc.Chrome(options=options, version_main=chrome_major)

    try:
        # 导航并等待
        if not navigate_and_wait(driver, URL):
            print("Navigation failed")
            sys.exit(1)

        # 额外等待让页面完全稳定
        time.sleep(5)

        content = None
        current_url = driver.current_url
        print(f"Current URL: {current_url}")

        # 方法1：页面直接显示 M3U 文本
        try:
            body_text = driver.execute_script("return document.body.innerText")
            if body_text and "#EXTM3U" in body_text:
                content = body_text
                print("Method 1 success: extracted from page body text")
        except Exception as e:
            print(f"Method 1 failed: {e}")

        # 方法2：自动下载的文件
        if not content:
            m3u_files = (
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u")) +
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u8"))
            )
            if m3u_files:
                latest = max(m3u_files, key=os.path.getctime)
                with open(latest, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Method 2 success: read downloaded file {latest}")
                os.remove(latest)

        # 方法3：从 <pre> 标签提取
        if not content:
            try:
                pre = driver.find_element(By.TAG_NAME, "pre")
                text = pre.text
                if "#EXTM3U" in text:
                    content = text
                    print("Method 3 success: extracted from <pre> tag")
            except Exception as e:
                print(f"Method 3 failed: {e}")

        # 方法4：从 page_source 中提取（有时 M3U 在 HTML 中）
        if not content:
            try:
                source = driver.page_source
                if "#EXTM3U" in source:
                    # 尝试提取 body 中的纯文本
                    import html
                    # 简单提取：去掉 HTML 标签
                    import re
                    text = re.sub(r'<[^>]+>', '', source)
                    text = html.unescape(text)
                    if "#EXTM3U" in text:
                        content = text
                        print("Method 4 success: extracted from page source")
            except Exception as e:
                print(f"Method 4 failed: {e}")

        # Debug
        if not content:
            debug_png = os.path.join(DOWNLOAD_DIR, "debug.png")
            driver.save_screenshot(debug_png)
            print(f"Debug screenshot: {debug_png}")
            print(f"Page title: {driver.title}")
            print(f"Current URL: {driver.current_url}")
            try:
                body = driver.execute_script("return document.body.innerText")[:500]
                print(f"Body text preview: {body}")
            except Exception:
                pass

        if content:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Success: {len(content)} bytes -> {OUTPUT}")
        else:
            print("ERROR: No M3U content retrieved")
            sys.exit(1)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
