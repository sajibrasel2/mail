from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import json
import mysql.connector
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
from datetime import datetime, date
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me')

# When running behind the PHP proxy, honor X-Forwarded headers so URL generation
# and redirects use the original host/proto/prefix. Try both newer and older
# ProxyFix signatures for compatibility.
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    try:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    except TypeError:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
except Exception:
    # ProxyFix not available; continue without it
    pass

# Authentication defaults. These can be overridden with environment variables.
AUTH_EMAIL = os.getenv('AUTH_EMAIL', 'raselsajib25@gmail.com')
AUTH_PASSWORD = os.getenv('AUTH_PASSWORD', '12345Sajibs6@')

# Database configuration (reads from .env)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD') or None,
    'database': os.getenv('DB_NAME', 'github_leads'),
}

# SMTP configuration (reads from .env)
MAIL_SERVER = os.getenv('MAIL_SERVER')
MAIL_PORT = os.getenv('MAIL_PORT')
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS')
MAIL_USE_SSL = os.getenv('MAIL_USE_SSL')
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')

SMTP_SERVER = MAIL_SERVER or os.getenv('SMTP_SERVER', 'localhost')
SMTP_PORT = int(MAIL_PORT or os.getenv('SMTP_PORT', '25'))
SMTP_USERNAME = MAIL_USERNAME or os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = MAIL_PASSWORD or os.getenv('SMTP_PASSWORD', '')
SENDER_EMAIL = MAIL_DEFAULT_SENDER or os.getenv('SENDER_EMAIL') or (SMTP_USERNAME or f'no-reply@{os.getenv("DB_HOST","localhost")}')

# Determine TLS/SSL: MAIL_USE_TLS/MAIL_USE_SSL (1/0 or true/false) or infer from port
if MAIL_USE_SSL is not None:
    try:
        SMTP_USE_SSL = bool(int(MAIL_USE_SSL))
    except Exception:
        SMTP_USE_SSL = str(MAIL_USE_SSL).lower() in ('1', 'true', 'yes', 'on')
else:
    SMTP_USE_SSL = SMTP_PORT == 465

if MAIL_USE_TLS is not None:
    try:
        SMTP_USE_TLS = bool(int(MAIL_USE_TLS))
    except Exception:
        SMTP_USE_TLS = str(MAIL_USE_TLS).lower() in ('1', 'true', 'yes', 'on')
else:
    SMTP_USE_TLS = not SMTP_USE_SSL and SMTP_PORT != 465

CATEGORY_FILTERS = [
    ('all', 'All Categories'),
    ('Developer (GitHub)', 'Developer (GitHub)'),
    ('Web (General)', 'Web (General)'),
    ('Gaming', 'Gaming'),
    ('Marketing', 'Marketing'),
    ('Business', 'Business'),
    ('Freelancer', 'Freelancer'),
    ('Blogger', 'Blogger'),
    ('Job Seeker', 'Job Seeker'),
    ('Unknown', 'Unknown'),
]

CATEGORY_ORDER = [
    'Developer (GitHub)',
    'Web (General)',
    'Marketing',
    'Gaming',
    'Business',
    'Freelancer',
    'Blogger',
    'Job Seeker',
]

CATEGORY_TARGETS = {
    'Developer (GitHub)': 3,
    'Web (General)': 3,
    'Marketing': 3,
    'Gaming': 3,
    'Business': 2,
    'Freelancer': 2,
    'Blogger': 2,
    'Job Seeker': 2,
}
DAILY_EMAIL_LIMIT_DEFAULT = 20

CATEGORY_BADGES = {
    'Developer (GitHub)': 'bg-info text-dark',
    'Web (General)': 'bg-secondary text-dark',
    'Gaming': 'bg-primary',
    'Marketing': 'bg-success',
    'Business': 'bg-info text-dark',
    'Freelancer': 'bg-warning text-dark',
    'Blogger': 'bg-dark',
    'Job Seeker': 'bg-danger',
    'Unknown': 'bg-secondary text-dark',
    None: 'bg-secondary text-dark',
}

