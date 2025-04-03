"""Platform for sensor integration."""

from __future__ import annotations
from datetime import timedelta
from dateutil import parser
import logging
import voluptuous as vol
from .station_codes import STATIONS

from homeassistant import config_entries, core
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .api import Api
from .const import (
    CONF_API_KEY,
    CONF_ARRIVAL,
    CONF_DESTINATIONS,
    CONF_TIME_OFFSET,
    CONF_TIME_WINDOW,
    DEFAULT_ICON,
    DEFAULT_NAME,
    DOMAIN,
    CONF_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=CONF_REFRESH_SECONDS)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_ARRIVAL): cv.string,
        vol.Required(CONF_TIME_OFFSET): cv.string,
        vol.Required(CONF_TIME_WINDOW): cv.string,
        vol.Optional(CONF_DESTINATIONS, default=[]): vol.All(cv.ensure_list, [cv.string]),
    }
)

async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up sensors from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    name = config.get(CONF_NAME, DEFAULT_NAME)
    station = config[CONF_ARRIVAL]
    destinations = config.get(CONF_DESTINATIONS, [])
    api_key = config[CONF_API_KEY]
    time_offset = config[CONF_TIME_OFFSET]
    time_window = config[CONF_TIME_WINDOW]
    # Fetch service hours (default to 5 and 23 if not set)
    service_start_hour = config.get("service_start_hour", 5)
    service_end_hour = config.get("service_end_hour", 23)
    sensors = [
        NationalrailSensor(
            name,
            station,
            destination,
            api_key,
            time_offset,
            time_window,
            service_start_hour,
            service_end_hour,
        )
        for destination in destinations
        if destination
    ]
    async_add_entities(sensors, update_before_add=True)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    name = config.get(CONF_NAME, DEFAULT_NAME)
    station = config[CONF_ARRIVAL]
    destinations = config.get(CONF_DESTINATIONS, [])
    api_key = config[CONF_API_KEY]
    time_offset = config[CONF_TIME_OFFSET]
    time_window = config[CONF_TIME_WINDOW]
    sensors = [
        NationalrailSensor(
            name,
            station,
            destination,
            api_key,
            time_offset,
            time_window,
        )
        for destination in destinations
        if destination
    ]
    async_add_entities(sensors, update_before_add=True)

