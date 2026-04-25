"""
Run this once to sign into Apple Music and save your browser session.
Usage: uv run python auth.py
"""

import json
import os
from playwright.sync_api import sync_playwright

CONFIG_DIR = os.path.expanduser("~/.config/apple-music-mcp")
STATE_PATH = os.path.join(CONFIG_DIR, "browser_state.json")


def main():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    print("\n=== Apple Music Authorization ===")
    print("A browser window will open. Sign into Apple Music, then come back here.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://music.apple.com")
        page.wait_for_function("typeof MusicKit !== 'undefined'", timeout=30000)

        print("Sign in with your Apple ID in the browser.")
        print("Once you can see your Apple Music library, press Enter here...")
        input()

        # Save the full browser storage state (cookies + localStorage)
        context.storage_state(path=STATE_PATH)
        browser.close()

    print(f"\n✅ Session saved to {STATE_PATH}")
    print("Your Apple Music MCP is ready! Restart Claude Code.")


if __name__ == "__main__":
    main()
