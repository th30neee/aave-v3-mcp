# Aave MCP Server - Local Setup Guide

## Quick Start

### 1. Prerequisites

- Python 3.10 or higher
- pip or uv package manager

### 2. Installation

```bash
# Clone or download the files to a directory
cd aave-mcp-server

# Option A: Using pip
pip install -r requirements.txt

# Option B: Using uv (recommended)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 3. Test the Server

```bash
# Run the test suite
python test_server.py

# Expected output:
# ============================================================
# Aave MCP Server - Test Suite
# ============================================================
# Testing get_supported_chains()...
#   ✓ Found 12 chains
# ...
```

### 4. Run the Server

```bash
# Start the MCP server (stdio mode for Claude Desktop)
python aave_mcp_server.py
```

---

## Integrating with Claude Desktop

### Step 1: Find Your Config File

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### Step 2: Add the Server Configuration

Edit the config file and add (or merge with existing):

```json
{
  "mcpServers": {
    "aave-v3": {
      "command": "python",
      "args": ["/full/path/to/aave-mcp-server/aave_mcp_server.py"]
    }
  }
}
```

**Important:** Replace `/full/path/to/` with the actual absolute path.

### Step 3: Restart Claude Desktop

Close and reopen Claude Desktop. You should see the Aave tools available.

---

## Integrating with Other LLM Clients

### OpenAI Agents SDK

```python
from agents.mcp import MCPServerStdio

async with MCPServerStdio(
    name="aave-v3",
    params={
        "command": "python",
        "args": ["/path/to/aave_mcp_server.py"]
    }
) as server:
    # Use with your agent
    pass
```

### Generic MCP Client

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["/path/to/aave_mcp_server.py"]
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        
        # List available tools
        tools = await session.list_tools()
        print(tools)
        
        # Call a tool
        result = await session.call_tool(
            "get_markets",
            {"chain_ids": [1]}
        )
        print(result)
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `get_supported_chains` | List all supported blockchain networks |
| `get_markets` | Fetch markets with TVL and APY data |
| `get_market_details` | Detailed market information |
| `get_user_positions` | User's supply and borrow positions |
| `get_user_market_state` | Health factor and liquidation risk |
| `get_user_transaction_history` | Historical transactions |
| `get_reserve_details` | Asset-specific information |
| `get_apy_history` | Historical APY data |
| `prepare_supply_transaction` | Prepare supply tx data |
| `prepare_borrow_transaction` | Prepare borrow tx data |
| `prepare_repay_transaction` | Prepare repay tx data |
| `prepare_withdraw_transaction` | Prepare withdraw tx data |
| `get_vaults` | List yield vaults |
| `get_vault_details` | Vault information |
| `get_gho_balance` | sGHO balance |

---

## Example Usage in Claude

Once configured, you can ask Claude:

- "What are the current Aave markets on Ethereum?"
- "Check the health factor for wallet 0x..."
- "What's the best APY for USDC across all chains?"
- "Prepare a transaction to supply 100 USDC to Aave"
- "Analyze my DeFi positions on 0x..."

---

## Troubleshooting

### Server won't start
- Ensure Python 3.10+ is installed: `python --version`
- Check dependencies are installed: `pip list | grep mcp`

### Claude doesn't see the tools
- Verify the path in config is absolute and correct
- Check Claude Desktop logs for errors
- Restart Claude Desktop completely

### API errors
- The Aave API may rate limit requests
- Some chains may have temporary issues
- Check your network connection

### Permission errors
- Ensure the Python script is readable
- On Unix, you may need: `chmod +x aave_mcp_server.py`
