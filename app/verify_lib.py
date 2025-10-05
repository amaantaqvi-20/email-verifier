# verify_lib.py
import re
from typing import List, Dict, Optional
import tldextract
import dns.resolver

EMAIL_REGEX = re.compile(r"([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
DISPOSABLE_DOMAINS = set(['mailinator.com','10minutemail.com','yopmail.com','trashmail.com'])

DNS_TIMEOUT = 5.0

def find_emails_in_text(text: str) -> List[str]:
    return list({m.group(1).strip() for m in EMAIL_REGEX.finditer(text)})

def is_syntax_valid(email: str) -> bool:
    return bool(EMAIL_REGEX.fullmatch(email))

def domain_from_email(email: str) -> str:
    return email.split('@', 1)[1].lower()

def is_disposable_domain(domain: str) -> bool:
    base = tldextract.extract(domain).registered_domain
    return base in DISPOSABLE_DOMAINS

def has_mx_record(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, 'MX', lifetime=DNS_TIMEOUT)
        return True
    except Exception:
        return False

def classify_email(email: str) -> Dict[str, object]:
    e = email.strip().lower()
    if not is_syntax_valid(e):
        return {'email': e, 'verdict': 'bad', 'reasons': ['invalid-syntax']}
    domain = domain_from_email(e)
    reasons = []
    if is_disposable_domain(domain):
        reasons.append('disposable-domain')
    if not has_mx_record(domain):
        reasons.append('no-mx-record')
    if 'no-mx-record' in reasons:
        return {'email': e, 'verdict': 'bad', 'reasons': reasons}
    if 'disposable-domain' in reasons:
        return {'email': e, 'verdict': 'risky', 'reasons': reasons}
    return {'email': e, 'verdict': 'risky', 'reasons': ['inconclusive']}
