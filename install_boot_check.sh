#!/bin/bash
# Install Boot-Time Tournament Check
# This script sets up automatic tournament checking on system boot

echo "=========================================="
echo "Installing Boot-Time Tournament Check"
echo "=========================================="
echo ""

# Check if running as pi user or root
if [ "$USER" != "pi" ] && [ "$USER" != "root" ]; then
    echo "⚠ This script should be run as 'pi' user or with sudo"
    exit 1
fi

echo "Step 1: Copy boot check script"
echo "--------------------------------------"

# Download or copy the boot check script
if [ ! -f "/home/pi/boot_tournament_check.sh" ]; then
    echo "Creating boot check script..."
    
    # Try to download from GitHub
    wget -q https://raw.githubusercontent.com/jhamilt0n/tournament-scraper/main/boot_tournament_check.sh -O /home/pi/boot_tournament_check.sh 2>/dev/null
    
    if [ $? -ne 0 ]; then
        echo "⚠ Could not download from GitHub"
        echo "Please manually copy boot_tournament_check.sh to /home/pi/"
        exit 1
    fi
fi

chmod +x /home/pi/boot_tournament_check.sh
chown pi:pi /home/pi/boot_tournament_check.sh
echo "✓ Boot check script installed"

echo ""
echo "Step 2: Create systemd service"
echo "--------------------------------------"

# Create the systemd service file
sudo tee /etc/systemd/system/tournament-boot-check.service > /dev/null << 'EOF'
[Unit]
Description=Tournament Boot Check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
ExecStart=/home/pi/boot_tournament_check.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Systemd service created"

echo ""
echo "Step 3: Enable and start service"
echo "--------------------------------------"

# Reload systemd
sudo systemctl daemon-reload

# Enable service to run on boot
sudo systemctl enable tournament-boot-check.service

# Test the service now
echo "Testing service..."
sudo systemctl start tournament-boot-check.service

# Check status
if sudo systemctl is-active --quiet tournament-boot-check.service; then
    echo "✓ Service is running"
else
    echo "⚠ Service failed to start"
    echo "Check status with: sudo systemctl status tournament-boot-check.service"
fi

echo ""
echo "Step 4: Create logs directory"
echo "--------------------------------------"
mkdir -p /home/pi/logs
chown pi:pi /home/pi/logs
echo "✓ Logs directory created"

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "The boot check will now run automatically on every reboot."
echo ""
echo "Useful commands:"
echo "  View boot log:     tail -f /home/pi/logs/boot_check.log"
echo "  Check service:     sudo systemctl status tournament-boot-check.service"
echo "  View journal:      sudo journalctl -u tournament-boot-check.service"
echo "  Test manually:     bash /home/pi/boot_tournament_check.sh"
echo "  Disable service:   sudo systemctl disable tournament-boot-check.service"
echo ""
echo "To test reboot behavior:"
echo "  sudo reboot"
echo ""