class NationalrailSensor(SensorEntity):
    def __init__(
        self, name, station, destination, api_key, time_offset, time_window, service_start_hour=5, service_end_hour=23
    ):
        """Initialize the sensor."""
        self._platformname = name
        self._name = f"{station}_{destination}_{time_offset}"
        self.time_offset = time_offset
        self.destination = destination
        self.station = station
        self._state = None
        self.station_name = station
        self.destination_name = destination
        # Pass service hours to the API instance
        self.api = Api(api_key, station, destination, service_start_hour, service_end_hour)
        self.api.set_config(CONF_TIME_OFFSET, time_offset)
        self.api.set_config(CONF_TIME_WINDOW, time_window)
        self.last_data = {}
        self.service_data = []

    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._name

    @property
    def name(self) -> str:
        """Return the display name of the sensor."""
        walk_suffix = f" ({self.time_offset}m walk)" if int(self.time_offset) else ""
        return f"Trains {self.station_name} to {self.destination_name}{walk_suffix}"

    @property
    def icon(self):
        """Icon of the sensor."""
        return DEFAULT_ICON

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def parse_train_time(self, first_service):
        """Parse the next train time from the service data."""
        next_train_time = first_service.get("etd", "").lower()
        if next_train_time in ["delayed", "cancelled"]:
            _LOGGER.warning("Non-time value for next train time: %s", next_train_time)
            return next_train_time.capitalize()

        if next_train_time == "on time":
            # Use std if etd is "On time"
            next_train_time = first_service.get("std", "Unknown")
        try:
            return parser.parse(next_train_time).strftime("%H:%M")
        except Exception as parse_error:
            _LOGGER.error("Failed to parse train time: %s", parse_error)
            return "Invalid time"

    async def async_update(self):
        """Fetch new state data for the sensor."""
        if not self.api.is_service_available():
            self._state = "No train services expected"
            if not hasattr(self, "_logged_unavailable"):
                _LOGGER.info(f"No train services expected for {self.station} to {self.destination} at this time.")
                self._logged_unavailable = True
            return

        if self.api.is_service_available() and hasattr(self, "_logged_unavailable"):
            del self._logged_unavailable

        try:
            result = await self.api.api_request()
            if not isinstance(result, dict):
                _LOGGER.error("Invalid API response. Expected a dictionary but received: %s", type(result))
                self._state = "Error: Invalid API response"
                return

            self.station_name = result.get("locationName", "Unknown")
            self.destination_name = result.get("filterLocationName", "Unknown")
            self.service_data = result.get("trainServices", [])

            if not isinstance(self.service_data, list):
                _LOGGER.error("Unexpected type for trainServices. Expected list, got %s", type(self.service_data))
                self.service_data = []
                self._state = "Error: Invalid train service data"
                return

            if not self.service_data:
                _LOGGER.warning("No train services found for %s to %s: %s", self.station, self.destination, result)
                self._state = "No train services available for this station"
                self.last_data = result  # Store for reference
                self.service_data = []  # Clear data
                return

            first_service = self.service_data[0]
            self._state = self.parse_train_time(first_service)  # Use helper for time parsing
            self.last_data = result

        except Exception as e:
            _LOGGER.error("Failed to fetch or parse API data: %s", e, exc_info=True)
            self._state = "Error fetching or parsing API data"

    @property
    def extra_state_attributes(self):
        """Return additional sensor attributes."""
        attributes = {}
    
        # Basic Attributes
        attributes["last_refresh"] = self.last_data.get("generatedAt", "Unknown")
        attributes["station_name"] = self.last_data.get("locationName", "Unknown")
        attributes["destination_name"] = self.last_data.get("filterLocationName", "Unknown")
        attributes["offset"] = str(self.time_offset)  # Walking time offset
        attributes["station_code"] = self.station
        attributes["target_station_code"] = self.destination
        attributes["target_station_name"] = STATIONS.get(self.destination, "Unknown")
    
        # Primary Service (First Train)
        if isinstance(self.service_data, list) and len(self.service_data) > 0:
            first_service = self.service_data[0]
            attributes["service"] = {
                "std": first_service.get("std", "Unknown"),
                "etd": first_service.get("etd", "Unknown"),
                "platform": first_service.get("platform", "Unknown"),
                "operator": first_service.get("operator", "Unknown"),
                "destination": {
                    "location": {
                        "via": first_service.get("destinationVia", ""),
                    },
                },
                "calling_points": [
                    {
                        "locationName": point.get("locationName", "Unknown"),
                        "st": point.get("st", point.get("time", "Unknown")),  # Scheduled time
                        "et": point.get("et", "Unknown"),  # Estimated time
                    }
                    for point in first_service.get("subsequentCallingPoints", [{}])[0].get(
                        "callingPoint", []
                    )
                ],
            }
        else:
            attributes["service"] = {}
    
        # All Services List
        attributes["services"] = [
            {
                "std": service.get("std", "Unknown"),
                "etd": service.get("etd", "Unknown"),
                "platform": service.get("platform", "Unknown"),
                "operator": service.get("operator", "Unknown"),
                "destination": {
                    "location": {
                        "via": service.get("destinationVia", ""),
                    },
                },
                "calling_points": [
                    {
                        "locationName": point.get("locationName", "Unknown"),
                        "st": point.get("st", point.get("time", "Unknown")),  # Scheduled time
                        "et": point.get("et", "Unknown"),  # Estimated time
                    }
                    for point in service.get("subsequentCallingPoints", [{}])[0].get(
                        "callingPoint", []
                    )
                ],
            }
            for service in self.service_data
        ]
    
        # Flattened Calling Points
        attributes["calling_points"] = [
            {
                "locationName": point.get("locationName", "Unknown"),
                "st": point.get("st", "Unknown"),
                "et": point.get("et", "Unknown"),
            }
            for point in attributes["service"].get("calling_points", [])
        ]
    
        _LOGGER.debug("Final attributes prepared for sensor: %s", attributes)
        return attributes