DEFAULT_LINK_1 = 'https://omg10.com/4/11017767'
DEFAULT_LINK_2 = 'https://www.effectivecpmnetwork.com/mgtqwzbp?key=5c4003e0ae2b0ebd387daded087bc9aa'

DEFAULT_CAMPAIGN_SUBJECT = 'Quick opportunity for {{NAME}} — check this out'
DEFAULT_CAMPAIGN_BODY = '''Hi {{NAME}},

I wanted to share a quick opportunity with you because your profile looks like a great fit.

This is not a generic pitch — I think you'll find these two links worth a look:

👉 Check out this amazing opportunity → {{LINK1}}
👉 Don't miss out, click here to learn more → {{LINK2}}

If you'd like, I can send a short summary of how this works in under 2 minutes.

Best regards,
{{SENDER_NAME}}
{{SENDER_EMAIL}}'''


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_db_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn


def init_db_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE `{DB_CONFIG['database']}`")
        cur.execute("""
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_send_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255),
                category VARCHAR(100),
                sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20),
                subject TEXT,
                body LONGTEXT,
                links TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS campaign_config (
                id INT AUTO_INCREMENT PRIMARY KEY,
                subject TEXT,
                body LONGTEXT,
                link1 VARCHAR(255),
                link2 VARCHAR(255),
                daily_limit INT NOT NULL DEFAULT %s,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """ % (DAILY_EMAIL_LIMIT_DEFAULT,))
        # Ensure column exists for older installs
        try:
            cur.execute(f"ALTER TABLE campaign_config ADD COLUMN IF NOT EXISTS daily_limit INT NOT NULL DEFAULT {DAILY_EMAIL_LIMIT_DEFAULT}")
        except Exception:
            pass
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM campaign_config")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO campaign_config (subject, body, link1, link2, daily_limit) VALUES (%s, %s, %s, %s, %s)",
                (DEFAULT_CAMPAIGN_SUBJECT, DEFAULT_CAMPAIGN_BODY, DEFAULT_LINK_1, DEFAULT_LINK_2, DAILY_EMAIL_LIMIT_DEFAULT),
            )
            conn.commit()
    finally:
        cur.close()
        conn.close()


def get_campaign_config():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM campaign_config ORDER BY id LIMIT 1")
        config = cur.fetchone()
        if not config:
            cur.execute(
                "INSERT INTO campaign_config (subject, body, link1, link2, daily_limit) VALUES (%s, %s, %s, %s, %s)",
                (DEFAULT_CAMPAIGN_SUBJECT, DEFAULT_CAMPAIGN_BODY, DEFAULT_LINK_1, DEFAULT_LINK_2, DAILY_EMAIL_LIMIT_DEFAULT),
            )
            conn.commit()
            cur.execute("SELECT * FROM campaign_config ORDER BY id LIMIT 1")
            config = cur.fetchone()
        # Ensure daily_limit present
        if config is not None and ('daily_limit' not in config or config.get('daily_limit') is None):
            config['daily_limit'] = DAILY_EMAIL_LIMIT_DEFAULT
        return config
    finally:
        cur.close()
        conn.close()


def update_campaign_config(subject, body, link1, link2, daily_limit):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE campaign_config SET subject=%s, body=%s, link1=%s, link2=%s, daily_limit=%s, updated_at=CURRENT_TIMESTAMP WHERE id = (SELECT id FROM campaign_config ORDER BY id LIMIT 1)",
            (subject, body, link1, link2, daily_limit),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def render_campaign_body(body_template, recipient_name, recipient_email, sender_name, sender_email, link1, link2):
    body = body_template
    body = body.replace('{{NAME}}', recipient_name or 'Friend')
    body = body.replace('{{EMAIL}}', recipient_email)
    body = body.replace('{{SENDER_NAME}}', sender_name or 'Your Team')
    body = body.replace('{{SENDER_EMAIL}}', sender_email or SENDER_EMAIL)
    body = body.replace('{{LINK1}}', link1)
    body = body.replace('{{LINK2}}', link2)
    return body


