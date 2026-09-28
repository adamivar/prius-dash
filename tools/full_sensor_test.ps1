& {
    # ===== Prius Gen 3 FULL sensor test =====
    # 1) Reads every READ request from the ZVW30 PID spreadsheet (+ standard OBD ones) once, parked.
    # 2) Asks you to do things (brake, A/C, lights...) and re-reads the related requests to see what changes.
    # Only read requests (mode 01 / 21) are sent - nothing here changes any car setting.
    $ComPort = 'COM6'
    $Baud    = 38400
    $Requests = @(
        @('7E2','0100','Supported standard PIDs 01-20'),
        @('7E2','0140','Supported standard PIDs 41-60'),
        @('7E2','015B','State of Charge'),
        @('7E2','2101','Calculated Load_7E2, Manifold Air Pressure_7E2, Intake Air Temperature'),
        @('7E2','2121','CCS Vehicle Spd, CCS Mem Vehicle Spd, Cruise Operation Status +4 more'),
        @('7E2','2141','Shift Sensor Main, Shift Sensor Sub, Shift Sensor Select Main +4 more'),
        @('7E2','2161','MG1 temperature, MG1 temperature after IG-ON, MG1 temperature Max +1 m'),
        @('7E2','2162','MG2 temperature, MG2 temperature after IG-ON, MG2 temperature Max +1 m'),
        @('7E2','2167','MG1 torque, MG1 torque execution value, MG1 Control Mode'),
        @('7E2','2168','MG2 torque, MG2 torque execution value, MG2 Control Mode'),
        @('7E2','2170','Inverter MG1 Temp, Inverter MG1 Temp after IG-ON, Inverter MG1 Temp Ma'),
        @('7E2','2171','Inverter MG2 Temp, Inverter MG2 Temp after IG-ON, Inverter MG2 Temp Ma'),
        @('7E2','2174','Boost converter temperature, Boost converter temperature after IG-ON, '),
        @('7E2','2175','Prohibit DC/DC converter signal, Aircon Gate Status, Water Pump Runnin'),
        @('7E2','2178','MG1 Inverter Shutdown, MG1 Inverter Fail, MG2 Inverter Shutdown +1 mor'),
        @('7E2','2179','DCDC Cnv Target Pulse Duty, Water Pump Run Control Duty, Converter Shu'),
        @('7E2','217C','MG1 Carrier Frequency, MG2 Carrier Frequency'),
        @('7E2','217D','Boost Ratio, Converter Carrier Frequency, A/C consumption power'),
        @('7E2','2181','Battery Block Voltage -V01, Battery Block Voltage -V02, Battery Block '),
        @('7E2','2187','HV battery intake air temperature, Temp of Batt TB1, Temp of Batt TB2 '),
        @('7E2','218A','Power Resource IB'),
        @('7E2','218E','Cooling Fan 0, Cooling Fan Relay Status'),
        @('7E2','2192','Battery block minimum voltage, Battery block number with minimum volta'),
        @('7E2','2195','Internal Resistance R01, Internal Resistance R02, Internal Resistance '),
        @('7E2','2198','Batt Pack Current Val, HV battery charge control, HV battery discharge'),
        @('7E2','219B','ECU Control Mode, Cooling Fan Mode 1, Standby Blower Request Status +1'),
        @('7E2','21C1','Model Code_7E2, Engine Code, Destination'),
        @('7E2','21C2','ECU Code'),
        @('7E2','21E1','Number of Current Code, Number of History Code'),
        @('7E0','0100','Supported standard PIDs 01-20'),
        @('7E0','0105','Coolant temp'),
        @('7E0','010B','Manifold pressure'),
        @('7E0','010C','Engine RPM'),
        @('7E0','0120','Supported standard PIDs 21-40'),
        @('7E0','0132','Fuel tank vapour pressure'),
        @('7E0','0133','Barometric pressure'),
        @('7E0','013C','Catalyst temp'),
        @('7E0','0104','Engine load (standard OBD)'),
        @('7E0','0106','Short-term fuel trim (standard OBD)'),
        @('7E0','0107','Long-term fuel trim (standard OBD)'),
        @('7E0','010D','Vehicle speed (standard OBD)'),
        @('7E0','010E','Ignition timing (standard OBD)'),
        @('7E0','010F','Intake air temp (standard OBD)'),
        @('7E0','0110','Air flow (standard OBD)'),
        @('7E0','0111','Throttle position (standard OBD)'),
        @('7E0','0115','Rear oxygen sensor B1S2 voltage (standard OBD)'),
        @('7E0','011F','Run time since start (standard OBD)'),
        @('7E0','0121','Distance with check-engine light on (standard OBD)'),
        @('7E0','012C','Commanded EGR (standard OBD)'),
        @('7E0','012E','Commanded evap purge (standard OBD)'),
        @('7E0','0130','Warm-ups since codes cleared (standard OBD)'),
        @('7E0','0131','Distance since codes cleared (standard OBD)'),
        @('7E0','0134','Front air-fuel sensor lambda B1S1 (standard OBD)'),
        @('7E0','013E','Catalyst temp B1S2 (standard OBD)'),
        @('7E0','0142','Engine computer supply voltage (standard OBD)'),
        @('7E0','0143','Absolute engine load (standard OBD)'),
        @('7E0','0144','Commanded air-fuel ratio lambda (standard OBD)'),
        @('7E0','0145','Relative throttle position (standard OBD)'),
        @('7E0','0147','Throttle position B (standard OBD)'),
        @('7E0','014C','Commanded throttle actuator (standard OBD)'),
        @('7E0','014D','Minutes with check-engine light on (standard OBD)'),
        @('7E0','014E','Minutes since codes cleared (standard OBD)'),
        @('7E0','0140','Supported standard PIDs 41-60'),
        @('7E0','0160','Supported standard PIDs 61-80'),
        @('7E0','2101','Calculated Load_7E0, Vehicle Load, Mass Air Flow +7 more'),
        @('7E0','2103','Fuel System Status #1, Short FT #1, Long FT #1 +1 more'),
        @('7E0','2104','Target Air-Fuel Ratio, AF Lambda B1S1, AFS Voltage B1S1'),
        @('7E0','2106','MIL'),
        @('7E0','2124','Communication with HV, Communication with Brake, Comm with Air Conditi'),
        @('7E0','2137','Initial Engine Coolant Temp, Initial Intake Air Temp'),
        @('7E0','213C','Injection volume, Injection duration for cylinder 1, Total FT #1'),
        @('7E0','2144','VVT Aim Angle #1, VVT OCV Duty #1, VVT Change Angle #1'),
        @('7E0','2145','Misfire RPM, Misfire Load, Cylinder #1 Misfire Count +5 more'),
        @('7E0','2147','EGR Step Position'),
        @('7E0','2149','Requested Engine Torque, HV Target Engine Speed, Actual Engine Torque '),
        @('7E0','2154','Engine Speed of Cyl #1, Engine Speed of Cyl #2, Engine Speed of Cyl #3'),
        @('7E0','21C1','Model Code_7E0, Engine Type, Cylinder Number +3 more'),
        @('7B0','2103','FR Wheel Speed, FL Wheel Speed, RR Wheel Speed +1 more'),
        @('7B0','2105','Deceleration Sensor, Deceleration Sensor2'),
        @('7B0','2106','Yaw Rate Sensor, Yaw Rate Sensor2, Steering Angle Sensor'),
        @('7B0','2107','Wheel Cylinder Pressure Sensor'),
        @('7B0','211D','Reservoir Warning SW, Main Idle SW'),
        @('7B0','211F','Stop Light SW, Parking Brake SW'),
        @('7B0','2121','Vehicle Speed_7B0'),
        @('7B0','213C','Stop Light Relay Output'),
        @('7B0','213D','ABS Warning Light, Brake Warning Light, Slip Indicator Light +2 more'),
        @('7B0','2142','FR Wheel Acceleration, FL Wheel Acceleration, RR Wheel Acceleration +1'),
        @('7B0','2146','Zero Point of Decele, Zero Point of Decele2, Zero Point of Yaw Rate +1'),
        @('7B0','2147','Lateral G, Forward and Rearward G, Yaw Rate Value +1 more'),
        @('7B0','2148','FR Regenerative Request, FR Regenerative Operation'),
        @('7B0','2158','Regen Cooperation'),
        @('7B0','215A','TRC(TRAC) Ctrl Status, TRC(TRAC) Engine Ctrl Status, TRC(TRAC) Brake C'),
        @('7B0','215F','FR Wheel ABS Ctrl Status, FL Wheel ABS Ctrl Status, RR Wheel ABS Ctrl '),
        @('7B0','21A1','Zero Point of Yaw Rate2'),
        @('7B0','21A3','SLA Solenoid Current, SLR Solenoid Current, SSC Solenoid Current +3 mo'),
        @('7B0','21A6','Inspection Mode'),
        @('7B0','21BC','Hazard Switch History'),
        @('7B0','21BE','FR Speed Open, FL Speed Open, RR Speed Open +9 more'),
        @('7C0','2112','Tail Cancel SW, P-Seatbelt Buckle SW, Check Engine SW +1 more'),
        @('7C0','2113','+B Voltage Value'),
        @('7C0','2121','Vehicle Speed Meter_7C0'),
        @('7C0','2123','Coolant Temperature_7C0'),
        @('7C0','2129','Fuel Input'),
        @('7C0','2141','Distance Since Oil Change for U.S.A.'),
        @('7C0','2168','Rheostat value'),
        @('7C0','21A1','Key Remind Sound'),
        @('7C0','21A7','Seat Belt Beep Query'),
        @('7C0','21AC','Reverse Beep Query'),
        @('7C4','2121','Room Temp Sensor'),
        @('7C4','2122','Ambient Temp Sensor'),
        @('7C4','2124','Solar Sensor'),
        @('7C4','2126','Engine Coolant Temp_7C4'),
        @('7C4','2129','Set Temperature'),
        @('7C4','213C','Blower Motor Speed Level'),
        @('7C4','213D','Adjusted Ambient Temp'),
        @('7C4','2141','Air Mix Servo Targ Pulse, Air Mix Servo Actual Pulse'),
        @('7C4','2143','Air Outlet Servo Pulse, Air Outlet Servo Actu Pulse'),
        @('7C4','2144','Air Inlet Damper Targ Pulse, Air Inlet Damper Actual Pulse'),
        @('7C4','2149','Compressor Speed'),
        @('7C4','214A','Compressor Target Speed'),
        @('7C4','214B','Evaporator Fin Thermistor'),
        @('7C4','214C','Evaporator Target Temp'),
        @('7C4','2153','Regulator Pressure Sensor')
    )
    $Log   = New-Object System.Collections.Generic.List[string]
    $Base  = @{}                        # "7E2 2161" -> data bytes from the parked baseline
    $State = @{ Hdr = ''; Rx = ''; T0 = [Diagnostics.Stopwatch]::StartNew() }
    $Names = @{}; foreach ($r in $Requests) { $Names["$($r[0]) $($r[1])"] = $r[2] }
    function Get-Letter([int]$i) { if ($i -lt 26) { [string][char](65 + $i) } else { 'A' + [char](65 + $i - 26) } }
    function Send-Elm([string]$cmd, [int]$timeoutMs = 3000) {
        $sp.DiscardInBuffer()
        $sp.Write("$cmd`r")
        $sb = New-Object System.Text.StringBuilder
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ($sw.ElapsedMilliseconds -lt $timeoutMs) {
            $s = $sp.ReadExisting()
            if ($s) { [void]$sb.Append($s); if ($s.Contains('>')) { break } } else { Start-Sleep -Milliseconds 5 }
        }
        [pscustomobject]@{ Text = $sb.ToString().Replace('>', '').Trim(); Ms = $sw.ElapsedMilliseconds }
    }
    function Set-Header([string]$h) {
        if ($State.Hdr -eq $h) { return }
        $rx = '{0:X3}' -f ([Convert]::ToInt32($h, 16) + 8)       # Toyota replies come from request + 8
        $a = Send-Elm "ATSH$h"
        $b = Send-Elm "ATCRA$rx"                                   # only listen to that computer's replies
        $Log.Add("HEADER|$h|reply $rx|ATSH: $(($a.Text -replace '\s+', ' '))|ATCRA: $(($b.Text -replace '\s+', ' '))")
        $State.Hdr = $h; $State.Rx = $rx
    }
    function Read-Pid([string]$h, [string]$code) {
        Set-Header $h
        $r = Send-Elm $code 3000
        $flat = ($r.Text -replace '\s+', ' ').Trim()
        $bytes = New-Object System.Collections.Generic.List[int]; $len = -1
        foreach ($line in ($r.Text -split "[\r\n]+")) {
            $tok = $line.Trim() -split '\s+'
            if ($tok.Count -lt 2 -or $tok[0] -ne $State.Rx) { continue }
            $b = @(); for ($i = 1; $i -lt $tok.Count; $i++) { try { $b += [Convert]::ToInt32($tok[$i], 16) } catch {} }
            if ($b.Count -eq 0) { continue }
            $t = $b[0] -shr 4
            if ($t -eq 0) { $len = $b[0] -band 0xF; for ($i = 1; $i -lt $b.Count; $i++) { $bytes.Add($b[$i]) } }
            elseif ($t -eq 1) { $len = (($b[0] -band 0xF) * 256) + $b[1]; for ($i = 2; $i -lt $b.Count; $i++) { $bytes.Add($b[$i]) } }
            elseif ($t -eq 2) { for ($i = 1; $i -lt $b.Count; $i++) { $bytes.Add($b[$i]) } }
        }
        if ($len -ge 0 -and $bytes.Count -gt $len) { $bytes.RemoveRange($len, $bytes.Count - $len) }
        $mode = [Convert]::ToInt32($code.Substring(0, 2), 16); $pb = [Convert]::ToInt32($code.Substring(2, 2), 16)
        $data = ''
        if ($bytes.Count -ge 2 -and $bytes[0] -eq ($mode + 0x40) -and $bytes[1] -eq $pb) {
            $status = 'OK'
            $data = (@($bytes | Select-Object -Skip 2) | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
        }
        elseif ($bytes.Count -ge 3 -and $bytes[0] -eq 0x7F) { $status = ('REFUSED {0:X2}' -f $bytes[2]) }
        elseif ($flat -match 'NO DATA') { $status = 'NO DATA' }
        elseif ($flat -eq '' ) { $status = 'NO REPLY' }
        else { $status = 'ODD REPLY' }
        [pscustomobject]@{ Status = $status; Data = $data; Raw = $flat; Ms = $r.Ms }
    }
    function Save-Result([string]$step, [string]$h, [string]$code, $r) {
        $Log.Add(('{0}|{1:N1}s|{2}|{3}|{4}|{5}|raw: {6}' -f $step, ($State.T0.ElapsedMilliseconds / 1000), $h, $code,
                  $r.Status, $r.Data, $r.Raw))
    }
    function Compare-Data([string]$before, [string]$after) {
        if (-not $before -or -not $after) { return @() }
        $x = $before -split ' '; $y = $after -split ' '
        $out = @()
        for ($i = 0; $i -lt [Math]::Min($x.Count, $y.Count); $i++) {
            if ($x[$i] -ne $y[$i]) { $out += ('{0}:{1}>{2}' -f (Get-Letter $i), $x[$i], $y[$i]) }
        }
        return $out
    }
    function Do-Step([string]$name, [string]$instruction, [string[]]$reqs, [int]$reads = 3) {
        Write-Host ''
        Write-Host "=== $name ===" -ForegroundColor Cyan
        Write-Host $instruction -ForegroundColor Yellow
        $ans = Read-Host 'Press Enter when ready (or type S + Enter to skip)'
        if ($ans -match '^[sS]') { $Log.Add("$name|SKIPPED"); Write-Host '  skipped'; return }
        $changes = @{}; $last = @{}
        for ($n = 1; $n -le $reads; $n++) {
            foreach ($rq in $reqs) {
                $h, $code = $rq -split ' '
                $r = Read-Pid $h $code
                Save-Result $name $h $code $r
                $last[$rq] = $r.Status
                foreach ($c in (Compare-Data $Base[$rq] $r.Data)) { $changes["$rq|$($c.Split(':')[0])"] = $c }
            }
            Start-Sleep -Milliseconds 300
        }
        foreach ($rq in $reqs) {
            $c = @($changes.Keys | Where-Object { $_ -like "$rq|*" } | ForEach-Object { $changes[$_] })
            $colour = if ($c.Count) { 'Green' } elseif ($last[$rq] -eq 'OK') { 'Gray' } else { 'DarkYellow' }
            $what = if ($c.Count) { 'CHANGED ' + ($c -join ' ') } elseif ($last[$rq] -eq 'OK') { 'no change' } else { $last[$rq] }
            $nm = [string]$Names[$rq]; Write-Host ('  {0}  {1,-40} {2}' -f $rq, $nm.Substring(0, [Math]::Min(40, $nm.Length)), $what) -ForegroundColor $colour
        }
    }
    function Do-Timed([string]$name, [string]$instruction, [string[]]$reqs, [int]$seconds) {
        Write-Host ''
        Write-Host "=== $name ===" -ForegroundColor Cyan
        Write-Host $instruction -ForegroundColor Yellow
        $ans = Read-Host 'Press Enter to START recording (or type S + Enter to skip)'
        if ($ans -match '^[sS]') { $Log.Add("$name|SKIPPED"); Write-Host '  skipped'; return }
        [console]::Beep(880, 300)
        $sw = [Diagnostics.Stopwatch]::StartNew(); $n = 0
        while ($sw.Elapsed.TotalSeconds -lt $seconds) {
            foreach ($rq in $reqs) { $h, $code = $rq -split ' '; Save-Result $name $h $code (Read-Pid $h $code) }
            $n++
        }
        [console]::Beep(880, 200); Start-Sleep -Milliseconds 120; [console]::Beep(1320, 400)
        Write-Host "  recorded $n rounds in $seconds s - done, you can stop the car" -ForegroundColor Green
    }

    $sp = New-Object System.IO.Ports.SerialPort $ComPort, $Baud, 'None', 8, 'One'
    try {
        $sp.Open()
        $Log.Add("=== Prius FULL sensor test $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') on $ComPort ===")
        foreach ($c in 'ATZ', 'ATE0', 'ATL0', 'ATS1', 'ATH1', 'ATSP6') {
            $r = Send-Elm $c 5000; $Log.Add("INIT|$c|$(($r.Text -replace '\s+', ' '))")
        }
        # ---------- part 1: everything once, parked ----------
        Write-Host ''
        Write-Host "PART 1: car in READY, in PARK, don't touch anything. Reading all $($Requests.Count) requests (about 30 s)..." -ForegroundColor Cyan
        [void](Read-Host 'Press Enter to start')
        $i = 0; $count = @{}
        foreach ($rq in $Requests) {
            $i++
            $r = Read-Pid $rq[0] $rq[1]
            Save-Result 'BASELINE' $rq[0] $rq[1] $r
            $Base["$($rq[0]) $($rq[1])"] = $r.Data
            $key = "$($rq[0]) $($r.Status -replace ' [0-9A-F]{2}$', '')"; $count[$key] = 1 + [int]$count[$key]
            $n = if ($r.Data) { ($r.Data -split ' ').Count } else { 0 }
            Write-Host ('  [{0,2}/{1}] {2} {3}  {4,-10} {5,3} bytes  {6}' -f $i, $Requests.Count, $rq[0], $rq[1], $r.Status, $n, $rq[2]) `
                -ForegroundColor $(if ($r.Status -eq 'OK') { 'Green' } else { 'DarkYellow' })
        }
        Write-Host ''
        Write-Host 'Baseline summary (computer / result / how many):' -ForegroundColor Cyan
        $count.Keys | Sort-Object | ForEach-Object { Write-Host ('  {0,-14} {1}' -f $_, $count[$_]) }

        # ---------- part 2: do things and watch what changes ----------
        Write-Host ''
        Write-Host 'PART 2: I will ask you to do things. Green CHANGED = that reading reacted. Type S to skip any step.' -ForegroundColor Cyan
        $climate = @('7C4 2121','7C4 2122','7C4 2124','7C4 2126','7C4 2129','7C4 213C','7C4 213D','7C4 2141','7C4 2143',
                     '7C4 2144','7C4 2149','7C4 214A','7C4 214B','7C4 214C','7C4 2153','7E2 217D','7E2 2175')
        $meter = @($Requests | Where-Object { $_[0] -eq '7C0' } | ForEach-Object { "$($_[0]) $($_[1])" })
        Do-Step 'BRAKE PEDAL' 'Press and HOLD the brake pedal firmly until this step finishes.' `
            @('7B0 211F','7B0 213C','7B0 2107','7B0 2148','7B0 213D')
        Do-Step 'PARKING BRAKE' 'Release the brake pedal. Now SET the parking brake (foot pedal).' @('7B0 211F','7B0 213D','7C0 2112')
        Do-Step 'A/C COLD' 'Release the parking brake. Turn the A/C ON, temperature COLDEST, fan HIGH. Wait 20 seconds.' $climate
        Do-Step 'HEATER HOT' 'Now A/C OFF, temperature HOTTEST, fan HIGH. Wait 20 seconds.' $climate
        Do-Step 'HEADLIGHTS' 'Turn the climate back to normal. Turn the HEADLIGHTS ON.' $meter
        Do-Step 'ENGINE RUNNING (standard OBD)' ('Lights off. Stay in PARK. Press the gas pedal about HALFWAY so ' +
            'the engine runs, and hold.') @('7E0 0104','7E0 0106','7E0 0107','7E0 010D','7E0 010E','7E0 010F','7E0 0110','7E0 0111','7E0 0115','7E0 011F','7E0 0121','7E0 012C','7E0 012E','7E0 0130','7E0 0131','7E0 0134','7E0 013E','7E0 0142','7E0 0143','7E0 0144','7E0 0145','7E0 0147','7E0 014C','7E0 014D','7E0 014E') 3
        Do-Step 'GAS PEDAL IN PARK' 'Lights off. Stay in PARK. Press the gas pedal about HALFWAY and hold (the engine may start).' `
            @('7E2 2101','7E2 2141','7E0 2101','7E0 2103','7E0 2149','7E0 010C','7E2 2161','7E2 2167') 4
        Do-Step 'STEERING LEFT' 'Let go of the gas. Turn the steering wheel all the way LEFT and hold.' @('7B0 2106','7B0 2146','7B0 2147')
        Do-Step 'STEERING RIGHT' 'Now turn it all the way RIGHT and hold.' @('7B0 2106','7B0 2146','7B0 2147')
        Do-Step 'REVERSE GEAR' 'Straighten the wheel. Foot on the brake, shift to REVERSE (R) and stay stopped.' `
            @('7E2 2141','7E2 2162','7B0 211F','7C0 21AC')
        Do-Step 'CRUISE BUTTON' ('Shift back to PARK and make sure the car is in READY. Press the cruise control ON ' +
            'button (end of the cruise lever) and check the cruise light comes on in the dash.') @('7E2 2121')
        Do-Step 'PASSENGER SEATBELT' 'Buckle the PASSENGER seat belt (or unbuckle it if it was buckled).' @('7C0 2112')
        Do-Timed 'SLOW DRIVE (optional)' ("ONLY in a safe, empty place. After you press Enter, put the laptop down, drive slowly`n" +
            "(under 20 km/h), then brake gently to a stop. It records for 30 seconds and beeps at the start and the end.`n" +
            "Don't look at the laptop while moving. Type S to skip if it's not safe right now.") `
            @('7B0 2103','7B0 2121','7B0 2148','7B0 2147','7B0 2142','7E2 2101','7E2 2162','7E2 2168','7E2 218A','7C0 2121','7E0 2101') 30
    }
    catch { $Log.Add("ERROR|$($_.Exception.Message)"); Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red }
    finally {
        if ($sp.IsOpen) { $sp.Close() }
        $file = Join-Path ([Environment]::GetFolderPath('Desktop')) ("prius_fulltest_{0}.txt" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
        $Log | Out-File -FilePath $file -Encoding utf8
        Write-Host ''
        Write-Host "Saved log to: $file" -ForegroundColor Green
        Write-Host 'Tell Claude the test is done - it can read the log from your Desktop.' -ForegroundColor Green
    }
}
Read-Host "Press Enter to exit"
