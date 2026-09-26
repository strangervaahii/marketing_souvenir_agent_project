import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./orders.db")
    llm_mode: str = os.getenv("LLM_MODE", "mock")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:8001")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "in-house-model")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    auto_dispatch_max_total: float = float(os.getenv("AUTO_DISPATCH_MAX_TOTAL", "500"))
    min_reconciliation_confidence: float = float(
        os.getenv("MIN_RECONCILIATION_CONFIDENCE", "0.90")
    )


settings = Settings()
