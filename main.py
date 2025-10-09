from flask import Flask, jsonify, request
from nyct_gtfs import NYCTFeed
from datetime import datetime
import traceback

app = Flask(__name__)

@app.route('/transit/<stop_id>')
def get_transit_data(stop_id):
    try:
        line = request.args.get('line', '1')
        
        feed = NYCTFeed(line)
        
        arrivals = []
        
        for trip in feed.trips:
            for stop_time_update in trip.stop_time_updates:
                if stop_time_update.stop_id == stop_id:
                    arrival_data = {
                        'route': trip.route_id,
                        'destination': trip.headsign_text or 'Unknown',
                        'scheduled_arrival': None,
                        'actual_arrival': None,
                        'delay': None
                    }
                    
                    if stop_time_update.arrival:
                        arrival_data['actual_arrival'] = datetime.fromtimestamp(
                            stop_time_update.arrival
                        ).isoformat()
                    
                    if stop_time_update.departure:
                        if not arrival_data['actual_arrival']:
                            arrival_data['actual_arrival'] = datetime.fromtimestamp(
                                stop_time_update.departure
                            ).isoformat()
                    
                    arrivals.append(arrival_data)
        
        arrivals.sort(key=lambda x: x['actual_arrival'] if x['actual_arrival'] else '')
        
        response = {
            'stop_id': stop_id,
            'line': line,
            'timestamp': datetime.now().isoformat(),
            'arrivals': arrivals[:10]
        }
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/')
def index():
    return jsonify({
        'message': 'MTA GTFS Transit Data API',
        'usage': '/transit/<stop_id>?line=<line_id>',
        'example': '/transit/127N?line=1',
        'available_lines': ['1', '2', '3', '4', '5', '6', '7', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'J', 'L', 'M', 'N', 'Q', 'R', 'S', 'W', 'Z']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
