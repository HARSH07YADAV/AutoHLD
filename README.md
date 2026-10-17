<div align="center">
  <img src="frontend/images/autohld-logo.png" alt="AutoHLD Logo" width="560" />

  <p><strong>AUTOSAR High-Level Design Document Analysis Assistant</strong></p>
</div>

A Python/FastAPI tool that lets an engineer upload an AUTOSAR HLD PDF, ask plain-language questions about it, extract named architectural entities, run a basic consistency check, and download a structured analysis report.

Built as part of the **Tata Technologies Automotive Engineering AI** workshop — demonstrating how RAG (Retrieval-Augmented Generation) can be applied to real automotive engineering documents.

---

## The Problem

AUTOSAR High-Level Design documents can be long (30–200+ pages) and contain a lot of structured information: software components, ports, interfaces, signals, dependencies, and functional flows — spread across tables, diagrams captions, and prose.

Finding specific information, verifying that a port is consistently described across sections, or understanding a dependency chain normally requires a lot of manual searching. This becomes tedious when reviewing unfamiliar documents or comparing revisions.

## The Approach

This tool does four things:

1. **Ingest the PDF** — extracts text and tables page-by-page, preserving page numbers throughout the pipeline
2. **Index for search** — splits the text into overlapping chunks and stores them in a local vector database (ChromaDB) with sentence-transformer embeddings
3. **Answer questions** — uses retrieval-augmented generation: finds the most relevant chunks for a question, passes only those chunks to a local LLM (Ollama), and returns an answer with source page citations
4. **Extract and check** — uses regex patterns and naming-convention heuristics to identify AUTOSAR entities (SWCs, ports, interfaces, signals), then applies five deterministic rules to flag potential consistency issues

**What it is not:** a formal AUTOSAR toolchain validator, a model checker, or a replacement for arxml-based tools. It is a document-level assistant for early review.

---

## Architecture

```
PDF Upload
    │
    ▼
doc_processor.py   — pdfplumber extracts text + tables, page-by-page
    │
    ▼
chunker.py         — splits into ~450-token overlapping chunks, preserves page/section metadata
    │
    ▼
embedder.py        — sentence-transformers (all-MiniLM-L6-v2, 384-dim) generates chunk embeddings
    │
    ▼
ChromaDB           — stores chunks + embeddings locally on disk
SQLite             — stores document metadata, entity records, Q&A history, findings

When a question is asked:

Question → embedder → vector search (ChromaDB) → top-5 chunks
         → prompt_builder.py → [system prompt + retrieved context + question]
         → LLM (Ollama, local) → answer text
         → citations assembled from retriever metadata (not from LLM output)
         → saved to SQLite → returned to frontend

When extraction is run:

All chunks → extractor.py (regex + heuristic rules) → entity records → SQLite
Entity records → inconsistency.py (5 deterministic rules) → finding records → SQLite
```

The frontend is plain HTML/CSS/JS served as static files by FastAPI. No build step required.

---

## Features

**Document Upload**
- Upload any PDF up to 50 MB
- Tracks processing status (uploading → chunking → embedding → ready)
- Lists previously uploaded documents

**Ask the HLD (Q&A)**
- Ask natural language questions: *"What components use the BattV interface?"*, *"What signals are produced by ThermalManagement?"*
- Answers are grounded in the uploaded document — the LLM is instructed not to use training knowledge
- Every answer shows which pages the context came from
- If the answer is not in the document, it says so
- Q&A history is saved and shown per document

**Components & Interfaces**
- Extracts software components, ports (P-Port/R-Port), interfaces, and signals using regex patterns and AUTOSAR naming conventions
- Each entity shows its source page, a confidence level (high/medium/low/uncertain), and the text excerpt it was found in
- Confidence levels are honest — "uncertain" entities should be verified manually

**Dependencies / Architecture Graph**
- Shows relationships inferred from co-located ports and matching base names
- Text-based ASCII relationship view (no external graph library needed)
- Clearly labelled as inferred, not verified against arxml

**Inconsistency Findings**
- Five rule-based checks:
  1. Component referenced in one section but not found in another expected section
  2. Port references an interface not found in the document
  3. Same entity described with conflicting terms across sections
  4. Required port with no corresponding provider found in the document
  5. Same property (e.g. a voltage value) appears with different numeric values
- Each finding shows severity (Warning / Review / Info), the evidence text, and why the rule fired
- No finding is declared definitively wrong — all require engineer review

**Engineering Report**
- Generates a 13-section Markdown report covering all the above
- Each section clearly labels whether content is [EXTRACTED] from the document, [INFERRED] by pattern matching, [RULE-BASED] from deterministic checks, or [AI-GENERATED] by the LLM
- Includes an interactive sign-off section
- Downloadable as `.md`, copyable to clipboard, or printable to PDF via browser

