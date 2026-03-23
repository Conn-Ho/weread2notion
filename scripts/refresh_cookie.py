"""
自动刷新微信读书 Cookie 并更新 GitHub Secret
使用 Playwright 无头浏览器访问 weread.qq.com，提取刷新后的 cookie
"""
import asyncio
import base64
import os
import sys

import requests
from playwright.async_api import async_playwright

WEREAD_URL = "https://weread.qq.com"
REPO = "Conn-Ho/weread2notion"
SECRET_NAME = "WEREAD_COOKIE"


def parse_cookie_str(cookie_str: str) -> list[dict]:
    """将 cookie 字符串解析为 Playwright 格式"""
    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".weread.qq.com",
            "path": "/",
        })
    return cookies


async def get_fresh_cookie(old_cookie_str: str) -> str:
    """用 Playwright 刷新 cookie"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_cookies(parse_cookie_str(old_cookie_str))

        page = await context.new_page()
        print("正在访问微信读书...")
        await page.goto(WEREAD_URL, wait_until="networkidle", timeout=30000)

        # 检查是否登录成功
        title = await page.title()
        print(f"页面标题: {title}")

        all_cookies = await context.cookies(WEREAD_URL)
        wr_cookies = [c for c in all_cookies if c["name"].startswith("wr_")]
        if not wr_cookies:
            print("警告: 未找到 wr_ 开头的 cookie，可能登录失败")

        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
        await browser.close()
        print(f"成功提取 {len(all_cookies)} 个 cookie")
        return cookie_str


def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """用仓库公钥加密 secret（GitHub 要求）"""
    from nacl import encoding, public
    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    encrypted = box.encrypt(secret_value.encode())
    return base64.b64encode(encrypted).decode()


def update_github_secret(pat: str, new_cookie: str):
    """通过 GitHub API 更新 Secret"""
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }

    # 获取仓库公钥
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers=headers,
    )
    r.raise_for_status()
    key_data = r.json()

    encrypted = encrypt_secret(key_data["key"], new_cookie)

    r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{SECRET_NAME}",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
    )
    r.raise_for_status()
    print(f"✅ GitHub Secret [{SECRET_NAME}] 更新成功")


async def main():
    old_cookie = os.getenv("WEREAD_COOKIE")
    pat = os.getenv("GH_PAT")

    if not old_cookie:
        print("错误: 未设置 WEREAD_COOKIE 环境变量")
        sys.exit(1)
    if not pat:
        print("错误: 未设置 GH_PAT 环境变量")
        sys.exit(1)

    new_cookie = await get_fresh_cookie(old_cookie)
    update_github_secret(pat, new_cookie)


if __name__ == "__main__":
    asyncio.run(main())
