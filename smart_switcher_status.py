#!/usr/bin/env python3
"""
Smart Tournament Display Switcher - Status-Based Version
Switches display based on tournament status from DigitalPool
"""

import socket
import subprocess
import os
import json
import datetime


def get_ip_address():
    """Get the local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception:
        print("Error getting IP address.")
        return None


def get_tournament_data():
    """Read tournament data from JSON file - check both locations"""
    tournament_files = [
        '/home/pi/tournament_data.json',
        '/var/www/html/tournament_data.json'
    ]
    
    for tournament_file in tournament_files:
        if os.path.exists(tournament_file):
            try:
                with open(tournament_file, 'r') as f:
                    data = json.load(f)
                print(f"✓ Loaded tournament data from {tournament_file}")
                return data
            except Exception as e:
                print(f"Error reading {tournament_file}: {e}")
                continue
    
    print("✗ Tournament data file not found in any location")
    return None


def should_display_tournament(tournament_data):
    """
    Determine if tournament should be displayed based on status
    Returns True if status is "In Progress"
    """
    if not tournament_data:
        return False
    
    tournament_name = tournament_data.get('tournament_name', '')
    tournament_url = tournament_data.get('tournament_url', '')
    status = tournament_data.get('status', '')
    display_flag = tournament_data.get('display_tournament', False)
    
    print(f"\nTournament: {tournament_name}")
    print(f"Venue: {tournament_data.get('venue', 'N/A')}")
    print(f"Status: {status}")
    print(f"Display flag: {display_flag}")
    
    # Check if we have valid tournament data
    if tournament_name == 'No tournaments in progress' or not tournament_url:
        print("No active tournament")
        return False
    
    # Use the display_tournament flag set by the monitor
    if display_flag:
        print("✓ Tournament is in progress - should display")
    else:
        print("○ Tournament not in progress - should not display")
    
    return display_flag


def determine_page_to_display():
    """
    Determine which page to display based on tournament status
    """
    
    now = datetime.datetime.now()
    
    print(f"\n{'='*60}")
    print(f"Current time: {now.strftime('%Y-%m-%d %I:%M %p')}")
    print(f"{'='*60}\n")
    
    # Get tournament data
    tournament_data = get_tournament_data()
    
    if not tournament_data:
        print("No tournament data found")
        page_to_display = "index.php"
        reason = "No tournament data available"
    else:
        # Check if tournament should be displayed based on status
        if should_display_tournament(tournament_data):
            page_to_display = "index2.php"
            reason = "Tournament status is 'In Progress'"
        else:
            page_to_display = "index.php"
            reason = "No tournament in progress"
    
    print(f"\n{'='*60}")
    print(f"DECISION: Display {page_to_display}")
    print(f"REASON: {reason}")
    print(f"{'='*60}\n")
    
    return page_to_display


def cast_to_chromecast(page):
    """Cast the specified page to Chromecast"""
    ip = get_ip_address()
    
    if not ip:
        print("Could not retrieve IP address.")
        return False
    
    print(f"Casting http://{ip}/{page} to Chromecast...")
    
    # Change to catt directory
    new_directory = "/home/pi/.local/bin"
    if os.path.exists(new_directory):
        os.chdir(new_directory)
    
    # Cast the page
    command = f"/home/pi/.local/bin/catt cast_site 'http://{ip}/{page}'"
    result = subprocess.call(command, shell=True)
    
    if result == 0:
        print(f"✓ Successfully cast {page}")
        return True
    else:
        print(f"✗ Failed to cast {page}")
        return False


def main():
    """Main execution"""
    print("\n" + "="*60)
    print("SMART TOURNAMENT DISPLAY SWITCHER - STATUS-BASED")
    print("="*60)
    
    # First, run the tournament monitor to get latest status
    print("\nStep 1: Checking tournament status...")
    result = subprocess.call("/usr/bin/python3 /home/pi/bankshot_monitor_status.py", shell=True)
    print(f"Monitor exit code: {result}")
    
    # Wait a moment for file to be written
    import time
    time.sleep(2)
    
    # Determine which page to display
    print("\nStep 2: Determining which page to display...")
    page = determine_page_to_display()
    
    # Cast to Chromecast
    print("\nStep 3: Casting to Chromecast...")
    cast_to_chromecast(page)
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
