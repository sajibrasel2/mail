import sys
sys.path.insert(0, 'c:/xampp/htdocs/mail')
import general_leads

for url in ['https://github.com/torvalds', 'https://www.linkedin.com/in/jeffweiner']:
    print('URL', url)
    emails = general_leads._emails_from_url(url)
    print('emails', sorted(emails)[:10])
