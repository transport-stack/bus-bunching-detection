import unittest
import os
import pandas as pd
from datetime import datetime
from unittest.mock import patch
from bunching import load_config, filter_df, calculate_time_difference

class TestBunching(unittest.TestCase):

    def setUp(self):
        # Create a dummy config file for testing
        self.config_file = 'test_config.ini'
        with open(self.config_file, 'w') as f:
            f.write('[API]\n')
            f.write('bus_positions_url = https://test.com/api\n')
            f.write('schedule_url = https://test.com/schedule\n')
            f.write('fleet_url = https://test.com/fleet\n')
            f.write('stops_url = https://test.com/stops\n')
            f.write('routes_url = https://test.com/routes\n')
            f.write('[SETTINGS]\n')
            f.write('timezone = America/New_York\n')
            f.write('distance_threshold = 250\n')

    def tearDown(self):
        # Clean up the dummy file
        if os.path.exists(self.config_file):
            os.remove(self.config_file)

    @patch.dict(os.environ, {
        "BUS_POSITIONS_URL": "https://test.com/env_api",
        "TIMEZONE": "America/Los_Angeles"
    })
    def test_load_config_with_env_override(self):
        # Test that environment variables override config file settings
        config = load_config(self.config_file)
        self.assertEqual(config['API']['bus_positions_url'], 'https://test.com/env_api')
        self.assertEqual(config['SETTINGS']['timezone'], 'America/Los_Angeles')
        # This one is not in env, should come from file
        self.assertEqual(config['SETTINGS']['distance_threshold'], '250')

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_from_file(self):
        # Test loading from config file when no env vars are set
        config = load_config(self.config_file)
        self.assertEqual(config['API']['bus_positions_url'], 'https://test.com/api')
        self.assertEqual(config['SETTINGS']['timezone'], 'America/New_York')

    def test_filter_df(self):
        # Create a sample DataFrame for testing
        data = {
            'upcoming_stop_idx': [1, 5, 10, 15, 20],
            'route_len': [20, 20, 20, 20, 20]
        }
        df = pd.DataFrame(data)
        
        # Apply the filter function
        filtered_df = filter_df(df)
        
        # Check if the rows are filtered correctly
        self.assertEqual(len(filtered_df), 3)
        self.assertListEqual(filtered_df['upcoming_stop_idx'].tolist(), [5, 10, 15])

    def test_calculate_time_difference(self):
        # Test calculating time difference between two timestamps
        start_time = '2025-06-25T10:00:00+05:30'
        end_time = '2025-06-25T10:10:00+05:30'
        
        time_diff = calculate_time_difference(end_time, start_time)
        
        # Check if the time difference is calculated correctly
        self.assertEqual(time_diff, 600)

if __name__ == '__main__':
    unittest.main()
