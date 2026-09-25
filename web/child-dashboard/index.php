<?php
declare(strict_types=1);
if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(403); exit('Local laboratory only');
}
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header("Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");
try {
    $credential = json_decode(file_get_contents('C:/xampp/DRAGONHYDRACHILD/runtime/secrets/child-maria-web.local.json'), true, 16, JSON_THROW_ON_ERROR);
    if (($credential['username'] ?? '') !== 'dragonhydrachild_web') { throw new RuntimeException('Identity boundary'); }
    $db = new mysqli('127.0.0.1', $credential['username'], $credential['password'], 'dragonhydrachild_ops', 3306);
    $db->set_charset('utf8mb4');
    $query = $db->prepare('SELECT payload FROM presentation_cache WHERE cache_key = ?');
    $key = 'child-intelligence'; $query->bind_param('s', $key); $query->execute();
    $row = $query->get_result()->fetch_assoc();
    $data = $row ? json_decode($row['payload'], true, 64, JSON_THROW_ON_ERROR) : ['status'=>'INSUFFICIENT_EVIDENCE'];
    $db->close();
} catch (Throwable $error) {
    http_response_code(503); $data = ['status'=>'DATABASE_FAILURE', 'project'=>'DRAGONHYDRACHILD'];
}
if (($_GET['format'] ?? '') === 'json') {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE); exit;
}
function h(mixed $value): string { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
require_once __DIR__ . '/localai-status.php';
$localai = localai_status();
$analysis = $data['analysis'] ?? [];
$fixture = $analysis['selected_fixture'] ?? [];
?>
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DRAGONHYDRACHILD laboratory</title><link rel="stylesheet" href="dashboard.css"></head><body>
<header><p class="eyebrow">EXPERIMENTAL FULL-ROADMAP FORK · LOCAL LABORATORY</p><h1>DRAGONHYDRACHILD</h1><p class="intro">Evidence from the past. A present knowledge cursor. Probabilities for possible futures.</p><div class="badges"><span>Python 3.14</span><span>Provenance</span><span>Temporal discipline</span><span>Evaluation discipline</span></div></header>
<main>
<section class="hero"><div><p class="eyebrow">SELECTED MATCH</p><h2><?=h(($fixture['home_team'] ?? 'Awaiting analysis').' — '.($fixture['away_team'] ?? ''))?></h2><p><?=h($fixture['match_date'] ?? 'No fixture selected')?> · <?=h($fixture['round'] ?? '')?></p><p class="muted">Source-local kickoff timezone may be unknown. Decision boundaries and reconstruction assumptions remain explicit.</p></div><div id="probability" class="forecast"><h3>Ensemble forecast</h3><div id="probability-bars"></div><p class="muted">Probabilities, not certainty or a wagering instruction.</p></div></section>
<section class="stats"><article><strong><?=h($data['counts']['fixtures']['identities'] ?? 0)?></strong><span>SQL fixture identities</span></article><article><strong><?=h($data['counts']['snapshots']['versions'] ?? 0)?></strong><span>Immutable source snapshots</span></article><article><strong><?=h($analysis['historical_evaluation']['evaluation_matches'] ?? '—')?></strong><span>Historical evaluation matches</span></article><article><strong><?=h($analysis['prospective_prediction']['status'] ?? 'PENDING')?></strong><span>Prospective prediction ledger</span></article></section>
<nav><a href="#evidence">Evidence</a><a href="#features">Features</a><a href="#models">Models</a><a href="#simulation">Simulation</a><a href="#market">Market</a><a href="#uncertainty">Uncertainty</a><a href="#research">Research</a><a href="#heads">HYDRA</a><a href="#history">Evaluation</a></nav>
<div class="grid">
<section id="localai" class="wide"><h2>Local Qwen · analysis only</h2><p class="muted">Last reported state; a heartbeat older than three minutes is marked STALE. AI interpretations are not evidence. No machine controls are exposed.</p><dl><?php foreach ($localai as $name => $value): ?><dt><?=h(str_replace('_', ' ', $name))?></dt><dd><?=h($value)?></dd><?php endforeach; ?></dl></section>
<section id="evidence"><h2>Evidence & time</h2><p><span class="tag">STRICT_PIT capture</span> is distinct from <span class="tag warm">RECONSTRUCTED_PIT history</span>.</p><div id="evidence-view"></div><h3>Canonical identity review</h3><div id="identity-view"></div><h3>Sources and permissions</h3><div id="source-view"></div><h3>External weather hypothesis</h3><div id="weather-view"></div><p class="muted">Weather forecast data, when available: <a href="https://api.met.no/weatherapi/locationforecast/2.0/documentation">MET Norway</a>, <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Display reformatted; London coordinate proxy, not measured stadium weather.</p></section>
<section id="features"><h2>Feature factory</h2><p class="muted">Every snapshot retains input IDs, calculation/code version, availability, units and missingness.</p><div id="feature-view"></div></section>
<section id="models" class="wide"><h2>Math engines & Prediction Tribunal</h2><p class="muted">Simple baselines remain visible. Past-loss weights use only scored history available at the decision cursor.</p><div id="model-view"></div><div id="tribunal-view"></div></section>
<section id="simulation"><h2>Possible scorelines</h2><p class="tag warm">SIMULATION · NOT OBSERVED RESULTS</p><div id="simulation-view"></div></section>
<section id="market"><h2>Odds engineering</h2><p id="market-state" class="notice">No lawful real market snapshot is available. Contract and synthetic arithmetic tests do not close this gap.</p><div id="market-view"></div></section>
<section id="uncertainty"><h2>What remains uncertain?</h2><div id="uncertainty-view"></div><h3>Evidence-based explanation</h3><div id="explanation-view"></div></section>
<section id="research"><h2>Targeted research</h2><p class="muted">Controlled experiments are labelled. Reduced entropy alone does not prove improved accuracy.</p><div id="research-view"></div></section>
<section id="heads" class="wide"><h2>HYDRA logical capabilities</h2><p class="muted">A registry of bounded capabilities; no thirteen-agent theatre. Missing lawful sources remain blocked.</p><div id="head-view"></div></section>
<section id="history" class="wide"><h2>Scientific evaluation</h2><p class="notice">RECONSTRUCTED_PIT · DEMONSTRATION_ONLY · One season cannot establish small predictive differences.</p><div id="history-view"></div><h3>Calibration, sample size and compute</h3><div id="quality-view"></div></section>
<section class="wide"><h2>System health & chain boundaries</h2><div id="health-view"></div><div id="limits-view"></div><details><summary>Inspect the full sanitized presentation payload</summary><pre id="raw-view"></pre></details></section>
</div></main><footer>SQL Server owns structured intelligence. MariaDB holds this presentation cache. Parent DRAGONHYDRA remains read-only.</footer>
<script type="application/json" id="data"><?=json_encode($data, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_INVALID_UTF8_SUBSTITUTE)?></script>
<script>
const data=JSON.parse(document.getElementById('data').textContent), a=data.analysis||{};
function text(node,value){node.textContent=value===null?'UNKNOWN':String(value);}
function view(id,value){const host=document.getElementById(id);if(value===undefined||value===null){host.textContent='INSUFFICIENT_EVIDENCE';return;}if(Array.isArray(value)&&value.length&&value.every(x=>typeof x==='object'&&x!==null)){const keys=[...new Set(value.flatMap(x=>Object.keys(x)))].filter(k=>!['input_evidence','calibration','feature_snapshot','score_matrix'].includes(k));const table=document.createElement('table'),head=document.createElement('tr');for(const k of keys){const th=document.createElement('th');text(th,k.replaceAll('_',' '));head.append(th);}table.append(head);for(const row of value){const tr=document.createElement('tr');for(const k of keys){const td=document.createElement('td');text(td,typeof row[k]==='object'?JSON.stringify(row[k]):row[k]??'—');tr.append(td);}table.append(tr);}host.append(table);}else{const pre=document.createElement('pre');text(pre,JSON.stringify(value,null,2));host.append(pre);}}
view('evidence-view',a.evidence||data.latest_snapshot);view('source-view',a.sources);view('identity-view',a.entity_registry);view('weather-view',a.weather);view('feature-view',a.features);view('model-view',a.models);view('tribunal-view',a.tribunal);view('simulation-view',a.simulation);view('market-view',a.market);view('uncertainty-view',a.uncertainty);view('explanation-view',a.explanation);view('research-view',a.research);view('head-view',a.heads);view('history-view',a.historical_evaluation?.model_results);view('quality-view',{calibration:a.historical_evaluation?.calibration_summary,gpu:a.gpu});view('health-view',{sqlserver:data.sqlserver,mariadb:data.mariadb,built_at:data.built_at,scheduler:a.scheduler,prospective_prediction:a.prospective_prediction});view('limits-view',a.chain_breaks);text(document.getElementById('raw-view'),JSON.stringify(data,null,2));
const probs=a.ensemble?.probabilities||a.ensemble;
if(probs&&typeof probs==='object'){for(const [i,k] of ['HOME','DRAW','AWAY'].entries()){let value=Array.isArray(probs)?probs[i]:probs[k]??probs[k.toLowerCase()];if(typeof value!=='number')continue;const row=document.createElement('div');row.className='bar';const label=document.createElement('span');text(label,k+' '+(value*100).toFixed(1)+'%');const bar=document.createElement('meter');bar.min=0;bar.max=1;bar.value=value;bar.setAttribute('aria-label',k+' probability');row.append(label,bar);document.getElementById('probability-bars').append(row);}}
</script></body></html>
