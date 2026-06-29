import os
import sys
sys.path.insert(0, r'c:\\xampp\\htdocs\\mail')
import general_leads
import requests

urls = [
    'https://github.com/torvalds',
    'https://www.linkedin.com/in/jeffweiner',
    'https://www.reddit.com/user/kn0thing/',
    'https://medium.com/@naval',
]
for url in urls:
    print('URL', url)
    try:
        r = requests.get(url, timeout=20, headers=general_leads._headers())
        print('status', r.status_code)
        print('content-type', r.headers.get('content-type'))
        print(r.text[:800])
        print('---')
    except Exception as exc:
        print('ERR', type(exc).__name__, exc)
        print('---')
