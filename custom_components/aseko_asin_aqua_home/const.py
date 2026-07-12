"""Constants for ASEKO ASIN AQUA Home."""

from datetime import timedelta

DOMAIN = "aseko_asin_aqua_home"
CONFIG_ENTRY_VERSION = 2
PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "button"]
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 47524
DEFAULT_FORWARD_ENABLED = True
DEFAULT_FORWARD_HOST = "pool.aseko.com"
DEFAULT_FORWARD_PORT = 47524
DEFAULT_PROTOCOL_DEBUG = False
DEFAULT_CAPTURE_ENABLED = False
DEFAULT_MAX_CHLORINE = 20.0
DEFAULT_WATER_LEVEL_OFFSET = 33

DEFAULT_DOSING_CONTAINER_SIZES = {
    "chlorine": 20.0,
    "ph_minus": 20.0,
    "flocculation": 6.0,
    "algicide": 6.0,
}
DEFAULT_DOSING_FLOW_RATE = 0.0
MIN_DOSING_FLOW_RATE = 0.0
MAX_DOSING_FLOW_RATE = 500.0
DOSING_FLOW_RATE_UNIT = "ml/min"
LITERS_PER_HOUR_TO_MILLILITERS_PER_MINUTE = 1000 / 60
CONF_LISTEN_HOST = "listen_host"
CONF_LISTEN_PORT = "listen_port"
CONF_FORWARD_ENABLED = "forward_enabled"
CONF_FORWARD_HOST = "forward_host"
CONF_FORWARD_PORT = "forward_port"
CONF_PROTOCOL_DEBUG = "protocol_debug"
CONF_CAPTURE_ENABLED = "capture_enabled"
CONF_MAX_CHLORINE = "max_chlorine"
CONF_WATER_LEVEL_OFFSET = "water_level_offset"
UNAVAILABLE_AFTER = timedelta(seconds=60)
DEVICE_IDENTIFIER = "asin_aqua_home"
