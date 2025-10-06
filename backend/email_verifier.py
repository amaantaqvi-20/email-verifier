from __future__ import annotations
import os
import re
import csv
import time
import random
import socket
import argparse
import sqlite3
import threading
import concurrent.futures
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
import dns.resolver
from email_validator import validate_email, EmailNotValidError
from tqdm import tqdm
import tldextract
import hashlib
import json

# License Management
LICENSE_FILE = "config.json"

def get_hash(email: str) -> str:
    """Generate license key hash based on email"""
    return hashlib.sha256(email.encode()).hexdigest()[:12]

def init_license():
    """Initialize blank license config if not found"""
    if not os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "w") as f:
            json.dump({"email": "", "key": "", "premium": False, "activated_on": None}, f, indent=2)

def get_license_info():
    try:
        with open(LICENSE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"email": "", "key": "", "premium": False, "activated_on": None}

def is_premium():
    info = get_license_info()
    return info.get("premium", False)

def activate_license(email: str, key: str) -> bool:
    """Activate license if key matches generated hash"""
    correct = get_hash(email)
    if key.strip() == correct:
        with open(LICENSE_FILE, "w") as f:
            json.dump({
                "email": email,
                "key": key,
                "premium": True,
                "activated_on": time.strftime("%Y-%m-%d"),
            }, f, indent=2)
        return True
    return False

# Configuration
EMAIL_RE = re.compile(r'[^\s,;<>]+@[^\s,;<>]+')  # Simplified regex
DEFAULT_DB = "email_cache_v3.db"
DEFAULT_WORKERS = 60
MX_TIMEOUT = 3
SMTP_TIMEOUT = 6
SMTP_PORT = 25

DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "yopmail.com", "guerrillamail.com",
    "trashmail.com", "tempmail.com", "tempmail.net", "getnada.com", "dispostable.com"
}

DB_LOCK = threading.Lock()

