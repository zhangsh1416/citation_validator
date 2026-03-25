"""
extract_text.py

Extract full text from a PDF using PyMuPDF and save to a .txt file for inspection.

Usage:
    python extract_text.py <paper.pdf> [--output paper_text.txt]
"""

import argparse
import os
import sys
import fitz  # PyMuPDF


def extract_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages.append(f"=== Page {i + 1} ===\n{text}")
    doc.close()
    return "\n\n".join(pages)


def main():
    parser = argparse.ArgumentParser(description="Extract text from PDF for inspection.")
    parser.add_argument("paper_pdf", help="Path to the input PDF.")
    parser.add_argument("--output", default=None,
                        help="Output .txt path (default: <pdf_name>_text.txt).")
    args = parser.parse_args()

    if not os.path.isfile(args.paper_pdf):
        print(f"Error: File not found: {args.paper_pdf}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.splitext(args.paper_pdf)[0] + "_text.txt"

    print(f"Extracting text from {args.paper_pdf} ...")
    text = extract_text(args.paper_pdf)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    char_count = len(text)
    page_count = text.count("=== Page ")
    print(f"Done: {page_count} pages, {char_count:,} characters → {output_path}")


if __name__ == "__main__":
    main()
