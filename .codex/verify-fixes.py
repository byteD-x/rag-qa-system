from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:5174"
REPORT = Path(".codex/verify-fixes-results.txt")


def inspect(page, viewport_name: str):
    messages = []
    page.on("console", lambda message: messages.append(f"console:{message.type}:{message.text}"))
    page.on("pageerror", lambda error: messages.append(f"pageerror:{error}"))

    page.goto(f"{BASE_URL}/workspace/chat", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    page.screenshot(path=f".codex/chat-{viewport_name}.png", full_page=True)

    composer = page.locator(".composer-container")
    input_box = page.locator(".modern-input textarea")
    sidebar = page.locator(".session-sidebar")
    result = {
        "url": page.url,
        "viewport": viewport_name,
        "composer_box": composer.bounding_box(),
        "input_box": input_box.bounding_box(),
        "chat_page_box": page.locator(".chat-page").bounding_box(),
        "workspace_content_box": page.locator(".workspace-content").bounding_box(),
        "chat_main_box": page.locator(".chat-main").bounding_box(),
        "viewport_size": page.evaluate("({ width: window.innerWidth, height: window.innerHeight })"),
        "live_region": page.locator('[role="status"]').count(),
        "send_label": page.locator(".modern-send-btn").get_attribute("aria-label"),
        "sidebar_aria_hidden": sidebar.get_attribute("aria-hidden") if sidebar.count() else None,
        "sidebar_inert": sidebar.get_attribute("inert") if sidebar.count() else None,
        "messages": messages,
    }

    if viewport_name == "mobile" and page.locator(".mobile-sidebar-toggle").count():
        page.locator(".mobile-sidebar-toggle").click()
        page.wait_for_timeout(100)
        result["opened_sidebar_active_element"] = page.evaluate("document.activeElement?.getAttribute('aria-label')")
        page.locator(".sidebar-close-btn").click()
        page.wait_for_timeout(100)
        result["closed_sidebar_active_element"] = page.evaluate("document.activeElement?.getAttribute('aria-label')")
        result["closed_sidebar_inert"] = sidebar.get_attribute("inert")

    return result


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.locator(".demo-btn").first.click()
    page.locator(".submit-button").click()
    page.wait_for_url("**/workspace/**", timeout=10000)
    page.goto(f"{BASE_URL}/workspace/chat", wait_until="domcontentloaded")
    mobile = inspect(page, "mobile")
    context.close()

    desktop_context = browser.new_context(viewport={"width": 1280, "height": 800})
    desktop_page = desktop_context.new_page()
    desktop_page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    desktop_page.locator(".demo-btn").first.click()
    desktop_page.locator(".submit-button").click()
    desktop_page.wait_for_url("**/workspace/**", timeout=10000)
    desktop_page.goto(f"{BASE_URL}/workspace/chat", wait_until="domcontentloaded")
    desktop = inspect(desktop_page, "desktop")
    desktop_context.close()
    browser.close()

REPORT.write_text(f"mobile={mobile}\ndesktop={desktop}\n", encoding="utf-8")
print(f"wrote {REPORT}")
