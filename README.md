# Judge RAG Prototype

A small full-stack prototype for a court-document assistant:

- Upload a document
- Store case/document metadata
- Store docket/case events
- Store legal references/statutes separately from case records
- Split text by page
- Ask questions
- Return source-backed citation cards from documents and events
- Use hybrid retrieval with keyword and local vector scores
- Show retrieval scores and matched terms for debugging
- Validate that citation snippets map back to stored source text
- Generate answers through a separate answer provider layer
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
- digital PDF: `pdftotext` when installed, otherwise rough fallback extraction
- scanned PDF: `pdftoppm` + `tesseract` when installed
- image/TIFF: `tesseract` when installed

Install local OCR tools on macOS:

```bash
brew install tesseract poppler
```

After installing, restart the server:

```bash
python3 backend/server.py
```

To prepare for Azure Document Intelligence:

```bash
export OCR_PROVIDER=azure
export AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://YOUR-RESOURCE.cognitiveservices.azure.com"
export AZURE_DOCUMENT_INTELLIGENCE_KEY="YOUR-KEY"
export AZURE_DOCUMENT_INTELLIGENCE_MODEL="prebuilt-read"
export AZURE_DOCUMENT_INTELLIGENCE_API_VERSION="2024-11-30"
```

The Azure adapter uses the Document Intelligence REST API. It submits the uploaded file, polls the returned operation URL, then stores extracted text by page. Keep Azure keys out of GitHub; use environment variables or a secrets manager.

The answer generation layer lives in:

```text
backend/answer.py
```

By default it uses an extractive provider. It only writes answers from validated retrieved snippets.

To use OpenAI Responses API answer generation:

```bash
export ANSWER_PROVIDER=openai
export OPENAI_API_KEY="YOUR-KEY"
export OPENAI_MODEL="gpt-4.1-mini"
```

To use an Azure OpenAI Responses-compatible endpoint:

```bash
export ANSWER_PROVIDER=azure-openai
export AZURE_OPENAI_API_KEY="YOUR-KEY"
export AZURE_OPENAI_RESPONSES_URL="https://YOUR-ENDPOINT/openai/v1/responses?api-version=YOUR-API-VERSION"
export AZURE_OPENAI_MODEL="YOUR-DEPLOYMENT-OR-MODEL"
```

The app sends only the retrieved citation snippets to the LLM. If the LLM call fails or the key is missing, it falls back to extractive answers. Citation validation still runs before returning an answer.

You can also add docket events and legal references in the sidebar, then ask questions across:

- All sources
- Documents only
- Events only
- Law/rules only

Example question:

```text
Was temporary relief granted?
```

The answer should cite both the uploaded sample document and the docket event when both sources match.

For the legal reference demo, paste content from:

```text
sample-legal-reference.txt
```

Then ask:

```text
What remedies can an order of protection include?
```

The retrieval layer lives in:

```text
backend/search.py
```

It currently uses dependency-free hybrid search:

- keyword scoring for exact names, dates, legal terms, titles, and citations
- local hashed vector scoring for broader semantic overlap
- combined hybrid score for ranking

For production, replace the local vector scoring with pgvector, Azure AI Search, Elasticsearch, or OpenSearch.

## Next Upgrades

- Replace local hashed vectors with pgvector or Azure AI Search embeddings
- Implement the Azure Document Intelligence call in `backend/ocr.py`
- Store metadata in PostgreSQL
- Add pgvector or Azure AI Search
- Add authentication, role-based case access, and audit logs
