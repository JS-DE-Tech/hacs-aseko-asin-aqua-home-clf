"""Constants for ASEKO ASIN AQUA Home."""

from datetime import timedelta

DOMAIN = "aseko_asin_aqua_home"
PLATFORMS = ["sensor", "binary_sensor"]
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 47524
DEFAULT_FORWARD_ENABLED = True
DEFAULT_FORWARD_HOST = "pool.aseko.com"
DEFAULT_FORWARD_PORT = 47524
DEFAULT_PROTOCOL_DEBUG = False
DEFAULT_CAPTURE_ENABLED = False
DEFAULT_MAX_CHLORINE = 20.0
CONF_LISTEN_HOST = "listen_host"
CONF_LISTEN_PORT = "listen_port"
CONF_FORWARD_ENABLED = "forward_enabled"
CONF_FORWARD_HOST = "forward_host"
CONF_FORWARD_PORT = "forward_port"
CONF_PROTOCOL_DEBUG = "protocol_debug"
CONF_CAPTURE_ENABLED = "capture_enabled"
CONF_MAX_CHLORINE = "max_chlorine"
UNAVAILABLE_AFTER = timedelta(seconds=60)
DEVICE_IDENTIFIER = "asin_aqua_home"
