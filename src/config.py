"""Central configuration: API endpoints, model names, paths, and the
strict system persona / guardrails for the Agricultural Engineer AI.

All values can be overridden via environment variables (see `.env.example`),
which keeps secrets and per-machine paths out of the source tree.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------- #
# Filesystem layout
# --------------------------------------------------------------------------- #
# Project root = one level up from this file's directory (src/ -> project root).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = PROJECT_ROOT / "data"
VECTOR_STORE_DIR: Path = DATA_DIR / "vector_store"

DOCS_DIR: Path = PROJECT_ROOT / "docs"
BOOKS_DIR: Path = DOCS_DIR / "books"
PRODUCTS_DIR: Path = DOCS_DIR / "products"
PRODUCTS_JSON: Path = PRODUCTS_DIR / "products.json"


class Settings(BaseSettings):
    """Runtime settings, overridable through environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LM Studio (OpenAI-compatible local server) --- #
    lm_studio_base_url: str = Field(
        default="http://localhost:1234/v1",
        description="Base URL of the LM Studio OpenAI-compatible server.",
    )
    lm_studio_api_key: str = Field(
        default="lm-studio",
        description="Placeholder key; LM Studio ignores it but the client requires one.",
    )
    # Chat model as loaded in LM Studio (e.g. a local Gemma build).
    chat_model: str = Field(default="local-model")
    # Embedding model served by LM Studio (must be an embedding-capable model).
    embedding_model: str = Field(default="text-embedding-nomic-embed-text-v1.5")

    # --- Generation params --- #
    temperature: float = Field(default=0.4)
    # Kept generous: reasoning-capable local builds (e.g. Gemma QAT) spend
    # tokens "thinking" before the visible answer, so a tight budget can return
    # empty content with finish_reason="length".
    max_tokens: int = Field(default=2048)
    request_timeout: float = Field(default=120.0)

    # --- Retrieval params --- #
    retrieval_k: int = Field(default=4, description="Botany chunks to retrieve.")
    product_match_k: int = Field(default=3, description="Products to recommend.")
    collection_name: str = Field(default="botany_knowledge")

    # --- Ingestion params --- #
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    ingest_batch_size: int = Field(default=64)

    # --- API / CORS --- #
    # Comma-separated origins; "*" allows all (fine for local dev + mobile).
    cors_allow_origins: str = Field(default="*")

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()


# System persona and guardrails. Injected on every query; the engine fills in
# the {language_instruction}, {context} and {products} placeholders.
SYSTEM_PROMPT: str = """\
You are an expert Agricultural Engineer (Ziraat Muhendisi) working for an
ecological agriculture company. You specialise strictly in plant nutrition,
sustainable/organic fertilization, soil health, and botanical science
education.

# ROLE & TONE
- Give informative, ADVISORY, and NON-PRESCRIPTIVE suggestions.
- Use speculative but professional language. Prefer phrasings such as
  "bunun sebebi ... olabilir", "su yontemleri inceleyebilirsiniz",
  "genellikle onerilen yaklasim ...".
- Base your answer on the retrieved BOTANY CONTEXT below. If the context does
  not cover the question, say so honestly and give general, safe guidance
  instead of inventing facts.

# STRICT PROHIBITIONS (never violate)
- Do NOT diagnose plant diseases. You may describe general symptom patterns,
  but never assert a specific disease as a diagnosis.
- Do NOT recommend chemical pesticides, fungicides, herbicides, medical
  treatments, or any illegal / regulated substances.
- If the user asks for a disease diagnosis or a chemical/medical treatment,
  politely REFUSE and redirect them to a professional in-field soil/plant
  analysis or a licensed agronomist. Do this in the user's own language.

# FOCUS AREAS
Organic plant nutrition, eco-friendly fertilizers, soil health, composting,
micro/macro nutrient balance, and botanical science education.

# PRODUCT RECOMMENDATIONS
- You may be given a list of the company's catalog products below. Only refer
  to products that appear in that list. Never invent product names or links.
- Weave relevant products naturally into the advice as optional suggestions,
  not prescriptions.

# LANGUAGE (critical)
{language_instruction}

# BOTANY CONTEXT (retrieved from reference books)
{context}

# CANDIDATE COMPANY PRODUCTS (may be empty)
{products}
"""


def build_language_instruction(language_hint: str | None = None) -> str:
    """Return the language-matching directive injected into the system prompt.

    The model must answer in the same language the user wrote in. A detected
    hint, when available, is stated explicitly to reduce drift.
    """
    if language_hint:
        return (
            f"Detect the language of the user's message. It appears to be "
            f"'{language_hint}'. Write your ENTIRE response (including botanical "
            f"advice and product recommendations) in that same language. Do not "
            f"switch languages."
        )
    return (
        "Automatically detect the language of the user's message. Write your "
        "ENTIRE response (including botanical advice and product recommendations) "
        "in that exact same language. Do not switch languages."
    )
