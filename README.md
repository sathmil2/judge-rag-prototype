# Judge RAG Prototype

A small full-stack prototype for a court-document assistant:

- Upload a document
- Store case/document metadata
- Store docket/case events
- Split text by page
- Ask questions
- Return source-backed citation cards from documents and events
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

- Replace keyword scoring with hybrid search
- Add Azure AI Document Intelligence OCR
- Store metadata in PostgreSQL
- Add pgvector or Azure AI Search
- Add OpenAI/Azure OpenAI answer generation
- Add authentication, role-based case access, and audit logs
