"""
general_leads.py — MAX-YIELD Email Collector v4
Aggressive deep scraping · 150+ dorks · 15 threads · 25 results/query
"""

import re
import os
import csv
import time
import json
import io
import zipfile
import random
import threading
import socket
import logging
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from urllib.parse import quote_plus, parse_qs, urlparse, urljoin

import requests
from bs4 import BeautifulSoup
# DuckDuckGo search compatibility: try multiple import styles across versions
ddg = None
try:
    from duckduckgo_search import ddg as _ddg
    def ddg(query, max_results=25):
        try:
            return _ddg(query, max_results=max_results)
        except Exception:
            return []
except Exception:
    try:
        from duckduckgo_search import DDGS
        def ddg(query, max_results=25):
            try:
                return list(DDGS().text(query, max_results=max_results))
            except Exception:
                return []
    except Exception:
        try:
            from ddgs import DDGS
            def ddg(query, max_results=25):
                try:
                    return list(DDGS().text(query, max_results=max_results))
                except Exception:
                    return []
        except Exception:
            ddg = None
import mysql.connector

try:
    from googlesearch import search as _google_search
    def google_search(query, max_results=25):
        try:
            return list(_google_search(query, num_results=max_results))
        except Exception:
            return []
except ImportError:
    google_search = None

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import dns.resolver
    DNS_RESOLVER = dns.resolver.Resolver()
except ImportError:
    DNS_RESOLVER = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================
# CONFIG — tuned for maximum yield
# ============================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", os.getenv("DB_PASS", "")),
    "database": os.getenv("DB_NAME", "github_leads"),
}

GITHUB_PAT = os.getenv("GITHUB_PAT", "").strip()
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "general_leads.py/1.0",
}
if GITHUB_PAT:
    GITHUB_HEADERS["Authorization"] = f"token {GITHUB_PAT}"

CRUNCHBASE_API_KEY = os.getenv("CRUNCHBASE_API_KEY", "").strip()
CRUNCHBASE_QUERIES = [
    'site:crunchbase.com/organization "email"',
    'site:crunchbase.com/organization "contact"',
    'site:crunchbase.com/person "email"',
    'site:crunchbase.com/person "contact"',
]

CATEGORY_KEYS = (
    "gaming",
    "marketing",
    "business",
    "freelancer",
    "online-income",
    "affiliate-marketers",
    "side-hustle",
    "blogger",
    "job-seeker",
    "all",
)
CATEGORY_TERMS = {
    "gaming": [
        "game developer", "esports", "streamer", "game designer",
        "indie developer", "unity developer", "unreal developer",
        "game producer", "gaming journalist", "community manager",
        "pro gamer", "twitch streamer", "youtube gamer",
        "mobile game developer", "vr game developer", "game artist",
        "level designer", "qa tester", "game marketing",
        "esports manager", "game studio",
    ],
    "marketing": [
        "email marketing", "digital marketing", "growth marketing",
        "campaign manager", "marketing manager", "content marketer",
        "performance marketer", "social media marketer",
        "affiliate marketer", "brand manager", "marketing automation",
        "demand generation", "CRM manager", "SEO specialist",
        "paid media manager", "inbound marketer", "ecommerce marketer",
        "product marketer", "conversion rate optimizer",
        "content strategist", "marketing operations",
    ],
    "business": [
        "CEO", "founder", "entrepreneur", "co-founder",
        "business owner", "managing director", "executive director",
        "venture capitalist", "angel investor", "operations director",
        "startup founder", "business development", "strategy lead",
        "head of growth", "chairman", "president",
        "general manager", "sales director", "company founder",
        "corporate attorney", "business strategist",
        "finance director", "investor",
    ],
    "job-seeker": [
        "job seeker", "looking for job", "open to work", "fresh graduate",
        "entry level", "seeking opportunity", "career change",
        "job applicant", "candidate",
    ],
}
CATEGORY_TEMPLATES = {
    "gaming": [
        '"{term}" "@gmail.com" "contact"',
        '"{term}" "@gmail.com" "team"',
        '"{term}" "@gmail.com" "email"',
        '"{term}" "@gmail.com" "streamer"',
        '"{term}" "@gmail.com" "esports"',
        '"{term}" "@gmail.com" "dev"',
        '"{term}" "@gmail.com" "game"',
        '"{term}" "@gmail.com" "studio"',
        '"{term}" "@gmail.com" "designer"',
        '"{term}" "@gmail.com" "producer"',
    ],
    "marketing": [
        '"{term}" "@gmail.com" "specialist"',
        '"{term}" "@gmail.com" "expert"',
        '"{term}" "@gmail.com" "manager"',
        '"{term}" "@gmail.com" "lead"',
        '"{term}" "@gmail.com" "agency"',
        '"{term}" "@gmail.com" "strategy"',
        '"{term}" "@gmail.com" "campaign"',
        '"{term}" "@gmail.com" "growth"',
        '"{term}" "@gmail.com" "digital"',
        '"{term}" "@gmail.com" "automation"',
    ],
    "business": [
        '"{term}" "@gmail.com" "company"',
        '"{term}" "@gmail.com" "startup"',
        '"{term}" "@gmail.com" "founder"',
        '"{term}" "@gmail.com" "entrepreneur"',
        '"{term}" "@gmail.com" "director"',
        '"{term}" "@gmail.com" "office"',
        '"{term}" "@gmail.com" "partner"',
        '"{term}" "@gmail.com" "CEO"',
        '"{term}" "@gmail.com" "VP"',
        '"{term}" "@gmail.com" "executive"',
    ],
    "job-seeker": [
        '"{term}" "@gmail.com" "resume"',
        '"{term}" "@gmail.com" "cv"',
        '"{term}" "@gmail.com" "experience"',
        '"{term}" "@gmail.com" "portfolio"',
        '"{term}" "@gmail.com" "skills"',
        '"{term}" "@gmail.com" "available"',
        '"{term}" "@gmail.com" "looking"',
        '"{term}" "@gmail.com" "apply"',
        '"{term}" "@gmail.com" "career"',
    ],
}
CRUNCHBASE_CATEGORY_KEYWORDS = {
    "gaming": ["esports", "gaming", "game developer", "streamer", "unity", "indie game"],
    "marketing": ["email marketing", "digital marketing", "growth marketing", "marketing automation", "campaign"],
    "business": ["CEO", "founder", "startup", "entrepreneur", "investor"],
}

MX_CACHE = {}

THREADS = 15
RESULTS_PER_QUERY = 20
SAVE_BATCH = 1000
BACKUP_BATCH = 1000
REQUEST_TIMEOUT = 20
SEARCH_REQUEST_TIMEOUT = 30
CRUNCHBASE_TIMEOUT = 10
DELAY_MIN = 5
DELAY_MAX = 10
SEARCH_DELAY_MIN = 5
SEARCH_DELAY_MAX = 10
MAX_RETRIES = 5
SEARCH_RETRY_ATTEMPTS = 3
DDG_RETRIES = 4
DDG_RETRY_DELAY = 3
DDG_SEARCH_TIMEOUT = 30
COLLECTION_TIMEOUT = 600  # 10 min timeout per collection phase

SEARCH_ENGINE_FAILURES = {}
SEARCH_ENGINE_FAILURE_LIMIT = 2
EMAIL_DEBUG_ENABLED = True
EMAIL_DEBUG_COUNT = 0


def run_with_timeout(func, args=(), kwargs=None, timeout_sec=COLLECTION_TIMEOUT):
    """Run func with a hard timeout. Returns result or raises TimeoutError."""
    if kwargs is None:
        kwargs = {}
    result = []
    exc_info = []

    def wrapper():
        try:
            result.append(func(*args, **kwargs))
        except Exception as e:
            exc_info.append(e)

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        raise TimeoutError(f"'{func.__name__}' timed out after {timeout_sec}s")
    if exc_info:
        raise exc_info[0]
    return result[0] if result else None


# ============================================================
# USER-AGENTS
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
]
BING_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# ============================================================
# EMAIL FILTERS
# ============================================================
DUMMY_PREFIXES = {
    "test@", "example@", "demo@", "admin@", "info@", "support@",
    "noreply@", "no-reply@", "donotreply@", "mail@", "contact@",
    "webmaster@", "postmaster@", "sales@", "hello@", "hi@",
    "newsletter@", "abuse@", "alert@", "bounce@", "careers@",
    "complaints@", "customerservice@", "enquiries@", "feedback@",
    "fraud@", "help@", "inquiries@", "investor@", "investors@",
    "it@", "job@", "jobs@", "marketing@", "media@", "office@",
    "order@", "orders@", "press@", "pr@", "recruitment@",
    "registration@", "security@", "service@", "services@",
    "shop@", "spam@", "subscribe@", "sysadmin@", "team@",
    "web@", "website@", "inquiry@", "general@", "hr@",
    "customercare@", "returns@", "review@", "root@", "safety@",
    "signup@", "enquiry@", "trust@", "corp@", "information@",
    "public@", "reservations@", "report@", "request@",
}

