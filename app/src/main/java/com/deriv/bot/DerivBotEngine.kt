package com.deriv.bot

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import kotlinx.coroutines.*
import okhttp3.*
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit

data class SymbolProbSummary(
    val symbol: String,
    val p0: Double,
    val p1: Double,
    val ticksCount: Int,
    val signal: Boolean
)

data class TradeRecord(
    val id: String,
    val symbol: String,
    val result: String,
    val profit: Double,
    val time: String
)

data class BotState(
    val isAuthorized: Boolean,
    val isRunning: Boolean,
    val isTrading: Boolean,
    val balance: Double,
    val sessionProfit: Double,
    val currentBarrier: Int,
    val dailyTp: Double,
    val dailySl: Double,
    val activeContractLongcode: String?,
    val activeContractProfit: Double?,
    val symbolProbs: List<SymbolProbSummary>,
    val tradeHistory: List<TradeRecord>,
    val logs: List<String>
)

interface BotListener {
    fun onStateUpdated(state: BotState)
}

class DerivBotEngine(private val context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences("deriv_bot_prefs", Context.MODE_PRIVATE)
    private val client = OkHttpClient.Builder()
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private var webSocket: WebSocket? = null
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    var listener: BotListener? = null

    // Config parameters
    var apiToken: String
        get() = prefs.getString("deriv_token", "") ?: ""
        set(value) { prefs.edit().putString("deriv_token", value.trim()).apply() }

    var appId: Int
        get() = prefs.getInt("deriv_app_id", 1089)
        set(value) { prefs.edit().putInt("deriv_app_id", value).apply() }

    var stake: Double
        get() = prefs.getFloat("deriv_stake", 0.25f).toDouble()
        set(value) { prefs.edit().putFloat("deriv_stake", value.toFloat()).apply() }

    var duration: Int
        get() = prefs.getInt("deriv_duration", 3)
        set(value) { prefs.edit().putInt("deriv_duration", value).apply() }

    var dailyTp: Double
        get() = prefs.getFloat("deriv_daily_tp", 5.0f).toDouble()
        set(value) { prefs.edit().putFloat("deriv_daily_tp", value.toFloat()).apply() }

    var dailySl: Double
        get() = prefs.getFloat("deriv_daily_sl", -1.0f).toDouble()
        set(value) { prefs.edit().putFloat("deriv_daily_sl", value.toFloat()).apply() }

    var tradeTp: Double
        get() = prefs.getFloat("deriv_trade_tp", 1.0f).toDouble()
        set(value) { prefs.edit().putFloat("deriv_trade_tp", value.toFloat()).apply() }

    var tradeSl: Double
        get() = prefs.getFloat("deriv_trade_sl", -0.5f).toDouble()
        set(value) { prefs.edit().putFloat("deriv_trade_sl", value.toFloat()).apply() }

    // State variables
    val barrierSeq = listOf(0, 5, 5, 6, 6, 7, 7, 8, 8)
    private var barrierIdx = 0

    @Volatile var isAuthorized = false
    @Volatile var isRunning = false
    @Volatile var isTrading = false
    @Volatile var balance = 0.0
    @Volatile var startBalance = 0.0
    @Volatile var sessionProfit = 0.0

    private var activeContractId: String? = null
    private var activeContractLongcode: String? = null
    private var activeContractProfit: Double? = null

    private val candidateSymbols = listOf(
        "1HZ10V", "1HZ25V", "1HZ50V", "1HZ75V", "1HZ100V",
        "R_10", "R_25", "R_50", "R_75", "R_100"
    )
    private val activeSymbols = CopyOnWriteArrayList<String>()
    private val tickHistory = ConcurrentHashMap<String, MutableList<Int>>()

    private val tradeHistory = CopyOnWriteArrayList<TradeRecord>()
    private val logsList = CopyOnWriteArrayList<String>()

    private var scanJob: Job? = null

    fun startBot() {
        if (isRunning) return
        if (apiToken.isEmpty()) {
            logEvent("[-] Deriv API token not set. Please update in settings.")
            return
        }
        isRunning = true
        logEvent("[+] Starting Deriv Bot Engine...")
        connectWebSocket()

        scanJob = scope.launch {
            tradeLoop()
        }
    }

    fun stopBot() {
        isRunning = false
        scanJob?.cancel()
        webSocket?.close(1000, "Bot stopped by user")
        webSocket = null
        isAuthorized = false
        logEvent("[-] Deriv Bot Engine stopped.")
        notifyState()
    }

    private fun connectWebSocket() {
        val url = "wss://ws.derivws.com/websockets/v3?app_id=$appId"
        logEvent("[+] Connecting to Deriv WS ($url)...")
        val request = Request.Builder().url(url).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                logEvent("[+] WebSocket Connected")
                val authReq = JsonObject().apply { addProperty("authorize", apiToken) }
                ws.send(authReq.toString())
            }

            override fun onMessage(ws: WebSocket, text: String) {
                handleWsMessage(text)
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                logEvent("[-] WS Failure: ${t.message}")
                isAuthorized = false
                notifyState()
                if (isRunning) {
                    scope.launch {
                        delay(5000)
                        if (isRunning) connectWebSocket()
                    }
                }
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                logEvent("[-] WS Closed ($code): $reason")
                isAuthorized = false
                notifyState()
            }
        })
    }

    private fun sendJson(obj: JsonObject) {
        webSocket?.send(obj.toString())
    }

    private fun handleWsMessage(text: String) {
        try {
            val json = gson.fromJson(text, JsonObject::class.java)
            val msgType = json.get("msg_type")?.asString ?: return

            when (msgType) {
                "authorize" -> {
                    if (json.has("error")) {
                        val errMsg = json.getAsJsonObject("error").get("message")?.asString ?: "Auth error"
                        logEvent("[-] Auth failed: $errMsg")
                        isAuthorized = false
                        return
                    }
                    isAuthorized = true
                    val authObj = json.getAsJsonObject("authorize")
                    balance = authObj.get("balance")?.asDouble ?: 0.0
                    startBalance = balance
                    sessionProfit = 0.0
                    logEvent("[+] Authorized | Balance: $$balance | Daily TP:$$dailyTp SL:$$dailySl")

                    sendJson(JsonObject().apply {
                        addProperty("balance", 1)
                        addProperty("subscribe", 1)
                    })

                    sendJson(JsonObject().apply {
                        addProperty("active_symbols", "brief")
                        addProperty("product_type", "basic")
                    })
                }

                "balance" -> {
                    if (json.has("balance")) {
                        balance = json.getAsJsonObject("balance").get("balance")?.asDouble ?: balance
                    }
                }

                "active_symbols" -> {
                    val arr = json.getAsJsonArray("active_symbols") ?: JsonArray()
                    val symList = mutableListOf<String>()
                    for (elem in arr) {
                        val s = elem.asJsonObject
                        val sym = s.get("symbol")?.asString ?: s.get("underlying_symbol")?.asString ?: ""
                        if (sym in candidateSymbols || sym.contains("1HZ") || sym.startsWith("R_")) {
                            symList.add(sym)
                        }
                    }
                    activeSymbols.clear()
                    activeSymbols.addAll(if (symList.isNotEmpty()) symList.distinct() else candidateSymbols)
                    logEvent("[+] Scanning ${activeSymbols.size} symbols: $activeSymbols")

                    for (sym in activeSymbols) {
                        tickHistory[sym] = mutableListOf()
                        sendJson(JsonObject().apply {
                            addProperty("ticks", sym)
                            addProperty("subscribe", 1)
                        })
                    }
                }

                "tick" -> {
                    val tickObj = json.getAsJsonObject("tick") ?: return
                    val sym = tickObj.get("symbol")?.asString ?: return
                    val lastDigit = extractLastDigit(tickObj)
                    if (lastDigit != null) {
                        val list = tickHistory.getOrPut(sym) { mutableListOf() }
                        synchronized(list) {
                            list.add(lastDigit)
                            if (list.size > 100) list.removeAt(0)
                        }
                    }
                }

                "proposal" -> {
                    if (json.has("error")) {
                        val err = json.getAsJsonObject("error").get("message")?.asString ?: "Proposal error"
                        logEvent("[-] Proposal error: $err")
                        isTrading = false
                        activeContractLongcode = null
                        activeContractProfit = null
                        return
                    }
                    val prop = json.getAsJsonObject("proposal")
                    val propId = prop.get("id")?.asString ?: ""
                    sendJson(JsonObject().apply {
                        addProperty("buy", propId)
                        addProperty("price", stake)
                    })
                }

                "buy" -> {
                    if (json.has("error")) {
                        val err = json.getAsJsonObject("error").get("message")?.asString ?: "Buy error"
                        logEvent("[-] Buy error: $err")
                        isTrading = false
                        activeContractLongcode = null
                        activeContractProfit = null
                        return
                    }
                    val contract = json.getAsJsonObject("buy")
                    activeContractId = contract.get("contract_id")?.asString
                    activeContractLongcode = contract.get("longcode")?.asString ?: ""
                    activeContractProfit = 0.0
                    logEvent("[BUY] $activeContractLongcode | ID: $activeContractId")

                    sendJson(JsonObject().apply {
                        addProperty("proposal_open_contract", 1)
                        addProperty("contract_id", activeContractId)
                        addProperty("subscribe", 1)
                    })
                }

                "proposal_open_contract" -> {
                    val poc = json.getAsJsonObject("proposal_open_contract") ?: return
                    val isSold = poc.get("is_sold")?.asInt == 1 || poc.get("status")?.asString == "sold"
                    val profit = poc.get("profit")?.asDouble ?: 0.0

                    if (isSold) {
                        sessionProfit += profit
                        val won = profit > 0
                        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
                        logEvent("[${if (won) "WIN" else "LOSS"}] P/L: $$profit | Session: $$sessionProfit | Bal: $$balance")

                        tradeHistory.add(0, TradeRecord(
                            id = activeContractId ?: "",
                            symbol = poc.get("underlying")?.asString ?: "N/A",
                            result = if (won) "WIN" else "LOSS",
                            profit = profit,
                            time = timeStr
                        ))
                        if (tradeHistory.size > 50) tradeHistory.removeAt(tradeHistory.size - 1)

                        if (won) {
                            barrierIdx = 0
                        } else {
                            barrierIdx = (barrierIdx + 1).coerceAtMost(barrierSeq.size - 1)
                        }

                        if (json.has("subscription")) {
                            val subId = json.getAsJsonObject("subscription").get("id")?.asString
                            if (!subId.isNullOrEmpty()) {
                                sendJson(JsonObject().apply {
                                    addProperty("forget", subId)
                                })
                            }
                        }

                        isTrading = false
                        activeContractLongcode = null
                        activeContractProfit = null

                        if (sessionProfit >= dailyTp) {
                            logEvent("[DAILY TP REACHED] $$sessionProfit >= $$dailyTp. Bot paused.")
                        } else if (sessionProfit <= dailySl) {
                            logEvent("[DAILY SL HIT] $$sessionProfit <= $$dailySl. Bot paused.")
                        }
                    } else {
                        // Open contract - check per trade TP/SL
                        activeContractProfit = profit
                        if (profit >= tradeTp || profit <= tradeSl) {
                            logEvent("[TRADE ${if (profit >= tradeTp) "TP" else "SL"}] Floating $$profit -> Early selling")
                            sendJson(JsonObject().apply {
                                addProperty("sell", activeContractId)
                                addProperty("price", 0)
                            })
                        }
                    }
                }
            }
            notifyState()
        } catch (e: Exception) {
            logEvent("[-] Error parsing WS message: ${e.message}")
        }
    }

    private fun extractLastDigit(tickObj: JsonObject): Int? {
        val valStr = if (tickObj.has("display_value") && !tickObj.get("display_value").isJsonNull) {
            tickObj.get("display_value").asString
        } else if (tickObj.has("pip_size") && tickObj.has("quote")) {
            val pip = tickObj.get("pip_size").asInt
            val quote = tickObj.get("quote").asDouble
            String.format(Locale.US, "%.${pip}f", quote)
        } else {
            tickObj.get("quote")?.asString ?: ""
        }

        val digits = valStr.filter { it.isDigit() }
        return if (digits.isNotEmpty()) digits.last().toString().toInt() else null
    }

    private suspend fun tradeLoop() {
        logEvent("[+] Trade scan loop started")
        while (isRunning) {
            try {
                if (!isAuthorized) {
                    delay(2000)
                    continue
                }

                if (sessionProfit >= dailyTp || sessionProfit <= dailySl) {
                    delay(5000)
                    continue
                }

                if (isTrading) {
                    delay(1000)
                    continue
                }

                for (sym in activeSymbols) {
                    if (!isRunning || isTrading) break

                    val list = tickHistory[sym] ?: continue
                    val probs = synchronized(list) {
                        if (list.size < 20) null
                        else {
                            val count0 = list.count { it == 0 }
                            val count1 = list.count { it == 1 }
                            val total = list.size.toDouble()
                            Pair((count0 / total) * 100, (count1 / total) * 100)
                        }
                    } ?: continue

                    val (p0, p1) = probs
                    if (p0 < 10.0 && p1 < 10.0) {
                        val barrier = barrierSeq[barrierIdx]
                        logEvent("[SIGNAL] $sym | 0:${String.format("%.1f", p0)}% 1:${String.format("%.1f", p1)}% | Over $barrier")
                        isTrading = true

                        sendJson(JsonObject().apply {
                            addProperty("proposal", 1)
                            addProperty("amount", stake)
                            addProperty("basis", "stake")
                            addProperty("contract_type", "DIGITOVER")
                            addProperty("currency", "USD")
                            addProperty("duration", duration)
                            addProperty("duration_unit", "t")
                            addProperty("symbol", sym)
                            addProperty("barrier", barrier.toString())
                        })
                        break
                    }
                }
                delay(5000)
            } catch (e: Exception) {
                logEvent("[-] Scan loop error: ${e.message}")
                delay(3000)
            }
        }
    }

    private fun getSymbolProbSummaries(): List<SymbolProbSummary> {
        val list = mutableListOf<SymbolProbSummary>()
        for (sym in activeSymbols) {
            val ticks = tickHistory[sym] ?: continue
            val (p0, p1, cnt) = synchronized(ticks) {
                if (ticks.isEmpty()) Triple(0.0, 0.0, 0)
                else {
                    val count0 = ticks.count { it == 0 }
                    val count1 = ticks.count { it == 1 }
                    val total = ticks.size.toDouble()
                    Triple((count0 / total) * 100, (count1 / total) * 100, ticks.size)
                }
            }
            list.add(SymbolProbSummary(
                symbol = sym,
                p0 = Math.round(p0 * 10.0) / 10.0,
                p1 = Math.round(p1 * 10.0) / 10.0,
                ticksCount = cnt,
                signal = p0 < 10.0 && p1 < 10.0 && cnt >= 20
            ))
        }
        return list
    }

    fun getCurrentState(): BotState {
        return BotState(
            isAuthorized = isAuthorized,
            isRunning = isRunning,
            isTrading = isTrading,
            balance = Math.round(balance * 100.0) / 100.0,
            sessionProfit = Math.round(sessionProfit * 100.0) / 100.0,
            currentBarrier = barrierSeq[barrierIdx],
            dailyTp = dailyTp,
            dailySl = dailySl,
            activeContractLongcode = activeContractLongcode,
            activeContractProfit = activeContractProfit,
            symbolProbs = getSymbolProbSummaries(),
            tradeHistory = tradeHistory.take(15),
            logs = logsList.takeLast(30)
        )
    }

    private fun logEvent(msg: String) {
        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val formatted = "[$timeStr] $msg"
        logsList.add(formatted)
        if (logsList.size > 100) logsList.removeAt(0)
        notifyState()
    }

    private fun notifyState() {
        val state = getCurrentState()
        scope.launch(Dispatchers.Main) {
            listener?.onStateUpdated(state)
        }
    }
}