---

## Technology Stack

This project follows the technology stack recommended in the **AUTOSAR HLD Document Analysis Assistant** case study:

| Layer (from case study) | What this project uses | Notes |
| :--- | :--- | :--- |
| **User Interface** | Vanilla HTML/CSS/JS served by FastAPI | Flask Web UI option from the spec — no separate build step needed |
| **API and Services** | FastAPI + Uvicorn | FastAPI preferred for modular APIs, as recommended |
| **LLM** | Ollama (local) — Qwen2.5, Llama3.2, Mistral supported | Local/on-premises as required; no data sent externally |
| **Embeddings** | `sentence-transformers` — `all-MiniLM-L6-v2` (384-dim) | Sentence Transformers option from the spec; ~80 MB, CPU-friendly |
| **Vector Database** | ChromaDB (embedded, file-based) | ChromaDB option from the spec; persistent local storage, no separate server |
| **RAG Orchestration** | Custom Python pipeline | Custom pipeline option from the spec (no LangChain/LlamaIndex dependency) |
| **Structured Storage** | SQLite | SQLite option from the spec; stores documents, entities, Q&A history, findings |
| **Deployment** | Docker + docker-compose | `Dockerfile` and `docker-compose.yml` included — AutoHLD + Ollama start with a single command |

---

## Running with Docker (recommended)

The easiest way to run AutoHLD. Docker starts both the app and a local Ollama LLM server automatically.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Docker Compose plugin on Linux).

### One command to start everything

```bash
make run
```

That's it. This builds the image, starts two containers, and pulls the default LLM model.

- **AutoHLD app** → http://localhost:8000
- **API docs** → http://localhost:8000/docs

The first build takes a few minutes (downloads PyTorch CPU build + embedding model).

### Available `make` commands

| Command | What it does |
| :--- | :--- |
| `make run` | Build image, start containers, pull default LLM model |
| `make stop` | Stop containers (data is preserved) |
| `make restart` | Restart containers without rebuilding |
| `make logs` | Follow live logs from the app container |
| `make clean` | Stop containers and delete all stored data |

### Changing the LLM model

To use a different model, set `OLLAMA_MODEL` in your `.env` file and pull it:

```bash
# In .env:
OLLAMA_MODEL=llama3.2:3b

# Then pull it inside the ollama container:
docker-compose exec ollama ollama pull llama3.2:3b

# Models available:
# qwen2.5:1.5b  — ~1 GB, fast, works on most machines (default)
# llama3.2:3b   — ~2 GB, better quality on technical text
# mistral:7b    — ~4 GB, best quality, needs 8+ GB RAM
```

### Data persistence

All data lives in Docker named volumes — not inside the container:
- `autohld_storage` — uploaded PDFs, ChromaDB vectors, SQLite database, reports
- `ollama_models` — downloaded LLM model weights

Data survives container restarts and rebuilds. Only `make clean` deletes it.

---

## Running without Docker

### Requirements

