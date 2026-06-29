import sys
sys.path.insert(0, r'c:\\xampp\\htdocs\\mail')
import general_leads

urls = [
    'https://github.com/torvalds',
    'https://www.linkedin.com/in/jeffweiner',
    'https://www.reddit.com/user/kn0thing/',
    'https://medium.com/@naval',
]

for url in urls:
    print('URL', url)
    try:
        emails = general_leads._emails_from_url(url)
        print('emails', sorted(emails)[:20])
    except Exception as exc:
        print('ERR', type(exc).__name__, exc)
    print('---')
