<#
.SYNOPSIS
    AIS Relay — pure PowerShell, no Python required.

.DESCRIPTION
    Connects to Boat Beacon's NMEA TCP server on your LAN and POSTs the raw
    lines to the River Watch VM over HTTPS. No router port-forward, no static
    IP, no TCP listener on the VM — just outbound HTTPS.

    Works on Windows 10/11 PowerShell 5.1+ and PowerShell 7+.

.PARAMETER UserMmsi
    Your vessel's MMSI (required for GPS to be attributed to your vessel).

.PARAMETER BoatName
    Your vessel's display name (optional).

.PARAMETER BoatBeaconIp
    LAN IP of the device running Boat Beacon's TCP server. Default: 192.168.0.25

.PARAMETER BoatBeaconPort
    TCP port Boat Beacon listens on. Default: 5353

.PARAMETER VmUrl
    HTTPS base URL of the River Watch VM. Default: https://mississippi-kiosk.preview.emergentagent.com

.PARAMETER BatchSeconds
    How often (seconds) to flush buffered NMEA lines to the VM. Default: 1

.PARAMETER MaxBatchLines
    Max lines per POST. Default: 200

.EXAMPLE
    .\ais_relay.ps1 -UserMmsi 367123450 -BoatName "MY BOAT"

.EXAMPLE
    .\ais_relay.ps1 -UserMmsi 367123450 -BoatBeaconIp 192.168.0.30 -BoatBeaconPort 4001
#>
[CmdletBinding()]
param(
    [string]$UserMmsi       = $env:USER_MMSI,
    [string]$BoatName       = $env:BOAT_NAME,
    [string]$BoatBeaconIp   = $(if ($env:BOAT_BEACON_IP)   { $env:BOAT_BEACON_IP }   else { "192.168.0.25" }),
    [int]   $BoatBeaconPort = $(if ($env:BOAT_BEACON_PORT) { [int]$env:BOAT_BEACON_PORT } else { 5353 }),
    [string]$VmUrl          = $(if ($env:VM_URL)           { $env:VM_URL }           else { "https://mississippi-kiosk.preview.emergentagent.com" }),
    [double]$BatchSeconds   = $(if ($env:BATCH_SECONDS)    { [double]$env:BATCH_SECONDS } else { 1.0 }),
    [int]   $MaxBatchLines  = $(if ($env:MAX_BATCH_LINES)  { [int]$env:MAX_BATCH_LINES }  else { 200 })
)

$ErrorActionPreference = "Stop"
$VmUrl = $VmUrl.TrimEnd('/')
$IngestUrl = "$VmUrl/api/ais/ingest"

function Write-Log([string]$msg) {
    $ts = (Get-Date).ToString("HH:mm:ss")
    Write-Host "[$ts] $msg"
}

Write-Log ("=" * 56)
Write-Log "AIS NMEA Relay -> HTTP POST (PowerShell)"
Write-Log ("=" * 56)
Write-Log "  Boat Beacon : ${BoatBeaconIp}:${BoatBeaconPort}"
Write-Log "  VM ingest   : $IngestUrl"
Write-Log ("  USER_MMSI   : " + $(if ($UserMmsi) { $UserMmsi } else { '(unset - pass -UserMmsi for GPS attribution)' }))
Write-Log ("  BOAT_NAME   : " + $(if ($BoatName) { $BoatName } else { '(unset)' }))
Write-Log "  Batch       : every ${BatchSeconds}s, up to $MaxBatchLines lines"
Write-Log ("=" * 56)
Write-Log "Press Ctrl+C to stop."
Write-Log ""

# Force TLS 1.2 on Windows PowerShell 5.x (some Win10 boxes default lower)
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

# Shared buffer (thread-safe via lock object)
$buffer = New-Object System.Collections.Generic.List[string]
$lock   = New-Object Object
$stats  = [pscustomobject]@{
    LinesRead     = 0
    BatchesSent   = 0
    LinesSent     = 0
    Errors        = 0
    LastDataTime  = $null
    LastPostTime  = $null
    StartTime     = (Get-Date)
}

function Send-Batch([System.Collections.Generic.List[string]]$lines) {
    $body = @{
        user_mmsi = $UserMmsi
        boat_name = $BoatName
        lines     = @($lines)
    } | ConvertTo-Json -Compress

    try {
        $resp = Invoke-RestMethod -Uri $IngestUrl -Method Post `
            -ContentType "application/json" `
            -Body $body -TimeoutSec 15
        $stats.BatchesSent++
        $stats.LinesSent += $lines.Count
        $stats.LastPostTime = Get-Date
        if ($stats.BatchesSent -le 3 -or ($stats.BatchesSent % 60) -eq 0) {
            Write-Log ("POST -> 200  accepted={0}/{1}  total_sent={2}" -f $resp.accepted, $resp.received, $stats.LinesSent)
        }
        return $true
    }
    catch {
        $stats.Errors++
        Write-Log ("POST FAILED: " + $_.Exception.Message)
        return $false
    }
}

