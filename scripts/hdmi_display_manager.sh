#!/bin/bash
# Business Hours Display Manager for HDMI TV
# Manages Chromium browser for ad display during business hours

DISPLAY_URL="http://localhost/ads_display.html"
TOURNAMENT_DATA="/var/www/html/tournament_data.json"
LOG_FILE="/var/log/hdmi_display.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

is_business_hours() {
    local day=$(date +%u)  # 1=Mon, 7=Sun
    local hour=$(date +%H | sed 's/^0//')
    local minute=$(date +%M | sed 's/^0//')
    local current_minutes=$((hour * 60 + minute))
    
    # Business hours in minutes since midnight
    case $day in
        7)  # Sunday: 12pm - Monday 1am (next day)
            if [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
        1)  # Monday: Closes 1am, Opens 3pm - Tuesday 1am
            if [ $current_minutes -lt 60 ]; then  # Before 1:00am (from Sunday)
                return 0
            elif [ $current_minutes -ge 900 ]; then  # After 3:00pm
                return 0
            fi
            ;;
        2)  # Tuesday: Closes 1am, Opens 12pm - Wednesday 1am
            if [ $current_minutes -lt 60 ]; then  # Before 1:00am (from Monday)
                return 0
            elif [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
        3)  # Wednesday: Closes 1am, Opens 12pm - Thursday 1am
            if [ $current_minutes -lt 60 ]; then  # Before 1:00am (from Tuesday)
                return 0
            elif [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
        4)  # Thursday: Closes 1am, Opens 12pm - Friday 1am
            if [ $current_minutes -lt 60 ]; then  # Before 1:00am (from Wednesday)
                return 0
            elif [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
        5)  # Friday: Closes 1am, Opens 12pm - Saturday 2:30am
            if [ $current_minutes -lt 60 ]; then  # Before 1:00am (from Thursday)
                return 0
            elif [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
        6)  # Saturday: Closes 2:30am, Opens 12pm - Sunday 2:30am
            if [ $current_minutes -lt 150 ]; then  # Before 2:30am (from Friday)
                return 0
            elif [ $current_minutes -ge 720 ]; then  # After 12:00pm
                return 0
            fi
            ;;
    esac
    
    return 1
}

get_tournament_start_minutes() {
    if [ ! -f "$TOURNAMENT_DATA" ]; then
        echo "0"
        return
    fi
    
    local start_time=$(jq -r '.start_time // empty' "$TOURNAMENT_DATA" 2>/dev/null)
    if [ -z "$start_time" ]; then
        echo "0"
        return
    fi
    
    local hour=$(echo "$start_time" | grep -oP '\d+' | head -1)
    local minute=$(echo "$start_time" | grep -oP ':\K\d+' || echo "0")
    
    if echo "$start_time" | grep -iq "pm"; then
        if [ "$hour" -ne "12" ]; then
            hour=$((hour + 12))
        fi
    elif echo "$start_time" | grep -iq "am" && [ "$hour" -eq "12" ]; then
        hour=0
    fi
    
    echo $((hour * 60 + minute))
}

should_start_early_for_tournament() {
    if [ ! -f "$TOURNAMENT_DATA" ]; then
        return 1
    fi
    
    local is_today=$(jq -r '.date // empty' "$TOURNAMENT_DATA" 2>/dev/null)
    local today=$(date +%Y/%m/%d)
    
    if [ "$is_today" != "$today" ]; then
        return 1
    fi
    
    local tournament_start=$(get_tournament_start_minutes)
    if [ "$tournament_start" -eq 0 ]; then
        return 1
    fi
    
    local early_start=$((tournament_start - 30))
    local hour=$(date +%H | sed 's/^0//')
    local minute=$(date +%M | sed 's/^0//')
    local current_minutes=$((hour * 60 + minute))
    
    if [ $current_minutes -ge $early_start ] && [ $current_minutes -lt $tournament_start ]; then
        log "Early start for tournament (30 min before $tournament_start minutes)"
        return 0
    fi
    
    return 1
}

is_chromium_running() {
    pgrep -x chromium > /dev/null
}

start_chromium() {
    log "Starting Chromium in kiosk mode"
    
    pkill -f chromium
    sleep 2
    
    DISPLAY=:0 chromium \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --no-first-run \
        --disable-session-crashed-bubble \
        --disable-restore-session-state \
        --disable-translate \
        --disable-features=Translate \
        --check-for-update-interval=31536000 \
        "$DISPLAY_URL" &
    
    log "Chromium started"
}

stop_chromium() {
    log "Stopping Chromium"
    pkill -f chromium
    sleep 1
}

# Main loop
log "=== HDMI Display Manager Starting ==="

while true; do
    if is_business_hours || should_start_early_for_tournament; then
        if ! is_chromium_running; then
            start_chromium
        fi
    else
        if is_chromium_running; then
            log "Outside business hours - stopping display"
            stop_chromium
        fi
    fi
    
    sleep 60
done
