# Judge RAG Prototype

A small full-stack prototype for a court-document assistant:

- Upload a document
- Store case/document metadata
- Split text by page
- Ask questions
- Return source-backed citation cards
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

PDF upload is accepted for storage/viewing, but this dependency-free prototype cannot reliably extract text from scanned or complex PDFs. In production, plug OCR into `extract_pages` in `backend/server.py`.

## Next Upgrades

- Replace keyword scoring with hybrid search
- Add Azure AI Document Intelligence OCR
- Store metadata in PostgreSQL
- Add pgvector or Azure AI Search
- Add OpenAI/Azure OpenAI answer generation
- Add authentication, role-based case access, and audit logs

