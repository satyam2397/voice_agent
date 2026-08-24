from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env absolutely rather than relative to the working directory.
# pydantic-settings interprets a bare "env_file" against CWD, so running
# `uvicorn` from backend/ vs. the repo root would silently load a different
# file — or none at all, leaving every secret at its empty default.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent

# Repo-root .env is the shared one; backend/.env overrides it when present.
_ENV_FILES = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    llm_provider: str = "ollama"          # ollama | anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # A flash card is useless if it lands after the moment passed.
    agent_timeout_s: float = 12.0

    database_url: str = "postgresql://sc_user:sc_password@postgres:5432/sales_copilot"
    redis_url: str = "redis://redis:6379/0"

    otel_exporter_otlp_endpoint: str = "http://phoenix:4317"

    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"

    latency_budget_ms: int = 3000
    trigger_confidence_threshold: float = 0.7

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        # The .env carries keys for services not yet wired up (Phoenix UI, etc.).
        # Ignore what we don't model rather than failing to boot over it.
        extra="ignore",
    )

    @property
    def env_files_loaded(self) -> list[str]:
        """Which .env files actually exist — surfaced on /health for debugging."""
        return [str(p) for p in _ENV_FILES if p.exists()]


settings = Settings()
