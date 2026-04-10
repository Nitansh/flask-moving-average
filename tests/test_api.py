import pytest
import json

def test_healthcheck(client):
    """Test the healthcheck endpoint handles live data verification."""
    response = client.get('/healthcheck')
    assert response.status_code in [200, 502, 503]
    data = json.loads(response.data)
    assert "status" in data

def test_live_price_no_symbol(client):
    """Test the live endpoint with no symbol provided."""
    response = client.get('/live')
    # Based on the code, if no symbol is provided, it might return 200 with empty data or error
    # Let's check for basic connectivity
    assert response.status_code == 200

def test_live_price_valid_symbol(client):
    """Test fetching live data for a specific symbol."""
    response = client.get('/live?symbol=RELIANCE')
    assert response.status_code == 200
    data = json.loads(response.data)
    # Check for keys instead of specific data as live data might vary
    assert 'symbol' in data
    assert 'currentPrice' in data

def test_mcap_index(client):
    """Test the root index route with required parameters."""
    response = client.get('/?symbol=RELIANCE&dma=DMA_20,DMA_50')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['symbol'] == 'RELIANCE'
    assert 'DMA_20' in data
