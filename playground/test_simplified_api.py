#!/usr/bin/env python3

import requests
import json
import time

def test_simplified_api():
    """Test the simplified API with two routes"""
    base_url = "http://localhost:5000"
    
    print("Testing simplified long polling API...")
    
    # Test 1: Connect and start agent
    print("\n1. Testing connection endpoint...")
    connect_data = {
        "task": "Navigate to google.com and take a screenshot"
    }
    
    try:
        response = requests.post(f"{base_url}/api/connect", json=connect_data)
        if response.status_code == 200:
            result = response.json()
            connection_id = result.get("connection_id")
            print(f"✓ Connection established: {connection_id}")
            print(f"  Status: {result.get('status')}")
            print(f"  Message: {result.get('message')}")
        else:
            print(f"✗ Connection failed: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return
    
    # Test 2: Get data (first request should get immediate response)
    print("\n2. Testing first data request...")
    try:
        response = requests.get(f"{base_url}/api/data/{connection_id}")
        if response.status_code == 200:
            data = response.json()
            print("✓ First data request successful")
            print(f"  Timestamp: {data.get('timestamp')}")
            print(f"  Map nodes: {len(data.get('map', {}).get('nodes', []))}")
            print(f"  Map edges: {len(data.get('map', {}).get('edges', []))}")
            print(f"  Pages: {len(data.get('pages', []))}")
            print(f"  Screenshots: {len(data.get('screenshots', {}))}")
            print(f"  Sitewide metrics: {data.get('sitewide_metrics', {})}")
        else:
            print(f"✗ First data request failed: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"✗ First data request error: {e}")
        return
    
    # Test 3: Second request (should wait for new data or timeout)
    print("\n3. Testing second data request (will wait for new data)...")
    print("   This should wait for up to 60 seconds for new data...")
    
    start_time = time.time()
    try:
        response = requests.get(f"{base_url}/api/data/{connection_id}", timeout=65)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "waiting":
                print(f"✓ Timeout response received after {elapsed:.1f}s")
                print(f"  Status: {data.get('status')}")
            else:
                print(f"✓ New data received after {elapsed:.1f}s")
                print(f"  Timestamp: {data.get('timestamp')}")
                print(f"  Pages: {len(data.get('pages', []))}")
        else:
            print(f"✗ Second data request failed: {response.status_code} - {response.text}")
    except requests.Timeout:
        elapsed = time.time() - start_time
        print(f"✓ Request timed out after {elapsed:.1f}s (expected)")
    except Exception as e:
        print(f"✗ Second data request error: {e}")
    
    print("\n✓ API test completed")

if __name__ == "__main__":
    test_simplified_api()