def log_send(email, category, status, subject, body, links):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO email_send_log (email, category, status, subject, body, links) VALUES (%s, %s, %s, %s, %s, %s)",
            (email, category, status, subject, body, links),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def send_email_smtp(to_email, subject, body):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg.set_content(body)

    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
    else:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
    server.ehlo()
    if SMTP_USE_TLS and SMTP_PORT != 465:
        server.starttls()
        server.ehlo()
    if SMTP_USERNAME and SMTP_PASSWORD:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
    try:
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def get_today_sent_count():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS today_sent FROM email_send_log WHERE DATE(sent_at) = CURRENT_DATE() AND status = 'Sent'")
        return cur.fetchone()['today_sent'] or 0
    finally:
        cur.close()
        conn.close()


def select_daily_campaign_leads(max_leads=DAILY_EMAIL_LIMIT_DEFAULT):
    init_db_schema()
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    selected_emails = []
    selected_ids = set()

    try:
        remaining = max_leads
        for category in CATEGORY_ORDER:
            if remaining <= 0:
                break
            target = min(CATEGORY_TARGETS.get(category, 0), remaining)
            if target <= 0:
                continue
            cur.execute(
                "SELECT id, email, name, category FROM github_leads WHERE status='Pending' AND COALESCE(category, %s) = %s ORDER BY created_at ASC LIMIT %s",
                ('Unknown', category, target),
            )
            rows = cur.fetchall()
            for row in rows:
                selected_emails.append(row)
                selected_ids.add(row['id'])
            remaining = max_leads - len(selected_emails)

        if len(selected_emails) < max_leads:
            remaining = max_leads - len(selected_emails)
            format_ids = ','.join(str(i) for i in selected_ids) if selected_ids else '0'
            query = f"SELECT id, email, name, category FROM github_leads WHERE status='Pending' AND id NOT IN ({format_ids}) ORDER BY created_at ASC LIMIT %s"
            cur.execute(query, (remaining,))
            selected_emails.extend(cur.fetchall())

        return selected_emails
    finally:
        cur.close()
        conn.close()


def run_daily_campaign():
    today_sent = get_today_sent_count()
    config = get_campaign_config()
    daily_limit = int(config.get('daily_limit') or DAILY_EMAIL_LIMIT_DEFAULT)
    if today_sent >= daily_limit:
        return {
            'sent': 0,
            'attempted': 0,
            'message': f'Daily campaign quota already reached ({today_sent}/{daily_limit}).',
        }

    subject_template = config['subject']
    body_template = config['body']
    link1 = config['link1'] or DEFAULT_LINK_1
    link2 = config['link2'] or DEFAULT_LINK_2

    remaining = daily_limit - today_sent
    leads = select_daily_campaign_leads(max_leads=remaining)
    if not leads:
        return {'sent': 0, 'attempted': 0, 'message': 'No pending leads available.'}

    sent = 0
    attempted = 0
    for lead in leads:
        recipient_name = (lead.get('name') if isinstance(lead, dict) else None) or (lead.get('username') if isinstance(lead, dict) else None) or 'Friend'
        personalized_subject = subject_template.replace('{{NAME}}', recipient_name)
        personalized_body = render_campaign_body(
            body_template,
            recipient_name,
            lead['email'],
            AUTH_EMAIL,
            SENDER_EMAIL,
            link1,
            link2,
        )
        attempted += 1
        try:
            send_email_smtp(lead['email'], personalized_subject, personalized_body)
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("UPDATE github_leads SET status='Sent', sent_at=%s WHERE id=%s", (datetime.utcnow(), lead['id']))
                conn.commit()
            finally:
                cur.close()
                conn.close()
            log_send(lead['email'], lead['category'] or 'Unknown', 'Sent', personalized_subject, personalized_body, json.dumps([link1, link2]))
            sent += 1
        except Exception as exc:
            log_send(lead['email'], lead['category'] or 'Unknown', 'Failed', personalized_subject, personalized_body, json.dumps([link1, link2]))

    return {'sent': sent, 'attempted': attempted, 'message': f'{sent} emails sent.'}


