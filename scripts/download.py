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

async def wait_for_page_load(tab, timeout=120):
    """等待页面真正加载完成（有内容且不是空白）"""
    print("Waiting for page content...")
    for i in range(timeout):
        await asyncio.sleep(1)
        
        try:
            url = tab.url
            title = await tab.evaluate("document.title") or ""
        except Exception:
            url = ""
            title = ""
        
        # 每 5 秒打印一次状态
        if (i + 1) % 5 == 0:
            print(f"  [{i+1}s] URL: {url}, Title: {title}")
        
        # 跳过空白页
        if not url or url == "about:blank":
            continue
        
        # 如果还在 challenge 中，继续等待
        t = title.lower()
        if "moment" in t or "checking" in t or "challenge" in t:
            continue
        
        # 检查 body 是否有内容
        try:
            body_text = await tab.evaluate("document.body ? document.body.innerText : ''") or ""
            body_html = await tab.evaluate("document.body ? document.body.innerHTML : ''") or ""
        except Exception:
            body_text = ""
            body_html = ""
        
        # 如果 body 有实际内容（超过 100 字符），认为页面加载完成
        if len(body_text) > 100 or len(body_html) > 500:
            print(f"  Page content loaded after {i+1}s ({len(body_text)} chars text, {len(body_html)} chars html)")
            return True
        
        # 如果 title 不是 New Tab 且有内容，也认为加载完成
        if title and title != "New Tab" and len(body_html) > 100:
            print(f"  Page loaded after {i+1}s (title: {title})")
            return True
    
    print("Timeout waiting for page content")
    return False

async def main():
    chrome_path = get_chrome_path()
    if not chrome_path:
        print("ERROR: No Chrome found")
        sys.exit(1)

    print(f"Using Chrome: {chrome_path}")

    browser = await uc.start(
        browser_executable_path=chrome_path,
        headless=False,
    )

    try:
        print(f"Navigating to: {URL}")
        tab = await browser.get(URL)
        
        # 等待页面有内容
        loaded = await wait_for_page_load(tab)
        
        # 如果第一次加载失败，尝试刷新
        if not loaded:
            print("First load failed, trying refresh...")
            await tab.reload()
            loaded = await wait_for_page_load(tab)
        
        if not loaded:
            print("Page failed to load after refresh")
            sys.exit(1)

        # 额外等待让 JS 完全执行
        await asyncio.sleep(5)
        print("Extracting content...")

        content = None

        # 方法1：body 文本
        try:
            body_text = await tab.evaluate("document.body.innerText")
            if body_text and "#EXTM3U" in body_text:
                content = body_text
                print("Method 1 success: body text")
        except Exception as e:
            print(f"Method 1 failed: {e}")

        # 方法2：page source
        if not content:
            try:
                source = await tab.get_content()
                if "#EXTM3U" in source:
                    import html
                    text = re.sub(r'<[^>]+>', '', source)
                    text = html.unescape(text)
                    if "#EXTM3U" in text:
                        content = text
                        print("Method 2 success: page source")
            except Exception as e:
                print(f"Method 2 failed: {e}")

        # 方法3：<pre> 标签
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

        # 方法4：检查是否是文件下载
        if not content:
            m3u_files = (
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u")) +
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u8"))
            )
            if m3u_files:
                latest = max(m3u_files, key=os.path.getctime)
                with open(latest, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Method 4 success: downloaded file {latest}")
                os.remove(latest)

        # Debug
        if not content:
            print("DEBUG: Saving screenshot...")
            try:
                await tab.save_screenshot(os.path.join(DOWNLOAD_DIR, "debug.png"))
            except Exception as e:
                print(f"Screenshot failed: {e}")
            
            try:
                title = await tab.evaluate("document.title")
                url = tab.url
                body = await tab.evaluate("document.body.innerText") or "empty"
                html_len = len(await tab.get_content() or "")
                print(f"Title: {title}")
                print(f"URL: {url}")
                print(f"Body: {body[:500]}")
                print(f"HTML length: {html_len}")
            except Exception as e:
                print(f"Debug failed: {e}")

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
