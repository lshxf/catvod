import os
import sys
import time
import asyncio
import shutil
import glob
import subprocess
import re
import nodriver as uc

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"
DOWNLOAD_DIR = os.path.abspath("output")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_chrome_path():
    paths = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

async def main():
    chrome_path = get_chrome_path()
    if not chrome_path:
        print("ERROR: No Chrome found")
        sys.exit(1)

    print(f"Using Chrome: {chrome_path}")

    # 启动浏览器（nodriver 会自动处理 CDP 连接）
    browser = await uc.start(
        browser_executable_path=chrome_path,
        headless=False,  # 有头模式，配合 Xvfb
    )

    try:
        print(f"Navigating to: {URL}")
        tab = await browser.get(URL)

        # 等待页面加载和 CF challenge
        print("Waiting for page to load...")
        for i in range(120):
            await asyncio.sleep(1)
            try:
                title = await tab.evaluate("document.title")
                url = tab.url
            except Exception:
                title = ""
                url = ""
            
            t = (title or "").lower()
            print(f"  [{i+1}s] URL: {url}, Title: {title}")
            
            # 如果还在 challenge 页面，继续等待
            if "moment" in t or "checking" in t or "challenge" in t:
                if (i + 1) % 10 == 0:
                    print(f"  Still in CF challenge...")
                continue
            
            # 如果页面已经加载完成（有实际内容且不是空白页）
            if url and url != "about:blank" and "new-tab" not in url:
                # 再等几秒让内容稳定
                await asyncio.sleep(3)
                break
        else:
            print("Timeout waiting for page")
            sys.exit(1)

        # 获取页面内容
        print("Extracting content...")
        content = None

        # 方法1：直接获取 body 文本
        try:
            body_text = await tab.evaluate("document.body.innerText")
            if body_text and "#EXTM3U" in body_text:
                content = body_text
                print("Method 1 success: body text")
        except Exception as e:
            print(f"Method 1 failed: {e}")

        # 方法2：获取 page source
        if not content:
            try:
                source = await tab.get_content()
                if "#EXTM3U" in source:
                    # 去掉 HTML 标签
                    import html
                    text = re.sub(r'<[^>]+>', '', source)
                    text = html.unescape(text)
                    if "#EXTM3U" in text:
                        content = text
                        print("Method 2 success: page source")
            except Exception as e:
                print(f"Method 2 failed: {e}")

        # 方法3：查找 <pre> 标签
        if not content:
            try:
                pre = await tab.query_selector("pre")
                if pre:
                    text = await pre.get_text()
                    if "#EXTM3U" in text:
                        content = text
                        print("Method 3 success: <pre> tag")
            except Exception as e:
                print(f"Method 3 failed: {e}")

        # Debug
        if not content:
            print("DEBUG: Saving screenshot...")
            try:
                await tab.save_screenshot(os.path.join(DOWNLOAD_DIR, "debug.png"))
                print(f"Screenshot saved")
            except Exception as e:
                print(f"Screenshot failed: {e}")
            
            try:
                title = await tab.evaluate("document.title")
                url = tab.url
                body = await tab.evaluate("document.body.innerText")
                print(f"Title: {title}")
                print(f"URL: {url}")
                print(f"Body preview: {body[:500] if body else 'empty'}")
            except Exception as e:
                print(f"Debug info failed: {e}")

        if content:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Success: {len(content)} bytes -> {OUTPUT}")
        else:
            print("ERROR: No M3U content retrieved")
            sys.exit(1)

    finally:
        browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
