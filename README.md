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

- `stop_id` (required): The MTA stop ID (e.g., `127N` for Times Square northbound)
- `line` (optional): The subway line to query (e.g., `1`, `A`, `L`). Defaults to `1`

### Example Request

```
GET /transit/127N?line=1
```

### Response Format

```json
{
  "stop_id": "127N",
  "line": "1",
  "timestamp": "2025-10-09T21:08:00.123456",
  "arrivals": [
    {
      "route": "1",
      "destination": "Van Cortlandt Park - 242 St",
      "scheduled_arrival": null,
      "actual_arrival": "2025-10-09T21:15:30",
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

`1`, `2`, `3`, `4`, `5`, `6`, `7`, `A`, `B`, `C`, `D`, `E`, `F`, `G`, `J`, `L`, `M`, `N`, `Q`, `R`, `S`, `W`, `Z`

## Finding Stop IDs

Stop IDs can be found in the MTA's static GTFS data or by using tools like:
- MTA's official website
- Transit apps that display stop IDs
- The MTA GTFS static feed

Common stop ID patterns:
- Northbound stops often end in `N`
- Southbound stops often end in `S`

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