scheduler_started = False

def start_campaign_scheduler():
    global scheduler_started
    if scheduler_started:
        return
    scheduler_started = True
    try:
        from campaign_scheduler import start_campaign_scheduler as _start_scheduler
        _start_scheduler()
    except Exception as exc:
        app.logger.error('Unable to start campaign scheduler: %s', exc)


@app.before_request
def launch_scheduler():
    if not scheduler_started:
        start_campaign_scheduler()


# Ensure schema is available before first request
init_db_schema()

# ============================================================
# EMAIL TEMPLATES — Category-Specific Professional Templates
# ============================================================
EMAIL_TEMPLATES = {
    'Developer (GitHub)': {
        'subject': 'Build Something Amazing: Developer Opportunity for {{NAME}}',
        'template': '''Hi {{NAME}},

I hope this message finds you well. I came across your impressive GitHub profile and coding contributions, and I was impressed by your technical expertise and commitment to quality software development.

I wanted to reach out because I think you'd be interested in an exciting opportunity that aligns perfectly with your skills and interests. We're working on cutting-edge projects that challenge developers to push the boundaries of what's possible.

I'd love to discuss how we might collaborate and create something amazing together. Whether you're interested in a full-time role, freelance work, or just exploring new possibilities, I believe there's a great fit here.

Feel free to check out what we're working on:
{{LINK}}

Looking forward to connecting with you!

Best regards,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. Feel free to reply to this email or reach out directly through the link above. No pressure—just genuine interest in connecting with talented developers like yourself!'''
    },
    
    'Web (General)': {
        'subject': 'Exciting Opportunity for {{NAME}}',
        'template': '''Hello {{NAME}},

I hope you're having a great day. I'm reaching out because I believe you'd be a perfect fit for an opportunity we're working on.

After researching your background and online presence, I was impressed by what you're building and your approach to business and growth. Your expertise and perspective would be valuable to our team and projects.

I'd like to invite you to learn more about what we're offering and explore how we might work together. This could be a great opportunity for you to expand your impact and achieve your goals.

Learn more here:
{{LINK}}

I'd love to hear your thoughts. Looking forward to connecting!

Warm regards,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. If you're not interested or this isn't the right time, no worries at all. I hope you'll keep us in mind for the future!'''
    },
    
    'Gaming': {
        'subject': 'Level Up: Gaming Opportunity for {{NAME}}',
        'template': '''Hey {{NAME}}!

I'm reaching out because we're passionate about gaming (just like you!) and we think you'd be an awesome fit for what we're building.

Whether you're a streamer, game developer, esports enthusiast, or content creator, we're creating something exciting that brings the gaming community together. Your energy and passion for gaming make you exactly the kind of person we want to collaborate with.

We're breaking boundaries in gaming, and we'd love to have you on board. Check out what we've got in the works:

{{LINK}}

Let's create something legendary together!

Game on,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. No spam, just real opportunities to grow and connect with the gaming community!'''
    },
    
    'Marketing': {
        'subject': 'Growth Opportunity: Your Marketing Expertise is Needed',
        'template': '''Hi {{NAME}},

I was impressed by your marketing expertise and track record in driving growth. Your strategic thinking and ability to execute campaigns caught my attention, and I believe you'd be perfect for what we're planning.

We're looking to partner with savvy marketing professionals who understand how to build authentic connections with audiences, drive measurable results, and create real impact. Your background suggests you're exactly that kind of professional.

Here's what we're working on:
{{LINK}}

I think you'll find this compelling. Would love to chat about potential collaboration and how we can drive growth together.

Looking forward to hearing from you!

Best,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. Let's connect. Whether you're interested now or want to keep this on your radar for later, I'd value your perspective.'''
    },
    
    'Business': {
        'subject': 'Strategic Partnership Opportunity for {{NAME}}',
        'template': '''Dear {{NAME}},

I hope this message finds you well. I'm reaching out regarding a strategic opportunity that I believe aligns well with your business interests and leadership vision.

We're developing something significant with potential for substantial growth and impact. Your experience in {{CATEGORY}} business, along with your proven track record of success, makes you an ideal partner for this initiative.

I'd welcome the opportunity to discuss this with you at your convenience. I believe there's real potential here, and your insights would be invaluable.

Learn more about the opportunity:
{{LINK}}

Please feel free to reach out if you have any questions or if you'd like to schedule a brief call to discuss further.

Best regards,
{{SENDER_NAME}}
{{SENDER_TITLE}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. This is a time-sensitive opportunity, but there's no pressure. I simply wanted to ensure you were aware of what we're building.'''
    },
    
    'Freelancer': {
        'subject': 'Flexible Opportunity for Talented Freelancer {{NAME}}',
        'template': '''Hi {{NAME}},

I'm reaching out because I've seen your impressive freelance portfolio and I'm impressed by the quality of work you deliver and your entrepreneurial spirit.

We have some exciting, flexible projects coming up that would be perfect for a skilled freelancer like you. Whether you're looking for project-based work, retainer opportunities, or just want to explore what's possible, we think there could be a great fit.

Check out the details:
{{LINK}}

The best part? Complete flexibility. You work on your terms, your timeline, and your way.

Let's explore what we could build together!

Best,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. No long-term commitments required—just quality work with quality people!'''
    },
    
    'Blogger': {
        'subject': 'Content Collaboration Opportunity for {{NAME}}',
        'template': '''Hi {{NAME}},

I love your blog! Your content is genuinely engaging, thoughtful, and resonates with your audience. The way you write about {{CATEGORY}} is exceptional.

I'm reaching out because we're looking to collaborate with talented content creators and bloggers like yourself. We have some exciting ideas around content partnerships, collaborations, and potential monetization opportunities that could be a perfect fit for your platform and audience.

Here's what we've got in mind:
{{LINK}}

I think your audience would love what we're creating, and I know our community would benefit from your unique voice and perspective.

Excited to hear your thoughts!

Best,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. Whether you're interested in a one-off collaboration, ongoing partnership, or just want to chat—I'd love to connect!'''
    },
    
    'Job Seeker': {
        'subject': 'Career Opportunity Perfect for {{NAME}}',
        'template': '''Hi {{NAME}},

I hope you're having a great day! I'm reaching out because we have an exciting career opportunity that I think would be an excellent fit for your background and career goals.

We're growing our team and looking for talented, motivated individuals who are passionate about making an impact. Based on your profile, I believe you have exactly what we're looking for, and I think this could be a great next step in your career journey.

Here are the details:
{{LINK}}

We value enthusiasm, growth mindset, and dedication—which I see clearly in your background. This is a genuine opportunity to grow, learn, and make a real difference.

I'd love to chat with you about this. Feel free to reach out with any questions!

Warm regards,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. We're excited to meet talented people like you! Whether this role is right for you or not, I'd value connecting.'''
    },
    
    'Unknown': {
        'subject': 'Exciting Opportunity for {{NAME}}',
        'template': '''Hello {{NAME}},

I hope this email finds you well. I'm reaching out to introduce you to an exciting opportunity we think could be valuable for you.

We're building something special and we're looking for talented, ambitious people to be part of the journey. Your background and experience suggest you might be a great fit for what we're creating.

I'd like to invite you to learn more and see if this could be a great opportunity for both of us:

{{LINK}}

Looking forward to connecting!

Best regards,
{{SENDER_NAME}}
{{SENDER_EMAIL}}
{{SENDER_PHONE}}

---
P.S. If this isn't the right time or fit, I completely understand. Thanks for considering!'''
    }
}

