# MTA GTFS Transit Data API

A Python Flask application that parses MTA GTFS realtime data and provides a publicly accessible JSON feed with train arrival information.

## Features

- Parse MTA GTFS realtime data for any NYC subway stop
- Extract route, destination, and arrival times
- Serve data as JSON via HTTP endpoint
- No API key required for subway feeds
- Support for all NYC subway lines

## Usage

### API Endpoint

```
GET /transit/<stop_id>?line=<line_id>
```

### Parameters

- `stop_id` (required): The MTA stop ID (e.g., `N02N` for 8 Avenue (N) northbound)
- `line` (optional): The subway line to query (e.g., `1`, `A`, `L`). Defaults to `1`

### Example Request

```
GET /transit/N02N?line=N
```

### Response Format

```json
{
  "stop_id": "N02N",
  "line": "N",
  "timestamp": "2025-01-01T12:00:00.000000",
  "arrivals": [
    {
      "route": "N",
      "destination": "Astoria-Ditmars Blvd",
      "scheduled_arrival": null,
      "actual_arrival": "2025-01-01T12:05:00",
      "delay": null
    }
  ]
}
```

### Response Fields

- `stop_id`: The requested stop ID
- `line`: The subway line queried
- `timestamp`: When the data was fetched
- `arrivals`: Array of upcoming trains (up to 10)
  - `route`: The train route number/letter
  - `destination`: Where the train is heading
  - `scheduled_arrival`: Scheduled arrival time from timetable (ISO 8601 format)
  - `actual_arrival`: Realtime predicted arrival time (ISO 8601 format)
  - `delay`: Delay information (e.g., "5 min late", "On time", "2 min early")

## Available Lines

  - 7th Avenue: 1, 2, 3
  - Lexington Avenue: 4, 5, 6
  - Flushing: 7
  - 8th Avenue: A, C, E
  - 6th Avenue: B, D, F, M
  - Broadway: N, Q, R, W
  - Nassau Street: J, Z
  - Crosstown: G
  - Canarsie: L
  - Shuttles: GS (Grand Central Shuttle), H (Rockaway Park Shuttle), FS (Franklin Avenue Shuttle)
  - Staten Island Railway (SIR): SI

## Finding Stop IDs

Stop IDs can be found in the MTA's static GTFS data or by using tools like:
- MTA's official website
- Transit apps that display stop IDs

Stop ID patterns:
- Northbound stops end in `N`
- Southbound stops end in `S`

TransitFeeds stops.txt file: https://openmobilitydata-data.s3-us-west-1.amazonaws.com/public/feeds/mta/79/20240103/original/stops.txt

## Technical Details

- Built with Flask
- Uses the `nyct-gtfs` library for parsing MTA realtime feeds
- Runs on port 5000
- No API key required for NYC subway data

## Running the Application

The application starts automatically and is accessible at the provided URL.

## Error Handling

If an error occurs, the API returns:

```json
{
  "error": "Error message",
  "traceback": "Detailed traceback"
}
```

## Notes

- Data is fetched in real-time from MTA feeds
- Feed updates occur approximately every 30 seconds
- Up to 10 upcoming arrivals are returned per request
- If a trip doesn't appear in the feed, it may be cancelled
- The suggested deployment app to run this Flask application is the Render Cloud Application Platform (https://www.render.com)