# Cache Handling
def init_cache(db_path=DEFAULT_DB):
    with DB_LOCK:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                email TEXT PRIMARY KEY,
                verdict TEXT,
                reason TEXT,
                active_status TEXT,
                mx_domain TEXT,
                last_checked INTEGER
            )
        """)
        conn.commit()
        conn.close()

def read_cache(db_path, email):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT verdict, reason, active_status, mx_domain, last_checked FROM cache WHERE email=?", (email,))
        row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None

def write_cache(db_path, email, verdict, reason, active_status, mx_domain):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?, strftime('%s','now'))",
            (email, verdict, reason, active_status, mx_domain),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

# Utilities
def extract_emails_from_text(text: str) -> List[str]:
    emails = list({m.group(0).strip().lower() for m in EMAIL_RE.finditer(text)})
    # Debug: Log extracted emails
    with open("debug_emails.log", "a") as f:
        f.write(f"Extracted emails: {emails}\n")
    return emails

def domain_from_email(email: str) -> str:
    try:
        return email.split("@", 1)[1].lower()
    except IndexError:
        return ""

def is_disposable(domain: str) -> bool:
    base = tldextract.extract(domain).registered_domain or domain
    return base in DISPOSABLE_DOMAINS

# DNS / MX Resolution
def resolve_mx(domain: str):
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=MX_TIMEOUT)
        return domain, [str(r.exchange).rstrip(".") for r in answers]
    except Exception:
        return domain, []

def resolve_mx_bulk(domains: Set[str], max_workers=30):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(domains) or 1)) as ex:
        futures = {ex.submit(resolve_mx, d): d for d in domains}
        for fut in concurrent.futures.as_completed(futures):
            d, mx = fut.result()
            results[d] = mx
    return results

# SMTP Validation
def smtp_probe(mx_host, email):
    try:
        conn = socket.create_connection((mx_host, SMTP_PORT), timeout=SMTP_TIMEOUT)
        f = conn.makefile("rwb", buffering=0)

        def send(cmd): f.write((cmd + "\r\n").encode()); f.flush()
        def recv(): return f.readline().decode(errors="ignore").strip()

        recv()
        send("EHLO example.com"); recv()
        send("MAIL FROM:<verify@example.com>"); recv()
        send(f"RCPT TO:<{email}>")
        resp = recv()
        conn.close()

        if resp.startswith("250"):
            return "active"
        elif resp.startswith("550") or resp.startswith("551"):
            return "inactive"
        else:
            return "unknown"
    except Exception:
        return "unknown"

# Classify Email
def classify_email(email, mx_cache, db_path, premium):
    email = email.lower().strip()
    cached = read_cache(db_path, email)
    if cached:
        verdict, reason, active, domain, _ = cached
        return {"email": email, "verdict": verdict, "reason": reason, "active_status": active}

    try:
        validate_email(email)
    except EmailNotValidError:
        write_cache(db_path, email, "bad", "invalid", "inactive", None)
        return {"email": email, "verdict": "bad", "reason": "invalid", "active_status": "inactive"}

    domain = domain_from_email(email)
    if not domain:
        write_cache(db_path, email, "bad", "invalid_domain", "inactive", None)
        return {"email": email, "verdict": "bad", "reason": "invalid_domain", "active_status": "inactive"}

    if is_disposable(domain):
        write_cache(db_path, email, "risky", "disposable", "unknown", domain)
        return {"email": email, "verdict": "risky", "reason": "disposable", "active_status": "unknown"}

    mx_hosts = mx_cache.get(domain, [])
    if not mx_hosts:
        write_cache(db_path, email, "bad", "no-mx", "inactive", domain)
        return {"email": email, "verdict": "bad", "reason": "no-mx", "active_status": "inactive"}

    if premium:
        status = smtp_probe(mx_hosts[0], email)
        if status == "active":
            write_cache(db_path, email, "good", "smtp-active", "active", domain)
            return {"email": email, "verdict": "good", "reason": "smtp-active", "active_status": "active"}
        elif status == "inactive":
            write_cache(db_path, email, "bad", "smtp-reject", "inactive", domain)
            return {"email": email, "verdict": "bad", "reason": "smtp-reject", "active_status": "inactive"}
        else:
            write_cache(db_path, email, "risky", "smtp-unknown", "unknown", domain)
            return {"email": email, "verdict": "risky", "reason": "smtp-unknown", "active_status": "unknown"}

    write_cache(db_path, email, "good", "syntax+mx", "unknown", domain)
    return {"email": email, "verdict": "good", "reason": "syntax+mx", "active_status": "unknown"}

# Main Verification Runner
def run_verification(input_path, output_path, workers, premium, db_path, job_id=None, progress_store=None):
    init_cache(db_path)
    os.makedirs(output_path, exist_ok=True)
    emails = []

    # Debug: Log input path
    with open("debug_emails.log", "a") as f:
        f.write(f"Processing input: {input_path}\n")

    if os.path.isdir(input_path):
        for fn in os.listdir(input_path):
            if fn.endswith((".txt", ".csv")):
                with open(os.path.join(input_path, fn), "r", encoding="utf-8", errors="ignore") as f:
                    emails += extract_emails_from_text(f.read())
    elif os.path.isfile(input_path):
        with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
            emails += extract_emails_from_text(f.read())
    else:
        with open("debug_emails.log", "a") as f:
            f.write(f"Input not found: {input_path}\n")
        if progress_store and job_id:
            progress_store[job_id]["status"] = "error"
            progress_store[job_id]["error"] = "Input file or directory not found"
        return

    emails = list(set(emails))
    with open("debug_emails.log", "a") as f:
        f.write(f"Found emails: {emails}\n")
    if progress_store and job_id:
        progress_store[job_id]["total"] = len(emails)

    domains = {domain_from_email(e) for e in emails if domain_from_email(e)}
    with open("debug_emails.log", "a") as f:
        f.write(f"Resolving MX for domains: {domains}\n")
    mx_cache = resolve_mx_bulk(domains, max_workers=workers)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(classify_email, e, mx_cache, db_path, premium) for e in emails]
        for fut in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Verifying"):
            results.append(fut.result())
            if progress_store and job_id:
                progress_store[job_id]["done"] += 1

    out = os.path.join(output_path, "verified_results.csv")
    if os.path.exists(out):
        out = os.path.join(output_path, "verified_results_new.csv")

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "verdict", "reason", "active_status"])
        writer.writeheader()
        writer.writerows(results)

    with open("debug_emails.log", "a") as f:
        f.write(f"Results saved to: {out}\n")

# Main Entry for CLI / API
def main(args):
    """Entry point for CLI and API"""
    run_verification(
        input_path=args.input,
        output_path=args.output,
        workers=args.workers,
        premium=args.premium,
        db_path="email_cache_v3.db",
        job_id=getattr(args, 'job_id', None),
        progress_store=getattr(args, 'progress_store', None),
    )

if __name__ == "__main__":
    print("===========================================")
    print("     Email Verifier v3.8 - Free & Premium  ")
    print("===========================================")

    init_license()
    info = get_license_info()

    if not info.get("premium"):
        print("\n🔒 Free Mode Active (DNS + MX only).")
        choice = input("Do you want to activate Premium Mode? (y/n): ").strip().lower()
        if choice == "y":
            email = input("Enter your email: ").strip()
            print(f"🔑 Your license key (for testing): {get_hash(email)}")
            key = input("Enter your license key: ").strip()
            if activate_license(email, key):
                print("✅ Premium license activated successfully!")
            else:
                print("❌ Invalid license key. Continuing in Free Mode.")
        else:
            print("Continuing in Free Mode...")

    premium = is_premium()
    print(f"\n🚀 Running in {'PREMIUM' if premium else 'FREE'} MODE\n")

    parser = argparse.ArgumentParser(description="Email Verifier CLI")
    parser.add_argument("--input", "-i", required=True, help="Input file or folder")
    parser.add_argument("--output", "-o", required=True, help="Output folder")
    parser.add_argument("--workers", "-w", type=int, default=50, help="Concurrent threads")
    parser.add_argument("--premium", action="store_true", help="Enable deeper SMTP checks (optional override)")
    args = parser.parse_args()

    if args.premium:
        premium = True

    run_verification(args.input, args.output, args.workers, premium, "email_cache_v3.db")