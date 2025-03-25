"""Data handler for the response from the Darwin API"""

from datetime import datetime
from dateutil import parser
import logging

_LOGGER = logging.getLogger(__name__)

def check_key(element, *keys):
    """
    Check if a sequence of nested keys exists in a dictionary.

    Args:
        element (dict): The dictionary to check.
        *keys: Sequence of keys to validate.

    Returns:
        bool: True if all keys exist, False otherwise.
    """
    try:
        for key in keys:
            element = element[key]
        return True
    except (KeyError, TypeError):
        return False


class ApiData:
    """Data handler class for the response from the Darwin API"""

    def __init__(self):
        self.raw_result = {}
        self._last_update = None
        self._station_name = ""
        self._refresh_interval = 2

    def populate(self, json_data):
        """Hydrate the data entity with the JSON API response"""
        self.raw_result = json_data
        self._last_update = datetime.now()
        _LOGGER.debug("Data successfully populated.")

    def get_data(self):
        """Retrieve the raw JSON data."""
        if not self.raw_result:
            _LOGGER.warning("No data available in raw_result.")
            return {}
        return self.raw_result

    def is_empty(self):
        """Check if the raw result is empty."""
        return not bool(self.raw_result)

    def get_destination_data(self, station):
        """Retrieve service details for a specific destination CRS."""
        data = self.get_data()
        services = data.get("trainServices", [])
        for service in services:
            destinations = service.get("destination", [])
            if isinstance(destinations, list):
                for destination in destinations:
                    if destination.get("crs") == station:
                        return service
            elif isinstance(destinations, dict):
                if destinations.get("crs") == station:
                    return service
        _LOGGER.warning(f"No destination data found for station {station}.")
        return {}

    def get_service_details(self, crs):
        """Retrieve service details without calling points."""
        service = self.get_destination_data(crs)
        if service:
            service_copy = service.copy()
            service_copy.pop("subsequentCallingPoints", None)
            _LOGGER.debug("Removed subsequentCallingPoints from service details.")
            return service_copy
        _LOGGER.warning(f"No service details found for CRS {crs}.")
        return {}

    def get_calling_points(self, station):
        """Retrieve the calling points for a specific destination CRS."""
        service = self.get_destination_data(station)
        calling_points_group = service.get("subsequentCallingPoints", [])
        if calling_points_group and isinstance(calling_points_group, list):
            first_group = calling_points_group[0]
            calling_points = first_group.get("callingPoint", [])
            if isinstance(calling_points, list):
                return calling_points
        _LOGGER.warning(f"No calling points found for destination {station}.")
        return []

    def get_station_name(self):
        """Retrieve the name of the station."""
        if not self._station_name:
            data = self.get_data()
            self._station_name = data.get("locationName", "Unknown Station")
        return self._station_name

    def get_destination_name(self, crs):
        """Retrieve the name of a destination station."""
        service = self.get_destination_data(crs)
        destinations = service.get("destination", [])
        if isinstance(destinations, list):
            return destinations[0].get("locationName", "Unknown Destination")
        elif isinstance(destinations, dict):
            return destinations.get("locationName", "Unknown Destination")
        return "Unknown Destination"

    def message(self):
        """Retrieve station messages."""
        data = self.get_data()
        messages = data.get("nrccMessages", {}).get("message", [])
        if isinstance(messages, list):
            return messages
        elif isinstance(messages, str):
            return [messages]
        elif isinstance(messages, dict):
            return [messages.get("#text", "Unknown Message")]
        _LOGGER.warning("No valid station messages found.")
        return []

    def get_last_update(self):
        """Retrieve the last update timestamp."""
        return self._last_update

    def get_state(self, crs):
        """Retrieve the state based on the service departure time."""
        service = self.get_service_details(crs)
        if service:
            std = service.get("std")  # Scheduled departure time
            if std:
                return parser.parse(std).strftime("%H:%M")
        return "None"
