package com.deriv.bot

import android.os.Bundle
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.util.Locale

class MainActivity : AppCompatActivity(), BotListener {

    private lateinit var authManager: SupabaseAuthManager
    private lateinit var botEngine: DerivBotEngine

    // Auth Views
    private var authLayout: View? = null
    private var etEmail: EditText? = null
    private var etPassword: EditText? = null
    private var btnSignIn: Button? = null
    private var btnSignUp: Button? = null
    private var tvAuthStatus: TextView? = null
    private var etSupabaseUrl: EditText? = null
    private var etSupabaseKey: EditText? = null
    private var btnSaveSupabaseConfig: Button? = null

    // Dashboard Views
    private var dashboardLayout: View? = null
    private var tvUserEmail: TextView? = null
    private var btnSignOut: Button? = null
    private var tvBotStatus: TextView? = null
    private var btnToggleBot: Button? = null
    private var tvBalance: TextView? = null
    private var tvSessionProfit: TextView? = null
    private var tvBarrier: TextView? = null
    private var tvTradingState: TextView? = null

    private var etDerivToken: EditText? = null
    private var etStake: EditText? = null
    private var etDailyTp: EditText? = null
    private var etDailySl: EditText? = null
    private var btnSaveDerivSettings: Button? = null

    private var tvSymbolProbs: TextView? = null
    private var tvActivityLogs: TextView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        authManager = SupabaseAuthManager(this)
        botEngine = DerivBotEngine(this)
        botEngine.listener = this

