#!/bin/bash
# Pull tournament data from GitHub
# This script pulls the latest tournament_data.json from the GitHub repository

REPO_DIR="/home/pi/tournament-scraper"
DATA_FILE="/home/pi/tournament_data.json"
DATA_FILE_BACKUP="/var/www/html/tournament_data.json"
LOG_FILE="/home/pi/logs/github_pull.log"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if repo directory exists
if [ ! -d "$REPO_DIR" ]; then
    log "ERROR: Repository directory not found: $REPO_DIR"
    log "Please clone the repository first:"
    log "  cd /home/pi"
    log "  git clone https://github.com/jhamilt0n/tournament-scraper.git"
    exit 1
fi

# Change to repo directory
cd "$REPO_DIR" || {
    log "ERROR: Could not change to directory: $REPO_DIR"
    exit 1
}

# Pull latest changes from GitHub (quietly)
log "Pulling latest data from GitHub..."
git pull origin main -q 2>&1 | tee -a "$LOG_FILE"

if [ $? -eq 0 ]; then
    log "✓ Successfully pulled from GitHub"
else
    log "✗ Git pull failed"
    exit 1
fi

# Check if tournament_data.json exists in repo
if [ ! -f "$REPO_DIR/tournament_data.json" ]; then
    log "⚠ No tournament_data.json found in repository"
    exit 0
fi

# Copy to primary location
cp "$REPO_DIR/tournament_data.json" "$DATA_FILE"
if [ $? -eq 0 ]; then
    log "✓ Copied to $DATA_FILE"
else
    log "✗ Failed to copy to $DATA_FILE"
fi

# Copy to backup location
if [ -d "$(dirname "$DATA_FILE_BACKUP")" ]; then
    cp "$REPO_DIR/tournament_data.json" "$DATA_FILE_BACKUP"
    if [ $? -eq 0 ]; then
        log "✓ Copied to $DATA_FILE_BACKUP"
    else
        log "✗ Failed to copy to $DATA_FILE_BACKUP"
    fi
fi

# Display current tournament info
if command -v python3 &> /dev/null; then
    TOURNAMENT_NAME=$(python3 -c "
import json
try:
    with open('$DATA_FILE', 'r') as f:
        data = json.load(f)
    print(data.get('tournament_name', 'Unknown'))
except:
    print('Error reading file')
" 2>/dev/null)
    
    log "Current tournament: $TOURNAMENT_NAME"
fi

log "Update complete"
