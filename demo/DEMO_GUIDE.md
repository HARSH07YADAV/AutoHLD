# AutoHLD — 5–7 Minute Demonstration Flow
**Audience:** Tata Technologies Automotive Engineering AI Workshop / Technical Evaluators  
**Goal:** Demonstrate a grounded, practical RAG & document analysis tool on an AUTOSAR High-Level Design document without overpromising or using AI buzzwords.

---

## Pre-Demo Checklist (1 Minute Before Presentation)

1. **Start the backend server:**
   ```bash
   cd /home/anchorpoint/AutoHLD
   PYTHONPATH=. .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. **Open browser:** Navigate to `http://localhost:8000` (ensure dark/light mode preference is set).
3. **Have sample PDF ready:** Ensure `tests/sample_docs/sample_hld.pdf` exists. If not, generate it:
   ```bash
   python tests/generate_sample_pdf.py
   ```
4. **Clean state:** If you want a fresh demo, you can delete previous uploads from the **Document Upload** tab.

---

## Complete Demo Sequence

### Step 1: Introduce the Problem (⏱️ 0:00 – 0:45)
- **What to click:** Stay on the **Dashboard** tab.
- **What to show on screen:** Point out the clean engineering dashboard layout with Document Status, Extracted Entities count, and System Health.
- **What to say:**
  > "In automotive systems engineering—particularly with AUTOSAR architectures—High-Level Design documents are often 30 to over 100 pages long. They blend prose, port tables, interface definitions, and signal flows.
  >
  > When an engineer or reviewer joins a project, finding answers to simple questions like *'Which component provides this voltage signal?'* or checking if an interface is defined consistently across sections requires tedious manual cross-referencing.
  >
  > AutoHLD is a lightweight, local engineering assistant built to solve this. It combines Retrieval-Augmented Generation (RAG) for plain-English queries with deterministic heuristic checks for document consistency—all while strictly retaining source page numbers."
- **Technical concept demonstrated:** Domain-specific documentation complexity and the need for provenance-preserving RAG in safety-conscious automotive engineering.

---

### Step 2: Upload an AUTOSAR HLD Sample PDF (⏱️ 0:45 – 1:30)
- **What to click:** Click on the **Document Upload** tab. Drag-and-drop or select `sample_hld.pdf` from `tests/sample_docs/`.
- **What to show on screen:** The upload zone highlights, file size is displayed (synthetic 9-page BMS design), and the upload progress activates.
- **What to say:**
  > "I'll upload a sample 9-page AUTOSAR High-Level Design for an EV Battery Management System (BMS). The PDF contains three main software components: `BmsController`, `CellMonitoringUnit`, and `ThermalManagement`, along with port definitions and signal tables."
- **Technical concept demonstrated:** Client-side file validation, secure multipart streaming, and asynchronous pipeline initiation.

---

### Step 3: Show Document Processing (⏱️ 1:30 – 2:00)
- **What to click:** Observe the pipeline status badges update in real-time or switch to the **Dashboard** / **Overview** tab.
- **What to show on screen:** Processing stages transitioning: `Parsing PDF` $\rightarrow$ `Extracting Text & Tables` $\rightarrow$ `Chunking` $\rightarrow$ `Generating Embeddings` $\rightarrow$ `Ready`. Page count (9 pages) and chunk count (~16 chunks) displayed.
- **What to say:**
  > "Under the hood, `pdfplumber` extracts text page-by-page. A sliding-window chunker splits the text into ~450-token segments with a 200-character overlap, strictly tagging every single chunk with its source page number and detected section.
  > 
  > We then pass these chunks through a local sentence-transformer (`all-MiniLM-L6-v2`) to produce 384-dimensional dense vectors and store them in an embedded ChromaDB collection. Everything runs entirely locally on our machine—no document data is sent to external clouds."
- **Technical concept demonstrated:** Page-level metadata preservation during ingestion, chunk overlap strategies, dense vector embeddings, and local vector storage.

---

### Step 4: Show Extracted Components & Interfaces (⏱️ 2:00 – 2:45)
- **What to click:** Click the **Components & Interfaces** tab. Click the **Run Extraction** button.
- **What to show on screen:** The entity table populates with categories: Software Components (SWCs), Ports (`P-Port`, `R-Port`), Interfaces, and Signals. Highlight the **Confidence** badge (`High`, `Medium`, `Uncertain`) and **Source Page** link.
- **What to say:**
  > "Next, we run the entity extractor. Notice that rather than claiming 'AI magic', this uses transparent regex patterns tailored to AUTOSAR naming conventions (`SWC_*`, `P_*`, `R_*`, `I*`).
  >
  > Crucially, every entity displays an honest confidence rating and an exact source page. For example, `BmsController` was identified on Page 3 with High confidence, while an abbreviated symbol is flagged as Uncertain for the engineer to verify. We never guess or hallucinate components."
- **Technical concept demonstrated:** Rule-based Named Entity Recognition (NER), heuristic confidence scoring, and transparent human-in-the-loop engineering.

---

### Step 5 & 6: Ask an Architecture Question & Show Grounded Answer with Citations (⏱️ 2:45 – 3:45)
- **What to click:** Click the **Ask the HLD** tab. Type the question:
  ```text
  Which component provides the battery voltage signal and what interface is used?
  ```
  *(Or click one of the quick sample question buttons if available).* Click **Ask**.
