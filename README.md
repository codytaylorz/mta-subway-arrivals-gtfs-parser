# MTA Subway GTFS Parser API

A Python Flask application that parses MTA subway GTFS realtime data and provides a publicly accessible JSON feed with subway  arrival information.

## Features

- Parse MTA GTFS realtime data for any NYC subway stop
- Extract route, destination, and arrival times
- Serve data as JSON via HTTP endpoint
- Free API key required for subway feeds
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
  "line": "N",
  "stop_id": "N02N",
  "timestamp": "2000-01-01T12:00:00.000000",
  "arrivals": [
    {
      "destination": "Astoria-Ditmars Blvd",
      "delay": null,
      "route": "N",
      "actual_arrival": "2000-01-01T12:05:00"
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
  - `actual_arrival`: Realtime predicted arrival time (ISO 8601 format)

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

## Getting an API Key

Go to the MTA BusTime Developer Site (https://bustime.mta.info/wiki/Developers/Index) and click on the link to request an API key (https://register.developer.obanyc.com). The key should arrive in your email in about 30 minutes, and should be a combination of letters and numbers seperated by hyphens (dashes). You can use this key for all MTA BusTime and GTFS-RT feeds.

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
- Arrival times are in UTC (Coordinated Universal Time)
- If a trip doesn't appear in the feed, it may be cancelled
- The suggested deployment app to run this Flask application is the Render Cloud Application Platform (https://www.render.com)
