#!/usr/bin/env python3
"""
Deriv Digit Over bot
- Scans volatility 1s indices
- Only trades when last-digit 0 AND 1 probs both < 10%
- Barrier sequence on loss: 0 → 5 → 5 → 6 → 6 → 7 → 7 → 8 → 8
- Stake 0.25, duration 3 ticks
- Daily SL -$1 / TP +$5
- Per-trade SL -$0.5 / TP +$1 (early sell)
"""

import json
import time
import threading
import os
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
import websocket

# ========== CONFIG ==========
API_TOKEN = os.environ.get("DERIV_TOKEN", "pat_5b54ef8f870abd60c41e98aa70461d974c25343e419688611fd09a0bf579d27c")
APP_ID = 1089
STAKE = 0.25
DURATION = 3          # ticks
DURATION_UNIT = "t"
BARRIER_SEQ = [0, 5, 5, 6, 6, 7, 7, 8, 8]
TICK_SAMPLE = 100     # last N ticks for digit probs
PROB_THRESHOLD = 10.0 # % for digit 0 and 1
SCAN_INTERVAL = 5     # seconds between scans
DAILY_TP = 5.0        # stop when session profit >= this
DAILY_SL = -1.0       # stop when session profit <= this
TRADE_TP = 1.0        # sell if floating profit >= this
TRADE_SL = -0.5       # sell if floating profit <= this
# ============================

# Common 1-second volatility indices
CANDIDATE_SYMBOLS = [
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_75", "R_100"
]

