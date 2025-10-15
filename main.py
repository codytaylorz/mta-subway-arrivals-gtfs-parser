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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

GTFS_URL = 'http://web.mta.info/developers/data/nyct/subway/google_transit.zip'
GTFS_CACHE_DIR = 'gtfs_cache'

@lru_cache(maxsize=1)
def load_static_gtfs():
    """Download and load static GTFS data, cached in memory"""
    try:
        logger.info("Downloading static GTFS data...")
        response = requests.get(GTFS_URL, timeout=30)
        response.raise_for_status()
        
        os.makedirs(GTFS_CACHE_DIR, exist_ok=True)
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(GTFS_CACHE_DIR)
        
        stop_times = pd.read_csv(f'{GTFS_CACHE_DIR}/stop_times.txt')
        trips = pd.read_csv(f'{GTFS_CACHE_DIR}/trips.txt')
        
        logger.info(f"Loaded {len(stop_times)} stop times and {len(trips)} trips")
        return stop_times, trips
    except Exception as e:
        logger.error(f"Error loading static GTFS: {e}", exc_info=True)
        return None, None

def get_scheduled_time(trip_id, stop_id):
    """Get scheduled arrival time for a trip at a specific stop"""
    try:
        stop_times, trips = load_static_gtfs()
        if stop_times is None:
            return None
        
        match = stop_times[
            (stop_times['trip_id'] == trip_id) & 
            (stop_times['stop_id'] == stop_id)
        ]
        
        if not match.empty:
            arrival_time_str = match.iloc[0]['arrival_time']
            
            hours, minutes, seconds = map(int, arrival_time_str.split(':'))
            ny_tz = pytz.timezone('America/New_York')
            today = datetime.now(ny_tz).date()
            
            if hours >= 24:
                hours -= 24
                today += timedelta(days=1)
            
            naive_time = datetime.combine(today, datetime.min.time()) + timedelta(
                hours=hours, minutes=minutes, seconds=seconds
            )
            
            scheduled_time = ny_tz.localize(naive_time)
            
            return scheduled_time
    except Exception as e:
        logger.error(f"Error getting scheduled time for trip {trip_id}, stop {stop_id}: {e}")
    
    return None

@app.route('/transit/<stop_id>')
def get_transit_data(stop_id):
    try:
        line = request.args.get('line', '1')
        
        feed = NYCTFeed(line)
        feed.refresh()
        
        arrivals = []
        
        for trip in feed.trips:
            for stop_time_update in trip.stop_time_updates:
                if stop_time_update.stop_id == stop_id:
                    actual_arrival_time = None
                    if stop_time_update.arrival:
                        actual_arrival_time = stop_time_update.arrival
                    elif stop_time_update.departure:
                        actual_arrival_time = stop_time_update.departure
                    
                    scheduled_time = get_scheduled_time(trip.trip_id, stop_id)
                    
                    delay = None
                    if scheduled_time and actual_arrival_time:
                        delay_seconds = int((actual_arrival_time - scheduled_time).total_seconds())
                        if delay_seconds >= 60:
                            delay = f"{delay_seconds // 60} min late"
                        elif delay_seconds <= -60:
                            delay = f"{abs(delay_seconds) // 60} min early"
                        else:
                            delay = "On time"
                    
                    arrival_data = {
                        'route': trip.route_id,
                        'destination': trip.headsign_text or 'Unknown',
                        'scheduled_arrival': scheduled_time.isoformat() if scheduled_time else None,
                        'actual_arrival': actual_arrival_time.isoformat() if actual_arrival_time else None,
                        'delay': delay
                    }
                    
                    arrivals.append(arrival_data)
        
        arrivals.sort(key=lambda x: x['actual_arrival'] if x['actual_arrival'] else 'Z')
        
        response = {
            'stop_id': stop_id,
            'line': line,
            'timestamp': datetime.now().isoformat(),
            'arrivals': arrivals[:10]
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error fetching transit data for stop {stop_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to fetch transit data',
            'message': 'Please check the stop ID and line parameters'
        }), 500

@app.route('/')
def index():
    return jsonify({
        'message': 'MTA Subway GTFS Parser API',
        'usage': '/transit/<stop_id>?line=<line_id>',
        'example': '/transit/127N?line=1',
        'available_lines': ['1', '2', '3', '4', '5', '6', '7', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'J', 'L', 'M', 'N', 'Q', 'R', 'S', 'W', 'Z']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
