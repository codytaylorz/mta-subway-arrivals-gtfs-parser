from flask import Flask, jsonify, request
from nyct_gtfs import NYCTFeed
from datetime import datetime, timedelta
import logging
import requests
import zipfile
import io
import pandas as pd
import os
from functools import lru_cache
import pytz
from datetime import timezone

# --- Configuration and Setup ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration for static GTFS files
GTFS_URL = 'http://web.mta.info/developers/data/nyct/subway/google_transit.zip'
NY_TZ = pytz.timezone('America/New_York')

# Global variables for caching static dataframes
STOP_TIMES_DF = None
TRIPS_DF = None

# Fetch MTA API Key from environment variables (Required for NYCTFeed to fetch data)
MTA_API_KEY = os.environ.get("MTA_API_KEY")
if not MTA_API_KEY:
    logger.error("!!! MTA_API_KEY environment variable not found. API calls will fail. !!!")

# Dictionary mapping Route IDs to their feeds (used by NYCTFeed for URL lookup)
RT_FEED_URLS = {
    '1': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    'A': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    'L': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    'M': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    'N': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    'G': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    'J': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    '7': "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-7",
}


# --- Static Data Loading and Caching (In-Memory) ---

@lru_cache(maxsize=1)
def get_cached_gtfs_data():
    """Download and load static GTFS dataframes in memory."""
    try:
        logger.info("Starting download and in-memory processing of static GTFS data...")
        response = requests.get(GTFS_URL, timeout=45) # Increased timeout for large file
        response.raise_for_status()
        
        stop_times_df = None
        trips_df = None

        # Process the ZIP file entirely in memory (avoiding unreliable disk I/O)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            
            # Load stop_times.txt
            with z.open('stop_times.txt') as st_file:
                stop_times_df = pd.read_csv(st_file)
            
            # Load trips.txt
            with z.open('trips.txt') as t_file:
                trips_df = pd.read_csv(t_file)
                
        logger.info(f"Successfully loaded {len(stop_times_df)} stop times and {len(trips_df)} trips into memory.")
        # Return only the necessary dataframes
        return stop_times_df, trips_df
        
    except Exception as e:
        logger.error(f"FATAL: Error during in-memory GTFS processing: {e}", exc_info=True)
        return None, None

def initialize_global_static_data():
    """Initializes the global dataframes with the cached data."""
    global STOP_TIMES_DF, TRIPS_DF
    
    STOP_TIMES_DF, TRIPS_DF = get_cached_gtfs_data()
    
    if STOP_TIMES_DF is None:
        logger.error("Static data initialization failed. Delay calculation will be skipped.")

# Run initialization once at startup
initialize_global_static_data()


def get_scheduled_time(trip_id, stop_id):
    """Get scheduled arrival time for a trip at a specific stop"""
    
    if STOP_TIMES_DF is None:
        return None
        
    try:
        # Use the global in-memory DataFrame
        match = STOP_TIMES_DF[
            (STOP_TIMES_DF['trip_id'] == trip_id) & 
            (STOP_TIMES_DF['stop_id'] == stop_id)
        ]
        
        if not match.empty:
            arrival_time_str = match.iloc[0]['arrival_time']
            
            hours, minutes, seconds = map(int, arrival_time_str.split(':'))
            today = datetime.now(NY_TZ).date()
            
            # Handle timestamps past midnight (e.g., 25:00:00)
            if hours >= 24:
                hours -= 24
                today += timedelta(days=1)
            
            naive_time = datetime.combine(today, datetime.min.time()) + timedelta(
                hours=hours, minutes=minutes, seconds=seconds
            )
            
            scheduled_time = NY_TZ.localize(naive_time)
            
            return scheduled_time
    except Exception as e:
        logger.warning(f"Error calculating scheduled time for trip {trip_id}, stop {stop_id}: {e}")
    
    return None

# --- API Endpoint ---

@app.route('/transit/<stop_id>')
def get_transit_info(stop_id):
    """
    Returns real-time subway arrivals with delay calculation for a given stop ID and line.
    Requires query parameter: line=<route_id>
    """
    route_id = request.args.get('line', '').upper()
    stop_id = stop_id.upper()
    
    if not route_id:
        return jsonify({'error': 'Missing required query parameter: line=<route_id>'}), 400

    if not MTA_API_KEY:
        return jsonify({'error': 'Configuration Error', 'message': 'MTA_API_KEY environment variable is not set.'}), 500

    try:
        # 1. Fetch Real-Time Data (Fixed: removed api_key argument)
        feed = NYCTFeed(route_id)
        feed.refresh()
        
        # 2. Parse Arrivals
        arrivals = feed.filter_stop_info(stop_id)
        
        # 3. Process and Format
        formatted_arrivals = []
        now = datetime.now(NY_TZ)
        
        for arrival in arrivals:
            
            # NYCTFeed returns UTC time, convert to NY time for display
            arrival_time_utc = datetime.fromtimestamp(arrival['time'], tz=timezone.utc)
            actual_arrival_time_ny = arrival_time_utc.astimezone(NY_TZ)
            
            countdown_minutes = max(0, int((actual_arrival_time_ny - now).total_seconds() / 60))
            
            scheduled_time = get_scheduled_time(arrival['trip_id'], stop_id)
            delay = None
            scheduled_arrival_str = None

            # --- Delay Calculation Logic ---
            if scheduled_time:
                scheduled_arrival_str = scheduled_time.strftime('%I:%M %p')
                
                # Calculate difference between actual (real-time) and scheduled time
                delay_seconds = int((actual_arrival_time_ny - scheduled_time).total_seconds())
                
                if delay_seconds >= 90: # 1.5 minutes late threshold
                    delay = f"{delay_seconds // 60} min late"
                elif delay_seconds <= -90: # 1.5 minutes early threshold
                    delay = f"{abs(delay_seconds) // 60} min early"
                else:
                    delay = "On time"
            # -------------------------------
            
            formatted_arrivals.append({
                'route_id': arrival['route_id'],
                'destination': arrival['destination'],
                'actual_arrival_time_ny': actual_arrival_time_ny.strftime('%I:%M %p'),
                'countdown_minutes': countdown_minutes,
                'scheduled_arrival_ny': scheduled_arrival_str, # ADDED
                'delay': delay # ADDED
            })
            
        # 4. Sort by actual arrival time and build final response
        formatted_arrivals.sort(key=lambda x: x['actual_arrival_time_ny'])

        response = {
            'stop_id': stop_id,
            'timestamp_ny': now.strftime('%Y-%m-%d %I:%M:%S %p'),
            'arrivals': formatted_arrivals
        }

        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error fetching transit data for stop {stop_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to fetch transit data',
            'message': 'An unexpected error occurred during real-time processing.'
        }), 500

@app.route('/')
def index():
    return jsonify({
        'message': 'MTA Subway Arrivals GTFS Parser',
        'usage': 'GET /transit/<stop_id>?line=<route_id>',
        'example': '/transit/N02N?line=N',
        'available_lines': ['1', '2', '3', '4', '5', '6', '7', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'J', 'L', 'M', 'N', 'Q', 'R', 'S', 'W', 'Z']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
