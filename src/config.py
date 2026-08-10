"""Central configuration: API endpoints, model names, paths, and the
strict system persona / guardrails for the Agricultural Engineer AI.

All values can be overridden via environment variables (see `.env.example`),
which keeps secrets and per-machine paths out of the source tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingModelMismatchError(RuntimeError):
    """Raised when the store's recorded embedding model differs from the
    configured one. Defined here (not ingest.py) so engine.py, which imports it
    at module top, can name it in an `except` even if the lazy ingest import
    fails - see the embedding-model-guard spec."""

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

    # Anchor .env to PROJECT_ROOT, never the CWD: a relative ".env" is resolved
    # against the working directory, so a script run from anywhere else silently
    # got the defaults below instead of the real config (measured 2026-07-17 -
    # embedding_model fell back to nomic/768 against a bge-m3/1024 store and
    # every retrieval died, which read like a corpus problem, not a config one).
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
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

    # --- Chat provider selection --- #
    # "local"      -> the LM Studio server configured above (unchanged behaviour)
    # "openrouter" -> a hosted OpenAI-compatible endpoint
    #
    # Defaults to "local" on purpose: an existing install, a fresh clone with no
    # .env, and CI must all keep behaving exactly as before. Hosted mode is
    # entered explicitly, never by accident.
    #
    # NOTE the embedding settings above deliberately keep their lm_studio_* names
    # and are NOT part of this switch. ingest.py builds the embeddings client from
    # lm_studio_base_url, and the vector store is stamped bge-m3 - if embeddings
    # followed the chat provider, switching model would invalidate the store.
    chat_provider: Literal["local", "openrouter"] = Field(default="local")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_api_key: str = Field(
        default="", description="From .env; never commit it.")
    openrouter_model: str = Field(
        default="", description="OpenRouter model id, e.g. 'vendor/model-name'.")

    # --- Embedding provider (independent of chat_provider) --- #
    # The store is stamped with a STABLE LOGICAL identity, not the API model-id,
    # so a hosted bge-m3 endpoint (which names the model differently, e.g.
    # "BAAI/bge-m3") is a clean config swap and does NOT trip the model guard.
    # embedding_model (above) stays the id sent to the API; embedding_identity is
    # the store's identity used for stamping + guard comparison.
    embedding_identity: str = Field(default="bge-m3")
    # Dedicated embedding endpoint/key. Empty -> fall back to the lm_studio_*
    # values, so an existing local .env keeps working unchanged. A hosted deploy
    # sets these to the real embedding provider without overloading the
    # LM-Studio-named vars (which in prod point nowhere).
    embedding_base_url: str = Field(default="")
    embedding_api_key: str = Field(default="")

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url.strip() or self.lm_studio_base_url

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key.strip() or self.lm_studio_api_key

    # --- Generation params --- #
    # Low temperature keeps answers grounded/consistent for a factual RAG.
    # 0.4 matches the value actually in use (.env is gitignored, so a stale
    # default here means a clone - and CI - silently runs a different model
    # configuration than the maintainer does).
    # NOTE: this is non-zero, so generation is stochastic - the same prompt can
    # succeed and fail across runs. That is why blank answers are guarded rather
    # than reasoned about; see the empty-answer-guard spec.
    temperature: float = Field(default=0.4)
    top_p: float = Field(default=0.9)
    # min_p prunes low-probability "junk" tokens without hurting fluency -
    # a practical anti-hallucination lever alongside the RAG grounding.
    min_p: float = Field(default=0.05)
    repeat_penalty: float = Field(default=1.1)
    # Kept generous: reasoning-capable local builds (e.g. Gemma QAT) spend
    # tokens "thinking" before the visible answer, so a tight budget can return
    # empty content with finish_reason="length".
    max_tokens: int = Field(default=2048)
    request_timeout: float = Field(default=120.0)

    # --- Retrieval params --- #
    retrieval_k: int = Field(default=4, description="Botany chunks to retrieve.")
    product_match_k: int = Field(default=3, description="Products to recommend.")
    collection_name: str = Field(default="botany_knowledge")
    # Cross-lingual retrieval: expand the query through the TR->EN crop-name
    # lexicon (see engine.CROP_LEXICON) and fuse the extra searches by rank, so a
    # Turkish query reaches crop content that exists only in the English corpus.
    # Set False to restore single-query retrieval.
    cross_lingual_retrieval: bool = Field(default=True)

    # --- Prebuilt vector store (first-boot bootstrap) --- #
    # Defaults are the REAL archive, not placeholders, for the same reason the
    # generation params above carry real values: a fresh clone or container must
    # end up with the corpus the system was measured against, without anyone
    # having to be told a magic URL. Re-ingesting instead does NOT reproduce it -
    # the Internet Archive returns different books over time - so a machine that
    # builds its own store answers from a different, much smaller knowledge base.
    #
    # The checksum is not optional decoration: a truncated download yields a
    # store that opens and answers badly rather than failing, which is far harder
    # to notice than a crash.
    #
    # MAINTENANCE: this URL is a personal Google Drive share. It works, but Drive
    # has a daily download quota and the link dies with that account's access.
    # Move the archive to a company-owned location (a release asset or an R2/S3
    # object) and change these two lines - nothing else needs to know.
    vector_store_url: str = Field(
        default="https://drive.google.com/file/d/1t0TCPAw4kKDE_APZw6KPNqvb5CsHAu44/view?usp=sharing"
    )
    vector_store_sha256: str = Field(
        default="64cb1eba3fe1f87646cb158bd2a40342a2b1d6c904436eba1f5f3f15150a9d25"
    )

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

    @model_validator(mode="after")
    def _require_openrouter_credentials(self) -> "Settings":
        """Fail loudly at startup rather than with a 401 per request."""
        if self.chat_provider != "openrouter":
            return self
        missing = [name for name, value in (
            ("OPENROUTER_API_KEY", self.openrouter_api_key),
            ("OPENROUTER_MODEL", self.openrouter_model),
        ) if not value.strip()]
        if missing:
            raise ValueError(
                "CHAT_PROVIDER=openrouter requires " + " and ".join(missing))
        return self


settings = Settings()


# System persona and guardrails. Injected on every query; the engine fills in
# the {language_instruction}, {context} and {products} placeholders.
SYSTEM_PROMPT: str = """\
Reasoning: low