- Python 3.11 or 3.12
- [Ollama](https://ollama.com) installed and running locally

A machine with 8 GB RAM is sufficient for the default 1.5B model. A 7B model will need more RAM but gives better answers on technical documents.

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd AutoHLD
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

The sentence-transformers package pulls PyTorch as a dependency. On a machine without a GPU, install the CPU-only build first to avoid pulling a large CUDA package:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

If you do not mind the CUDA build (or have a GPU), just:

```bash
pip install -r requirements.txt
```

### 3. Configure the LLM

```bash
cp .env.example .env
```

The default `.env.example` uses Ollama with `qwen2.5:1.5b`. Pull the model:

```bash
# Install Ollama from https://ollama.com, then:
ollama pull qwen2.5:1.5b     # ~1 GB, fast, works on most laptops
# or for better quality on longer documents:
ollama pull llama3.2:3b      # ~2 GB
ollama pull mistral:7b       # ~4 GB
```

Update `OLLAMA_MODEL` in `.env` if you change the model.

**Using OpenAI instead of Ollama:**

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=sk-...` in `.env`. The same prompt builder is used for both providers.

### 4. Run the server

```bash
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open: **http://localhost:8000**

API documentation (auto-generated): **http://localhost:8000/docs**

---

## Example Workflow

1. Go to the **Upload** tab and upload an AUTOSAR HLD PDF
2. Wait for the status to show "ready" (usually 10–30 seconds depending on document size)
3. Go to **Components & Interfaces**, click **Run Extraction** to extract entities
4. Go to **Inconsistency Findings**, click **Run Consistency Check** to flag potential issues
5. Go to **Ask the HLD** and ask questions like:
   - *"What software components are described in this document?"*
   - *"Which component provides the battery voltage signal?"*
   - *"What ports does ThermalManagement have?"*
6. Go to **Reports** and click **Generate Report** for the full structured output

### Testing with the sample document

A synthetic 9-page AUTOSAR Battery Management System HLD is included for testing:

```bash
# Generate the sample PDF
python demo/generate_sample_pdf.py

# It creates: demo/sample_docs/sample_hld.pdf
# Contains: 3 SWCs, port tables, signal definitions, interface list
# Includes: intentional inconsistencies for testing the consistency checker
```

The sample document intentionally has:
- A port that references an undefined interface
- A component referenced in the overview but missing from the port definition section
- A signal value that appears with conflicting units in two sections

This makes it useful for demonstrating all five consistency rules.

### Running tests

```bash
PYTHONPATH=. pytest tests/ -v
```

The test suite covers:
- PDF extraction and chunking
- Embedding and vector storage/retrieval
- RAG pipeline (mocked LLM responses)
- Entity extraction from synthetic text
- All five consistency rules
- API endpoints (integration tests with a test database)

---

## Project Structure

```
AutoHLD/
├── backend/
│   ├── main.py                  # FastAPI app, startup, router registration
│   ├── config.py                # All settings in one place (model names, paths, limits)
│   ├── routers/
│   │   ├── ingest.py            # Upload, status polling, document list, delete
│   │   ├── query.py             # Q&A endpoint, history
│   │   └── analysis.py          # Entity extraction, relationships, consistency check, reports
│   ├── pipeline/
│   │   ├── doc_processor.py     # PDF → raw page content (pdfplumber)
│   │   ├── chunker.py           # Sliding-window chunker, preserves page/section metadata
│   │   ├── embedder.py          # sentence-transformers, batched embedding generation
│   │   ├── ingest.py            # Orchestrates the full ingestion pipeline
│   │   ├── retriever.py         # ChromaDB similarity search, returns typed chunks
│   │   ├── prompt_builder.py    # Assembles LLM prompt from retrieved chunks
│   │   ├── llm_client.py        # Ollama / OpenAI adapter (same interface, different backends)
│   │   └── rag.py               # End-to-end Q&A orchestrator
│   ├── analysis/
│   │   ├── extractor.py         # Regex + heuristic AUTOSAR entity extraction
│   │   ├── inconsistency.py     # Five deterministic consistency rules
│   │   └── report_builder.py    # Compiles structured report data and Markdown output
│   ├── database/
│   │   ├── sqlite_db.py         # Document, entity, finding, Q&A persistence (SQLite)
│   │   └── vector_db.py         # ChromaDB collection wrapper
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   └── utils/
│       ├── file_utils.py        # Upload validation, filename sanitisation
│       └── text_utils.py        # Text cleaning helpers
├── frontend/
│   ├── index.html               # Single-page app, 8 tab panels
│   ├── css/style.css            # All styles (dark/light theme via CSS variables)
│   └── js/
│       ├── api.js               # All HTTP calls to the backend in one file
│       ├── app.js               # Global state, tab routing, theme, document selector
│       ├── dashboard.js         # Dashboard metrics
│       ├── upload.js            # Upload flow, status polling
│       ├── overview.js          # Document overview tab
│       ├── query.js             # Q&A tab
│       ├── components.js        # Entity table view
│       ├── relationships.js     # Dependency/relationship view
│       ├── analysis.js          # Inconsistency findings tab
│       └── reports.js           # Report generation and rendering
├── tests/
│   ├── generate_sample_pdf.py   # Generates synthetic AUTOSAR BMS HLD for demo/testing
│   ├── test_ingestion.py        # PDF extraction, chunking, embedding, retrieval
│   ├── test_rag.py              # RAG pipeline, prompt building, citation assembly
│   └── test_inconsistency.py   # All five consistency rules + extraction
├── storage/                     # Runtime data — not committed to git
│   ├── uploads/                 # Uploaded PDF files
│   ├── chroma_db/               # ChromaDB vector store
│   └── reports/                 # Generated report files
├── templates/                   # Jinja2 templates (for future HTML report export)
├── Dockerfile                   # Builds the AutoHLD app image (python:3.12-slim, CPU PyTorch)
├── docker-compose.yml           # Starts autohld + ollama with a single command
├── .dockerignore                # Keeps the Docker image lean
├── Makefile                     # Short aliases: make run / stop / logs / clean
├── requirements.txt
├── .env.example
└── .gitignore
```


---

## Alignment with Case Study Spec

This project was built against the **Case Study 1: AUTOSAR HLD Document Analysis Assistant** specification from the Tata Technologies Automotive Engineering AI project case studies. Here is how each requirement is covered:

| Case Study Requirement | Status |
| :--- | :--- |
| PDF and supported document ingestion | ✅ pdfplumber handles upload and page-by-page text + table extraction |
| OCR for scanned pages | ⚠️ Not included — works best with digitally produced PDFs |
| Component, interface, port, signal, and flow extraction | ✅ extractor.py with regex + AUTOSAR naming heuristics |
| Natural language search with citations | ✅ RAG pipeline returns answers with page-level source citations |
| Document comparison and inconsistency reporting | ✅ Five deterministic consistency rules in inconsistency.py |
| Export of structured findings | ✅ 13-section Markdown report, downloadable as .md |
| Local / private LLM (Qwen, Llama, Mistral, etc.) | ✅ Ollama runs fully on-premises; no data sent externally |
| Vector store (ChromaDB / FAISS) | ✅ ChromaDB with cosine similarity, persistent local storage |
| Sentence-transformer embeddings | ✅ all-MiniLM-L6-v2 via sentence-transformers |
| Structured metadata storage (SQLite / PostgreSQL) | ✅ SQLite for documents, entities, Q&A history, findings |
| Docker deployment | ✅ `Dockerfile` + `docker-compose.yml` included; AutoHLD + Ollama start with one command |

---

## Known Limitations

**Entity extraction is heuristic, not semantic.** The extractor uses regular expressions and AUTOSAR naming conventions. It will miss entities that do not follow those conventions, and it will occasionally flag false positives. Confidence levels are an honest estimate of pattern-match strength — they do not guarantee correctness.

**The LLM answers are only as good as the retrieved context.** If the relevant information is in a diagram, a scanned table, or a section that the chunker split awkwardly, the answer may be incomplete or wrong. Always verify against the source document.

**ChromaDB is embedded and single-threaded.** It works fine for this use case (one user, one document at a time) but is not suitable for concurrent multi-user access.

**The consistency checker is document-level only.** It works on extracted text, not on parsed arxml. It will not catch issues that require understanding the AUTOSAR metamodel or cross-file references.

**OCR is not included.** Scanned PDFs (images of pages) will produce little or no extracted text. The tool works best with digitally-produced PDFs from AUTOSAR toolchains or Word/LaTeX-generated documents.

**The 1.5B default LLM model is limited.** It handles factual retrieval questions well but struggles with multi-step reasoning or questions that require synthesising many sections. Switching to llama3.2:3b or mistral:7b noticeably improves answer quality.

---

## Configuration Reference

All settings are in `backend/config.py` and can be overridden via `.env`:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `CHUNK_SIZE_CHARS` | 1800 | Approximate chunk size in characters (~450 tokens) |
| `CHUNK_OVERLAP_CHARS` | 200 | Overlap between consecutive chunks |
| `TOP_K_RESULTS` | 5 | Number of chunks to retrieve per question |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model for embeddings |
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Ollama model name |
| `MAX_UPLOAD_SIZE_MB` | 50 | Maximum PDF size |

---

## Possible Improvements

Things that would make this more useful but were out of scope for this project:

- **GPU support in Docker** — the current `Dockerfile` uses CPU-only PyTorch; passing through a GPU would speed up embedding generation on large documents
- **OCR for scanned pages** — add Tesseract or a cloud OCR step before pdfplumber to handle image-based PDFs
- **Better table extraction** — pdfplumber's table handling is inconsistent on complex AUTOSAR tables; camelot or a dedicated parser would help
- **Section detection** — currently uses heading heuristics; a proper document structure parser (font sizes or PDF bookmarks) would be more reliable
- **arxml parsing** — reading actual `.arxml` files directly would allow exact entity extraction rather than the current regex approach
- **Diff/compare mode** — comparing two document versions to highlight what changed
- **Multi-document queries** — asking questions across a set of related HLD documents
- **Role-based access control** — the case study recommends project isolation and approval workflows for production use
- **Export to Excel** — engineers often want entity tables in spreadsheet form for further analysis

---

## Project Context

This was built as a hands-on student project for the **Tata Technologies Automotive Engineering AI** workshop (Case Study 1). The goal was to demonstrate a complete, working RAG pipeline applied to a real domain problem — not to build a production tool.

The architecture and code are intentionally kept straightforward so the implementation can be understood, modified, and extended by another developer without needing to reverse-engineer complex abstractions.

> **Governance Principle (from case study):** AI-generated content must be traceable to approved source material and reviewed by authorised engineering specialists before it is used for compliance, design approval, software release, or vehicle validation. This tool is designed to support engineers in their review — not to replace their judgement or sign-off.
