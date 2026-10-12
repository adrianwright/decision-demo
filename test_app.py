import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import DemoError, Foundry, Handler, TEAMS, decision_request, questions, read_baseline, read_decision, validate_input


def decision_payload():
    return {
        "answers": {
            "team": {"type": "choice", "choice": "payments", "probabilities": dict(zip(TEAMS, [.96, .01, .01, .01, .01]))},
            "severity": {"type": "score", "score": 2.9, "probabilities": {"0": 0, "1": 0, "2": .1, "3": .9}},
            "escalate": {"type": "noul", "noul": .98},
        },
        "usage": {"input_tokens": 100, "output_tokens": 3},
    }


class ParsingTests(unittest.TestCase):
    def test_real_decision_shape(self):
        result = read_decision(decision_payload())
        self.assertEqual(result["team"], "payments")
        self.assertEqual(result["confidence"], .96)
        self.assertEqual(result["severity"], 2.9)
        self.assertEqual(result["escalation"], .98)

    def test_reject_bad_decision(self):
        for field, value in (("score", float("nan")), ("score", 4), ("score", True)):
            payload = decision_payload()
            payload["answers"]["severity"][field] = value
            with self.assertRaises(DemoError):
                read_decision(payload)
        for payload in ({}, {"answers": []}, {"answers": {"team": None}}):
            with self.assertRaises(DemoError):
                read_decision(payload)
        payload = decision_payload()
        payload["answers"]["team"]["choice"] = []
        with self.assertRaises(DemoError):
            read_decision(payload)

    def test_reject_invalid_distribution(self):
        payload = decision_payload()
        payload["answers"]["team"]["probabilities"]["payments"] = .5
        with self.assertRaises(DemoError):
            read_decision(payload)
        payload = decision_payload()
        del payload["answers"]["team"]["probabilities"]["uncertain"]
        with self.assertRaises(DemoError):
            read_decision(payload)

    def test_usage_not_invented(self):
        payload = decision_payload()
        del payload["usage"]
        with self.assertRaises(DemoError):
            read_decision(payload)

    def test_baseline_no_fabricated_confidence(self):
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"team": "payments", "severity": 3, "escalate": True})}}], "usage": {"prompt_tokens": 180, "completion_tokens": 24}}
        result = read_baseline(payload)
        self.assertIsNone(result["confidence"])
        self.assertIsNone(result["probabilities"])
        self.assertTrue(result["escalation"])
        truncated = copy.deepcopy(payload)
        truncated["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(DemoError):
            read_baseline(truncated)

    def test_input_validation(self):
        for body in ([], {}, {"message": ""}, {"message": 4}, {"message": "x" * 6001}, {"message": "hello", "model": "other"}, {"message": "hello", "rubric": "other"}):
            with self.assertRaises(DemoError):
                validate_input(body)
        self.assertEqual(validate_input({"message": " hello "}), ("hello", "standard", "decision"))

    def test_sales_rubric_and_abstention(self):
        self.assertIn("uncertain", questions("standard")["team"]["criteria"])
        self.assertNotEqual(questions("standard")["severity"], questions("sales")["severity"])

    def test_endpoint_validation(self):
        for endpoint in ("http://example.com", "https://example.com", "https://x.cognitiveservices.azure.com/path"):
            with self.assertRaises(ValueError):
                Foundry({"endpoint": endpoint})

    def test_baseline_cost_uses_both_token_rates(self):
        payload = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"team": "payments", "severity": 3, "escalate": True})}}],
            "usage": {"prompt_tokens": 4131, "completion_tokens": 270},
        }
        foundry = Foundry({
            "endpoint": "https://example.cognitiveservices.azure.com",
            "baseline_deployment": "test-baseline",
            "baseline_reasoning_effort": "none",
            "baseline_input_usd_per_million": .1,
            "baseline_output_usd_per_million": .5,
        })
        with patch.object(foundry, "auth_headers", return_value={}), patch("app.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            result = foundry.call("Checkout failed.", "standard", "baseline")
            body = json.loads(request.call_args.args[0].data)
        self.assertAlmostEqual(result["cost_usd"], .0005481)
        self.assertEqual(body["model"], "test-baseline")
        self.assertEqual(body["reasoning_effort"], "none")

    def test_request_preview_matches_live_body(self):
        foundry = Foundry({"endpoint": "https://example.cognitiveservices.azure.com", "decision_deployment": "test-decision"})
        for rubric in ("standard", "sales"):
            with self.subTest(rubric=rubric), patch.object(foundry, "auth_headers", return_value={}), patch("app.urllib.request.urlopen") as request:
                request.return_value.__enter__.return_value.read.return_value = json.dumps(decision_payload()).encode()
                foundry.call("Synthetic incident.", rubric, "decision")
                body = json.loads(request.call_args.args[0].data)
            preview = decision_request("Synthetic incident.", rubric, "YOUR-DECISION-DEPLOYMENT")
            self.assertEqual(body["state"], preview["state"])
            self.assertEqual(body["questions"], preview["questions"])
            self.assertEqual(body["model"], "test-decision")
            self.assertEqual(preview["model"], "YOUR-DECISION-DEPLOYMENT")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = {"endpoint": "https://example.cognitiveservices.azure.com", "decision_deployment": "test-decision", "baseline_deployment": "test-baseline"}
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.foundry = Foundry(config)
        cls.server.call_lock = threading.Lock()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_only_intended_files_served(self):
        with urllib.request.urlopen(self.url + "/") as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(self.url + "/config.json")
        self.assertEqual(exc.exception.code, 404)

    def test_preview_templates_exclude_connection_details(self):
        with urllib.request.urlopen(self.url + "/api/config") as response:
            payload = json.load(response)
        templates = payload["decision_request_templates"]
        self.assertEqual(set(templates), {"standard", "sales"})
        for rubric, template in templates.items():
            self.assertEqual(template, decision_request("", rubric, "YOUR-DECISION-DEPLOYMENT"))
        encoded = json.dumps(templates)
        self.assertNotIn("test-decision", encoded)
        self.assertNotIn("example.cognitiveservices.azure.com", encoded)
        self.assertNotIn("Authorization", encoded)
        self.assertNotIn("api-key", encoded)

    def test_cross_origin_blocked(self):
        request = urllib.request.Request(self.url + "/api/decision", data=b'{"message":"test"}', headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
        self.assertEqual(exc.exception.code, 403)

    def test_model_error_has_no_fixture_fallback(self):
        request = urllib.request.Request(self.url + "/api/decision", data=b'{"message":"test"}', headers={"Content-Type": "application/json"})
        with patch.object(self.server.foundry, "call", side_effect=DemoError("Foundry unavailable.")):
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request)
        self.assertEqual(exc.exception.code, 502)
        self.assertEqual(json.loads(exc.exception.read()), {"error": "Foundry unavailable."})


if __name__ == "__main__":
    unittest.main()