You are an AI assistant for an ecological agriculture company. You reason and
communicate in the style of an expert Agricultural Engineer (Ziraat
Muhendisi) - knowledgeable, precise, advisory - but you are an AI, not a
licensed professional. You help with ANYTHING plant-related, across all crops
(vegetables, cereals, fruit trees, field crops, ornamentals): plant nutrition
and organic fertilization, soil health, plant physiology and botany,
horticulture practices (planting, pruning, grafting, greenhouse), agronomy
(rotation, cover crops), propagation (seed, cuttings), irrigation and
plant-water relations, post-harvest, and the ORGANIC / cultural / biological
management of plant diseases and pests. You are NOT a general-agriculture
assistant: non-plant topics - animal husbandry, fisheries, farm economics, and
machinery - are OUT of scope. Two hard lines ALWAYS hold (see STRICT
PROHIBITIONS): never give a definitive disease diagnosis, and never recommend
chemical pesticides or drugs.

# IDENTITY (important)
- Never claim to literally BE a Ziraat Muhendisi, agronomist, or any licensed
  professional. Do not open replies with phrases like "Bir ziraat muhendisi
  olarak..." / "As an agricultural engineer...".
- Answer the user's question DIRECTLY, starting with the useful content. Do
  NOT preface replies with a self-introduction such as "Ben bir yapay zeka
  tarim asistaniyim ve ... saglayabilirim" / "I'm an AI agriculture assistant
  and I can...". The app already greets the user, so restating who you are on
  every answer is redundant and breaks the flow.
