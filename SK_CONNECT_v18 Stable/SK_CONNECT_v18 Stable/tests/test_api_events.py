import json
import types

import pytest

from app import app as flask_app

class DummyRes:
    def __init__(self, data):
        self.data = data

class DummyTable:
    def __init__(self, data):
        self._data = data
    def select(self, *args, **kwargs):
        return self
    def order(self, *args, **kwargs):
        return self
    def execute(self):
        return DummyRes(self._data)

class DummySupabase:
    def __init__(self, data):
        self._data = data
    def table(self, name):
        return DummyTable(self._data)

@pytest.fixture
def client(monkeypatch):
    # prepare predictable events
    sample = [
        {
            'id': 1,
            'name': 'Test Event 1',
            'date': '2025-10-20',
            'start_time': '09:00',
            'end_time': '11:00',
            'description': 'First test event',
            'location': 'Hall'
        },
        {
            'id': 2,
            'name': 'Test Event 2',
            'date': '2025-10-20',
            'start_time': '',
            'description': 'All day event',
            'location': 'Park'
        }
    ]
    # patch the app.supabase to our dummy
    monkeypatch.setattr('app.supabase', DummySupabase(sample))
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

def test_api_events_returns_events(client):
    res = client.get('/api/events')
    assert res.status_code == 200
    data = res.get_json()
    assert 'events' in data
    assert data['count'] == 2
    # check structure
    ev0 = data['events'][0]
    assert ev0['id'] == 1
    assert ev0['title'] == 'Test Event 1'
    assert ev0['start'] == '2025-10-20T09:00'

def test_api_events_all_day_flag(client):
    res = client.get('/api/events')
    data = res.get_json()
    ev1 = data['events'][1]
    # second event has no start_time, should be allDay
    assert ev1['allDay'] is True
