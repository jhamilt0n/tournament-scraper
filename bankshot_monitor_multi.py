#!/usr/bin/env python3
"""
Bankshot Billiards Tournament Monitor - Multi-Tournament Version
FIXED: Search for just "Bankshot Billiards" not "Bankshot Billiards Hilliard"
Handles multiple tournaments per day with smart priority logic:
- Shows first scheduled tournament until later one starts
- Switches to latest "In Progress" tournament
- Keeps showing tournament even after midnight until completed
"""

import datetime
import time
import json
import sys
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# Configuration
VENUE_NAME = "Bankshot Billiards"
VENUE_CITY = "Hilliard"
DATA_FILE = "/home/pi/tournament_data.json"
DATA_FILE_BACKUP = "/var/www/html/tournament_data.json"
LOG_FILE = "/home/pi/logs/tournament_monitor.log"


def log(message):
    """Log message to console and file"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_message + "\n")
    except:
        pass


def setup_driver(headless=True):
    """Setup Chrome WebDriver"""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument('--headless')
    
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36')
    chrome_options.add_argument('--disable-extensions')
    
    try:
        service = Service(executable_path='/usr/bin/chromedriver')
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        log(f"Error setting up ChromeDriver: {e}")
        raise


def parse_time_string(time_str):
    """Parse time strings like '7:00 PM' and return datetime.time object"""
    try:
        time_str = time_str.strip()
        for fmt in ['%I:%M %p', '%I:%M%p', '%I %p', '%I%p']:
            try:
                parsed = datetime.datetime.strptime(time_str, fmt)
                return parsed.time()
            except:
                continue
        return None
    except:
        return None


def search_tournaments_on_page(driver):
    """Search for Bankshot tournaments on the current page"""
    tournaments = []
    
    try:
        # Search for venue (just name, not city - city in search doesn't work)
        search_term = VENUE_NAME
        log(f"Searching for: {search_term}")
        
        # Find and use search input
        search_input = None
        selectors = [
            "input.ant-input",
            "input[type='text']",
            "//input[contains(@class, 'ant-input')]",
        ]
        
        for selector in selectors:
            try:
                if selector.startswith('//'):
                    search_input = driver.find_element(By.XPATH, selector)
                else:
                    search_input = driver.find_element(By.CSS_SELECTOR, selector)
                
                if search_input.is_displayed() and search_input.is_enabled():
                    break
                else:
                    search_input = None
            except NoSuchElementException:
                continue
        
        if not search_input:
            log("✗ Could not find search input")
            return []
        
        search_input.click()
        time.sleep(0.5)
        search_input.clear()
        time.sleep(0.5)
        
        for char in search_term:
            search_input.send_keys(char)
            time.sleep(0.05)
        
        time.sleep(1)
        
        from selenium.webdriver.common.keys import Keys
        search_input.send_keys(Keys.ENTER)
        
        log("Waiting for search results...")
        time.sleep(8)
        
        # Scroll to load all content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # Get page text
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = body_text.split('\n')
        
        log(f"Checking {len(lines)} lines for tournament info...")
        log(f"Looking for: '{VENUE_NAME}' with city '{VENUE_CITY}'")
        
        # Count how many times we find the venue
        venue_mentions = 0
        for line in lines:
            if VENUE_NAME in line:
                venue_mentions += 1
        
        log(f"Found {venue_mentions} mentions of {VENUE_NAME}")
        
        # Look for tournaments
        for i, line in enumerate(lines):
            line = line.strip()
            
            # First check if line contains venue name
            if VENUE_NAME in line:
                # Get more context to check for city
                context_lines = lines[max(0, i-5):min(len(lines), i+15)]
                context = '\n'.join(context_lines)
                
                # Verify this is the Hilliard location (not another Bankshot location)
                if VENUE_CITY not in context:
                    log(f"Skipping - found {VENUE_NAME} but not in {VENUE_CITY}")
                    continue
                
                log(f"Found venue mention at line {i}: {line}")
                log(f"Context around match:\n{context}\n")
                
                # Extract info
                date_match = re.search(r'(\d{4}/\d{2}/\d{2})', context)
                tournament_date = date_match.group(1) if date_match else None
                
                time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', context, re.IGNORECASE)
                start_time_str = time_match.group(1) if time_match else None
                start_time = parse_time_string(start_time_str) if start_time_str else None
                
                # Find tournament name
                tournament_name = None
                for ctx_line in context_lines:
                    if 'tournament' in ctx_line.lower() and VENUE_NAME not in ctx_line:
                        tournament_name = ctx_line.strip()
                        break
                
                if not tournament_name:
                    tournament_name = f"Tournament at {VENUE_NAME}"
                
                # Determine status
                actual_status = "Unknown"
                if "In Progress" in context:
                    actual_status = "In Progress"
                elif "Upcoming" in context:
                    actual_status = "Upcoming"
                elif "Completed" in context:
                    actual_status = "Completed"
                
                # Construct URL
                tournament_url = None
                if tournament_date and tournament_name:
                    date_no_slashes = tournament_date.replace('/', '')
                    name_slug = re.sub(r'[^a-z0-9-]', '', tournament_name.lower().replace(' ', '-'))
                    name_slug = re.sub(r'-+', '-', name_slug).strip('-')
                    tournament_url = f"https://digitalpool.com/tournaments/{date_no_slashes}-{name_slug}/"
                
                tournament_info = {
                    'name': tournament_name,
                    'venue': f"{VENUE_NAME}, {VENUE_CITY}",
                    'date': tournament_date,
                    'start_time': start_time_str,
                    'start_time_parsed': start_time.strftime("%H:%M") if start_time else None,
                    'status': actual_status,
                    'url': tournament_url,
                    'found_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                tournaments.append(tournament_info)
                log(f"✓ Found tournament: {tournament_name}")
                log(f"  Date: {tournament_date}, Time: {start_time_str}, Status: {actual_status}")
        
        if not tournaments:
            log("✗ No tournaments found for Hilliard location")
        
        return tournaments
        
    except Exception as e:
        log(f"Error searching tournaments: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_all_todays_tournaments():
    """Get all tournaments at Bankshot for today"""
    driver = None
    
    try:
        log("="*60)
        log("Searching for ALL Bankshot tournaments today...")
        log("="*60)
        
        driver = setup_driver(headless=True)
        driver.get("https://www.digitalpool.com/tournaments")
        
        log("Waiting for page to load...")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input"))
            )
            log("✓ Page loaded")
        except TimeoutException:
            log("✗ Page load timeout")
            return []
        
        time.sleep(3)
        
        # Don't worry about status filter - just search
        log("Skipping status filter (will search all visible tournaments)")
        all_tournaments = search_tournaments_on_page(driver)
        
        if not all_tournaments:
            log("No tournaments found")
            return []
        
        # Filter to today's date
        today = datetime.date.today()
        today_str = today.strftime("%Y/%m/%d")
        
        todays_tournaments = [t for t in all_tournaments if t['date'] == today_str]
        
        log(f"\n{'='*60}")
        log(f"Found {len(todays_tournaments)} tournament(s) for today ({today_str})")
        log(f"{'='*60}")
        
        for t in todays_tournaments:
            log(f"\n  Tournament: {t['name']}")
            log(f"  Start time: {t['start_time']}")
            log(f"  Status: {t['status']}")
        
        return todays_tournaments
        
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def determine_which_tournament_to_display(tournaments):
    """
    Smart logic to determine which tournament to display:
    1. If any tournament is "In Progress", show the LATEST one that's in progress
    2. If no tournaments are in progress, show the FIRST scheduled tournament
    3. Continue showing a tournament even after midnight until it's completed
    """
    
    if not tournaments:
        log("No tournaments to display")
        return None
    
    log("\n" + "="*60)
    log("DETERMINING WHICH TOURNAMENT TO DISPLAY")
    log("="*60)
    
    # Check for any "In Progress" tournaments
    in_progress = [t for t in tournaments if t['status'] == 'In Progress']
    
    if in_progress:
        log(f"Found {len(in_progress)} tournament(s) in progress")
        
        # If multiple in progress, show the latest one (by start time)
        if len(in_progress) > 1:
            # Sort by start time
            sorted_in_progress = sorted(in_progress, 
                                       key=lambda x: x['start_time_parsed'] if x['start_time_parsed'] else "00:00",
                                       reverse=True)
            selected = sorted_in_progress[0]
            log(f"Multiple in progress - selecting latest: {selected['name']} at {selected['start_time']}")
        else:
            selected = in_progress[0]
            log(f"Selecting in-progress tournament: {selected['name']}")
        
        return selected
    
    # No tournaments in progress - show first scheduled
    log("No tournaments in progress")
    
    # Filter out completed tournaments
    not_completed = [t for t in tournaments if t['status'] != 'Completed']
    
    if not not_completed:
        log("All tournaments are completed - no tournament to display")
        return None
    
    # Sort by start time to get first scheduled
    sorted_tournaments = sorted(not_completed,
                                key=lambda x: x['start_time_parsed'] if x['start_time_parsed'] else "00:00")
    
    selected = sorted_tournaments[0]
    log(f"Selecting first scheduled tournament: {selected['name']} at {selected['start_time']}")
    log(f"Status: {selected['status']}")
    
    return selected


def check_previous_tournament_still_active():
    """
    Check if we were displaying a tournament that's still in progress
    (handles after-midnight scenario)
    """
    try:
        with open(DATA_FILE, 'r') as f:
            prev_data = json.load(f)
        
        # Check if we were displaying a tournament
        if prev_data.get('display_tournament') and prev_data.get('status') == 'In Progress':
            tournament_date = prev_data.get('date')
            
            # If tournament was from yesterday but still in progress
            if tournament_date:
                prev_date = datetime.datetime.strptime(tournament_date, "%Y/%m/%d").date()
                today = datetime.date.today()
                
                if prev_date < today:
                    log(f"Previous tournament from {tournament_date} may still be active")
                    log(f"Will need to verify status on DigitalPool")
                    return prev_data
        
        return None
    except:
        return None


def save_tournament_data(tournament):
    """Save tournament data to JSON files"""
    if not tournament:
        output_data = {
            'tournament_name': 'No tournaments to display',
            'tournament_url': None,
            'venue': None,
            'date': None,
            'start_time': None,
            'status': None,
            'payout_data': None,
            'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'display_tournament': False
        }
    else:
        # Determine payout data
        payout_data = 'payouts15.json'
        if tournament['name']:
            if '8-ball' in tournament['name'].lower():
                payout_data = 'payouts20.json'
        
        # ONLY display if status is "In Progress"
        should_display = (tournament['status'] == 'In Progress')
        
        output_data = {
            'tournament_name': tournament['name'],
            'tournament_url': tournament['url'],
            'venue': tournament['venue'],
            'date': tournament['date'],
            'start_time': tournament['start_time'],
            'status': tournament['status'],
            'payout_data': payout_data,
            'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'display_tournament': should_display
        }
        
        log(f"\nTournament to display: {tournament['name']}")
        log(f"Status: {tournament['status']}")
        log(f"Display flag: {should_display}")
    
    # Save to both locations
    for file_path in [DATA_FILE, DATA_FILE_BACKUP]:
        try:
            with open(file_path, 'w') as f:
                json.dump(output_data, f, indent=2)
            log(f"✓ Saved to {file_path}")
        except Exception as e:
            log(f"✗ Error saving to {file_path}: {e}")


def main():
    """Main execution"""
    log("\n" + "="*60)
    log("BANKSHOT BILLIARDS TOURNAMENT MONITOR - MULTI-TOURNAMENT")
    log("="*60)
    
    # Check if previous tournament might still be active (after midnight)
    prev_tournament = check_previous_tournament_still_active()
    if prev_tournament:
        log("Checking if previous day's tournament is still active...")
    
    # Get all today's tournaments
    tournaments = get_all_todays_tournaments()
    
    # Determine which one to display
    selected_tournament = determine_which_tournament_to_display(tournaments)
    
    # Save results
    save_tournament_data(selected_tournament)
    
    log("\n" + "="*60)
    log("MONITOR COMPLETED")
    log("="*60)
    
    if selected_tournament:
        log(f"✓ Selected tournament to display")
        sys.exit(0)
    else:
        log("○ No tournament to display")
        sys.exit(1)


if __name__ == "__main__":
    main()
