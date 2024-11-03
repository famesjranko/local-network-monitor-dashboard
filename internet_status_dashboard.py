import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import pandas as pd
import subprocess
import datetime
import sqlite3
from flask_caching import Cache
import redis
import os
import sys
import logging
import socket

SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0])) 

# Configure logging
logging.basicConfig(level=logging.INFO)

# Set up logging configuration
logging.basicConfig(
    filename=os.path.join(SCRIPT_DIR, 'logs/dashboard.log'),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server  # Expose the Flask server for caching

# Configure caching with Redis using environment variables for security
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')  # can set this in your environment

cache = Cache(app.server, config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_URL': REDIS_URL,
    'CACHE_DEFAULT_TIMEOUT': 60,  # Cache timeout in seconds (5 minutes)
})

# Function to read and parse data from the SQLite database
def parse_log(db_path):
    """
    Fetches all records from the internet_status table.
    """
    try:
        conn = sqlite3.connect(db_path)
        query = """
        SELECT timestamp,
               status AS status_message,
               success_percentage AS success,
               avg_latency_ms,
               max_latency_ms,
               min_latency_ms,
               packet_loss
        FROM internet_status
        """
        df = pd.read_sql_query(query, conn)
        # Convert the 'timestamp' column to datetime type
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # Ensure numeric columns are indeed numeric
        numeric_columns = ['success', 'avg_latency_ms', 'max_latency_ms', 'min_latency_ms', 'packet_loss']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')  # Convert, setting errors to NaN
        # Cap the values to prevent outliers
        df['avg_latency_ms'] = df['avg_latency_ms'].clip(upper=500)  # Updated to 500ms as per user
        df['max_latency_ms'] = df['max_latency_ms'].clip(upper=500)
        df['min_latency_ms'] = df['min_latency_ms'].clip(upper=500)
        df['packet_loss'] = df['packet_loss'].clip(upper=100)
        conn.close()
        logger.info("Data parsed successfully from the database.")
        return df
    except Exception as e:
        logger.error(f"Error parsing log: {e}")
        return pd.DataFrame()  # Return empty DataFrame on error

# Function to filter data based on the selected date range
def filter_data_by_date(log_data, date_range):
    """
    Filters the log data based on the selected date range.
    """
    now = pd.to_datetime(datetime.datetime.now())

    if date_range == 'last_12_hours':
        start_date = now - pd.DateOffset(hours=12)
    elif date_range == 'last_24_hours':
        start_date = now - pd.DateOffset(hours=24)
    elif date_range == 'last_48_hours':
        start_date = now - pd.DateOffset(hours=48)
    elif date_range == 'last_7_days':
        start_date = now - pd.DateOffset(days=7)
    else:
        return log_data  # For 'all_time', no filtering

    # Filter the data by the calculated date range
    filtered_data = log_data[log_data['timestamp'] >= start_date]
    logger.info(f"Data filtered for date range: {date_range}")
    return filtered_data

# Cached data fetching function with error handling
@cache.memoize(timeout=300)  # Cache timeout of 5 minutes
def get_filtered_data(db_path, date_range):
    """
    Retrieves filtered data from the database, utilizing Redis for caching.
    """
    try:
        df = parse_log(db_path)
        if df.empty:
            logger.warning("Parsed DataFrame is empty.")
            return []
        filtered_df = filter_data_by_date(df, date_range)
        if filtered_df.empty:
            logger.warning("Filtered DataFrame is empty after applying date range.")
            return []
        # Select only necessary columns for caching to reduce memory usage
        columns_to_cache = ['timestamp', 'success', 'avg_latency_ms', 'max_latency_ms', 'min_latency_ms', 'packet_loss']
        logger.info(f"Returning filtered data with {len(filtered_df)} records.")
        return filtered_df[columns_to_cache].to_dict('records')
    except Exception as e:
        logger.error(f"Redis Cache Error: {e}")
        # Fallback to fetching data without caching
        df = parse_log(db_path)
        filtered_df = filter_data_by_date(df, date_range)
        return filtered_df.to_dict('records') if not filtered_df.empty else []

# Function to calculate dynamic y-axis range with buffer and capping
def calculate_y_range(data_series, absolute_max, buffer_ratio=0.1):
    """
    Calculates the y-axis range dynamically with an absolute maximum limit.
    """
    if data_series.empty:
        return [0, absolute_max]
    data_max = data_series.max()
    # Add a buffer to the max value
    dynamic_max = data_max * (1 + buffer_ratio)
    # Ensure the dynamic max does not exceed the absolute maximum
    y_max = min(dynamic_max, absolute_max)
    return [0, y_max]

