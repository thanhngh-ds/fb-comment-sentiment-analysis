import asyncio
import random
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def setup_browser_context(browser: Browser) -> BrowserContext:
    """Create a browser context with custom viewport and user-agent."""

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    return context


def wait_for_page_load(page: Page, timeout: int = 10) -> None:
    """Wait until the page finishes loading."""

    try:
        page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        # time.sleep(random.uniform(1, 2))

    except Exception:
        time.sleep(2)


def parse_facebook_number(num_str: str) -> int:
    num_str = num_str.lower().replace(",", "").strip()
    if "k" in num_str:
        return int(float(num_str.replace("k", "")) * 1_000)
    elif "m" in num_str:
        return int(float(num_str.replace("m", "")) * 1_000_000)
    return int(re.findall(r"\d+", num_str)[0])


def extract_engagement_metrics(page: Page) -> Dict[str, int]:
    """Extract reaction, comment, and share counts from the post."""

    metrics = {
        "reactions_count": 0,
        "comments_count": 0,
        "shares_count": 0,
    }

    reaction_selectors = ['span[aria-hidden="true"] span span']
    comment_selectors = ['span:has-text("comments")', 'span:has-text("bình luận")']

    def extract_from_selectors(selectors, metric_key):
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible():
                    text = element.inner_text(timeout=1000).strip().lower()
                    match = re.search(r"\d[\d,.]*[kKmM]?", text)
                    if match:
                        val = parse_facebook_number(match.group(0))
                        metrics[metric_key] = max(metrics[metric_key], val)
                        break
            except Exception:
                continue

    try:
        page.wait_for_selector(reaction_selectors[0], timeout=15000)
    except Exception:
        pass
    extract_from_selectors(reaction_selectors, "reactions_count")

    extract_from_selectors(comment_selectors, "comments_count")

    possible_share_spans = page.locator(
        'span.html-span:has-text("share"), span.html-span:has-text("lượt chia sẻ")'
    )
    for element in possible_share_spans.all():
        try:
            if element.is_visible():
                text = element.inner_text(timeout=1000).strip().lower()
                if re.search(r"\d[\d,.]*\s+(shares|chia sẻ|lượt chia sẻ)$", text):
                    match = re.search(r"\d[\d,.]*[kKmM]?", text)
                    if match:
                        val = parse_facebook_number(match.group(0))
                        metrics["shares_count"] = max(metrics["shares_count"], val)
                        break
        except Exception:
            continue

    return metrics


def extract_post_content(page: Page) -> str:
    """Extract main text content of the Facebook post."""

    try:
        element = page.locator('[data-ad-preview="message"]').first
        if element.is_visible():
            content = element.inner_text(timeout=3000)
            if content and len(content) > 0:
                return content.strip()
    except Exception:
        pass
    return ""


def extract_post_metadata(page: Page) -> Dict[str, str]:
    """Extract post metadata like author name."""

    metadata = {"author": ""}

    try:
        author_selectors = [
            'div[data-ad-rendering-role="profile_name"] h3 a[role="link"]'
        ]

        for selector in author_selectors:
            try:
                author_elem = page.locator(selector).first
                if author_elem.count() > 0:
                    metadata["author"] = author_elem.inner_text()
                    break
            except Exception:
                continue

    except Exception as e:
        print(f"Error extracting metadata: {e}")

    return metadata


def extract_comments(page: Page) -> List[Dict[str, str]]:
    """Extract visible comments from the post area."""

    comments = []

    try:
        # Click the "Most relevant" button
        try:
            most_relevant = page.locator('span:has-text("Most relevant")').first
            if most_relevant.count() > 0:
                most_relevant.click()
                time.sleep(1)
        except Exception:
            print("Could not find or click 'Most relevant'.")

        # Click "All comments" if available
        try:
            all_comments_btn = page.locator(
                'span:has-text("Show all comments, including potential spam.")'
            ).first
            if all_comments_btn.count() > 0:
                all_comments_btn.click()
                time.sleep(2)
        except Exception:
            print("Could not find or click 'All comments'.")

        # Scroll down to load all comments
        try:
            scrollable_container = page.locator(
                "div.xb57i2i.x1q594ok.x5lxg6s.x78zum5.xdt5ytf.x6ikm8r.x1ja2u2z.x1pq812k.x1rohswg"
                ".xfk6m8.x1yqm8si.xjx87ck.xx8ngbg.xwo3gff.x1n2onr6.x1oyok0e.x1odjw0f.x1iyjqo2.xy5w88m"
            ).first
            previous_height = scrollable_container.evaluate("(el) => el.scrollHeight")

            for _ in range(1000):
                scrollable_container.evaluate("(el) => el.scrollBy(0, 1500)")
                time.sleep(random.uniform(1, 2))

                current_height = scrollable_container.evaluate(
                    "(el) => el.scrollHeight"
                )
                if current_height == previous_height:
                    scrollable_container.evaluate("(el) => el.scrollBy(0, 2500)")
                    time.sleep(random.uniform(1, 2))

                    current_height = scrollable_container.evaluate(
                        "(el) => el.scrollHeight"
                    )
                    if current_height == previous_height:
                        break

                previous_height = current_height
        except Exception as e:
            print(f"Scroll error: {e}")

        # Extract comments
        comment_elements = page.locator(
            "div.html-div.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.x18d9i69.x1g0dm76.xpdmqnj.x1n2onr6 "
            'div[dir="auto"][style="text-align: start;"]'
        ).all()

        for el in comment_elements:
            try:
                # Extract main text
                comment_text = el.inner_text().strip()

                # Add emojis (if any)
                emojis = el.locator("img[alt]").all()
                for emoji in emojis:
                    alt = emoji.get_attribute("alt")
                    if alt:
                        comment_text += f" {alt}"

                # Append to list
                comments.append(
                    {
                        "comments_text": comment_text,
                    }
                )

            except Exception:
                continue

    except Exception as e:
        print(f"Error extracting comments: {e}")

    return comments


