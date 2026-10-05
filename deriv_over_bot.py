#!/usr/bin/env python3
"""
Deriv Digit Over bot with Web UI Dashboard
- Scans volatility 1s indices
- Only trades when last-digit 0 AND 1 probs both < 10%
- Barrier sequence on loss: 0 → 5 → 5 → 6 → 6 → 7 → 7 → 8 → 8
- Stake 0.25, duration 3 ticks
- Daily SL -$1 / TP +$5
- Per-trade SL -$0.5 / TP +$1 (early sell)
- Includes lightweight Web UI dashboard on HTTP server
"""

import json
import time
import threading
import os
from collections import Counter, deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import websocket

# ========== CONFIG ==========
API_TOKEN = os.environ.get("DERIV_TOKEN", "").strip()
APP_ID = int(os.environ.get("DERIV_APP_ID", "1089"))
STAKE = float(os.environ.get("DERIV_STAKE", "0.25"))
DURATION = int(os.environ.get("DERIV_DURATION", "3"))          # ticks
DURATION_UNIT = "t"
BARRIER_SEQ = [0, 5, 5, 6, 6, 7, 7, 8, 8]
TICK_SAMPLE = 100     # last N ticks for digit probs
PROB_THRESHOLD = 10.0 # % for digit 0 and 1
SCAN_INTERVAL = 5     # seconds between scans
DAILY_TP = float(os.environ.get("DERIV_DAILY_TP", "5.0"))        # stop when session profit >= this
DAILY_SL = float(os.environ.get("DERIV_DAILY_SL", "-1.0"))       # stop when session profit <= this
TRADE_TP = float(os.environ.get("DERIV_TRADE_TP", "1.0"))        # sell if floating profit >= this
TRADE_SL = float(os.environ.get("DERIV_TRADE_SL", "-0.5"))       # sell if floating profit <= this
# ============================

# Common 1-second volatility indices
CANDIDATE_SYMBOLS = [
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_75", "R_100"
]

# Global log buffer for UI dashboard
logs_buffer = deque(maxlen=100)

def log_event(message):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    print(formatted)
    logs_buffer.append({"time": timestamp, "message": message})


def extract_last_digit(tick_data):
    """
    Extracts the last digit from a Deriv tick response dictionary.
    Prefers `display_value` or formats using `pip_size` to prevent trailing zero loss.
    """
    if "display_value" in tick_data and tick_data["display_value"] is not None:
        val_str = str(tick_data["display_value"])
    elif "pip_size" in tick_data and isinstance(tick_data["pip_size"], int):
        pip_size = tick_data["pip_size"]
        try:
            val_str = f"{float(tick_data['quote']):.{pip_size}f}"
        except (ValueError, TypeError, KeyError):
            val_str = str(tick_data.get("quote", ""))
    else:
        val_str = str(tick_data.get("quote", ""))

    digits = [c for c in val_str if c.isdigit()]
    if digits:
        return int(digits[-1])
    return None


