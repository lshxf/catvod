import os
import sys
import time
import shutil
import glob
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"
DOWNLOAD_DIR = os.path.abspath("output")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_chrome_path():
    return shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")

def wait_for_challenge(driver, timeout=45):
    """循环检测 CF challenge 是否完成"""
    print("Waiting for Cloudflare challenge...")
    for i in range(timeout):
        time.sleep(1)
        try:
            title = driver.title or ""
        except Exception:
            title = ""
        t = title.lower()
        if "moment" not in t and "checking" not in t and "challenge" not in t and title.strip():
            print(f"Challenge cleared after {i+1}s (title: {title})")
            return True
    print(f"Warning: timeout reached, current title: {driver.title}")
    return False

def main():
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # 配置自动下载（如果服务器返回 Content-Disposition: attachment）
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "profile.default_content_settings.popups": 0,
    }
    options.add_experimental_option("prefs", prefs)

    chrome_path = get_chrome_path()
    if chrome_path:
        print(f"Using Chrome: {chrome_path}")
        options.binary_location = chrome_path

    driver = uc.Chrome(options=options)
    print(f"Browser version: {driver.capabilities.get('browserVersion', 'unknown')}")

    try:
        driver.get(URL)

        # 1. 等待 CF challenge 通过
        wait_for_challenge(driver)

        # 再留一点时间让页面/下载完成
        time.sleep(5)

        content = None

        # 方法1：页面直接显示 M3U 文本（通常在 <pre> 标签中）
        try:
            body_text = driver.execute_script("return document.body.innerText")
            if body_text and "#EXTM3U" in body_text:
                content = body_text
                print("Method 1 success: extracted from page body text")
        except Exception as e:
            print(f"Method 1 failed: {e}")

        # 方法2：查找自动下载的 .m3u / .m3u8 文件
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

        # 方法4：截图 Debug（如果以上都失败）
        if not content:
            debug_png = os.path.join(DOWNLOAD_DIR, "debug.png")
            driver.save_screenshot(debug_png)
            print(f"Debug screenshot saved: {debug_png}")
            print("Page title:", driver.title)
            print("Page source preview:", driver.page_source[:500])

        if content:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Success: saved {len(content)} bytes to {OUTPUT}")
        else:
            print("ERROR: Could not retrieve M3U content")
            sys.exit(1)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
