#!/usr/bin/env python3
"""
Bankshot Billiards Tournament Monitor - Multi-Tournament Version
FIXED: Uses DOM element parsing instead of text parsing to properly capture tournament data
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
    """Search for Bankshot tournaments on the current page using DOM parsing"""
    tournaments = []
    
    try:
        # Search for venue
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
        
        # DEBUG: Save page source for inspection
        try:
            with open('/tmp/digitalpool_page.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            log("Saved page source to /tmp/digitalpool_page.html for debugging")
        except:
            pass
        
        # Try multiple selector strategies to find tournament cards
        card_selectors = [
            ".ant-card",
            "[class*='tournament']",
            "[class*='TournamentCard']",
            ".card",
            "div[class*='Card']"
        ]
        
        tournament_cards = []
        for selector in card_selectors:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    log(f"Found {len(cards)} elements with selector: {selector}")
                    tournament_cards = cards
                    break
            except:
                continue
        
        if not tournament_cards:
            log("Could not find tournament cards with standard selectors, trying alternative approach...")
            # Fallback: look for any div that contains both venue and date pattern
            all_divs = driver.find_elements(By.TAG_NAME, "div")
            tournament_cards = [div for div in all_divs 
                              if VENUE_NAME in div.text and re.search(r'\d{4}/\d{2}/\d{2}', div.text)]
            log(f"Found {len(tournament_cards)} potential tournament divs with venue and date")
        
        log(f"Processing {len(tournament_cards)} potential tournament cards")
        
        # DEBUG: Save all card HTML and text for inspection
        debug_dir = "/tmp/tournament_debug"
        try:
            import os
            os.makedirs(debug_dir, exist_ok=True)
            log(f"Created debug directory: {debug_dir}")
        except:
            debug_dir = None
        
        for idx, card in enumerate(tournament_cards):
            try:
                card_text = card.text
                
                # DEBUG: Save this card's HTML and text
                if debug_dir:
                    try:
                        # Save HTML
                        card_html = card.get_attribute('outerHTML')
                        with open(f"{debug_dir}/card_{idx}_html.html", 'w', encoding='utf-8') as f:
                            f.write(card_html)
                        
                        # Save text
                        with open(f"{debug_dir}/card_{idx}_text.txt", 'w', encoding='utf-8') as f:
                            f.write(card_text)
                        
                        log(f"Saved card {idx} debug files")
                    except Exception as e:
                        log(f"Could not save debug for card {idx}: {e}")
                
                # Check if this card is for Bankshot Billiards in Hilliard
                if VENUE_NAME not in card_text:
                    continue
                
                if VENUE_CITY not in card_text:
                    log(f"Card {idx}: Found {VENUE_NAME} but not in {VENUE_CITY}, skipping")
                    continue
                
                log(f"\n{'='*50}")
                log(f"Card {idx} - Found matching venue!")
                log(f"{'='*50}")
                log(f"Card text:\n{card_text}\n")
                
                # DEBUG: Mark this as the matching card
                if debug_dir:
                    try:
                        with open(f"{debug_dir}/MATCHING_CARD_{idx}.txt", 'w') as f:
                            f.write(f"This is the matching tournament card!\n\n{card_text}")
                        log(f"★ Marked card {idx} as MATCHING CARD")
                    except:
                        pass
                
                # Extract tournament name - try multiple strategies
                tournament_name = None
                
                # Strategy 1: Look for heading elements
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
                    try:
                        heading = card.find_element(By.TAG_NAME, tag)
                        if heading.text and heading.text.strip() and VENUE_NAME not in heading.text:
                            tournament_name = heading.text.strip()
                            log(f"Found name in {tag}: {tournament_name}")
                            break
                    except:
                        continue
                
                # Strategy 2: Look for elements with 'title' class
                if not tournament_name:
                    try:
                        title_elem = card.find_element(By.CSS_SELECTOR, "[class*='title'], [class*='Title'], [class*='name'], [class*='Name']")
                        if title_elem.text and title_elem.text.strip():
                            tournament_name = title_elem.text.strip()
                            log(f"Found name in title element: {tournament_name}")
                    except:
                        pass
                
                # Strategy 3: Look for first meaningful text line
                if not tournament_name:
                    lines = card_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if (line and 
                            len(line) > 5 and 
                            VENUE_NAME not in line and
                            VENUE_CITY not in line and
                            not re.match(r'^\d{4}/\d{2}/\d{2}', line) and
                            'Showing tournaments' not in line):
                            tournament_name = line
                            log(f"Found name from text parsing: {tournament_name}")
                            break
                
                if not tournament_name:
                    tournament_name = f"Tournament at {VENUE_NAME}"
                    log(f"Using default name: {tournament_name}")
                
                # Extract date
                date_match = re.search(r'(\d{4}/\d{2}/\d{2})', card_text)
                tournament_date = date_match.group(1) if date_match else None
                log(f"Date: {tournament_date}")
                
                # Extract time - prioritize tournament start time over registration/check-in
                start_time_str = None
                all_times_found = []
                
                # First, try to find times with specific context keywords (most reliable)
                priority_patterns = [
                    (r'(?:Tournament\s+)?Start[s]?[:\s]+(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)', 'Tournament Start'),
                    (r'(?:Play\s+)?Start[s]?[:\s]+(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)', 'Play Start'),
                    (r'Start\s+Time[:\s]+(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)', 'Start Time'),
                    (r'Begins?[:\s]+(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)', 'Begins'),
                ]
                
                for pattern, label in priority_patterns:
                    time_match = re.search(pattern, card_text, re.IGNORECASE)
                    if time_match:
                        start_time_str = time_match.group(1).strip()
                        log(f"Found time with priority pattern '{label}': {start_time_str}")
                        break
                
                # If no priority pattern found, collect ALL times and filter out registration/check-in
                if not start_time_str:
                    log("No priority time pattern found, scanning for all times...")
                    
                    # Find all times in the card
                    all_time_patterns = [
                        r'(\d{1,2}:\d{2}\s*[AP]\.?M\.?)',  # 7:00 PM, 7:00PM
                        r'(\d{1,2}\s*[AP]\.?M\.?)',         # 7 PM, 7PM
                    ]
                    
                    for pattern in all_time_patterns:
                        matches = re.finditer(pattern, card_text, re.IGNORECASE)
                        for match in matches:
                            time_val = match.group(1).strip()
                            # Get context around the time (50 chars before and after)
                            start_pos = max(0, match.start() - 50)
                            end_pos = min(len(card_text), match.end() + 50)
                            context = card_text[start_pos:end_pos]
                            
                            all_times_found.append({
                                'time': time_val,
                                'context': context
                            })
                    
                    log(f"Found {len(all_times_found)} time(s) in card")
                    
                    # Filter out registration/check-in times
                    filtered_times = []
                    exclude_keywords = ['registration', 'check-in', 'check in', 'checkin', 'sign-in', 
                                       'signin', 'sign in', 'doors', 'door open']
                    
                    for time_info in all_times_found:
                        context_lower = time_info['context'].lower()
                        is_excluded = any(keyword in context_lower for keyword in exclude_keywords)
                        
                        if is_excluded:
                            log(f"  Excluding time {time_info['time']} (context suggests registration/check-in)")
                            log(f"    Context: {time_info['context'][:100]}")
                        else:
                            filtered_times.append(time_info)
                            log(f"  Keeping time {time_info['time']}")
                            log(f"    Context: {time_info['context'][:100]}")
                    
                    # Use the LAST remaining time (tournament start is usually listed after registration)
                    if filtered_times:
                        start_time_str = filtered_times[-1]['time']
                        log(f"Selected last filtered time as tournament start: {start_time_str}")
                    elif all_times_found:
                        # If all were filtered out, use the last one anyway
                        start_time_str = all_times_found[-1]['time']
                        log(f"All times were filtered, using last time anyway: {start_time_str}")
                
                if not start_time_str:
                    log("No start time found in card text")
                
                start_time = parse_time_string(start_time_str) if start_time_str else None
                
                # Extract status - check for explicit keywords first, then infer from context
                actual_status = "Unknown"
                
                # First check for explicit status keywords
                status_indicators = {
                    "In Progress": ["In Progress", "Live", "Active", "Playing"],
                    "Upcoming": ["Upcoming", "Scheduled", "Future"],
                    "Completed": ["Completed", "Finished", "Final", "Ended"]
                }
                
                for status, keywords in status_indicators.items():
                    if any(keyword in card_text for keyword in keywords):
                        actual_status = status
                        log(f"Status from keyword: {actual_status}")
                        break
                
                # If no explicit keyword, infer from context
                if actual_status == "Unknown":
                    log("No explicit status keyword found, inferring from context...")
                    
                    # Look for completion percentage
                    completion_match = re.search(r'(\d+)%\s*Complete', card_text, re.IGNORECASE)
                    if completion_match:
                        completion_pct = int(completion_match.group(1))
                        log(f"Found completion: {completion_pct}%")
                        
                        if completion_pct == 100:
                            actual_status = "Completed"
                            log("Status inferred: Completed (100% complete)")
                        elif completion_pct == 0:
                            actual_status = "Upcoming"
                            log("Status inferred: Upcoming (0% complete)")
                        elif completion_pct > 0 and completion_pct < 100:
                            actual_status = "In Progress"
                            log("Status inferred: In Progress (partial completion)")
                    else:
                        # Check if today's date matches tournament date
                        if tournament_date:
                            today = datetime.date.today()
                            today_str = today.strftime("%Y/%m/%d")
                            
                            if tournament_date == today_str:
                                # Today's tournament with no completion info - probably upcoming
                                actual_status = "Upcoming"
                                log("Status inferred: Upcoming (today's tournament, no completion data)")
                            elif tournament_date < today_str:
                                # Past tournament - probably completed
                                actual_status = "Completed"
                                log("Status inferred: Completed (past date)")
                
                log(f"Final status: {actual_status}")
                
                # Get tournament URL from link element
                tournament_url = None
                try:
                    link_element = card.find_element(By.CSS_SELECTOR, "a[href*='/tournaments/']")
                    tournament_url = link_element.get_attribute('href')
                    log(f"Found URL from link: {tournament_url}")
                except:
                    # Fallback: construct URL
                    if tournament_date and tournament_name:
                        date_no_slashes = tournament_date.replace('/', '')
                        
                        # Remove date from tournament name to avoid duplication in URL
                        # Tournament names often start with date like "2025/11/19 Wednesday Night..."
                        name_for_url = tournament_name
                        name_for_url = re.sub(r'^\d{4}/\d{2}/\d{2}\s+', '', name_for_url)  # Remove date prefix
                        
                        name_slug = re.sub(r'[^a-z0-9-]', '', name_for_url.lower().replace(' ', '-'))
                        name_slug = re.sub(r'-+', '-', name_slug).strip('-')
                        tournament_url = f"https://digitalpool.com/tournaments/{date_no_slashes}-{name_slug}/"
                        log(f"Constructed URL: {tournament_url}")
                
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
                log(f"✓ Successfully extracted tournament info")
                log(f"  Name: {tournament_name}")
                log(f"  Date: {tournament_date}")
                log(f"  Time: {start_time_str}")
                log(f"  Status: {actual_status}")
                
            except Exception as e:
                log(f"Error parsing tournament card {idx}: {e}")
                import traceback
                log(traceback.format_exc())
                continue
        
        if not tournaments:
            log("✗ No tournaments found for Hilliard location")
        else:
            log(f"\n✓ Found {len(tournaments)} tournament(s) total")
        
        # DEBUG: Create summary report
        if debug_dir:
            try:
                summary_file = f"{debug_dir}/DEBUG_SUMMARY.txt"
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write("="*60 + "\n")
                    f.write("TOURNAMENT SCRAPER DEBUG SUMMARY\n")
                    f.write("="*60 + "\n\n")
                    f.write(f"Search Term: {search_term}\n")
                    f.write(f"Total Cards Found: {len(tournament_cards)}\n")
                    f.write(f"Matching Tournaments: {len(tournaments)}\n\n")
                    
                    f.write("FILES SAVED:\n")
                    f.write(f"- Full page HTML: /tmp/digitalpool_page.html\n")
                    f.write(f"- Card HTML files: {debug_dir}/card_*_html.html\n")
                    f.write(f"- Card text files: {debug_dir}/card_*_text.txt\n")
                    f.write(f"- Matching cards: {debug_dir}/MATCHING_CARD_*.txt\n\n")
                    
                    if tournaments:
                        f.write("TOURNAMENTS FOUND:\n")
                        f.write("-"*60 + "\n")
                        for i, t in enumerate(tournaments, 1):
                            f.write(f"\nTournament {i}:\n")
                            f.write(f"  Name: {t['name']}\n")
                            f.write(f"  Venue: {t['venue']}\n")
                            f.write(f"  Date: {t['date']}\n")
                            f.write(f"  Start Time: {t['start_time']}\n")
                            f.write(f"  Status: {t['status']}\n")
                            f.write(f"  URL: {t['url']}\n")
                    else:
                        f.write("NO TOURNAMENTS FOUND\n")
                        f.write("\nPossible reasons:\n")
                        f.write("- Venue name/city not matching in card text\n")
                        f.write("- Cards not being detected properly\n")
                        f.write("- Check the card HTML/text files to see what data is available\n")
                    
                    f.write("\n" + "="*60 + "\n")
                    f.write("NEXT STEPS:\n")
                    f.write("="*60 + "\n")
                    f.write("1. Review MATCHING_CARD_*.txt to see the raw text\n")
                    f.write("2. Review card_*_html.html to see the HTML structure\n")
                    f.write("3. Look for status indicators (In Progress, Upcoming, etc.)\n")
                    f.write("4. Look for start time patterns\n")
                    f.write("5. Adjust regex patterns or selectors as needed\n")
                
                log(f"\n★★★ DEBUG SUMMARY SAVED: {summary_file} ★★★")
                log(f"Review the files in {debug_dir}/ to see all card data")
            except Exception as e:
                log(f"Could not create debug summary: {e}")
        
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
        
        # Search for tournaments
        log("Searching for tournaments...")
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
        
        # Display if status is "In Progress" OR "Upcoming"
        should_display = (tournament['status'] in ['In Progress', 'Upcoming'])
        
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
        if should_display:
            log("✓ Tournament will be displayed (Upcoming or In Progress)")
        else:
            log("○ Tournament will NOT be displayed (status is not Upcoming/In Progress)")
    
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
