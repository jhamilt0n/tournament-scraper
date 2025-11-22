#!/usr/bin/env python3
"""
Smart CATT Casting Monitor
Automatically switches Chromecast display based on tournament status
FIXED: Works with bankshot_monitor_multi.py data format
"""

import json
import subprocess
import time
import socket
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
TOURNAMENT_DATA_FILE = '/var/www/html/tournament_data.json'
STATE_FILE = '/var/www/html/cast_state.json'
LOG_FILE = '/var/log/catt_monitor.log'
CHECK_INTERVAL = 30  # Check every 30 seconds
CATT_COMMAND = '/home/pi/.local/bin/catt'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def get_local_ip():
    """Get the local IP address of the Pi"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception as e:
        logging.error(f"Error getting IP address: {e}")
        return None

def load_tournament_data():
    """Load tournament data from JSON file"""
    try:
        if Path(TOURNAMENT_DATA_FILE).exists():
            with open(TOURNAMENT_DATA_FILE, 'r') as f:
                return json.load(f)
        return None
    except Exception as e:
        logging.error(f"Error loading tournament data: {e}")
        return None

def load_cast_state():
    """Load the current cast state"""
    try:
        if Path(STATE_FILE).exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {
            'is_casting_tournament': False,
            'last_tournament_url': None,
            'last_status': None,
            'cast_started_at': None,
            'failsafe_check_done': False
        }
    except Exception as e:
        logging.error(f"Error loading cast state: {e}")
        return {
            'is_casting_tournament': False,
            'last_tournament_url': None,
            'last_status': None,
            'cast_started_at': None,
            'failsafe_check_done': False
        }

def save_cast_state(state):
    """Save the current cast state"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        return True
    except Exception as e:
        logging.error(f"Error saving cast state: {e}")
        return False

def catt_stop():
    """Stop current CATT cast"""
    try:
        logging.info("Stopping current cast...")
        result = subprocess.run(
            [CATT_COMMAND, 'stop'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logging.info("Cast stopped successfully")
            return True
        else:
            logging.warning(f"CATT stop returned non-zero: {result.stderr}")
            return False
    except Exception as e:
        logging.error(f"Error stopping cast: {e}")
        return False

def catt_cast_site(url):
    """Cast a website using CATT"""
    try:
        logging.info(f"Casting site: {url}")
        result = subprocess.run(
            [CATT_COMMAND, 'cast_site', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logging.info("Site cast successfully")
            return True
        else:
            logging.warning(f"CATT cast returned non-zero: {result.stderr}")
            return False
    except Exception as e:
        logging.error(f"Error casting site: {e}")
        return False

def should_display_tournament(tournament_data):
    """
    Determine if tournament should be displayed based on the scraper's display_tournament flag
    This flag is set by bankshot_monitor_multi.py based on smart logic
    """
    try:
        # Primary check: use the display_tournament flag from scraper
        should_display = tournament_data.get('display_tournament', False)
        
        # Additional safety checks
        status = tournament_data.get('status', '')
        tournament_name = tournament_data.get('tournament_name', '')
        
        # Don't display if explicitly marked as "No tournaments"
        if 'no tournament' in tournament_name.lower():
            return False
        
        # Status should be "In Progress" or "Upcoming"
        if status not in ['In Progress', 'Upcoming', 'in_progress', 'upcoming']:
            return False
        
        return should_display
        
    except Exception as e:
        logging.error(f"Error checking display status: {e}")
        return False

def monitor_and_cast():
    """Main monitoring and casting logic"""
    logging.info("=" * 60)
    logging.info("CATT Monitor Starting (Fixed for bankshot_monitor_multi.py)")
    logging.info("=" * 60)
    
    state = load_cast_state()
    
    while True:
        try:
            # Load current tournament data
            tournament_data = load_tournament_data()
            
            if not tournament_data:
                logging.debug("No tournament data found")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Get tournament info
            tournament_name = tournament_data.get('tournament_name', 'Unknown')
            tournament_url = tournament_data.get('tournament_url')
            status = tournament_data.get('status', 'Unknown')
            should_display = should_display_tournament(tournament_data)
            
            logging.debug(f"Tournament: {tournament_name}")
            logging.debug(f"  Status: {status}, Should Display: {should_display}")
            
            # Get local IP for casting
            local_ip = get_local_ip()
            if not local_ip:
                logging.error("Could not determine local IP address")
                time.sleep(CHECK_INTERVAL)
                continue
            
            cast_url = f"http://{local_ip}/"
            
            # SCENARIO 1: Tournament should be displayed and we're not casting yet
            if should_display and not state['is_casting_tournament']:
                logging.info(f"🎱 Tournament ready to display")
                logging.info(f"   Name: {tournament_name}")
                logging.info(f"   Status: {status}")
                
                catt_stop()
                time.sleep(2)
                
                if catt_cast_site(cast_url):
                    state['is_casting_tournament'] = True
                    state['last_tournament_url'] = tournament_url
                    state['last_status'] = status
                    state['cast_started_at'] = datetime.now().isoformat()
                    state['failsafe_check_done'] = False
                    save_cast_state(state)
                    logging.info("✓ Successfully started casting tournament display")
            
            # SCENARIO 2: Tournament no longer should be displayed - reset state
            elif not should_display and state['is_casting_tournament']:
                logging.info("Tournament no longer should be displayed - Resetting state")
                state['is_casting_tournament'] = False
                state['last_tournament_url'] = None
                state['last_status'] = None
                state['failsafe_check_done'] = False
                state['cast_started_at'] = None
                save_cast_state(state)
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("Monitor stopped by user")
            break
        except Exception as e:
            logging.error(f"Error in monitor loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)

def main():
    monitor_and_cast()

if __name__ == '__main__':
    main()