# Connect to Boat Beacon and stream lines into the shared buffer
$client = $null
$stream = $null
$reader = $null
$lastFlush = Get-Date

try {
    while ($true) {
        if (-not $client -or -not $client.Connected) {
            try {
                Write-Log "Connecting to Boat Beacon @ ${BoatBeaconIp}:${BoatBeaconPort} ..."
                $client = New-Object System.Net.Sockets.TcpClient
                $client.ReceiveTimeout = 30000
                $client.SendTimeout    = 10000
                $iar = $client.BeginConnect($BoatBeaconIp, $BoatBeaconPort, $null, $null)
                if (-not $iar.AsyncWaitHandle.WaitOne(10000)) {
                    throw "Boat Beacon connect timeout after 10s"
                }
                $client.EndConnect($iar)
                $stream = $client.GetStream()
                $stream.ReadTimeout = 30000
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::ASCII)
                Write-Log "Boat Beacon connected. Streaming NMEA..."
            }
            catch {
                $stats.Errors++
                Write-Log ("Boat Beacon connect failed: " + $_.Exception.Message + "  - retrying in 5s")
                Start-Sleep -Seconds 5
                continue
            }
        }

        # Read one line (blocks up to ReadTimeout)
        try {
            $line = $reader.ReadLine()
            if ($null -eq $line) {
                Write-Log "Boat Beacon closed the connection."
                try { $client.Close() } catch {}
                $client = $null
                Start-Sleep -Seconds 2
                continue
            }
            $line = $line.Trim()
            if ($line.Length -gt 0) {
                [System.Threading.Monitor]::Enter($lock)
                try {
                    $buffer.Add($line) | Out-Null
                    $stats.LinesRead++
                    $stats.LastDataTime = Get-Date
                    if ($stats.LinesRead -le 5) {
                        Write-Log ("NMEA: " + $line.Substring(0, [Math]::Min(90, $line.Length)))
                    }
                } finally { [System.Threading.Monitor]::Exit($lock) }
            }
        }
        catch [System.IO.IOException] {
            # Read timeout / connection reset — reconnect
            $stats.Errors++
            Write-Log ("Read error: " + $_.Exception.Message + " - reconnecting")
            try { $client.Close() } catch {}
            $client = $null
            Start-Sleep -Seconds 2
            continue
        }

        # Time to flush?
        $age = ((Get-Date) - $lastFlush).TotalSeconds
        if ($age -ge $BatchSeconds) {
            $toSend = $null
            [System.Threading.Monitor]::Enter($lock)
            try {
                if ($buffer.Count -gt 0) {
                    $take = [Math]::Min($buffer.Count, $MaxBatchLines)
                    $toSend = New-Object System.Collections.Generic.List[string]
                    for ($i = 0; $i -lt $take; $i++) { $toSend.Add($buffer[$i]) | Out-Null }
                    $buffer.RemoveRange(0, $take)
                }
            } finally { [System.Threading.Monitor]::Exit($lock) }

            if ($toSend -and $toSend.Count -gt 0) {
                $ok = Send-Batch $toSend
                if (-not $ok) {
                    # Put it back at the front so we don't lose lines
                    [System.Threading.Monitor]::Enter($lock)
                    try { $buffer.InsertRange(0, $toSend) } finally { [System.Threading.Monitor]::Exit($lock) }
                    Start-Sleep -Seconds 2
                }
            }
            $lastFlush = Get-Date

            # Periodic status line
            if ($stats.BatchesSent -gt 0 -and ($stats.BatchesSent % 30) -eq 0) {
                $uptime = (Get-Date) - $stats.StartTime
                Write-Log ("status uptime={0:hh\:mm\:ss} read={1} sent={2} batches={3} errors={4}" -f `
                    $uptime, $stats.LinesRead, $stats.LinesSent, $stats.BatchesSent, $stats.Errors)
            }
        }
    }
}
finally {
    if ($reader) { try { $reader.Dispose() } catch {} }
    if ($stream) { try { $stream.Dispose() } catch {} }
    if ($client) { try { $client.Close()  } catch {} }
    Write-Log ("Relay stopped. read={0} sent={1} batches={2} errors={3}" -f `
        $stats.LinesRead, $stats.LinesSent, $stats.BatchesSent, $stats.Errors)
}
