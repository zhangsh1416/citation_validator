# Citation Validator

A two-step pipeline that extracts all citations from an academic paper and validates each one against the cited source using Gemini LLM.

一个两步流程工具：从学术论文中提取所有引用，并使用 Gemini LLM 逐条验证引用是否真实支持对应论断。

---

## Overview / 概述

**Step 1 — Extract / 提取** (`extract_citations.py`): Reads a paper PDF, uses Gemini to identify every in-text citation and its corresponding bibliography entry, and outputs a CSV.

读取论文 PDF，用 Gemini 识别正文中的每一条引用及其对应的参考文献条目，输出 CSV 文件。

**Step 2 — Validate / 验证** (`validate_citations.py`): For each citation, fuzzy-matches the reference to a local file in `papers/`, uploads it to Gemini, and asks whether the cited paper actually supports the claim. Results are written back to the same CSV.

对每条引用，将参考文献与 `papers/` 目录中的本地文件进行模糊匹配，上传至 Gemini，询问被引论文是否真正支持该论断。结果直接写回原始 CSV。

---

## Requirements / 环境要求

Install dependencies / 安装依赖：

```bash
pip install google-genai pymupdf thefuzz python-Levenshtein pandas
```

Set your Gemini API key / 设置 Gemini API Key：

```bash
export GEMINI_MUSIC_AGENT_API_KEY=your_api_key_here
```

---

## Usage / 使用方法

### Step 1: Extract citations / 提取引用

```bash
python extract_citations.py paper.pdf --output citations.csv
```

Outputs `citations.csv` with columns / 输出 `citations.csv`，包含以下列：

| Column | Description | 说明 |
|---|---|---|
| `ref_id` | Citation marker as it appears in text | 正文中的引用标记，如 `(Smith, 2023)` |
| `context_sentence` | The sentence containing the citation — the claim to verify | 包含引用的原文句子，即待验证的论断 |
| `reference` | Full bibliography entry from the reference section | 参考文献列表中的完整条目 |

### (Optional) Inspect extracted PDF text / 可选：检查提取的文本

```bash
python extract_text.py paper.pdf
```

Saves `<paper>_text.txt` for manual inspection before running extraction.

将提取的文本保存为 `<paper>_text.txt`，供运行提取前手动检查。

### Step 2: Validate citations / 验证引用

Place the cited papers (PDF or image) in the `papers/` directory. Filenames should contain the paper title for fuzzy matching to work.

将被引论文（PDF 或图片）放入 `papers/` 目录，文件名需包含论文标题以便模糊匹配。

```bash
python validate_citations.py citations.csv paper.pdf --papers-dir papers/
```

Two columns are added to `citations.csv` in place / 结果直接追加到 `citations.csv`：

| Column | Description | 说明 |
|---|---|---|
| `validated` | `True` if the cited paper supports the claim | 被引论文支持该论断为 `True`，否则为 `False` |
| `rationale` | 1–3 sentence explanation citing specific evidence | 1–3 句引用具体证据的解释 |

### Options / 参数

```
--papers-dir   Directory containing cited PDFs/images (default: papers/)
               被引文献目录（默认：papers/）
--threshold    Fuzzy match score threshold 0–100 (default: 60)
               模糊匹配阈值 0–100（默认：60）
--delay        Seconds between API calls (default: 2.0)
               API 调用间隔秒数（默认：2.0）
```

---

## Multi-citation handling / 多引用处理

When a single sentence cites multiple papers (e.g. `(Li, 2020; Dang, 2026)`), the validator automatically detects the citation count, finds all matching files, uploads them together, and asks Gemini to evaluate the claim against all cited papers collectively.

当一句话同时引用多篇论文时（如 `(Li, 2020; Dang, 2026)`），验证器自动检测引用数量，找到所有匹配文件，同时上传并让 Gemini 基于所有被引论文共同判断论断是否成立。

---

## Supported file formats / 支持的文件格式

The `papers/` directory accepts / `papers/` 目录支持：`.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`

---

## Notes / 注意事项

- The main paper is processed via text extraction (PyMuPDF) since large PDFs exceed the Gemini upload limit. Cited papers are uploaded directly as files.
  主论文通过 PyMuPDF 提取文本（因为大 PDF 超出 Gemini 上传限制），被引论文则直接上传文件。
- Already-validated rows are skipped on re-runs, so interrupted runs can be safely resumed.
  重新运行时已验证的行会被跳过，中断后可安全续跑。
- Model: `gemini-3.1-pro-preview`
