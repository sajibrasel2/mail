<?php
// PHP proxy to the local Flask app running on 127.0.0.1:5000.
$targetHost = '127.0.0.1';
$targetPort = 5000;
$targetUrl = 'http://' . $targetHost . ':' . $targetPort . $_SERVER['REQUEST_URI'];
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
        $responseHeaders = explode("\r\n", trim(substr($rawResponse, 0, $headerSize)));
        $responseBody = substr($rawResponse, $headerSize);
        $responseCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
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
