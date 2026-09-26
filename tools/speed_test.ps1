& {
    # ===== Prius adapter SPEED test =====
    # A) times the same questions with 5 different adapter settings (and checks the replies stay complete)
    # B) times switching between the car's computers
    # C) just LISTENS to the car's network (no questions) to see what it broadcasts by itself
    # Only read requests and adapter (AT) settings are sent - nothing changes any car setting.
    $ComPort = 'COM6'
    $Baud    = 38400
    $Reps    = 8
    $Tests = @(   # computer, question, what it is
        @('7E2','218A','battery current (short reply)'),
        @('7E2','2161','generator rpm (short reply)'),
        @('7E2','2101','hybrid summary (4-frame reply)'),
        @('7E2','2181','14 battery blocks (6-frame reply)'),
        @('7E0','010C','engine rpm (standard)'),
        @('7B0','2103','wheel speeds (brake computer)'),
        @('7C4','2149','A/C compressor (climate computer)')
    )
    $Configs = @(
        @{ Name = '1 now: spaces+headers';         Init = @('ATS1','ATH1','ATAT1'); Suffix = '' },
        @{ Name = '2 + expect-1-reply';            Init = @('ATS1','ATH1','ATAT1'); Suffix = '1' },
        @{ Name = '3 no spaces/headers';           Init = @('ATS0','ATH0','ATAT1'); Suffix = '' },
        @{ Name = '4 no spaces/headers + expect-1'; Init = @('ATS0','ATH0','ATAT1'); Suffix = '1' },
        @{ Name = '5 = 4 + fast timing (ATAT2)';   Init = @('ATS0','ATH0','ATAT2'); Suffix = '1' }
    )
    $Log = New-Object System.Collections.Generic.List[string]
    $State = @{ Hdr = '' }
    function Send-Elm([string]$cmd, [int]$timeoutMs = 3000) {
        $sp.DiscardInBuffer()
        $sp.Write("$cmd`r")
        $sb = New-Object System.Text.StringBuilder
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ($sw.ElapsedMilliseconds -lt $timeoutMs) {
            $s = $sp.ReadExisting()
            if ($s) { [void]$sb.Append($s); if ($s.Contains('>')) { break } } else { Start-Sleep -Milliseconds 1 }
        }
        [pscustomobject]@{ Text = $sb.ToString().Replace('>', '').Trim(); Ms = $sw.Elapsed.TotalMilliseconds }
    }
    function Set-Header([string]$h, [bool]$cra = $true) {
        if ($State.Hdr -eq $h) { return }
        [void](Send-Elm "ATSH$h")
        if ($cra) { [void](Send-Elm ('ATCRA{0:X3}' -f ([Convert]::ToInt32($h, 16) + 8))) } else { [void](Send-Elm 'ATAR') }
        $State.Hdr = $h
    }
    # Count the data bytes in a reply (works with or without spaces/headers). Returns -1 if no usable reply.
    function Count-Bytes([string]$text, [bool]$headers) {
        $bytes = 0; $len = -1; $got = $false
        foreach ($line in ($text -split "[\r\n]+")) {
            $l = ($line -replace '\s', '').ToUpper()
            if ($l -eq '' -or $l -match 'NODATA|ERROR|STOPPED|\?|SEARCHING|BUFFER') { continue }
            if ($headers) {
                if ($l.Length -lt 5) { continue }
                $hex = $l.Substring(3)
                $pci = [Convert]::ToInt32($hex.Substring(0, 1), 16)
                if ($pci -eq 0) { $len = [Convert]::ToInt32($hex.Substring(1, 1), 16); $bytes += ($hex.Length - 2) / 2 }
                elseif ($pci -eq 1) { $len = [Convert]::ToInt32($hex.Substring(1, 3), 16); $bytes += ($hex.Length - 4) / 2 }
                elseif ($pci -eq 2) { $bytes += ($hex.Length - 2) / 2 }
                $got = $true
            }
            else {
                if ($l -match '^[0-9A-F]{3}$') { $len = [Convert]::ToInt32($l, 16); $got = $true }
                elseif ($l -match '^[0-9A-F]:(.*)$') { $bytes += $Matches[1].Length / 2; $got = $true }
                elseif ($l -match '^[0-9A-F]+$') { $bytes += $l.Length / 2; $got = $true }
            }
        }
        if (-not $got) { return -1 }
        if ($len -ge 0 -and $bytes -gt $len) { $bytes = $len }
        return [int]$bytes
    }
    function Listen([string]$name, [int]$seconds, [string]$filter) {
        # filter '' = everything; otherwise only one message ID (3 hex digits)
        foreach ($c in 'ATH1', 'ATS1') { [void](Send-Elm $c) }
        if ($filter) { [void](Send-Elm "ATCRA$filter") } else { [void](Send-Elm 'ATAR') }
        $State.Hdr = ''
        $sp.DiscardInBuffer()
        $sp.Write("ATMA`r")
        $sb = New-Object System.Text.StringBuilder
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ($sw.Elapsed.TotalSeconds -lt $seconds) {
            $s = $sp.ReadExisting(); if ($s) { [void]$sb.Append($s) } else { Start-Sleep -Milliseconds 2 }
        }
        $sp.Write("x")                                   # any character stops monitoring
        $stop = [Diagnostics.Stopwatch]::StartNew()
        while ($stop.ElapsedMilliseconds -lt 3000) {
            $s = $sp.ReadExisting(); if ($s) { [void]$sb.Append($s); if ($s.Contains('>')) { break } } else { Start-Sleep -Milliseconds 5 }
        }
        $lines = @($sb.ToString() -split "[\r\n]+" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -ne '>' })
        $frames = @($lines | Where-Object { $_ -match '^[0-9A-F]{3} ' })
        $full = @($lines | Where-Object { $_ -match 'BUFFER FULL' }).Count
        $ids = @{}; foreach ($f in $frames) { $id = $f.Substring(0, 3); $ids[$id] = 1 + [int]$ids[$id] }
        $rate = [Math]::Round($frames.Count / [Math]::Max(0.1, $seconds), 1)
        $Log.Add("LISTEN|$name|filter=$filter|seconds=$seconds|frames=$($frames.Count)|per_sec=$rate|buffer_full=$full|ids=$($ids.Count)")
        $keep = 0; foreach ($l in $lines) { if ($keep -lt 4000) { $Log.Add("MON|$name|$l"); $keep++ } }
        Write-Host ('  {0,-34} {1,6} messages ({2,6}/s)  {3,3} different IDs  {4}' -f $name, $frames.Count, $rate, $ids.Count,
            $(if ($full) { 'BUFFER FULL x' + $full } else { '' })) -ForegroundColor $(if ($full) { 'DarkYellow' } else { 'Green' })
        [void](Send-Elm 'ATAR')
        return $ids
    }

    $sp = New-Object System.IO.Ports.SerialPort $ComPort, $Baud, 'None', 8, 'One'
    try {
        $sp.Open()
        $Log.Add("=== Prius SPEED test $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') on $ComPort ===")
        foreach ($c in 'ATZ', 'ATE0', 'ATL0', 'ATSP6') { $r = Send-Elm $c 5000; $Log.Add("INIT|$c|$(($r.Text -replace '\s+', ' '))") }
        Write-Host ''
        Write-Host 'Car in READY, in PARK, not touching anything. About 2 minutes total.' -ForegroundColor Cyan
        [void](Read-Host 'Press Enter to start')

        # ---------- A: same questions, 5 adapter settings ----------
        Write-Host ''
        Write-Host 'PART A - average time per question (ms), and whether replies stay complete' -ForegroundColor Cyan
        $expected = @{}
        foreach ($cfg in $Configs) {
            foreach ($c in $cfg.Init) { [void](Send-Elm $c) }
            $headers = $cfg.Init -contains 'ATH1'
            $State.Hdr = ''
            $all = @()
            $line = '  {0,-32}' -f $cfg.Name
            foreach ($t in $Tests) {
                Set-Header $t[0]
                $times = @(); $bad = 0
                for ($i = 0; $i -lt $Reps; $i++) {
                    $r = Send-Elm ($t[1] + $cfg.Suffix) 3000
                    $n = Count-Bytes $r.Text $headers
                    $key = "$($t[0]) $($t[1])"
                    if (-not $expected.ContainsKey($key) -and $n -gt 0) { $expected[$key] = $n }
                    $ok = $n -gt 0 -and $n -eq $expected[$key]
                    if (-not $ok) { $bad++ }
                    $times += $r.Ms
                    $Log.Add(('TIME|{0}|{1}|{2}|{3:N1}|bytes={4}|{5}|raw: {6}' -f $cfg.Name, $t[0], $t[1], $r.Ms, $n,
                              $(if ($ok) { 'complete' } else { 'INCOMPLETE' }), ($r.Text -replace '\s+', ' ')))
                }
                $avg = ($times | Measure-Object -Average).Average; $all += $times
                $line += ('{0,6:N0}{1}' -f $avg, $(if ($bad) { '!' } else { ' ' }))
            }
            $total = ($all | Measure-Object -Average).Average
            Write-Host ($line + ('  | avg {0,4:N0} ms' -f $total))
        }
        Write-Host ('  {0,-32}{1}' -f 'columns:', (($Tests | ForEach-Object { $_[1] }) -join '   '))
        Write-Host '  ! = some replies came back incomplete or empty with that setting' -ForegroundColor DarkYellow
        foreach ($c in 'ATS1', 'ATH1', 'ATAT1') { [void](Send-Elm $c) }

        # ---------- B: cost of switching computers ----------
        Write-Host ''
        Write-Host 'PART B - switching between two computers (hybrid <-> brake), 10 round trips' -ForegroundColor Cyan
        foreach ($mode in @($true, $false)) {
            $State.Hdr = ''; $ok = 0
            $sw = [Diagnostics.Stopwatch]::StartNew()
            for ($i = 0; $i -lt 10; $i++) {
                foreach ($t in @(@('7E2', '218A'), @('7B0', '2103'))) {
                    Set-Header $t[0] $mode
                    $r = Send-Elm $t[1] 3000
                    if ((Count-Bytes $r.Text $true) -gt 0) { $ok++ }
                }
            }
            $name = if ($mode) { 'switch with reply filter (ATSH+ATCRA)' } else { 'switch without reply filter (ATSH+ATAR)' }
            $per = $sw.Elapsed.TotalMilliseconds / 20
            $Log.Add(('SWITCH|{0}|{1:N1} ms per question incl. switch|{2}/20 answered' -f $name, $per, $ok))
            Write-Host ('  {0,-42} {1,5:N0} ms per question   {2}/20 answered' -f $name, $per, $ok)
        }
        [void](Send-Elm 'ATAR'); $State.Hdr = ''

        # ---------- C: just listen ----------
        Write-Host ''
        Write-Host "PART C - just LISTENING to the car's network (no questions)" -ForegroundColor Cyan
        $idsQuiet = Listen 'everything, parked' 3 ''
        [void](Read-Host 'Now press and HOLD the brake pedal, then press Enter (keep holding ~3 s)')
        $idsBrake = Listen 'everything, brake held' 3 ''
        Write-Host '  (you can let go of the brake)'
        $top = @($idsQuiet.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 4 | ForEach-Object { $_.Key })
        $cands = @('03B', '3CB', '0B4', '244', '2C4', '030', '3C8', '520') + $top | Select-Object -Unique
        foreach ($id in $cands) { [void](Listen "only ID $id" 2 $id) }
    }
    catch { $Log.Add("ERROR|$($_.Exception.Message)"); Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red }
    finally {
        if ($sp.IsOpen) { try { $sp.Write("x`r"); Start-Sleep -Milliseconds 200; $sp.Write("ATAR`r") } catch {}; $sp.Close() }
        $file = Join-Path ([Environment]::GetFolderPath('Desktop')) ("prius_speedtest_{0}.txt" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
        $Log | Out-File -FilePath $file -Encoding utf8
        Write-Host ''
        Write-Host "Saved log to: $file" -ForegroundColor Green
        Write-Host 'Tell Claude the speed test is done - it can read the log from your Desktop.' -ForegroundColor Green
    }
}
Read-Host "Press Enter to exit"
