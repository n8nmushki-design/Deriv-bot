package com.deriv.bot

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

data class SupabaseUser(
    val id: String,
    val email: String,
    val accessToken: String,
    val refreshToken: String?
)

data class AuthResult(
    val isSuccess: Boolean,
    val user: SupabaseUser? = null,
    val errorMessage: String? = null
)

class SupabaseAuthManager(private val context: Context) {

    private val client = OkHttpClient()
    private val gson = Gson()
    private val prefs: SharedPreferences = context.getSharedPreferences("supabase_auth_prefs", Context.MODE_PRIVATE)

    var supabaseUrl: String
        get() = prefs.getString("supabase_url", DEFAULT_SUPABASE_URL) ?: DEFAULT_SUPABASE_URL
        set(value) {
            prefs.edit().putString("supabase_url", value.trim().removeSuffix("/")).apply()
        }

    var supabaseAnonKey: String
        get() = prefs.getString("supabase_anon_key", DEFAULT_SUPABASE_KEY) ?: DEFAULT_SUPABASE_KEY
        set(value) {
            prefs.edit().putString("supabase_anon_key", value.trim()).apply()
        }

    var currentAccessToken: String?
        get() = prefs.getString("access_token", null)
        private set(value) {
            prefs.edit().putString("access_token", value).apply()
        }

    var currentUserEmail: String?
        get() = prefs.getString("user_email", null)
        private set(value) {
            prefs.edit().putString("user_email", value).apply()
        }

    var currentUserId: String?
        get() = prefs.getString("user_id", null)
        private set(value) {
            prefs.edit().putString("user_id", value).apply()
        }

    fun isLoggedIn(): Boolean {
        return !currentAccessToken.isNullOrEmpty()
    }

    suspend fun signUp(email: String, pass: String): AuthResult = withContext(Dispatchers.IO) {
        val url = "$supabaseUrl/auth/v1/signup"
        val jsonBody = JsonObject().apply {
            addProperty("email", email)
            addProperty("password", pass)
        }

        val request = Request.Builder()
            .url(url)
            .addHeader("apikey", supabaseAnonKey)
            .addHeader("Content-Type", "application/json")
            .post(jsonBody.toString().toRequestBody("application/json".toMediaType()))
            .build()

        try {
            val response = client.newCall(request).execute()
            val responseBody = response.body?.string() ?: ""

            if (!response.isSuccessful) {
                val errorMsg = parseErrorMessage(responseBody, "Sign up failed (${response.code})")
                return@withContext AuthResult(false, errorMessage = errorMsg)
            }

            val json = gson.fromJson(responseBody, JsonObject::class.java)
            val accessToken = json.get("access_token")?.asString
                ?: json.getAsJsonObject("session")?.get("access_token")?.asString

            val userObj = json.getAsJsonObject("user")
            val userId = userObj?.get("id")?.asString ?: "user_${System.currentTimeMillis()}"
            val userEmail = userObj?.get("email")?.asString ?: email

            if (!accessToken.isNullOrEmpty()) {
                saveSession(accessToken, userEmail, userId)
                return@withContext AuthResult(true, SupabaseUser(userId, userEmail, accessToken, null))
            } else {
                // Email confirmation might be enabled on Supabase project
                return@withContext AuthResult(true, SupabaseUser(userId, userEmail, "", null), "Account created! Please sign in or check your email for confirmation.")
            }
        } catch (e: Exception) {
            return@withContext AuthResult(false, errorMessage = "Connection error: ${e.message}")
        }
    }

    suspend fun signIn(email: String, pass: String): AuthResult = withContext(Dispatchers.IO) {
        val url = "$supabaseUrl/auth/v1/token?grant_type=password"
        val jsonBody = JsonObject().apply {
            addProperty("email", email)
            addProperty("password", pass)
        }

        val request = Request.Builder()
            .url(url)
            .addHeader("apikey", supabaseAnonKey)
            .addHeader("Content-Type", "application/json")
            .post(jsonBody.toString().toRequestBody("application/json".toMediaType()))
            .build()

        try {
            val response = client.newCall(request).execute()
            val responseBody = response.body?.string() ?: ""

            if (!response.isSuccessful) {
                val errorMsg = parseErrorMessage(responseBody, "Invalid credentials or sign in failed")
                return@withContext AuthResult(false, errorMessage = errorMsg)
            }

            val json = gson.fromJson(responseBody, JsonObject::class.java)
            val accessToken = json.get("access_token")?.asString
                ?: return@withContext AuthResult(false, errorMessage = "No access token in response")

            val userObj = json.getAsJsonObject("user")
            val userId = userObj?.get("id")?.asString ?: ""
            val userEmail = userObj?.get("email")?.asString ?: email

            saveSession(accessToken, userEmail, userId)
            return@withContext AuthResult(true, SupabaseUser(userId, userEmail, accessToken, null))

        } catch (e: Exception) {
            return@withContext AuthResult(false, errorMessage = "Connection error: ${e.message}")
        }
    }

    suspend fun signOut() = withContext(Dispatchers.IO) {
        val token = currentAccessToken
        if (!token.isNullOrEmpty()) {
            val url = "$supabaseUrl/auth/v1/logout"
            val request = Request.Builder()
                .url(url)
                .addHeader("apikey", supabaseAnonKey)
                .addHeader("Authorization", "Bearer $token")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .build()

            try {
                client.newCall(request).execute().close()
            } catch (_: Exception) {}
        }
        clearSession()
    }

    private fun saveSession(token: String, email: String, id: String) {
        currentAccessToken = token
        currentUserEmail = email
        currentUserId = id
    }

    fun clearSession() {
        prefs.edit()
            .remove("access_token")
            .remove("user_email")
            .remove("user_id")
            .apply()
    }

    private fun parseErrorMessage(jsonStr: String, fallback: String): String {
        return try {
            val json = gson.fromJson(jsonStr, JsonObject::class.java)
            json.get("error_description")?.asString
                ?: json.get("msg")?.asString
                ?: json.get("message")?.asString
                ?: fallback
        } catch (_: Exception) {
            fallback
        }
    }

    companion object {
        // Default Supabase project placeholders (users can edit in app settings)
        const val DEFAULT_SUPABASE_URL = "https://your-supabase-project.supabase.co"
        const val DEFAULT_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.your-anon-key-here"
    }
}