def render_email_template(category, recipient_name='Friend', link='http://example.com', sender_name='', sender_email='', sender_phone='', sender_title=''):
    """Render an email template with provided values."""
    if category not in EMAIL_TEMPLATES:
        category = 'Unknown'
    
    template = EMAIL_TEMPLATES[category]
    subject = template['subject']
    body = template['template']
    
    # Replace placeholders
    subject = subject.replace('{{NAME}}', recipient_name)
    body = body.replace('{{NAME}}', recipient_name)
    body = body.replace('{{LINK}}', link)
    body = body.replace('{{CATEGORY}}', category)
    body = body.replace('{{SENDER_NAME}}', sender_name or 'Team')
    body = body.replace('{{SENDER_EMAIL}}', sender_email or 'contact@example.com')
    body = body.replace('{{SENDER_PHONE}}', sender_phone or '')
    body = body.replace('{{SENDER_TITLE}}', sender_title or '')
    
    # Clean up extra spaces in phone if not provided
    if not sender_phone:
        body = body.replace('\n\n\n', '\n\n')
    
    return subject, body


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        if email == AUTH_EMAIL and password == AUTH_PASSWORD:
            session['logged_in'] = True
            session['user'] = email
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid login credentials.', 'danger')

    return render_template('login.html', auth_email=AUTH_EMAIL)


