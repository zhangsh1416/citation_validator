"""
extract_citations.py

Extract all citations from an academic paper PDF using Gemini.

Usage:
    python extract_citations.py <paper.pdf> [--output citations.csv]
"""

import argparse
import json
import os
import re
import sys
import time

import fitz  # PyMuPDF
from google import genai
import pandas as pd

GEMINI_API_KEY = os.getenv("GEMINI_MUSIC_AGENT_API_KEY")
GEMINI_MODEL = "gemini-3.1-pro-preview"

PROMPT_TEMPLATE = """You are a precise academic citation extractor.

Below is the full text of a research paper. Extract EVERY citation that appears in the body text.

For each citation, produce a JSON object with exactly these three fields:
- "ref_id": the citation marker exactly as it appears in the text (e.g. "[1]", "[Smith2023]", "(Author, 2020)").
- "context_sentence": the complete sentence from the body text that contains this citation marker. This is the claim the cited paper is supposed to support.
- "reference": the full bibliography entry for that cited paper, exactly as written in the reference section.

Return a single JSON array of these objects, ordered by first appearance.
If the same ref_id appears multiple times, include a separate entry for each occurrence.
Output valid JSON only — no markdown, no explanation.

Paper text:
{paper_text}"""


def extract_pdf_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


def parse_response(text: str) -> list:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return []


def extract_citations(client, paper_text: str, retries: int = 3) -> list[dict]:
    # Gemini context limit: truncate at ~500k chars to be safe
    prompt = PROMPT_TEMPLATE.format(paper_text=paper_text[:500_000])

    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            result = parse_response(response.text)
            if result:
                return result
        except Exception as e:
            wait = 2 ** attempt
            print(f"  Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

    print("  All retries failed.")
    return []


def main():
    parser = argparse.ArgumentParser(description="Extract citations from a paper PDF using Gemini.")
    parser.add_argument("paper_pdf", help="Path to the input PDF.")
    parser.add_argument("--output", default="citations.csv", help="Output CSV path (default: citations.csv).")
    args = parser.parse_args()

    if not os.path.isfile(args.paper_pdf):
        print(f"Error: File not found: {args.paper_pdf}", file=sys.stderr)
        sys.exit(1)

    if not GEMINI_API_KEY:
        print("Error: GEMINI_MUSIC_AGENT_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting text from {args.paper_pdf} ...")
    paper_text = extract_pdf_text(args.paper_pdf)
    print(f"Text extracted: {len(paper_text):,} characters")

    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"Calling Gemini ({GEMINI_MODEL}) ...")
    citations = extract_citations(client, paper_text)

    if not citations:
        print("Warning: No citations found.")

    rows = [
        {
            "ref_id": str(item.get("ref_id", "")).strip(),
            "context_sentence": str(item.get("context_sentence", "")).strip(),
            "reference": str(item.get("reference", "")).strip(),
        }
        for item in citations
    ]

    df = pd.DataFrame(rows, columns=["ref_id", "context_sentence", "reference"])
    df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"Saved {len(df)} citation(s) to {args.output}")


if __name__ == "__main__":
    main()
