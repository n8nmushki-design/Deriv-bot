import unittest
import os
import json
import urllib.request
import threading
import time
from deriv_over_bot import extract_last_digit, DerivBot, BARRIER_SEQ, PROB_THRESHOLD, WebDashboardHandler, start_http
from http.server import HTTPServer

class TestDerivOverBot(unittest.TestCase):

    def test_extract_last_digit_display_value(self):
        tick = {"display_value": "123.40", "quote": 123.4}
        digit = extract_last_digit(tick)
        self.assertEqual(digit, 0)

        tick = {"display_value": "123.45", "quote": 123.45}
        digit = extract_last_digit(tick)
        self.assertEqual(digit, 5)

    def test_extract_last_digit_pip_size(self):
        tick = {"quote": 123.4, "pip_size": 2}
        digit = extract_last_digit(tick)
        self.assertEqual(digit, 0)

        tick = {"quote": 123.456, "pip_size": 3}
        digit = extract_last_digit(tick)
        self.assertEqual(digit, 6)

    def test_extract_last_digit_fallback(self):
        tick = {"quote": 123.45}
        digit = extract_last_digit(tick)
        self.assertEqual(digit, 5)

        tick = {"quote": "invalid"}
        digit = extract_last_digit(tick)
        self.assertIsNone(digit)

    def test_get_digit_probs(self):
        bot = DerivBot()
        symbol = "1HZ10V"

        bot.ticks[symbol] = [1] * 10
        self.assertIsNone(bot.get_digit_probs(symbol))

        bot.ticks[symbol] = [0] * 10 + [1] * 10
        probs = bot.get_digit_probs(symbol)
        self.assertIsNotNone(probs)
        self.assertEqual(probs[0], 50.0)
        self.assertEqual(probs[1], 50.0)
        self.assertEqual(probs[2], 0.0)

    def test_barrier_progression_logic(self):
        bot = DerivBot()

        self.assertEqual(BARRIER_SEQ[bot.barrier_idx], 0)

        bot.barrier_idx = min(bot.barrier_idx + 1, len(BARRIER_SEQ) - 1)
        self.assertEqual(BARRIER_SEQ[bot.barrier_idx], 5)

        bot.barrier_idx = min(bot.barrier_idx + 1, len(BARRIER_SEQ) - 1)
        self.assertEqual(BARRIER_SEQ[bot.barrier_idx], 5)

        bot.barrier_idx = 0
        self.assertEqual(BARRIER_SEQ[bot.barrier_idx], 0)

    def test_web_ui_http_server(self):
        bot = DerivBot()
        bot.symbols = ["1HZ10V"]
        bot.ticks["1HZ10V"] = [0]*10 + [1]*10
        bot.balance = 100.0
        bot.session_profit = 2.5

        # Start HTTP server on test port 10088
        os.environ["PORT"] = "10088"
        t = threading.Thread(target=start_http, args=(bot,), daemon=True)
        t.start()
        time.sleep(1)

        # Test GET / (HTML Dashboard)
        req_ui = urllib.request.urlopen("http://127.0.0.1:10088/")
        self.assertEqual(req_ui.getcode(), 200)
        html_content = req_ui.read().decode('utf-8')
        self.assertIn("Deriv Digit Over Bot Dashboard", html_content)

        # Test GET /status (JSON API)
        req_status = urllib.request.urlopen("http://127.0.0.1:10088/status")
        self.assertEqual(req_status.getcode(), 200)
        data = json.loads(req_status.read().decode('utf-8'))
        self.assertEqual(data["balance"], 100.0)
        self.assertEqual(data["session_profit"], 2.5)
        self.assertIn("1HZ10V", data["symbols_probs"])

if __name__ == "__main__":
    unittest.main()
