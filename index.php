<?php
// PHP proxy to the local Flask app running on 127.0.0.1:5000.
$targetHost = '127.0.0.1';
$targetPort = 5000;
$basePath = '/mail';
$requestUri = $_SERVER['REQUEST_URI'];
$forwardPath = preg_replace('#^' . preg_quote($basePath, '#') . '#', '', $requestUri, 1);
if ($forwardPath === '' || $forwardPath[0] !== '/') {
    $forwardPath = '/' . ltrim($forwardPath, '/');
}
$targetUrl = 'http://' . $targetHost . ':' . $targetPort . $forwardPath;
$method = $_SERVER['REQUEST_METHOD'];
$body = file_get_contents('php://input');
$headers = [];
foreach (getallheaders() as $name => $value) {
    if (strtolower($name) === 'host') {
        continue;
    }
    if (is_array($value)) {
        foreach ($value as $v) {
            $headers[] = $name . ': ' . $v;
        }
    } else {
        $headers[] = $name . ': ' . $value;
    }
}
$headers[] = 'Host: ' . $targetHost;

// Add X-Forwarded headers so Flask (with ProxyFix) can reconstruct original URL
$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$headers[] = 'X-Forwarded-Host: ' . ($_SERVER['HTTP_HOST'] ?? $targetHost);
$headers[] = 'X-Forwarded-Proto: ' . $scheme;
$headers[] = 'X-Forwarded-Prefix: ' . $basePath;
$headers[] = 'X-Forwarded-For: ' . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');

$responseBody = '';
$responseHeaders = [];
$responseCode = 502;

if (function_exists('curl_init')) {
    $ch = curl_init($targetUrl);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 5);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);

    if ($method !== 'GET' && $method !== 'HEAD') {
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    }

    $rawResponse = curl_exec($ch);
    if ($rawResponse !== false) {
        $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $rawHeaders = trim(substr($rawResponse, 0, $headerSize));
        $responseHeaders = explode("\r\n", $rawHeaders);
        $responseBody = substr($rawResponse, $headerSize);
        $responseCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);

        // Rewrite Location headers that reference localhost/127.0.0.1 back to public path
        foreach ($responseHeaders as &$hdr) {
            if (stripos($hdr, 'Location:') === 0) {
                $loc = trim(substr($hdr, strlen('Location:')));
                $hdr = 'Location: ' . rewrite_location_header($loc);
            }
        }
        unset($hdr);
    } else {
        $responseBody = 'Proxy error: ' . curl_error($ch);
    }
    curl_close($ch);
} else {
    $contextOptions = [
        'http' => [
            'method' => $method,
            'header' => implode("\r\n", $headers),
            'content' => $body,
            'ignore_errors' => true,
            'timeout' => 30,
        ],
    ];
    $context = stream_context_create($contextOptions);
    $responseBody = @file_get_contents($targetUrl, false, $context);
    if ($responseBody !== false && isset($http_response_header)) {
        $responseHeaders = $http_response_header;
        preg_match('#HTTP/\d+\.\d+\s+(\d+)#', $http_response_header[0], $matches);
        $responseCode = isset($matches[1]) ? intval($matches[1]) : 200;

        // Rewrite Location headers in the stream wrapper headers
        foreach ($responseHeaders as &$hdr) {
            if (stripos($hdr, 'Location:') === 0) {
                $loc = trim(substr($hdr, strlen('Location:')));
                $hdr = 'Location: ' . rewrite_location_header($loc);
            }
        }
        unset($hdr);
    } else {
        $responseBody = 'Proxy error: unable to connect to ' . $targetHost . ':' . $targetPort;
    }
}

http_response_code($responseCode);
foreach ($responseHeaders as $headerLine) {
    if (stripos($headerLine, 'Transfer-Encoding:') === 0) {
        continue;
    }
    if (stripos($headerLine, 'Content-Length:') === 0) {
        continue;
    }
    if (stripos($headerLine, 'HTTP/') === 0) {
        continue;
    }
    header($headerLine, false);
}

echo $responseBody;


// Helper to rewrite Location headers from local addresses to public path
function rewrite_location_header($location) {
    if (empty($location)) return $location;
    $location = trim($location);
    $parsed = parse_url($location);
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? null;

    // If absolute URL pointing to localhost or 127.0.0.1, map to public host + basePath
    if (isset($parsed['host']) && preg_match('#^(127\.0\.0\.1|localhost)$#', $parsed['host'])) {
        $path = $parsed['path'] ?? '/';
        $query = isset($parsed['query']) ? ('?' . $parsed['query']) : '';
        if ($host) {
            return $scheme . '://' . $host . $GLOBALS['basePath'] . $path . $query;
        }
        return $GLOBALS['basePath'] . $path . $query;
    }

    // If it's a root-relative path and not already prefixed, add the basePath
    if (isset($location[0]) && $location[0] === '/' && strpos($location, $GLOBALS['basePath']) !== 0) {
        return $GLOBALS['basePath'] . $location;
    }

    return $location;
}