- **What to show on screen:** The system retrieves top matching chunks, displays the streaming or completed response, and renders explicit clickable **[Page 3]**, **[Page 4]** citation pills next to the text.
- **What to say:**
  > "Now let's ask a typical engineering query: *'Which component provides the battery voltage signal and what interface is used?'*
  >
  > The retrieval engine embeds our question, performs a similarity search in ChromaDB, and pulls the top 5 most relevant chunks. The local LLM is given strict instructions: answer *only* from the supplied excerpts.
  >
  > As you see on screen: `CellMonitoringUnit` provides the battery voltage signal via `P_BattVolt` using interface `IBattVolt`.
  >
  > Notice the page citation pills at the bottom. These are assembled directly from the vector store metadata—not made up by the language model. If an engineer wants to verify the statement, they know exactly which page of the PDF to open."
- **Technical concept demonstrated:** Retrieval-Augmented Generation (RAG), strict prompt grounding against hallucinations, and citation integrity.

---

### Step 7: Show Architecture & Dependency View (⏱️ 3:45 – 4:30)
- **What to click:** Click the **Dependencies** tab.
- **What to show on screen:** The interactive ASCII architecture diagram and connection table showing `BmsController` connected to `CellMonitoringUnit` via matched `P-Port` / `R-Port` pairs.
- **What to say:**
  > "In the Dependencies tab, AutoHLD correlates extracted provider and requester ports to construct a high-level component interaction map.
  >
  > We intentionally use a clear, text-based visualizer that highlights how `CellMonitoringUnit` feeds voltage and temperature signals into `BmsController`. We explicitly label this as an *inferred* connection based on matching interfaces in the document text, so engineers know it represents document claims rather than compiled ARXML."
- **Technical concept demonstrated:** Graph inference from port-interface associations and visualization of architectural topology.

---

### Step 8 & 9: Run Inconsistency Detection & Review a Finding (⏱️ 4:30 – 5:30)
- **What to click:** Click the **Inconsistency Findings** tab. Click **Run Consistency Check**. Then click on the first **Warning** card to expand its details.
- **What to show on screen:** The list of flagged findings grouped by severity (Warning, Review, Info). Expand a finding such as:
  - *Missing Interface Definition for `R_UndefinedBusInterface`* OR
  - *Conflicting Signal Value / Unit between Section 2 and Section 4*.
- **What to say:**
  > "Here is where AutoHLD provides immediate engineering value. Instead of relying on an LLM to guess if something is inconsistent, we run five deterministic rule checks against the extracted records.
  >
  > Let's inspect this Warning: *'Port references an interface not found in interface definitions.'*
  > On Page 5, port `R_UndefinedBusInterface` references an interface that appears nowhere else in the document.
  >
  > AutoHLD displays the exact excerpt, the rule that triggered it, and flags it for human review. It does not pretend to be a formal model compiler—it acts as an automated second pair of eyes during the document review stage."
- **Technical concept demonstrated:** Deterministic static analysis rules complementing generative AI; evidence-based anomaly detection.

---

### Step 10: Generate the Engineering Report (⏱️ 5:30 – 6:15)
- **What to click:** Click the **Reports** tab. Select the document and click **Generate Report**.
- **What to show on screen:** The full 13-section Markdown report renders in the browser, showing metadata, entity tables, dependency maps, findings, Q&A history, and a formal Sign-off block. Highlight the badge tags: `[EXTRACTED]`, `[RULE-BASED]`, `[INFERRED]`, `[AI-GENERATED]`.
- **What to say:**
  > "Finally, we can generate a consolidated Engineering Analysis Report.
  >
  > Notice the provenance headers on each section: we explicitly distinguish what was extracted verbatim from the PDF, what was inferred by our rules, and what was synthesized by the LLM.
  >
  > It includes an engineering sign-off table and can be downloaded as a Markdown document or printed to PDF directly from the browser for inclusion in a review pack."
- **Technical concept demonstrated:** Auditability, transparency of AI vs. rule-based provenance, and exportable engineering artifacts.

---

### Step 11: Summary & Value for Automotive Engineers (⏱️ 6:15 – 7:00)
- **What to click:** Switch back to the **Dashboard** to show the populated metrics.
- **What to show on screen:** Updated metrics: 1 document active, 9 pages processed, 14 entities extracted, 1 query answered, 4 findings reviewed.
- **What to say:**
  > "To summarize: AutoHLD is not an overblown enterprise claim or an attempt to replace AUTOSAR toolchains like DaVinci or SystemDesk.
  >
  > It is a practical, locally runnable developer tool that:
  > 1. Drastically cuts the time required to comprehend large HLD documents.
  > 2. Grounds all Q&A strictly in the text with verifiable page citations.
  > 3. Catches basic cross-reference omissions early, before work reaches the modeling stage.
  >
  > Thank you, and I'd be happy to take any questions."
- **Technical concept demonstrated:** Summary of engineering ROI: localized processing, provenance, and human-in-the-loop verification.

---

## Quick Q&A Cheat Sheet (Anticipated Questions)

| Question | Recommended Answer |
| :--- | :--- |
| *Does this replace formal ARXML validation?* | "No. Formal validation requires schema validation against the AUTOSAR metamodel. AutoHLD focuses on the *document level* (PDFs) during preliminary design reviews before ARXML is created or when reviewing vendor specifications." |
| *Why use ChromaDB and local sentence-transformers?* | "Automotive HLDs often contain proprietary IP. By running ChromaDB and `all-MiniLM-L6-v2` locally, zero proprietary data leaves the engineer's workstation or internal network." |
| *Can the LLM hallucinate answers?* | "We mitigate hallucination through two mechanisms: first, the prompt explicitly instructs the model to only use the retrieved context and declare if information is missing; second, citation page numbers are pulled from ChromaDB chunk metadata, not generated by the LLM." |
| *How are tables handled?* | "`pdfplumber` extracts table structures into text representations so column relationships (e.g., Port Name $\rightarrow$ Interface $\rightarrow$ Direction) are preserved in the chunk text." |
