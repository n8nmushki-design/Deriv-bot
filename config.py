"""
Configuration module for Deriv Digit Over Bot
Loads settings from environment variables or a local .env file.
"""

import os

def load_env_file(filepath=".env"):
    """Simple parser for .env files without requiring external packages."""
    if not os.path.isfile(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val

# Load local .env if present
load_env_file()

# Configuration variables
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
PORT = int(os.environ.get("PORT", "10000"))

# Common 1-second volatility indices
CANDIDATE_SYMBOLS = [
    "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
    "R_10", "R_25", "R_50", "R_75", "R_100"
]
