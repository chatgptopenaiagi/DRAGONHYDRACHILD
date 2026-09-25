# Fixed, read-only ARX probe. No model text is accepted as an instruction.
param([ValidateRange(0,2147483647)][int]$OwnedTestPid = 0)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$rows = [System.Collections.Generic.List[object]]::new()
$domains = [System.Collections.Generic.List[object]]::new()
function Add-Row($kind, $id, $attributes) { $rows.Add(@{kind=$kind; entity_id=$id; attributes=$attributes}) }
function Probe($id, [scriptblock]$body) {
    $before = $rows.Count
    try { & $body; $domains.Add(@{probe_id=$id;status='OK';failure_state=$null}) }
    catch {
        while ($rows.Count -gt $before) { $rows.RemoveAt($rows.Count - 1) }
        $domains.Add(@{probe_id=$id;status='FAILED';failure_state='MACHINE_PROBE_FAILED'})
    }
}
Probe 'os' {
    $os = Get-CimInstance Win32_OperatingSystem
    Add-Row 'os' 'os.windows' @{name=$os.Caption;version=$os.Version;build=$os.BuildNumber;architecture=$os.OSArchitecture;boot_time=$os.LastBootUpTime.ToUniversalTime().ToString('o');uptime_seconds=[long]((Get-Date).ToUniversalTime()-$os.LastBootUpTime.ToUniversalTime()).TotalSeconds}
}
Probe 'cpu' {
    $i=0
    foreach ($cpu in @(Get-CimInstance Win32_Processor | Select-Object -First 8)) {
        Add-Row 'cpu' "cpu.$i" @{name=$cpu.Name.Trim();cores=[int]$cpu.NumberOfCores;logical_processors=[int]$cpu.NumberOfLogicalProcessors;load_percent=$cpu.LoadPercentage}; $i++
    }
    if ($i -eq 0) { throw 'EMPTY' }
}
Probe 'ram' {
    $os = Get-CimInstance Win32_OperatingSystem
    Add-Row 'ram' 'ram.system' @{total_bytes=[long]$os.TotalVisibleMemorySize*1024;available_bytes=[long]$os.FreePhysicalMemory*1024}
}
Probe 'process' {
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='llama-server.exe' OR Name='ollama.exe' OR Name='ollama_llama_server.exe' OR Name='codex.exe' OR Name='httpd.exe' OR Name='mysqld.exe' OR Name='sqlservr.exe' OR Name='python.exe' OR Name='LocalAI.ObserverService.exe' OR Name='LocalAI.BrokerService.exe' OR Name='LocalAI.QwenService.exe' OR Name='LocalAI.SentinelService.exe' OR ProcessId=$OwnedTestPid" | Where-Object {
        $_.Name -ne 'python.exe' -or $_.ProcessId -eq $OwnedTestPid -or $_.CommandLine -match '(?:scripts[/\\]localai_service\.py| -m dragonhydra\.localai)(?:\s|$)'
    })
    if ($processes.Count -gt 256) { throw 'BOUND' }
    foreach ($p in $processes) {
        if ($p.ProcessId -eq 0) { continue }
        $model = $null; $port = $null; $bind = $null
        # Only recognized fixed flags/identities leave this probe; never the command line.
        if ($p.CommandLine -match '(?:Qwen3-Coder-30B-A3B-Instruct-Q4_K_M|--model\s+qwen3-coder-30b)') { $model='QWEN_30B' }
        elseif ($p.CommandLine -match '(?:Qwen3-4B-Q4_K_M|--model\s+qwen3-4b)') { $model='QWEN_4B' }
        if ($p.Name -eq 'llama-server.exe') {
            if ($p.CommandLine -match '(?:--port|-p)\s+(\d{1,5})(?:\s|$)') { $port=[int]$Matches[1] }
            if ($p.CommandLine -match '--host\s+(127\.0\.0\.1|0\.0\.0\.0|localhost|::1)(?:\s|$)') { $bind=$Matches[1] }
        }
        $start=$p.CreationDate.ToUniversalTime().ToString('o')
        Add-Row 'process' "process.$($p.ProcessId)" @{pid=[int]$p.ProcessId;name=$p.Name;start_time=$start;model_id=$model;port=$port;bind_address=$bind;owned_experiment=($OwnedTestPid -gt 0 -and $p.ProcessId -eq $OwnedTestPid)}
    }
}
Probe 'service' {
    foreach ($s in @(Get-CimInstance Win32_Service | Where-Object {$_.Name -match '^(Apache2\.4|mysql|MariaDB|MSSQLSERVER|SQLSERVERAGENT|MSSQL\$[^\\]+|LocalAI[^\\]*)$'} | Select-Object -First 64)) {
        Add-Row 'service' ('service.'+$s.Name.Replace('$','_')) @{name=$s.Name.Replace('$','_');state=$s.State;start_mode=$s.StartMode;pid=[int]$s.ProcessId}
    }
}
Probe 'listener' {
    $ports = @(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalAddress -in @('127.0.0.1','::1','0.0.0.0','::')} | Sort-Object LocalAddress,LocalPort,OwningProcess -Unique)
    if ($ports.Count -gt 192) { throw 'BOUND' }
    foreach ($p in $ports) {
        $exposure = if ($p.LocalAddress -in @('127.0.0.1','::1')) {'LOOPBACK'} else {'ALL_INTERFACES'}
        Add-Row 'listener' ('listener.'+$p.LocalAddress.Replace(':','_')+'.'+$p.LocalPort+'.'+$p.OwningProcess) @{address=$p.LocalAddress;port=[int]$p.LocalPort;pid=[int]$p.OwningProcess;exposure=$exposure}
    }
}
Probe 'tool' {
    foreach ($name in @('node','git','codex','ollama','docker','wsl','pwsh')) {
        $tool=Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        $ver=$null
        if ($tool -and $tool.Version) { $ver=$tool.Version.ToString() }
        Add-Row 'tool' "tool.$name" @{name=$name;available=[bool]$tool;version=$ver;runtime_id=$null}
    }
    $fixed=@(
        @('canonical-python','C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe'),
        @('python314','C:\Python314\python.exe'),
        @('python315','C:\Users\Administrator\AppData\Local\Programs\Python\Python315\python.exe'),
        @('python314-32','C:\Users\Administrator\AppData\Local\Programs\Python\Python314-32\python.exe'),
        @('python39-vs','C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe'),
        @('php','C:\xampp\php\php.exe'),
        @('apache','C:\xampp\apache\bin\httpd.exe'),
        @('llama-b10665','C:\LocalAI\runtime\llama-b10665\llama-server.exe')
    )
    foreach ($entry in $fixed) {
        $exists=Test-Path -LiteralPath $entry[1] -PathType Leaf
        $ver=if ($exists) { (Get-Item -LiteralPath $entry[1]).VersionInfo.FileVersion } else {$null}
        Add-Row 'tool' ('tool.'+$entry[0]) @{name=$entry[0];available=$exists;version=$ver;runtime_id=$(if ($entry[0] -eq 'llama-b10665') {'b10665'} else {$null})}
    }
}
Probe 'task' {
    $task=Get-ScheduledTask -TaskName 'DRAGONHYDRACHILD-Prospective' -ErrorAction Stop
    $info=$task | Get-ScheduledTaskInfo
    Add-Row 'task' 'task.child-prospective' @{name='DRAGONHYDRACHILD-Prospective';state=$task.State.ToString();last_result=[long]$info.LastTaskResult;last_run=$info.LastRunTime.ToUniversalTime().ToString('o');next_run=$info.NextRunTime.ToUniversalTime().ToString('o')}
}
Probe 'conda_environment' {
    $envroot='C:\Users\Administrator\anaconda3\envs'
    if (-not (Test-Path -LiteralPath $envroot -PathType Container)) { throw 'MISSING' }
    $i=0
    foreach ($item in @(Get-ChildItem -LiteralPath $envroot -Directory | Select-Object -First 32)) {
        if ($item.Name -match '^[A-Za-z0-9_.-]{1,64}$') {
            Add-Row 'conda_environment' ('conda.'+$item.Name) @{name=$item.Name;available=$true}; $i++
        }
    }
}
@{schema_version='2';rows=@($rows);domains=@($domains)} | ConvertTo-Json -Depth 8 -Compress
