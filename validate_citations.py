"""
validate_citations.py

Validate each citation by:
  - Extracting a relevant excerpt from the main paper via PyMuPDF (too large to upload)
  - Uploading the cited paper as a file (PDF or image)
  - Asking Gemini whether the cited paper supports the claim

Results are written directly back to the citations CSV as two new columns:
  validated  : True / False / NaN (if not found or error)
  rationale  : explanation string

Usage:
    python validate_citations.py <citations.csv> <paper.pdf> \
        [--papers-dir papers/] [--threshold 60]
"""

import argparse
import glob
import json
import mimetypes
import os
import re
import sys
import time

import fitz  # PyMuPDF
from google import genai
from google.genai import types
import pandas as pd
from thefuzz import fuzz, process

GEMINI_API_KEY = os.getenv("GEMINI_MUSIC_AGENT_API_KEY")
GEMINI_MODEL = "gemini-3.1-pro-preview"
CONTEXT_WINDOW = 2000

SUPPORTED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

MIME_MAP = {
    ".pdf":  "application/pdf",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

PROMPT_TEMPLATE = """You are an academic fact-checker.

Below is a passage from the main paper, followed by {paper_label}.

=== PASSAGE FROM MAIN PAPER ===
{main_excerpt}
=== END OF PASSAGE ===

Claim (ref_id: {ref_id}):
"{context_sentence}"

Cited as: "{reference}"

Read {paper_label} and determine whether they support, contradict, or provide insufficient evidence for the claim above.

Answer in valid JSON only (no markdown, no explanation):
{{
  "validation_result": "Supported" or "Contradicted" or "Insufficient",
  "rationale": "1-3 sentences citing specific evidence from the cited paper(s)"
}}"""


def extract_pdf_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n\n".join(pages)


def get_main_excerpt(main_text: str, context_sentence: str) -> str:
    idx = main_text.find(context_sentence[:80])
    if idx == -1:
        return main_text[:CONTEXT_WINDOW * 2]
    start = max(0, idx - CONTEXT_WINDOW)
    end = min(len(main_text), idx + len(context_sentence) + CONTEXT_WINDOW)
    return main_text[start:end]


def upload_file(client, file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    mime_type = MIME_MAP.get(ext, "application/octet-stream")
    with open(file_path, "rb") as f:
        uploaded = client.files.upload(
            file=f,
            config=types.UploadFileConfig(
                mime_type=mime_type,
                display_name=os.path.basename(file_path),
            ),
        )
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state.name != "ACTIVE":
        raise RuntimeError(f"Upload failed with state: {uploaded.state.name}")
    return uploaded


def parse_response(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}


def validate_citation(
    client,
    main_text: str,
    cited_files: list,
    ref_id: str,
    context_sentence: str,
    reference: str,
    retries: int = 3,
) -> dict:
    main_excerpt = get_main_excerpt(main_text, context_sentence)
    n = len(cited_files)
    paper_label = "the cited paper" if n == 1 else f"the {n} cited papers"
    prompt = PROMPT_TEMPLATE.format(
        paper_label=paper_label,
        main_excerpt=main_excerpt,
        ref_id=ref_id,
        context_sentence=context_sentence,
        reference=reference,
    )
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=cited_files + [prompt],
            )
            result = parse_response(response.text)
            if result:
                is_supported = str(result.get("validation_result", "")).strip() == "Supported"
                return {
                    "validated": is_supported,
                    "rationale": str(result.get("rationale", "")).strip(),
                }
        except Exception as e:
            wait = 2 ** attempt
            print(f"  Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    return {"validated": None, "rationale": "All retries failed."}


def count_citations(ref_id: str) -> int:
    return ref_id.count(";") + 1


def find_papers(reference: str, candidates: list[str], threshold: int, n: int) -> list[tuple[str, int]]:
    """Return up to n best matches above threshold."""
    if not candidates:
        return []
    results = process.extract(reference, candidates, scorer=fuzz.token_set_ratio, limit=n)
    return [(match, score) for match, score, *_ in results if score >= threshold]


def main():
    parser = argparse.ArgumentParser(description="Validate citations and update CSV in place.")
    parser.add_argument("citations_csv", help="CSV produced by extract_citations.py.")
    parser.add_argument("paper_pdf", help="Path to the main paper PDF.")
    parser.add_argument("--papers-dir", default="papers", help="Directory containing cited files (default: papers/).")
    parser.add_argument("--threshold", type=int, default=60, help="Fuzzy match score threshold (default: 60).")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between API calls (default: 2.0).")
    args = parser.parse_args()

    for path, label in [(args.citations_csv, "Citations CSV"), (args.paper_pdf, "Paper PDF")]:
        if not os.path.isfile(path):
            print(f"Error: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)
    if not os.path.isdir(args.papers_dir):
        print(f"Error: Papers directory not found: {args.papers_dir}", file=sys.stderr)
        sys.exit(1)
    if not GEMINI_API_KEY:
        print("Error: GEMINI_MUSIC_AGENT_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    # Collect all supported files (PDF + images)
    all_files = []
    for ext in SUPPORTED_EXTS:
        all_files.extend(glob.glob(os.path.join(args.papers_dir, f"*{ext}")))
        all_files.extend(glob.glob(os.path.join(args.papers_dir, f"*{ext.upper()}")))
    name_to_path = {os.path.splitext(os.path.basename(p))[0]: p for p in all_files}
    candidates = list(name_to_path.keys())
    print(f"Found {len(candidates)} file(s) in {args.papers_dir}/")

    df = pd.read_csv(args.citations_csv)
    required_cols = {"ref_id", "context_sentence", "reference"}
    if not required_cols.issubset(df.columns):
        print(f"Error: CSV is missing columns: {required_cols - set(df.columns)}", file=sys.stderr)
        sys.exit(1)

    # Initialize new columns if not present
    if "validated" not in df.columns:
        df["validated"] = None
    if "rationale" not in df.columns:
        df["rationale"] = None

    print("Extracting text from main paper ...")
    main_text = extract_pdf_text(args.paper_pdf)
    print(f"Main paper: {len(main_text):,} characters")

    client = genai.Client(api_key=GEMINI_API_KEY)
    file_cache: dict[str, object] = {}
    total = len(df)

    try:
        for idx, row in df.iterrows():
            # Skip already validated rows
            if pd.notna(row.get("validated")) and str(row.get("rationale", "")).strip():
                print(f"[{idx + 1}/{total}] Skipping (already validated): {row['ref_id']}")
                continue

            ref_id = str(row["ref_id"])
            context_sentence = str(row["context_sentence"])
            reference = str(row["reference"])
            print(f"\n[{idx + 1}/{total}] ref_id={ref_id}")

            n = count_citations(ref_id)
            matched = find_papers(reference, candidates, args.threshold, n)

            if not matched:
                print(f"  No matching file found (threshold={args.threshold}).")
                df.at[idx, "validated"] = None
                df.at[idx, "rationale"] = f"No matching file found in {args.papers_dir}/"
                continue

            cited_files = []
            for matched_name, score in matched:
                file_path = name_to_path[matched_name]
                ext = os.path.splitext(file_path)[1].lower()
                print(f"  Matched: {matched_name}{ext} (score={score})")
                if file_path not in file_cache:
                    file_cache[file_path] = upload_file(client, file_path)
                    print(f"  Uploaded: {file_cache[file_path].name}")
                cited_files.append(file_cache[file_path])

            result = validate_citation(client, main_text, cited_files, ref_id, context_sentence, reference)
            print(f"  validated={result['validated']}")

            df.at[idx, "validated"] = result["validated"]
            df.at[idx, "rationale"] = result["rationale"]

            time.sleep(args.delay)

    finally:
        for path, f in file_cache.items():
            client.files.delete(name=f.name)
            print(f"Deleted: {f.name}")

    df.to_csv(args.citations_csv, index=False, encoding="utf-8")
    print(f"\nUpdated {args.citations_csv}")

    n_true  = df["validated"].sum()
    n_false = (df["validated"] == False).sum()
    n_none  = df["validated"].isna().sum()
    print(f"\n--- Summary ---")
    print(f"  Validated (True):  {int(n_true)}")
    print(f"  Not validated (False): {int(n_false)}")
    print(f"  Not found / Error: {int(n_none)}")


if __name__ == "__main__":
    main()
