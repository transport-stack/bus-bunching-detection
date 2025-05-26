# Bus Bunching Detection

This module detects instances of bus bunching in a transit system and saves the results to CSV and JSON files. Bus bunching occurs when buses on the same route that are scheduled to be evenly spaced arrive close to each other at the same stop, causing irregular service intervals, longer wait times for passengers, and inefficient use of transit resources.

## Overview

The bus bunching detection algorithm works by:

1. Fetching real-time bus position data with estimated arrival times
2. Filtering buses that are within 3 minutes of arriving at the same stop on the same route
3. Identifying groups of buses on the same route that are arriving too close to each other (bunched)
4. Calculating the time differences between buses to determine if they are bunched
5. Storing the bunching instances in a database to avoid duplicates
6. Generating reports in CSV and JSON formats for analysis and visualization

## Requirements

- Python 3.7+
- Required packages (install via `pip install -r requirements.txt`):
  - pandas
  - requests
  - pytz
  - geopy
  - tqdm

## Configuration

The module supports two methods of configuration:

### 1. Environment Variables (.env file)

For better security, you can store confidential API endpoints in a `.env` file. Copy the provided `.env.example` file to `.env` and update with your actual API endpoints:

```env
# API Endpoints
BUS_POSITIONS_URL=https://api.example.com/v2/get_buses_next_stop_eta
SCHEDULE_URL=https://gpsfeed.example.com/depot_tool_duty_master.txt
FLEET_URL=https://depot.example.com/all_fleet/
STOPS_URL=https://routesapi.example.com/transit/agency/get_stops
ROUTES_URL=https://routesapi.example.com/transit/agency/get_routes

# Settings
TIMEZONE=Asia/Kolkata
DISTANCE_THRESHOLD=300
```

### 2. Configuration File (config.ini)

Alternatively, the module can use a configuration file (`config.ini`). If the file doesn't exist, a default one will be created with example values.

```ini
[API]
pis_url = https://pis.example.com/v2/get_buses_next_stop_eta
schedule_url = https://gpsfeed.example.com/depot_tool_duty_master.txt
fleet_url = https://depot.example.com/all_fleet/
stops_url = https://routesapi.example.com/transit/agency/get_stops
routes_url = https://routesapi.example.com/transit/agency/get_routes

[SETTINGS]
timezone = Asia/Kolkata
distance_threshold = 300
```

**Note:** Environment variables take precedence over the config.ini file settings.

## Expected API Response Structures

### 1. Bus Positions API

This API should return real-time bus positions with estimated time of arrival (ETA) information. Based on the code analysis, the endpoint URL format is:

```text
https://[your-domain]/api/get_buses_next_stop_eta
```

Expected response format:

```json
[
  {
    "vehicle_id": "DL1PC1234",
    "route_id": "534",
    "upcoming_stop_id": "1234",
    "upcoming_stop_idx": 7,
    "route_len": 15,
    "timestamp": 1621234567,
    "eta": 2,
    "bus_lat": 40.7128,
    "bus_lon": -74.0060,
    "agency_id": "DIMTS"
  },
  {
    "vehicle_id": "DL1PC5678",
    "route_id": "534",
    "upcoming_stop_id": "1234",
    "upcoming_stop_idx": 7,
    "route_len": 15,
    "timestamp": 1621234567,
    "eta": 2.5,
    "bus_lat": 40.7130,
    "bus_lon": -74.0062,
    "agency_id": "DIMTS"
  }
]
```

### 2. Stops API

This API should return information about all stops in the system. Based on the code analysis, the endpoint URL format is:

```text
https://[your-domain]/api/get_stops
```

Expected response format:

