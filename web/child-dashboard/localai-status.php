<?php
declare(strict_types=1);
// Read-only bounded presentation artifact. No API token or inference/control route.
if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(403); exit('Local laboratory only');
}
function localai_status(): array {
    $path = 'C:/xampp/DRAGONHYDRACHILD/runtime/localai/status.json';
    $fallback = ['status' => 'UNAVAILABLE', 'adapter_state' => 'UNKNOWN'];
    if (!is_file($path) || filesize($path) > 8192) { return $fallback; }
    try {
        $record = json_decode(file_get_contents($path), true, 8, JSON_THROW_ON_ERROR);
        $allowed = ['status', 'model_id', 'model_hash_abbreviation', 'runtime_id', 'checked_at',
            'execution_mode', 'last_success_at', 'last_latency_ms', 'request_count', 'last_failure', 'adapter_state'];
        $result = [];
        foreach ($allowed as $name) {
            if (isset($record[$name]) && (is_string($record[$name]) || is_numeric($record[$name]))) {
                $result[$name] = is_string($record[$name]) ? substr($record[$name], 0, 120) : $record[$name];
            }
        }
        $stamp = strtotime($result['checked_at'] ?? '');
        if (!$stamp || time() - $stamp > 180 || $stamp > time() + 30) { $result['status'] = 'STALE'; }
        return $result;
    } catch (Throwable $error) { return $fallback; }
}
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    echo json_encode(localai_status(), JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE);
}
