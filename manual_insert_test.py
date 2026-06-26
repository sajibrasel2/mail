import os
import re
import time
import logging
from dotenv import load_dotenv
import requests
import mysql.connector

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

GITHUB_API_BASE = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "github-leads-manual-test/1.0"}
PAT = os.getenv('GITHUB_PAT')
if PAT:
    HEADERS['Authorization'] = f"token {PAT}"

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DUMMY_EMAIL_PATTERNS = [r"^test@", r"^example@", r"^donotreply@", r"^no-reply@", r"^noreply@", r"@users\.noreply\.github\.com$", r"^admin@", r"^info@", r"^support@", r"^contact@"]
DUMMY_EMAIL_RE = re.compile("|".join(DUMMY_EMAIL_PATTERNS), re.IGNORECASE)

def is_valid_email(email: str) -> bool:
    if not email:
        return False
    email = email.strip()
    if DUMMY_EMAIL_RE.search(email):
        return False
    return bool(EMAIL_REGEX.match(email))

def fetch_profile(username: str):
    url = f"{GITHUB_API_BASE}/users/{username}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        logging.warning("Failed to fetch %s: %s", username, resp.status_code)
        return None
    return resp.json()

def get_db_conn():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST','127.0.0.1'),
        port=int(os.getenv('DB_PORT','3306')),
        user=os.getenv('DB_USER','root'),
        password=os.getenv('DB_PASSWORD') or None,
        database=os.getenv('DB_NAME','github_leads'),
        autocommit=True,
    )

def upsert_lead(conn, username, name, email, location, bio):
    cur = conn.cursor()
    insert_sql = """
    INSERT IGNORE INTO github_leads (username, name, email, location, bio)
    VALUES (%s, %s, %s, %s, %s)
    """
    cur.execute(insert_sql, (username, name, email, location, bio))
    affected = cur.rowcount
    cur.close()
    return affected

def main():
    candidates = [
        'sindresorhus', 'gaearon', 'tj', 'kennethreitz', 'yyx990803', 'mojombo',
        'defunkt', 'pjhyett', 'dhh', 'addyosmani', 'bdash', 'rstacruz', 'JakeWharton'
    ]

    conn = get_db_conn()

    for username in candidates:
        logging.info('Checking user: %s', username)
        profile = fetch_profile(username)
        time.sleep(1.0)
        if not profile:
            continue
        email = profile.get('email')
        if not email:
            logging.info('%s has no public email', username)
            continue
        logging.info('Found email for %s: %s', username, email)
        if not is_valid_email(email):
            logging.info('Email for %s failed validation/filtering', username)
            continue
        affected = upsert_lead(conn, username, profile.get('name'), email.strip(), profile.get('location'), profile.get('bio'))
        if affected > 0:
            logging.info('Inserted lead: %s <%s>', username, email)
        else:
            logging.info('Lead already exists or was skipped: %s <%s>', username, email)
        # print the inserted row for verification
        cur = conn.cursor()
        cur.execute('SELECT id, username, name, email, location, created_at FROM github_leads WHERE username = %s LIMIT 1', (username,))
        row = cur.fetchone()
        cur.close()
        print('DB ROW:', row)
        break

    conn.close()

if __name__ == '__main__':
    main()
