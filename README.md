# Deriv Digit Over Bot & Mobile App (Android Studio + Supabase)

An automated trading application for Deriv (formerly Binary.com) designed to trade **Digit Over** contracts on Volatility 1s Indices using real-time WebSocket tick stream analysis.

This repository includes:
1. **Android Studio Mobile App (Kotlin)** with **Supabase Authentication** and APK build support.
2. **Python Web UI & Bot Server** for server/cloud deployments.

---

## 📱 Mobile App (Android Studio & Supabase)

The Android mobile application is structured as a native **Android Studio** project with full Kotlin & Gradle integration, Supabase Auth, and automated APK building.

### Key Mobile Features
- **Supabase Authentication**: Secure user Sign Up, Sign In, Sign Out, and session persistence via Supabase REST Auth API.
- **Real-Time WebSocket Engine**: Connects directly to Deriv WebSocket API (`wss://ws.derivws.com/websockets/v3`).
- **Live Trading Strategy**:
  - Monitors Volatility 1s indices (`1HZ10V`, `1HZ25V`, `R_10`, etc.).
  - Calculates last digit distribution (triggers when last-digit 0 and 1 probabilities are both < 10.0%).
  - Progression sequence on loss: `0 → 5 → 5 → 6 → 6 → 7 → 7 → 8 → 8`.
  - Target profit & stop loss management (Daily TP `$5.00`, Daily SL `-$1.00`, trade early sell TP/SL).
- **Mobile Control Dashboard**:
  - Real-time balance, session profit, barrier level, and trading state.
  - Live tick probability scanner table.
  - Interactive activity logs and trade history.
  - Strategy parameters settings screen (Deriv API token, stake, daily TP/SL).

---

## 🛠 Building the APK & Android Studio Usage

### 1. Opening in Android Studio
- Open **Android Studio**.
- Select **Open an Existing Project** and select this repository root folder.
- Android Studio will automatically import the Gradle project (`settings.gradle`, `build.gradle`, `app/build.gradle`).

### 2. Building APK via Script (`build_apk.sh`)
You can build the Android APK directly from the command line:
```bash
bash build_apk.sh
```
Or using the Gradle wrapper:
```bash
./gradlew assembleDebug
```
The generated APK file will be located at:
- `app-debug.apk` (root directory)
- `app/build/outputs/apk/debug/app-debug.apk`

---

## 🔑 Supabase Authentication Configuration

In the Mobile App Sign In screen:
1. Enter your **Supabase Project URL** (e.g. `https://your-project.supabase.co`) and **Supabase Anon Key**.
2. Click **Save Config**.
3. Create an account via **Sign Up** or sign in with an existing account via **Sign In**.

---

## 🐍 Python Web UI & Server

The Python backend server runs the trading bot and serves a lightweight HTML/JS web dashboard on port `10000` (or `PORT` env variable).

### Local Setup:
```bash
pip install -r requirements.txt
python deriv_over_bot.py
```

### Running Unit Tests:
```bash
python -m unittest test_deriv_over_bot.py
```

---

## Risk Disclaimer

*Trading financial contracts carries risk. Always test in a Deriv demo account before trading with real funds.*