```json
{
  "description": "",
  "message": "success",
  "status": "success",
  "stops": [
    {
      "id": 4,
      "lat": 28.857683,
      "lng": 77.097115,
      "name": "Narela A-6 / CPJ College",
      "next_stop": "State Bank Of Allahbad"
    },
    {
      "id": 5,
      "lat": 28.854725,
      "lng": 77.097931,
      "name": "State Bank Of Allahbad",
      "next_stop": "Sec A-9 Narela"
    },
    {
      "id": 8,
      "lat": 28.848993,
      "lng": 77.098488,
      "name": "Narela Pocket 13 / A-6",
      "next_stop": "Raja Harish Chandra Hospital"
    },
    {
      "id": 10,
      "lat": 28.837227,
      "lng": 77.098579,
      "name": "Kasturi Ram School",
      "next_stop": "Munim Ji Ka Bagh"
    }
  ]
}
```

### 3. Routes API

This API should return information about all routes in the system. Based on the code analysis, the endpoint URL format is:

```text
https://[your-domain]/api/get_routes
```

Expected response format:

```json
{
  "routes": [
    {
      "agency": "DTC",
      "direction": 0,
      "end": "ISBT Anand Vihar Terminal",
      "id": 11021,
      "long_name": "543STLDOWN",
      "route": "543STL",
      "short_name": "nan",
      "start": "PG DAV College / Sri Niwaspuri",
      "trips_count": 48
    },
    {
      "agency": "DTC",
      "direction": 1,
      "end": "Sri Niwaspuri / PG DAV College Lajpat Nagar",
      "id": 11020,
      "long_name": "543STLUP",
      "route": "543STL",
      "short_name": "nan",
      "start": "Anand Vihar ISBT Terminal",
      "trips_count": 49
    }
  ]
}
```

### 4. Schedule API

This API should return a CSV file with schedule information. Based on the code analysis, the endpoint URL format is:

```text
https://[your-domain]/api/duty_master.txt
```

Expected CSV format:

```csv
Plate No.,Route No.,Trip Start Time,Trip End Time,Duty ID,Trip Number
DL1PC1234,534,08:00:00,09:30:00,DT001,1
DL1PC1234,534,09:45:00,11:15:00,DT001,2
DL1PC5678,423,08:15:00,09:45:00,DT002,1
```

The code processes this CSV to extract:

- Vehicle IDs (from 'Plate No.' column)
- Route information (from 'Route No.' column)
- Trip timing information (from 'Trip Start Time' and 'Trip End Time' columns)

### 5. Fleet API

This API should return a JSON array of objects with fleet information. Based on the code analysis, the endpoint URL format is:

```text
https://[your-domain]/api/all_fleet
```

Expected response format:

```json
[
  {
    "vehicle_id": "DL1PC1234",
    "agency": "DIMTS",
    "vehicle_type": "BUS",
    "status": "ACTIVE"
  },
  {
    "vehicle_id": "DL1PC5678",
    "agency": "DIMTS",
    "vehicle_type": "BUS",
    "status": "ACTIVE"
  }
]
```

The code primarily uses the `vehicle_id` and `agency` fields from this response.

## Usage

1. Update the `config.ini` file with your API endpoints
2. Run the script:

```bash
python bunching.py
```

## Output

The script generates the following outputs:

1. A SQLite database file: `bus_bunching/data/bus_bunching_YYYY-MM-DD.db`
2. Intermediate CSV files:
   - `bus_bunching/pis_df.csv`: All filtered bus positions
   - `bus_bunching/final_bunching.csv`: Detected bunching instances
3. A JSON file with bunching data: `bus_bunching/bunching_data.json`

## Customization

### Special Coordinates

The `special_coordinates` list in the code contains locations where bunching detection should be ignored (e.g., bus terminals, depots). Replace the example coordinates with actual coordinates for your transit system.

### Distance Threshold

The distance threshold for filtering buses near special coordinates can be adjusted in the `config.ini` file under the `distance_threshold` setting (default: 300 meters).

### Timezone

The timezone used for timestamp conversion can be set in the `config.ini` file under the `timezone` setting (default: 'Asia/Kolkata').

## License

This project is licensed under the Apache License, Version 2.0 - see below for details:

```text
Copyright 2025 Transport Stack

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
