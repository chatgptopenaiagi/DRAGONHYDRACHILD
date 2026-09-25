<?php
declare(strict_types=1);
if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(403); exit('Local laboratory only');
}
function cognitive_status(): array {
    $path = 'C:/xampp/DRAGONHYDRACHILD/runtime/cognitive-v2/cockpit.json';
    $fallback = ['status' => 'UNAVAILABLE', 'reason_codes' => ['NO_COGNITIVE_SNAPSHOT']];
    if (!is_file($path) || filesize($path) > 65536) { return $fallback; }
    try {
        $data = json_decode(file_get_contents($path), true, 16, JSON_THROW_ON_ERROR);
        $fields = ['schema_version', 'status', 'created_at', 'observed_at', 'state_hash',
            'cognitive', 'machine', 'world', 'deltas', 'memory', 'security', 'metrics', 'reason_codes'];
        if (!is_array($data) || array_diff(array_keys($data), $fields) || ($data['schema_version'] ?? '') !== '2') { return $fallback; }
        $serialized = json_encode($data, JSON_THROW_ON_ERROR);
        if (preg_match('/"(?:password|api_key|access_token|authorization|cookie|chain_of_thought|reasoning_content|raw_commandline)"\s*:/i', $serialized)
            || preg_match('/(?:password|passwd|api[_ -]?key|access[_ -]?token)\s*[=:]|Bearer\s+[A-Za-z0-9]|-----BEGIN.*PRIVATE KEY|sk-proj-/i', $serialized)) {
            return ['status' => 'INVALID_CONTEXT', 'reason_codes' => ['UNTRUSTED_CONTEXT']];
        }
        $stamp = strtotime($data['observed_at'] ?? '');
        $age = $stamp ? time() - $stamp : null;
        $data['machine_snapshot_age_seconds'] = $age;
        if ($age === null || $age > 60 || $age < -30) {
            $data['status'] = 'STALE';
            $data['reason_codes'][] = 'MACHINE_STATE_STALE';
        }
        return $data;
    } catch (Throwable $error) { return $fallback; }
}
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    echo json_encode(cognitive_status(), JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE);
}