class DerivBot:
    def __init__(self):
        self.ws = None
        self.authorized = False
        self.balance = 0.0
        self.start_balance = 0.0
        self.session_profit = 0.0
        self.barrier_idx = 0
        self.ticks = {}          # symbol -> list of last digits
        self.running = True
        self.is_trading = False   # Flag to prevent multiple concurrent trades
        self.pending_proposal = None
        self.last_contract_id = None
        self.reconnect_delay = 5  # seconds
        self.symbols = []
        self.active_contract_info = None
        self.trades_history = []

    def connect(self):
        if not API_TOKEN:
            log_event("[-] Error: DERIV_TOKEN environment variable is not set.")
            self.running = False
            return

        url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
        log_event(f"[+] Connecting to {url}...")
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        t = threading.Thread(target=self.ws.run_forever, daemon=True)
        t.start()

    def send(self, data):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(json.dumps(data))
            except Exception as e:
                log_event(f"[-] Send error: {e}")

    def on_open(self, ws):
        log_event("[+] Connected to WebSocket")
        self.send({"authorize": API_TOKEN})

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            log_event(f"[-] Failed to decode message: {e}")
            return

        msg_type = data.get("msg_type")

        if msg_type == "authorize":
            if "error" in data:
                log_event(f"[-] Auth failed: {data['error']['message']}")
                self.authorized = False
                self.running = False
                return
            self.authorized = True
            self.balance = float(data["authorize"].get("balance", 0))
            self.start_balance = self.balance
            self.session_profit = 0.0
            log_event(f"[+] Authorized | Balance: ${self.balance:.2f} | Daily TP:${DAILY_TP} SL:${DAILY_SL}")
            self.send({"balance": 1, "subscribe": 1})
            # Get active symbols and filter
            self.send({"active_symbols": "brief", "product_type": "basic"})

        elif msg_type == "balance":
            if "balance" in data:
                self.balance = float(data["balance"].get("balance", self.balance))

        elif msg_type == "active_symbols":
            symbols = data.get("active_symbols", [])
            available = []
            for s in symbols:
                sym = s.get("symbol") or s.get("underlying_symbol")
                if sym and (sym in CANDIDATE_SYMBOLS or "1HZ" in sym or sym.startswith("R_")):
                    available.append(sym)
            self.symbols = list(set(available)) or CANDIDATE_SYMBOLS
            log_event(f"[+] Scanning {len(self.symbols)} symbols: {self.symbols}")
            for sym in self.symbols:
                self.ticks[sym] = []
                self.send({"ticks": sym, "subscribe": 1})

        elif msg_type == "tick":
            tick = data.get("tick", {})
            sym = tick.get("symbol")
            last_digit = extract_last_digit(tick)
            if last_digit is not None and sym in self.ticks:
                self.ticks[sym].append(last_digit)
                if len(self.ticks[sym]) > TICK_SAMPLE:
                    self.ticks[sym].pop(0)

        elif msg_type == "proposal":
            if "error" in data:
                log_event(f"[-] Proposal error: {data['error']['message']}")
                self.is_trading = False
                self.active_contract_info = None
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
                log_event(f"[-] Buy error: {data['error']['message']}")
                self.is_trading = False
                self.active_contract_info = None
                return
            contract = data["buy"]
            self.last_contract_id = contract.get("contract_id")
            longcode = contract.get('longcode', '')
            log_event(f"[BUY] {longcode} | ID: {self.last_contract_id}")
            self.active_contract_info = {
                "id": self.last_contract_id,
                "longcode": longcode,
                "status": "OPEN",
                "profit": 0.0,
                "stake": STAKE,
                "time": time.strftime("%H:%M:%S")
            }
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
                log_event(f"[{'WIN' if won else 'LOSS'}] P/L: ${profit:.2f} | Session: ${self.session_profit:.2f} | Bal: ${self.balance:.2f}")

                trade_entry = {
                    "id": self.last_contract_id,
                    "symbol": poc.get("underlying", "N/A"),
                    "result": "WIN" if won else "LOSS",
                    "profit": profit,
                    "time": time.strftime("%H:%M:%S")
                }
                self.trades_history.insert(0, trade_entry)
                if len(self.trades_history) > 50:
                    self.trades_history.pop()

                if won:
                    self.barrier_idx = 0
                else:
                    self.barrier_idx = min(self.barrier_idx + 1, len(BARRIER_SEQ) - 1)

                if "subscription" in data:
                    self.send({"forget": data["subscription"]["id"]})

                self.is_trading = False
                self.active_contract_info = None

                if self.session_profit >= DAILY_TP:
                    log_event(f"[DAILY TP REACHED] ${self.session_profit:.2f} >= ${DAILY_TP}. Bot stopping.")
                    self.running = False
                elif self.session_profit <= DAILY_SL:
                    log_event(f"[DAILY SL HIT] ${self.session_profit:.2f} <= ${DAILY_SL}. Bot stopping.")
                    self.running = False
            else:
                # Still open – check per-trade SL/TP
                profit = float(poc.get("profit", 0))
                if self.active_contract_info:
                    self.active_contract_info["profit"] = profit

                if profit >= TRADE_TP or profit <= TRADE_SL:
                    log_event(f"[TRADE {'TP' if profit >= TRADE_TP else 'SL'}] Floating ${profit:.2f} → selling")
                    self.send({"sell": self.last_contract_id, "price": 0})

    def on_error(self, ws, error):
        log_event(f"[-] WS error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        log_event(f"[-] Connection closed (code: {close_status_code}, msg: {close_msg})")
        self.authorized = False

    def get_digit_probs(self, symbol):
        digits = self.ticks.get(symbol, [])
        if len(digits) < 20:
            return None
        cnt = Counter(digits)
        total = len(digits)
        probs = {d: (cnt.get(d, 0) / total) * 100 for d in range(10)}
        return probs

    def get_all_symbol_probs(self):
        summary = {}
        for sym in self.symbols:
            probs = self.get_digit_probs(sym)
            if probs:
                p0 = round(probs.get(0, 0), 1)
                p1 = round(probs.get(1, 0), 1)
                ticks_cnt = len(self.ticks.get(sym, []))
                signal = (p0 < PROB_THRESHOLD and p1 < PROB_THRESHOLD)
                summary[sym] = {
                    "p0": p0,
                    "p1": p1,
                    "ticks": ticks_cnt,
                    "signal": signal
                }
        return summary

    def get_status_summary(self):
        return {
            "authorized": self.authorized,
            "running": self.running,
            "is_trading": self.is_trading,
            "balance": round(self.balance, 2),
            "session_profit": round(self.session_profit, 2),
            "barrier": BARRIER_SEQ[self.barrier_idx],
            "barrier_idx": self.barrier_idx,
            "daily_tp": DAILY_TP,
            "daily_sl": DAILY_SL,
            "active_contract": self.active_contract_info,
            "symbols_probs": self.get_all_symbol_probs(),
            "trades_history": self.trades_history[:10],
            "logs": list(logs_buffer)[-20:]
        }

    def trade_loop(self):
        log_event("[+] Trade loop started")
        while self.running:
            try:
                if not self.authorized:
                    time.sleep(1)
                    continue

                if self.session_profit >= DAILY_TP or self.session_profit <= DAILY_SL:
                    self.running = False
                    break

                if self.is_trading:
                    time.sleep(1)
                    continue

                for sym in self.symbols:
                    if not self.running or self.is_trading:
                        break
                    probs = self.get_digit_probs(sym)
                    if not probs:
                        continue
                    p0 = probs.get(0, 100.0)
                    p1 = probs.get(1, 100.0)
                    if p0 < PROB_THRESHOLD and p1 < PROB_THRESHOLD:
                        barrier = BARRIER_SEQ[self.barrier_idx]
                        log_event(f"[SIGNAL] {sym} | 0:{p0:.1f}% 1:{p1:.1f}% | Over {barrier}")
                        self.is_trading = True
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
                        break  # one proposal at a time
                time.sleep(SCAN_INTERVAL)
            except Exception as e:
                log_event(f"[-] Loop error: {e}")
                time.sleep(3)

    def run(self):
        if not API_TOKEN:
            log_event("[-] Error: DERIV_TOKEN environment variable is not set. Exiting.")
            return

        threading.Thread(target=self.trade_loop, daemon=True).start()

        while self.running:
            if not self.ws or not self.ws.sock or not self.ws.sock.connected:
                log_event("[+] Initializing or reconnecting WebSocket connection...")
                self.connect()
            time.sleep(self.reconnect_delay)

        log_event("[!] Bot finished running.")


# Web Dashboard UI HTML Template
HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deriv Digit Over Bot Dashboard</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --accent-amber: #f59e0b;
            --border-color: #334155;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 20px;
        }

        h1 {
            margin: 0;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-badge {
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: bold;
        }

        .bg-green { background-color: var(--accent-green); color: black; }
        .bg-red { background-color: var(--accent-red); color: white; }
        .bg-amber { background-color: var(--accent-amber); color: black; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }

        .metric-card {
            background-color: var(--card-bg);
            padding: 18px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }

        .metric-title {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 6px;
        }

        .metric-value {
            font-size: 1.6rem;
            font-weight: bold;
        }

        .grid-two {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 25px;
        }

        @media (max-width: 768px) {
            .grid-two { grid-template-columns: 1fr; }
        }

        .card {
            background-color: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            padding: 20px;
        }

        .card-title {
            font-size: 1.1rem;
            font-weight: bold;
            margin-top: 0;
            margin-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }

        th, td {
            text-align: left;
            padding: 10px;
            border-bottom: 1px solid var(--border-color);
        }

        th { color: var(--text-muted); font-weight: 600; }

        .signal-yes { color: var(--accent-green); font-weight: bold; }
        .signal-no { color: var(--text-muted); }

        .log-box {
            background-color: #090d16;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 12px;
            height: 220px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.85rem;
        }

        .log-entry { margin-bottom: 4px; color: #cbd5e1; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Deriv Digit Over Bot <span id="auth-status" class="status-badge bg-amber">Connecting...</span></h1>
            <div>Target TP: <strong style="color:var(--accent-green)" id="val-tp">$5.00</strong> | Daily SL: <strong style="color:var(--accent-red)" id="val-sl">-$1.00</strong></div>
        </header>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-title">Account Balance</div>
                <div class="metric-value" id="val-balance">$0.00</div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Session P/L</div>
                <div class="metric-value" id="val-profit">$0.00</div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Current Barrier</div>
                <div class="metric-value" id="val-barrier">Over 0</div>
            </div>
            <div class="metric-card">
                <div class="metric-title">Trading State</div>
                <div class="metric-value" id="val-trading">Scanning</div>
            </div>
        </div>

        <div class="grid-two">
            <div class="card">
                <h2 class="card-title">Live Symbol Probabilities (Last 100 Ticks)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Digit 0 Prob</th>
                            <th>Digit 1 Prob</th>
                            <th>Ticks</th>
                            <th>Signal</th>
                        </tr>
                    </thead>
                    <tbody id="symbols-body">
                        <tr><td colspan="5">Loading tick probabilities...</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="card">
                <h2 class="card-title">Recent Trades History</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Symbol</th>
                            <th>Result</th>
                            <th>Profit</th>
                        </tr>
                    </thead>
                    <tbody id="trades-body">
                        <tr><td colspan="4">No trades executed yet.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2 class="card-title">Live Activity Logs</h2>
            <div class="log-box" id="logs-box">
                <div class="log-entry">Initializing dashboard connection...</div>
            </div>
        </div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/status');
                const data = await res.json();

                // Auth & Running Status
                const authBadge = document.getElementById('auth-status');
                if (!data.running) {
                    authBadge.className = 'status-badge bg-red';
                    authBadge.innerText = 'STOPPED';
                } else if (data.authorized) {
                    authBadge.className = 'status-badge bg-green';
                    authBadge.innerText = 'CONNECTED & ACTIVE';
                } else {
                    authBadge.className = 'status-badge bg-amber';
                    authBadge.innerText = 'CONNECTING...';
                }

                // Metrics
                document.getElementById('val-balance').innerText = `$${data.balance.toFixed(2)}`;

                const profEl = document.getElementById('val-profit');
                profEl.innerText = `${data.session_profit >= 0 ? '+' : ''}$${data.session_profit.toFixed(2)}`;
                profEl.style.color = data.session_profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

                document.getElementById('val-barrier').innerText = `Over ${data.barrier}`;

                const tradeEl = document.getElementById('val-trading');
                if (data.is_trading) {
                    tradeEl.innerText = 'IN TRADE';
                    tradeEl.style.color = 'var(--accent-amber)';
                } else {
                    tradeEl.innerText = 'Scanning';
                    tradeEl.style.color = 'var(--accent-blue)';
                }

                // Symbols Table
                const symbolsBody = document.getElementById('symbols-body');
                const symKeys = Object.keys(data.symbols_probs);
                if (symKeys.length > 0) {
                    symbolsBody.innerHTML = symKeys.map(sym => {
                        const s = data.symbols_probs[sym];
                        return `<tr>
                            <td><strong>${sym}</strong></td>
                            <td style="color:${s.p0 < 10 ? 'var(--accent-green)' : 'inherit'}">${s.p0}%</td>
                            <td style="color:${s.p1 < 10 ? 'var(--accent-green)' : 'inherit'}">${s.p1}%</td>
                            <td>${s.ticks}</td>
                            <td class="${s.signal ? 'signal-yes' : 'signal-no'}">${s.signal ? 'TRIGGER' : 'Waiting'}</td>
                        </tr>`;
                    }).join('');
                }

                // Trades History Table
                const tradesBody = document.getElementById('trades-body');
                if (data.trades_history && data.trades_history.length > 0) {
                    tradesBody.innerHTML = data.trades_history.map(t => {
                        const isWin = t.result === 'WIN';
                        return `<tr>
                            <td>${t.time}</td>
                            <td>${t.symbol}</td>
                            <td style="color:${isWin ? 'var(--accent-green)' : 'var(--accent-red)'}; font-weight:bold">${t.result}</td>
                            <td style="color:${isWin ? 'var(--accent-green)' : 'var(--accent-red)'}">${t.profit >= 0 ? '+' : ''}$${t.profit.toFixed(2)}</td>
                        </tr>`;
                    }).join('');
                }

                // Activity Logs
                const logsBox = document.getElementById('logs-box');
                if (data.logs && data.logs.length > 0) {
                    logsBox.innerHTML = data.logs.map(l => `<div class="log-entry">[${l.time}] ${l.message}</div>`).join('');
                    logsBox.scrollTop = logsBox.scrollHeight;
                }

            } catch (err) {
                console.error("Dashboard fetch error:", err);
            }
        }

        setInterval(fetchStatus, 2000);
        fetchStatus();
    </script>
</body>
</html>
"""

bot_instance = None

# HTTP Server for Web Dashboard & API
class WebDashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path).path
        if parsed_path == "/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            status_data = bot_instance.get_status_summary() if bot_instance else {}
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
        elif parsed_path == "/" or parsed_path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def log_message(self, format, *args):
        pass  # silence request logs


def start_http(bot):
    global bot_instance
    bot_instance = bot
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), WebDashboardHandler)
    log_event(f"[+] HTTP Web Dashboard available on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    bot = DerivBot()
    threading.Thread(target=start_http, args=(bot,), daemon=True).start()
    bot.run()
