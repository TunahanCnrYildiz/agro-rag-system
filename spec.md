# Project Specification: Agro-Botany RAG & Product Linker System

## 1. Project Overview & Goals
This project aims to build a production-ready, Python-based RAG (Retrieval-Augmented Generation) backend. The system will power a Mobile App chatbot and a Web Widget for an ecological agriculture company (`https://www.ekolojiktarim.com.tr/`).

The AI will act as an **expert Agricultural Engineer (Ziraat Mühendisi)** focusing strictly on plant nutrition, sustainable fertilization, and botany education.

---

## 2. Technical Stack
*   **LLM Provider:** LM Studio (Localhost API running Gemma Local Model via `http://localhost:1234/v1`)
*   **RAG Framework:** LangChain or LlamaIndex (Python)
*   **Vector Database:** ChromaDB or FAISS (Local persistent storage)
*   **Backend API:** FastAPI (To serve both Mobile App and Web Widget)
*   **Data Processing:** PyPDF2 / Unstructured (For processing hundreds of botany books)
*   **Scraping Tools:** Beautiful Soup / Requests (To fetch product links from the website)

---

## 3. Strict System Persona & Guardrails (System Prompt)
The AI must strictly adhere to the following rules in all completions:
*   **Role:** Act as an expert Agricultural Engineer giving informative, non-prescriptive, and advisory suggestions. Use speculative but professional language (e.g., "bunun sebebi x olabilir, şu yöntemleri inceleyebilirsiniz").
*   **STRICT PROHIBITION:** Do **NOT** diagnose plant diseases and do **NOT** recommend chemical pesticides, medical treatments, or illegal substances (*ilaç ve hastalık teşhis/önerisi kesinlikle yasaktır*). If asked, politely refuse and redirect the user to professional field analysis.
*   **Focus Areas:** Organic plant nutrition, eco-friendly fertilizers, soil health, and botanical science education.
*   **Multilingual Support & Language Matching:** The AI must automatically detect the language of the user's input query. The entire response (including product recommendations and botanical advice) MUST be generated in the exact same language the user used.

---

## 4. Key Functional Requirements

### Task A: E-Commerce Product Integration (Scraper & Metadata)
1.  Write a utility script (`scraper.py`) to crawl `https://www.ekolojiktarim.com.tr/`.
2.  Extract product names, descriptions, categories, and direct URLs.
3.  Save this product index into a structured format (JSON or an isolated Vector DB collection) with explicit metadata schemas containing `product_name` and `source_url`.
4.  **Behavior:** When a user asks about plant nutrition issues, the RAG system must fetch botanical solutions from books AND automatically match relevant products from the company's catalog, outputting the exact product link.

### Task B: Document Ingestion Pipeline
1.  Create a data directory (`/docs/books/`) to hold hundreds of PDF/text documents about botany and fertilization.
2.  Implement a chunking mechanism (suggested: `RecursiveCharacterTextSplitter` with chunk size 1000 and overlap 200).
3.  Generate embeddings using a highly capable local embedding model or default local server configurations, and persist them in `/data/vector_store/`.

### Task C: Core RAG Query Engine & LM Studio Router
1.  Connect via OpenAI-compatible client to LM Studio local server (`localhost:1234`).
2.  Combine Contextual Retrieval (Botany knowledge) + Product Metadata Lookup (Company catalog).
3.  Format the final payload ensuring the **System Prompt** constraints are injected safely on every query.

### Task D: Unified REST API (FastAPI)
1.  Expose an endpoint `/api/chat` accepting JSON payloads: `{"message": "user query", "history": [...]}`.
2.  The endpoint must support streaming or unified JSON response containing the message answer and a separate array of `recommended_products: [{"title": "...", "link": "..."}]`.
3.  This API will serve both the web widget and the mobile app concurrently.

---

## 5. Expected Directory Structure
Claude Code must initialize the project with the following clean, modular structure:
```text
agro-rag-system/
│
├── data/
│   └── vector_store/       # Persistent Vector DB files
├── docs/
│   ├── books/              # PDF/TXT source files for Botany
│   └── products/           # Scraped company product catalog (JSON/CSV)
│
├── src/
│   ├── __init__.py
│   ├── config.py           # API keys, Base URLs, System Prompts
│   ├── scraper.py          # Web scraper script for ekolojiktarim.com.tr
│   ├── ingest.py           # Document processing & embedding generation script
│   ├── engine.py           # Core RAG querying logic & LM Studio communication
│   └── main.py             # FastAPI Application server
│
├── requirements.txt        # Dependencies
└── README.md               # Quickstart and execution log
```

---

## 6. Execution Instructions for Claude Code
1.  **Step 1:** Create the directory structure and initialize a local `git` repository.
2.  **Step 2:** Write `requirements.txt` containing `fastapi`, `uvicorn`, `langchain`, `chromadb`, `beautifulsoup4`, `requests`, `pypdf`. Install dependencies.
3.  **Step 3:** Implement `scraper.py` to target product structures on `https://www.ekolojiktarim.com.tr/`. Create a fallback mocked version if external requests are rate-limited.
4.  **Step 4:** Build `ingest.py` to safely process document batches without leaking memory.
5.  **Step 5:** Write `engine.py` incorporating the **Strict Safety Guardrails** and **Multilingual Support** in the prompt layout.
6.  **Step 6:** Launch the FastAPI application via `main.py` with proper CORS policies enabled for mobile and web clients.