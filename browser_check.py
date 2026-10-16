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
        page = browser.new_page(viewport={"width": 1512, "height": 1100}, color_scheme="light")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.wait_for_function("() => config !== null && !document.getElementById('classify').disabled")
        assert page.locator("#mode").count() == 0
        assert page.evaluate("typeof rehearsal") == "undefined"
        assert page.evaluate("SAMPLES.every(sample => !['score', 'escalation', 'salesScore', 'salesEscalation', 'probabilities'].some(key => key in sample))")
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
        assert page.evaluate("incidents.find(incident => incident.id === selected).result") is None
        assert not page.locator("#classify").is_disabled()
        page.unroute("**/api/decision")

        assert page.locator(".workspace > *").count() == 2
        assert page.locator("#stream, #rescore, #reset, #threshold, #escalate-threshold, #rubric").count() == 0
        for incident_id in page.evaluate("SAMPLES.map(sample => sample.id)"):
            page.locator(f"[data-id='{incident_id}']").click()
            page.locator("#incident-text").fill(page.evaluate("SAMPLES.find(sample => sample.id === selected).message"))
            page.locator("#classify").click()
            page.wait_for_selector("#decision-results", timeout=90_000)
            result = page.evaluate("incidents.find(incident => incident.id === selected).result")
            assert result["source"] == "live"
            assert result["raw"]["model"].lower() == "microsoft-decision-1"
        assert page.locator("#k-count").inner_text() == "9 / 9"
        assert page.locator("#k-latency").inner_text() != "--"
        assert page.locator("#k-cost").inner_text() != "--"
        page.locator("[data-id='INC-003']").click()
        page.locator("#context").click()
        assert page.locator("#decision-results").count() == 0
        page.locator("#classify").click()
        page.wait_for_selector("#decision-results", timeout=90_000)
        result = page.evaluate("incidents.find(incident => incident.id === selected).result")
        assert result["source"] == "live"
        assert "Payment authorization returns HTTP 500" in result["input"]
        page.locator("#view-request").click()
        page.locator("#request-rubric").select_option("sales")
        page.locator("#tab-operations").click()
        page.locator("[data-id='INC-006']").click()
        page.locator("#classify").click()
        page.wait_for_selector("#decision-results", timeout=90_000)
        result = page.evaluate("incidents.find(incident => incident.id === selected).result")
        assert result["source"] == "live"
        assert result["rubric"] == "sales"
        assert result["severity"] == result["raw"]["answers"]["severity"]["score"]
        page.screenshot(path=str(output / "operations.png"), full_page=True)

        page.locator("#theme").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
        page.screenshot(path=str(output / "dark.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile content overflows"
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1512, "height": 1100})
        page.locator("#theme").click()

        page.locator("#tab-input").click()
        page.locator("#request-rubric").select_option("standard")
        page.locator("#tab-evaluate").click()
        config = page.evaluate("config")
        assert config["baseline_model_name"] in page.locator("#comparison").inner_text()
        assert f"reasoning: {config['baseline_reasoning_effort']}" in page.locator("#comparison").inner_text()
        page.locator("#run-eval").click()
        page.wait_for_function("() => evaluation?.finished_at && !document.getElementById('run-eval').disabled", timeout=240_000)
        result = page.evaluate("evaluation")
        assert result["status"] == "completed", result
        failures = [(row["id"], model, row[model].get("error")) for row in result["rows"] for model in ("decision", "baseline") if row[model].get("error")]
        assert not failures, failures
        assert len(result["rows"]) == 9
        assert all(row[model]["result"]["source"] == "live" for row in result["rows"] for model in ("decision", "baseline"))
        assert result["baseline_deployment"] == config["baseline_deployment"]
        assert result["baseline_reasoning_effort"] == config["baseline_reasoning_effort"]
        if config["baseline_priced"]:
            assert all(row["baseline"]["result"]["cost_usd"] is not None for row in result["rows"])
        (output / "live-evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        page.screenshot(path=str(output / "comparison.png"), full_page=True)
        print(json.dumps({"decision": page.evaluate("metrics('decision')"), "baseline": page.evaluate("metrics('baseline')")}, indent=2))

        page.route("**/api/decision", lambda route: route.fulfill(status=502, json={"error": "Deliberate warm-up failure"}))
        page.locator("#run-eval").click()
        page.wait_for_function("() => evaluation?.finished_at && !document.getElementById('run-eval').disabled")
        assert page.evaluate("evaluation.status") == "warmup failed"
        assert "Deliberate warm-up failure" in page.locator("#error").inner_text()
        assert page.evaluate("evaluation.rows.every(row => !row.decision && !row.baseline)")

        for failure in ("http", "network"):
            unavailable = browser.new_page()
            unavailable.on("pageerror", lambda error: errors.append(str(error)))
            if failure == "http":
                unavailable.route("**/api/config", lambda route: route.fulfill(status=503, json={"error": "Backend unavailable"}))
            else:
                unavailable.route("**/api/config", lambda route: route.abort("failed"))
            unavailable.goto(args.url)
            unavailable.wait_for_selector("#error:not([hidden])")
            assert "Live backend unavailable" in unavailable.locator("#error").inner_text()
            assert unavailable.locator("#classify").is_disabled()
            assert unavailable.locator("#run-eval").is_disabled()
            unavailable.locator("[data-id='INC-003']").click()
            assert unavailable.locator("#classify").is_disabled()
            assert unavailable.locator("#context").is_disabled()
            assert unavailable.locator("#decision-results").count() == 0
            assert unavailable.locator("#k-count").inner_text() == "0 / 9"
            unavailable.close()

        offline = browser.new_page()
        offline.on("pageerror", lambda error: errors.append(str(error)))
        offline.goto((Path(__file__).parent / "index.html").resolve().as_uri())
        assert offline.locator("#classify").is_disabled()
        assert offline.locator("#run-eval").is_disabled()
        assert "Start python app.py" in offline.locator("#error").inner_text()
        assert offline.locator("#decision-results").count() == 0
        assert not errors, errors
        browser.close()
    print("Browser integration OK: live-only inference, unavailable backend, errors, inspector, rubric, mobile, dark, comparison.")


if __name__ == "__main__":
    main()
