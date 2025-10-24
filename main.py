from flask import Flask, jsonify, request
from nyct_gtfs import NYCTFeed
from datetime import datetime, timedelta, timezone
import logging
import requests
import zipfile
import io
import pandas as pd
import os
from functools import lru_cache
import pytz

# --- Configuration and Setup ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global configuration constants
GTFS_URL = 'http://web.mta.info/developers/data/nyct/subway/google_transit.zip'
NY_TZ = pytz.timezone('America/New_York')

# Global variables for caching static GTFS data
STOP_TIMES_DF = None
TRIPS_DF = None

# Global cache for API responses
API_RESPONSE_CACHE = {}
CACHE_DURATION_SECONDS = 30

# Fetch MTA API Key from environment variables
MTA_API_KEY = os.environ.get("MTA_API_KEY")
if not MTA_API_KEY:
    logger.error("!!! MTA_API_KEY environment variable not found. Real-time API calls will fail. !!!")

# --- Static GTFS Data Loading (In-Memory for Stability) ---

@lru_cache(maxsize=1)
def get_cached_gtfs_data():
    """Download and load static GTFS dataframes directly into memory."""
    try:
        logger.info("Starting in-memory processing of static GTFS data...")
        response = requests.get(GTFS_URL, timeout=60) 
        response.raise_for_status()
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            with z.open('stop_times.txt') as st_file:
                stop_times_df = pd.read_csv(st_file)
            with z.open('trips.txt') as t_file:
                trips_df = pd.read_csv(t_file)
                
        logger.info(f"Successfully loaded {len(stop_times_df)} stop times and {len(trips_df)} trips.")
        return stop_times_df, trips_df
        
    except Exception as e:
        logger.error(f"FATAL: Static GTFS data loading failed: {e}", exc_info=True)
        return None, None

def initialize_global_static_data():
    """Initializes the global dataframes with the cached data."""
    global STOP_TIMES_DF, TRIPS_DF
    STOP_TIMES_DF, TRIPS_DF = get_cached_gtfs_data()

# Run initialization once at startup
initialize_global_static_data()


def get_scheduled_time(trip_id, stop_id):
    """Get scheduled arrival time for a trip at a specific stop"""
    
    if STOP_TIMES_DF is None:
        return None
        
    try:
        match = STOP_TIMES_DF[
            (STOP_TIMES_DF['trip_id'] == trip_id) & 
            (STOP_TIMES_DF['stop_id'] == stop_id)
        ]
        
        if not match.empty:
            arrival_time_str = match.iloc[0]['arrival_time']
            
            hours, minutes, seconds = map(int, arrival_time_str.split(':'))
            today = datetime.now(NY_TZ).date()
            
            # Handle times that roll past midnight (e.g., 25:00:00)
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
def get_transit_data(stop_id):
    stop_id = stop_id.upper()
    line = request.args.get('line', '1').upper()
    
    if not line:
        return jsonify({'error': 'Missing required query parameter', 'message': 'Please provide line=<route_id>.'}), 400

    if not MTA_API_KEY:
        return jsonify({'error': 'Configuration Error', 'message': 'MTA_API_KEY environment variable is not set.'}), 500

    # 1. Caching Check
    cache_key = f"{stop_id}-{line}"
    now_utc = datetime.now(timezone.utc)

    if cache_key in API_RESPONSE_CACHE:
        cache_entry = API_RESPONSE_CACHE[cache_key]
        cache_time = cache_entry['timestamp']
        if (now_utc - cache_time).total_seconds() < CACHE_DURATION_SECONDS:
            logger.info(f"Cache hit for {cache_key}. Returning cached data.")
            return jsonify(cache_entry['response'])
        logger.info(f"Cache expired for {cache_key}. Re-fetching.")
    
    # Check if static data is loaded before attempting delay calculation
    if STOP_TIMES_DF is None:
        logger.error("Static schedule data is not available. Delay calculation will fail.")


    try:
        # 2. Fetch Real-Time Data (Cache Miss)
        feed = NYCTFeed(line)
        feed.refresh()
        
        formatted_arrivals = []
        now_ny = datetime.now(NY_TZ)
        
        for trip in feed.trips:
            for stop_time_update in trip.stop_time_updates:
                if stop_time_update.stop_id == stop_id:
                    
                    actual_arrival_time = None
                    
                    # --- FIX APPLIED HERE: Use the datetime object directly ---
                    # The library returns a full datetime object, not a timestamp
                    if stop_time_update.arrival:
                        actual_arrival_time = stop_time_update.arrival 
                    elif stop_time_update.departure:
                        actual_arrival_time = stop_time_update.departure
                    # -----------------------------------------------------

                    if not actual_arrival_time:
                        continue # Skip if no actual time is available
                        
                    # The object from nyct-gtfs is already timezone-aware (UTC),
                    # so we just need to convert it to NY time.
                    actual_arrival_time_ny = actual_arrival_time.astimezone(NY_TZ)
                    
                    countdown_minutes = max(0, int((actual_arrival_time_ny - now_ny).total_seconds() / 60))
                    
                    scheduled_time = get_scheduled_time(trip.trip_id, stop_id)
                    delay = None
                    scheduled_arrival_str = None

                    # --- Delay Calculation Logic ---
                    if scheduled_time:
                        scheduled_arrival_str = scheduled_time.strftime('%I:%M %p')
                        delay_seconds = int((actual_arrival_time_ny - scheduled_time).total_seconds())
                        
                        if delay_seconds >= 60:
                            delay = f"{delay_seconds // 60} min late"
                        elif delay_seconds <= -60:
                            delay = f"{abs(delay_seconds) // 60} min early"
                        else:
                            delay = "On time"
                    # -------------------------------
                    
                    formatted_arrivals.append({
                        'route_id': trip.route_id,
                        'destination': trip.headsign_text,
                        'actual_arrival_time_ny': actual_arrival_time_ny.strftime('%I:%M %p'),
                        'countdown_minutes': countdown_minutes,
                        'scheduled_arrival_ny': scheduled_arrival_str,
                        'delay': delay
                    })
            
        formatted_arrivals.sort(key=lambda x: x['actual_arrival_time_ny'])

        response = {
            'stop_id': stop_id,
            'line': line,
            'timestamp_ny': now_ny.strftime('%Y-%m-%d %I:%M:%S %p'),
            'arrivals': formatted_arrivals
        }

        # 3. Cache the new response
        API_RESPONSE_CACHE[cache_key] = {
            'timestamp': now_utc,
            'response': response
        }
        
        return jsonify(response)
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error during feed refresh: {e}")
        return jsonify({
            'error': 'MTA API Error',
            'message': 'Failed to fetch real-time data from MTA (check API key validity or network status).'
        }), 503
    except Exception as e:
        # Catch all other errors
        logger.error(f"General runtime error fetching transit data for stop {stop_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to fetch transit data',
            'message': 'A general error occurred during real-time processing. Check server logs for details.'
        }), 500

@app.route('/')
def index():
    return jsonify({
        'message': 'MTA Subway GTFS Real-Time Parser (Cached and Stabilized)',
        'usage': 'GET /transit/<stop_id>?line=<route_id>',
        'example': 'To get N-trains at Astoria Blvd (N02N): /transit/N02N?line=N',
        'caching': 'Responses are cached for 30 seconds per unique stop/line combination.',
        'required_api_key': 'MTA_API_KEY environment variable'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
