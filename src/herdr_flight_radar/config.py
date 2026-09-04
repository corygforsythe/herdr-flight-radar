"""Load and validate the plugin's user config (center location + radius).

Canonical unit: statute miles, everywhere in this codebase. The config file
may be edited by hand, so we keep it to plain JSON with a single explicit
"radius_miles" key rather than trying to support multiple units.
"""
import json
import os

DEFAULT_RADIUS_MILES = 100.0

_EXAMPLE = (
    '{\n'
    '  "location": {"lat": 47.6062, "lon": -122.3321},\n'
    '  "radius_miles": 100\n'
    '}\n'
)


class ConfigError(Exception):
    """Raised for a missing/invalid config file. Message is user-facing."""


def config_path():
    config_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if not config_dir:
        config_dir = os.getcwd()
    return os.path.join(config_dir, "config.json")


class Config:
    def __init__(self, lat, lon, radius_miles, path):
        self.lat = lat
        self.lon = lon
        self.radius_miles = radius_miles
        self.path = path


def load_config(path=None):
    path = path or config_path()

    if not os.path.isfile(path):
        raise ConfigError(
            "No Flight Radar location is configured.\n\n"
            "Create {path} with your center location, e.g.:\n\n"
            "{example}\n"
            "radius_miles is optional and defaults to {default}.".format(
                path=path, example=_EXAMPLE, default=DEFAULT_RADIUS_MILES
            )
        )

    try:
        with open(path, "r") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(
            "Could not read Flight Radar config at {path}: {err}".format(path=path, err=exc)
        )

    location = raw.get("location")
    if not isinstance(location, dict) or "lat" not in location or "lon" not in location:
        raise ConfigError(
            "Flight Radar config at {path} is missing a location.\n\n"
            "Add a \"location\" object with \"lat\" and \"lon\", e.g.:\n\n"
            "{example}".format(path=path, example=_EXAMPLE)
        )

    try:
        lat = float(location["lat"])
        lon = float(location["lon"])
    except (TypeError, ValueError):
        raise ConfigError(
            "Flight Radar config at {path} has a non-numeric lat/lon.".format(path=path)
        )

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ConfigError(
            "Flight Radar config at {path} has an out-of-range lat/lon "
            "(lat must be -90..90, lon must be -180..180).".format(path=path)
        )

    radius_miles = raw.get("radius_miles", DEFAULT_RADIUS_MILES)
    try:
        radius_miles = float(radius_miles)
    except (TypeError, ValueError):
        raise ConfigError(
            "Flight Radar config at {path} has a non-numeric radius_miles.".format(path=path)
        )
    if radius_miles <= 0:
        raise ConfigError(
            "Flight Radar config at {path} has a non-positive radius_miles.".format(path=path)
        )

    return Config(lat=lat, lon=lon, radius_miles=radius_miles, path=path)
