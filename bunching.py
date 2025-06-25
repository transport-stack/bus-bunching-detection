import requests
import json
import pytz
import pandas as pd
from tqdm import tqdm
import os
import sqlite3
from datetime import datetime, timedelta
from geopy.distance import geodesic
import re
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import io
import configparser
from dotenv import load_dotenv

# Load configuration
def load_config(config_file='config.ini'):
    """
    Load configuration from config.ini file and .env file if available
    Priority order:
    1. Environment variables (.env file)
    2. config.ini file
    3. Default values
    """
    # First try to load from .env file
    load_dotenv()
    
    # Initialize config parser for config.ini
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file)
    
    # Create sections if they don't exist
    if 'API' not in config:
        config['API'] = {}
    if 'SETTINGS' not in config:
        config['SETTINGS'] = {}
    
    # Set API endpoints - prioritize environment variables
    config['API']['bus_positions_url'] = os.getenv('BUS_POSITIONS_URL', config['API'].get('bus_positions_url', 
                                         'https://api.example.com/v2/get_buses_next_stop_eta'))
    config['API']['schedule_url'] = os.getenv('SCHEDULE_URL', config['API'].get('schedule_url', 
                                              'https://gpsfeed.example.com/depot_tool_duty_master.txt'))
    config['API']['fleet_url'] = os.getenv('FLEET_URL', config['API'].get('fleet_url', 
                                           'https://depot.example.com/all_fleet/'))
    config['API']['stops_url'] = os.getenv('STOPS_URL', config['API'].get('stops_url', 
                                           'https://routesapi.example.com/transit/agency/get_stops'))
    config['API']['routes_url'] = os.getenv('ROUTES_URL', config['API'].get('routes_url', 
                                            'https://routesapi.example.com/transit/agency/get_routes'))
    
    # Set settings - prioritize environment variables
    config['SETTINGS']['timezone'] = os.getenv('TIMEZONE', config['SETTINGS'].get('timezone', 'Asia/Kolkata'))
    config['SETTINGS']['distance_threshold'] = os.getenv('DISTANCE_THRESHOLD', 
                                                        config['SETTINGS'].get('distance_threshold', '300'))
    
    # Save the config file if it doesn't exist
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            config.write(f)
    
    return config

# Global config
CONFIG = load_config()

def make_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """
    Create a requests session with retry mechanism.
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
    
def fetch_data_with_retry(url):
    """
    Fetch data from the given URL with retry mechanism and timeout.
    """
    session = make_session()
    try:
        response = session.get(url, timeout=10)  # Adjust timeout as needed
        response.raise_for_status()
        if "text/plain" in response.headers.get("content-type", ""):
            return response.text
        else:
            return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data from {url}: {e}")
        return None

def filter_df(pis_df):

    pis_df['trip_completion'] = (pis_df['upcoming_stop_idx'] / pis_df['route_len']).round(2)
    # Drop rows where 'next_stop_idx' is less than 5
    pis_df = pis_df[pis_df['upcoming_stop_idx'] >= 5]
    # Drop rows where 'route_len' - 'next_stop_idx' is less than 5
    pis_df = pis_df[(pis_df['route_len'] - pis_df['upcoming_stop_idx']) >= 5]

    return pis_df

def filter_rows_within_1_minutes(df):
    """
    Filter rows to include only those within 1 minute of the latest timestamp for each route and stop
    """
    # Group by route_id and upcoming_stop_id
    grouped_df = df.groupby(["route_id", "upcoming_stop_id"])
    
    # Convert timestamp to datetime and localize to UTC
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC')
    
    # Convert timestamp to local timezone from config
    timezone_str = CONFIG['SETTINGS'].get('timezone', 'Asia/Kolkata')
    df['timestamp'] = df['timestamp'].dt.tz_convert(timezone_str)
    
    # Function to filter rows within 1 minutes of the latest timestamp in each group
    def filter_rows(group):
        latest_timestamp = group['timestamp'].max()
        time_diff = (latest_timestamp - group['timestamp']).dt.total_seconds()
        return group[time_diff <= 60]
    
    # Apply the filtering function to each group
    filtered_df = grouped_df.apply(filter_rows).reset_index(drop=True)
    
    return filtered_df

def create_db(db_file):
    if not os.path.isfile(db_file):
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE bus_bunching (
                    vehicle_id TEXT,
                    route_id TEXT,
                    route_long_name TEXT,
                    agency_id TEXT,
                    timestamp TEXT,
                    stop_id TEXT,
                    stop_name TEXT,
                    stop_lat FLOAT,
                    stop_lon FLOAT,
                    bunching_vehicles TEXT
                )
            """)
    else:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bus_bunching'"
            )
            if cursor.fetchone() is None:
                cursor.execute("""
                    CREATE TABLE bus_bunching (
                        vehicle_id TEXT,
                        route_id TEXT,
                        route_long_name TEXT,
                        agency_id TEXT,
                        timestamp TEXT,
                        stop_id TEXT,
                        stop_name TEXT,
                        stop_lat FLOAT,
                        stop_lon FLOAT,
                        bunching_vehicles TEXT
                    )
                """)

