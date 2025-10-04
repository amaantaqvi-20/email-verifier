"""
Email Verifier with Live Progress (TXT + CSV)
---------------------------------------------

- Free: Syntax + MX + Disposable + Lightweight SMTP
- Premium (--premium): Full SMTP retries, deeper checks
- Progress updates per email via shared PROGRESS dict
"""

import argparse
import os
import re
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

import pandas as pd
import tldextract
import dns.resolver
from smtplib import SMTP

# --------------------------- Config ---------------------------
EMAIL_REGEX = re.compile(r"([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
DISPOSABLE_DOMAINS = {
    'mailinator.com','10minutemail.com','yopmail.com',
    'guerrillamail.com','trashmail.com','tempmail.com','getnada.com'
}
DNS_TIMEOUT = 5.0
SMTP_TIMEOUT = 5.0
MAX_WORKERS = 10

# --------------------------- Utils ---------------------------

def find_emails_in_text(text: str) -> List[str]:
    return list({m.group(1).strip() for m in EMAIL_REGEX.finditer(text)})

def is_syntax_valid(email: str) -> bool:
    return bool(EMAIL_REGEX.fullmatch(email))

def domain_from_email(email: str) -> str:
    return email.split('@', 1)[1].lower()

def is_disposable_domain(domain: str) -> bool:
    base = tldextract.extract(domain).top_domain_under_public_suffix
    return base in DISPOSABLE_DOMAINS

def has_mx_record(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=DNS_TIMEOUT)
        return len(answers) > 0
    except Exception:
        return False

# --------------------------- SMTP check ---------------------------

def smtp_check(email: str, domain: str, premium: bool) -> str:
    """Lightweight SMTP check (free) or deeper (premium)."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)
        mx_host = str(answers[0].exchange).rstrip(".")
        server = SMTP(timeout=SMTP_TIMEOUT if not premium else 8)
        server.connect(mx_host)
        server.helo()
        server.mail("no-reply@example.com")
        code, _ = server.rcpt(email)
        server.quit()
        if 200 <= code < 300:
            return "active"
        elif 500 <= code < 600:
            return "inactive"
        else:
            return "unknown"
    except Exception:
        return "unknown"

# --------------------------- Classification ---------------------------

def classify_email(email: str, premium: bool, mx_cache: dict) -> Dict[str, str]:
    """Return dict with verdict + active_status."""
    reasons = []
    email_lower = email.strip().lower()

    if not is_syntax_valid(email_lower):
        return {"email": email_lower, "verdict": "bad", "active_status": "inactive", "reasons": ["invalid-syntax"]}

    domain = domain_from_email(email_lower)

    if is_disposable_domain(domain):
        reasons.append("disposable-domain")

    if domain in mx_cache:
        mx_exists = mx_cache[domain]
    else:
        mx_exists = has_mx_record(domain)
        mx_cache[domain] = mx_exists

    if not mx_exists:
        reasons.append("no-mx-record")
        return {"email": email_lower, "verdict": "bad", "active_status": "inactive", "reasons": reasons}

    smtp_status = smtp_check(email_lower, domain, premium)
    if smtp_status == "active":
        return {"email": email_lower, "verdict": "good", "active_status": "active", "reasons": ["smtp-accept"]}
    elif smtp_status == "inactive":
        return {"email": email_lower, "verdict": "bad", "active_status": "inactive", "reasons": ["smtp-reject"]}
    else:
        if "disposable-domain" in reasons:
            return {"email": email_lower, "verdict": "risky", "active_status": "inactive", "reasons": reasons}
        return {"email": email_lower, "verdict": "risky", "active_status": "unknown", "reasons": reasons or ["smtp-unknown"]}

# --------------------------- File Handlers ---------------------------

def process_txt(path: str, output_path: str, premium: bool, mx_cache: dict, args=None):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    emails = find_emails_in_text(text)

    if args and hasattr(args, "job_id") and hasattr(args, "progress_store"):
        args.progress_store[args.job_id]["total"] += len(emails)

    rows = []
    for e in emails:
        verdict = classify_email(e, premium, mx_cache)
        rows.append({
            "filename": os.path.basename(path),
            "email": e,
            "verdict": verdict["verdict"],
            "active_status": verdict["active_status"],
            "reasons": ";".join(verdict["reasons"]),
        })
        if args and hasattr(args, "job_id") and hasattr(args, "progress_store"):
            args.progress_store[args.job_id]["done"] += 1

    out_file = os.path.join(output_path, os.path.basename(path) + ".emails.csv")
    with open(out_file, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=["filename", "email", "verdict", "active_status", "reasons"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote: {out_file}")

def process_csv(path: str, output_path: str, premium: bool, mx_cache: dict, args=None):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    if args and hasattr(args, "job_id") and hasattr(args, "progress_store"):
        args.progress_store[args.job_id]["total"] += len(df)

    rows = []
    for _, row in df.iterrows():
        found_emails = []
        for col in row:
            emails = find_emails_in_text(str(col))
            found_emails.extend(emails)
        for e in found_emails:
            verdict = classify_email(e, premium, mx_cache)
            rows.append({
                "filename": os.path.basename(path),
                "email": e,
                "verdict": verdict["verdict"],
                "active_status": verdict["active_status"],
                "reasons": ";".join(verdict["reasons"]),
            })
        if args and hasattr(args, "job_id") and hasattr(args, "progress_store"):
            args.progress_store[args.job_id]["done"] += 1

    out_file = os.path.join(output_path, os.path.basename(path) + ".emails.csv")
    with open(out_file, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=["filename", "email", "verdict", "active_status", "reasons"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote: {out_file}")

# --------------------------- Orchestration ---------------------------

def process_file(path: str, output_path: str, premium: bool, mx_cache: dict, args=None):
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext in (".txt", ".text"):
        process_txt(path, output_path, premium, mx_cache, args=args)
    elif ext == ".csv":
        process_csv(path, output_path, premium, mx_cache, args=args)
    else:
        print(f"Skipping unsupported file type: {path}")

def main(args):
    input_path = args.input
    output_path = args.output
    concurrency = args.workers or MAX_WORKERS
    premium = args.premium

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    mx_cache = {}

    files = []
    if os.path.isdir(input_path):
        for fname in os.listdir(input_path):
            full = os.path.join(input_path, fname)
            if os.path.isfile(full):
                files.append(full)
    elif os.path.isfile(input_path):
        files = [input_path]
    else:
        print("Input path not found")
        return

    print(f"Found {len(files)} files to process")

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(process_file, f, output_path, premium, mx_cache, args=args) for f in files]
        for fut in as_completed(futures):
            fut.result()

    print("All done.")

# --------------------------- CLI ---------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Email Verifier with Live Progress")
    parser.add_argument("--input", "-i", required=True, help="Input folder or file path")
    parser.add_argument("--output", "-o", required=True, help="Output folder to write results")
    parser.add_argument("--workers", "-w", type=int, required=False, help="Concurrency (default 10)")
    parser.add_argument("--premium", action="store_true", help="Enable deeper SMTP checks for premium clients")

    args = parser.parse_args()
    main(args)
