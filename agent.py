#!/usr/bin/env python3
"""
agent.py - Groq-powered PDF parser generator
Generates a custom parser for the target bank PDF → DataFrame, then tests it against the expected CSV.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pdfplumber
from dotenv import load_dotenv
import requests
import importlib.util

# ==== LOAD .env ====
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    print("❌ Missing GROQ_API_KEY in environment. Please set it in .env")
    sys.exit(1)

# ==== CONFIG ====
BANK_CONFIG = {
    "icici": {
        "sample_pdf": "data/icici/icici_sample.pdf",
        "expected_csv": "data/icici/icici_expected.csv",
        "parser_path": "custom_parsers/icici_parser.py",
        "max_attempts": 3,
    },
}

# ==== UTILS ====

def load_expected_headers(csv_path: str) -> List[str]:
    df = pd.read_csv(csv_path, nrows=0)
    return df.columns.tolist()

def extract_table_preview(pdf_path: str, samples_per_section: int = 2) -> List[List[str]]:
    """Extracts table samples from first, middle, and last pages."""
    preview_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        candidate_pages = {0, total_pages // 2, total_pages - 1}
        for page_idx in sorted(candidate_pages):
            if page_idx < 0 or page_idx >= total_pages:
                continue
            tables = pdf.pages[page_idx].extract_tables()
            if not tables:
                continue
            for table in tables:
                for row in table:
                    clean_row = [cell if cell else "" for cell in row]
                    if any(cell.strip() for cell in clean_row):
                        preview_rows.append(clean_row)
                        if len(preview_rows) >= samples_per_section * len(candidate_pages):
                            return preview_rows
    return preview_rows

def strip_code_fences(text: str) -> str:
    # Try to capture the largest Python code block
    code_blocks = re.findall(r"``````", text, flags=re.DOTALL | re.IGNORECASE)
    if code_blocks:
        return code_blocks[0].strip()
    return text.strip()

def run_tests() -> (bool, str):
    """Run pytest quietly and capture output"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        capture_output=True,
        text=True
    )
    passed = result.returncode == 0
    return passed, result.stdout + "\n" + result.stderr

# ==== GROQ API WRAPPER ====

def call_groq(model: str, system_prompt: str, user_prompt: str) -> str:
    """
    Calls Groq API using API key from .env.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error: {resp.status_code} {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]

# ==== PROMPT BUILDERS ====

def build_initial_prompt(bank: str, headers: List[str], preview: List[List[str]]) -> (str, str):
    system_prompt = f"""
You are a coding agent.
Generate a single Python module: custom_parsers/{bank}_parser.py
It must define:

    def parse(pdf_path: str) -> pandas.DataFrame

RULES:
1. Use only pdfplumber, pandas, typing.
2. Preserve every cell value exactly as in the PDF — including spaces, punctuation, and case.
3. Return all values as strings.
4. Use exactly these column names (in this order): {headers}
5. DO NOT transform numbers or dates — no formatting, trimming, or retyping.
6. Parse all pages, removing repeated headers and ignoring any footers.
7. This is the grading check (must pass exactly):

    assert df.astype(str).equals(expected_df.astype(str))

8. Output ONLY valid Python code. No markdown, no triple backticks, no explanations.
The first line MUST be a valid Python import statement.
"""
    user_prompt = json.dumps({
        "bank": bank,
        "expected_headers": headers,
        "table_preview": preview
    }, indent=2)
    return system_prompt.strip(), user_prompt

def build_repair_prompt(bank: str, code: str, failure_output: str, mismatches: Dict) -> (str, str):
    mismatch_preview = [
        f"{'EXPECTED':<60} | {'ACTUAL':<60}",
        "-" * 125
    ]
    expected_rows = mismatches.get("expected", [])
    actual_rows = mismatches.get("actual", [])
    for exp, act in zip(expected_rows, actual_rows):
        mismatch_preview.append(f"{str(exp):<60} | {str(act):<60}")
    mismatch_table = "\n".join(mismatch_preview) if expected_rows else "(No mismatch data)"

    system_prompt = f"""
You previously wrote a parser for {bank}.
The parser failed:

    assert df.astype(str).equals(expected_df.astype(str))