TEMP_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "temp-mail.org", "sharklasers.com",
    "yopmail.com", "trashmail.com", "10minutemail.com", "throwaway.email",
    "tempmail.com", "mail.tm", "dispostable.com", "mailnator.com",
    "getnada.com", "emailfake.com", "tempmail.net", "maildrop.cc",
    "inboxbear.com", "fakeinbox.com", "tempemail.net", "spambox.us",
    "mailexpire.com", "spamgourmet.com", "mytemp.email", "tempemail.co",
    "guerrillamail.org", "mailcatch.com", "tempinbox.com", "spamspot.com",
    "maileater.com", "emailias.com", "sneakemail.com", "pookmail.com",
    "dodgeit.com", "mytrashmail.com", "trashymail.com", "tyldd.com",
    "wegwerfmail.de", "spam.la", "emailtempm.com", "mailmetrash.com",
    "despam.it", "spambob.com", "haltospam.com", "kasmail.com",
    "filzmail.com", "boun.cr", "spam4.me", "trashmailer.com",
    "10mail.org", "tempinbox.co", "maillist.in", "mt2009.com",
    "trash2009.com", "uggsrock.com", "miniurl.de",
    "discard.email", "trashymail.com", "sneakemail.com", "pookmail.com",
}

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "protonmail.com", "proton.me", "icloud.com", "aol.com", "mail.com",
    "zoho.com", "yandex.com", "riseup.net", "gmx.com", "gmx.net",
}

GENERIC_EMAIL_LOCAL_PARTS = {
    "info", "support", "contact", "admin", "sales", "hello", "team", "hr",
    "careers", "career", "jobs", "job", "office", "service", "services",
    "help", "marketing", "press", "media", "newsletter", "bounce", "abuse",
    "alert", "complaints", "customerservice", "enquiries", "feedback",
    "security", "webmaster", "postmaster", "noreply", "no-reply", "donotreply",
    "sysadmin", "root", "safety", "signup", "enquiry", "trust", "corp",
    "public", "reservations", "report", "request", "general", "inquiry",
    "inquiries", "customercare", "returns", "review", "spam", "subscribe",
    "developer", "student", "freelancer", "gamer", "resume", "portfolio",
}


def is_fake_email(email):
    lower = email.lower().strip()
    for p in DUMMY_PREFIXES:
        if lower.startswith(p):
            return True
    domain = lower.split("@")[1] if "@" in lower else ""
    return domain in TEMP_DOMAINS


def looks_like_personal_email(email, debug=False):
    lower = email.lower().strip()
    if "@" not in lower or lower.count("@") != 1:
        return False, "missing_or_multiple_at_symbols"
    local, domain = lower.split("@", 1)
    if domain not in PERSONAL_EMAIL_DOMAINS:
        if debug:
            logging.info("[email-debug] rejected %s reason=domain_not_in_personal_domains domain=%s", email, domain)
        return False, "domain_not_in_personal_domains"
    if len(local) < 2 or len(local) > 32:
        return False, "local_part_length"
    if local.startswith((".", "-")) or local.endswith((".", "-")):
        return False, "local_part_boundary"
    if re.fullmatch(r"[0-9]+", local):
        return False, "numeric_local_part"
    if any(part in GENERIC_EMAIL_LOCAL_PARTS for part in re.split(r"[._-]+", local)):
        return False, "generic_local_part"
    if local in GENERIC_EMAIL_LOCAL_PARTS:
        return False, "generic_local_part"
    return True, "ok"


def is_valid_email(email, debug=False):
    if is_fake_email(email):
        return False, "temp_or_fake_domain"
    lower = email.lower().strip()
    if "@" not in lower or lower.count("@") != 1:
        return False, "missing_or_multiple_at_symbols"
    local, domain = lower.split("@")
    if len(local) < 1 or len(local) > 64 or len(domain) < 3 or len(domain) > 255:
        return False, "local_or_domain_length"
    if domain.count(".") < 1:
        return False, "missing_dot_in_domain"
    tld = domain.split(".")[-1]
    if len(tld) < 2:
        return False, "invalid_tld"
    suspicious_exts = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                       ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
                       ".tar", ".gz", ".exe", ".dll", ".bin")
    if domain.endswith(suspicious_exts):
        return False, "suspicious_file_extension"
    return looks_like_personal_email(email, debug=debug)


def merge_categories(existing, new_category):
    if not new_category:
        return existing
    if not existing:
        return new_category
    existing_parts = [p.strip() for p in existing.split(",") if p.strip()]
    if new_category not in existing_parts:
        existing_parts.append(new_category)
    return ",".join(existing_parts)


