#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _click_first(page, selectors: list[str], timeout_ms: int = 2000) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
            if count <= 0:
                continue
            for idx in range(count):
                target = locator.nth(idx)
                try:
                    if not target.is_visible():
                        continue
                    target.scroll_into_view_if_needed(timeout=timeout_ms)
                    target.click(timeout=timeout_ms)
                    return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def _fill_first(page, selectors: list[str], text: str, timeout_ms: int = 2000) -> bool:
    if not text:
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() <= 0:
                continue
            locator.fill(text, timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _upload_first(page, selectors: list[str], file_path: Path, timeout_ms: int = 2000) -> bool:
    if not file_path.exists():
        return False
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() <= 0:
                continue
            locator.set_input_files(str(file_path), timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def run_apply_test(
    platform: str,
    url: str,
    resume_path: Path | None,
    cover_letter: str,
    submit: bool,
) -> int:
    profile_dir = Path(".browser_profiles") / platform
    profile_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = Path("outputs")
    debug_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 960},
        )
        page = context.new_page()

        print(f"[{platform}] 開啟職缺頁: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(debug_dir / f"apply_{platform}_00_open.png"), full_page=True)

        print(f"[{platform}] 請先確認已登入（必要時手動登入後回終端按 Enter）")
        input()
        if any(x in page.url for x in ["login", "accounts.google.com", "sign-in", "users/sign-in"]):
            print(f"[{platform}] 目前仍在登入頁，請在瀏覽器完成登入並回到職缺頁，再按 Enter。")
            input()
            if page.url != url:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(1200)

        # Try to enter the application flow.
        apply_selectors = [
            'button:has-text("立即應徵")',
            'a:has-text("立即應徵")',
            'button:has-text("應徵")',
            'a:has-text("應徵")',
            'a[href*="users/sign-up?job="]',
            'a[href*="users/sign-in?job="]',
            'a[href*="login.104.com.tw/login"]',
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            'button:has-text("我要應徵")',
            'a:has-text("我要應徵")',
        ]
        clicked_apply = _click_first(page, apply_selectors)
        print(f"[{platform}] 點擊應徵按鈕: {'成功' if clicked_apply else '未找到'}")
        page.wait_for_timeout(1800)
        page.screenshot(path=str(debug_dir / f"apply_{platform}_01_after_apply_click.png"), full_page=True)

        if resume_path:
            resume_selectors = [
                'input[type="file"]',
                'input[accept*="pdf"]',
                'input[name*="resume" i]',
                'input[id*="resume" i]',
            ]
            uploaded = _upload_first(page, resume_selectors, resume_path)
            print(f"[{platform}] 上傳履歷: {'成功' if uploaded else '未偵測到可上傳欄位'}")

        if cover_letter:
            cover_selectors = [
                'textarea[name*="cover" i]',
                'textarea[id*="cover" i]',
                'textarea[placeholder*="自我介紹"]',
                'textarea[placeholder*="cover"]',
                'textarea[placeholder*="介紹"]',
                "textarea",
            ]
            filled = _fill_first(page, cover_selectors, cover_letter)
            print(f"[{platform}] 填寫 cover letter: {'成功' if filled else '未偵測到文字欄位'}")

        page.wait_for_timeout(1000)
        page.screenshot(path=str(debug_dir / f"apply_{platform}_02_ready_to_submit.png"), full_page=True)

        submit_selectors = [
            'button:has-text("送出")',
            'button:has-text("提交")',
            'button:has-text("確認送出")',
            'button:has-text("Apply")',
            'button:has-text("Submit")',
            'button[type="submit"]',
        ]
        submit_locator = None
        for selector in submit_selectors:
            loc = page.locator(selector).first
            try:
                if loc.count() > 0:
                    submit_locator = loc
                    break
            except PlaywrightTimeoutError:
                continue

        if submit_locator is None:
            print(f"[{platform}] 未偵測到送出按鈕，請手動檢查頁面。")
            print(f"[{platform}] 已截圖: {debug_dir / f'apply_{platform}_02_ready_to_submit.png'}")
            context.close()
            return 1

        print(f"[{platform}] 已到送出前。")
        if not submit:
            print(f"[{platform}] 測試模式：不送出。")
            context.close()
            return 0

        print(f"[{platform}] 請確認是否送出。輸入 SEND 才會真的送出，其餘取消。")
        confirm = input().strip()
        if confirm != "SEND":
            print(f"[{platform}] 已取消送出。")
            context.close()
            return 0

        submit_locator.click(timeout=5000)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(debug_dir / f"apply_{platform}_03_submitted.png"), full_page=True)
        print(f"[{platform}] 已送出（請人工再次確認頁面狀態）。")
        context.close()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="104/Cake 測試投遞腳本（送出前確認）")
    parser.add_argument("--platform", choices=["104", "cake"], required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--resume-path", default="")
    parser.add_argument("--cover-letter", default="")
    parser.add_argument("--submit", action="store_true", help="啟用真實送出（仍需輸入 SEND 確認）")
    args = parser.parse_args()

    resume_path = Path(args.resume_path).expanduser().resolve() if args.resume_path else None
    return run_apply_test(
        platform=args.platform,
        url=args.url,
        resume_path=resume_path,
        cover_letter=args.cover_letter,
        submit=args.submit,
    )


if __name__ == "__main__":
    sys.exit(main())
