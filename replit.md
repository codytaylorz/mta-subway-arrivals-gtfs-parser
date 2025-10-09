# MTA GTFS Transit Data Parser

## Overview
A Python Flask application that parses MTA GTFS realtime data for NYC subway stops and serves it as a publicly accessible JSON feed. The application provides route information, destinations, scheduled arrival times, and actual arrival times for trains at any given stop.

## Recent Changes
- **2025-10-09**: Initial implementation
  - Created Flask API with `/transit/<stop_id>` endpoint
  - Integrated nyct-gtfs library for MTA realtime data parsing
  - Added proper feed.refresh() to fetch live GTFS data
  - Integrated static GTFS data to provide scheduled arrival times
  - Implemented delay calculation between scheduled and actual arrivals
  - Added caching for static GTFS data to improve performance
  - Improved error handling with server-side logging instead of exposing tracebacks
  - Created comprehensive documentation in README.md

## Project Architecture

### Main Components
- **main.py**: Flask application serving the transit data API
  - `/transit/<stop_id>`: Main endpoint for fetching train arrivals
  - `/`: API documentation endpoint
  - Uses nyct-gtfs library for GTFS data parsing
  - Implements proper error handling and logging

### Dependencies
- Flask: Web framework for API server
- nyct-gtfs: MTA GTFS realtime data parser
- protobuf: Protocol buffer support for GTFS data
- Python 3.11: Runtime environment

### API Design
- RESTful JSON API
- Accepts stop_id as path parameter
- Optional line parameter via query string
- Returns up to 10 upcoming arrivals
- Includes route, destination, scheduled/actual arrival times, and delay information

### Data Flow
1. Client requests `/transit/<stop_id>?line=<line>`
2. Server creates NYCTFeed instance for the specified line
3. Feed is refreshed to fetch latest GTFS data
4. Server filters trips for the requested stop_id
5. Arrival data is extracted and formatted
6. JSON response is returned to client

### Error Handling
- Exceptions logged server-side with full traceback
- Generic error messages returned to clients
- No sensitive information exposed in API responses

## Technical Notes
- No API key required for NYC subway feeds (as of nyct-gtfs 2.0.0)
- Feeds update approximately every 30 seconds
- Server runs on port 5000 (required for Replit)
- Development mode enabled for easier debugging

## Next Steps / Future Enhancements
- Add caching to reduce API calls
- Support for MTA bus feeds (requires API key)
- Historical data logging
- Additional filtering options (direction, route)
- Static GTFS data integration for scheduled times
