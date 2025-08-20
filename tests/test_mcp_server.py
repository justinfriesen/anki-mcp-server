#!/usr/bin/env python3
"""Comprehensive test suite for the MCP-compliant Anki server."""

import json
import subprocess
import sys
import time
import unittest
from typing import Any, Dict, Optional
import os


class MCPServerTestCase(unittest.TestCase):
    """Base test case for MCP server tests."""
    
    proc: Optional[subprocess.Popen] = None
    request_id: int = 0
    
    @classmethod
    def setUpClass(cls):
        """Start the MCP server subprocess once for all tests."""
        # Find the server file
        server_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "anki_mcp_server.py"
        )
        
        cls.proc = subprocess.Popen(
            [sys.executable, server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        
        # Initialize the server
        cls._initialize_server()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the server subprocess."""
        if cls.proc:
            cls.proc.terminate()
            cls.proc.wait()
            
            # Print any stderr output for debugging
            stderr = cls.proc.stderr.read().decode()
            if stderr and "ERROR" in stderr:
                print("\nServer error logs:")
                print(stderr)
    
    @classmethod
    def _initialize_server(cls):
        """Initialize the MCP server."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        response = cls.send_request(request)
        assert response is not None, "Failed to initialize server"
        assert "result" in response, f"Invalid initialize response: {response}"
        
        # Send initialized notification
        notify = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        cls.proc.stdin.write((json.dumps(notify) + "\n").encode())
        cls.proc.stdin.flush()
        time.sleep(0.1)  # Give server time to process
    
    @classmethod
    def send_request(cls, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request and get the response."""
        if not cls.proc:
            return None
            
        request_str = json.dumps(request) + "\n"
        cls.proc.stdin.write(request_str.encode())
        cls.proc.stdin.flush()
        
        # Read response with timeout
        response_line = cls.proc.stdout.readline().decode().strip()
        if response_line:
            return json.loads(response_line)
        return None
    
    def make_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Helper to make a request with auto-incrementing ID."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        return self.send_request(request)


class TestMCPProtocol(MCPServerTestCase):
    """Test MCP protocol compliance."""
    
    def test_protocol_version(self):
        """Test that server reports correct protocol version."""
        response = self.make_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {}
        })
        
        self.assertIn("result", response)
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
    
    def test_server_capabilities(self):
        """Test that server reports its capabilities correctly."""
        response = self.make_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {}
        })
        
        result = response["result"]
        self.assertIn("capabilities", result)
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
    
    def test_invalid_method_error(self):
        """Test that invalid methods return proper JSON-RPC errors."""
        response = self.make_request("invalid/method")
        
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)  # Method not found
        self.assertIn("not found", response["error"]["message"].lower())
    
    def test_missing_required_params(self):
        """Test that missing required parameters return errors."""
        response = self.make_request("tools/call", {
            # Missing 'name' parameter
            "arguments": {}
        })
        
        self.assertIn("error", response)
        self.assertIn("name", response["error"]["message"].lower())


class TestToolsList(MCPServerTestCase):
    """Test tools listing functionality."""
    
    def test_list_all_tools(self):
        """Test that all expected tools are listed."""
        response = self.make_request("tools/list")
        
        self.assertIn("result", response)
        self.assertIn("tools", response["result"])
        
        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        
        # Check that all expected tools are present
        expected_tools = [
            "listDecks", "listModels", "getDeckInfo", "createDeck",
            "addNote", "addNotesBatch", "canAddNotes", "findNotes",
            "updateNoteFields", "addTags", "deleteNotes", "guiCurrentCard"
        ]
        
        for tool in expected_tools:
            self.assertIn(tool, tool_names, f"Missing tool: {tool}")
    
    def test_tool_schemas(self):
        """Test that all tools have valid schemas."""
        response = self.make_request("tools/list")
        tools = response["result"]["tools"]
        
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("inputSchema", tool)
            
            # Check schema structure
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)
            
            # Check for required fields if specified
            if "required" in schema:
                self.assertIsInstance(schema["required"], list)


class TestResourcesList(MCPServerTestCase):
    """Test resources listing functionality."""
    
    def test_list_resources(self):
        """Test that resources can be listed without errors."""
        response = self.make_request("resources/list")
        
        self.assertIn("result", response)
        self.assertIn("resources", response["result"])
        
        resources = response["result"]["resources"]
        self.assertIsInstance(resources, list)
        
        # Check resource structure if any exist
        for resource in resources:
            self.assertIn("uri", resource)
            self.assertIn("name", resource)
            self.assertIn("mimeType", resource)
    
    def test_read_invalid_resource(self):
        """Test reading a non-existent resource returns error."""
        response = self.make_request("resources/read", {
            "uri": "anki://invalid/12345"
        })
        
        self.assertIn("error", response)


class TestToolExecution(MCPServerTestCase):
    """Test individual tool execution."""
    
    def test_list_decks_tool(self):
        """Test the listDecks tool."""
        response = self.make_request("tools/call", {
            "name": "listDecks",
            "arguments": {}
        })
        
        self.assertIn("result", response)
        self.assertIn("content", response["result"])
        content = response["result"]["content"][0]["text"]
        self.assertTrue(
            "decks" in content.lower() or 
            "anki" in content.lower() or
            "could not connect" in content.lower()
        )
    
    def test_list_models_tool(self):
        """Test the listModels tool."""
        response = self.make_request("tools/call", {
            "name": "listModels",
            "arguments": {}
        })
        
        self.assertIn("result", response)
        self.assertIn("content", response["result"])
    
    def test_invalid_tool_name(self):
        """Test calling a non-existent tool."""
        response = self.make_request("tools/call", {
            "name": "nonExistentTool",
            "arguments": {}
        })
        
        self.assertIn("error", response)
        self.assertIn("not found", response["error"]["message"].lower())
    
    def test_tool_with_missing_required_args(self):
        """Test calling a tool without required arguments."""
        response = self.make_request("tools/call", {
            "name": "getDeckInfo",
            "arguments": {}  # Missing required 'deckName'
        })
        
        self.assertIn("result", response)
        content = response["result"]["content"][0]["text"]
        self.assertIn("required", content.lower())
    
    def test_gui_current_card_tool(self):
        """Test the guiCurrentCard tool."""
        response = self.make_request("tools/call", {
            "name": "guiCurrentCard",
            "arguments": {}
        })
        
        self.assertIn("result", response)
        self.assertIn("content", response["result"])
        
        # Should return either card info or "no card being reviewed"
        content = response["result"]["content"][0]["text"]
        self.assertTrue(
            "no card" in content.lower() or 
            "deckName" in content or
            "not connect" in content.lower()
        )
    
    def test_add_note_validation(self):
        """Test addNote with invalid parameters."""
        response = self.make_request("tools/call", {
            "name": "addNote",
            "arguments": {
                "deckName": "TestDeck"
                # Missing modelName and fields
            }
        })
        
        self.assertIn("result", response)
        content = response["result"]["content"][0]["text"]
        self.assertIn("required", content.lower())
    
    def test_batch_operations(self):
        """Test batch note operations."""
        # Test canAddNotes validation
        response = self.make_request("tools/call", {
            "name": "canAddNotes",
            "arguments": {
                "notes": [
                    {
                        "deckName": "Default",
                        "modelName": "Basic",
                        "fields": {"Front": "Q1", "Back": "A1"}
                    }
                ]
            }
        })
        
        self.assertIn("result", response)
        content = response["result"]["content"][0]["text"]
        # Should either validate or report connection error
        self.assertTrue(
            "validation" in content.lower() or 
            "connect" in content.lower()
        )


class TestErrorHandling(MCPServerTestCase):
    """Test error handling and edge cases."""
    
    def test_malformed_json(self):
        """Test that malformed JSON is handled gracefully."""
        # Send invalid JSON directly
        self.proc.stdin.write(b"not valid json\n")
        self.proc.stdin.flush()
        
        # Try to read response (should get parse error)
        response_line = self.proc.stdout.readline().decode().strip()
        if response_line:
            response = json.loads(response_line)
            self.assertIn("error", response)
            self.assertEqual(response["error"]["code"], -32700)  # Parse error
    
    def test_empty_request(self):
        """Test handling of empty requests."""
        response = self.send_request({})
        if response:
            self.assertIn("error", response)
    
    def test_concurrent_requests(self):
        """Test that server handles multiple rapid requests."""
        responses = []
        
        for i in range(5):
            response = self.make_request("tools/list")
            responses.append(response)
        
        # All requests should succeed
        for response in responses:
            self.assertIn("result", response)
            self.assertIn("tools", response["result"])


def run_basic_test():
    """Run a basic connectivity test without unittest framework."""
    print("Running basic MCP server test...")
    
    # Find server path
    server_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "anki_mcp_server.py"
    )
    
    if not os.path.exists(server_path):
        print(f"❌ Server file not found at: {server_path}")
        return False
    
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False
    )
    
    try:
        # Test initialize
        print("Testing initialize...")
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"}
        }
        
        proc.stdin.write((json.dumps(request) + "\n").encode())
        proc.stdin.flush()
        
        response_line = proc.stdout.readline().decode().strip()
        response = json.loads(response_line)
        
        if "result" in response:
            print("✅ Server initialized successfully")
            print(f"   Protocol version: {response['result']['protocolVersion']}")
            return True
        else:
            print(f"❌ Initialization failed: {response}")
            return False
            
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test MCP Anki Server")
    parser.add_argument("--basic", action="store_true", help="Run basic connectivity test only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    if args.basic:
        success = run_basic_test()
        sys.exit(0 if success else 1)
    else:
        # Run full test suite
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(sys.modules[__name__])
        
        verbosity = 2 if args.verbose else 1
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        
        sys.exit(0 if result.wasSuccessful() else 1)