# Anki MCP Server

A Model Context Protocol (MCP) server that provides AI assistants with access to Anki flashcard functionality through AnkiConnect.

## Prerequisites

1. **Anki** - The desktop application must be running
2. **AnkiConnect** - Install from Anki's add-on menu (code: 2055492159)
3. **Python 3.6+** - Required to run the server

## Features

### Resources
- Browse and read deck information
- View note model (card type) details
- Access individual note contents

### Tools
- `listDecks` - List all available decks
- `listModels` - List all note models
- `getDeckInfo` - Get statistics for a specific deck
- `createDeck` - Create a new deck
- `addNote` - Create a single flashcard
- **`addNotesBatch`** - **Create multiple flashcards in one efficient operation** ⭐
- `canAddNotes` - Validate notes before batch creation (check for duplicates/errors)
- `findNotes` - Search for notes using Anki's query syntax
- `updateNoteFields` - Update existing note content
- `addTags` - Add tags to notes
- `deleteNotes` - Delete notes
- `guiCurrentCard` - Get the card currently being reviewed in Anki

## Installation

### Prerequisites
1. **Anki Desktop** - Must be running when using the MCP server
2. **AnkiConnect Add-on** - Install in Anki via Tools → Add-ons → Get Add-ons → Code: `2055492159`
3. **Python 3.6+** - Required to run the server
4. **Claude Desktop** - Download from [claude.ai](https://claude.ai/download)

### Minimal Installation (Easiest)

1. **Download just the server file:**
   ```bash
   curl -O https://raw.githubusercontent.com/justinfriesen/anki-mcp-server/main/anki_mcp_server.py
   ```
   Or manually download `anki_mcp_server.py` from the repository.

2. **Configure Claude Desktop:**
   
   Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
   
   ```json
   {
     "mcpServers": {
       "anki": {
         "command": "python3",
         "args": ["/path/to/anki_mcp_server.py"]
       }
     }
   }
   ```

3. **Restart Claude Desktop** - That's it! 🎉

### Full Setup (Recommended for developers)

1. **Clone this repository:**
   ```bash
   git clone https://github.com/justinfriesen/anki-mcp-server.git
   cd anki-mcp-server
   ```

2. **Install dependencies (optional):**
   ```bash
   pip install -r requirements.txt  # Only if you want requests library
   ```

3. **Configure Claude Desktop:**
   
   Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
   
   ```json
   {
     "mcpServers": {
       "anki": {
         "command": "python3",
         "args": ["/absolute/path/to/anki_mcp_server.py"]
       }
     }
   }
   ```
   
   Replace `/absolute/path/to/` with your actual path to the cloned repository.

4. **Restart Claude Desktop**

5. **Test the connection:**
   - Open Anki
   - Open Claude Desktop  
   - Ask Claude: "What Anki decks do I have?"

## Usage

### With Claude Desktop

See installation instructions above for configuring Claude Desktop.

### With Other MCP Clients

The server communicates via stdio (standard input/output) using JSON-RPC 2.0 messages.

### Testing

Run the test scripts to verify everything is working:

```bash
python3 tests/test_anki_connection.py  # Test AnkiConnect
python3 tests/test_mcp_server.py       # Test MCP server
```

## Example Usage

Once connected, an AI assistant can:

1. **Create a new deck:**
   "Create an Anki deck called 'Spanish Vocabulary'"

2. **Add flashcards efficiently:**
   "Create 10 Spanish vocabulary flashcards for common greetings" (uses batch upload)

3. **Search and update:**
   "Find all notes tagged 'verb' and add the tag 'conjugation'"

4. **Get deck statistics:**
   "How many cards are due for review in my Default deck?"

5. **Help with the card you're reviewing:**
   "What's the card I'm looking at?" (shows current card)
   "Can you explain this concept in more detail?" (Claude sees your card and provides explanation)
   "Give me a mnemonic to remember this answer"

## Protocol Details

This server implements MCP protocol version 2025-06-18 with:
- Full resources support (list and read)
- Tools with JSON Schema validation
- Proper error handling and logging
- Stdio transport

## Troubleshooting

1. **Connection Error**: Make sure Anki is running and AnkiConnect is installed
2. **Port Issues**: AnkiConnect uses port 8765 by default
3. **Permission Errors**: Some Anki operations may require specific permissions in AnkiConnect settings

## License

MIT License - See LICENSE file for details