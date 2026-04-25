"""
Standalone script that runs JS in a browser.
Reads JSON from stdin, writes JSON result to stdout.

stdin can be either:
  - Plain JS string (legacy — navigates to music.apple.com + waits for MusicKit)
  - JSON object:
      {
        "js":                "...",   # required — JS to evaluate
        "arg":               <value>, # optional — passed as 2nd arg to page.evaluate
        "url":               "...",   # optional — URL to navigate to (default: music.apple.com)
        "no_musickit":       true,    # optional — skip MusicKit auth wait
        "capture_responses": "..."    # optional — URL substring; matching JSON responses
                                      #   are collected and returned as result["captured"]
      }
"""
import json
import os
import sys
from playwright.sync_api import sync_playwright

STATE_PATH = os.path.expanduser("~/.config/apple-music-mcp/browser_state.json")
BASE_URL = "https://music.apple.com"


def main():
    raw = sys.stdin.read()

    js = raw
    arg = None
    url = BASE_URL
    no_musickit = False
    capture_pattern = None

    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "js" in data:
            js = data["js"]
            arg = data.get("arg")
            url = data.get("url", BASE_URL)
            no_musickit = bool(data.get("no_musickit", False))
            capture_pattern = data.get("capture_responses")  # URL substring to capture
    except Exception:
        pass

    if not no_musickit and not os.path.exists(STATE_PATH):
        print(json.dumps({"error": "Not authorized. Run auth.py first."}))
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        if os.path.exists(STATE_PATH):
            ctx_kwargs["storage_state"] = STATE_PATH
        context = browser.new_context(**ctx_kwargs)

        if no_musickit:
            # Hide automation fingerprints so sites like Spotify don't detect headless Chrome
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
            """)

        page = context.new_page()

        # Set up response capture BEFORE navigating so we don't miss early requests
        captured = []
        if capture_pattern:
            def on_response(response):
                if capture_pattern in response.url:
                    try:
                        body = response.json()
                        captured.append({"url": response.url, "body": body})
                    except Exception:
                        pass
            page.on("response", on_response)

        wait_until = "networkidle" if no_musickit else "load"
        page.goto(url, wait_until=wait_until, timeout=60000)

        if not no_musickit:
            page.wait_for_function("""
                () => {
                    try {
                        const mk = MusicKit.getInstance();
                        return mk && mk.isAuthorized;
                    } catch(e) { return false; }
                }
            """, timeout=30000)

        if arg is not None:
            js_result = page.evaluate(js, arg)
        else:
            js_result = page.evaluate(js)

        browser.close()

    if capture_pattern:
        result = {"js_result": js_result, "captured": captured}
    else:
        result = js_result

    print(json.dumps(result))


if __name__ == "__main__":
    main()
