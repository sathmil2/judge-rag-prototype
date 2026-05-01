# Judge RAG Prototype

A small full-stack prototype for a court-document assistant:

- Upload a document
- Store case/document metadata
- Store docket/case events
- Split text by page
- Ask questions
- Return source-backed citation cards from documents and events
- Show retrieval scores and matched terms for debugging
- Open the cited document page

This first version is intentionally dependency-light. The backend uses Python's standard library, and the frontend is plain HTML/CSS/JavaScript. It is designed as a learning scaffold that can later be upgraded to React, Spring Boot, OCR, vector search, and Azure/OpenAI services.

## Run

```bash
python3 backend/server.py
```

Then open:

```text
http://localhost:8000
```

## Try It

Upload a `.txt` file first. Use form-feed characters to separate pages if you want page mapping:

```text
Page one text...

\f
Page two text...
```

PDF upload is accepted for storage/viewing, but this dependency-free prototype cannot reliably extract text from scanned or complex PDFs. In production, plug OCR into `extract_document` in `backend/ocr.py`.

The extraction layer now lives in:

```text
backend/ocr.py
```

By default it uses the local provider:

- `.txt`, `.md`, `.csv`: full page text extraction
- simple digital PDF: rough fallback extraction
- scanned PDF/TIFF/image: marked as `needs_ocr`

To prepare for Azure Document Intelligence:

```bash
export OCR_PROVIDER=azure
export AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://YOUR-RESOURCE.cognitiveservices.azure.com"
export AZURE_DOCUMENT_INTELLIGENCE_KEY="YOUR-KEY"
```

The Azure adapter boundary is scaffolded, but the actual cloud OCR polling call is intentionally left as the next integration step so keys and security choices are handled deliberately.

You can also add a docket event in the sidebar, then ask questions across:

- Documents and events
- Documents only
- Events only

Example question:

```text
Was temporary relief granted?
```

The answer should cite both the uploaded sample document and the docket event when both sources match.

## Next Upgrades

- Replace `backend/search.py` keyword scoring with hybrid search
- Implement the Azure Document Intelligence call in `backend/ocr.py`
- Store metadata in PostgreSQL
- Add pgvector or Azure AI Search
- Add OpenAI/Azure OpenAI answer generation
- Add authentication, role-based case access, and audit logs
