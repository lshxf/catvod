import os
import sys
import time

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"

def save(content: str, source: str):
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[{source}] Success: Saved {len(content)} bytes to {OUTPUT}")
    # 校验 M3U 头
    if content.strip().startswith("#EXTM3U"):
        print(f"[{source}] Valid M3U format confirmed.")
    else:
        print(f"[{source}] WARNING: Content does not start with #EXTM3U")
        print("--- First 500 chars ---")
        print(content[:500])
        print("-----------------------")

def try_curl_cffi():
    print("\n>>> Trying curl_cffi (browser impersonation)...")
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(URL, impersonate="chrome124", timeout=60)
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        if resp.status_code == 200:
            save(resp.text, "curl_cffi")
            return True
        else:
            print(f"curl_cffi returned status {resp.status_code}, body preview: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"curl_cffi failed: {e}")
        return False

def try_requests():
    print("\n>>> Trying standard requests (custom headers)...")
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        resp = requests.get(URL, headers=headers, timeout=60)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            save(resp.text, "requests")
            return True
        else:
            print(f"requests returned status {resp.status_code}, body preview: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"requests failed: {e}")
        return False

def try_selenium():
    print("\n>>> Trying Selenium headless (last resort)...")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        # GitHub Actions ubuntu 自带 chromedriver
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(URL)
        time.sleep(5)  # 等待 JS 执行
        content = driver.page_source
        driver.quit()

        # page_source 是 HTML，需要从中提取 M3U 内容或检查是否是直接下载
        if "#EXTM3U" in content:
            # 尝试提取 body 中的纯文本
            save(content, "selenium")
            return True
        else:
            print("Selenium page source does not contain M3U data. Preview:")
            print(content[:500])
            return False
    except Exception as e:
        print(f"Selenium failed: {e}")
        return False

def main():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    
    if try_curl_cffi():
        sys.exit(0)
    if try_requests():
        sys.exit(0)
    if try_selenium():
        sys.exit(0)
    
    print("\n!!! ALL METHODS FAILED !!!")
    sys.exit(1)

if __name__ == "__main__":
    main()