class DerivBot:
    def __init__(self):
        self.ws = None
        self.authorized = False
        self.balance = 0.0
        self.start_balance = 0.0
        self.session_profit = 0.0
        self.barrier_idx = 0
        self.ticks = {}          # symbol -> list of last digits
        self.tick_subs = {}
        self.running = True
        self.pending_proposal = None
        self.last_contract_id = None

    def connect(self):
        url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        t = threading.Thread(target=self.ws.run_forever, daemon=True)
        t.start()
        time.sleep(2)

    def send(self, data):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps(data))

    def on_open(self, ws):
        print("[+] Connected")
        self.send({"authorize": API_TOKEN})

    def on_message(self, ws, message):
        data = json.loads(message)
        msg_type = data.get("msg_type")

        if msg_type == "authorize":
            if "error" in data:
                print("[-] Auth failed:", data["error"]["message"])
                self.running = False
                return
            self.authorized = True
            self.balance = float(data["authorize"].get("balance", 0))
            self.start_balance = self.balance
            self.session_profit = 0.0
            print(f"[+] Authorized | Balance: {self.balance} | Daily TP:{DAILY_TP} SL:{DAILY_SL}")
            self.send({"balance": 1, "subscribe": 1})
            # Get active symbols and filter
            self.send({"active_symbols": "brief", "product_type": "basic"})

        elif msg_type == "balance":
            self.balance = float(data["balance"]["balance"])

        elif msg_type == "active_symbols":
            symbols = data.get("active_symbols", [])
            available = []
            for s in symbols:
                sym = s.get("symbol") or s.get("underlying_symbol")
                if sym in CANDIDATE_SYMBOLS or (sym and "1HZ" in sym) or (sym and sym.startswith("R_")):
                    available.append(sym)
            self.symbols = list(set(available)) or CANDIDATE_SYMBOLS
            print(f"[+] Scanning symbols: {self.symbols}")
            for sym in self.symbols:
                self.ticks[sym] = []
                self.send({"ticks": sym, "subscribe": 1})
            # Start trading loop
            threading.Thread(target=self.trade_loop, daemon=True).start()

        elif msg_type == "tick":
            tick = data["tick"]
            sym = tick["symbol"]
            quote = str(tick["quote"])
            last_digit = int(quote[-1]) if quote and quote[-1].isdigit() else None
            if last_digit is not None and sym in self.ticks:
                self.ticks[sym].append(last_digit)
                if len(self.ticks[sym]) > TICK_SAMPLE:
                    self.ticks[sym].pop(0)

        elif msg_type == "proposal":
            if "error" in data:
                print("[-] Proposal error:", data["error"]["message"])
                return
            prop = data["proposal"]
            self.pending_proposal = prop
            # Buy immediately
            self.send({
                "buy": prop["id"],
                "price": STAKE
            })

        elif msg_type == "buy":
            if "error" in data:
                print("[-] Buy error:", data["error"]["message"])
                return
            contract = data["buy"]
            self.last_contract_id = contract["contract_id"]
            print(f"[BUY] {contract.get('longcode', '')} | ID: {self.last_contract_id}")
            self.send({
                "proposal_open_contract": 1,
                "contract_id": self.last_contract_id,
                "subscribe": 1
            })

        elif msg_type == "proposal_open_contract":
            poc = data.get("proposal_open_contract", {})
            if poc.get("is_sold") or poc.get("status") == "sold":
                profit = float(poc.get("profit", 0))
                self.session_profit += profit
                won = profit > 0
                print(f"[{'WIN' if won else 'LOSS'}] P/L: {profit:.2f} | Session: {self.session_profit:.2f} | Bal: {self.balance}")
                if won:
                    self.barrier_idx = 0
                else:
                    self.barrier_idx = min(self.barrier_idx + 1, len(BARRIER_SEQ) - 1)
                if "subscription" in data:
                    self.send({"forget": data["subscription"]["id"]})
                if self.session_profit >= DAILY_TP:
                    print(f"[DAILY TP] {self.session_profit:.2f} >= {DAILY_TP}. Stopping.")
                    self.running = False
                elif self.session_profit <= DAILY_SL:
                    print(f"[DAILY SL] {self.session_profit:.2f} <= {DAILY_SL}. Stopping.")
                    self.running = False
            else:
                # Still open – check per-trade SL/TP
                profit = float(poc.get("profit", 0))
                if profit >= TRADE_TP or profit <= TRADE_SL:
                    print(f"[TRADE {'TP' if profit >= TRADE_TP else 'SL'}] Floating {profit:.2f} → selling")
                    self.send({"sell": self.last_contract_id, "price": 0})

    def on_error(self, ws, error):
        print("[-] WS error:", error)

    def on_close(self, ws, *args):
        print("[-] Connection closed")

    def get_digit_probs(self, symbol):
        digits = self.ticks.get(symbol, [])
        if len(digits) < 20:
            return None
        cnt = Counter(digits)
        total = len(digits)
        probs = {d: (cnt.get(d, 0) / total) * 100 for d in range(10)}
        return probs

    def trade_loop(self):
        print("[+] Trade loop started")
        while self.running:
            try:
                if self.session_profit >= DAILY_TP or self.session_profit <= DAILY_SL:
                    self.running = False
                    break
                for sym in getattr(self, "symbols", []):
                    probs = self.get_digit_probs(sym)
                    if not probs:
                        continue
                    p0 = probs.get(0, 100)
                    p1 = probs.get(1, 100)
                    if p0 < PROB_THRESHOLD and p1 < PROB_THRESHOLD:
                        barrier = BARRIER_SEQ[self.barrier_idx]
                        print(f"[SIGNAL] {sym} | 0:{p0:.1f}% 1:{p1:.1f}% | Over {barrier}")
                        self.send({
                            "proposal": 1,
                            "amount": STAKE,
                            "basis": "stake",
                            "contract_type": "DIGITOVER",
                            "currency": "USD",
                            "duration": DURATION,
                            "duration_unit": DURATION_UNIT,
                            "symbol": sym,
                            "barrier": str(barrier)
                        })
                        time.sleep(DURATION + 2)  # wait for result roughly
                        break  # one trade at a time
                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                print("[-] Loop error:", e)
                time.sleep(3)

    def run(self):
        self.connect()
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[!] Stopped by user")
            self.running = False

# Simple keep-alive HTTP server for Render free tier
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Deriv bot alive")
    def log_message(self, format, *args):
        pass  # silence logs

def start_http():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[+] HTTP keep-alive on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    # Start HTTP server in background (required for Render web service)
    threading.Thread(target=start_http, daemon=True).start()
    bot = DerivBot()
    bot.run()
