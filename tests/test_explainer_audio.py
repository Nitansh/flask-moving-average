import pytest
import json
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_explainer_voices_endpoint(client):
    response = client.get('/api/explainer/voices')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'voices' in data
    assert len(data['voices']) >= 1
    assert data['default'] == 'en-IN-PrabhatNeural'


def test_explainer_audio_missing_text(client):
    response = client.post('/api/explainer/audio', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['status'] == 'error'


def test_explainer_audio_synthesis(client):
    # Quick short sentence test
    response = client.post('/api/explainer/audio', json={
        "text": "Golden trading rule for Titan. Any level below CMP is support.",
        "symbol": "TITAN",
        "voice": "en-IN-PrabhatNeural"
    })
    assert response.status_code == 200
    assert response.mimetype == "audio/mpeg"
    assert len(response.data) > 500  # Generated valid MP3 bytes
    assert "TITAN_explainer.mp3" in response.headers.get("Content-Disposition", "")
