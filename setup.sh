#!/bin/

# Exit immediately if a command exits with a non-zero status
set -e

# Set the desired maximum memory for Redis
REDIS_MAX_MEMORY="256mb" 

# Variables
PROJECT_DIR=$(pwd)
LOGS_DIR="$PROJECT_DIR/logs"
VENV_DIR="$PROJECT_DIR/venv"
SYSTEMD_DIR="/etc/systemd/system"
USERNAME=$(whoami)

# Prompt the user for Tapo credentials
read -p "Enter your Tapo email: " TAPO_EMAIL
read -sp "Enter your Tapo password: " TAPO_PASSWORD
echo
read -p "Enter your Tapo device IP: " TAPO_DEVICE_IP
read -p "Enter your Tapo device name: " TAPO_DEVICE_NAME

# Update the Python scripts with the Tapo credentials
sed -i "s/email = .*/email = \"$TAPO_EMAIL\"/" $PROJECT_DIR/power_cycle_nbn.py
sed -i "s/password = .*/password = \"$TAPO_PASSWORD\"/" $PROJECT_DIR/power_cycle_nbn.py
sed -i "s/device_ip = .*/device_ip = \"$TAPO_DEVICE_IP\"/" $PROJECT_DIR/power_cycle_nbn.py
sed -i "s/device_name = .*/device_name = \"$TAPO_DEVICE_NAME\"/" $PROJECT_DIR/power_cycle_nbn.py

sed -i "s/email = .*/email = \"$TAPO_EMAIL\"/" $PROJECT_DIR/power_cycle_nbn_override.py
sed -i "s/password = .*/password = \"$TAPO_PASSWORD\"/" $PROJECT_DIR/power_cycle_nbn_override.py
sed -i "s/device_ip = .*/device_ip = \"$TAPO_DEVICE_IP\"/" $PROJECT_DIR/power_cycle_nbn_override.py
sed -i "s/device_name = .*/device_name = \"$TAPO_DEVICE_NAME\"/" $PROJECT_DIR/power_cycle_nbn_override.py

# Create necessary directories
mkdir -p "$LOGS_DIR"

# Create necessary log files if they don't exist
touch "$LOGS_DIR/failure_count.txt"
touch "$LOGS_DIR/check_internet.log"
touch "$LOGS_DIR/cooldown.txt"
touch "$LOGS_DIR/failure_count.txt"
touch "$LOGS_DIR/dashboard.log"

# Set up Python virtual environment and install dependencies
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install -r "$PROJECT_DIR/requirements.txt"
deactivate

# Set up Redis
if ! command -v redis-server &> /dev/null
then
    sudo apt-get update
    sudo apt-get install -y redis-server sqlite3
    sudo systemctl start redis-server
    sudo systemctl enable redis-server

    # Configure Redis to limit memory usage
    sudo bash -c "echo 'maxmemory $REDIS_MAX_MEMORY' >> /etc/redis/redis.conf"
    sudo bash -c "echo 'maxmemory-policy allkeys-lru' >> /etc/redis/redis.conf"
    sudo systemctl restart redis-server
else
    echo "Redis is already installed"
fi

# Check if Redis is running correctly
if redis-cli ping | grep -q "PONG"; then
    echo "Redis is running correctly"
else
    echo "Redis is not running correctly. Please check the Redis installation."
    exit 1
fi

# Run check_internet.sh to initialize the database and log initial data
/bin/bash $PROJECT_DIR/check_internet.sh

# Create systemd service and timer files for check_internet
sudo bash -c "cat > $SYSTEMD_DIR/check_internet.service" <<EOL
[Unit]
Description=Check Internet Connectivity

[Service]
Type=oneshot
ExecStart=/bin/bash $PROJECT_DIR/check_internet.sh
StandardOutput=append:$LOGS_DIR/check_internet-script.log
StandardError=append:$LOGS_DIR/check_internet-script_error.log
EOL

sudo bash -c "cat > $SYSTEMD_DIR/check_internet.timer" <<EOL
[Unit]
Description=Runs Check Internet Connectivity Every Minute

[Timer]
OnCalendar=*:0/1
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
EOL

# Create systemd service file for Dash app
sudo bash -c "cat > $SYSTEMD_DIR/dash_app.service" <<EOL
[Unit]
Description=Dash App for Internet Status Monitoring
After=network.target redis-server.service

[Service]
User=$USERNAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_DIR/bin/python3 $PROJECT_DIR/internet_status_dashboard.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOL

# Enable and start the services
sudo systemctl daemon-reload
sudo systemctl enable --now check_internet.timer
sudo systemctl enable --now dash_app.service

# Print status of the services
sudo systemctl status check_internet.timer
sudo systemctl status dash_app.service

echo "Setup complete. The internet monitoring system is now running."
