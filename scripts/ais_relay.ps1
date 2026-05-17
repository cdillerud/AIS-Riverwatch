<#
.SYNOPSIS
    River Watch NMEA Relay - TCP forwarder.

.DESCRIPTION
    Reads NMEA from Boat Beacon's TCP server on the LAN and pushes the raw
    bytes straight into the ais-relay container's :6000 ingest port on the
    GCP VM. This matches the architecture shown in the dashboard's
    "AIS Feed Scanner" panel: push-relay mode.

    Boat Beacon (LAN)   192.168.0.25:5353
            ||
            \/   pure TCP forward, no parsing
    ais-relay container 136.116.165.255:6000
            ||
            \/
    backend container  ais-relay:5353 (internal)
            ||
            \/
    dashboard

.PARAMETER BoatBeaconIp     LAN IP of Boat Beacon. Default: 192.168.0.25
.PARAMETER BoatBeaconPort   Boat Beacon TCP port.   Default: 5353
.PARAMETER VmHost           Public VM hostname/IP.  Default: 136.116.165.255
.PARAMETER VmPort           Relay ingest TCP port.  Default: 6000
#>
[CmdletBinding()]
param(
    [string]$BoatBeaconIp   = $(if ($env:BOAT_BEACON_IP)   { $env:BOAT_BEACON_IP }   else { "192.168.0.25" }),
    [int]   $BoatBeaconPort = $(if ($env:BOAT_BEACON_PORT) { [int]$env:BOAT_BEACON_PORT } else { 5353 }),
    [string]$VmHost         = $(if ($env:VM_HOST)          { $env:VM_HOST }          else { "136.116.165.255" }),
    [int]   $VmPort         = $(if ($env:VM_PORT)          { [int]$env:VM_PORT }     else { 6000 })
)

$ErrorActionPreference = "Stop"

function Write-Log([string]$msg) {
    Write-Host ("[" + (Get-Date).ToString("HH:mm:ss") + "] " + $msg)
}

Write-Log ("=" * 60)
Write-Log "River Watch NMEA Relay (TCP forwarder)"
Write-Log ("=" * 60)
Write-Log "  Boat Beacon : ${BoatBeaconIp}:${BoatBeaconPort}"
Write-Log "  Ingest port : ${VmHost}:${VmPort}"
Write-Log ("=" * 60)
Write-Log "Press Ctrl+C to stop."
Write-Log ""

$stats = [pscustomobject]@{ Bytes = 0; Lines = 0; Errors = 0; Start = (Get-Date); LastLine = $null }

while ($true) {
    $bbClient = $null; $bbStream = $null; $bbReader = $null
    $vmClient = $null; $vmStream = $null; $vmWriter = $null
    try {
        Write-Log "Connecting to Boat Beacon @ ${BoatBeaconIp}:${BoatBeaconPort} ..."
        $bbClient = New-Object System.Net.Sockets.TcpClient
        $bbClient.ReceiveTimeout = 30000
        $bbClient.SendTimeout    = 10000
        $iar = $bbClient.BeginConnect($BoatBeaconIp, $BoatBeaconPort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(10000)) { throw "Boat Beacon connect timeout" }
        $bbClient.EndConnect($iar)
        $bbStream = $bbClient.GetStream()
        $bbStream.ReadTimeout = 30000
        $bbReader = New-Object System.IO.StreamReader($bbStream, [System.Text.Encoding]::ASCII)
        Write-Log "Boat Beacon connected."

        Write-Log "Connecting to VM ingest @ ${VmHost}:${VmPort} ..."
        $vmClient = New-Object System.Net.Sockets.TcpClient
        $vmClient.SendTimeout = 15000
        $iar = $vmClient.BeginConnect($VmHost, $VmPort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(10000)) { throw "VM connect timeout (is :$VmPort open on $VmHost?)" }
        $vmClient.EndConnect($iar)
        $vmStream = $vmClient.GetStream()
        $vmWriter = New-Object System.IO.StreamWriter($vmStream, [System.Text.Encoding]::ASCII)
        $vmWriter.AutoFlush = $true
        Write-Log "VM ingest connected. Forwarding NMEA..."

        $lastStatus = Get-Date

        while ($bbClient.Connected -and $vmClient.Connected) {
            $line = $bbReader.ReadLine()
            if ($null -eq $line) {
                Write-Log "Boat Beacon closed the connection."
                break
            }
            $line = $line.Trim()
            if ($line.Length -eq 0) { continue }

            $vmWriter.WriteLine($line)
            $stats.Lines++
            $stats.Bytes += $line.Length + 2
            $stats.LastLine = $line

            if ($stats.Lines -le 5) {
                Write-Log ("FWD: " + $line.Substring(0, [Math]::Min(90, $line.Length)))
            }

            $age = ((Get-Date) - $lastStatus).TotalSeconds
            if ($age -ge 15) {
                $uptime = (Get-Date) - $stats.Start
                Write-Log ("status uptime={0:hh\:mm\:ss} lines={1} bytes={2}" -f $uptime, $stats.Lines, $stats.Bytes)
                $lastStatus = Get-Date
            }
        }
    }
    catch {
        $stats.Errors++
        Write-Log ("ERROR: " + $_.Exception.Message)
    }
    finally {
        foreach ($d in @($bbReader, $bbStream, $bbClient, $vmWriter, $vmStream, $vmClient)) {
            if ($d) { try { $d.Dispose() } catch {} }
        }
    }
    Write-Log "Reconnecting in 5s..."
    Start-Sleep -Seconds 5
}