        if (authManager.isLoggedIn()) {
            showDashboardView()
        } else {
            showAuthView()
        }
    }

    private fun showAuthView() {
        setContentView(R.layout.activity_auth)

        etEmail = findViewById(R.id.etEmail)
        etPassword = findViewById(R.id.etPassword)
        btnSignIn = findViewById(R.id.btnSignIn)
        btnSignUp = findViewById(R.id.btnSignUp)
        tvAuthStatus = findViewById(R.id.tvAuthStatus)
        etSupabaseUrl = findViewById(R.id.etSupabaseUrl)
        etSupabaseKey = findViewById(R.id.etSupabaseKey)
        btnSaveSupabaseConfig = findViewById(R.id.btnSaveSupabaseConfig)

        etSupabaseUrl?.setText(authManager.supabaseUrl)
        etSupabaseKey?.setText(authManager.supabaseAnonKey)

        btnSignIn?.setOnClickListener {
            val email = etEmail?.text?.toString()?.trim() ?: ""
            val pass = etPassword?.text?.toString()?.trim() ?: ""
            if (email.isEmpty() || pass.isEmpty()) {
                showAuthMsg("Please enter email and password")
                return@setOnClickListener
            }
            showAuthMsg("Signing in to Supabase...")
            lifecycleScope.launch {
                val result = authManager.signIn(email, pass)
                if (result.isSuccess) {
                    Toast.makeText(this@MainActivity, "Signed in successfully!", Toast.LENGTH_SHORT).show()
                    showDashboardView()
                } else {
                    showAuthMsg(result.errorMessage ?: "Sign in failed")
                }
            }
        }

        btnSignUp?.setOnClickListener {
            val email = etEmail?.text?.toString()?.trim() ?: ""
            val pass = etPassword?.text?.toString()?.trim() ?: ""
            if (email.isEmpty() || pass.isEmpty()) {
                showAuthMsg("Please enter email and password")
                return@setOnClickListener
            }
            showAuthMsg("Signing up on Supabase...")
            lifecycleScope.launch {
                val result = authManager.signUp(email, pass)
                if (result.isSuccess) {
                    showAuthMsg(result.errorMessage ?: "Sign up successful! You can now sign in.")
                } else {
                    showAuthMsg(result.errorMessage ?: "Sign up failed")
                }
            }
        }

        btnSaveSupabaseConfig?.setOnClickListener {
            val url = etSupabaseUrl?.text?.toString()?.trim() ?: ""
            val key = etSupabaseKey?.text?.toString()?.trim() ?: ""
            if (url.isNotEmpty() && key.isNotEmpty()) {
                authManager.supabaseUrl = url
                authManager.supabaseAnonKey = key
                Toast.makeText(this, "Supabase settings updated!", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun showDashboardView() {
        setContentView(R.layout.activity_dashboard)

        tvUserEmail = findViewById(R.id.tvUserEmail)
        btnSignOut = findViewById(R.id.btnSignOut)
        tvBotStatus = findViewById(R.id.tvBotStatus)
        btnToggleBot = findViewById(R.id.btnToggleBot)
        tvBalance = findViewById(R.id.tvBalance)
        tvSessionProfit = findViewById(R.id.tvSessionProfit)
        tvBarrier = findViewById(R.id.tvBarrier)
        tvTradingState = findViewById(R.id.tvTradingState)

        etDerivToken = findViewById(R.id.etDerivToken)
        etStake = findViewById(R.id.etStake)
        etDailyTp = findViewById(R.id.etDailyTp)
        etDailySl = findViewById(R.id.etDailySl)
        btnSaveDerivSettings = findViewById(R.id.btnSaveDerivSettings)

        tvSymbolProbs = findViewById(R.id.tvSymbolProbs)
        tvActivityLogs = findViewById(R.id.tvActivityLogs)
        tvActivityLogs?.movementMethod = ScrollingMovementMethod()

        tvUserEmail?.text = "User: ${authManager.currentUserEmail ?: "Authenticated"}"

        etDerivToken?.setText(botEngine.apiToken)
        etStake?.setText(botEngine.stake.toString())
        etDailyTp?.setText(botEngine.dailyTp.toString())
        etDailySl?.setText(botEngine.dailySl.toString())

        btnSignOut?.setOnClickListener {
            lifecycleScope.launch {
                if (botEngine.isRunning) {
                    botEngine.stopBot()
                }
                authManager.signOut()
                showAuthView()
            }
        }

        btnToggleBot?.setOnClickListener {
            if (botEngine.isRunning) {
                botEngine.stopBot()
                btnToggleBot?.text = "START BOT"
                btnToggleBot?.setBackgroundColor(0xFF22C55E.toInt())
            } else {
                saveDerivSettings()
                if (botEngine.apiToken.isEmpty()) {
                    Toast.makeText(this, "Please enter your Deriv API Token", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                botEngine.startBot()
                btnToggleBot?.text = "STOP BOT"
                btnToggleBot?.setBackgroundColor(0xFFEF4444.toInt())
            }
        }

        btnSaveDerivSettings?.setOnClickListener {
            saveDerivSettings()
            Toast.makeText(this, "Deriv settings saved!", Toast.LENGTH_SHORT).show()
        }

        onStateUpdated(botEngine.getCurrentState())
    }

    private fun saveDerivSettings() {
        val token = etDerivToken?.text?.toString()?.trim() ?: ""
        val stakeVal = etStake?.text?.toString()?.toDoubleOrNull() ?: 0.25
        val tpVal = etDailyTp?.text?.toString()?.toDoubleOrNull() ?: 5.0
        val slVal = etDailySl?.text?.toString()?.toDoubleOrNull() ?: -1.0

        botEngine.apiToken = token
        botEngine.stake = stakeVal
        botEngine.dailyTp = tpVal
        botEngine.dailySl = slVal
    }

    private fun showAuthMsg(msg: String) {
        tvAuthStatus?.visibility = View.VISIBLE
        tvAuthStatus?.text = msg
    }

    override fun onStateUpdated(state: BotState) {
        if (tvBotStatus == null) return

        if (!state.isRunning) {
            tvBotStatus?.text = "STATUS: STOPPED"
            tvBotStatus?.setTextColor(0xFFEF4444.toInt())
            btnToggleBot?.text = "START BOT"
            btnToggleBot?.setBackgroundColor(0xFF22C55E.toInt())
        } else if (state.isAuthorized) {
            tvBotStatus?.text = "STATUS: ACTIVE & CONNECTED"
            tvBotStatus?.setTextColor(0xFF22C55E.toInt())
            btnToggleBot?.text = "STOP BOT"
            btnToggleBot?.setBackgroundColor(0xFFEF4444.toInt())
        } else {
            tvBotStatus?.text = "STATUS: CONNECTING..."
            tvBotStatus?.setTextColor(0xFFF59E0B.toInt())
        }

        tvBalance?.text = String.format(Locale.US, "$%.2f", state.balance)

        val profText = String.format(Locale.US, "%s$%.2f", if (state.sessionProfit >= 0) "+" else "", state.sessionProfit)
        tvSessionProfit?.text = profText
        tvSessionProfit?.setTextColor(if (state.sessionProfit >= 0) 0xFF22C55E.toInt() else 0xFFEF4444.toInt())

        tvBarrier?.text = "Over ${state.currentBarrier}"

        if (state.isTrading) {
            tvTradingState?.text = "IN TRADE"
            tvTradingState?.setTextColor(0xFFF59E0B.toInt())
        } else {
            tvTradingState?.text = "Scanning"
            tvTradingState?.setTextColor(0xFF3B82F6.toInt())
        }

        // Symbol probabilities text
        if (state.symbolProbs.isNotEmpty()) {
            val sb = StringBuilder()
            for (s in state.symbolProbs) {
                val signalStr = if (s.signal) " [TRIGGER]" else ""
                sb.append(String.format(Locale.US, "%-8s | 0:%4.1f%% | 1:%4.1f%% | Ticks:%3d%s\n",
                    s.symbol, s.p0, s.p1, s.ticksCount, signalStr))
            }
            tvSymbolProbs?.text = sb.toString()
        } else {
            tvSymbolProbs?.text = "Scanning market symbols..."
        }

        // Activity Logs
        if (state.logs.isNotEmpty()) {
            tvActivityLogs?.text = state.logs.joinToString("\n")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (botEngine.isRunning) {
            botEngine.stopBot()
        }
    }
}
