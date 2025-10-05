# worker.py
import csv
from pathlib import Path
from verify_lib import find_emails_in_text, classify_email

def process_file(path: str, job_id: str):
    p = Path(path)
    text = ''
    if p.suffix.lower() in ['.txt', '.csv']:
        text = p.read_text(encoding='utf-8', errors='ignore')
    else:
        try:
            # placeholder: for now try to read text; we'll add PDF/DOCX parsing next
            text = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            text = ''
    emails = find_emails_in_text(text)
    rows = []
    for e in emails:
        r = classify_email(e)
        rows.append({'email': e, 'verdict': r['verdict'], 'reasons': ';'.join(r['reasons'])})
    out_dir = p.parent
    out_file = out_dir / f"{p.stem}.emails.csv"
    with open(out_file, 'w', newline='', encoding='utf-8') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=['email','verdict','reasons'])
        writer.writeheader()
        writer.writerows(rows)
    print('Wrote', out_file)
