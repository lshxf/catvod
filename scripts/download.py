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

    browser = await uc.start(
        browser_executable_path=chrome_path,
        headless=False,
    )

    try:
        print(f"Navigating to: {URL}")
        tab = await browser.get(URL)

        # 等待更长时间让页面完全加载
        print("Waiting 15s for page to fully load...")
        await asyncio.sleep(15)

        # 获取各种信息
        url = tab.url
        title = await tab.evaluate("document.title") or "N/A"
        html = await tab.get_content() or ""
        body_text = await tab.evaluate("document.body ? document.body.innerText : 'NO BODY'") or "NO BODY"
        
        print(f"\n=== URL: {url}")
        print(f"=== Title: {title}")
        print(f"=== HTML length: {len(html)}")
        print(f"=== Body innerText length: {len(body_text)}")
        
        # 打印 HTML 前 3000 字符，看看实际内容
        print(f"\n=== HTML PREVIEW (first 3000 chars) ===")
        print(html[:3000])
        print("=== END PREVIEW ===\n")

        # 检查 iframe
        iframe_count = await tab.evaluate("document.querySelectorAll('iframe').length")
        print(f"=== iframe count: {iframe_count}")

        # 检查是否有 shadow DOM
        shadow_hosts = await tab.evaluate("""
            Array.from(document.querySelectorAll('*')).filter(el => el.shadowRoot).length
        """)
        print(f"=== Shadow DOM hosts: {shadow_hosts}")

        # 检查所有文本内容（包括隐藏元素）
        all_text = await tab.evaluate("""
            document.documentElement.innerText || document.documentElement.textContent
        """)
        print(f"=== documentElement text length: {len(all_text or '')}")
        if all_text:
            print(f"=== documentElement text preview (first 1000 chars) ===")
            print((all_text or "")[:1000])
            print("=== END ===\n")

        # 尝试多种方式找 M3U
        content = None

        # 1. body innerText
        if body_text and "#EXTM3U" in body_text:
            content = body_text
            print("Found M3U in body.innerText")

        # 2. documentElement text
        if not content and all_text and "#EXTM3U" in all_text:
            content = all_text
            print("Found M3U in documentElement text")

        # 3. HTML 中直接找
        if not content and "#EXTM3U" in html:
            # 提取 M3U 部分
            start = html.find("#EXTM3U")
            # 找到 M3U 结束位置（可能在 </pre> 或 </body> 前）
            end_markers = ["</pre>", "</body>", "</html>"]
            end = len(html)
            for marker in end_markers:
                idx = html.find(marker, start)
                if idx != -1 and idx < end:
                    end = idx
            content = html[start:end]
            # 去掉 HTML 标签
            content = re.sub(r'<[^>]+>', '', content)
            import html as html_module
            content = html_module.unescape(content)
            print(f"Found M3U in raw HTML, extracted {len(content)} chars")

        # 4. iframe
        if not content and iframe_count > 0:
            for i in range(iframe_count):
                try:
                    iframe_text = await tab.evaluate(f"""
                        (function() {{
                            var iframes = document.querySelectorAll('iframe');
                            if (iframes[{i}]) {{
                                try {{
                                    return iframes[{i}].contentDocument.body.innerText;
                                }} catch(e) {{ return 'CROSS_ORIGIN'; }}
                            }}
                            return 'NO_IFRAME';
                        }})()
                    """)
                    print(f"  iframe[{i}] text length: {len(str(iframe_text))}")
                    if iframe_text and "#EXTM3U" in str(iframe_text):
                        content = str(iframe_text)
                        print(f"Found M3U in iframe[{i}]")
                        break
                except Exception as e:
                    print(f"  iframe[{i}] error: {e}")

        # 5. 下载的文件
        if not content:
            m3u_files = (
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u")) +
                glob.glob(os.path.join(DOWNLOAD_DIR, "*.m3u8"))
            )
            if m3u_files:
                latest = max(m3u_files, key=os.path.getctime)
                with open(latest, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"Found M3U in downloaded file: {latest}")
                os.remove(latest)

        # 保存截图
        try:
            await tab.save_screenshot(os.path.join(DOWNLOAD_DIR, "debug.png"))
            print("Screenshot saved")
        except Exception as e:
            print(f"Screenshot error: {e}")

        if content:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"\nSuccess: {len(content)} bytes -> {OUTPUT}")
        else:
            print("\nERROR: No M3U content found")
            # 保存 HTML 用于离线分析
            with open(os.path.join(DOWNLOAD_DIR, "debug.html"), "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved debug.html for analysis")
            sys.exit(1)

    finally:
        browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
