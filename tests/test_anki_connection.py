#!/usr/bin/env python3
"""Test script to verify Anki connection."""

import json
import urllib.request
import urllib.error

def test_anki_connection():
    """Test if AnkiConnect is accessible."""
    print("Testing Anki connection...")
    
    payload = {
        "action": "version",
        "version": 6
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8765", 
            data=data, 
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            
        print("✓ Successfully connected to AnkiConnect!")
        print(f"  AnkiConnect version: {result.get('result')}")
        
        # Test getting deck names
        payload = {"action": "deckNames", "version": 6}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:8765", 
            data=data, 
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            
        decks = result.get("result", [])
        print(f"  Found {len(decks)} decks: {', '.join(decks) if decks else 'None'}")
        
        return True
        
    except urllib.error.URLError as e:
        print("✗ Failed to connect to AnkiConnect")
        print(f"  Error: {e}")
        print("\n  Make sure:")
        print("  1. Anki is running")
        print("  2. AnkiConnect add-on is installed")
        print("  3. AnkiConnect is listening on http://localhost:8765")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_anki_connection()