# Example special coordinates - replace with your own coordinates of areas to exclude
# These are sample coordinates and should be replaced with actual coordinates for your use case
special_coordinates = [
    (40.7128, -74.0060),  # Example: New York City
    (34.0522, -118.2437),  # Example: Los Angeles
    (41.8781, -87.6298),  # Example: Chicago
    (37.7749, -122.4194),  # Example: San Francisco
    (39.9526, -75.1652)   # Example: Philadelphia
]

# Note: In a real implementation, you would add coordinates of areas where
# bus bunching detection should be ignored (e.g., bus terminals, depots, etc.)

def filter_by_distance(df, special_coordinates, threshold=300):
    bus_coordinates = list(zip(df['bus_lat'], df['bus_lon']))
    
    for idx, bus_coord in enumerate(bus_coordinates):   
        for coord in special_coordinates:
            distance = geodesic(coord, bus_coord).meters
            if distance < threshold:
                df.drop(idx, inplace=True)
                break
    return df

def filter_within_eta(df):
    df = filter_by_distance(df.copy(), special_coordinates)
    # Group by route_id and upcoming_stop_id
    grouped = df.groupby(["route_id", "upcoming_stop_id"])
    
    filtered_rows = []
    for name, group in grouped:
        filtered_indices = group.index[group['eta'] <= 3]
        if len(filtered_indices) > 1:
            filtered_rows.extend(filtered_indices)
    
    # Remove filtered rows from the DataFrame
    df_filtered = df.loc[filtered_rows]
    return df_filtered


def bunching_vehicles_list(pis_df):
    # Group by route_id and aggregate vehicle_id into a list
    grouped = pis_df.groupby(["route_id", "upcoming_stop_id"])['vehicle_id'].agg(list).reset_index()

    # Create a dictionary mapping vehicle_id to bunching_vehicles
    vehicle_to_bunching = {}
    for _, row in grouped.iterrows():
        vehicles = row['vehicle_id']
        bunching_vehicles = {v: [v_ for v_ in vehicles if v_ != v] for v in vehicles}
        vehicle_to_bunching.update(bunching_vehicles)

    # Create DataFrame from the dictionary
    new_df = pd.DataFrame(vehicle_to_bunching.items(), columns=['vehicle_id', 'bunching_vehicles'])

    # Merge with original DataFrame
    pis_merged_df = pd.merge(pis_df, new_df, on='vehicle_id', how='left')

    return pis_merged_df


