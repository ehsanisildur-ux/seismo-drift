from datetime import date, timedelta
from pathlib import Path
import json
import re

import pytest


URL = 'https://earthquake.usgs.gov/fdsnws/event/1/query'
CONFIG = {'start': '2019-07-03', 'west': -119, 'east': -116, 'south': 34, 'north': 37,
          'allowance': 2, 'trigger': 2, 'clear': 0}


def query(day):
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    return (f'{URL}?format=geojson&starttime={day}&endtime={tomorrow}&minlatitude=34&maxlatitude=37'
            '&minlongitude=-119&maxlongitude=-116&minmagnitude=4.5&limit=65&orderby=time-asc&eventtype=earthquake')


def deploy(vm, direct_deploy, config=CONFIG):
    vm.warp('2020-01-01T00:00:00+00:00')
    return direct_deploy('contracts/seismo_drift.py', 'sd1:' + json.dumps(config), sdk_version='v0.2.16')


def fixture(day):
    return json.loads(Path(f'fixtures/{day}.json').read_bytes())


def mock(vm, day, document, status=200):
    vm.clear_mocks()
    body = document if isinstance(document, bytes) else json.dumps(document).encode()
    vm.mock_web(re.escape(query(day)), {'status': status, 'body': body})


def test_historical_signal_opens_at_threshold_holds_then_clears(direct_vm, direct_deploy, direct_bob):
    contract = deploy(direct_vm, direct_deploy)
    direct_vm.sender = direct_bob
    expected = [
        ('2019-07-03', 0, 0, False, 'HOLD'),
        ('2019-07-04', 4, 2, True, 'OPEN'),
        ('2019-07-05', 1, 1, True, 'HOLD')
    ]
    for day, count, score, active, transition in expected:
        mock(direct_vm, day, fixture(day))
        contract.advance(day)
        assert direct_vm.run_validator() is True
        observed = contract.get_day(day)
        assert (observed['count'], observed['score'], observed['active'], observed['transition']) == (
            count, score, active, transition)
    empty = fixture('2019-07-03')
    empty['metadata']['url'] = query('2019-07-06')
    mock(direct_vm, '2019-07-06', empty)
    contract.advance('2019-07-06')
    assert contract.get_day('2019-07-06')['transition'] == 'CLEAR'
    assert not contract.get_state()['active']
    assert contract.get_day('2019-07-04')['transition'] == 'OPEN'


def test_validator_checks_exact_events_even_if_the_count_is_equal(direct_vm, direct_deploy):
    day = '2019-07-04'
    contract = deploy(direct_vm, direct_deploy, {**CONFIG, 'start': day})
    record = fixture(day)
    mock(direct_vm, day, record)
    contract.advance(day)
    record['features'].reverse()
    record['metadata']['generated'] += 4
    mock(direct_vm, day, record)
    assert direct_vm.run_validator() is True
    record['features'][0]['id'] = 'substituted-event'
    mock(direct_vm, day, record)
    assert direct_vm.run_validator() is False
    events = contract.get_day(day)['events']
    assert direct_vm.run_validator(leader_result=events[:-1]) is False
    assert len(events) == 4


def test_day_progression_is_atomic_and_lagged(direct_vm, direct_deploy):
    day = CONFIG['start']
    contract = deploy(direct_vm, direct_deploy)
    initial = contract.get_state()
    with direct_vm.expect_revert('Expected the next unsealed day'):
        contract.advance('2019-07-04')
    direct_vm.warp('2019-07-05T23:59:59+00:00')
    with direct_vm.expect_revert('Catalog settlement lag has not elapsed'):
        contract.advance(day)
    assert contract.get_state() == initial
    direct_vm.warp('2019-07-06T00:00:00+00:00')
    mock(direct_vm, day, fixture(day))
    contract.advance(day)
    before = contract.get_state()
    with direct_vm.expect_revert('Expected the next unsealed day'):
        contract.advance(day)
    assert contract.get_state() == before


def test_explicit_daily_cap_and_half_open_end(direct_vm, direct_deploy):
    day = '2019-07-04'
    document = fixture(day)
    event = document['features'][0]
    document['features'] = [{**event, 'id': f'event-{n:02}'} for n in range(64)]
    document['features'].append({**event, 'id': 'tomorrow',
                                 'properties': {**event['properties'], 'time': 1562284800000}})
    contract = deploy(direct_vm, direct_deploy, {**CONFIG, 'start': day})
    mock(direct_vm, day, document)
    contract.advance(day)
    result = contract.get_day(day)
    assert result['count'] == 64 and result['at_cap'] is True
    assert len({event['id'] for event in result['events']}) == 64
    assert result['events'][-1]['id'] == 'event-63'
    assert result['score'] == 62


@pytest.mark.parametrize('case', ['http', 'invalid', 'repeat', 'magnitude', 'coordinates', 'time', 'query'])
def test_invalid_observations_never_advance(direct_vm, direct_deploy, case):
    day = '2019-07-04'
    contract = deploy(direct_vm, direct_deploy, {**CONFIG, 'start': day})
    document = fixture(day)
    event = document['features'][0]
    status = 200
    if case == 'http':
        status = 503
    elif case == 'invalid':
        document = b'{ "features": [] }'
    elif case == 'repeat':
        document['features'].append(event)
    elif case == 'magnitude':
        event['properties']['mag'] = 4.4999999
    elif case == 'coordinates':
        event['geometry']['coordinates'][0] = -120
    elif case == 'query':
        document['metadata']['url'] = query('2019-07-05')
    else:
        event['properties']['time'] = 0
    mock(direct_vm, day, document, status)
    with direct_vm.expect_revert():
        contract.advance(day)
    assert contract.get_state()['next_day'] == day and contract.get_day(day) == {}
    mock(direct_vm, day, fixture(day))
    contract.advance(day)
    assert contract.get_day(day)['count'] == 4
