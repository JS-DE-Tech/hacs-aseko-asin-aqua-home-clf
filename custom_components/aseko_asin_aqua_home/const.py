"""Constants for ASEKO ASIN AQUA Home."""

from datetime import timedelta

DOMAIN = "aseko_asin_aqua_home"
PLATFORMS = ["sensor", "binary_sensor"]
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 47524
DEFAULT_FORWARD_ENABLED = True
DEFAULT_FORWARD_HOST = "pool.aseko.com"
DEFAULT_FORWARD_PORT = 47524
CONF_LISTEN_HOST = "listen_host"
CONF_LISTEN_PORT = "listen_port"
CONF_FORWARD_ENABLED = "forward_enabled"
CONF_FORWARD_HOST = "forward_host"
CONF_FORWARD_PORT = "forward_port"
UNAVAILABLE_AFTER = timedelta(seconds=60)
DEVICE_IDENTIFIER = "asin_aqua_home"
