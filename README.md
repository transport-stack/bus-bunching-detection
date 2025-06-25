# Bus Bunching Detection

## Overview

This project provides a Python-based solution for detecting bus bunching in real-time. It fetches data from various public transit APIs, processes it to identify instances where buses on the same route are running too close together, and stores the bunching events in a local SQLite database for further analysis.

The core script, `bunching.py`, orchestrates the entire process, from data fetching and processing to storage.

## Features

- Fetches real-time bus positions, schedules, and route information from configurable API endpoints.
- Identifies bus bunching based on proximity and time headway between vehicles on the same route.
- Filters out irrelevant data, such as buses near depots or at the start/end of their routes.
- Stores detected bunching events in a SQLite database for persistence.
- Uses a configuration file (`config.ini`) and environment variables for easy setup.

## Project Structure

```bash
.
├── data/                     # Directory for database and other data files
│   └── bus_bunching.db       # SQLite database file
├── tests/                    # Directory for tests
│   └── test_bunching.py      # Unit tests for the project
├── bunching.py             # Core script for the bunching detection logic
├── config.ini              # Configuration file for API endpoints and settings
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment file
└── README.md               # This documentation file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.7+

### 2. Clone the Repository

```bash
git clone <repository-url>
cd bus-bunching-detection
```

### 3. Create a Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

The script uses a `config.ini` file and environment variables to manage configuration. Create a `.env` file by copying the example file:

```bash
cp .env.example .env
```

Add the following variables to your `.env` file, replacing the example URLs with your actual API endpoints:

```dotenv
BUS_POSITIONS_URL=https://api.example.com/v2/get_buses_next_stop_eta
SCHEDULE_URL=https://gpsfeed.example.com/depot_tool_duty_master.txt
FLEET_URL=https://depot.example.com/all_fleet/
STOPS_URL=https://routesapi.example.com/transit/agency/get_stops
ROUTES_URL=https://routesapi.example.com/transit/agency/get_routes
TIMEZONE=Asia/Kolkata
DISTANCE_THRESHOLD=300
```

The script prioritizes environment variables over settings in the `config.ini` file.

## How to Run

To run the bus bunching detection script, execute the following command from the project's root directory:

```bash
python bunching.py
```

The script will:

1. Fetch the latest bus data.
2. Process the data to detect bunching.
3. Store any new bunching events in the SQLite database located at `data/bus_bunching.db`.

## Running Tests

To run the unit tests, use the following command:

```bash
python -m unittest discover tests
```

## External Services

This project relies on several external APIs to function correctly. Ensure that the URLs for these services are correctly configured in your `.env` or `config.ini` file.

- **Bus Positions API**: Provides real-time location and ETA data for buses.
- **Schedule API**: Provides bus schedule information.
- **Fleet API**: Provides details about the bus fleet.
- **Stops API**: Provides information about bus stops.
- **Routes API**: Provides details about bus routes.

## License

This project is licensed under the Apache License, Version 2.0.
