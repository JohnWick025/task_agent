import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI, APIError
from app.config import settings

logger = logging.getLogger(__name__)


class ProviderEndpoint:
    def __init__(self, name: str, base_url: str, api_key: str, models: List[str]):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key or "dummy-key"
        self.models = models or ["default"]
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        self.current_model_idx = 0

    @property
    def current_model(self) -> str:
        return self.models[self.current_model_idx % len(self.models)]

    def rotate_model(self) -> str:
        self.current_model_idx = (self.current_model_idx + 1) % len(self.models)
        return self.current_model


class UniversalLLMProvider:
    """
    Universal LLM provider with multi-provider failover and automatic model rotation.
    Supports OpenRouter, Google Gemini, Groq, NVIDIA NIM, Local Ollama, OpenAI, and custom endpoints.
    """

    def __init__(self):
        self.providers: List[ProviderEndpoint] = []
        self._setup_providers()
        self.current_provider_idx = 0

    def _setup_providers(self):
        # 1. OpenRouter
        if settings.OPENROUTER_API_KEY:
            models = [m.strip() for m in settings.OPENROUTER_MODELS.split(",") if m.strip()]
            self.providers.append(
                ProviderEndpoint("OpenRouter", settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, models)
            )

        # 2. Google Gemini
        if settings.GEMINI_API_KEY:
            models = [m.strip() for m in settings.GEMINI_MODELS.split(",") if m.strip()]
            self.providers.append(
                ProviderEndpoint("Google Gemini", settings.GEMINI_BASE_URL, settings.GEMINI_API_KEY, models)
            )

        # 3. Groq
        if settings.GROQ_API_KEY:
            models = [m.strip() for m in settings.GROQ_MODELS.split(",") if m.strip()]
            self.providers.append(
                ProviderEndpoint("Groq", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, models)
            )

        # 4. NVIDIA NIM
        if settings.NVIDIA_API_KEY:
            models = [m.strip() for m in settings.NVIDIA_MODELS.split(",") if m.strip()]
            self.providers.append(
                ProviderEndpoint("NVIDIA NIM", settings.NVIDIA_BASE_URL, settings.NVIDIA_API_KEY, models)
            )

        # 5. Local Ollama
        if settings.OLLAMA_BASE_URL:
            models = [settings.OLLAMA_MODEL]
            self.providers.append(
                ProviderEndpoint("Local Ollama", settings.OLLAMA_BASE_URL, "ollama", models)
            )

        # 6. OpenAI
        if settings.OPENAI_API_KEY:
            models = [settings.OPENAI_MODEL]
            self.providers.append(
                ProviderEndpoint("OpenAI", settings.OPENAI_BASE_URL, settings.OPENAI_API_KEY, models)
            )

        # 7. Custom Endpoint
        if settings.CUSTOM_LLM_BASE_URL:
            models = [settings.CUSTOM_LLM_MODEL or "default"]
            self.providers.append(
                ProviderEndpoint("Custom", settings.CUSTOM_LLM_BASE_URL, settings.CUSTOM_LLM_API_KEY, models)
            )

        # If user explicitly preferred a specific provider, prioritize it to the front
        preferred = settings.LLM_PROVIDER
        if preferred != "auto":
            match = [p for p in self.providers if p.name.lower().startswith(preferred)]
            rest = [p for p in self.providers if not p.name.lower().startswith(preferred)]
            self.providers = match + rest

        if not self.providers:
            # Fallback placeholder to prevent startup crashes when no keys are supplied yet
            self.providers.append(
                ProviderEndpoint(
                    "Fallback",
                    settings.NVIDIA_BASE_URL,
                    "dummy-key",
                    ["meta/llama-3.3-70b-instruct"]
                )
            )

    @property
    def active_provider(self) -> ProviderEndpoint:
        return self.providers[self.current_provider_idx % len(self.providers)]

    def _rotate_provider(self):
        prev = self.active_provider.name
        self.current_provider_idx = (self.current_provider_idx + 1) % len(self.providers)
        logger.warning(f"Rotating from provider '{prev}' to '{self.active_provider.name}'")

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.2,
        max_retries: int = 6
    ) -> Any:
        last_error = None

        for attempt in range(max_retries):
            provider = self.active_provider
            model = provider.current_model
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice

                response = provider.client.chat.completions.create(**kwargs)
                choice = response.choices[0] if response.choices else None
                if choice:
                    # Detect provider internal failures (e.g. OpenRouter upstream provider error)
                    if getattr(choice, "finish_reason", None) == "error":
                        raise RuntimeError(f"Provider returned finish_reason='error'")
                    # Detect empty/null response without tool calls
                    if not choice.message.content and not getattr(choice.message, "tool_calls", None):
                        raise RuntimeError(f"Provider returned empty response without tool calls")
                return response

            except Exception as e:
                err_str = str(e)
                logger.error(f"[{provider.name} | {model}] Error: {err_str}")
                last_error = f"{provider.name} ({model}): {err_str}"

                # First, rotate to next model inside this provider
                old_model = model
                new_model = provider.rotate_model()
                if new_model == old_model or provider.current_model_idx == 0:
                    # Cycled through all models of this provider, failover to next provider
                    self._rotate_provider()

        raise RuntimeError(f"All LLM providers and models failed. Last error: {last_error}")


llm_provider = UniversalLLMProvider()