# Function to check internet connection
def is_internet_up():
    try:
        # Connect to Google Public DNS to check internet
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

# Dashboard layout
app.layout = html.Div([
    # Centered heading
    html.Div([
        html.H1("Network Health Monitoring", style={'color': '#00ccff', 'margin': '0', 'textAlign': 'center'})
    ], style={'padding': '10px 0', 'backgroundColor': '#1e1e1e', 'borderRadius': '8px', 'marginBottom': '20px', 'font-family': 'Arial, sans-serif'}),

    # Row with internet status badge on the left and power cycle button on the right
    html.Div([
        # Internet connection status styled as a badge on the left
        html.Div(id='internet-status', style={
            'textAlign': 'center',
            'fontSize': '18px',
            'padding': '8px 15px',
            'borderRadius': '5px',
            'color': '#FFFFFF',
            'fontWeight': 'bold',
            #'width': '180px'
        }),

        html.Div([], style={'display': 'flex', 'alignItems': 'center'}),

        # Power cycle button on the right
        html.Div([
            html.Button(
                'Restart NBN',
                id='power-cycle-button',
                n_clicks=0,
                style={
                    'backgroundColor': '#00ccff',
                    'color': '#1e1e1e',              # Match badge color
                    'border': 'none',
                    'padding': '8px 15px',           # Match badge padding
                    'border-radius': '5px',
                    'font-size': '18px',             # Match badge font size
                    'font-weight': 'bold',           # Match badge font weight
                    'font-family': 'Arial, sans-serif', # Match badge font family
                    'cursor': 'pointer'
                }
            ),
            html.Div(id='power-cycle-status', style={'color': '#00ccff', 'margin-top': '10px'}),
        ], style={'display': 'flex', 'alignItems': 'center'}) 
    ], style={
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'backgroundColor': '#1e1e1e',
        'padding': '10px 20px',
        'border-radius': '8px',
        'margin-bottom': '20px'
    }),

    # Date range selector
    html.Div([
        html.H4("Select Date Range", style={'color': '#ffffff'}),
        dcc.Dropdown(
            id='date-range-dropdown',
            options=[
                {'label': 'Last 12 Hours', 'value': 'last_12_hours'},
                {'label': 'Last 24 Hours', 'value': 'last_24_hours'},
                {'label': 'Last 48 Hours', 'value': 'last_48_hours'},
                {'label': 'Last 7 Days', 'value': 'last_7_days'},
                {'label': 'All Time', 'value': 'all_time'}
            ],
            value='last_12_hours',
            clearable=False,
            style={'backgroundColor': '#121212', 'color': '#00ccff'},
            className='dropdown',
        )
    ], style={'backgroundColor': '#121212', 'padding': '10px', 'border-radius': '8px'}),

    # Store for filtered data
    dcc.Store(id='filtered-data'),

    # Status counts section
    html.Div([
        html.Div([
            html.H4(id="full-up-count", style={'color': '#00ccff'}),
            html.H4(id="partial-up-count", style={'color': '#ffcc00'}),
            html.H4(id="down-count", style={'color': '#ff6666'})
        ], style={'display': 'flex', 'justify-content': 'space-around', 'color': '#ffffff'})
    ], style={'backgroundColor': '#1e1e1e', 'padding': '10px', 'border-radius': '8px', 'margin-top': '10px'}),

    # Graphs within Loading components
    dcc.Loading(dcc.Graph(id="success-graph"), type="default"),

    # Latency metrics selector
    html.Div([
        dcc.Checklist(
            id='latency-metrics-checkbox',
            options=[
                {'label': 'Average Latency (ms)', 'value': 'avg_latency_ms'},
                {'label': 'Maximum Latency (ms)', 'value': 'max_latency_ms'},
                {'label': 'Minimum Latency (ms)', 'value': 'min_latency_ms'},
            ],
            value=['avg_latency_ms', 'max_latency_ms', 'min_latency_ms'],
            labelStyle={'display': 'inline-block', 'margin-right': '10px', 'color': '#ffffff'},
            inputStyle={"margin-right": "5px"}
        )
    ], style={'backgroundColor': '#121212', 'padding': '10px', 'border-radius': '8px', 'margin-top': '10px'}),

    dcc.Loading(dcc.Graph(id="latency-graph"), type="default"),

    html.Div([], style={'backgroundColor': '#121212', 'padding': '10px', 'border-radius': '8px', 'margin-top': '10px'}),

    dcc.Loading(dcc.Graph(id="packetloss-graph"), type="default"),

    # Detailed Log Entries table within Loading component
    html.Div([
        html.H4("Detailed Log Entries", style={'color': '#ffffff'}),
        dcc.Loading(
            dash_table.DataTable(
                id='log-table',
                style_table={'overflowX': 'auto', 'backgroundColor': '#333', 'color': '#fff'},
                style_cell={'textAlign': 'left', 'backgroundColor': '#333', 'color': '#fff'},
                page_size=10,
            ),
            type="default"
        )
    ], style={'margin-top': '20px', 'backgroundColor': '#1e1e1e', 'padding': '10px', 'border-radius': '8px'}),

    # Interval for refreshing the data every 30 minutes
    dcc.Interval(
        id='interval-component',
        interval=30 * 60 * 1000,  # 30 minutes in milliseconds
        n_intervals=0
    ),

    # Interval for checking the internet connection every 10 seconds
    dcc.Interval(id='internet-interval', interval=10 * 1000, n_intervals=0)  # Check every 10 seconds

], style={'backgroundColor': '#121212', 'padding': '20px'})