def crawl_facebook_post(page: Page, url: str) -> Dict[str, Any]:
    """Crawl all post data including content, metadata, and comments."""

    try:
        page.goto(url, timeout=30000)
        wait_for_page_load(page)

        # Extract data
        content = extract_post_content(page)
        metadata = extract_post_metadata(page)
        metrics = extract_engagement_metrics(page)
        comments = extract_comments(page)

        result = {
            "url": url,
            "author": metadata["author"],
            "content": content,
            "reactions_count": metrics["reactions_count"],
            "comments_count": metrics["comments_count"],
            "shares_count": metrics["shares_count"],
            "comments": comments,
        }

        return result

    except Exception:
        raise RuntimeError(
            f"Không thể thu thập dữ liệu từ liên kết: {url}. Vui lòng kiểm tra lại liên kết hoặc thử lại sau."
        )


def check_post_links(post_links: Optional[List[str]] = None) -> bool:
    """Validate the format of Facebook post URLs."""

    if not post_links:
        raise ValueError(
            "Bạn chưa nhập đường dẫn nào. Vui lòng nhập ít nhất 1 liên kết bài viết."
        )

    for link in post_links:
        if not re.match(r"https?://www\.facebook\.com/[^/]+/posts/[\w\d]+", link):
            raise ValueError(f"Liên kết không hợp lệ: {link}")

    return True


def run_facebook_crawling(
    post_links: Optional[List[str]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Crawl multiple Facebook posts and return their data as DataFrames."""

    print("\nCrawling data from Facebook posts...")

    try:
        check_post_links(post_links)
    except ValueError as e:
        raise ValueError(str(e))

    posts_summary = []
    all_comments = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        try:
            context = setup_browser_context(browser)
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.accept())

            for i, url in enumerate(post_links, 1):
                try:
                    data = crawl_facebook_post(page, url)
                except RuntimeError as e:
                    print(str(e))
                    continue

                posts_summary.append(
                    {
                        "url": data["url"],
                        "author": data["author"],
                        "content": data["content"],
                        "reactions_count": data["reactions_count"],
                        "comments_count": data["comments_count"],
                        "shares_count": data["shares_count"],
                        "total_comments_crawled": len(data["comments"]),
                    }
                )

                comments = data.get("comments")

                if isinstance(comments, list) and comments:
                    all_comments.extend(
                        [
                            {"url": data["url"], "comment_text": c["comments_text"]}
                            for c in comments
                        ]
                    )
                else:
                    all_comments.append({"url": data["url"], "comment_text": ""})

                if on_progress:
                    on_progress(i, len(post_links))

                if i < len(post_links):
                    time.sleep(random.uniform(1, 2))
        finally:
            browser.close()

    return pd.DataFrame(posts_summary), pd.DataFrame(all_comments)


if __name__ == "__main__":
    try:
        post_links = []
        print("Nhập các liên kết bài viết Facebook (gõ 'done' để kết thúc):")
        while True:
            link = input("Link: ").strip()
            if link.lower() == "done":
                break
            if link:
                post_links.append(link)

        df_posts, df_comments = run_facebook_crawling(post_links)

        if df_posts is None or df_comments is None:
            print(
                "Không thể thu thập dữ liệu. Vui lòng kiểm tra các liên kết và thử lại."
            )
        else:
            print("\nĐã thu thập xong!")
            print("Thống kê:")
            print(f"   - Số bài viết: {len(df_posts)}")
            print(f"   - Tổng số bình luận: {len(df_comments)}")
            total_reactions = df_posts["reactions_count"].fillna(0).sum()
            total_shares = df_posts["shares_count"].fillna(0).sum()
            print(f"   - Tổng số lượt cảm xúc: {int(total_reactions)}")
            print(f"   - Tổng số lượt chia sẻ: {int(total_shares)}")

    except ValueError as e:
        print(f"Lỗi: {e}")

    except Exception:
        print("Đã xảy ra lỗi không xác định. Vui lòng thử lại hoặc kiểm tra mã nguồn.")
