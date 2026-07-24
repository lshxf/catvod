import os
import sys
import time
import shutil
import glob
import subprocess
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"
DOWNLOAD_DIR = os.path.abspath("output")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_chrome_info():
    """查找 Chrome 路径并提取主版本号"""
    paths = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]
    for p in paths:
        if os.path.exists(p):
            try:
                result = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=10)
                version_str = result.stdout.strip()
                print(f"Found Chrome: {p} -> {version_str}")
                # 修复：从 "Chromium 150.0.7871.128 snap" 中提取版本号
                match = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', version_str)
                if match:
                    major = int(match.group(1))
                    return p, major
                else:
                    print(f"Could not parse version from: {version_str}")
            except Exception as e:
                print(f"Failed to get version from {p}: {e}")
                continue
    return None, None

def wait_for_challenge(driver, timeout=90):
    """循环检测 CF challenge 是否完成"""
    print("Waiting for Cloudflare challenge...")
    for i in range(timeout):
        time.sleep(1)
        try:
            title = (driver.title or "").lower()
        except Exception:
            title = ""
        t = title.lower()
        if "moment" not in t and "checking" not in t and "challenge" not in t and title.strip():
            print(f"Challenge cleared after {i+1}s (title: {driver.title})")
            return True
        # 每 10 秒打印一次状态
        if (i + 1) % 10 == 0:
            print(f"  ... still waiting ({i+1}s), title: {driver.title}")
    print(f"Timeout. Current title: {driver.title}")
    return False

def main():
    chrome_path, chrome_major = get_chrome_info()
    if not chrome_path:
        print("ERROR: No Chrome/Chromium found")
        sys.exit(1)

    options = uc.ChromeOptions()
    # 关键修复：不使用 headless，让 Chrome 在 Xvfb 中以有头模式运行
    options.headless = False
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = chrome_path

    # 可选：代理配置
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

    print(f"Launching undetected Chrome {chrome_major} in HEADED mode (via Xvfb)...")
    driver = uc.Chrome(options=options, version_main=chrome_major)

    try:
        driver.get(URL)

        # 等待 CF challenge 通过
        challenge_passed = wait_for_challenge(driver)

        # 即使 challenge 超时，也尝试获取内容（有时 title 没变但内容已加载）
        time.sleep(3)

        content = None

        # 方法1：页面直接显示 M3U 文本
        try:
            body_text = driver.execute_script("return document.body.innerText")
            if body_text and "#EXTM3U" in body_text:
                content = body_text
                print("Extracted from page body text")
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
                print(f"Read downloaded file: {latest}")
                os.remove(latest)

        # 方法3：从 <pre> 标签提取
        if not content:
            try:
                pre = driver.find_element(By.TAG_NAME, "pre")
                text = pre.text
                if "#EXTM3U" in text:
                    content = text
                    print("Extracted from <pre> tag")
            except Exception as e:
                print(f"Method 3 failed: {e}")

        # Debug
        if not content:
            debug_png = os.path.join(DOWNLOAD_DIR, "debug.png")
            driver.save_screenshot(debug_png)
            print(f"Debug screenshot: {debug_png}")
            print("Page title:", driver.title)
            try:
                print("Source preview:", driver.page_source[:500])
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
