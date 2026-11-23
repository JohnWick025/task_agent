import os
from pathlib import Path
from typing import List

# Attempt to load .env with dotenv or standard library fallback
env_path = Path(".env")
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v


class Settings:
    def __init__(self):
        # Telegram
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_WEBHOOK_URL: str = os.getenv("TELEGRAM_WEBHOOK_URL", "")
        self.TELEGRAM_SECRET_TOKEN: str = os.getenv("TELEGRAM_SECRET_TOKEN", "secret-telegram-webhook-token")

        # Multi-tenant Database (Neon Postgres or local SQLite fallback)
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")

        # Encryption Key
        self.ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

        # LLM Provider Selection: 'auto', 'openrouter', 'gemini', 'groq', 'nvidia', 'ollama', 'openai', or 'custom'
        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").strip().lower()

        # OpenRouter (Supports free models and paid models like Claude, Gemini, DeepSeek, Llama)
        self.OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
        self.OPENROUTER_MODELS: str = os.getenv(
            "OPENROUTER_MODELS",
            "deepseek/deepseek-chat,qwen/qwen-2.5-72b-instruct,meta-llama/llama-3.1-70b-instruct"
        ).strip()

        # Google Gemini (Direct via OpenAI-compatible endpoint)
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
        self.GEMINI_MODELS: str = os.getenv("GEMINI_MODELS", "gemini-2.0-flash,gemini-1.5-flash").strip()

        # Groq (Ultra-fast inference)
        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
        self.GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
        self.GROQ_MODELS: str = os.getenv(
            "GROQ_MODELS",
            "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b,llama-3.3-70b-versatile"
        ).strip()

        # NVIDIA NIM
        self.NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "").strip()
        self.NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
        self.NVIDIA_MODELS: str = os.getenv(
            "NVIDIA_MODELS",
            "meta/llama-3.3-70b-instruct,meta/llama-3.1-70b-instruct,mistralai/mixtral-8x22b-instruct"
        ).strip()

        # Local Ollama
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

        # OpenAI Direct
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Custom / Generic OpenAI Compatible Endpoint
        self.CUSTOM_LLM_BASE_URL: str = os.getenv("CUSTOM_LLM_BASE_URL", "")
        self.CUSTOM_LLM_API_KEY: str = os.getenv("CUSTOM_LLM_API_KEY", "")
        self.CUSTOM_LLM_MODEL: str = os.getenv("CUSTOM_LLM_MODEL", "")

        # Server
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("PORT", "8000"))
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    def get_fernet_key(self) -> bytes:
        if self.ENCRYPTION_KEY:
            return self.ENCRYPTION_KEY.encode("utf-8")
        return b"Zz9yWEpZZkR2eXhzM0xCY1VfVk5rOHFvbW52c0V2YmU="


settings = Settings()
