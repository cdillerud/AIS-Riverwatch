<#
.SYNOPSIS
    River Watch NMEA Relay - HTTPS push (via nginx on port 80).

.DESCRIPTION
    Reads NMEA from Boat Beacon's TCP server on the LAN and POSTs the lines
    to the VM's nginx-proxied /api/ais/ingest endpoint. Uses port 80, which
    is already open on the GCP firewall - no firewall changes needed.

.PARAMETER BoatBeaconIp     LAN IP of Boat Beacon. Default: 192.168.0.25
.PARAMETER BoatBeaconPort   Boat Beacon TCP port. Default: 5353
.PARAMETER VmUrl            Base URL of your VM. Default: http://34.172.47.153
.PARAMETER BatchSeconds     Flush interval (seconds). Default: 1
.PARAMETER MaxBatchLines    Max lines per POST. Default: 200
#>
[CmdletBinding()]
param(
    [string]$BoatBeaconIp   = $(if ($env:BOAT_BEACON_IP)   { $env:BOAT_BEACON_IP }   else { "192.168.0.25" }),
    [int]   $BoatBeaconPort = $(if ($env:BOAT_BEACON_PORT) { [int]$env:BOAT_BEACON_PORT } else { 5353 }),
    [string]$VmUrl          = $(if ($env:VM_URL)           { $env:VM_URL }           else { "http://34.172.47.153" }),
    [double]$BatchSeconds   = $(if ($env:BATCH_SECONDS)    { [double]$env:BATCH_SECONDS } else { 1.0 }),
    [int]   $MaxBatchLines  = $(if ($env:MAX_BATCH_LINES)  { [int]$env:MAX_BATCH_LINES }  else { 200 })
)

$ErrorActionPreference = "Stop"
$VmUrl = $VmUrl.TrimEnd('/')
$IngestUrl = "$VmUrl/api/ais/ingest"

function Write-Log([string]$msg) {
    Write-Host ("[" + (Get-Date).ToString("HH:mm:ss") + "] " + $msg)
}

Write-Log ("=" * 60)
Write-Log "River Watch NMEA Relay (HTTPS push)"
Write-Log ("=" * 60)
Write-Log "  Boat Beacon : ${BoatBeaconIp}:${BoatBeaconPort}"
Write-Log "  VM ingest   : $IngestUrl"
Write-Log ("=" * 60)
Write-Log "Press Ctrl+C to stop."
Write-Log ""

try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$buffer = New-Object System.Collections.Generic.List[string]
$lock   = New-Object Object
$stats  = [pscustomobject]@{
    LinesRead = 0; BatchesSent = 0; LinesSent = 0; Errors = 0
    LastDataTime = $null; LastPostTime = $null; StartTime = (Get-Date)
}

function Send-Batch([System.Collections.Generic.List[string]]$lines) {
    $body = @{ lines = @($lines) } | ConvertTo-Json -Compress
    try {
        $resp = Invoke-RestMethod -Uri $IngestUrl -Method Post `
            -ContentType "application/json" -Body $body -TimeoutSec 15
        $stats.BatchesSent++
        $stats.LinesSent += $lines.Count
        $stats.LastPostTime = Get-Date
        if ($stats.BatchesSent -le 3 -or ($stats.BatchesSent % 30) -eq 0) {
            Write-Log ("POST -> 200  accepted={0}/{1}  total_sent={2}" -f $resp.accepted, $resp.received, $stats.LinesSent)
        }
        return $true
    } catch {
        $stats.Errors++
        Write-Log ("POST FAILED: " + $_.Exception.Message)
        return $false
    }
}

$client = $null; $stream = $null; $reader = $null
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
                if (-not $iar.AsyncWaitHandle.WaitOne(10000)) { throw "Boat Beacon connect timeout after 10s" }
                $client.EndConnect($iar)
                $stream = $client.GetStream()
                $stream.ReadTimeout = 30000
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::ASCII)
                Write-Log "Boat Beacon connected. Streaming NMEA..."
            } catch {
                $stats.Errors++
                Write-Log ("Boat Beacon connect failed: " + $_.Exception.Message + "  - retrying in 5s")
                Start-Sleep -Seconds 5
                continue
            }
        }

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
        } catch [System.IO.IOException] {
            $stats.Errors++
            Write-Log ("Read error: " + $_.Exception.Message + " - reconnecting")
            try { $client.Close() } catch {}
            $client = $null
            Start-Sleep -Seconds 2
            continue
        }

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
                    [System.Threading.Monitor]::Enter($lock)
                    try { $buffer.InsertRange(0, $toSend) } finally { [System.Threading.Monitor]::Exit($lock) }
                    Start-Sleep -Seconds 2
                }
            }
            $lastFlush = Get-Date
        }
    }
} finally {
    foreach ($d in @($reader, $stream, $client)) { if ($d) { try { $d.Dispose() } catch {} } }
    Write-Log ("Relay stopped. read={0} sent={1} batches={2} errors={3}" -f `
        $stats.LinesRead, $stats.LinesSent, $stats.BatchesSent, $stats.Errors)
}
