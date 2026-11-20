from playwright.sync_api import sync_playwright
from pathlib import Path

URL = "https://www.bisefsd.edu.pk/MatricResults.aspx"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("\nOpening BISE Faisalabad website...")

    try:
        response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        print("\n========== WEBSITE STATUS ==========")
        print("HTTP Status:", response.status if response else "Unknown")
        print("Page title:", page.title())
        print("Current URL:", page.url)

        print("\n========== DROPDOWN MENUS ==========")
        for i, select in enumerate(page.locator("select").all()):
            print(f"\nDropdown {i + 1}")
            print("ID:", select.get_attribute("id"))
            print("Name:", select.get_attribute("name"))
            print("Options:")
            for option in select.locator("option").all():
                print("  ", option.inner_text().strip(),
                      "| value:", option.get_attribute("value"))

        print("\n========== INPUT FIELDS ==========")
        for i, field in enumerate(page.locator("input").all()):
            print(
                i + 1,
                "type:", field.get_attribute("type"),
                "| id:", field.get_attribute("id"),
                "| name:", field.get_attribute("name"),
                "| placeholder:", field.get_attribute("placeholder")
            )

        print("\n========== BUTTONS ==========")
        for i, button in enumerate(page.locator(
            "button, input[type=submit], input[type=button]"
        ).all()):
            print(
                i + 1,
                "| text:", button.inner_text().strip() if button.evaluate(
                    "(e) => e.tagName === 'BUTTON'"
                ) else "",
                "| value:", button.get_attribute("value"),
                "| id:", button.get_attribute("id"),
                "| name:", button.get_attribute("name")
            )

        print("\n========== TABLES ==========")
        for i, table in enumerate(page.locator("table").all()):
            print(f"\nTable {i + 1}:")
            print(table.inner_text()[:1500])

        html_path = Path("bise_website_inspection.html")
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path="bise_website_inspection.png", full_page=True)

        print("\n========== FILES SAVED ==========")
        print("HTML:", html_path.resolve())
        print("Screenshot:", Path("bise_website_inspection.png").resolve())

        print("\nInspection complete. Browser will remain open for 15 seconds.")
        page.wait_for_timeout(15000)

    except Exception as e:
        print("\nINSPECTION ERROR:", repr(e))

    finally:
        browser.close()
