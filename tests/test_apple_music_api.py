import importlib
import sys
import types


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetch_metadata_retries_until_success(monkeypatch):
    calls = {'count': 0}

    fake_requests = types.SimpleNamespace()

    def fake_get(url, timeout):
        calls['count'] += 1
        if calls['count'] < 3:
            raise RuntimeError('temporary failure')

        return DummyResponse({
            'results': [{
                'artistName': 'Artist',
                'trackName': 'Track',
                'collectionName': 'Album',
                'trackNumber': 4,
                'trackCount': 10,
            }],
        })

    fake_requests.get = fake_get
    monkeypatch.setitem(sys.modules, 'requests', fake_requests)
    sys.modules.pop('core.apple_music_api', None)

    apple_music_api = importlib.import_module('core.apple_music_api')
    metadata = apple_music_api.fetch_metadata(
        'https://music.apple.com/mx/album/example/1754429349?i=1754429354'
    )

    assert calls['count'] == 3
    assert metadata == {
        'artist': 'Artist',
        'track': 'Track',
        'album': 'Album',
        'track_number': 4,
        'track_count': 10,
    }
