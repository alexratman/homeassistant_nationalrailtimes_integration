"""Constants for the National Rail Departure Times integration."""

DOMAIN = "nationalrailtimes"

DEFAULT_NAME = "National Rail Departure Times"
DEFAULT_ICON = "mdi:train"
DEFAULT_TIME_OFFSET = 0
DEFAULT_TIME_WINDOW = 120

NATIONAL_RAIL_URL = "https://lite.realtime.nationalrail.co.uk/OpenLDBWS/ldb9.asmx"

CONF_API_KEY = "api_key"
CONF_ARRIVAL = "arrival"
CONF_DESTINATIONS = "destination"
CONF_TIME_OFFSET = "time_offset"
CONF_TIME_WINDOW = "time_window"
CONF_REFRESH_SECONDS = 60
