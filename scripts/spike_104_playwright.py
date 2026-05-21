#!/usr/bin/env python3
"""Smoke-test whether Playwright can reach 104 search/API from GitHub Actions."""

from __future__ import annotations

import json
import os
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _is_cloudflare_challenge(text: str, title: str) -> bool:
    haystack = f"{title}\n{text}".lower()
    return any(
        marker in haystack
        for marker in (
            "just a moment",
            "cf-mitigated",
            "cloudflare",
            "verify you are human",
            "checking your browser",
        )
    )


def main() -> int:
    keyword = os.getenv("WEB104_KEYWORD", "產品經理").strip() or "產品經理"
    area = os.getenv("WEB104_AREA", "6001001000").strip() or "6001001000"
    order = os.getenv("WEB104_ORDER", "15").strip() or "15"
    asc = os.getenv("WEB104_ASC", "0").strip() or "0"
    api_url = os.getenv(
        "WEB104_API_URL", "https://www.104.com.tw/jobs/search/api/jobs"
    ).strip()
    search_params = {
        "keyword": keyword,
        "area": area,
        "page": "1",
        "order": order,
        "asc": asc,
        "mode": "s",
        "jobsource": "2018indexpoc",
    }
    search_url = f"https://www.104.com.tw/jobs/search/?{urlencode({'keyword': keyword, 'area': area})}"
    api_with_query = f"{api_url}?{urlencode(search_params)}"

    result: dict[str, object] = {
        "keyword": keyword,
        "area": area,
        "search_url": search_url,
        "api_url": api_with_query,
        "search_loaded": False,
        "challenge_detected": False,
        "api_status": None,
        "api_content_type": None,
        "api_job_count": None,
        "api_body_head": "",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        page = context.new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            result["search_loaded"] = True
        except PlaywrightTimeoutError as exc:
            result["search_error"] = f"timeout: {exc}"

        title = page.title()
        body_text = page.locator("body").inner_text(timeout=10_000) if result["search_loaded"] else ""
        result["search_title"] = title
        result["challenge_detected"] = _is_cloudflare_challenge(body_text, title)
        result["search_body_head"] = body_text[:500]

        page_api = page.evaluate(
            """async ({ url }) => {
                const response = await fetch(url, {
                    headers: { "Accept": "application/json, text/plain, */*" },
                    credentials: "include"
                });
                return {
                    status: response.status,
                    contentType: response.headers.get("content-type"),
                    body: await response.text()
                };
            }""",
            {"url": api_with_query},
        )
        result["api_method"] = "page.fetch"
        result["api_status"] = page_api["status"]
        result["api_content_type"] = page_api["contentType"]
        body = page_api["body"]
        if result["api_status"] == 403:
            response = context.request.get(
                api_with_query,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": search_url,
                },
                timeout=30_000,
            )
            result["api_method"] = "context.request"
            result["api_status"] = response.status
            result["api_content_type"] = response.headers.get("content-type")
            body = response.text()
        result["api_body_head"] = body[:500]
        try:
            payload = json.loads(body)
            data = payload.get("data")
            if isinstance(data, list):
                result["api_job_count"] = len(data)
        except json.JSONDecodeError:
            pass
        finally:
            browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["api_status"] == 200 and result["api_job_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
