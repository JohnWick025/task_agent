# Multi-User Telegram Odoo Agent

An autonomous multi-tenant Telegram Agent that connects and dynamically orchestrates your Odoo instances:
1. **HR Attendance:** Real-time Clock-In, Clock-Out, attendance status, and worked-hour calculations.
2. **Projects & Timesheets:** Full task management (search, complete, create) and logging work hours to `account.analytic.line`.

Designed for **Render Free Tier**, **Neon Serverless PostgreSQL**, and a **Universal Multi-Provider LLM Engine** (OpenRouter, Google Gemini, Groq, NVIDIA NIM, Local Ollama, and OpenAI).

---

## 🌟 Key Features

- **Dynamic & Partial Instance Setup:** Connect **both instances**, or **only Tasks & Timesheets**, or **only HR Attendance**. The bot dynamically adapts its tools and commands without demanding credentials for unconfigured instances.
- **Universal Multi-Provider AI with Automatic Failover:**
  - **OpenRouter** (Free & paid models: Claude, Gemini, DeepSeek, Llama)
  - **Google Gemini** (Generous free tier: `gemini-2.0-flash`)
  - **Groq** (Fastest inference: `llama-3.3-70b-versatile`)
  - **Local Ollama** (Run locally for free: `qwen2.5`, `llama3.1`)
  - **NVIDIA NIM** (Developer catalog)
  - **OpenAI** (`gpt-4o-mini`)
  - *Automatic Failover:* If one model/provider encounters 404, rate limits (429), or errors, the bot automatically rotates to the next model/provider in the pool!
- **Multi-User & Multi-Tenant:** Multiple team members can use the same bot. Each user's Odoo credentials are encrypted at rest with `Fernet`.
- **Fast Short-Circuiting:** Persistent Telegram reply buttons (`⏱️ Clock In`, `⏹️ Clock Out`, `📋 My Tasks`, `⏳ Today's Hours`) execute with zero latency without burning LLM tokens.
- **Render Free Tier Optimized:** 
  - Runs in Webhook mode so incoming Telegram messages wake up the instance.
  - Returns `200 OK` to Telegram within milliseconds while executing agent tasks in the background.
  - Keeps memory footprint strictly under 300MB RAM to stay within Render's 512MB limit.

---

## 🚀 Setup & Configuration

### 1. Telegram Bot Token
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, follow prompts to choose a name and username.
3. Copy the HTTP API **Bot Token**.

### 2. Choose Your LLM Provider
Set your preferred provider in `.env` (or leave `LLM_PROVIDER=auto` to auto-detect based on whichever key is present):

- **Option A: Google Gemini (Free & High Quota)**
  ```env
  GEMINI_API_KEY=your_gemini_api_key
  ```
- **Option B: OpenRouter (All-in-one Free & Paid models)**
  ```env
  OPENROUTER_API_KEY=your_openrouter_api_key
  ```
- **Option C: Groq (Ultra-fast)**
  ```env
  GROQ_API_KEY=your_groq_api_key
  ```
- **Option D: Local Ollama (100% Free & Local)**
  ```env
  OLLAMA_BASE_URL=http://localhost:11434/v1
  OLLAMA_MODEL=qwen2.5:7b
  ```
- **Option E: NVIDIA NIM**
  ```env
  NVIDIA_API_KEY=your_nvidia_api_key
  ```

### 3. Generate Encryption Key
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Save the output as `ENCRYPTION_KEY` in `.env`.

### 4. Database Setup
- For cloud hosting: Sign up at [neon.tech](https://neon.tech) (free) and set `DATABASE_URL`.
- For local testing: Leave `DATABASE_URL` empty to automatically use local SQLite!

---

## 📱 User Experience in Telegram

### Running `/setup`
Users are presented with an interactive menu:
- **✨ All-in-One (Same Instance):** Sets up both Attendance and Tasks on the same Odoo URL.
- **📋 Tasks & Timesheets Only:** Connects only your task management instance.
- **⏱️ HR Attendance Only:** Connects only your clock-in/out instance.
- **🔀 Separate Instances:** Connects two different Odoo URLs with skip options.

### Credential Formats Accepted:
Users can send either plain lines or labeled values:
```text
https://skit-timesheet.odoo.com
skit-timesheet
your_username_or_email
your_api_key_or_password
```
*(Any labels like `URL:`, `Database:`, `Username:`, `API Key:` are stripped and sanitized automatically).*

### What happens if an instance is not configured?
- If a user only connects **Tasks & Timesheets**:
  - Asking for tasks, logging time, or completing tasks works immediately!
  - Asking to clock in returns a polite message with a 1-tap `[ ⏱️ Connect Attendance Instance ]` button.
- If a user only connects **Attendance**:
  - Clock in / out works immediately.
  - Asking for tasks prompts them with a 1-tap `[ 📋 Connect Tasks Instance ]` button.
- `/status` displays the live connection status of both instances.
