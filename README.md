# Citation Validator

A two-step pipeline that extracts all citations from an academic paper and validates each one against the cited source using Gemini LLM.

## Overview

**Step 1 — Extract** (`extract_citations.py`): Reads a paper PDF, uses Gemini to identify every in-text citation and its corresponding bibliography entry, and outputs a CSV.

**Step 2 — Validate** (`validate_citations.py`): For each citation, fuzzy-matches the reference to a local file in `papers/`, uploads it to Gemini, and asks whether the cited paper actually supports the claim. Results are written back to the same CSV.

## Requirements

Use the existing conda environment or install dependencies manually:

```bash
pip install google-genai pymupdf thefuzz python-Levenshtein pandas
```

Set your Gemini API key:

```bash
export GEMINI_MUSIC_AGENT_API_KEY=your_api_key_here
```

## Usage

### Step 1: Extract citations

```bash
python extract_citations.py paper.pdf --output citations.csv
```

Outputs `citations.csv` with columns:

| Column | Description |
|---|---|
| `ref_id` | Citation marker as it appears in text, e.g. `(Smith, 2023)` |
| `context_sentence` | The sentence containing the citation — the claim to verify |
| `reference` | Full bibliography entry from the reference section |

### (Optional) Inspect extracted PDF text

```bash
python extract_text.py paper.pdf
```

Saves `<paper>_text.txt` for manual inspection before running extraction.

### Step 2: Validate citations

Place the cited papers (PDF or image) in the `papers/` directory. Filenames should contain the paper title for fuzzy matching to work.

```bash
python validate_citations.py citations.csv paper.pdf --papers-dir papers/
```

Two columns are added to `citations.csv` in place:

| Column | Description |
|---|---|
| `validated` | `True` if the cited paper supports the claim, `False` otherwise |
| `rationale` | 1–3 sentence explanation citing specific evidence |

### Options

```
--papers-dir   Directory containing cited PDFs/images (default: papers/)
--threshold    Fuzzy match score threshold 0–100 (default: 60)
--delay        Seconds between API calls (default: 2.0)
```

## Multi-citation handling

When a single sentence cites multiple papers (e.g. `(Li, 2020; Dang, 2026)`), the validator automatically detects the citation count, finds all matching files, uploads them together, and asks Gemini to evaluate the claim against all cited papers collectively.

## Supported file formats

The `papers/` directory accepts: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`

## Notes

- The main paper is processed via text extraction (PyMuPDF) since large PDFs exceed the Gemini upload limit. Cited papers are uploaded directly as files.
- Already-validated rows are skipped on re-runs, so interrupted runs can be safely resumed.
- Model: `gemini-3.1-pro-preview`
