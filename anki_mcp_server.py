#!/usr/bin/env python3
"""
MCP-compliant server for Anki using the 2025-06-18 protocol version.

This server implements the Model Context Protocol to expose Anki functionality
through AnkiConnect. It supports resources (decks, models, notes) and tools
for creating, updating, and managing Anki content.
"""

import json
import sys
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import requests
except ImportError:
    requests = None
import urllib.request
import urllib.error


# Configure logging to stderr only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class AnkiRequestError(Exception):
    """Raised when an error occurs communicating with AnkiConnect."""


def anki_request(action: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    Make a request to the AnkiConnect HTTP API.
    
    :param action: The AnkiConnect action to call.
    :param params: Parameters for the action. May be None.
    :returns: The `result` field of the JSON response.
    :raises AnkiRequestError: If the request fails or Anki returns an error.
    """
    payload = {"action": action, "version": 6}
    if params:
        payload["params"] = params
    
    try:
        if requests is not None:
            response = requests.post(
                "http://localhost:8765",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        else:
            # Fall back to urllib if requests is unavailable
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:8765", data=data, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise AnkiRequestError(
            f"Could not connect to AnkiConnect at http://localhost:8765: {exc}"
        ) from exc
    except Exception as exc:
        raise AnkiRequestError(f"Error contacting AnkiConnect: {exc}") from exc
    
    if isinstance(data, dict) and data.get("error"):
        raise AnkiRequestError(str(data["error"]))
    return data.get("result")


class MCPServer:
    """
    MCP server implementation following the 2025-06-18 protocol specification.
    """
    
    def __init__(self):
        self.protocol_version = "2025-06-18"
        self.server_info = {
            "name": "anki-mcp",
            "version": "2.0.0"
        }
        self.initialized = False
        # Registry of tools: name -> (description, input_schema, handler)
        self.tools: Dict[str, Tuple[str, Dict[str, Any], Callable[[Dict[str, Any]], Any]]] = {}
    
    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Any],
    ) -> None:
        """Register a tool that can be called via tools/call."""
        self.tools[name] = (description, input_schema, handler)
    
    def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the initialize request."""
        client_version = params.get("protocolVersion", self.protocol_version)
        client_capabilities = params.get("capabilities", {})
        
        logger.info(f"Client requesting protocol version: {client_version}")
        
        # Return our capabilities
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "resources": {
                    "subscribe": False,
                    "listChanged": False
                },
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": self.server_info
        }
    
    def handle_initialized(self, params: Dict[str, Any]) -> None:
        """Handle the initialized notification."""
        self.initialized = True
        logger.info("Server initialized successfully")
    
    def handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a list of available resources (decks, models and notes)."""
        resources: List[Dict[str, Any]] = []
        try:
            # Decks
            deck_map = anki_request("deckNamesAndIds")  # returns {name: id}
            for name, deck_id in deck_map.items():
                resources.append({
                    "uri": f"anki://decks/{deck_id}",
                    "name": f"Deck: {name}",
                    "description": f"Anki deck containing cards",
                    "mimeType": "application/json"
                })
            
            # Models
            model_map = anki_request("modelNamesAndIds")
            for name, model_id in model_map.items():
                resources.append({
                    "uri": f"anki://models/{model_id}",
                    "name": f"Model: {name}",
                    "description": f"Note type template",
                    "mimeType": "application/json"
                })
        except AnkiRequestError as exc:
            logger.error(f"Error listing resources: {exc}")
            # Return empty list if Anki isn't available
            
        return {"resources": resources}
    
    def handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the contents of the specified resource."""
        uri = params.get("uri")
        if not uri:
            raise ValueError("'uri' parameter is required")
        
        if uri.startswith("anki://decks/"):
            deck_id = uri.split("/")[-1]
            return self._read_deck(int(deck_id))
        elif uri.startswith("anki://models/"):
            model_id = uri.split("/")[-1]
            return self._read_model(int(model_id))
        elif uri.startswith("anki://notes/"):
            note_id = uri.split("/")[-1]
            return self._read_note(int(note_id))
        else:
            raise ValueError(f"Unsupported resource URI: {uri}")
    
    def _read_deck(self, deck_id: int) -> Dict[str, Any]:
        """Return detailed information about a deck."""
        deck_map = anki_request("deckNamesAndIds")
        name = next((n for n, i in deck_map.items() if i == deck_id), None)
        if not name:
            raise ValueError(f"Deck ID {deck_id} not found")
        
        note_ids = anki_request("findNotes", {"query": f"deck:'{name}'"})
        due_card_ids = anki_request("findCards", {"query": f"deck:'{name}' is:due"})
        
        info = {
            "deckId": deck_id,
            "name": name,
            "numNotes": len(note_ids),
            "numDueCards": len(due_card_ids),
            "noteIds": note_ids[:10]  # First 10 note IDs as sample
        }
        
        return {
            "contents": [{
                "uri": f"anki://decks/{deck_id}",
                "mimeType": "application/json",
                "text": json.dumps(info, indent=2)
            }]
        }
    
    def _read_model(self, model_id: int) -> Dict[str, Any]:
        """Return detailed information about a model."""
        model_map = anki_request("modelNamesAndIds")
        name = next((n for n, i in model_map.items() if i == model_id), None)
        if not name:
            raise ValueError(f"Model ID {model_id} not found")
        
        fields = anki_request("modelFieldNames", {"modelName": name})
        templates = anki_request("modelTemplates", {"modelName": name})
        styling = anki_request("modelStyling", {"modelName": name})
        
        info = {
            "modelId": model_id,
            "name": name,
            "fields": fields,
            "templates": templates,
            "styling": styling
        }
        
        return {
            "contents": [{
                "uri": f"anki://models/{model_id}",
                "mimeType": "application/json",
                "text": json.dumps(info, indent=2)
            }]
        }
    
    def _read_note(self, note_id: int) -> Dict[str, Any]:
        """Return detailed information about a note."""
        result = anki_request("notesInfo", {"notes": [note_id]})
        info = result[0] if result else {}
        
        return {
            "contents": [{
                "uri": f"anki://notes/{note_id}",
                "mimeType": "application/json",
                "text": json.dumps(info, indent=2)
            }]
        }
    
    def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a list of available tools."""
        tools_list = []
        for name, (desc, schema, _) in self.tools.items():
            tools_list.append({
                "name": name,
                "description": desc,
                "inputSchema": schema
            })
        return {"tools": tools_list}
    
    def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("'name' parameter is required")
        
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        _, _, handler = self.tools[tool_name]
        
        try:
            result = handler(arguments)
            return {
                "content": [{
                    "type": "text",
                    "text": str(result)
                }]
            }
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: {str(e)}"
                }],
                "isError": True
            }
    
    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        
        logger.debug(f"Handling request: {method}")
        
        try:
            # Handle different methods according to MCP spec
            if method == "initialize":
                result = self.handle_initialize(params)
            elif method == "notifications/initialized":
                self.handle_initialized(params)
                return None  # Notifications don't get responses
            elif method == "resources/list":
                result = self.handle_resources_list(params)
            elif method == "resources/read":
                result = self.handle_resources_read(params)
            elif method == "tools/list":
                result = self.handle_tools_list(params)
            elif method == "tools/call":
                result = self.handle_tools_call(params)
            else:
                # Method not found
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
            
            # Return successful response
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            
        except Exception as exc:
            logger.error(f"Error handling request: {exc}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(exc)
                }
            }
    
    # Tool handler methods
    def _tool_list_decks(self, args: Dict[str, Any]) -> str:
        decks = anki_request("deckNames")
        return f"Available decks: {', '.join(decks)}" if decks else "No decks found."
    
    def _tool_list_models(self, args: Dict[str, Any]) -> str:
        models = anki_request("modelNames")
        return f"Available models: {', '.join(models)}" if models else "No models found."
    
    def _tool_get_deck_info(self, args: Dict[str, Any]) -> str:
        deck_name = args.get("deckName")
        if not deck_name:
            raise ValueError("'deckName' is required")
        
        deck_map = anki_request("deckNamesAndIds")
        deck_id = deck_map.get(deck_name)
        if deck_id is None:
            raise ValueError(f"Deck '{deck_name}' not found")
        
        note_ids = anki_request("findNotes", {"query": f"deck:'{deck_name}'"})
        due_ids = anki_request("findCards", {"query": f"deck:'{deck_name}' is:due"})
        
        info = {
            "deckId": deck_id,
            "name": deck_name,
            "numNotes": len(note_ids),
            "numDueCards": len(due_ids)
        }
        return json.dumps(info, indent=2)
    
    def _tool_create_deck(self, args: Dict[str, Any]) -> str:
        name = args.get("deckName")
        if not name:
            raise ValueError("'deckName' is required")
        
        result = anki_request("createDeck", {"deck": name})
        if result is None:
            return f"Deck '{name}' already exists."
        return f"Created deck '{name}' with ID {result}."
    
    def _tool_add_note(self, args: Dict[str, Any]) -> str:
        required = ["deckName", "modelName", "fields"]
        for key in required:
            if key not in args or not args[key]:
                raise ValueError(f"'{key}' is required")
        
        note = {
            "deckName": args["deckName"],
            "modelName": args["modelName"],
            "fields": args["fields"],
            "options": args.get("options", {"allowDuplicate": False}),
            "tags": args.get("tags", [])
        }
        
        note_id = anki_request("addNote", {"note": note})
        if note_id is None:
            return "Failed to create note (possibly duplicate)."
        return f"Created note with ID {note_id}."
    
    def _tool_find_notes(self, args: Dict[str, Any]) -> str:
        query = args.get("query")
        if not query:
            raise ValueError("'query' is required")
        
        ids = anki_request("findNotes", {"query": query})
        if not ids:
            return "No notes found."
        
        # Get info for first few notes
        sample_ids = ids[:5]
        notes_info = anki_request("notesInfo", {"notes": sample_ids})
        
        result = f"Found {len(ids)} notes. First {len(sample_ids)}:\n"
        for note in notes_info:
            fields_summary = ", ".join(f"{k}: {v[:30]}..." if len(v) > 30 else f"{k}: {v}" 
                                     for k, v in note.get("fields", {}).items())
            result += f"- ID {note['noteId']}: {fields_summary}\n"
        
        return result
    
    def _tool_update_note_fields(self, args: Dict[str, Any]) -> str:
        note_id = args.get("noteId")
        fields = args.get("fields")
        if note_id is None or fields is None:
            raise ValueError("'noteId' and 'fields' are required")
        
        anki_request("updateNoteFields", {"note": {"id": note_id, "fields": fields}})
        return f"Updated fields for note {note_id}."
    
    def _tool_add_tags(self, args: Dict[str, Any]) -> str:
        note_ids = args.get("noteIds", [])
        tags = args.get("tags", [])
        
        if not note_ids or not tags:
            raise ValueError("'noteIds' and 'tags' are required")
        
        if isinstance(note_ids, int):
            note_ids = [note_ids]
        
        tags_str = " ".join(tags) if isinstance(tags, list) else tags
        anki_request("addTags", {"notes": note_ids, "tags": tags_str})
        
        return f"Added tags '{tags_str}' to {len(note_ids)} note(s)."
    
    def _tool_delete_notes(self, args: Dict[str, Any]) -> str:
        note_ids = args.get("noteIds", args.get("noteId"))
        if not note_ids:
            raise ValueError("'noteIds' or 'noteId' is required")
        
        if isinstance(note_ids, int):
            note_ids = [note_ids]
        
        anki_request("deleteNotes", {"notes": note_ids})
        return f"Deleted {len(note_ids)} note(s)."
    
    def _tool_add_notes_batch(self, args: Dict[str, Any]) -> str:
        """Add multiple notes in a single batch operation for maximum efficiency."""
        notes = args.get("notes")
        if not notes or not isinstance(notes, list):
            raise ValueError("'notes' must be a list of note objects")
        
        # Validate each note has required fields
        for i, note in enumerate(notes):
            required = ["deckName", "modelName", "fields"]
            for key in required:
                if key not in note or not note[key]:
                    raise ValueError(f"Note {i}: '{key}' is required")
            
            # Ensure tags is present (can be empty list)
            if "tags" not in note:
                note["tags"] = []
            
            # Set default options if not provided
            if "options" not in note:
                note["options"] = {"allowDuplicate": False}
        
        # Make the batch request
        result = anki_request("addNotes", {"notes": notes})
        
        # Analyze results
        successful = [id_ for id_ in result if id_ is not None]
        failed = [i for i, id_ in enumerate(result) if id_ is None]
        
        response = f"Batch operation completed: {len(successful)} notes created successfully"
        if failed:
            response += f", {len(failed)} notes failed (possibly duplicates)"
            response += f"\nFailed note indices: {failed}"
        
        if successful:
            response += f"\nCreated note IDs: {successful}"
        
        return response
    
    def _tool_can_add_notes(self, args: Dict[str, Any]) -> str:
        """Check if notes can be added before attempting batch creation."""
        notes = args.get("notes")
        if not notes or not isinstance(notes, list):
            raise ValueError("'notes' must be a list of note objects")
        
        # Use AnkiConnect's canAddNotes to validate
        result = anki_request("canAddNotes", {"notes": notes})
        
        valid_count = sum(result)
        invalid_indices = [i for i, valid in enumerate(result) if not valid]
        
        response = f"Validation completed: {valid_count}/{len(notes)} notes can be added"
        if invalid_indices:
            response += f"\nInvalid note indices: {invalid_indices}"
        
        return response
    
    def _tool_gui_current_card(self, args: Dict[str, Any]) -> str:
        """Get information about the card currently being reviewed in Anki."""
        try:
            result = anki_request("guiCurrentCard")
            
            if result is None:
                return "No card is currently being reviewed in Anki."
            
            import re
            
            def clean_html_content(html_text):
                """Remove CSS styles and clean up HTML content."""
                if not html_text:
                    return ""
                # Remove style tags and their content
                text = re.sub(r'<style[^>]*>.*?</style>', '', html_text, flags=re.DOTALL)
                # Replace br tags with newlines
                text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
                # Remove remaining HTML tags but keep content
                text = re.sub(r'<[^>]+>', '', text)
                # Clean up excessive whitespace
                text = re.sub(r'\n\s*\n', '\n', text)
                text = text.strip()
                return text
            
            # Extract clean field values
            fields = result.get("fields", {})
            
            # Try to get question/answer from fields first (cleaner), otherwise from HTML
            question = ""
            answer = ""
            
            # Check for standard field names
            if "Front" in fields:
                question = fields["Front"].get("value", "") if isinstance(fields["Front"], dict) else fields["Front"]
            elif result.get("question"):
                question = clean_html_content(result.get("question", ""))
                
            if "Back" in fields:
                answer = fields["Back"].get("value", "") if isinstance(fields["Back"], dict) else fields["Back"]
            elif result.get("answer"):
                answer = clean_html_content(result.get("answer", ""))
            
            # Simple, clean output with just Q&A
            card_info = {
                "deckName": result.get("deckName"),
                "question": question,
                "answer": answer
            }
            
            return json.dumps(card_info, indent=2)
        except AnkiRequestError as e:
            if "Collection is not open" in str(e):
                return "Anki is not currently in review mode or no deck is open."
            return f"Error getting current card: {str(e)}"


def main():
    """Main entry point for the MCP server."""
    server = MCPServer()
    
    # Register all tools
    server.register_tool(
        name="listDecks",
        description="Get the names of all decks in Anki",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        },
        handler=server._tool_list_decks
    )
    
    server.register_tool(
        name="listModels",
        description="Get the names of all note models in Anki",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        },
        handler=server._tool_list_models
    )
    
    server.register_tool(
        name="getDeckInfo",
        description="Get information about a specific deck",
        input_schema={
            "type": "object",
            "properties": {
                "deckName": {
                    "type": "string",
                    "description": "Name of the deck"
                }
            },
            "required": ["deckName"],
            "additionalProperties": False
        },
        handler=server._tool_get_deck_info
    )
    
    server.register_tool(
        name="createDeck",
        description="Create a new deck",
        input_schema={
            "type": "object",
            "properties": {
                "deckName": {
                    "type": "string",
                    "description": "Name of the new deck"
                }
            },
            "required": ["deckName"],
            "additionalProperties": False
        },
        handler=server._tool_create_deck
    )
    
    server.register_tool(
        name="addNote",
        description="Create a new note",
        input_schema={
            "type": "object",
            "properties": {
                "deckName": {
                    "type": "string",
                    "description": "Name of the deck"
                },
                "modelName": {
                    "type": "string",
                    "description": "Name of the note model"
                },
                "fields": {
                    "type": "object",
                    "description": "Field name to value mapping"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags"
                },
                "options": {
                    "type": "object",
                    "properties": {
                        "allowDuplicate": {
                            "type": "boolean",
                            "description": "Allow duplicate notes"
                        }
                    }
                }
            },
            "required": ["deckName", "modelName", "fields"],
            "additionalProperties": False
        },
        handler=server._tool_add_note
    )
    
    server.register_tool(
        name="findNotes",
        description="Search for notes using Anki's query syntax",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Anki search query"
                }
            },
            "required": ["query"],
            "additionalProperties": False
        },
        handler=server._tool_find_notes
    )
    
    server.register_tool(
        name="updateNoteFields",
        description="Update fields of an existing note",
        input_schema={
            "type": "object",
            "properties": {
                "noteId": {
                    "type": "integer",
                    "description": "ID of the note to update"
                },
                "fields": {
                    "type": "object",
                    "description": "Field name to new value mapping"
                }
            },
            "required": ["noteId", "fields"],
            "additionalProperties": False
        },
        handler=server._tool_update_note_fields
    )
    
    server.register_tool(
        name="addTags",
        description="Add tags to notes",
        input_schema={
            "type": "object",
            "properties": {
                "noteIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of note IDs"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add"
                }
            },
            "required": ["noteIds", "tags"],
            "additionalProperties": False
        },
        handler=server._tool_add_tags
    )
    
    server.register_tool(
        name="deleteNotes",
        description="Delete one or more notes",
        input_schema={
            "type": "object",
            "properties": {
                "noteId": {
                    "type": "integer",
                    "description": "Single note ID"
                },
                "noteIds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of note IDs"
                }
            },
            "additionalProperties": False
        },
        handler=server._tool_delete_notes
    )
    
    server.register_tool(
        name="addNotesBatch",
        description="Create multiple notes in a single efficient batch operation - USE THIS instead of multiple addNote calls",
        input_schema={
            "type": "object",
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "deckName": {
                                "type": "string",
                                "description": "Name of the deck"
                            },
                            "modelName": {
                                "type": "string", 
                                "description": "Name of the note model (e.g., 'Basic', 'Cloze')"
                            },
                            "fields": {
                                "type": "object",
                                "description": "Field name to value mapping (e.g., {'Front': 'Question', 'Back': 'Answer'})"
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional tags to apply"
                            },
                            "options": {
                                "type": "object",
                                "properties": {
                                    "allowDuplicate": {
                                        "type": "boolean",
                                        "description": "Allow duplicate notes (default: false)"
                                    }
                                },
                                "description": "Optional settings"
                            }
                        },
                        "required": ["deckName", "modelName", "fields"],
                        "additionalProperties": False
                    },
                    "description": "List of notes to create",
                    "minItems": 1
                }
            },
            "required": ["notes"],
            "additionalProperties": False
        },
        handler=server._tool_add_notes_batch
    )
    
    server.register_tool(
        name="canAddNotes",
        description="Validate if notes can be added before attempting batch creation (useful for checking duplicates)",
        input_schema={
            "type": "object",
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "deckName": {"type": "string"},
                            "modelName": {"type": "string"},
                            "fields": {"type": "object"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["deckName", "modelName", "fields"]
                    },
                    "description": "List of candidate notes to validate"
                }
            },
            "required": ["notes"],
            "additionalProperties": False
        },
        handler=server._tool_can_add_notes
    )
    
    server.register_tool(
        name="guiCurrentCard",
        description="Get information about the card currently being reviewed in Anki",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        },
        handler=server._tool_gui_current_card
    )
    
    logger.info("Anki MCP Server v2 starting...")
    
    # Main loop: read JSON-RPC messages from stdin
    for line in sys.stdin:
        if not line.strip():
            continue
        
        try:
            request = json.loads(line)
            logger.debug(f"Received request: {request}")
            
            response = server.handle_request(request)
            
            # Only send response if it's not a notification
            if response is not None:
                print(json.dumps(response), flush=True)
                logger.debug(f"Sent response: {response}")
                
        except json.JSONDecodeError as exc:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {exc}"
                }
            }
            print(json.dumps(error_response), flush=True)
        except Exception as exc:
            logger.error(f"Unexpected error: {exc}", exc_info=True)


if __name__ == "__main__":
    main()