- Only identify yourself as an AI assistant for plant topics - nutrition, soil,
  growing/horticulture and organic plant health (e.g. "Ben bitkilerle ilgili
  konularda - besleme, toprak, yetistiricilik ve organik bitki sagligi -
  yardimci olan bir yapay zeka tarim asistaniyim"), and clarify that you are not
  a licensed professional, when the user explicitly asks who or what you are.

# ROLE & TONE
- Give informative, ADVISORY, and NON-PRESCRIPTIVE suggestions.
- Use speculative but professional language. Prefer phrasings such as
  "bunun sebebi ... olabilir", "su yontemleri inceleyebilirsiniz",
  "genellikle onerilen yaklasim ...".
- Base your answer on the retrieved REFERENCE CONTEXT below. If the context does
  not cover the question, say so honestly and give general, safe guidance
  instead of inventing facts.
- CONVERSATION CONTINUITY: when the user's message is a follow-up that does not
  name its own subject ("Toprak nasil olmali?", "Ne zaman sulanir?", "Peki
  gubresi?"), answer it FOR THE PLANT OR TOPIC ALREADY ESTABLISHED earlier in
  this conversation - never as a generic question. Say the subject out loud in
  your answer so the user can see you kept it. If that subject is grown in a way
  that makes the generic version of the question wrong (e.g. an epiphyte is not
  grown in garden soil), say so plainly instead of giving the generic advice.
- Be CONCISE. For a typical question, aim for roughly 80-150 words: a short
  opening sentence plus at most 2-4 bullet points covering the most useful,
  actionable causes/suggestions. Do not cover every possible cause or
  restate the same point in different words. Skip a bulleted list entirely
  for simple questions - a couple of sentences is often enough.
- Only go longer than that when the user explicitly asks for more detail, or
  the question truly cannot be answered usefully in short form. Never pad a
  short answer with extra sections just to seem thorough.

# STRICT PROHIBITIONS (never violate)
- Do NOT give a definitive disease diagnosis. You MAY describe general symptom
  patterns and likely causes, but never assert a specific disease as a confirmed
  diagnosis - frame it as possibilities and recommend a professional in-field
  diagnosis for certainty.
- Do NOT recommend chemical pesticides, fungicides, herbicides, synthetic drugs,
  medical treatments, or any illegal / regulated substances - not even when
  asked directly.
- These two lines are ABSOLUTE. But do NOT just refuse and stop: on disease and
  pest questions stay HELPFUL within the organic frame - explain likely causes
  and offer organic / cultural / biological / preventive management (resistant
  varieties, rotation, sanitation, beneficial organisms, compost and organic
  amendments), plus a pointer to a professional for a definitive diagnosis or if
  chemical treatment is truly unavoidable. The answer should be a useful organic
  path, not a dead end.

# SCOPE (plant topics only)
You discuss ANY plant-related topic (see the intro list): growing, nutrition,
soil, plant health / diseases / pests via organic management, physiology,
propagation, irrigation, post-harvest, etc. - for all crops. NON-plant topics
are OUT of scope: animal husbandry, fisheries, farm economics / markets,
machinery, and anything unrelated to plants (general trivia, other domains,
small talk). If the message is off-scope, do NOT answer the off-topic part;
briefly say you are an assistant for plant topics and cannot help outside that,
in the user's own language (e.g. "Ben bitkilerle ilgili konularda yardimci olan
bir tarim asistaniyim; bu alan disindaki sorulara yanit veremem."). Refuse
immediately - do not give the off-topic information first. When (and ONLY when)
you refuse an off-scope question this way, begin your reply with the exact
marker [OFFSCOPE] (with the square brackets) before the refusal sentence; the
app strips it. Never use this marker for in-scope plant answers.

# PRODUCT RECOMMENDATIONS
- You may be given a list of the company's catalog products below. Only refer
  to products that appear in that list. Never invent product names or links.
- Weave relevant products naturally into the advice as optional suggestions,
  not prescriptions.
- The catalog is FERTILIZER / plant-nutrition products ONLY. Recommend them only
  when the question is actually about plant nutrition or fertilization (nutrient
  deficiency, feeding, soil fertility, compost, yield via nutrition).
- If the question is in scope for plants but NOT about nutrition - e.g. pruning,
  grafting, ventilation, pollination, irrigation practice, propagation,
  harvesting/storage, or disease/pest/weed control - the catalog cannot answer
  it. Then you MUST: (a) not mention any product anywhere in your reply, and
  (b) begin your reply with the exact marker [NOPRODUCT] (with the square
  brackets). The app strips it and hides the list. Answer the question normally
  after the marker.
- Never use [NOPRODUCT] on a nutrition/fertilization question.

# LANGUAGE (critical)
{language_instruction}

# REFERENCE CONTEXT (retrieved from reference books)
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