def get_route_trip_mean_time(all_routes_df):
    """
    Fetch schedule data and calculate mean trip time for each route
    
    Expected API Response Structure for schedule_url:
    A CSV file with columns: 'Plate No.', 'Route No.', 'Trip Start Time', 'Trip End Time', 'Duty ID', 'Trip Number'
    
    Expected API Response Structure for fleet_url:
    A JSON array of objects with at least 'vehicle_id' and 'agency' fields
    """
    # Get timezone from config
    timezone_str = CONFIG['SETTINGS'].get('timezone', 'Asia/Kolkata')
    local_tz = pytz.timezone(timezone_str)
    formatted_date = datetime.now(local_tz)
    formatted_date_str = formatted_date.strftime('%Y-%m-%d')

    # Get URLs from config
    schedule_url = CONFIG['API'].get('schedule_url')
    fleet_url = CONFIG['API'].get('fleet_url')

    schedule_data = fetch_data_with_retry(schedule_url)
    fleet_response = fetch_data_with_retry(fleet_url)

    depot_df = pd.read_csv(io.StringIO(schedule_data))
    fleet_data = pd.DataFrame(fleet_response)

    depot_df.columns = depot_df.columns.str.replace('Plate No.','vehicle_id')
    pattern = r"CL|_| |P[0-9]+|\."  # Updated regex pattern to include any number after 'P'
    depot_df['Route No.'] = depot_df['Route No.'].str.replace(pattern, "", regex=True)
    depot_df['Route No.'] = depot_df['Route No.'].apply(lambda x: re.sub(r'DN$', 'DOWN', x)).str.upper()

    desired_date = formatted_date_str
    for index, row in tqdm(depot_df.iterrows(), total=len(depot_df), desc="Convert to ISO Time Format"):
        trip_start_time = datetime.strptime(f"{desired_date} {row['Trip Start Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=local_tz)
        trip_end_time = datetime.strptime(f"{desired_date} {row['Trip End Time']}", '%Y-%m-%d %H:%M:%S').replace(tzinfo=local_tz)

        # Check if Trip End Time is smaller than Trip Start Time, add one day
        if trip_end_time < trip_start_time:
            trip_end_time += timedelta(days=1)

        # Convert to ISO format
        depot_df.at[index, 'Trip Start Time'] = trip_start_time.strftime('%Y-%m-%dT%H:%M:%S+05:30')
        depot_df.at[index, 'Trip End Time'] = trip_end_time.strftime('%Y-%m-%dT%H:%M:%S+05:30')

    depot_df.columns = depot_df.columns.str.replace('Route No.','route_long_name')
    depot_df.columns = depot_df.columns.str.replace('Trip End Time','scheduled_end_timestamp')
    depot_df.columns = depot_df.columns.str.replace('Trip Start Time','scheduled_start_timestamp')

    columns_to_delete = ['Duty ID', 'Trip Number']
    depot_df = depot_df.drop(columns=columns_to_delete)

    # Convert agency column to uppercase
    fleet_data['agency'] = fleet_data['agency'].str.upper()

    # Create vehicle_mapping dictionary
    vehicle_mapping = dict(zip(fleet_data['vehicle_id'], fleet_data['agency']))
    depot_df['agency_id'] = depot_df['vehicle_id'].map(vehicle_mapping)

    routes_df = all_routes_df
    depot_df['agency_id'] = depot_df['agency_id'].astype(str)
    merged_df = pd.merge(depot_df, routes_df, how='left', on=['agency_id', 'route_long_name'])

    # dropped_df = merged_df[merged_df['route_id'].isna()]
    merged_df = merged_df.dropna(subset=['route_id'])
    
    if merged_df['route_id'].dtype != 'object':
        merged_df['route_id'] = merged_df['route_id'].astype(int).astype(str)
    
    scheduled_timestamp = merged_df

    route_timestamp = calculate_avg_time_difference(scheduled_timestamp)

    return route_timestamp

def calculate_avg_time_difference(df):   
    # Calculate the time difference in each row
    df['time_difference'] = abs(df.apply(lambda row: calculate_time_difference(row['scheduled_end_timestamp'], row['scheduled_start_timestamp']), axis=1))

    # Group by route_long_name
    grouped = df.groupby('route_long_name')

    # Calculate the average time difference
    average_time_difference = grouped['time_difference'].mean().astype(int)

    # Create a new dataframe
    new_data = pd.DataFrame({'route_long_name': average_time_difference.index, 
                             'max_time_difference': average_time_difference.values})

    return new_data

def calculate_time_difference(actual_timestamp, scheduled_timestamp):

    if not isinstance(actual_timestamp, str) or not isinstance(scheduled_timestamp, str):
        return None
    
    try:
        actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%dT%H:%M:%S%z')
        scheduled_dt = datetime.strptime(scheduled_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    except ValueError:
        return None
    
    actual_dt = datetime.strptime(actual_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    scheduled_dt = datetime.strptime(scheduled_timestamp, '%Y-%m-%dT%H:%M:%S%z')
    time_difference = (actual_dt - scheduled_dt).total_seconds()
    return int(time_difference)

def filter_with_db(pis_df, db_file, route_timestamp):
    # Establish connection
    connection = sqlite3.connect(db_file)
    cursor = connection.cursor()

    new_data = []  # List to store new data

    try:
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bus_bunching (
                vehicle_id TEXT,
                route_id TEXT,
                route_long_name TEXT,
                agency_id TEXT,
                timestamp TEXT,
                stop_id TEXT,
                stop_name TEXT,
                stop_lat FLOAT,
                stop_lon FLOAT,
                bunching_vehicles TEXT,
                PRIMARY KEY (vehicle_id, route_id, timestamp, bunching_vehicles)
            )
        """)
        connection.commit()

        # Iterate over DataFrame rows
        for _, row in pis_df.iterrows():
            vehicle_id = row['vehicle_id']
            route_id = row['route_id']
            route_long_name = row['route_long_name']
            agency_id = row['agency_id']
            timestamp = row['timestamp']
            bunching_vehicles = json.dumps(row['bunching_vehicles'])
            upcoming_stop_id = row['upcoming_stop_id']
            upcoming_stop_name = row['upcoming_stop_name']
            upcoming_stop_lat = row['upcoming_stop_lat']
            upcoming_stop_lon = row['upcoming_stop_lon']

            # Check if the row already exists
            cursor.execute("""
                SELECT COUNT(*) FROM bus_bunching
                WHERE vehicle_id=? AND route_id=? AND bunching_vehicles=?
            """, (vehicle_id, str(route_id), bunching_vehicles))
            existing_row_count = cursor.fetchone()[0]

            if existing_row_count == 0:
                # Insert new row if it doesn't exist
                cursor.execute("""
                    INSERT INTO bus_bunching (
                        vehicle_id, route_id, route_long_name, agency_id, timestamp, bunching_vehicles,
                        stop_id, stop_name, stop_lat, stop_lon
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (vehicle_id, route_id, route_long_name, agency_id, timestamp, bunching_vehicles,
                      upcoming_stop_id, upcoming_stop_name, upcoming_stop_lat, upcoming_stop_lon))
                connection.commit()
                new_data.append(row)  # Append new data to the list

            else:
                # Check if the time difference exceeds the threshold
                cursor.execute("""
                    SELECT timestamp FROM bus_bunching
                    WHERE vehicle_id=? AND route_id=? AND bunching_vehicles=?
                    ORDER BY strftime('%Y-%m-%dT%H:%M:%S', timestamp) DESC LIMIT 1
                """, (vehicle_id, str(route_id), bunching_vehicles))

                latest_timestamp_str = cursor.fetchone()
                
                if latest_timestamp_str:
                    latest_timestamp = datetime.strptime(latest_timestamp_str[0], '%Y-%m-%dT%H:%M:%S%z')
                    current_timestamp = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S%z')
                    max_time_difference = route_timestamp.loc[route_timestamp['route_long_name'] == route_long_name, 'max_time_difference'].iloc[0] if not route_timestamp.loc[route_timestamp['route_long_name'] == route_long_name].empty else 3600
                    time_difference = abs((latest_timestamp - current_timestamp).total_seconds())

                    if time_difference > max_time_difference:
                        # Update row if time difference exceeds threshold
                        cursor.execute("""
                            INSERT INTO bus_bunching (
                                vehicle_id, route_id, route_long_name, agency_id, timestamp, bunching_vehicles,
                                stop_id, stop_name, stop_lat, stop_lon
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (vehicle_id, route_id, route_long_name, agency_id, timestamp, bunching_vehicles,
                            upcoming_stop_id, upcoming_stop_name, upcoming_stop_lat, upcoming_stop_lon))
                        connection.commit()
                        new_data.append(row)  # Append new data to the list

    except sqlite3.Error as e:
        print("SQLite error:", e)
    finally:
        # Close connection
        connection.close()

    new_df = pd.DataFrame(new_data, columns=pis_df.columns)
    return new_df

def make_json_data(final_bunching):

    grouped = final_bunching.groupby(["route_id", "upcoming_stop_id"])

    # Filter groups where len == 1
    grouped_filtered = grouped.filter(lambda x: len(x) > 1)

    # Initialize list to store JSON objects
    json_objects = []

    # Iterate over groups
    for name, group in grouped_filtered.groupby(["route_id", "upcoming_stop_id"]):
        # Extract information from the first row of the group
        first_row = group.iloc[0]
        timestamp = first_row["timestamp"]
        agency_id = first_row["agency_id"]
        route_id = first_row["route_id"]
        route_long_name = first_row["route_long_name"]
        stop_id = first_row["upcoming_stop_id"]
        stop_name = first_row["upcoming_stop_name"]
        stop_lat = first_row["upcoming_stop_lat"]
        stop_lon = first_row["upcoming_stop_lon"]
        
        # Count number of vehicles bunching and create list of bunching vehicles
        no_of_vehicles_bunching = len(group)
        no_of_bunching = 1
        bunching_vehicles = list(group["vehicle_id"])

        route_id = str(route_id)
        stop_id = str(stop_id)
        # Convert stop_lat and stop_lon to float explicitly
        stop_lat = float(stop_lat)
        stop_lon = float(stop_lon)

        # Convert no_of_vehicles_bunching and no_of_bunching to int explicitly
        no_of_vehicles_bunching = int(no_of_vehicles_bunching)
        no_of_bunching = int(no_of_bunching)

        # Create JSON object
        json_obj = {
            "timestamp": timestamp,
            "agency_id": agency_id,
            "route_id": route_id,
            "route_long_name": route_long_name,
            "stop_id": stop_id,
            "stop_name": stop_name,
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
            "no_of_vehicles_bunching": no_of_vehicles_bunching,
            "no_of_bunching": no_of_bunching,
            "bunching_vehicles": bunching_vehicles
        }

        # Append JSON object to the list
        json_objects.append(json_obj)

    # Convert list of JSON objects to JSON string
    json_string = json.dumps(json_objects, indent=4)

    return json_string


def run():
    """
    Main function to run the bus bunching detection process
    
    Expected API Response Structures:
    
    1. PIS API (pis_url):
       JSON array of objects with fields including:
       - vehicle_id: unique identifier for the vehicle
       - route_id: identifier for the route
       - upcoming_stop_id: identifier for the next stop
       - upcoming_stop_idx: index of the next stop in the route
       - route_len: total number of stops in the route
       - timestamp: unix timestamp in seconds
       - eta: estimated time of arrival in minutes
       - bus_lat: latitude of the bus
       - bus_lon: longitude of the bus
    
    2. Stops API (stops_url):
       JSON object with a 'stops' array containing objects with fields:
       - id: stop identifier
       - name: stop name
       - lat: latitude
       - lng: longitude
    
    3. Routes API (routes_url):
       JSON object with a 'routes' array containing objects with fields:
       - id: route identifier
       - agency: agency identifier
       - long_name: route name
    """
    # Create directory structure if it doesn't exist
    os.makedirs("bus_bunching/data", exist_ok=True)
    
    # Get current date for file naming
    current_date = datetime.now().strftime("%Y-%m-%d")
    db_file = f"bus_bunching/data/bus_bunching_{current_date}.db"
    create_db(db_file)

    # Get URLs from config
    bus_positions_url = CONFIG['API'].get('bus_positions_url')
    stops_url = CONFIG['API'].get('stops_url')
    routes_url = CONFIG['API'].get('routes_url')
    
    # Fetch real-time bus positions with ETA
    bus_positions_data = fetch_data_with_retry(bus_positions_url)

    if bus_positions_data:
        # Convert to DataFrame
        pis_df = pd.DataFrame(bus_positions_data)

        # Apply filters
        pis_df = filter_df(pis_df)
        pis_df = filter_rows_within_1_minutes(pis_df)
        pis_df = filter_within_eta(pis_df)

        # Format timestamp
        timezone_str = CONFIG['SETTINGS'].get('timezone', 'Asia/Kolkata')
        timezone_offset = '+05:30'  # This should be derived from the timezone
        pis_df['timestamp'] = pis_df['timestamp'].dt.strftime(f"%Y-%m-%dT%H:%M:%S{timezone_offset}")

        # Fetch stop information
        all_stops_data = fetch_data_with_retry(stops_url)
        
        if all_stops_data:
            stops = all_stops_data.get("stops", [])
            all_stops_df = pd.DataFrame(stops)
            stops_merged_df = pd.merge(pis_df, all_stops_df, left_on='upcoming_stop_id', right_on='id', how='left')
            stops_merged_df['upcoming_stop_name'] = stops_merged_df['name']
            stops_merged_df['upcoming_stop_lat'] = stops_merged_df['lat']
            stops_merged_df['upcoming_stop_lon'] = stops_merged_df['lng']

            # Drop unnecessary columns
            stops_merged_df.drop(['id', 'lat', 'lng', 'name', 'next_stop'], axis=1, inplace=True)
            
            # Fetch route information
            all_routes_data = fetch_data_with_retry(routes_url)
            
            if all_routes_data:
                routes = all_routes_data.get("routes", [])
                all_routes_df = pd.DataFrame(routes)
                all_routes_df = all_routes_df.rename(columns={'agency': 'agency_id', 'id': 'route_id', 'long_name': 'route_long_name'})
                # Reorder columns
                all_routes_df = all_routes_df[['agency_id', 'route_id', 'route_long_name']]
                routes_merged_df = pd.merge(stops_merged_df, all_routes_df[['agency_id', 'route_id']], left_on='route_id', right_on='route_id', how='left')
                pis_df = routes_merged_df
                route_timestamp = get_route_trip_mean_time(all_routes_df)
            else:
                print("Failed to fetch data from the routes URL")
        else:
            print("Failed to fetch data from the stops URL")

        # Identify bunching vehicles
        pis_df = bunching_vehicles_list(pis_df)
        
        # Save intermediate results
        os.makedirs("bus_bunching", exist_ok=True)
        pis_df.to_csv("bus_bunching/pis_df.csv", index=False)
        
        # Filter using database to avoid duplicates
        final_bunching = filter_with_db(pis_df, db_file, route_timestamp)
        final_bunching.to_csv("bus_bunching/final_bunching.csv", index=False)

        # Create JSON output
        bunching_json = make_json_data(final_bunching)

        # Save results
        file_path = "bus_bunching/bunching_data.json"
        with open(file_path, "w") as file:
            file.write(bunching_json)
            
        print(f"Bus bunching detection completed. Results saved to {file_path}")
    else:
        print("Failed to fetch data from the PIS URL")

if __name__ == '__main__':
    run() 