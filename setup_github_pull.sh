#!/bin/bash
# Setup script to configure Raspberry Pi for automatic GitHub pulls

echo "========================================"
echo "Pi GitHub Pull Setup"
echo "========================================"
echo ""

# Check if running as pi user
if [ "$USER" != "pi" ]; then
    echo "⚠ Warning: This script should be run as the 'pi' user"
    echo "Current user: $USER"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

REPO_DIR="/home/pi/tournament-scraper"

echo "Step 1: Clone repository (if not already cloned)"
echo "--------------------------------------"

if [ -d "$REPO_DIR" ]; then
    echo "✓ Repository already exists at $REPO_DIR"
else
    echo "Cloning repository..."
    cd /home/pi
    git clone https://github.com/jhamilt0n/tournament-scraper.git
    
    if [ $? -eq 0 ]; then
        echo "✓ Repository cloned successfully"
    else
        echo "✗ Failed to clone repository"
        echo "Please clone manually:"
        echo "  cd /home/pi"
        echo "  git clone https://github.com/jhamilt0n/tournament-scraper.git"
        exit 1
    fi
fi

echo ""
echo "Step 2: Create log directory"
echo "--------------------------------------"
mkdir -p /home/pi/logs
echo "✓ Log directory created/verified"

echo ""
echo "Step 3: Copy pull script"
echo "--------------------------------------"

# Create the pull script
cat > /home/pi/pull_tournament_data.sh << 'SCRIPT_EOF'
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
    exit 1
fi

# Change to repo directory
cd "$REPO_DIR" || {
    log "ERROR: Could not change to directory: $REPO_DIR"
    exit 1
}

# Pull latest changes from GitHub (quietly)
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
SCRIPT_EOF

chmod +x /home/pi/pull_tournament_data.sh
echo "✓ Pull script created at /home/pi/pull_tournament_data.sh"

echo ""
echo "Step 4: Test the pull script"
echo "--------------------------------------"
bash /home/pi/pull_tournament_data.sh

echo ""
echo "Step 5: Setup cron job"
echo "--------------------------------------"

# Check if cron job already exists
CRON_JOB="*/5 * * * * /home/pi/pull_tournament_data.sh > /dev/null 2>&1"
CRON_EXISTS=$(crontab -l 2>/dev/null | grep -F "pull_tournament_data.sh" | wc -l)

if [ "$CRON_EXISTS" -gt 0 ]; then
    echo "⚠ Cron job already exists"
    crontab -l | grep "pull_tournament_data.sh"
    echo ""
    read -p "Replace with new cron job? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing cron job"
    else
        # Remove old, add new
        (crontab -l 2>/dev/null | grep -v "pull_tournament_data.sh"; echo "$CRON_JOB") | crontab -
        echo "✓ Cron job updated"
    fi
else
    # Add new cron job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✓ Cron job added"
fi

echo ""
echo "Current crontab:"
crontab -l | grep -v "^#" | grep -v "^$"

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "The Pi will now automatically pull tournament data from GitHub every 5 minutes."
echo ""
echo "Useful commands:"
echo "  Test pull:        bash /home/pi/pull_tournament_data.sh"
echo "  View logs:        tail -f /home/pi/logs/github_pull.log"
echo "  Check cron:       crontab -l"
echo "  Edit cron:        crontab -e"
echo "  View data:        cat /home/pi/tournament_data.json"
echo ""
