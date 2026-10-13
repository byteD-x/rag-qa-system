from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    for path, heading in (("/register", "注册账号"), ("/password-reset", "找回密码")):
        page.goto(f"http://127.0.0.1:5174{path}")
        page.wait_for_load_state("networkidle")
        assert page.get_by_role("heading", name=heading).is_visible()
        assert page.locator("input").count() >= 1
    page.goto("http://127.0.0.1:5174/login")
    page.wait_for_load_state("networkidle")
    assert page.get_by_role("link", name="注册新账号").is_visible()
    assert page.get_by_role("link", name="忘记密码？").is_visible()
    page.screenshot(path=".codex/auth-pages-mobile.png", full_page=True)
    browser.close()