def verify_email_mx(email):
    try:
        domain = email.split("@", 1)[1].lower()
    except IndexError:
        return False
    if domain in MX_CACHE:
        return MX_CACHE[domain]
    valid = False
    if DNS_RESOLVER:
        try:
            answers = DNS_RESOLVER.resolve(domain, "MX", lifetime=10)
            valid = bool(answers)
        except Exception:
            valid = False
    else:
        try:
            resp = requests.get(
                "https://dns.google/resolve",
                params={"name": domain, "type": "MX"},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            valid = bool(payload.get("Answer"))
        except Exception:
            valid = False
    MX_CACHE[domain] = valid
    return valid


# ============================================================
# COUNTRY DETECTION
# ============================================================
TLD_COUNTRY = {
    "bd": "Bangladesh", "in": "India", "pk": "Pakistan",
    "us": "USA", "uk": "UK", "ca": "Canada",
    "au": "Australia", "de": "Germany", "fr": "France",
    "jp": "Japan", "br": "Brazil", "mx": "Mexico",
    "it": "Italy", "es": "Spain", "ru": "Russia",
    "cn": "China", "kr": "South Korea", "sa": "Saudi Arabia",
    "ae": "UAE", "eg": "Egypt", "ng": "Nigeria",
    "za": "South Africa", "ar": "Argentina", "co": "Colombia",
    "ch": "Switzerland", "se": "Sweden", "no": "Norway",
    "dk": "Denmark", "fi": "Finland", "nl": "Netherlands",
    "be": "Belgium", "at": "Austria", "pl": "Poland",
    "cz": "Czech Republic", "tr": "Turkey", "gr": "Greece",
    "pt": "Portugal", "ro": "Romania", "hu": "Hungary",
    "il": "Israel", "my": "Malaysia", "sg": "Singapore",
    "ph": "Philippines", "th": "Thailand", "vn": "Vietnam",
    "id": "Indonesia", "hk": "Hong Kong", "tw": "Taiwan",
    "nz": "New Zealand", "ke": "Kenya", "gh": "Ghana",
    "ma": "Morocco", "tn": "Tunisia", "ie": "Ireland",
    "cl": "Chile", "pe": "Peru", "ua": "Ukraine",
    "kz": "Kazakhstan", "qa": "Qatar", "kw": "Kuwait",
}

PROVIDER_MAP = {
    "gmail.com": "Global (Gmail)", "yahoo.com": "Global (Yahoo)",
    "hotmail.com": "Global (Hotmail)", "outlook.com": "Global (Outlook)",
    "live.com": "Global (Live)", "msn.com": "Global (MSN)",
    "aol.com": "Global (AOL)", "protonmail.com": "Global (Proton)",
    "icloud.com": "Global (iCloud)", "mail.com": "Global (Mail.com)",
    "yandex.com": "Global (Yandex)", "zoho.com": "Global (Zoho)",
    "gmx.com": "Global (GMX)", "fastmail.com": "Global (FastMail)",
}


def detect_country(email):
    domain = email.split("@")[1].lower()
    parts = domain.split(".")
    if len(parts) >= 2:
        tld = parts[-1]
        if tld in TLD_COUNTRY:
            return TLD_COUNTRY[tld]
    for key, val in PROVIDER_MAP.items():
        if key in domain:
            return val
    for cctld in ("co.uk", "co.in", "co.jp", "com.au", "co.nz", "co.za",
                  "com.br", "com.mx", "com.ar", "co.kr", "com.sg", "com.hk"):
        if domain.endswith(cctld):
            t = cctld.split(".")[-1]
            if t in TLD_COUNTRY:
                return TLD_COUNTRY[t]
    return "Other"

KNOWN_EMAILS = set()
KNOWN_EMAILS_LOCK = threading.Lock()


def load_existing_emails():
    emails = set()
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT email FROM github_leads")
        for row in cursor:
            if row and row[0]:
                emails.add(row[0].lower().strip())
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()
    return emails


def merge_category_labels(existing, new_category):
    if not new_category:
        return existing
    if not existing:
        return new_category
    existing_parts = [p.strip() for p in existing.split(",") if p.strip()]
    if new_category not in existing_parts:
        existing_parts.append(new_category)
    return ", ".join(existing_parts)


# ============================================================
# DATABASE
# ============================================================
def init_database():
    conn = mysql.connector.connect(
        host=DB_CONFIG["host"], port=DB_CONFIG["port"],
        user=DB_CONFIG["user"], password=DB_CONFIG["password"],
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` CHARACTER SET utf8mb4")
    cursor.execute(f"USE `{DB_CONFIG['database']}`")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS github_leads (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255),
            name VARCHAR(255),
            email VARCHAR(255) NOT NULL UNIQUE,
            location VARCHAR(255),
            bio TEXT,
            country VARCHAR(100),
            source VARCHAR(255),
            category VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            sent_at TIMESTAMP NULL DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()

    # Ensure older schemas are upgraded with missing columns.
    for column, definition in [
        ('status', "VARCHAR(20) NOT NULL DEFAULT 'Pending'"),
        ('sent_at', "TIMESTAMP NULL DEFAULT NULL"),
        ('created_at', "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ('country', "VARCHAR(100)"),
        ('source', "VARCHAR(255)"),
        ('category', "VARCHAR(100)"),
    ]:
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                (DB_CONFIG['database'], 'github_leads', column),
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(f"ALTER TABLE github_leads ADD COLUMN {column} {definition}")
                conn.commit()
        except Exception:
            pass

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
            "AND COLUMN_NAME='email' AND NON_UNIQUE=0",
            (DB_CONFIG['database'], 'github_leads'),
        )
        unique_email_index = cursor.fetchone()[0]
        if not unique_email_index:
            try:
                cursor.execute("ALTER TABLE github_leads ADD UNIQUE INDEX idx_github_leads_email (email)")
                conn.commit()
            except mysql.connector.Error as exc:
                if exc.errno == 1062:
                    cursor.execute(
                        "DELETE t1 FROM github_leads t1 "
                        "JOIN github_leads t2 ON t1.email = t2.email "
                        "WHERE t1.id > t2.id"
                    )
                    conn.commit()
                    cursor.execute("ALTER TABLE github_leads ADD UNIQUE INDEX idx_github_leads_email (email)")
                    conn.commit()
                else:
                    raise
    except Exception:
        pass
    finally:
        cursor.close()
        conn.close()


def save_emails(email_pairs, source="DuckDuckGo"):
    if not email_pairs:
        return 0, 0, []
    inserted = 0
    duplicates = 0
    unique_emails = {}
    for item in email_pairs:
        if isinstance(item, tuple):
            email, category = item
        else:
            email = item
            category = None
        email = email.lower().strip()
        if not is_valid_email(email):
            continue
        if email in unique_emails:
            unique_emails[email] = merge_category_labels(unique_emails[email], category)
            duplicates += 1
            continue
        unique_emails[email] = category

    if not unique_emails:
        return 0, duplicates, []

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    inserted_emails = []
    for email, category in unique_emails.items():
        with KNOWN_EMAILS_LOCK:
            if email in KNOWN_EMAILS:
                duplicates += 1
                continue
        if not verify_email_mx(email):
            continue
        country = detect_country(email)
        username = email.split("@")[0][:50]
        try:
            cursor.execute(
                "INSERT INTO github_leads "
                "(username, email, location, country, source, category, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')",
                (username, email, "Web Scraping", country, source, category),
            )
            conn.commit()
            if cursor.rowcount > 0:
                inserted += 1
                inserted_emails.append(email)
                with KNOWN_EMAILS_LOCK:
                    KNOWN_EMAILS.add(email)
        except mysql.connector.Error as exc:
            if exc.errno == 1062:
                duplicates += 1
            else:
                logging.debug("save_emails failed for %s: %s", email, exc)
    cursor.close()
    conn.close()
    return inserted, duplicates, inserted_emails


def save_single_email(
    email,
    source="DuckDuckGo",
    username=None,
    name=None,
    location=None,
    bio=None,
    category=None,
):
    email = email.lower().strip()
    if not is_valid_email(email):
        return False
    with KNOWN_EMAILS_LOCK:
        if email in KNOWN_EMAILS:
            return False
    if not verify_email_mx(email):
        return False
    country = detect_country(email)
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO github_leads "
            "(username, name, email, location, bio, country, source, category, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending')",
            (
                username or email.split("@", 1)[0],
                name,
                email,
                location,
                bio,
                country,
                source,
                category,
            ),
        )
        conn.commit()
        if cursor.rowcount > 0:
            with KNOWN_EMAILS_LOCK:
                KNOWN_EMAILS.add(email)
            return True
        return False
    except mysql.connector.Error as exc:
        if exc.errno == 1062:
            return False
        logging.debug("save_single_email failed for %s: %s", email, exc)
        return False
    except Exception as exc:
        logging.debug("save_single_email unexpected error for %s: %s", email, exc)
        return False
    finally:
        cursor.close()
        conn.close()


def github_search_users(query, max_pages=2, per_page=50):
    users = []
    session = requests.Session()
    session.headers.update(GITHUB_HEADERS)
    for page in range(1, max_pages + 1):
        params = {
            "q": query,
            "per_page": per_page,
            "page": page,
        }
        try:
            resp = session.get("https://api.github.com/search/users", params=params, timeout=20)
            if resp.status_code != 200:
                logging.warning("GitHub search failed (%s): %s", resp.status_code, resp.text[:200])
                break
            payload = resp.json()
            items = payload.get("items", [])
            if not items:
                break
            users.extend(items)
            if len(items) < per_page:
                break
            time.sleep(1.0)
        except Exception as exc:
            logging.warning("GitHub search exception: %s", exc)
            break
    return users


def github_fetch_profile(username):
    session = requests.Session()
    session.headers.update(GITHUB_HEADERS)
    try:
        resp = session.get(f"https://api.github.com/users/{username}", timeout=20)
        if resp.status_code != 200:
            logging.debug("GitHub profile fetch failed for %s: %s", username, resp.status_code)
            return None
        return resp.json()
    except Exception:
        return None


def collect_github_public_emails(locations=None, max_pages=2):
    if locations is None:
        locations = ["USA", "UK", "Canada", "Australia", "Germany", "France", "India"]
    saved = 0
    for location in locations:
        query = f"location:{location} type:user"
        logging.info("GitHub search for public users in %s", location)
        users = github_search_users(query, max_pages=max_pages)
        for user in users:
            username = user.get("login")
            if not username:
                continue
            profile = github_fetch_profile(username)
            time.sleep(1.0)
            if not profile:
                continue
            email = profile.get("email")
            if not email or not is_valid_email(email):
                continue
            if save_single_email(
                email,
                source="GitHub",
                username=username,
                name=profile.get("name"),
                location=profile.get("location"),
                bio=profile.get("bio"),
            ):
                saved += 1
                logging.info("Saved GitHub lead: %s", email)
    logging.info("GitHub collection complete — saved %d new leads.", saved)
    return saved


def search_crunchbase_pages(keywords=None, max_results=20):
    if keywords is None:
        keywords = ["startup", "founder", "technology", "software"]
    urls = []
    try:
        for keyword in keywords:
            query = f'site:crunchbase.com "{keyword}" "email"'
            results = search_duckduckgo(query, max_results=max_results)
            if not results:
                results = _ddg_search(query, max_results=max_results)
            for item in results:
                if isinstance(item, dict):
                    url = item.get("href") or item.get("url") or item.get("link") or ""
                else:
                    url = str(item).strip()
                if url and "crunchbase.com" in url:
                    urls.append(url)
            if not results:
                logging.warning("Crunchbase query returned no results: %s", query)
            time.sleep(1.0)
    except Exception as exc:
        logging.warning("Crunchbase search failed: %s", exc)
    return list(dict.fromkeys(urls))


def collect_crunchbase_public_emails(keywords=None, category="all"):
    if CRUNCHBASE_API_KEY:
        logging.info("Crunchbase API key detected, using public page search instead of API.")
    if category and category in CRUNCHBASE_CATEGORY_KEYWORDS:
        keywords = CRUNCHBASE_CATEGORY_KEYWORDS[category]
    saved = 0
    urls = search_crunchbase_pages(keywords)
    for url in urls:
        try:
            resp = requests.get(url, headers=_headers(), timeout=CRUNCHBASE_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            emails = _emails_from_soup(soup)
            for email in emails:
                if save_single_email(
                    email,
                    source="Crunchbase",
                    category=category.title() if category and category != "all" else None,
                ):
                    saved += 1
                    logging.info("Saved Crunchbase email: %s", email)
            time.sleep(1.5)
        except Exception as exc:
            logging.debug("Crunchbase scrape failed for %s: %s", url, exc)
    logging.info("Crunchbase collection complete — saved %d new leads.", saved)
    return saved


def collect_search_engine_leads(category="all", engine="all"):
    logging.debug("collect_search_engine_leads() STARTED with category='%s' engine='%s'", category, engine)
    queries = build_queries(category)
    logging.info("collect_search_engine_leads: %d queries to process", len(queries))
    if not queries:
        logging.warning("collect_search_engine_leads: query list is EMPTY — nothing to do")
        return 0
    logging.debug("First 3 queries: %s", [(q[0][:80], q[1]) for q in queries[:3]])

    saved = 0
    for i, (query_text, q_category) in enumerate(queries, 1):
        if i % 25 == 0 or i == 1:
            logging.info("collect_search_engine_leads: query %d/%d [saved=%d]", i, len(queries), saved)
        query_start = time.time()
        try:
            urls = search_all_engines(query_text, max_results=RESULTS_PER_QUERY, engine=engine)
        except Exception as exc:
            elapsed = time.time() - query_start
            logging.debug("search_all_engines failed for query %d after %.2fs: %s", i, elapsed, exc)
            urls = []
        elapsed = time.time() - query_start
        logging.info("collect_search_engine_leads: query %d/%d took %.2fs and returned %d URLs", i, len(queries), elapsed, len(urls))
        if not urls:
            logging.debug("Query %d returned 0 URLs: %s", i, query_text[:80])
        for url in urls:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            try:
                for email in _emails_from_url(url):
                    if save_single_email(email, source="SearchEngine", category=q_category):
                        saved += 1
            except Exception as exc:
                logging.debug("_emails_from_url/save failed for %s: %s", url[:80], exc)
        if saved and saved % BACKUP_BATCH == 0:
            _backup_emails()
    logging.info("Search engine collection complete — saved %d new leads.", saved)
    return saved


def collect_public_files(category="all"):
    file_queries = [
        '"email" "@gmail.com" "contact" "CEO"',
        '"email" "@yahoo.com" "manager"',
        '"resume" "@gmail.com" "experience"',
        '"portfolio" "@gmail.com" "designer"',
    ]
    saved = 0
    for query_text in file_queries:
        urls = search_all_engines(query_text, max_results=RESULTS_PER_QUERY)
        for url in urls:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            for email in _emails_from_url(url):
                if save_single_email(email, source="PublicFile", category=category.title() if category != "all" else None):
                    saved += 1
        if saved and saved % BACKUP_BATCH == 0:
            _backup_emails()
    logging.info("Public file collection complete — saved %d new leads.", saved)
    return saved


def collect_social_media_leads(category="all"):
    social_queries = [
        'site:linkedin.com/in "email"',
        'site:github.com "email"',
        'site:twitter.com "email" OR "@gmail.com"',
        'site:facebook.com "email"',
        'site:instagram.com "email"',
        'site:reddit.com "email"',
        'site:medium.com "email"',
        'site:quora.com "email"',
        'site:pinterest.com "email"',
    ]
    if category and category != "all":
        social_queries = [f'{q} "{category}"' for q in social_queries]
    saved = 0
    for query_text in social_queries:
        urls = search_all_engines(query_text, max_results=RESULTS_PER_QUERY)
        for url in urls:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            for email in _emails_from_url(url):
                if save_single_email(email, source="SocialMedia", category=category.title() if category != "all" else None):
                    saved += 1
        if saved and saved % BACKUP_BATCH == 0:
            _backup_emails()
    logging.info("Social media collection complete — saved %d new leads.", saved)
    return saved


def collect_professional_platform_leads(category="all"):
    professional_queries = [
        'site:crunchbase.com "email"',
        'site:angel.co "email"',
        'site:behance.net "email"',
        'site:dribbble.com "email"',
        'site:about.me "email"',
        'site:keybase.io "email"',
        'site:stackoverflow.com "email"',
    ]
    if category and category != "all":
        professional_queries = [f'{q} "{category}"' for q in professional_queries]
    saved = 0
    for query_text in professional_queries:
        urls = search_all_engines(query_text, max_results=RESULTS_PER_QUERY)
        for url in urls:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            for email in _emails_from_url(url):
                if save_single_email(email, source="Professional", category=category.title() if category != "all" else None):
                    saved += 1
        if saved and saved % BACKUP_BATCH == 0:
            _backup_emails()
    logging.info("Professional platform collection complete — saved %d new leads.", saved)
    return saved


def _backup_emails():
    if not os.path.exists("emails.txt"):
        return
    try:
        backup_name = f"emails_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open("emails.txt", encoding="utf-8") as fin, open(backup_name, "w", encoding="utf-8") as fout:
            fout.write(fin.read())
        logging.info("Backup created: %s", backup_name)
    except Exception as exc:
        logging.debug("Backup failed: %s", exc)


# ============================================================
# SCRAPER — aggressive deep scraping (up to 12 pages)
# ============================================================
_visited_urls = set()
_url_lock = threading.Lock()

DEEP_SLUGS = [
    "contact", "contact-us", "about", "about-us", "team", "our-team",
    "staff", "directory", "people", "members", "contributors",
    "support", "help", "write-for-us", "get-in-touch",
    "meet-the-team", "leadership", "management", "board",
    "faculty", "department", "admissions",
    "careers", "jobs", "join-us", "work-with-us",
    "profile", "portfolio", "profiles",
    "investors", "press", "media", "newsroom",
    "partners", "affiliates", "sponsors",
    "community", "forum", "blog", "authors",
    "find-us", "locations", "offices",
    "executive", "governance",
    "alumni", "graduates",
    "doctor", "physician", "providers",
    "faculty-staff", "administration",
]


def _headers(user_agent_list=None):
    if user_agent_list is None:
        user_agent_list = USER_AGENTS
    return {
        "User-Agent": random.choice(user_agent_list),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
    }


def _backoff_delay(attempt, base_delay=SEARCH_DELAY_MIN):
    delay = min(30.0, base_delay * (2 ** (attempt - 1)))
    return delay + random.uniform(0.5, 2.0)


def _soup(url):
    resp = _get_url(url, timeout=REQUEST_TIMEOUT, log_prefix="[scrape]")
    if resp is None:
        raise requests.RequestException(f"Failed to fetch {url}")
    return BeautifulSoup(resp.text, "lxml")


def _extract_emails_from_text(text, source_name="text", debug=False):
    # Debug logging for scraper email extraction and rejection reasons.
    found = set()
    if not text:
        return found
    if debug:
        snippet = text[:1500].replace("\n", " ").replace("\r", " ")
        logging.info("[email-debug] source=%s snippet=%s", source_name, snippet)
    rejected_count = 0
    for m in re.finditer(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        e = m.group().lower().strip()
        if debug:
            logging.info("[email-debug] regex candidate=%s from %s", e, source_name)
        if len(e) < 100:
            valid, reason = is_valid_email(e, debug=debug)
            if valid:
                found.add(e)
            elif debug:
                rejected_count += 1
                logging.info("[email-debug] rejected candidate=%s from %s reason=%s", e, source_name, reason)
    if debug:
        logging.info("[email-debug] summary source=%s accepted=%d rejected=%d", source_name, len(found), rejected_count)
    return found


def _collect_email_candidates(soup, debug=False):
    candidates = []
    visible_text = soup.get_text(separator="\n", strip=True)
    if visible_text:
        candidates.append(("visible_text", visible_text))
    html_source = str(soup)
    if html_source:
        candidates.append(("html_source", html_source))

    for tag in soup.find_all(True):
        for attr_name in ("href", "src", "content", "title", "alt", "placeholder", "data-email", "value", "aria-label"):
            value = tag.get(attr_name)
            if isinstance(value, str) and value.strip():
                candidates.append((f"{tag.name}:{attr_name}", value.strip()))
        if tag.name == "a":
            href = tag.get("href", "")
            if isinstance(href, str) and href.startswith("mailto:"):
                candidates.append(("mailto", href[7:].split("?", 1)[0].strip()))
    return candidates


def _emails_from_soup(soup, debug=None):
    found = set()
    if debug is None:
        debug = EMAIL_DEBUG_ENABLED
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    candidates = _collect_email_candidates(soup, debug=debug)
    for source_name, text in candidates:
        found.update(_extract_emails_from_text(text, source_name=source_name, debug=debug))
    return found


def _get_url(url, allow_redirects=True, timeout=None, log_prefix=None, user_agent_list=None):
    if timeout is None:
        timeout = REQUEST_TIMEOUT
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=timeout, headers=_headers(user_agent_list), allow_redirects=allow_redirects)
            resp.raise_for_status()
            if log_prefix:
                logging.debug("%s request succeeded: %s status=%s length=%s attempt=%d", log_prefix, url, resp.status_code, len(resp.text or ""), attempt)
            return resp
        except requests.Timeout as exc:
            if log_prefix:
                logging.warning("%s request timed out: %s attempt=%d/%d", log_prefix, url, attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(_backoff_delay(attempt, base_delay=SEARCH_DELAY_MIN))
        except Exception as exc:
            if log_prefix:
                logging.debug("%s request failed: %s attempt=%d/%d error=%s", log_prefix, url, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(_backoff_delay(attempt, base_delay=SEARCH_DELAY_MIN))
    return None


def _download_file(url):
    resp = _get_url(url)
    return resp.content if resp else None


def _parse_file_bytes(content, url):
    found = set()
    if not content:
        return found
    lower = url.lower()
    if lower.endswith(".pdf") and HAS_PYPDF2:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            found.update(_extract_emails_from_text(text))
            return found
        except Exception:
            pass
    if lower.endswith(".xslx") or lower.endswith(".xlsx"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    for cell in row:
                        if isinstance(cell, str):
                            found.update(_extract_emails_from_text(cell))
            return found
        except Exception:
            pass
    if lower.endswith(".xls"):
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=content)
            for sheet in book.sheets():
                for row in range(sheet.nrows):
                    for cell in sheet.row(row):
                        value = str(cell.value)
                        found.update(_extract_emails_from_text(value))
            return found
        except Exception:
            pass
    if lower.endswith(".docx"):
        try:
            import docx
            document = docx.Document(io.BytesIO(content))
            for para in document.paragraphs:
                found.update(_extract_emails_from_text(para.text))
            return found
        except Exception:
            pass
    if lower.endswith(".doc"):
        try:
            import textract
            text = textract.process(io.BytesIO(content)).decode('utf-8', errors='ignore')
            found.update(_extract_emails_from_text(text))
            return found
        except Exception:
            pass
    try:
        text = content.decode('utf-8', errors='ignore')
        found.update(_extract_emails_from_text(text))
    except Exception:
        pass
    return found


def _deep_urls(soup, base_url):
    urls = set()
    if not base_url:
        return urls
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        try:
            full = urljoin(base_url, href)
        except Exception:
            continue
        if not full.startswith("http"):
            continue
        parsed_full = urlparse(full)
        if parsed_full.netloc != parsed.netloc:
            continue
        if parsed_full.path in {"", "/"}:
            continue
        if any(part in parsed_full.path.lower() for part in ("/contact", "/about", "/team", "/people", "/profile", "/blog", "/jobs", "/careers")):
            urls.add(full)
    return list(urls)[:10]


def _emails_from_url(url):
    global EMAIL_DEBUG_COUNT
    url = url.strip()
    if not url or not url.startswith("http"):
        return set()
    if any(url.lower().endswith(ext) for ext in (".pdf", ".csv", ".txt", ".xls", ".xlsx", ".doc", ".docx")):
        content = _download_file(url)
        emails = _parse_file_bytes(content, url)
        logging.info("_emails_from_url: extracted %d emails from %s", len(emails), url[:200])
        return emails
    try:
        soup = _soup(url)
        if EMAIL_DEBUG_ENABLED and EMAIL_DEBUG_COUNT < 3:
            html_snippet = str(soup)[:3000]
            logging.info("[email-debug] URL=%s HTML sample=%s", url[:250], html_snippet)
            EMAIL_DEBUG_COUNT += 1
        emails = _emails_from_soup(soup, debug=EMAIL_DEBUG_ENABLED)
        if url.endswith(".xml") or url.endswith(".rss"):
            emails.update(_extract_emails_from_text(soup.get_text(separator=" ")))
        logging.info("_emails_from_url: extracted %d emails from %s", len(emails), url[:200])
        if not emails:
            logging.warning("[email-debug] no emails found for %s; visible text sample=%s", url[:250], soup.get_text(separator=" ")[:2000])
        return emails
    except Exception as exc:
        logging.debug("_emails_from_url: failed for %s: %s", url[:200], exc)
        return set()


def _extract_search_urls(soup, base=None):
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/") and base:
            href = urljoin(base, href)
        if href.startswith("http"):
            urls.add(href.split("&url=")[-1].split("&rct=")[0])
    return urls


def _ddg_search(query, max_results=RESULTS_PER_QUERY):
    urls = []
    if not ddg:
        return urls
    for attempt in range(1, DDG_RETRIES + 1):
        try:
            try:
                results = ddg(query, max_results=max_results, timeout=DDG_SEARCH_TIMEOUT)
            except TypeError:
                results = ddg(query, max_results=max_results)
            return list(results or [])
        except Exception as exc:
            logging.warning("DuckDuckGo query attempt %d/%d failed: %s", attempt, DDG_RETRIES, exc)
            if attempt < DDG_RETRIES:
                time.sleep(_backoff_delay(attempt, base_delay=DDG_RETRY_DELAY))
    return []


def _duckduckgo_html_search(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        logging.debug("[search_duckduckgo] request URL=%s", search_url)
        resp = _get_url(search_url, timeout=SEARCH_REQUEST_TIMEOUT, log_prefix="[search_duckduckgo]")
        if resp is None:
            logging.warning("[search_duckduckgo] no response for query=%r", query)
            return urls
        raw_html = resp.text or ""
        logging.debug("[search_duckduckgo] response status=%s length=%s", resp.status_code, len(raw_html))
        soup = BeautifulSoup(raw_html, "html.parser")
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and href.startswith("http"):
                urls.append(href)
        if not urls:
            for a in soup.select("a[href]"):
                href = a.get("href").strip()
                if href.startswith("http"):
                    urls.append(href)
        logging.info("[search_duckduckgo] extracted %d URLs from HTML DuckDuckGo for query=%r", len(urls), query)
    except Exception as exc:
        snippet = raw_html[:1000].replace("\n", " ").replace("\r", " ") if 'raw_html' in locals() else ''
        logging.exception("[search_duckduckgo] parse failed for query=%r: %s", query, exc)
        logging.debug("[search_duckduckgo] raw HTML sample=%s", snippet)
    return urls[:max_results]


def search_duckduckgo(query, max_results=RESULTS_PER_QUERY):
    urls = []
    results = _ddg_search(query, max_results=max_results)
    if results:
        for item in results:
            url = item.get("href") or item.get("url") or item.get("link") or ""
            if url:
                urls.append(url)
    if not urls:
        urls = _duckduckgo_html_search(query, max_results=max_results)
    return urls


def search_google(query, max_results=RESULTS_PER_QUERY):
    urls = []
    if not google_search:
        return urls
    try:
        for result in google_search(query, num_results=max_results):
            if result:
                urls.append(result)
    except Exception:
        pass
    return urls


def _resolve_bing_redirect(href, base_url=None):
    if not href:
        return None
    if href.startswith("/"):
        href = urljoin(base_url or "https://www.bing.com", href)
    if "bing.com/ck/a" not in href:
        return href

    try:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        if "u" in params and params["u"]:
            encoded = params["u"][0]
            for candidate in (encoded, encoded[2:] if encoded.startswith("a1") else encoded):
                try:
                    padded = candidate + "=" * (-len(candidate) % 4)
                    decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="ignore")
                    if decoded.startswith("http"):
                        logging.info("[search_bing] resolved Bing redirect from %s to %s", href, decoded)
                        return decoded
                except Exception:
                    continue

        # Fallback: follow the redirect if the encoded u parameter failed.
        resp = _get_url(href)
        if resp is None:
            return None
        final_url = getattr(resp, "url", None)
        if final_url and final_url.startswith("http"):
            logging.info("[search_bing] followed redirect from %s to %s", href, final_url)
            return final_url
    except Exception as exc:
        logging.debug("[search_bing] redirect resolution failed for %s: %s", href, exc)
    return None


def search_bing(query, max_results=RESULTS_PER_QUERY):
    urls = []
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    logging.debug("[search_bing] request URL=%s", url)
    try:
        resp = _get_url(url, timeout=SEARCH_REQUEST_TIMEOUT, log_prefix="[search_bing]")
        if resp is None:
            logging.warning("[search_bing] no response received for query=%r", query)
            return urls

        raw_html = resp.text or ""
        logging.debug("[search_bing] response status=%s length=%d", resp.status_code, len(raw_html))
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
            selectors = [
                "li.b_algo h2 a",
                "h2 a",
                ".b_algo h2 a",
                "a[href*='bing.com/ck/a']",
                "a[href*='www.bing.com/aclick']",
                "a[href*='/aclick?']",
                "a[href*='rd?']",
                "a[href*='/search?q=']",
            ]
            parsed_links = []
            for selector in selectors:
                found = []
                for a in soup.select(selector):
                    href = a.get("href")
                    if href:
                        found.append(href)
                logging.info("[search_bing] selector %r matched %d links for query=%r", selector, len(found), query)
                if found:
                    parsed_links.extend(found)
                    break

            if not parsed_links:
                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    if href.startswith("http") or href.startswith("/"):
                        parsed_links.append(href)
                logging.info("[search_bing] fallback extracted %d links for query=%r", len(parsed_links), query)

            resolved_urls = []
            for href in parsed_links:
                final_url = _resolve_bing_redirect(href, base_url=url)
                if final_url and final_url.startswith("http") and "bing.com" not in urlparse(final_url).netloc.lower():
                    resolved_urls.append(final_url)
                elif final_url:
                    resolved_urls.append(final_url)
            if not resolved_urls and search_duckduckgo:
                logging.info("[search_bing] no resolved Bing URLs, falling back to DuckDuckGo for query=%r", query)
                resolved_urls = search_duckduckgo(query, max_results=max_results)

            urls = resolved_urls[:max_results]
            logging.info("[search_bing] found %d resolved links for query=%r", len(urls), query)
            if urls:
                logging.info("[search_bing] first resolved result=%s", urls[0][:200])
            else:
                snippet = raw_html[:2000].replace("\n", " ").replace("\r", " ")
                logging.info("[search_bing] no links found; HTML sample=%s", snippet)
        except Exception as parse_exc:
            snippet = raw_html[:1000].replace("\n", " ").replace("\r", " ")
            logging.exception("[search_bing] parse failed for query=%r: %s", query, parse_exc)
            logging.debug("[search_bing] raw HTML sample=%s", snippet)
    except Exception as exc:
        logging.exception("[search_bing] request failed for query=%r", query, exc)
    return urls[:max_results]


def search_yahoo(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        resp = _get_url(f"https://search.yahoo.com/search?p={quote_plus(query)}")
        if resp is None:
            return urls
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href]"):
            href = a["href"].strip()
            if href.startswith("http") and "yahoo.com" not in href and "mkp=swp" not in href:
                urls.append(href)
    except Exception:
        pass
    return urls[:max_results]


def search_yandex(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        resp = _get_url(f"https://yandex.com/search/?text={quote_plus(query)}")
        if resp is None:
            return urls
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.link.organic__url"):
            href = a.get("href")
            if href and href.startswith("http"):
                urls.append(href)
        if not urls:
            for a in soup.select("a[href]"):
                href = a["href"].strip()
                if href.startswith("http") and "yandex" not in href:
                    urls.append(href)
    except Exception:
        pass
    return urls[:max_results]


def search_qwant(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        resp = _get_url(f"https://www.qwant.com/?q={quote_plus(query)}")
        if resp is None:
            return urls
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.result__url"):
            href = a.get("href")
            if href and href.startswith("http"):
                urls.append(href)
        if not urls:
            urls.update(_extract_search_urls(soup, base="https://www.qwant.com"))
    except Exception:
        pass
    return list(urls)[:max_results]


def search_startpage(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        resp = _get_url(f"https://www.startpage.com/sp/search?q={quote_plus(query)}")
        if resp is None:
            return urls
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.w-gl__result-url"):
            href = a.get("href")
            if href and href.startswith("http"):
                urls.append(href)
        if not urls:
            urls.update(_extract_search_urls(soup, base="https://www.startpage.com"))
    except Exception:
        pass
    return list(urls)[:max_results]


def search_baidu(query, max_results=RESULTS_PER_QUERY):
    urls = []
    try:
        resp = _get_url(f"https://www.baidu.com/s?wd={quote_plus(query)}")
        if resp is None:
            return urls
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("div.result a[href]"):
            href = a.get("href")
            if href and href.startswith("http"):
                urls.append(href)
    except Exception:
        pass
    return urls[:max_results]


def _search_with_retry(engine_func, query, max_results, engine_name):
    last_error = None
    for attempt in range(1, SEARCH_RETRY_ATTEMPTS + 1):
        try:
            found = engine_func(query, max_results=max_results)
            if found:
                return found
            last_error = "empty result"
        except Exception as exc:
            last_error = exc
            logging.warning("[search_all_engines] %s attempt %d/%d failed for query=%r: %s", engine_name, attempt, SEARCH_RETRY_ATTEMPTS, query, exc)
        if attempt < SEARCH_RETRY_ATTEMPTS:
            delay = min(30, SEARCH_DELAY_MIN * (2 ** (attempt - 1)) + random.uniform(0, 2))
            time.sleep(delay)
    if last_error is not None:
        logging.warning("[search_all_engines] %s exhausted retries for query=%r", engine_name, query)
    return []


def search_all_engines(query, max_results=RESULTS_PER_QUERY, engine="all"):
    urls = set()
    
    # Establish priority search order: Bing -> DuckDuckGo -> Google
    if engine == "bing":
        order = [search_bing, search_duckduckgo]
        if google_search:
            order.append(search_google)
    elif engine == "duckduckgo":
        order = [search_duckduckgo]
    elif engine == "google":
        order = [search_google] if google_search else []
    else:  # "all" or any other value
        order = [search_bing, search_duckduckgo]
        if google_search:
            order.append(search_google)
        extra_engines = [search_yahoo, search_yandex, search_qwant, search_startpage]
    
    # Execute engines in priority order. If an engine returns results, we stop trying fallbacks.
    results_found = False
    for engine_func in order:
        if not engine_func:
            continue
        engine_name = engine_func.__name__
        if SEARCH_ENGINE_FAILURES.get(engine_name, 0) >= SEARCH_ENGINE_FAILURE_LIMIT:
            logging.warning("[search_all_engines] skipping engine %s due to repeated failures", engine_name)
            continue
        logging.info("[search_all_engines] trying engine %s for query=%r", engine_name, query)
        start_time = time.time()
        try:
            found = _search_with_retry(engine_func, query, max_results, engine_name)
            elapsed = time.time() - start_time
            logging.info("[search_all_engines] engine %s returned %d URLs for query=%r in %.2fs", engine_name, len(found), query, elapsed)
            if found:
                urls.update(found)
                results_found = True
                SEARCH_ENGINE_FAILURES[engine_name] = 0
                break
            SEARCH_ENGINE_FAILURES[engine_name] = SEARCH_ENGINE_FAILURES.get(engine_name, 0) + 1
        except Exception as exc:
            elapsed = time.time() - start_time
            SEARCH_ENGINE_FAILURES[engine_name] = SEARCH_ENGINE_FAILURES.get(engine_name, 0) + 1
            logging.debug("[search_all_engines] engine %s failed for query=%r after %.2fs: %s", engine_name, query, elapsed, exc)
        time.sleep(random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX))
        
    # If no results were found from priority engines, and we are using "all", try extra engines
    if not results_found and engine == "all":
        for engine_func in extra_engines:
            if not engine_func:
                continue
            engine_name = engine_func.__name__
            if SEARCH_ENGINE_FAILURES.get(engine_name, 0) >= SEARCH_ENGINE_FAILURE_LIMIT:
                logging.warning("[search_all_engines] skipping fallback engine %s due to repeated failures", engine_name)
                continue
            logging.info("[search_all_engines] trying fallback engine %s for query=%r", engine_name, query)
            start_time = time.time()
            try:
                found = _search_with_retry(engine_func, query, max_results, engine_name)
                elapsed = time.time() - start_time
                logging.info("[search_all_engines] fallback engine %s returned %d URLs for query=%r in %.2fs", engine_name, len(found), query, elapsed)
                if found:
                    urls.update(found)
                    SEARCH_ENGINE_FAILURES[engine_name] = 0
                else:
                    SEARCH_ENGINE_FAILURES[engine_name] = SEARCH_ENGINE_FAILURES.get(engine_name, 0) + 1
            except Exception as exc:
                elapsed = time.time() - start_time
                SEARCH_ENGINE_FAILURES[engine_name] = SEARCH_ENGINE_FAILURES.get(engine_name, 0) + 1
                logging.debug("[search_all_engines] fallback engine %s failed for query=%r after %.2fs: %s", engine_name, query, elapsed, exc)
            time.sleep(random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX))
            
    return list(urls)[: max_results * 3]


def scrape_site(url):
    with _url_lock:
        if url in _visited_urls:
            return set()
        _visited_urls.add(url)

    emails = set()
    for attempt in range(MAX_RETRIES):
        try:
            soup = _soup(url)
            emails.update(_emails_from_soup(soup))
            deeps = _deep_urls(soup, url)
            for durl in deeps:
                with _url_lock:
                    if durl in _visited_urls:
                        continue
                    _visited_urls.add(durl)
                try:
                    time.sleep(random.uniform(1.0, 2.5))
                    ds = _soup(durl)
                    emails.update(_emails_from_soup(ds))
                except Exception:
                    pass
            break
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return emails


# ============================================================
# QUERIES — 150+ aggressive dorks
# ============================================================
def build_queries(category="all"):
    category = category.lower().strip() if category else "all"
    if category not in CATEGORY_KEYS:
        category = "all"

    def add(query_text, query_category=None):
        q.append((query_text, query_category))

    q = []

    if category == "all":
        add('site:github.com "email" "@gmail.com"', "Personal")
        add('site:github.com "email" "@yahoo.com"', "Personal")
        add('site:github.com "email" "@outlook.com"', "Personal")
        add('site:github.io "email" "@gmail.com"', "Personal")
        add('"github.com" "contact" "@gmail.com"', "Personal")
        add('site:linkedin.com/in "email" "@gmail.com"', "Personal")
        add('site:linkedin.com/in "contact" "@gmail.com"', "Personal")
        add('"linkedin.com" "resume" "@gmail.com"', "Personal")
        add('site:reddit.com "email" "@gmail.com"', "Personal")
        add('site:reddit.com "contact" "@gmail.com"', "Personal")
        add('"reddit.com" "message" "@gmail.com"', "Personal")
        add('site:quora.com "email" "@gmail.com"', "Personal")
        add('site:quora.com "profile" "@gmail.com"', "Personal")
        add('site:medium.com "email" "@gmail.com"', "Personal")
        add('site:medium.com "contact" "@gmail.com"', "Personal")
        add('site:stackoverflow.com "email" "@gmail.com"', "Personal")
        add('site:stackoverflow.com "profile" "@gmail.com"', "Personal")
        add('site:behance.net "email" "@gmail.com"', "Personal")
        add('site:dribbble.com "email" "@gmail.com"', "Personal")
        add('site:about.me "email" "@gmail.com"', "Personal")
        add('"github.com" "email" "@gmail.com" "issue"', "Personal")
        add('"github.com" "email" "@gmail.com" "comment"', "Personal")
        add('"resume" "@gmail.com" "experience"', "Personal")
        add('"portfolio" "@gmail.com" "developer"', "Personal")
        add('"student" "@gmail.com" "university"', "Personal")
        add('"student" "@yahoo.com" "college"', "Student")
        add('"developer" "@outlook.com" "github"', "Developer")
        add('"gamer" "@protonmail.com" "discord"', "Gamer")

    if category in ("all", "gaming"):
        for term in CATEGORY_TERMS["gaming"]:
            for template in CATEGORY_TEMPLATES["gaming"]:
                add(template.format(term=term), "Gaming")
        add('"esports" "@gmail.com" "team"', "Gaming")
        add('"streamer" "@gmail.com" "contact"', "Gaming")
        add('"game producer" "@gmail.com" "contact"', "Gaming")
        add('"game studio" "@gmail.com" "email"', "Gaming")

    if category in ("all", "marketing"):
        for term in CATEGORY_TERMS["marketing"]:
            for template in CATEGORY_TEMPLATES["marketing"]:
                add(template.format(term=term), "Marketing")
        add('"email marketing" "@gmail.com" "specialist"', "Marketing")
        add('"marketing automation" "@gmail.com" "expert"', "Marketing")
        add('"campaign manager" "@gmail.com" "contact"', "Marketing")

    if category in ("all", "business"):
        for term in CATEGORY_TERMS["business"]:
            for template in CATEGORY_TEMPLATES["business"]:
                add(template.format(term=term), "Business")
        add('"CEO" "@gmail.com" "company"', "Business")
        add('"founder" "@gmail.com" "startup"', "Business")
        add('"entrepreneur" "@gmail.com" "contact"', "Business")

    if category in ("all", "freelancer"):
        add('"freelancer" "@gmail.com" "portfolio"', "Freelancer")
        add('"upwork" "@gmail.com" "profile"', "Freelancer")

    if category in ("all", "online-income"):
        add('"online income" "@gmail.com" "blog"', "Online Income")
        add('"passive income" "@gmail.com" "expert"', "Online Income")

    if category in ("all", "affiliate-marketers"):
        add('"affiliate" "@gmail.com" "marketing"', "Affiliate Marketers")
        add('"digital product" "@gmail.com"', "Affiliate Marketers")

    if category in ("all", "side-hustle"):
        add('"side hustle" "@gmail.com" "founder"', "Side Hustle")
        add('"startup" "@gmail.com" "entrepreneur"', "Side Hustle")

    if category in ("all", "blogger"):
        add('"blogger" "@gmail.com" "contact"', "Blogger")
        add('"content creator" "@gmail.com" "email"', "Blogger")

    if category in ("all", "job-seeker"):
        for term in CATEGORY_TERMS["job-seeker"]:
            for template in CATEGORY_TEMPLATES["job-seeker"]:
                add(template.format(term=term), "Job Seeker")
        add('"job seeker" "@gmail.com" "resume"', "Job Seeker")
        add('"looking for job" "@gmail.com" "experience"', "Job Seeker")
        add('"open to work" "@gmail.com" "skills"', "Job Seeker")
        add('"fresh graduate" "@gmail.com" "cv"', "Job Seeker")
        add('"entry level" "@gmail.com" "portfolio"', "Job Seeker")
        add('"career change" "@gmail.com" "available"', "Job Seeker")
        add('"seeking opportunity" "@gmail.com" "apply"', "Job Seeker")
        add('"job applicant" "@gmail.com" "experience"', "Job Seeker")
        add('"candidate" "@gmail.com" "resume" "hire"', "Job Seeker")
        add('"now hiring" "@gmail.com" "job" "apply"', "Job Seeker")

    if category == "all":
        pros = ["CEO", "CTO", "CFO", "COO", "Founder", "Co-Founder",
                "President", "Vice President", "Managing Director",
                "Executive Director", "Board Member", "Director",
                "Senior Manager", "Department Head", "Team Lead",
                "Project Manager", "Product Manager", "Engineering Manager",
                "Software Engineer", "Full Stack Developer", "Data Scientist",
                "DevOps Engineer", "UX Designer", "Product Designer",
                "Cloud Architect", "Security Analyst", "AI Engineer",
                "Research Scientist", "Biotech Researcher",
                "Financial Analyst", "Investment Banker",
                "Marketing Director", "Brand Manager",
                "Sales Director", "Business Development Manager",
                "HR Director", "Talent Acquisition Manager",
                "Legal Counsel", "Corporate Attorney",
                "Professor", "Associate Professor", "Principal",
                "Physician", "Surgeon", "Cardiologist",
                "Architect", "Civil Engineer", "Mechanical Engineer",
                "Consultant", "Analyst", "Advisor"]
        for role in pros:
            add(f'"{role}" "@gmail.com" "contact"')

        countries = ["USA", "UK", "Canada", "Australia", "Germany", "France",
                     "Japan", "Brazil", "India", "China", "UAE", "Singapore",
                     "Bangladesh", "Pakistan", "South Africa", "Italy", "Spain",
                     "Netherlands", "Switzerland", "Sweden", "Norway", "Denmark",
                     "Finland", "Ireland", "Belgium", "Austria", "Poland",
                     "Turkey", "Greece", "Portugal", "Malaysia", "Philippines",
                     "Thailand", "Vietnam", "Indonesia", "Hong Kong", "Taiwan",
                     "New Zealand", "South Korea", "Saudi Arabia", "Egypt",
                     "Nigeria", "Kenya", "Morocco", "Israel", "Qatar", "Kuwait"]
        for c in countries:
            add(f'"CEO" "@gmail.com" "{c}"')
            add(f'"director" "@" "{c}" "email"')
            add(f'"manager" "@" "{c}" "company"')
            add(f'"founder" "@gmail.com" "{c}"')
            add(f'"professor" "@" "{c}" "university"')

        institutions = ["hospital", "clinic", "medical center", "university",
                        "college", "school", "IT firm", "software company",
                        "technology", "startup", "NGO", "nonprofit",
                        "foundation", "charity", "research institute",
                        "government", "ministry", "embassy", "consulate",
                        "bank", "insurance", "hospitality", "hotel",
                        "restaurant", "retail", "ecommerce", "manufacturing",
                        "logistics", "pharmaceutical", "biotech",
                        "telecom", "media", "entertainment",
                        "law firm", "consulting", "accounting",
                        "real estate", "construction", "architecture",
                        "energy", "oil & gas", "mining", "agriculture",
                        "aviation", "automotive", "aerospace",
                        "defense", "security"]
        for inst in institutions:
            add(f'"{inst}" "contact" "@" "email"')
            add(f'"{inst}" "CEO" "@gmail.com"')

        top_c = ["USA", "UK", "Canada", "India", "Bangladesh", "UAE", "Singapore",
                 "Australia", "Germany", "France", "Japan", "Brazil"]
        top_i = ["tech", "finance", "healthcare", "education", "manufacturing",
                 "legal", "hospitality", "construction"]
        for c in top_c:
            for ind in top_i:
                add(f'"{ind}" "@" "{c}" "director"')
                add(f'"{ind}" "@gmail.com" "{c}"')

        q.extend([
            ('inurl:contact "email" "@gmail.com" "CEO"', None),
            ('inurl:contact "email" "@" "director" "company"', None),
            ('inurl:contact "email" "@" "manager"', None),
            ('inurl:about "email" "@" "founder" "company"', None),
            ('inurl:about "email" "@" "CEO" "leadership"', None),
            ('inurl:team "email" "@gmail.com" "developer"', None),
            ('inurl:team "email" "@" "designer" "creative"', None),
            ('inurl:team "email" "@" "engineer" "software"', None),
            ('inurl:staff "email" "@" "manager" "company"', None),
            ('inurl:staff "email" "@" "professor" "university"', None),
            ('inurl:staff "email" "@gmail.com" "faculty"', None),
            ('inurl:directory "email" "@" "employee"', None),
            ('inurl:directory "email" "@gmail.com" "member"', None),
            ('inurl:faculty "email" "@" "professor" "PhD"', None),
            ('inurl:faculty "email" "@" "department"', None),
            ('inurl:leadership "email" "@" "CEO" "executive"', None),
            ('inurl:leadership "email" "@" "director" "VP"', None),
            ('inurl:management "email" "@" "director"', None),
            ('inurl:management "email" "@gmail.com" "manager"', None),
            ('inurl:careers "email" "@" "hr" "recruitment"', None),
            ('inurl:careers "email" "@gmail.com" "apply"', None),
            ('inurl:careers "email" "@" "contact" "job"', None),
            ('inurl:portfolio "email" "@gmail.com" "designer"', None),
            ('inurl:portfolio "email" "@" "artist" "creative"', None),
            ('inurl:profile "email" "@" "user" "member"', None),
            ('inurl:profile "email" "@gmail.com" "bio"', None),
            ('intitle:contact "email" "@" "business" "inquiry"', None),
            ('intitle:contact "email" "@" "customer" "service"', None),
            ('intitle:contact "email" "@gmail.com" "message"', None),
            ('intitle:team "email" "@" "meet" "our"', None),
            ('intitle:staff "email" "@" "our" "team"', None),
        ])

        q.extend([
            ('"resume" "@gmail.com" "CEO" "experience"', None),
            ('"resume" "@gmail.com" "senior" "manager" "technology"', None),
            ('"resume" "@gmail.com" "PhD" "research" "university"', None),
            ('"resume" "@gmail.com" "MBA" "finance" "executive"', None),
            ('"resume" "@gmail.com" "software" "engineer" "senior"', None),
            ('"resume" "@gmail.com" "data" "scientist" "machine" "learning"', None),
            ('"resume" "@gmail.com" "product" "manager" "SaaS"', None),
            ('"resume" "@gmail.com" "UX" "designer" "portfolio"', None),
            ('"portfolio" "@gmail.com" "frontend" "developer" "react"', None),
            ('"portfolio" "@gmail.com" "full" "stack" "developer"', None),
            ('"portfolio" "@gmail.com" "graphic" "designer" "creative"', None),
            ('"portfolio" "@gmail.com" "photographer" "professional"', None),
            ('"portfolio" "@gmail.com" "architect" "project" "design"', None),
            ('"about" "@gmail.com" "founder" "CEO" "startup"', None),
            ('"about" "@gmail.com" "co-founder" "entrepreneur"', None),
            ('"about" "@gmail.com" "developer" "engineer" "software"', None),
            ('"about" "@gmail.com" "designer" "creative" "director"', None),
            ('"about" "@gmail.com" "professor" "researcher" "university"', None),
            ('"about" "@gmail.com" "consultant" "advisor" "business"', None),
        ])

        q.extend([
            ('site:ac.in "email" "@" "professor" "department"', None),
            ('site:ac.in "email" "@gmail.com" "faculty"', None),
            ('site:ac.uk "email" "@" "professor" "contact"', None),
            ('site:ac.uk "email" "@" "head" "department"', None),
            ('site:edu "email" "@" "professor" "department"', None),
            ('site:edu "email" "@gmail.com" "faculty" "member"', None),
            ('site:sch.gr "email" "@" "teacher" "contact"', None),
            ('"faculty" "@" "university" "department" "email"', None),
            ('"professor" "@" "university" "contact" "research"', None),
            ('"dean" "@" "university" "contact" "email"', None),
            ('"registrar" "@" "college" "edu" "email"', None),
            ('"admissions" "@" "university" "contact" "apply"', None),
            ('"academic" "@" "institute" "contact" "email"', None),
            ('"research" "@" "lab" "contact" "scientist"', None),
            ('"dean" "@gmail.com" "university" "academic"', None),
            ('"provost" "@" "university" "contact"', None),
        ])

        q.extend([
            ('site:alumni.edu "email" "@gmail.com"', None),
            ('site:alumni.org "email" "@" "contact"', None),
            ('"alumni" "@gmail.com" "university" "class"', None),
            ('"alumni" "@gmail.com" "batch" "MBA"', None),
            ('"alumni" "@gmail.com" "engineering" "graduate"', None),
            ('"student" "@gmail.com" "university" "scholarship"', None),
            ('"student" "@gmail.com" "college" "internship"', None),
            ('"student" "@" "college" "forum" "member"', None),
            ('"graduate" "@gmail.com" "university" "class"', None),
            ('"graduate" "@" "university" "alumni" "contact"', None),
        ])

        q.extend([
            ('"email" "@" "contact" "CEO" "company"', None),
            ('"email" "@" "info" "director" "organization"', None),
            ('"email" "@" "contact" "president" "firm"', None),
            ('"email" "@" "reach" "founder" "startup"', None),
            ('"email" "@" "contact" "manager" "department"', None),
            ('"email" "@" "contact" "engineer" "software"', None),
            ('"email" "@" "contact" "developer" "web"', None),
            ('"email" "@" "contact" "designer" "graphic"', None),
            ('"email" "@" "contact" "professor" "university"', None),
            ('"email" "@" "contact" "doctor" "hospital"', None),
            ('"email" "@" "contact" "attorney" "law"', None),
            ('"email" "@" "contact" "architect" "firm"', None),
            ('"email" "@" "contact" "consultant" "management"', None),
            ('"email" "@" "contact" "analyst" "financial"', None),
            ('"email" "@" "contact" "director" "marketing"', None),
            ('"email" "@" "contact" "manager" "operations"', None),
            ('"email" "@" "contact" "head" "sales"', None),
            ('"email" "@" "contact" "VP" "engineering"', None),
            ('"email" "@" "contact" "director" "HR"', None),
            ('"email" "@" "contact" "supervisor" "department"', None),
        ])

        random.shuffle(q)
        return q

    random.shuffle(q)
    return q


# ============================================================
# COUNTRY REPORT
# ============================================================
def generate_report(all_emails):
    if not all_emails:
        return
    counter = Counter()
    normalized_emails = []
    for e in all_emails:
        email = e[0] if isinstance(e, tuple) else e
        normalized_emails.append(email)
        counter[detect_country(email)] += 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"country_report_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Country", "Emails", "Percentage"])
        total = len(normalized_emails)
        for country, count in counter.most_common():
            w.writerow([country, count, f"{count/total*100:.1f}%"])
    print("\n" + "-" * 60)
    print("  COUNTRY BREAKDOWN (top 15)")
    print("" + "-" * 60)
    for country, count in counter.most_common(15):
        bar = "#" * max(1, int(count / max(counter.values()) * 20))
        print(f"  {country:<24s} {count:>5d}  {bar}")
    print("" + "-" * 60)
    print(f"  Total countries: {len(counter)}")
    print(f"  CSV report: {csv_path}")


# ============================================================
# MAIN COLLECTOR
# ============================================================
class Collector:
    def __init__(self, category="all"):
        self.all_emails = set()
        self.category = category
        self.queries = build_queries(category)
        random.shuffle(self.queries)
        self.total_queries = len(self.queries)
        self.queries_done = 0
        self.db_inserted = 0
        self.duplicates_skipped = 0
        self.start_time = time.time()
        self._stats_lock = threading.Lock()

    def _worker(self, query_pair):
        query, category = query_pair
        local = set()
        try:
            urls = search_all_engines(query, max_results=RESULTS_PER_QUERY, engine="bing")
            for url in urls:
                time.sleep(random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX))
                emails = scrape_site(url)
                local.update((email, category) for email in emails)
        except Exception:
            pass
        return query_pair, local

    def run(self, max_queries=None):
        init_database()
        queries = self.queries[:max_queries] if max_queries else self.queries
        print(f"\n  Starting: {len(queries)} queries · {THREADS} threads · {RESULTS_PER_QUERY} results/query\n")

        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            futures = {executor.submit(self._worker, q): q for q in queries}

            for future in as_completed(futures):
                self.queries_done += 1
                try:
                    _, found = future.result()
                except Exception:
                    found = set()

                with self._stats_lock:
                    self.all_emails.update(found)

                with self._stats_lock:
                    if len(self.all_emails) >= SAVE_BATCH:
                        batch = list(self.all_emails)
                        self.all_emails.clear()
                    else:
                        batch = None

                if batch:
                    saved, skipped, saved_emails = save_emails(batch)
                    with self._stats_lock:
                        self.db_inserted += saved
                        self.duplicates_skipped += skipped
                    with open("emails.txt", "a", encoding="utf-8") as f:
                        for email in saved_emails:
                            f.write(email + "\n")

                elapsed = time.time() - self.start_time
                rate = self.queries_done / elapsed * 3600 if elapsed > 0 else 0
                pct = self.queries_done / self.total_queries * 100
                print(
                    f"\r[{self.queries_done}/{self.total_queries}] "
                    f"{pct:5.1f}% | "
                    f"Saved: {self.db_inserted:>5d} | "
                    f"Skipped: {self.duplicates_skipped:>4d} | "
                    f"Buffer: {len(self.all_emails):>3d} | "
                    f"{rate:.0f} q/h    ",
                    end="", flush=True,
                )

        if self.all_emails:
            saved, skipped, saved_emails = save_emails(list(self.all_emails))
            self.db_inserted += saved
            self.duplicates_skipped += skipped
            with open("emails.txt", "a", encoding="utf-8") as f:
                for email in saved_emails:
                    f.write(email + "\n")

        return self.db_inserted


# ============================================================
# CLI
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="general_leads.py v4 — Max-yield email collector")
    parser.add_argument("--quick", type=int, default=None, help="Run N queries")
    parser.add_argument("--report", action="store_true", help="Country report from emails.txt")
    parser.add_argument(
        "--category",
        type=str,
        default="all",
        choices=CATEGORY_KEYS,
        help="Run a category-specific campaign: gaming, marketing, business, freelancer, online-income, affiliate-marketers, side-hustle, blogger, all",
    )
    parser.add_argument("--skip-github", action="store_true", help="Skip GitHub public email collection")
    parser.add_argument("--skip-crunchbase", action="store_true", help="Skip Crunchbase public email collection")
    parser.add_argument(
        "--engine",
        type=str,
        default="bing",
        choices=["google", "bing", "duckduckgo", "all"],
        help="Primary search engine to use for search engine lead collection",
    )
    args = parser.parse_args()

    if args.report:
        if os.path.exists("emails.txt"):
            with open("emails.txt", encoding="utf-8") as f:
                existing = {line.strip() for line in f if line.strip()}
            generate_report(existing)
        else:
            print("No emails.txt found.")
        return

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    print("=" * 56)
    print("  general_leads.py v4 - MEGA Email Collector")
    print(f"  Category: {args.category.title()} | Queries: {len(build_queries(args.category))}  |  Threads: {THREADS}  |  Results/q: {RESULTS_PER_QUERY}")
    print("=" * 56)

    init_database()
    KNOWN_EMAILS.update(load_existing_emails())
    logging.info("Loaded %d existing emails from DB", len(KNOWN_EMAILS))

    github_saved = 0
    if args.skip_github:
        print("\nSkipping GitHub public collection (--skip-github).")
    elif GITHUB_PAT:
        print("\nCollecting public GitHub emails...")
        github_saved = collect_github_public_emails()
        print(f"GitHub saved: {github_saved} leads")
    else:
        print("\nGITHUB_PAT not set; skipping GitHub public collection.")

    crunchbase_saved = 0
    if args.skip_crunchbase:
        print("\nSkipping Crunchbase public collection (--skip-crunchbase).")
    else:
        crunchbase_saved = collect_crunchbase_public_emails(category=args.category)
        print(f"Crunchbase saved: {crunchbase_saved} leads")

    try:
        search_saved = run_with_timeout(collect_search_engine_leads, args=(args.category, args.engine), timeout_sec=COLLECTION_TIMEOUT)
    except TimeoutError as exc:
        logging.error("collect_search_engine_leads TIMED OUT: %s", exc)
        print(f"\n  TIMEOUT: collect_search_engine_leads exceeded {COLLECTION_TIMEOUT}s — skipping to next phase")
        search_saved = 0
    print(f"Search engine saved ({args.engine}): {search_saved} leads")

    social_saved = collect_social_media_leads(category=args.category)
    print(f"Social media saved: {social_saved} leads")

    professional_saved = collect_professional_platform_leads(category=args.category)
    print(f"Professional platforms saved: {professional_saved} leads")

    file_saved = collect_public_files(category=args.category)
    print(f"Public file saved: {file_saved} leads")

    collector = Collector(category=args.category)
    query_limit = args.quick
    total_scrape_saved = collector.run(max_queries=query_limit)
    print(f"\nDeep scraper saved: {total_scrape_saved} leads")

    total = github_saved + crunchbase_saved + search_saved + social_saved + professional_saved + file_saved + total_scrape_saved
    print(f"\n{'='*56}")
    print(f"  COMPLETE — {total} new emails saved to database")
    print(f"  Duplicates skipped: {collector.duplicates_skipped}")
    print(f"{'='*56}")

    if collector.all_emails:
        generate_report(collector.all_emails)

    print(f"\n  Backup: emails.txt")


if __name__ == "__main__":
    main()
