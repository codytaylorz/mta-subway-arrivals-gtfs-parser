# main.py - MTA Subway Parser (Refactored for In-Memory Static GTFS)

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

# Global configuration constants
GTFS_URL = 'http://web.mta.info/developers/data/nyct/subway/google_transit.zip'
NY_TZ = pytz.timezone('America/New_York')

# Global variables for caching static data
# These are initialized after the cached function returns data
STOP_TIMES_DF = None
TRIPS_DF = None
STOP_NAME_MAP = {}

# --- Static Data Loading and Caching (Refactored) ---

@lru_cache(maxsize=1)
def get_cached_gtfs_data():
    """Download and load all necessary static GTFS dataframes in memory."""
    try:
        logger.info("Starting download and in-memory processing of static GTFS data...")
        response = requests.get(GTFS_URL, timeout=45) # Increased timeout for large file
        response.raise_for_status()
        
        stop_times_df = None
        trips_df = None
        stops_df = None

        # Process the ZIP file entirely in memory (using io.BytesIO)
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            
            # Load stop_times.txt
            with z.open('stop_times.txt') as st_file:
                stop_times_df = pd.read_csv(st_file)
            
            # Load trips.txt
            with z.open('trips.txt') as t_file:
                trips_df = pd.read_csv(t_file)
                
            # Load stops.txt for stop names
            with z.open('stops.txt') as s_file:
                stops_df = pd.read_csv(s_file, usecols=['stop_id', 'stop_name'])
                
        logger.info("Successfully loaded all GTFS dataframes into memory.")
        # Return all three dataframes
        return stop_times_df, trips_df, stops_df
        
    except Exception as e:
        logger.error(f"FATAL: Error during in-memory GTFS processing: {e}", exc_info=True)
        return None, None, None

def initialize_global_static_data():
    """Initializes the global variables with the cached dataframes and map."""
    global STOP_TIMES_DF, TRIPS_DF, STOP_NAME_MAP
    
    STOP_TIMES_DF, TRIPS_DF, stops_df = get_cached_gtfs_data()
    
    if stops_df is not None:
        # Map parent stop IDs (e.g., A02) to the name ("Canal St")
        STOP_NAME_MAP = stops_df.set_index('stop_id')['stop_name'].to_dict()
        logger.info(f"Initialized {len(STOP_NAME_MAP)} unique stop names.")

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
            
            # Determine the date relative to 'today' for calculating scheduled time
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
        # Log error, but do not crash the app, return None
        logger.warning(f"Error calculating scheduled time for trip {trip_id}, stop {stop_id}: {e}")
    
    return None

def get_stop_name(stop_id_with_direction):
    """Maps the full stop ID (e.g., 127N) to its stop name (e.g., 14 St - Union Sq)."""
    # The static stops.txt uses the parent ID (e.g., 127), strip the direction (N/S)
    parent_stop_id = stop_id_with_direction[:-1] if stop_id_with_direction[-1] in ('N', 'S', 'W', 'E') else stop_id_with_direction
    
    return STOP_NAME_MAP.get(parent_stop_id, 'Stop Name Unavailable')


@app.route('/transit/<stop_id>')
def get_transit_data(stop_id):
    # Check if static data loading failed at startup
    if STOP_TIMES_DF is None:
        return jsonify({
            'error': 'Static Data Load Failure',
            'message': 'Initial download of MTA GTFS files failed. Check logs for timeout or network errors.'
        }), 503
        
    try:
        line = request.args.get('line', '1').upper()
        stop_id = stop_id.upper()
        
        MTA_API_KEY = os.environ.get("MTA_API_KEY")
        if not MTA_API_KEY:
            raise ValueError("MTA_API_KEY environment variable is not set.")
            
        stop_name = get_stop_name(stop_id)
        
        # Dynamic feed fetching (requires MTA API Key)
        feed = NYCTFeed(line, api_key=MTA_API_KEY)
        feed.refresh()
        
        arrivals = []
        
        for trip in feed.trips:
            for stop_time_update in trip.stop_time_updates:
                if stop_time_update.stop_id == stop_id:
                    
                    actual_arrival_time = None
                    if stop_time_update.arrival and stop_time_update.arrival.time:
                        # Convert UTC timestamp from feed to New York time zone
                        actual_arrival_time = datetime.fromtimestamp(stop_time_update.arrival.time, tz=timezone.utc).astimezone(NY_TZ)
                    elif stop_time_update.departure and stop_time_update.departure.time:
                        actual_arrival_time = datetime.fromtimestamp(stop_time_update.departure.time, tz=timezone.utc).astimezone(NY_TZ)
                    
                    # Only process trains with a real-time update
                    if actual_arrival_time:
                        scheduled_time = get_scheduled_time(trip.trip_id, stop_id)
                        
                        delay = None
                        if scheduled_time:
                            # Calculate time difference only if we have both times
                            delay_seconds = int((actual_arrival_time - scheduled_time).total_seconds())
                            
                            if delay_seconds >= 90: 
                                delay = f"{delay_seconds // 60} min late"
                            elif delay_seconds <= -90: 
                                delay = f"{abs(delay_seconds) // 60} min early"
                            else:
                                delay = "On time"
                        
                        arrivals.append({
                            'route': trip.route_id,
                            'destination': trip.headsign_text or 'Unknown Destination',
                            'scheduled_arrival_ny': scheduled_time.strftime('%I:%M %p') if scheduled_time else 'Unavailable',
                            'actual_arrival_ny': actual_arrival_time.strftime('%I:%M %p'),
                            'delay': delay
                        })
        
        arrivals.sort(key=lambda x: x['actual_arrival_ny'])
        
        response = {
            'stop_id': stop_id,
            'stop_name': stop_name,
            'line': line,
            'timestamp': datetime.now(NY_TZ).strftime('%Y-%m-%d %I:%M:%S %p'),
            'arrivals': arrivals[:10]
        }
        
        return jsonify(response)
    
    except ValueError as ve:
        # Handles missing API key case
        logger.error(f"Configuration error: {ve}", exc_info=True)
        return jsonify({
            'error': 'Configuration Error',
            'message': str(ve)
        }), 500
    except Exception as e:
        logger.error(f"Runtime error fetching transit data for stop {stop_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to fetch transit data',
            'message': 'An unexpected error occurred during real-time processing.'
        }), 500

@app.route('/')
def index():
    return jsonify({
        'message': 'MTA Subway GTFS Parser API',
        'usage': '/transit/<stop_id>?line=<line_id>',
        'example': '/transit/N02N?line=N',
        'available_lines': ['1', '2', '3', '4', '5', '6', '7', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'J', 'L', 'M', 'N', 'Q', 'R', 'S', 'W', 'Z']
    })

if __name__ == '__main__':
    initialize_global_static_data() # Ensure local run initializes data
    app.run(host='0.0.0.0', port=5000)
