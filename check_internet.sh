#!/bin/bash

# Targets array
TARGETS=("8.8.8.8" "1.1.1.1" "9.9.9.9")

# File references
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
DB_FILE="$SCRIPT_DIR/logs/internet_status.db"
FAILURE_COUNT_FILE="$SCRIPT_DIR/logs/failure_count.txt"
LOG_FILE="$SCRIPT_DIR/logs/check_internet.log"
#COOLDOWN_FILE="$SCRIPT_DIR/logs/cooldown.txt"

now=$(date '+%Y-%m-%d %H:%M:%S')
SUCCESS_COUNT=0
LATENCIES=()
PING_COUNT_PER_TARGET=5
TOTAL_COUNT=$(( ${#TARGETS[@]} * PING_COUNT_PER_TARGET ))
PING_TIMEOUT=2  # Reduced timeout for faster failure detection

# Cooldown period (10 minutes)
#COOLDOWN_PERIOD=600  # in seconds (600 seconds = 10 minutes)

# Initialize failure count file if it doesn't exist
if [ ! -f $FAILURE_COUNT_FILE ]; then
    echo "0" > $FAILURE_COUNT_FILE
fi

echo "starting..."

# Initialize SQLite database and table if not exists
sqlite3 $DB_FILE "CREATE TABLE IF NOT EXISTS internet_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    status TEXT,
    success_percentage INTEGER,
    avg_latency_ms REAL,
    max_latency_ms REAL,
    min_latency_ms REAL,
    packet_loss REAL
);" 2>> $LOG_FILE  # Log any errors

# New table for power cycle events
sqlite3 $DB_FILE "CREATE TABLE IF NOT EXISTS power_cycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    reason TEXT
);" 2>> $LOG_FILE

# Function to ping targets and collect latency
check_internet() {
    echo "checking internet..."
    for target in ${TARGETS[@]}; do
        echo "pinging" $target
        for i in $(seq 1 $PING_COUNT_PER_TARGET); do
            #PING_RESULT=$(ping -c 1 -W 5 $target | grep 'time=')
			PING_RESULT=$(ping -c 1 -W $PING_TIMEOUT $target | grep 'time=')
            if [[ $PING_RESULT ]]; then
                # Extract the latency in ms and add it to the list
                LATENCY=$(echo $PING_RESULT | sed -e 's/.*time=\([0-9.]*\).*/\1/')
                LATENCIES+=($LATENCY)
                SUCCESS_COUNT=$((SUCCESS_COUNT+1))
            fi
        done
    done
}

# Run the check
check_internet
echo "finished running internet check" >> $LOG_FILE
echo "finished running internet check"

# Calculate the success percentage
SUCCESS_PERCENTAGE=$((SUCCESS_COUNT * 100 / TOTAL_COUNT))

# Calculate average, min, max latency if there are successful pings
if [[ $SUCCESS_COUNT -gt 0 ]]; then
    AVG_LATENCY=$(echo "${LATENCIES[@]}" | awk '{for(i=1;i<=NF;i++) sum+=$i; print sum/NF}')
    MAX_LATENCY=$(echo "${LATENCIES[@]}" | awk '{for(i=1;i<=NF;i++) if($i>max) max=$i; print max}')
    MIN_LATENCY=$(echo "${LATENCIES[@]}" | awk '{for(i=1;i<=NF;i++) if(min=="" || $i<min) min=$i; print min}')
else
    AVG_LATENCY="NULL"
    MAX_LATENCY="NULL"
    MIN_LATENCY="NULL"
    
fi

# Log the calculated latencies regardless of success
echo "Latencies calculated - AVG: $AVG_LATENCY, MAX: $MAX_LATENCY, MIN: $MIN_LATENCY" >> $LOG_FILE
echo "Latencies calculated - AVG: $AVG_LATENCY, MAX: $MAX_LATENCY, MIN: $MIN_LATENCY"

# Calculate packet loss
LOSS_COUNT=$((TOTAL_COUNT - SUCCESS_COUNT))
PACKET_LOSS_PERCENTAGE=$((LOSS_COUNT * 100 / TOTAL_COUNT))

# Determine status based on success percentage
if [[ $SUCCESS_PERCENTAGE -eq 100 ]]; then
    STATUS="Internet is fully up (100% success)"
elif [[ $SUCCESS_PERCENTAGE -gt 0 ]]; then
    STATUS="Internet is partially up ($SUCCESS_PERCENTAGE% success)"
else
    STATUS="Internet is down (0% success)"
fi

# Insert log into the database with error handling
sqlite3 $DB_FILE "INSERT INTO internet_status (timestamp, status, success_percentage, avg_latency_ms, max_latency_ms, min_latency_ms, packet_loss)
VALUES ('$now', '$STATUS', $SUCCESS_PERCENTAGE, $AVG_LATENCY, $MAX_LATENCY, $MIN_LATENCY, $PACKET_LOSS_PERCENTAGE);" 2>> $LOG_FILE

if [[ $? -eq 0 ]]; then
    echo "Log successfully inserted into db" >> $LOG_FILE
    echo "Log successfully inserted into db"
else
    echo "Failed to insert log into db" >> $LOG_FILE
    echo "Failed to insert log into db"
fi

# Clean up old data (keep only last 2 weeks)
sqlite3 $DB_FILE "DELETE FROM internet_status WHERE timestamp < datetime('now', '-14 days');" 2>> $LOG_FILE

if [[ $? -eq 0 ]]; then
    echo "Old data successfully cleaned up" >> $LOG_FILE
    echo "Old data successfully cleaned up"
else
    echo "Failed to clean up old data" >> $LOG_FILE
    echo "Failed to clean up old data"
fi

# Handle consecutive failures
FAILURE_COUNT=$(cat $FAILURE_COUNT_FILE)
#echo "Failure count is: " $FAILURE_COUNT >> $LOG_FILE
#echo "Failure count is: " $FAILURE_COUNT

# Check if cooldown period is in effect
#if [ -f "$COOLDOWN_FILE" ]; then
#    last_cycle=$(cat "$COOLDOWN_FILE")
#    current_time=$(date +%s)
#    time_diff=$((current_time - last_cycle))

#    if [[ $time_diff -lt $COOLDOWN_PERIOD ]]; then
#        echo "Cooldown period is still active, skipping power cycle." >> $LOG_FILE
#        exit 0
#    fi
#fi

if [[ $SUCCESS_PERCENTAGE -eq 0 ]]; then
    # Increase failure count
    FAILURE_COUNT=$((FAILURE_COUNT + 1))
    echo $FAILURE_COUNT > $FAILURE_COUNT_FILE
    echo "Internet test failed!" >> $LOG_FILE

    FAILURE_COUNT=$(cat $FAILURE_COUNT_FILE)
    echo "Failure count is: " $FAILURE_COUNT >> $LOG_FILE

    # If failure count exceeds 5 (indicating 5 minutes of downtime), trigger modem power cycle
    if [[ $FAILURE_COUNT -ge 5 ]]; then
        echo "Internet down for 5+ minutes. Power cycling modem..." >> $LOG_FILE
        echo "Internet down for 5+ minutes. Power cycling modem..."

        # Activate the virtual environment
        source /home/dorothy/venv/bin/activate

        # Run the power cycle script within the virtual environment
        /home/dorothy/venv/bin/python3 /home/dorothy/scripts/power_cycle_nbn.py >> $LOG_FILE 2>&1  # power cycle nbn

        # Log the power cycle action with error handling
        #sqlite3 $DB_FILE "INSERT INTO internet_status (timestamp, status) VALUES ('$now', 'Modem power cycled due to network failure');" 2>> $LOG_FILE

        if [[ $? -eq 0 ]]; then
            echo "Power cycle action logged successfully" >> $LOG_FILE
            echo "Power cycle action logged successfully"
        else
            echo "Failed to log power cycle action" >> $LOG_FILE
            echo "Failed to log power cycle action"
        fi

        # Deactivate the virtual environment after running the script
        deactivate

        # Reset failure count after power cycle
        echo "0" > $FAILURE_COUNT_FILE

        # Create cooldown file with the current timestamp
        #date +%s > $COOLDOWN_FILE
    fi
else
    # Reset failure count if internet is back up
    echo "0" > $FAILURE_COUNT_FILE
fi
