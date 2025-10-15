# main.py - MTA Subway Parser with Stop Names and Delay

from flask import Flask, jsonify, request
from nyct_gtfs import NYCTFeed
from datetime import datetime, timedelta, date
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
GTFS_CACHE_DIR = 'gtfs_cache'
NY_TZ = pytz.timezone('America/New_York')

# Global variables for caching static data
STOP_NAME_MAP = {}

# --- Static Data Loading and Caching ---

@lru_cache(maxsize=1)
def load_static_gtfs_files():
    """Download and extract stops.txt, stop_times.txt, and trips.txt from GTFS zip."""
    try:
        logger.info("Downloading static GTFS data...")
        response = requests.get(GTFS_URL, timeout=30)
        response.raise_for_status()
        
        # We don't need a disk cache for the stop names lookup, but we keep the folder structure
        # if the goal is to calculate scheduled time from local files.
        os.makedirs(GTFS_CACHE_DIR, exist_ok=True)
        
        stop_times_df = None
        trips_df = None
        stops_df = None

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            
            # Load stop_times.txt
            with z.open('stop_times.txt') as st_file:
                stop_times_df = pd.read_csv(st_file)
            
            # Load trips.txt
            with z.open('trips.txt') as t_file:
                trips_df = pd.read_csv(t_file)
                
            # --- NEW: Load stops.txt for stop names ---
            with z.open('stops.txt') as s_file:
                # Only load the stop_id and stop_name columns
                stops_df = pd.read_csv(s_file, usecols=['stop_id', 'stop_name'])
                
        logger.info(f"Loaded static data: {len(stop_times_df)} stop times, {len(trips_df)} trips, {len(stops_df)} stops.")
        return stop_times_df, trips_df, stops_df
        
    except Exception as e:
        logger.error(f"Error loading static GTFS: {e}", exc_info=True)
        return None, None, None

def initialize_stop_name_map():
    """Initializes the global stop name map from the loaded stops DataFrame."""
    global STOP_NAME_MAP
    
    # Check cache first to avoid re-running if a map already exists
    if STOP_NAME_MAP:
        return
        
    _, _, stops_df = load_static_gtfs_files()
    
    if stops_df is not None:
        # Map parent stop IDs (e.g., A02) to the name ("Canal St")
        STOP_NAME_MAP = stops_df.set_index('stop_id')['stop_name'].to_dict()
        logger.info(f"Successfully mapped {len(STOP_NAME_MAP)} unique stop names.")

# Run initialization once at startup
initialize_stop_name_map()


def get_scheduled_time(trip_id, stop_id):
    """Get scheduled arrival time for a trip at a specific stop"""
    try:
        # Load the data frames from the cache (lru_cache ensures they're only downloaded once)
        stop_times, _, _ = load_static_gtfs_files()
        
        if stop_times is None:
            return None
        
        match = stop_times[
            (stop_times['trip_id'] == trip_id) & 
            (stop_times['stop_id'] == stop_id)
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
        logger.error(f"Error getting scheduled time for trip {trip_id}, stop {stop_id}: {e}")
    
    return None

def get_stop_name(stop_id_with_direction):
    """Maps the full stop ID (e.g., 127N) to its stop name (e.g., 14 St - Union Sq)."""
    # The static stops.txt uses the parent ID (e.g., 127), strip the direction (N/S)
    parent_stop_id = stop_id_with_direction[:-1] if stop_id_with_direction[-1] in ('N', 'S', 'W', 'E') else stop_id_with_direction
    
    return STOP_NAME_MAP.get(parent_stop_id, 'Stop Name Unavailable')


@app.route('/transit/<stop_id>')
def get_transit_data(stop_id):
    try:
        line = request.args.get('line', '1').upper()
        stop_id = stop_id.upper()
        
        # --- NEW: Get Stop Name ---
        stop_name = get_stop_name(stop_id)
        
        # Dynamic feed fetching (requires MTA API Key)
        MTA_API_KEY = os.environ.get("MTA_API_KEY")
        feed = NYCTFeed(line, api_key=MTA_API_KEY)
        feed.refresh()
        
        arrivals = []
        
        for trip in feed.trips:
            for stop_time_update in trip.stop_time_updates:
                if stop_time_update.stop_id == stop_id:
                    
                    actual_arrival_time = None
                    if stop_time_update.arrival and stop_time_update.arrival.time:
                        actual_arrival_time = datetime.fromtimestamp(stop_time_update.arrival.time, tz=timezone.utc).astimezone(NY_TZ)
                    elif stop_time_update.departure and stop_time_update.departure.time:
                        actual_arrival_time = datetime.fromtimestamp(stop_time_update.departure.time, tz=timezone.utc).astimezone(NY_TZ)
                    
                    # Only process trains with a real-time update
                    if actual_arrival_time:
                        scheduled_time = get_scheduled_time(trip.trip_id, stop_id)
                        
                        delay = None
                        if scheduled_time and actual_arrival_time:
                            # Calculate delay
                            delay_seconds = int((actual_arrival_time - scheduled_time).total_seconds())
                            
                            if delay_seconds >= 90: # 1.5 minutes late
                                delay = f"{delay_seconds // 60} min late"
                            elif delay_seconds <= -90: # 1.5 minutes early
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
            'stop_name': stop_name, # ADDED STOP NAME
            'line': line,
            'timestamp': datetime.now(NY_TZ).strftime('%Y-%m-%d %I:%M:%S %p'),
            'arrivals': arrivals[:10]
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error fetching transit data for stop {stop_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to fetch transit data',
            'message': 'Please check the stop ID and line parameters. Ensure the MTA_API_KEY is set.'
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
    app.run(host='0.0.0.0', port=5000)
