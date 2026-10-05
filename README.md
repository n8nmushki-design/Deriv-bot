# Deriv Digit Over Bot with Web UI Dashboard

An automated trading bot for Deriv (formerly Binary.com) designed to trade **Digit Over** contracts on Volatility 1s Indices using real-time WebSocket tick stream analysis and featuring a live Web UI Dashboard.

---

## What is Required to Run the Bot

To successfully run this bot locally or in the cloud, you need:

1. **Deriv Account**: A real or demo trading account on [Deriv.com](https://deriv.com).
2. **Deriv API Token (`DERIV_TOKEN`)**:
   - Go to **Deriv Account Settings** > **API Token**.
   - Create a token with **Read** and **Trade** scopes.
3. **Python Environment**: Python 3.10 or higher.
4. **Dependencies**: `websocket-client` package (listed in `requirements.txt`).

---

## Strategy & Signal Overview

The bot monitors continuous tick data across active Deriv volatility indices (e.g., `1HZ10V`, `1HZ25V`, `1HZ50V`, `R_10`, etc.) and calculates empirical digit distribution over a sample of recent ticks.

### Signal Rules
1. **Digit Probability Filter**: Evaluates the last 100 ticks (`TICK_SAMPLE`). A trade signal triggers for a symbol when both digit `0` and digit `1` probabilities are below **10.0%** (`PROB_THRESHOLD`).
2. **Barrier Progression Sequence**:
   - Initial contract barrier: `0`
   - Progression on loss: `0 → 5 → 5 → 6 → 6 → 7 → 7 → 8 → 8`
   - On win: Resets barrier back to `0`.
3. **Execution Locks**: Ensures strictly one active trade proposal/contract at a time.
4. **Target Profit & Stop Loss**:
   - **Daily / Session TP**: Defaults to `+$5.00`
   - **Daily / Session SL**: Defaults to `-$1.00`
   - **Per-Trade Early Exit**: Early sell if floating profit reaches `+$1.00` (TP) or drops to `-$0.50` (SL).

---

## Web UI Dashboard

The bot runs a built-in lightweight Web UI dashboard accessible in your web browser:
- **Real-Time Account Metrics**: Connection status, balance, session P/L, current barrier, and trading state.
- **Live Symbol Probabilities**: Displays digit 0 & 1 percentages across monitored symbols.
- **Trades History**: Live table recording recent win/loss results and payouts.
- **Activity Logs**: Real-time streaming log output.
- **REST Status API**: Serves JSON data at `/status` for external monitoring or custom integrations.

Default Web UI URL: `http://localhost:10000/` (or your Render service domain).

---

## Configuration & Environment Variables

All main parameters are configured using `.env` or system environment variables (managed via `config.py`):

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DERIV_TOKEN` | *Required* | API token generated from your Deriv account |
| `DERIV_APP_ID` | `1089` | Deriv App ID |
| `DERIV_STAKE` | `0.25` | Stake amount per trade (in USD/account currency) |
| `DERIV_DURATION` | `3` | Contract duration in ticks |
| `DERIV_DAILY_TP` | `5.0` | Target profit for session |
| `DERIV_DAILY_SL` | `-1.0` | Stop loss limit for session |
| `DERIV_TRADE_TP` | `1.0` | Per-trade early sell take profit threshold |
| `DERIV_TRADE_SL` | `-0.5` | Per-trade early sell stop loss threshold |
| `PORT` | `10000` | Port for the Web UI Dashboard and HTTP server |

---

## Setup & Local Usage

1. Clone the repository:
   ```bash
   git clone <repository_url>
   cd deriv-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create your `.env` configuration file:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and enter your Deriv API token:
   ```env
   DERIV_TOKEN="your_deriv_api_token_here"
   ```

4. Run the bot locally:
   ```bash
   python deriv_over_bot.py
   ```

5. Open `http://localhost:10000` in your web browser to view the Web UI Dashboard.

---

## Cloud Deployment on Render

This bot is configured for automated deployment on [Render](https://render.com) using the included `render.yaml` blueprint file.

### Render Configuration & Run Commands:
- **Runtime**: Python 3.11
- **Build Command**:
  ```bash
  pip install -r requirements.txt
  ```
- **Start / Run Command**:
  ```bash
  python deriv_over_bot.py
  ```

### Steps to Deploy on Render:
1. Push your repository to GitHub or GitLab.
2. In the Render Dashboard, click **New +** > **Blueprint**.
3. Connect your repository (`render.yaml` will be automatically detected).
4. Under Environment Variables, add your `DERIV_TOKEN` secret.
5. Click **Apply**. Render will run the build and start commands automatically!

---

## Running Tests

To run the automated unit test suite:
```bash
python -m unittest test_deriv_over_bot.py
```

---

## Risk Disclaimer

*Trading financial instruments and contracts for difference (CFDs) carries a high level of risk and may not be suitable for all investors. Past performance of automated strategies is not indicative of future results. Use this bot at your own risk and test thoroughly in a demo account before using real funds.*
