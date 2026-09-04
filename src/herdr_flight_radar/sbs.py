"""Parser and aircraft-state table for dump1090's SBS (BaseStation) feed.

dump1090 (and dump1090-fa) serve a line-oriented CSV stream on the SBS/
BaseStation port (default 30003) whenever networking is enabled. Fields for
a single aircraft arrive incrementally across several message
("transmission") types rather than all at once, so a stateful table keyed
by ICAO hex address is required to build up a full picture of each
aircraft. This is the standard, widely-documented dump1090 client pattern
(the same one FlightAware's own tools and most third-party dump1090
front ends use), chosen here over polling --write-json output because it
works against *any* already-running dump1090 instance without depending on
flags we did not choose (see dump1090_manager.py).

Field layout (BaseStation "MSG" record), 1-indexed for readability:
  1 MessageType (always "MSG" for the records we care about)
  2 TransmissionType (1-8)
  3 SessionID
  4 AircraftID
  5 HexIdent          <- stable per-aircraft key
  6 FlightID
  7 DateMsgGenerated
  8 TimeMsgGenerated
  9 DateMsgLogged
  10 TimeMsgLogged
  11 Callsign
  12 Altitude (ft)
  13 GroundSpeed (kt)
  14 Track (deg)
  15 Latitude
  16 Longitude
  17 VerticalRate
  18 Squawk
  19 Alert
  20 Emergency
  21 SPI
  22 IsOnGround
"""
import threading
import time

MSG_FIELD_COUNT = 22

STALE_SECONDS = 60.0


class Aircraft:
    __slots__ = (
        "hex", "callsign", "altitude_ft", "speed_kt", "track_deg",
        "lat", "lon", "last_update",
    )

    def __init__(self, hex_ident):
        self.hex = hex_ident
        self.callsign = None
        self.altitude_ft = None
        self.speed_kt = None
        self.track_deg = None
        self.lat = None
        self.lon = None
        self.last_update = 0.0

    def has_position(self):
        return self.lat is not None and self.lon is not None

    def to_dict(self):
        return {
            "hex": self.hex,
            "callsign": self.callsign,
            "altitude_ft": self.altitude_ft,
            "speed_kt": self.speed_kt,
            "track_deg": self.track_deg,
            "lat": self.lat,
            "lon": self.lon,
            "last_update": self.last_update,
        }


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_sbs_line(line):
    """Parse one SBS line into a field dict, or None if not a usable MSG record."""
    line = line.strip()
    if not line:
        return None
    parts = line.split(",")
    if len(parts) < MSG_FIELD_COUNT or parts[0] != "MSG":
        return None

    hex_ident = parts[4].strip().upper()
    if not hex_ident:
        return None

    callsign = parts[10].strip() or None

    return {
        "transmission_type": parts[1].strip(),
        "hex": hex_ident,
        "callsign": callsign,
        "altitude_ft": _to_float(parts[11]),
        "speed_kt": _to_float(parts[12]),
        "track_deg": _to_float(parts[13]),
        "lat": _to_float(parts[14]),
        "lon": _to_float(parts[15]),
    }


class AircraftTable:
    """Aircraft-state accumulator, merging incremental SBS updates by hex."""

    def __init__(self, stale_seconds=STALE_SECONDS, clock=time.time):
        self._aircraft = {}
        self._stale_seconds = stale_seconds
        self._clock = clock
        self._lock = threading.Lock()

    def update_from_line(self, line):
        fields = parse_sbs_line(line)
        if fields is None:
            return None
        return self.update_from_fields(fields)

    def update_from_fields(self, fields):
        hex_ident = fields["hex"]
        with self._lock:
            ac = self._aircraft.get(hex_ident)
            if ac is None:
                ac = Aircraft(hex_ident)
                self._aircraft[hex_ident] = ac

            if fields.get("callsign"):
                ac.callsign = fields["callsign"]
            if fields.get("altitude_ft") is not None:
                ac.altitude_ft = fields["altitude_ft"]
            if fields.get("speed_kt") is not None:
                ac.speed_kt = fields["speed_kt"]
            if fields.get("track_deg") is not None:
                ac.track_deg = fields["track_deg"]
            if fields.get("lat") is not None:
                ac.lat = fields["lat"]
            if fields.get("lon") is not None:
                ac.lon = fields["lon"]

            ac.last_update = self._clock()
            return ac

    def expire_stale(self):
        now = self._clock()
        with self._lock:
            stale = [
                hex_ident for hex_ident, ac in self._aircraft.items()
                if now - ac.last_update > self._stale_seconds
            ]
            for hex_ident in stale:
                del self._aircraft[hex_ident]
            return stale

    def snapshot(self):
        """Aircraft with a known position, as a list of Aircraft objects."""
        with self._lock:
            return [ac for ac in self._aircraft.values() if ac.has_position()]

    def __len__(self):
        with self._lock:
            return len(self._aircraft)
