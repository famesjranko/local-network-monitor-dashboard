# Basic Internet Monitoring and Modem Power Cycle System (Tapo P100)

This project monitors internet connectivity by pinging multiple targets, logs the status in an SQLite database, and automatically triggers a modem power cycle via Tapo P100 Smart Plug if consecutive failures are detected. It also provides a dashboard to visualize the network status over time using a Dash web app.

## Features

- **Monitor Internet Connectivity**: Pings a list of IPs (e.g., `8.8.8.8`, `1.1.1.1`) and logs success/failure in SQLite.
- **Automatic Power Cycle**: If the internet is down for 5 consecutive checks, it triggers a power cycle of a TP-Link Tapo smart plug (controlling the modem).
- **Dash Dashboard**: A web interface to visualize internet status logs using Dash, showing connectivity success rate, latency, and packet loss over time.
- **Redis Caching**: Used in the Dash app for performance optimization.
- **Cooldown Logic**: Ensures the power cycle isn’t retriggered within a specified cooldown period (10 minutes).
- **Tapo p100 Smart Plug**: Utilises [Tapo Smart Plug](https://www.tapo.com/au/product/smart-plug/tapo-p100/) for power cycling modem.

## Dash Web App Interface

![Dash Web App Screenshot](screenshots/dashboard.png)

---

## Project Structure

```
internet-monitoring/
├── check_internet.sh                  # Script that checks the internet and triggers the power cycle
├── power_cycle_nbn.py                 # Python script for power cycling the modem via Tapo smart plug
├── power_cycle_nbn_override.py        # Pytho script to manually trigger power cycling of Tapo smart plug
├── requirements.txt                   # Python dependencies for the power cycle script (pytapo)
├── internet_status_dashboard.py       # Dash web app to visualize network logs
├── README.md
├── setup.sh                           # Automated setup script
└── logs/                              # Directory for logs, state files, and db
```

---

## Auto Setup 

### 1. Clone the repo:
```bash
git clone https://github.com/famesjranko/internet-monitoring.git
cd internet-monitoring
```

### 2. Run the Setup Script:
```bash
chmod +x setup.sh
sudo ./setup.sh
```

This script will:
 - Create necessary directories.
 - Move relevant files into the project directory.
 - Set up a Python virtual environment and install dependencies.
 - Install and configure Redis (can set cache size max in script)
 - Create and enable systemd service and timer files for the internet check and Dash app.

### 3. Verify Services:
Check the status of the services to ensure they are running correctly:
```bash
sudo systemctl status check_internet.timer
sudo systemctl status dash_app.service
```

## Manual Setup 

### 1. Install Dependencies

First, clone this repository and navigate to the directory:

```bash
git clone https://github.com/famesjranko/internet-monitoring.git
cd internet-monitoring
```

#### a. Python Virtual Environment

1. Create a virtual environment to manage Python dependencies:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies for both the **power cycle script** and the **Dash app**:

   ```bash
   pip install -r scripts/requirements.txt
   pip install -r dash_app/requirements.txt
   ```

#### b. Redis Setup

##### i. Install and Start Redis

1. **Install Redis** on your system:

   ```bash
   sudo apt-get update
   sudo apt-get install redis-server
   ```

2. **Start Redis** and enable it to run at startup:

   ```bash
   sudo systemctl start redis-server
   sudo systemctl enable redis-server
   ```

##### ii. Configure Redis

1. **Set the Redis port** (if using a port other than the default `6379`):

   - Open the Redis configuration file:
   
     ```bash
     sudo nano /etc/redis/redis.conf
     ```

   - Find the `port` setting and modify it if necessary:

     ```bash
     port 6379  # Change this if needed
     ```

   - Save the file and restart Redis:

     ```bash
     sudo systemctl restart redis-server
     ```

2. **Limit Redis memory usage** (optional):

   - Open the configuration file:

     ```bash
     sudo nano /etc/redis/redis.conf
     ```

   - Set the maximum memory Redis can use (e.g., 100MB):

     ```bash
     maxmemory 100mb
     ```

   - Choose an eviction policy to remove the least recently used keys when Redis reaches the memory limit:

     ```bash
     maxmemory-policy allkeys-lru
     ```

   - Save the file and restart Redis:

     ```bash
     sudo systemctl restart redis-server
     ```

##### iii. Verify Redis is Running

Check that Redis is running correctly by using the following command:

```bash
redis-cli ping
```

You should see the response `PONG` if Redis is running.

---

## 2. Script and App Configuration

### a. Bash Script (`check_internet.sh`)

This script pings predefined targets (e.g., `8.8.8.8`) and logs internet status in the SQLite database (`internet_status.db`). If the internet is down for 5 consecutive checks, it triggers the power cycle of the modem via the Python script.

1. **Edit Target IPs**: You can edit the target IPs in the `TARGETS` array in `check_net.sh` if needed.

2. **Database and Log Paths**: The logs are stored in the `logs/` directory. The SQLite database (`internet_status.db`) stores the ping results.

### b. Python Power Cycle Scripts (`power_cycle_nbn.py` and 'power_cycle_nbn_override')

This script communicates with a TP-Link Tapo smart plug to power cycle the modem. You can find more information about the Tapo P100 smart plug [here](https://www.tapo.com/au/product/smart-plug/tapo-p100/).

1. **Tapo Credentials**: Update the `email`, `password`, and `device_ip` in the script with your Tapo credentials and device IP address.
   
2. **Cooldown Period**: The script includes a cooldown period (default: 10 minutes) to avoid repeated power cycling. The cooldown is tracked via the `logs/cooldown.txt` file.

---

## 3. Systemd Setup

To automate the running of the internet check script and the Dash app, you can set up systemd services and timers.

### a. Internet Check Script Service

You can use `systemd` to run the internet check script every minute.

1. **Create a Timer**: Save the following as `/etc/systemd/system/check_internet.timer`

   ```ini
   [Unit]
   Description=Runs Check Internet Connectivity Every Minute

   [Timer]
   # Run every minute
   OnCalendar=*:0/1
   AccuracySec=1s
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

2. **Create the Service**: Save the following as `/etc/systemd/system/check_internet.service`

   ```ini
   [Unit]
   Description=Check Internet Connectivity

   [Service]
   Type=oneshot
   ExecStart=/bin/bash /path/to/project/check_internet.sh
   StandardOutput=append:/path/to/project/logs/check_internet-script.log
   StandardError=append:/path/to/project/logs/check_internet-script_error.log

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable the Timer**:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now check_internet.timer
   ```

### b. Dash Web App Service

You can also set up the Dash app to run automatically on system startup.

1. **Create the Service**: Save the following as `/etc/systemd/system/dash_app.service`

   ```ini
   [Unit]
   Description=Dash App for Internet Status Monitoring
   After=network.target redis-server.service

   [Service]
   User=<your-username>
   WorkingDirectory=/path/to/project/
   ExecStart=/path/to/project/venv/bin/python3 /path/to/project/internet_status_dashboard.py
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable the Dash App Service**:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable dash_app.service
   sudo systemctl start dash_app.service
   ```

### Checking the Services

- To check if the internet check service is running properly:

   ```bash
   sudo systemctl status check_internet.service
   ```

- To check if the Dash app service is running:

   ```bash
   sudo systemctl status dash_app.service
   ```

---

## 4. Dash Web App Setup

The **Dash app** provides a web interface to monitor network connectivity and manually trigger power cycling.

1. **Run the Dash App**:
   ```bash
   cd /path/to/project/
   python3 internet_status_dashboard.py
   ```

2. **Access the App**: Navigate to `http://<your-server-ip>:8050` in a browser to access the dashboard.

---

## How It Works

1. **The Internet Check**:
   - The `check_interet.sh` script runs every minute via the systemd timer.
   - It pings 3 target IPs. If all fail for 5 consecutive attempts, it triggers the modem power cycle via the Tapo smart plug.
   - Each result is logged in an SQLite database, and details like packet loss, latency, and success rate are recorded.

2. **The Power Cycle**:
   - The `power_cycle_nbn.py` script communicates with a Tapo smart plug to power cycle the modem.
   - A cooldown period of 10 minutes ensures that consecutive power cycles do not happen too soon.

3. **The Dashboard**:
   - The Dash web app provides a graphical view of the network history and current connection satus, and a power cycle button for the tapo plug.

 It shows metrics like success rates, latency, and packet loss.
   - You can manually trigger a power cycle from the dashboard by clicking the **Power Cycle NBN Plug** button.

---

## Additional Notes

- **Logs**: All logs are stored in the `logs/` directory, and can be useful for debugging.
- **Database**: The SQLite database (`internet_status.db`) stores all the ping data for the dashboard and logs.