Modify ONLY the parser code to make the test pass.
Do not change the tests.
Preserve all rules from the initial prompt.
Output ONLY valid Python code, no markdown or backticks.
"""
    user_prompt = json.dumps({
        "current_code": code,
        "failure_trace": failure_output,
        "mismatch_rows": mismatch_table
    }, indent=2)

    return system_prompt.strip(), user_prompt

# ==== MAIN AGENT FLOW ====

def main():
    parser = argparse.ArgumentParser(description="Groq-powered PDF parser generator")
    parser.add_argument("--target", required=True, help="Bank target name (e.g., icici)")
    args = parser.parse_args()

    if args.target not in BANK_CONFIG:
        print(f"Unknown target '{args.target}'")
        sys.exit(1)

    cfg = BANK_CONFIG[args.target]
    sample_pdf = Path(cfg["sample_pdf"])
    expected_csv = Path(cfg["expected_csv"])
    parser_path = Path(cfg["parser_path"])
    max_attempts = cfg.get("max_attempts", 3)

    print(f"[1] Loading config for '{args.target}'...")
    headers = load_expected_headers(expected_csv)
    preview = extract_table_preview(sample_pdf)
    if not preview:
        print("No preview table found — PDF may be scanned. OCR not implemented in this skeleton.")
    print(f"[2] Extracted table preview: {preview[:3]} ...")

    sys_prompt, user_prompt = build_initial_prompt(args.target, headers, preview)

    for attempt in range(1, max_attempts + 1):
        print(f"[Attempt {attempt}] Requesting parser code from Groq...")
        code = call_groq(model=GROQ_MODEL, system_prompt=sys_prompt, user_prompt=user_prompt)
        code = strip_code_fences(code)

        # Syntax check before saving
        try:
            compile(code, parser_path.name, 'exec')
        except SyntaxError as e:
            print(f"❌ Groq returned invalid Python syntax: {e}")
            if attempt == max_attempts:
                Path("artifacts").mkdir(exist_ok=True)
                (Path("artifacts") / parser_path.name).write_text(code, encoding="utf-8")
                sys.exit(1)
            else:
                sys_prompt = f"The code you wrote did not compile: {e}. Fix the syntax and return only valid Python code."
                user_prompt = code
                continue

        parser_path.parent.mkdir(parents=True, exist_ok=True)
        parser_path.write_text(code, encoding="utf-8")

        # Ensure test file exists
        test_file = Path(f"tests/test_{args.target}.py")
        if not test_file.exists():
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_code = f"""
import pandas as pd
from custom_parsers.{args.target}_parser import parse

def test_parser():
    df = parse(r"{sample_pdf}")
    expected = pd.read_csv(r"{expected_csv}")
    assert df.astype(str).equals(expected.astype(str))
"""
            test_file.write_text(test_code.strip(), encoding="utf-8")

        print("[Testing parser...]")
        passed, output = run_tests()
        if passed:
            print("✅ Tests passed. Parser generated successfully.")
            sys.exit(0)
        else:
            print("❌ Test failed.")

            # Extract mismatches
            try:
                spec = importlib.util.spec_from_file_location(f"custom_parsers.{args.target}_parser", str(parser_path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                parse_func = getattr(mod, "parse")
                df_actual = parse_func(str(sample_pdf)).astype(str)
                df_expected = pd.read_csv(str(expected_csv)).astype(str)
                mismatched = [(er, ar) for er, ar in zip(df_expected.values.tolist(), df_actual.values.tolist()) if er != ar]
                mismatches = {
                    "expected": [list(map(str, t[0])) for t in mismatched[:5]],
                    "actual": [list(map(str, t[1])) for t in mismatched[:5]],
                }
            except Exception as e:
                print(f"⚠️ Warning: failed to extract mismatches: {e}")
                mismatches = {"expected": [], "actual": []}

            if attempt == max_attempts:
                print("[Max attempts reached] Trying regex-fallback...")
                with pdfplumber.open(sample_pdf) as pdf:
                    full_text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
                sys_prompt_fallback = f"""
All previous attempts failed.
Write a parser using pdfplumber text and regex to extract rows matching headers: {headers}
Preserve all values exactly.
Must pass: df.astype(str).equals(expected_df.astype(str))
Output ONLY valid Python code.
"""
                usr_prompt_fallback = json.dumps({
                    "bank": args.target,
                    "full_page_text_excerpt": full_text[:5000]
                }, indent=2)
                code = call_groq(GROQ_MODEL, sys_prompt_fallback, usr_prompt_fallback)
                code = strip_code_fences(code)
                try:
                    compile(code, parser_path.name, 'exec')
                except SyntaxError as e:
                    print(f"❌ Fallback code invalid: {e}")
                    sys.exit(1)
                parser_path.write_text(code, encoding="utf-8")
                passed, _ = run_tests()
                if passed:
                    print("✅ Passed after regex fallback!")
                    sys.exit(0)
                else:
                    print("❌ Failed after regex fallback.")
                    sys.exit(1)

            sys_prompt, user_prompt = build_repair_prompt(args.target, code, output, mismatches)


if __name__ == "__main__":
    main()