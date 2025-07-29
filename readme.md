# YouTube Latest Videos MCP Server

An MCP server that allows you to get the latest videos from your YouTube subscriptions.

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Get YouTube API credentials from Google Cloud Console
3. Save credentials as `credentials.json`
4. Configure in Claude Desktop

## Tools
- `get_latest_youtube_videos` - Get latest videos from subscriptions
- `get_subscribed_channels` - List subscribed channels  
- `get_channel_videos` - Get videos from specific channel

## Latest version changes:

1. FastMCP Framework

Simplified syntax using @mcp.tool() decorators
No need for complex async/await handling
Cleaner, more readable code structure

2. UV Compatibility

Updated pyproject.toml for uv package manager
Simplified dependency management
Better project structure

3. Simplified Architecture

Removed complex MCP protocol handling
Direct function-based tools
Easier to debug and maintain

Setup Instructions:
1. Install UV
bash# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
2. Initialize Project
bashcd your-project-directory
uv sync
3. Test the Server
bashuv run python youtube_mcp_server.py
4. Claude Desktop Configuration
json{
  "mcpServers": {
    "youtube-latest-videos": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/your/project",
        "run",
        "python", 
        "youtube_mcp_server.py"
      ]
    }
  }
}
Project Structure:
your-project/
├── pyproject.toml          # UV configuration
├── youtube_mcp_server.py   # FastMCP server
├── credentials.json        # YouTube API credentials
├── token.json             # Auto-generated
├── setup.sh               # Setup script
├── test_server.py         # Test script
└── README.md              # Documentation
Benefits of FastMCP + UV:

Simpler Code: FastMCP reduces boilerplate significantly
Better Dependency Management: UV handles Python dependencies efficiently
Faster Startup: UV's resolver is much faster than pip
Development Friendly: Easy testing and debugging
Modern Toolchain: Uses the latest Python packaging standards
