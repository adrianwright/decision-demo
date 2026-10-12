"""Optional browser integration check; requires playwright and installed Edge."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    output = Path("test-results")
    output.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1512, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_function("() => document.getElementById('mode').value === 'live'")
        page.locator("#classify").click()
        page.wait_for_selector("#decision-results", timeout=90_000)
        config = page.evaluate("config")
        assert f"LIVE / {config['decision_deployment']}" in page.locator("#detail").inner_text()

        page.locator("#incident-text").fill("<img src=x onerror=alert(1)> altered incident")
        assert page.locator("#decision-results").count() == 0
        assert page.locator("#k-count").inner_text() == "0 / 9"
        assert page.locator("#queue img").count() == 0

        page.route("**/api/decision", lambda route: route.fulfill(status=502, content_type="application/json", body='{"error":"Deliberate integration failure"}'))
        page.locator("#classify").click()
        page.wait_for_selector("#error:not([hidden])")
        assert "Deliberate integration failure" in page.locator("#error").inner_text()
        assert page.locator("#decision-results").count() == 0
        assert page.locator("#mode").input_value() == "live"
        page.unroute("**/api/decision")

        page.locator("#mode").select_option("rehearsal")
        page.locator("#stream").click()
        page.wait_for_function("() => document.getElementById('k-count').textContent === '9 / 9'", timeout=20_000)
        page.wait_for_function("() => !document.getElementById('reset').disabled")
        assert page.locator("#k-latency").inner_text() == "--"
        assert page.locator("#k-cost").inner_text() == "--"
        page.locator("[data-id='INC-003']").click()
        assert "Hold routing for human review" in page.locator("#detail").inner_text()
        page.locator("#context").click()
        page.locator("#classify").click()
        page.wait_for_selector("#decision-results")
        assert "Eligible for automatic routing" in page.locator("#detail").inner_text()
        page.locator("#rubric").select_option("sales")
        page.locator("#rescore").click()
        page.wait_for_function("() => !document.getElementById('reset').disabled", timeout=20_000)
        page.locator("[data-id='INC-006']").click()
        assert "2.91" in page.locator("#detail").inner_text()
        page.screenshot(path=str(output / "operations.png"), full_page=True)

        page.locator("#theme").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
        page.screenshot(path=str(output / "dark.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile content overflows"
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1512, "height": 1100})
        page.locator("#theme").click()

        page.locator("#mode").select_option("live")
        page.locator("#rubric").select_option("standard")
        page.locator("#tab-evaluate").click()
        config = page.evaluate("config")
        assert config["baseline_model_name"] in page.locator("#comparison").inner_text()
        assert f"reasoning: {config['baseline_reasoning_effort']}" in page.locator("#comparison").inner_text()
        page.locator("#run-eval").click()
        page.wait_for_function("() => !document.getElementById('export').disabled", timeout=240_000)
        result = page.evaluate("evaluation")
        assert result["status"] == "completed", result
        failures = [(row["id"], model, row[model].get("error")) for row in result["rows"] for model in ("decision", "baseline") if row[model].get("error")]
        assert not failures, failures
        assert len(result["rows"]) == 9
        assert result["baseline_deployment"] == config["baseline_deployment"]
        assert result["baseline_reasoning_effort"] == config["baseline_reasoning_effort"]
        if config["baseline_priced"]:
            assert all(row["baseline"]["result"]["cost_usd"] is not None for row in result["rows"])
        (output / "live-evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        page.screenshot(path=str(output / "comparison.png"), full_page=True)
        assert not errors, errors
        print(json.dumps({"decision": page.evaluate("metrics('decision')"), "baseline": page.evaluate("metrics('baseline')")}, indent=2))

        offline = browser.new_page()
        offline.goto((Path(__file__).parent / "index.html").resolve().as_uri())
        assert offline.locator("#mode").input_value() == "rehearsal"
        offline.locator("#classify").click()
        assert "REHEARSAL / authored fixture" in offline.locator("#detail").inner_text()
        browser.close()
    print("Browser integration OK: live, offline, errors, streaming, rubric, mobile, dark, comparison.")


if __name__ == "__main__":
    main()
