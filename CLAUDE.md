# CLAUDE.md — Workspace Rules for Claude

This file is automatically read by Claude at the start of every session.

## Workspace Overview

This workspace contains multiple **independent** directories.
They are NOT related unless explicitly stated.

| Directory | Purpose |
|---|---|
| `client-projects/` | Client-specific deliverables. Isolated per client/contract. |
| `products/` | My own products and tools (long-term assets). |
| `marketing/` | Marketing assets for my own services/products. |
| `reusable/` | Generalized templates. No client-specific content. |
| `ideas/` | Notes, concepts, drafts. Documentation only. |

## Mandatory Rules

1. **Always work ONLY in the directory explicitly specified by the user.**
2. **Do NOT mix logic, content, or context across directories.**
3. `client-projects/` must remain strictly isolated — no reuse without abstraction.
4. `reusable/` must contain abstracted, non-client-specific content only.
5. **If no target directory is specified, ask before proceeding.**

## Directory-Specific Notes

### client-projects/
- Each subdirectory = one client. Do not cross-reference clients.
- Treat all content as confidential.

### products/
- `ebay-inventory-tool/` — Python scraper + eBay listing automation
- `google-integration/` — Google Calendar / Drive / Gmail agent
- `trustlink/` — In planning phase

### reusable/
- `matching-lp/` — LP generation template (HTML + image assets + Python scripts)
  - Scripts: `nanobanana_generate_*.py`, `check_models.py`
  - Output: `index.html`

### ideas/
- Documentation-focused. No production code here.

## Code Style Preferences

- Python: follow PEP8, use type hints where practical
- Use `.env` files for secrets (never hardcode credentials)
- Each product manages its own `requirements.txt`

## What NOT to Do

- Never commit `.env` files
- Never mix client data into `reusable/` or `ideas/`
- Never create files outside the specified target directory without asking
