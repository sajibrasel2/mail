<?php
// The Flask app is now deployed through Passenger via passenger_wsgi.py.
// This file is intentionally left minimal to avoid redirecting the browser to localhost.

http_response_code(200);
echo "Phusion Passenger deployment active. If you see this page, the app is not being handled by Passenger yet.";
