# Aave V3 MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides tools for interacting with the [Aave V3](https://aave.com/) DeFi protocol. This server enables LLMs like Claude to query markets, analyze user positions, prepare transactions, and interact with Aave's lending/borrowing protocol.

## Features

### 🔧 Tools

The server provides 18+ tools organized into categories:

#### Market Tools
- `get_supported_chains` - List all supported blockchain networks
- `get_markets` - Fetch markets across multiple chains with TVL and APY data
- `get_market_details` - Get comprehensive data for a specific market

#### User Position Tools
- `get_user_positions` - Get all supply/borrow positions for a user
- `get_user_market_state` - Get health factor and liquidation risk
- `get_user_transaction_history` - View historical transactions

#### Reserve/Asset Tools
- `get_reserve_details` - Detailed info about specific assets (APY, caps, risk params)
- `get_apy_history` - Historical APY data for supply or borrow

#### Transaction Preparation Tools
- `prepare_supply_transaction` - Prepare a supply/deposit transaction
- `prepare_borrow_transaction` - Prepare a borrow transaction
- `prepare_repay_transaction` - Prepare a debt repayment transaction
- `prepare_withdraw_transaction` - Prepare a withdrawal transaction

#### Vault Tools
- `get_vaults` - List yield-generating vault strategies
- `get_vault_details` - Detailed vault information

#### GHO Stablecoin Tools
- `get_gho_balance` - Get sGHO (staked GHO) balance

### 📚 Resources

- `aave://chains` - List of supported networks
- `aave://markets/{chain_id}` - Markets for a specific chain
- `aave://common-addresses` - Quick reference for market addresses

### 💡 Prompts

Pre-built prompts for common workflows:
- `analyze_user_positions` - Comprehensive position analysis
- `find_best_yield` - Compare yields across chains
- `prepare_defi_strategy` - Create yield/leverage/hedge strategies

## Installation

### Using pip

```bash
pip install -e .
```

### Using uv (recommended)

```bash
uv pip install -e .
```

### Dependencies

- Python 3.10+
- `mcp[cli]>=1.4.0`
- `httpx>=0.27.0`

## Usage

### Running the Server

```bash
# Using Python directly
python aave_mcp_server.py

# Or using the installed script
aave-mcp-server
```

### Configuring with Claude Desktop

Add to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "aave-v3": {
      "command": "python",
      "args": ["/path/to/aave-mcp-server/aave_mcp_server.py"]
    }
  }
}
```

Or if using uv:

```json
{
  "mcpServers": {
    "aave-v3": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/aave-mcp-server",
        "run",
        "aave_mcp_server.py"
      ]
    }
  }
}
```

### Testing with MCP Inspector

```bash
# Start the server
python aave_mcp_server.py

# In another terminal, use MCP Inspector
mcp dev aave_mcp_server.py
```

## Example Interactions

### Get Markets Overview

```
User: What are the current Aave markets on Ethereum?

Claude: [Uses get_markets tool with chain_id=1]
```

### Check User Position

```
User: Can you analyze the health of wallet 0x742d35...?

Claude: [Uses get_user_positions and get_user_market_state tools]
```

### Prepare a Transaction

```
User: I want to supply 100 USDC to Aave on Ethereum

Claude: [Uses prepare_supply_transaction tool with the parameters]
```

### Find Best Yield

```
User: Where can I get the best yield for my USDC?

Claude: [Uses find_best_yield prompt, then get_markets to compare]
```

## Supported Chains

| Chain | Chain ID | Market Address |
|-------|----------|----------------|
| Ethereum | 1 | 0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2 |
| Polygon | 137 | 0x794a61358d6845594f94dc1db02a252b5b4814ad |
| Arbitrum | 42161 | 0x794a61358d6845594f94dc1db02a252b5b4814ad |
| Optimism | 10 | 0x794a61358d6845594f94dc1db02a252b5b4814ad |
| Avalanche | 43114 | 0x794a61358d6845594f94dc1db02a252b5b4814ad |
| Base | 8453 | 0xa238dd80c259a72e81d7e4664a9801593f98d1c5 |

## Transaction Execution

**Important**: This MCP server prepares transactions but does not execute them. The transaction data returned must be:

1. Signed by the user's wallet
2. Broadcast to the blockchain

For transaction execution, you'll need:
- A wallet provider (MetaMask, WalletConnect, etc.)
- Sufficient native tokens for gas
- The user's explicit approval

## API Reference

This server communicates with Aave's official GraphQL API:
- Production: `https://api.v3.aave.com/graphql`

Based on the official [Aave SDK](https://github.com/aave/aave-sdk).

## Security Considerations

- **No Private Keys**: This server never handles private keys or signs transactions
- **Read Operations**: Most tools perform read-only queries
- **Transaction Prep**: Transaction tools only prepare unsigned transaction data
- **Rate Limits**: The Aave API may have rate limits; implement caching for production use

## Development

### Running Tests

```bash
pytest tests/
```

### Linting

```bash
ruff check .
black --check .
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Acknowledgments

- [Aave Protocol](https://aave.com/) for the DeFi infrastructure
- [Anthropic](https://anthropic.com/) for the Model Context Protocol
- [Aave SDK](https://github.com/aave/aave-sdk) for the API structure