@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('user', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/campaign-settings', methods=['GET', 'POST'])
@login_required
def campaign_settings():
    config = get_campaign_config()
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        link1 = request.form.get('link1', '').strip() or DEFAULT_LINK_1
        link2 = request.form.get('link2', '').strip() or DEFAULT_LINK_2
        daily_limit_raw = request.form.get('daily_limit', '').strip()
        try:
            daily_limit = int(daily_limit_raw) if daily_limit_raw else DAILY_EMAIL_LIMIT_DEFAULT
            if daily_limit <= 0:
                raise ValueError()
        except Exception:
            flash('Daily email limit must be a positive integer.', 'danger')
            return redirect(url_for('campaign_settings'))
        if not subject or not body:
            flash('Subject and body are required.', 'danger')
            return redirect(url_for('campaign_settings'))
        update_campaign_config(subject, body, link1, link2, daily_limit)
        flash('Campaign settings saved.', 'success')
        return redirect(url_for('campaign_settings'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS today_sent FROM email_send_log WHERE DATE(sent_at) = CURRENT_DATE() AND status = 'Sent'")
        today_sent = cur.fetchone()['today_sent'] or 0
        cur.execute("SELECT category, COUNT(*) AS count FROM email_send_log WHERE DATE(sent_at) = CURRENT_DATE() AND status = 'Sent' GROUP BY category")
        category_breakdown = {row['category'] or 'Unknown': row['count'] for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) AS pending FROM github_leads WHERE status = 'Pending'")
        pending_count = cur.fetchone()['pending'] or 0
        cur.execute("SELECT COUNT(*) AS sent FROM github_leads WHERE status = 'Sent'")
        sent_count = cur.fetchone()['sent'] or 0
    finally:
        cur.close()
        conn.close()

    return render_template(
        'campaign_settings.html',
        config=config,
        today_sent=today_sent,
        category_breakdown=category_breakdown,
        pending_count=pending_count,
        sent_count=sent_count,
        daily_limit=config.get('daily_limit', DAILY_EMAIL_LIMIT_DEFAULT),
        category_filters=CATEGORY_FILTERS,
        category_badges=CATEGORY_BADGES,
    )


@app.route('/campaign/run-now', methods=['POST'])
@login_required
def campaign_run_now():
    result = run_daily_campaign()
    flash(f"Campaign run complete: {result['sent']} sent of {result['attempted']} attempted.", 'success' if result['sent'] else 'warning')
    return redirect(url_for('campaign_settings'))


@app.route('/')
@login_required
def dashboard():
    selected_category = request.args.get('category', 'all')

    # Load campaign config to get dynamic daily limit
    config = get_campaign_config()
    daily_limit = int(config.get('daily_limit', DAILY_EMAIL_LIMIT_DEFAULT))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute('SELECT COUNT(*) AS total FROM github_leads')
    total = cur.fetchone()['total'] or 0

    cur.execute("SELECT COUNT(*) AS sent FROM github_leads WHERE status = 'Sent'")
    sent = cur.fetchone()['sent'] or 0

    cur.execute("SELECT COUNT(*) AS failed FROM github_leads WHERE status = 'Failed'")
    failed = cur.fetchone()['failed'] or 0

    cur.execute("SELECT COUNT(*) AS pending FROM github_leads WHERE status = 'Pending'")
    pending = cur.fetchone()['pending'] or 0

    cur.execute("SELECT category, COUNT(*) AS count FROM github_leads GROUP BY category")
    counts = {}
    allowed_category_keys = [key for key, _ in CATEGORY_FILTERS if key != 'all']
    for row in cur.fetchall():
        category = row['category'] or 'Unknown'
        if category not in allowed_category_keys:
            category = 'Unknown'
        counts[category] = counts.get(category, 0) + row['count']
    cur.execute("SELECT COUNT(*) AS today_sent FROM email_send_log WHERE DATE(sent_at) = CURRENT_DATE() AND status = 'Sent'")
    today_sent = cur.fetchone()['today_sent'] or 0

    cur.execute("SELECT category, COUNT(*) AS count FROM email_send_log WHERE DATE(sent_at) = CURRENT_DATE() AND status = 'Sent' GROUP BY category")
    category_breakdown = {row['category'] or 'Unknown': row['count'] for row in cur.fetchall()}

    cur.execute("SELECT id, email, category, status, subject, sent_at FROM email_send_log ORDER BY sent_at DESC LIMIT 10")
    recent_send_logs = cur.fetchall()
    category_filters = CATEGORY_FILTERS

    category_counts = {
        key: counts.get(key, 0)
        for key, _ in CATEGORY_FILTERS
        if key != 'all'
    }

    allowed_categories = [value for value, _ in category_filters]
    if selected_category not in allowed_categories:
        selected_category = 'all'

    query = '''
        SELECT id, username, name, email, category, source, status, sent_at, created_at
        FROM github_leads
    '''
    params = []
    if selected_category != 'all':
        query += ' WHERE COALESCE(category, %s) = %s'
        params.extend(['Unknown', selected_category])
    query += ' ORDER BY created_at DESC LIMIT 500'

    cur.execute(query, params)
    leads = cur.fetchall()
    cur.close()
    conn.close()

    # Format datetimes for display
    for l in leads:
        if isinstance(l.get('sent_at'), datetime):
            l['sent_at'] = l['sent_at'].strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(l.get('created_at'), datetime):
            l['created_at'] = l['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        if not l.get('category'):
            l['category'] = 'Uncategorized'

    return render_template(
        'dashboard.html',
        total=total,
        sent=sent,
        failed=failed,
        pending=pending,
        today_sent=today_sent,
        daily_limit=daily_limit,
        category_breakdown=category_breakdown,
        recent_send_logs=recent_send_logs,
        leads=leads,
        selected_category=selected_category,
        category_filters=category_filters,
        category_counts=category_counts,
        category_badges=CATEGORY_BADGES,
    )


@app.route('/template-preview', methods=['GET'])
@login_required
def template_preview():
    """Preview an email template with sample data."""
    category = request.args.get('category', 'Unknown')
    link = request.args.get('link', 'https://example.com')
    sender_name = request.args.get('sender_name', 'Your Company')
    sender_email = request.args.get('sender_email', SENDER_EMAIL)
    sender_phone = request.args.get('sender_phone', '')
    
    allowed_categories = [value for value, _ in CATEGORY_FILTERS if value != 'all']
    if category not in allowed_categories:
        category = 'Unknown'
    
    subject, body = render_email_template(
        category,
        recipient_name='John Doe',
        link=link,
        sender_name=sender_name,
        sender_email=sender_email,
        sender_phone=sender_phone
    )
    
    return render_template(
        'template_preview.html',
        category=category,
        subject=subject,
        body=body,
        link=link,
        sender_name=sender_name,
        sender_email=sender_email,
        sender_phone=sender_phone,
        category_badges=CATEGORY_BADGES,
    )


@app.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    selected_category = request.args.get('category', 'all') if request.method == 'GET' else request.form.get('category', 'all')
    allowed_categories = [value for value, _ in CATEGORY_FILTERS]
    if selected_category not in allowed_categories:
        selected_category = 'all'

    if request.method == 'POST':
        use_template = request.form.get('use_template', 'no') == 'yes'
        selected_category = request.form.get('category', 'all')
        link = request.form.get('link', '').strip()
        sender_name = request.form.get('sender_name', '').strip()
        sender_email_custom = request.form.get('sender_email_custom', '').strip()
        sender_phone = request.form.get('sender_phone', '').strip()

        if selected_category not in allowed_categories:
            selected_category = 'all'

        if use_template:
            if not link:
                flash('Link field is required when using templates.', 'warning')
                return redirect(url_for('compose', category=selected_category))
            
            # Generate subject and body from template
            subject, body = render_email_template(
                selected_category if selected_category != 'all' else 'Unknown',
                recipient_name='Friend',
                link=link,
                sender_name=sender_name,
                sender_email=sender_email_custom or SENDER_EMAIL,
                sender_phone=sender_phone
            )
        else:
            subject = request.form.get('subject', '').strip()
            body = request.form.get('body', '').strip()

            if not subject or not body:
                flash('Subject and body are required.', 'danger')
                return redirect(url_for('compose', category=selected_category))

        conn = get_db_connection()
        cur = conn.cursor()
        query = "SELECT id, email, name FROM github_leads WHERE status = 'Pending'"
        params = []
        if selected_category != 'all':
            query += " AND COALESCE(category, %s) = %s"
            params.extend(['Unknown', selected_category])
        cur.execute(query, params)
        rows = cur.fetchall()

        if not rows:
            flash('No pending leads to send to the selected category.', 'warning')
            cur.close()
            conn.close()
            return redirect(url_for('compose', category=selected_category))

        sent_count = 0
        failed_count = 0

        try:
            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
            else:
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
            server.ehlo()
            if SMTP_USE_TLS and SMTP_PORT != 465:
                server.starttls()
                server.ehlo()
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
        except Exception as exc:
            flash(f'Unable to connect to SMTP server: {exc}', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('compose', category=selected_category))

        for lead_id, email, name in rows:
            try:
                # If using template, personalize with recipient name
                if use_template and name:
                    personalized_subject, personalized_body = render_email_template(
                        selected_category if selected_category != 'all' else 'Unknown',
                        recipient_name=name,
                        link=link,
                        sender_name=sender_name,
                        sender_email=sender_email_custom or SENDER_EMAIL,
                        sender_phone=sender_phone
                    )
                else:
                    personalized_subject = subject
                    personalized_body = body

                msg = EmailMessage()
                msg['Subject'] = personalized_subject
                msg['From'] = SENDER_EMAIL
                msg['To'] = email
                msg.set_content(personalized_body)

                server.send_message(msg)

                cur.execute("UPDATE github_leads SET status='Sent', sent_at=%s WHERE id=%s", (datetime.utcnow(), lead_id))
                conn.commit()
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                app.logger.error('Email failed for %s: %s', email, exc)

        # Do not mark failures as non-pending so they can be retried later.

        cur.close()
        conn.close()
        try:
            server.quit()
        except Exception:
            pass

        flash(f'Emails sent: {sent_count}, failed: {failed_count}', 'success' if sent_count else 'danger')
        return redirect(url_for('dashboard', category=selected_category if selected_category != 'all' else None))

    return render_template(
        'compose.html',
        selected_category=selected_category,
        category_filters=CATEGORY_FILTERS,
        category_badges=CATEGORY_BADGES,
        email_templates=EMAIL_TEMPLATES,
    )


if __name__ == '__main__':
    start_campaign_scheduler()
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=os.getenv('FLASK_DEBUG', '0') in ('1', 'true', 'True'))
