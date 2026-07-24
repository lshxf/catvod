import os
import sys
from curl_cffi import requests

URL = os.environ.get("M3U_URL", "https://live.catvod.com/?tk=883bbb11b5989f9103c729fc6d0cfa45")
OUTPUT = "output/playlist.m3u"

def main():
    try:
        # impersonate="chrome124" 模拟 Chrome 124 的完整指纹（TLS + HTTP/2 + Headers）
        resp = requests.get(URL, impersonate="chrome124", timeout=60)
        resp.raise_for_status()
        
        # 简单校验是否为 M3U 格式
        content = resp.text
        if not content.strip().startswith("#EXTM3U"):
            print("Warning: Response does not look like a valid M3U file.")
            print("First 200 chars:", content[:200])
            # 仍然保存，方便排查
        
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"Success: Saved {len(content)} bytes to {OUTPUT}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
