#!/usr/bin/env python3
"""
AIS Relay Script
Connects to Boat Beacon and forwards NMEA data to the collector server.

Usage:
    python3 ais_relay.py

Configuration (edit below or use environment variables):
    BOAT_BEACON_IP=192.168.0.25
    BOAT_BEACON_PORT=5353
    COLLECTOR_IP=136.116.165.255
    COLLECTOR_PORT=6000
"""

import socket
import time
import sys
import os
import signal
import threading
from datetime import datetime

# Configuration - edit these or set environment variables
BOAT_BEACON_IP = os.environ.get("BOAT_BEACON_IP", "192.168.0.25")
BOAT_BEACON_PORT = int(os.environ.get("BOAT_BEACON_PORT", "5353"))
COLLECTOR_IP = os.environ.get("COLLECTOR_IP", "136.116.165.255")
COLLECTOR_PORT = int(os.environ.get("COLLECTOR_PORT", "6000"))

# Reconnect settings
RECONNECT_DELAY = 5  # seconds

# Stats
stats = {
    "lines_relayed": 0,
    "bytes_relayed": 0,
    "start_time": None,
    "last_data_time": None,
    "errors": 0
}

running = True

def signal_handler(sig, frame):
    global running
    print("\n[RELAY] Shutting down...")
    running = False
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def connect_to_boat_beacon():
    """Connect to Boat Beacon TCP server."""
    while running:
        try:
            log(f"Connecting to Boat Beacon at {BOAT_BEACON_IP}:{BOAT_BEACON_PORT}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((BOAT_BEACON_IP, BOAT_BEACON_PORT))
            sock.settimeout(30)  # Timeout for reads
            log(f"Connected to Boat Beacon!")
            return sock
        except socket.error as e:
            log(f"ERROR: Cannot connect to Boat Beacon: {e}")
            stats["errors"] += 1
            log(f"Retrying in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)
    return None


def connect_to_collector():
    """Connect to the collector server."""
    while running:
        try:
            log(f"Connecting to Collector at {COLLECTOR_IP}:{COLLECTOR_PORT}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((COLLECTOR_IP, COLLECTOR_PORT))
            sock.settimeout(None)  # No timeout for sending
            log(f"Connected to Collector!")
            return sock
        except socket.error as e:
            log(f"ERROR: Cannot connect to Collector: {e}")
            stats["errors"] += 1
            log(f"Retrying in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)
    return None


def relay_data():
    """Main relay loop."""
    global running
    stats["start_time"] = datetime.now()
    
    while running:
        boat_beacon_sock = None
        collector_sock = None
        
        try:
            # Connect to both endpoints
            boat_beacon_sock = connect_to_boat_beacon()
            if not boat_beacon_sock:
                continue
                
            collector_sock = connect_to_collector()
            if not collector_sock:
                boat_beacon_sock.close()
                continue
            
            log("Relay active - forwarding NMEA data...")
            buffer = ""
            
            while running:
                try:
                    # Receive data from Boat Beacon
                    data = boat_beacon_sock.recv(4096)
                    if not data:
                        log("Boat Beacon connection closed")
                        break
                    
                    # Decode and process
                    buffer += data.decode("ascii", errors="ignore")
                    
                    # Process complete lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            # Forward to collector
                            try:
                                collector_sock.sendall((line + "\n").encode("ascii"))
                                stats["lines_relayed"] += 1
                                stats["bytes_relayed"] += len(line)
                                stats["last_data_time"] = datetime.now()
                                
                                # Print every 100th line to show activity
                                if stats["lines_relayed"] % 100 == 0:
                                    log(f"Relayed {stats['lines_relayed']} lines ({stats['bytes_relayed']} bytes)")
                                
                                # Print first few lines to confirm data flow
                                if stats["lines_relayed"] <= 5:
                                    log(f"DATA: {line[:80]}...")
                                    
                            except socket.error as e:
                                log(f"ERROR sending to collector: {e}")
                                stats["errors"] += 1
                                raise
                                
                except socket.timeout:
                    log("WARNING: No data from Boat Beacon for 30 seconds")
                    continue
                    
        except socket.error as e:
            log(f"Connection error: {e}")
            stats["errors"] += 1
            
        finally:
            if boat_beacon_sock:
                try:
                    boat_beacon_sock.close()
                except:
                    pass
            if collector_sock:
                try:
                    collector_sock.close()
                except:
                    pass
        
        if running:
            log(f"Reconnecting in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)


def print_stats():
    """Print relay statistics."""
    if stats["start_time"]:
        runtime = datetime.now() - stats["start_time"]
        log(f"=== Relay Stats ===")
        log(f"  Runtime: {runtime}")
        log(f"  Lines relayed: {stats['lines_relayed']}")
        log(f"  Bytes relayed: {stats['bytes_relayed']}")
        log(f"  Errors: {stats['errors']}")
        if stats["last_data_time"]:
            log(f"  Last data: {stats['last_data_time']}")


if __name__ == "__main__":
    log("=" * 50)
    log("AIS NMEA Relay Starting")
    log("=" * 50)
    log(f"  Boat Beacon: {BOAT_BEACON_IP}:{BOAT_BEACON_PORT}")
    log(f"  Collector:   {COLLECTOR_IP}:{COLLECTOR_PORT}")
    log("=" * 50)
    log("Press Ctrl+C to stop")
    log("")
    
    try:
        relay_data()
    except KeyboardInterrupt:
        pass
    finally:
        print_stats()
        log("Relay stopped.")
