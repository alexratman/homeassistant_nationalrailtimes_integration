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
    """Representation of a Sensor."""

    def __init__(self, name, station, destination, api_key, time_offset, time_window):
        """Initialize the sensor."""
        self._platformname = name
        self._name = f"{station}_{destination}_{time_offset}"
        self.time_offset = time_offset
        self.destination = destination
        self.station = station
        self._state = None
        self.station_name = station
        self.destination_name = destination

        self.api = Api(api_key, station, destination)
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

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            result = await self.api.api_request()
            _LOGGER.debug("Received result: %s", result)
        
            # Ensure the result is a dictionary
            if not isinstance(result, dict):
                _LOGGER.error("Unexpected result type. Expected dict, got %s", type(result))
                self._state = "Error: Invalid API response"
                return
        
            # Assign and validate key data
            self.station_name = result.get("locationName", "Unknown")
            self.destination_name = result.get("filterLocationName", "Unknown")
            self.service_data = result.get("trainServices", [])
        
            # Validate `service_data` is a list
            if not isinstance(self.service_data, list):
                _LOGGER.error("Unexpected type for trainServices. Expected list, got %s", type(self.service_data))
                self.service_data = []
                self._state = "Error: Invalid train service data"
                return
        
            # Ensure the list is not empty
            if not self.service_data:
                _LOGGER.warning("No train services found in result: %s", result)
                self._state = "No train services available for this station"
                return
        
            # Validate the first element in `service_data` is a dictionary
            first_service = self.service_data[0]
            if not isinstance(first_service, dict):
                _LOGGER.error("Expected dictionary in service_data[0], got %s", type(first_service))
                self._state = "Invalid train service data format"
                return
        
            # Safely get the next train time
            next_train_time = first_service.get("etd", "").lower()
            if next_train_time in ["delayed", "cancelled"]:  # Handle non-time values
                _LOGGER.warning("Non-time value for next train time: %s", next_train_time)
                self._state = next_train_time.capitalize()  # Display "Delayed" or "Cancelled"
            elif next_train_time == "on time":
                # Fall back to std if etd is "On time"
                next_train_time = first_service.get("std", "Unknown")
                self._state = parser.parse(next_train_time).strftime("%H:%M")
            else:
                # Ensure valid time string before parsing
                try:
                    self._state = parser.parse(next_train_time).strftime("%H:%M")
                except Exception as parse_error:
                    _LOGGER.error("Failed to parse next train time: %s", parse_error)
                    self._state = "Invalid time"
        
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
