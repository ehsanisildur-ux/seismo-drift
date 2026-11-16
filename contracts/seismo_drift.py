# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re


SOURCE = 'https://earthquake.usgs.gov/fdsnws/event/1/query'
SCALE = 10**7
DAY_MS = 86_400_000
EPOCH = date(1970, 1, 1)
CAP = 64


def fail(message):
    raise gl.vm.UserError(message)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse(text, reason):
    try:
        return json.loads(text, parse_float=str, object_pairs_hook=unique_keys)
    except ValueError:
        fail(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def day_of(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        fail('Invalid UTC day')
    try:
        day = date.fromisoformat(value)
    except ValueError:
        fail('Invalid UTC day')
    if day.year < 2000:
        fail('UTC day before supported catalog window')
    return day


def config_from(text):
    if not text.startswith('sd1:') or len(text) > 512:
        fail('Invalid monitor configuration')
    config = parse(text[4:], 'Invalid monitor configuration')
    keys = {'start', 'west', 'east', 'south', 'north', 'allowance', 'trigger', 'clear'}
    if not isinstance(config, dict) or set(config) != keys:
        fail('Invalid monitor configuration')
    day_of(config['start'])
    if any(type(config[key]) is not int for key in keys - {'start'}):
        fail('Monitor parameters must be integers')
    w, e, s, n = (config[key] for key in ('west', 'east', 'south', 'north'))
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90 and e - w <= 4 and n - s <= 4):
        fail('Invalid bounded region')
    if not (1 <= config['allowance'] < CAP and 0 <= config['clear'] < config['trigger'] <= 1024):
        fail('Invalid cumulative thresholds')
    return config


def url_for(day, config):
    end = day + timedelta(days=1)
    return (f"{SOURCE}?format=geojson&starttime={day.isoformat()}&endtime={end.isoformat()}"
            f"&minlatitude={config['south']}&maxlatitude={config['north']}"
            f"&minlongitude={config['west']}&maxlongitude={config['east']}"
            f"&minmagnitude=4.5&limit={CAP+1}&orderby=time-asc&eventtype=earthquake")


def fixed(value):
    if type(value) is not int and not isinstance(value, str):
        fail('Invalid catalog decimal')
    match = re.fullmatch(r'(-?)([0-9]{1,3})(?:\.([0-9]{1,7}))?', str(value))
    if not match:
        fail('Invalid catalog decimal')
    sign, whole, fractional = match.groups()
    scaled = int(whole) * SCALE + int((fractional or '').ljust(7, '0'))
    return -scaled if sign else scaled


def normalize(raw, day, config, url):
    if not isinstance(raw, dict) or raw.get('type') != 'FeatureCollection':
        fail('Invalid catalog response')
    meta, features = raw.get('metadata'), raw.get('features')
    if (not isinstance(meta, dict) or meta.get('status') != 200 or meta.get('limit') != CAP + 1
            or meta.get('offset') != 1 or meta.get('url') != url
            or not isinstance(features, list) or len(features) > CAP + 1):
        fail('Unexpected catalog query result')
    start = (day - EPOCH).days * DAY_MS
    end = start + DAY_MS
    events = []
    seen = set()
    for item in features:
        if not isinstance(item, dict) or item.get('type') != 'Feature':
            fail('Invalid catalog feature')
        event_id, props, geometry = item.get('id'), item.get('properties'), item.get('geometry')
        if (not isinstance(event_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', event_id)
                or event_id in seen or not isinstance(props, dict) or props.get('type') != 'earthquake'
                or not isinstance(geometry, dict) or geometry.get('type') != 'Point'):
            fail('Invalid or repeated catalog event')
        seen.add(event_id)
        time = props.get('time')
        if type(time) is not int or not start <= time <= end:
            fail('Catalog event outside requested day')
        coords = geometry.get('coordinates')
        if not isinstance(coords, list) or len(coords) != 3:
            fail('Invalid earthquake coordinates')
        lon, lat, magnitude = fixed(coords[0]), fixed(coords[1]), fixed(props.get('mag'))
        if not (config['west'] * SCALE <= lon <= config['east'] * SCALE
                and config['south'] * SCALE <= lat <= config['north'] * SCALE
                and 45 * SCALE // 10 <= magnitude <= 10 * SCALE):
            fail('Catalog event outside region or magnitude filter')
        if time < end:
            events.append({'id': event_id, 'time_ms': time, 'longitude_e7': lon, 'latitude_e7': lat,
                           'magnitude_e7': magnitude})
    events.sort(key=lambda event: (event['time_ms'], event['id']))
    return events[:CAP]


def observe(day, config, url):
    def fetch():
        response = gl.nondet.web.get(url)
        if response.status != 200 or not 1 <= len(response.body) <= 240000:
            fail('USGS catalog unavailable')
        try:
            text = response.body.decode('utf-8')
        except UnicodeError:
            fail('Invalid catalog JSON')
        return normalize(parse(text, 'Invalid catalog JSON'), day, config, url)

    def verify(proposal):
        try:
            independent = fetch()
        except gl.vm.UserError as error:
            return not isinstance(proposal, gl.vm.Return) and getattr(proposal, 'message', None) == error.message
        except Exception:
            return False
        return isinstance(proposal, gl.vm.Return) and encode(proposal.calldata) == encode(independent)

    return gl.vm.run_nondet_unsafe(fetch, verify)


class SeismoDrift(gl.Contract):
    configuration: str
    next_day: u256
    score: u256
    active: bool
    history: TreeMap[u256, str]

    def __init__(self, config: str):
        values = config_from(config)
        self.configuration = encode(values)
        self.next_day = u256(day_of(values['start']).toordinal())
        self.score = u256(0)
        self.active = False

    @gl.public.write
    def advance(self, expected_day: str) -> None:
        day = day_of(expected_day)
        key = u256(day.toordinal())
        if key != self.next_day:
            fail('Expected the next unsealed day')
        if (datetime.now(timezone.utc).date() - day).days < 3:
            fail('Catalog settlement lag has not elapsed')

        config = json.loads(self.configuration)
        url = url_for(day, config)
        events = observe(day, config, url)
        before_score, before_active = int(self.score), self.active
        count = len(events)
        score = max(0, before_score + count - config['allowance'])
        active = score > config['clear'] if before_active else score >= config['trigger']
        transition = 'HOLD' if before_active == active else 'OPEN' if active else 'CLEAR'
        self.history[key] = encode({
            'day': expected_day, 'source': url, 'events': events,
            'observation_sha256': sha256(encode(events).encode()).hexdigest(),
            'count': count, 'at_cap': count == CAP, 'score_before': before_score, 'score': score,
            'active_before': before_active, 'active': active, 'transition': transition
        })
        self.score = u256(score)
        self.active = active
        self.next_day = u256(int(key) + 1)

    @gl.public.view
    def get_state(self) -> dict:
        return {'config': json.loads(self.configuration), 'next_day': date.fromordinal(int(self.next_day)).isoformat(),
                'score': int(self.score), 'active': self.active}

    @gl.public.view
    def get_day(self, day: str) -> dict:
        key = u256(day_of(day).toordinal())
        return json.loads(self.history[key]) if key in self.history else {}