# Callback to fetch and store filtered data
@app.callback(
    Output('filtered-data', 'data'),
    [
        Input('interval-component', 'n_intervals'),
        Input('date-range-dropdown', 'value')
    ]
)
def fetch_data(n, date_range):
    # Determine the directory of the current script
    SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
    db_path = os.path.join(SCRIPT_DIR, 'logs/internet_status.db')
    
    filtered_data = get_filtered_data(db_path, date_range)
    return filtered_data

# Callback to update graphs and counts based on stored data and selected metrics
@app.callback(
    [
        Output('success-graph', 'figure'),
        Output('latency-graph', 'figure'),
        Output('packetloss-graph', 'figure'),
        Output('log-table', 'data'),
        Output('full-up-count', 'children'),
        Output('partial-up-count', 'children'),
        Output('down-count', 'children')
    ],
    [
        Input('filtered-data', 'data'),
        Input('latency-metrics-checkbox', 'value')  # New Input for selected metrics
    ]
)
def update_dashboard(filtered_data, selected_latency_metrics):
    df = pd.DataFrame(filtered_data)

    # Debug: Check the DataFrame
    logger.info("Update Dashboard Callback:")
    logger.info(f"Number of records: {len(df)}")
    if not df.empty:
        logger.info(f"Timestamp range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    logger.debug(f"Data Head:\n{df.head()}")
    logger.debug(f"Data Tail:\n{df.tail()}")

    # Fetch NBN power cycle events from the SQLite database
    SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
    db_path = os.path.join(SCRIPT_DIR, 'logs/internet_status.db')
    
    logger.info("Attempting to fetch NBN power cycle events from the database.")
    try:
        conn = sqlite3.connect(db_path)
        power_cycle_query = "SELECT timestamp FROM power_cycle_events"
        power_cycle_df = pd.read_sql_query(power_cycle_query, conn)
        conn.close()
        logger.info(f"Successfully fetched {len(power_cycle_df)} power cycle events.")
        
        # Ensure power cycle timestamps are in datetime format
        power_cycle_df['timestamp'] = pd.to_datetime(power_cycle_df['timestamp'])
        
        if not power_cycle_df.empty:
            logger.info(f"Power cycle events timestamp range: {power_cycle_df['timestamp'].min()} to {power_cycle_df['timestamp'].max()}")
            logger.debug(f"Power Cycle Events Data Head:\n{power_cycle_df.head()}")
            logger.debug(f"Power Cycle Events Data Tail:\n{power_cycle_df.tail()}")
        else:
            logger.warning("No power cycle events found in the database.")
    except Exception as e:
        logger.error(f"Failed to fetch power cycle events: {e}")

    if df.empty:
        # Handle empty DataFrame
        success_fig = {}
        latency_fig = {}
        packetloss_fig = {}
        table_data = []
        full_up_count = "Fully Up: 0"
        partial_up_count = "Partially Up: 0"
        down_count = "Down: 0"
        return success_fig, latency_fig, packetloss_fig, table_data, full_up_count, partial_up_count, down_count

    # Define absolute maximum limits
    ABSOLUTE_MAX_LATENCY = 500  # in milliseconds
    ABSOLUTE_MAX_PACKET_LOSS = 100  # in percentage

    # Ensure the DataFrame is sorted by timestamp
    df.sort_values('timestamp', inplace=True)

    # Calculate dynamic y-axis ranges based on selected metrics
    if selected_latency_metrics:
        # Extract the relevant columns based on selection
        latency_data = df[selected_latency_metrics]
        # Determine the maximum value among the selected metrics
        max_latency = latency_data.max().max()
        # Calculate dynamic y-axis range with buffer, capping at ABSOLUTE_MAX_LATENCY
        dynamic_max_latency = min(max_latency * 1.1, ABSOLUTE_MAX_LATENCY)
        latency_y_range = [0, dynamic_max_latency]
    else:
        # If no metrics are selected, set y-axis to default or minimal range
        latency_y_range = [0, ABSOLUTE_MAX_LATENCY]  # Alternatively, set to [0,1]

    ## Marker options:
    ##  'circle'
    ##  'square'
    ##  'diamond'
    ##  'cross'
    ##  'x'
    ##  'triangle-up', 'triangle-down', 'triangle-left', 'triangle-right'
    ##  'star', 'hexagram', 'pentagon'
    ##  'hourglass', 'bowtie'
    ##  'hexagon', 'octagon'

    # Success rate graph using Scattergl for better performance
    success_fig = {
        'data': [
            {
                'x': df['timestamp'],
                'y': df['success'],
                'type': 'scattergl',  # Use Scattergl for better performance with large datasets
                'mode': 'lines',
                'name': 'Success Rate (%)',
                'line': {'color': '#00ccff', 'width': 2},
                'marker': {'size': 5, 'symbol': 'circle'}
            },
            # Adding power cycle markers
            {
                'x': power_cycle_df['timestamp'],
                'y': [50] * len(power_cycle_df),  # Place markers at the middle (50%) of the success graph
                'mode': 'markers',
                'name': 'NBN Power Cycle',
                'marker': {'color': 'red', 'size': 24, 'symbol': 'square'},
                'text': ['NBN Power Cycle Event'] * len(power_cycle_df),  # Hover label for each marker
                'hoverinfo': 'text+x'  # Display timestamp and custom text on hover
            },
        ],
        'layout': {
            'title': 'Internet Connectivity Over Time',
            'yaxis': {
                'title': 'Ping Response Success Rate (%)',
                'range': [0, 100],
                'color': '#ffffff'
            },
            'xaxis': {
                'title': 'Timestamp',
                'color': '#ffffff',
                'range': [df['timestamp'].min(), df['timestamp'].max()]
            },
            'plot_bgcolor': '#1e1e1e',
            'paper_bgcolor': '#1e1e1e',
            'font': {'color': '#ffffff'},
            'titlefont': {'color': '#00ccff'},
            'legend': {
                'orientation': 'h',
                'x': 0,
                'y': -0.2  # Position below the graph
            },
            'hovermode': 'closest',
        }
    }

    # Latency graph using Scattergl with dynamic y-axis range
    if selected_latency_metrics:
        # Prepare data traces based on selected metrics
        latency_traces = []
        color_mapping = {
            'avg_latency_ms': '#ffcc00',
            'max_latency_ms': '#ff6666',
            'min_latency_ms': '#66ff66'
        }
        name_mapping = {
            'avg_latency_ms': 'Avg Latency (ms)',
            'max_latency_ms': 'Max Latency (ms)',
            'min_latency_ms': 'Min Latency (ms)'
        }
        for metric in selected_latency_metrics:
            latency_traces.append({
                'x': df['timestamp'],
                'y': df[metric],
                'type': 'scattergl',
                'mode': 'lines',
                'name': name_mapping.get(metric, metric),
                'line': {'color': color_mapping.get(metric, '#000000'), 'width': 2},
                'marker': {'size': 5, 'symbol': 'circle'}
            })
    else:
        latency_traces = []

    if selected_latency_metrics:
        latency_fig = {
            'data': latency_traces,
            'layout': {
                'title': 'Latency Over Time',
                'yaxis': {
                    'title': 'Latency (ms)',
                    'range': latency_y_range,
                    'color': '#ffffff'
                },
                'xaxis': {
                    'title': 'Timestamp',
                    'color': '#ffffff',
                    'range': [df['timestamp'].min(), df['timestamp'].max()]
                },
                'plot_bgcolor': '#1e1e1e',
                'paper_bgcolor': '#1e1e1e',
                'font': {'color': '#ffffff'},
                'titlefont': {'color': '#ffcc00'},
                'legend': {
                    'orientation': 'h',
                    'x': 0,
                    'y': -0.2
                },
                'hovermode': 'closest',
            }
        }
    else:
        # Display a placeholder message when no metrics are selected
        latency_fig = {
            'data': [],
            'layout': {
                'title': 'Latency Over Time',
                'yaxis': {
                    'title': 'Latency (ms)',
                    'range': [0, ABSOLUTE_MAX_LATENCY],
                    'color': '#ffffff'
                },
                'xaxis': {
                    'title': 'Timestamp',
                    'color': '#ffffff',
                    'range': [df['timestamp'].min(), df['timestamp'].max()]
                },
                'annotations': [
                    {
                        'text': "Please select at least one latency metric to display.",
                        'xref': "paper",
                        'yref': "paper",
                        'showarrow': False,
                        'font': {
                            'size': 16,
                            'color': '#ffffff'
                        }
                    }
                ],
                'plot_bgcolor': '#1e1e1e',
                'paper_bgcolor': '#1e1e1e',
                'font': {'color': '#ffffff'},
                'titlefont': {'color': '#ffcc00'},
                'legend': {
                    'orientation': 'h',
                    'x': 0,
                    'y': -0.2
                },
                'hovermode': 'closest',
            }
        }

    # Packet Loss graph using Scattergl with dynamic y-axis range
    packetloss_y_range = calculate_y_range(df['packet_loss'], ABSOLUTE_MAX_PACKET_LOSS)
    
    packetloss_fig = {
        'data': [
            {
                'x': df['timestamp'],
                'y': df['packet_loss'],
                'type': 'scattergl',
                'mode': 'lines',
                'name': 'Packet Loss (%)',
                'line': {'color': '#ff0000', 'width': 2},
                'marker': {'size': 5, 'symbol': 'circle'}
            },
        ],
        'layout': {
            'title': 'Packet Loss Over Time',
            'yaxis': {
                'title': 'Packet Loss (%)',
                'range': [0, packetloss_y_range[1]],  # Dynamic range
                'color': '#ffffff'
            },
            'xaxis': {
                'title': 'Timestamp',
                'color': '#ffffff',
                'range': [df['timestamp'].min(), df['timestamp'].max()]
            },
            'plot_bgcolor': '#1e1e1e',
            'paper_bgcolor': '#1e1e1e',
            'font': {'color': '#ffffff'},
            'titlefont': {'color': '#ff0000'},
            'hovermode': 'closest',
        }
    }

    # Sort by the 'timestamp' in descending order for the table
    filtered_data_sorted = df.sort_values(by='timestamp', ascending=False)
    table_data = filtered_data_sorted.to_dict('records')

    # Calculate status counts based on raw data
    full_up_count = f"Fully Up: {df[df['success'] == 100].shape[0]}"
    partial_up_count = f"Partially Up: {df[(df['success'] > 0) & (df['success'] < 100)].shape[0]}"
    down_count = f"Down: {df[df['success'] == 0].shape[0]}"

    return success_fig, latency_fig, packetloss_fig, table_data, full_up_count, partial_up_count, down_count


# Callback to handle the button click
@app.callback(
    Output('power-cycle-status', 'children'),
    Input('power-cycle-button', 'n_clicks')
)
def trigger_power_cycle(n_clicks):
    if n_clicks > 0:
        # Run the external script using subprocess
        try:
            SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
            script_path = os.path.join(SCRIPT_DIR, 'power_cycle_nbn_override.py')
            result = subprocess.run(["/usr/bin/python3", script_path], check=True, capture_output=True, text=True)
            return f"Power cycle triggered at {datetime.datetime.now()}"
        except subprocess.CalledProcessError as e:
            return f"Power cycle failed: {e.stderr}"
    return ""

# Callback to update the internet connection status with dynamic color
@app.callback(
    Output('internet-status', 'children'),
    Output('internet-status', 'style'),
    Input('internet-interval', 'n_intervals')
)
def update_internet_status(n):
    if is_internet_up():
        return "Internet: Up", {
            'backgroundColor': '#4CAF50',  # Green background for up
            'color': '#1e1e1e',  # White text
            'textAlign': 'center',
            'fontSize': '18px',
            'padding': '8px 15px',
            'borderRadius': '5px',
            'fontWeight': 'bold',
            'font-family': 'Arial, sans-serif', # Match badge font family
            #'width': '180px'
        }
    else:
        return "Internet: Down", {
            'backgroundColor': '#ff6666',  # Red background for down
            'color': '#1e1e1e',  # White text
            'textAlign': 'center',
            'fontSize': '18px',
            'padding': '8px 15px',
            'borderRadius': '5px',
            'fontWeight': 'bold',
            'font-family': 'Arial, sans-serif', # Match badge font family
            #'width': '180px'
        }

if __name__ == '__main__':
    # Ensure Redis server is running and accessible
    app.run_server(host='0.0.0.0', port=8050, debug=False)
