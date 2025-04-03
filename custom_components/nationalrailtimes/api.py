"""API wrapper for fetching data from the Darwin API"""

import aiohttp
import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

class Api:
    """API wrapper for interacting with the Darwin API"""

    def __init__(self, api_key, station, destination, service_start_hour=5, service_end_hour=23):
        self.base_url = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepBoardWithDetails/"
        self.api_key = api_key
        self.station = station
        self.destination = destination
        self.time_offset = 0
        self.time_window = 120
        self.service_start_hour = service_start_hour
        self.service_end_hour = service_end_hour

    def set_config(self, key, val):
        """Set configuration values like time_offset and time_window."""
        if key == "time_offset":
            self.time_offset = val
            return True
        if key == "time_window":
            self.time_window = val
            return True
        _LOGGER.warning(f"Unknown config key: {key}")
        return False
        
    def is_service_available(self):
        """
        Check dynamically if train services are likely available based on the time of day.
        Returns True if services should be fetched, False otherwise.
        """
        now = datetime.now()
        # Fallback to default hours if not explicitly set
        service_start_hour = getattr(self, "service_start_hour", 5)
        service_end_hour = getattr(self, "service_end_hour", 23)

        # Check if current time is outside service hours
        if now.hour < service_start_hour or now.hour >= service_end_hour:
            _LOGGER.info(
                f"No train services expected for {self.station} to {self.destination} "
                f"outside {service_start_hour}:00–{service_end_hour}:00. Current time: {now}."
            )
            return False
        return True

    async def api_request(self):
        """
        Make an API request to the Darwin API.

        Returns:
            dict: Parsed JSON data from the API response.
        """
        if not self.is_service_available():
            _LOGGER.info("Skipping API call due to no expected train services.")
            return None  # Avoid API call during quiet hours or unavailable times

        url = f"{self.base_url}{self.station}"  # Construct the full URL
        headers = {
            "x-apikey": self.api_key,  # Include API key in headers
        }
        params = self.build_params()  # Build query parameters dynamically

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        # Parse JSON response
                        json_data = await response.json()
                        _LOGGER.info(f"Raw API response: {json_data}")
                        return json_data
                    else:
                        _LOGGER.error(
                            f"API request failed with status {response.status}: {await response.text()}"
                        )
                        return None
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Client error during API request: {e}", exc_info=True)
            return None
        except Exception as e:
            _LOGGER.error(f"Unexpected error during API request: {e}", exc_info=True)
            return None

    def build_params(self):
        """
        Build API query parameters dynamically.

        Returns:
            dict: Parameters for the API request.
        """
        params = {
            "numRows": 10,  # Number of rows to fetch
            "timeOffset": self.time_offset,
            "timeWindow": self.time_window,
        }
        if self.destination:
            params["filterCrs"] = self.destination  # Destination CRS code
            params["filterType"] = "to"  # Filter type
        return params
