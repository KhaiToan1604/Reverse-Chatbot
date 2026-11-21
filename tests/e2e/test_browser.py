"""E2E trình duyệt (Playwright + Chromium) trên giao diện React đã build."""

import pytest

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def page(live_server):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_default_timeout(15000)
        yield pg
        browser.close()


def test_learner_completes_quiz(page, live_server):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(live_server)
    page.get_by_role("textbox").first.fill("Sinh viên E2E")
    page.get_by_role("button", name="Bắt đầu").click()
    page.get_by_role("button", name="Bắt đầu học").click()
    for _ in range(10):
        if page.get_by_role("button", name="Gửi đáp án").count() == 0:
            page.get_by_role("button", name="Gửi đáp án").wait_for(state="visible")
        radios = page.locator("input[name=choice]")
        if radios.count():
            radios.first.check()
        elif page.get_by_label("Đáp án của bạn").count():
            page.get_by_label("Đáp án của bạn").fill("thẻ sinh viên")
        else:
            page.locator("textarea").first.fill("Cần mang thẻ sinh viên và làm thủ tục mượn sách")
        page.get_by_role("button", name="Gửi đáp án").click()
        nxt = page.get_by_role("button", name="Câu tiếp theo").or_(page.get_by_role("button", name="Xem kết quả"))
        nxt.wait_for(state="visible")
        done = nxt.inner_text() == "Xem kết quả"
        nxt.click()
        if done:
            break
    else:
        pytest.fail("Phiên học không kết thúc")
    page.get_by_role("button", name="Học tiếp").wait_for(state="visible")
    assert not errors


def test_admin_unlocks_with_key_and_lists_documents(page, live_server):
    from tests.e2e.conftest import ADMIN_KEY

    page.goto(f"{live_server}/#/admin")
    page.locator("input[type=password]").fill(ADMIN_KEY)
    page.get_by_role("button", name="Mở khoá").click()
    page.get_by_role("tab").first.wait_for(state="visible")
    assert page.get_by_role("tab").count() >= 2
