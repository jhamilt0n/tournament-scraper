#!/usr/bin/env python3
"""
Tournament Monitor - GitHub Integration
Pulls tournament data from GitHub repository and updates local cache
"""

import json
import subprocess
import os
import time
import logging
from datetime import datetime
from pathlib import Path

# Configuration
GITHUB_REPO_URL = "https://github.com/jhamilt0n/tournament-scraper.git"
LOCAL_REPO_PATH = "/tmp/tournament-scraper"
OUTPUT_FILE = "/var/www/html/tournament_data.json"
LOG_FILE = "/home/pi/logs/tournament_monitor.log"
CHECK_INTERVAL = 60  # seconds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def clone_or_pull_repo():
    """Clone repository if it doesn't exist, otherwise pull latest changes"""
    try:
        if not os.path.exists(LOCAL_REPO_PATH):
            logging.info(f"Cloning repository from {GITHUB_REPO_URL}")
            result = subprocess.run(
                ['git', 'clone', GITHUB_REPO_URL, LOCAL_REPO_PATH],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logging.error(f"Failed to clone repository: {result.stderr}")
                return False
            logging.info("Repository cloned successfully")
        else:
            logging.info("Pulling latest changes from repository")
            result = subprocess.run(
                ['git', '-C', LOCAL_REPO_PATH, 'pull'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logging.error(f"Failed to pull repository: {result.stderr}")
                return False
            logging.info("Successfully pulled latest data from GitHub")
        
        return True
    except subprocess.TimeoutExpired:
        logging.error("Git operation timed out")
        return False
    except Exception as e:
        logging.error(f"Error with git operation: {e}")
        return False

def load_tournament_data():
    """Load tournament data from the cloned repository"""
    try:
        # Look for tournament JSON files
        json_files = list(Path(LOCAL_REPO_PATH).glob('*.json'))
        
        if not json_files:
            logging.warning("No JSON files found in repository")
            return None
        
        # Get the most recently modified JSON file
        latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
        
        with open(latest_file, 'r') as f:
            data = json.load(f)
        
        logging.info("Loaded tournament data from GitHub repo")
        logging.info(f"  Tournament: {data.get('tournament_name', 'Unknown')}")
        logging.info(f"  Status: {data.get('status', 'Unknown')}")
        logging.info(f"  Display: {data.get('display_tournament', False)}")
        
        return data
        
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in tournament file: {e}")
        return None
    except Exception as e:
        logging.error(f"Error loading tournament data: {e}")
        return None

def save_tournament_data(data):
    """Save tournament data to web-accessible location"""
    try:
        # Add last updated timestamp
        data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        logging.info(f"Saved tournament data to {OUTPUT_FILE}")
        return True
    except Exception as e:
        logging.error(f"Error saving tournament data: {e}")
        return False

def generate_qr_code():
    """Generate QR code for tournament bracket"""
    try:
        result = subprocess.run(
            ['php', '/var/www/html/generate_qr.php'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            logging.info("✓ QR code generated successfully")
        else:
            logging.warning(f"QR generation returned non-zero: {result.stderr.strip()}")
        
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error generating QR code: {e}")
        return False

def check_tournament_status(data):
    """Log current tournament status"""
    if not data:
        return
    
    display = data.get('display_tournament', False)
    player_count = data.get('player_count', 0)
    
    if display and player_count > 0:
        logging.info(f"✓ Tournament is active: {data.get('tournament_name', 'Unknown')}")
    elif display and player_count == 0:
        logging.info(f"⏳ Tournament scheduled but no players yet: {data.get('tournament_name', 'Unknown')}")
    else:
        logging.info("○ No active tournament to display")

def monitor_loop():
    """Main monitoring loop"""
    logging.info("Starting GitHub-based tournament monitor...")
    logging.info(f"Repository: {GITHUB_REPO_URL}")
    logging.info(f"Check interval: {CHECK_INTERVAL} seconds")
    
    while True:
        try:
            # Pull latest data from GitHub
            if clone_or_pull_repo():
                # Load tournament data
                tournament_data = load_tournament_data()
                
                if tournament_data:
                    # Check if data has changed
                    if save_tournament_data(tournament_data):
                        logging.info("Tournament data has been updated")
                        
                        # Generate QR code if tournament is active
                        if tournament_data.get('display_tournament', False):
                            generate_qr_code()
                        
                        check_tournament_status(tournament_data)
                else:
                    logging.warning("No valid tournament data found")
            
            # Wait before next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("Monitor stopped by user")
            break
        except Exception as e:
            logging.error(f"Error in monitor loop: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    monitor_loop()
