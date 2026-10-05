# Deriv Digit Over Bot with Web UI Dashboard

An automated trading bot for Deriv (formerly Binary.com) designed to trade **Digit Over** contracts on Volatility 1s Indices using real-time WebSocket tick stream analysis and featuring a live Web UI Dashboard.

---

## Overview & Strategy Details

The bot monitors continuous tick data across active Deriv volatility indices (e.g., `1HZ10V`, `1HZ25V`, `1HZ50V`, `R_10`, etc.) and calculates empirical digit distribution over a sample of recent ticks.

### Signal Strategy
1. **Digit Probability Filter**: Evaluates the last 100 ticks (`TICK_SAMPLE`). A trade signal is triggered for a symbol when both digit `0` and digit `1` probabilities are below **10.0%** (`PROB_THRESHOLD`).
2. **Barrier Progression Sequence**:
   - Initial contract barrier: `0`
   - Progression on loss: `0 → 5 → 5 → 6 → 6 → 7 → 7 → 8 → 8`
   - On win: Resets barrier back to `0`.
3. **Execution Locks**: Ensures strictly one active trade proposal/contract at a time to avoid over-leveraging and race conditions.
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

### Prerequisites
- Python 3.10+
- A valid Deriv account and API Token (`DERIV_TOKEN`)

### Installation & Configuration

1. Clone the repository and navigate into the directory:
   ```bash
   git clone <repository_url>
   cd deriv-bot
   ```

2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create your `.env` configuration file from the template:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and enter your Deriv API token:
   ```env
   DERIV_TOKEN="your_deriv_api_token_here"
   ```

4. Run the bot:
   ```bash
   python deriv_over_bot.py
   ```

5. Open `http://localhost:10000` in your web browser to view the Web UI Dashboard.

### Running Tests

To run the automated unit test suite:
```bash
python -m unittest test_deriv_over_bot.py
```

---

## Cloud Deployment (Render)

This bot is configured for automated deployment on [Render](https://render.com) using the included `render.yaml` blueprint file. The Web UI Dashboard serves as the public web service on Render.

### Deploying on Render:
1. Push your repository to GitHub or GitLab.
2. In the Render Dashboard, click **New +** > **Blueprint**.
3. Connect your repository. Render will automatically detect `render.yaml`.
4. Add your `DERIV_TOKEN` secret under environment variables.
5. Deploy and view the web interface at your Render service URL!

---

## Risk Disclaimer

*Trading financial instruments and contracts for difference (CFDs) carries a high level of risk and may not be suitable for all investors. Past performance of automated strategies is not indicative of future results. Use this bot at your own risk and test thoroughly in a demo account before using real funds.*
