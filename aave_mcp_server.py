#!/usr/bin/env python3
"""
Aave V3 MCP Server

A Model Context Protocol (MCP) server that provides tools for interacting with
the Aave V3 DeFi protocol. This server allows LLMs to query markets, user positions,
reserves, vaults, and generate transaction data for DeFi operations.

Based on the official Aave SDK (https://github.com/aave/aave-sdk)
"""

import json
import logging
from typing import Any, Optional
from decimal import Decimal

import httpx
from mcp.server.fastmcp import FastMCP

# Configure logging to stderr (required for MCP stdio transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("aave-mcp-server")

# Initialize FastMCP server
mcp = FastMCP("aave-v3")

# Aave API configuration
AAVE_API_URL = "https://api.v3.aave.com/graphql"

# Common chain IDs
CHAIN_IDS = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "avalanche": 43114,
    "base": 8453,
    "gnosis": 100,
    "bnb": 56,
    "scroll": 534352,
    "metis": 1088,
    "zksync": 324,
}

# Known market addresses per chain
KNOWN_MARKETS = {
    1: "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",  # Ethereum mainnet
    137: "0x794a61358d6845594f94dc1db02a252b5b4814ad",  # Polygon
    42161: "0x794a61358d6845594f94dc1db02a252b5b4814ad",  # Arbitrum
    10: "0x794a61358d6845594f94dc1db02a252b5b4814ad",  # Optimism
    43114: "0x794a61358d6845594f94dc1db02a252b5b4814ad",  # Avalanche
    8453: "0xa238dd80c259a72e81d7e4664a9801593f98d1c5",  # Base
}


async def execute_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against the Aave API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            AAVE_API_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Aave-MCP-Server/1.0",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        result = response.json()
        
        if "errors" in result:
            raise Exception(f"GraphQL errors: {json.dumps(result['errors'])}")
        
        return result.get("data", {})


def format_token_amount(amount: dict[str, Any]) -> str:
    """Format a token amount for display."""
    if not amount:
        return "N/A"
    
    value = amount.get("amount", {}).get("value", "0")
    symbol = amount.get("amount", {}).get("currency", {}).get("symbol", "")
    usd = amount.get("usd", "0")
    
    return f"{value} {symbol} (${usd} USD)"


def format_percent(value: str | None) -> str:
    """Format a percentage value."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(value)


# ============================================================================
# MARKET TOOLS
# ============================================================================

@mcp.tool()
async def get_supported_chains() -> dict[str, Any]:
    """
    Get a list of all blockchain networks supported by Aave V3.
    
    Returns information about each chain including name, chain ID, 
    and whether it's a testnet.
    """
    query = """
    query Chains {
        chains(filter: MAINNET_ONLY) {
            name
            chainId
            icon
            explorerUrl
            isTestnet
            nativeWrappedToken
        }
    }
    """
    
    try:
        data = await execute_graphql(query)
        chains = data.get("chains", [])
        
        return {
            "success": True,
            "chains": chains,
            "count": len(chains),
            "common_chain_ids": CHAIN_IDS
        }
    except Exception as e:
        logger.error(f"Error fetching chains: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_markets(chain_ids: list[int] | None = None) -> dict[str, Any]:
    """
    Fetch all Aave V3 markets for specified chains.

    Args:
        chain_ids: List of chain IDs to query. If not provided, queries major chains.
                   Common values: 1 (Ethereum), 137 (Polygon), 42161 (Arbitrum),
                   10 (Optimism), 8453 (Base)

    Returns market information including TVL, available assets, and APY rates.
    """
    if chain_ids is None:
        chain_ids = [1, 137, 42161, 10, 8453]  # Default to major chains

    query = """
    query Markets($request: MarketsRequest!) {
        markets(request: $request) {
            address
            name
            chain {
                name
                chainId
            }
            totalMarketSize
            totalAvailableLiquidity
            reserves {
                underlyingToken {
                    address
                    symbol
                    name
                }
                supplyInfo {
                    apy {
                        value
                        formatted
                    }
                    total {
                        value
                    }
                }
                borrowInfo {
                    apy {
                        value
                        formatted
                    }
                    total {
                        amount {
                            value
                        }
                        usd
                    }
                }
            }
        }
    }
    """

    variables = {
        "request": {"chainIds": chain_ids}
    }

    try:
        data = await execute_graphql(query, variables)
        markets = data.get("markets", [])

        # Format the response
        formatted_markets = []
        for market in markets:
            reserves = market.get("reserves", [])
            # Filter reserves with supply/borrow info
            supply_reserves = [r for r in reserves if r.get("supplyInfo")]
            borrow_reserves = [r for r in reserves if r.get("borrowInfo")]

            formatted_market = {
                "address": market["address"],
                "name": market["name"],
                "chain": market["chain"]["name"],
                "chain_id": market["chain"]["chainId"],
                "total_market_size_usd": market["totalMarketSize"],
                "total_available_liquidity_usd": market["totalAvailableLiquidity"],
                "supply_assets_count": len(supply_reserves),
                "borrow_assets_count": len(borrow_reserves),
                "top_supply_assets": [
                    {
                        "symbol": r["underlyingToken"]["symbol"],
                        "apy": r["supplyInfo"]["apy"]["formatted"] + "%" if r.get("supplyInfo") else "N/A",
                        "total_supply": r["supplyInfo"]["total"]["value"] if r.get("supplyInfo") else "N/A"
                    }
                    for r in supply_reserves[:5]
                ],
                "top_borrow_assets": [
                    {
                        "symbol": r["underlyingToken"]["symbol"],
                        "apy": r["borrowInfo"]["apy"]["formatted"] + "%" if r.get("borrowInfo") else "N/A",
                        "total_borrow_usd": r["borrowInfo"]["total"]["usd"] if r.get("borrowInfo") else "N/A"
                    }
                    for r in borrow_reserves[:5]
                ]
            }
            formatted_markets.append(formatted_market)

        return {
            "success": True,
            "markets": formatted_markets,
            "count": len(formatted_markets)
        }
    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_market_details(
    market_address: str,
    chain_id: int,
    user_address: str | None = None
) -> dict[str, Any]:
    """
    Get detailed information about a specific Aave market.

    Args:
        market_address: The pool address for the market (e.g., '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2')
        chain_id: The blockchain chain ID (e.g., 1 for Ethereum mainnet)
        user_address: Optional user wallet address to include user-specific data

    Returns comprehensive market data including all reserves, APYs, and liquidity info.
    """
    query = """
    query Market($request: MarketRequest!) {
        market(request: $request) {
            address
            name
            chain {
                name
                chainId
                explorerUrl
            }
            totalMarketSize
            totalAvailableLiquidity
            eModeCategories {
                id
                label
                maxLTV {
                    value
                    formatted
                }
                liquidationThreshold {
                    value
                    formatted
                }
                liquidationPenalty {
                    value
                    formatted
                }
            }
            reserves {
                underlyingToken {
                    address
                    symbol
                    name
                    decimals
                }
                isFrozen
                isPaused
                supplyInfo {
                    apy {
                        value
                        formatted
                    }
                    total {
                        value
                    }
                    supplyCap {
                        amount {
                            value
                        }
                        usd
                    }
                    supplyCapReached
                    canBeCollateral
                    maxLTV {
                        value
                        formatted
                    }
                    liquidationThreshold {
                        value
                        formatted
                    }
                    liquidationBonus {
                        value
                        formatted
                    }
                }
                borrowInfo {
                    apy {
                        value
                        formatted
                    }
                    total {
                        amount {
                            value
                        }
                        usd
                    }
                    borrowCap {
                        amount {
                            value
                        }
                        usd
                    }
                    borrowCapReached
                    borrowingState
                    availableLiquidity {
                        amount {
                            value
                        }
                        usd
                    }
                }
            }
        }
    }
    """

    request = {
        "address": market_address,
        "chainId": chain_id
    }
    if user_address:
        request["user"] = user_address

    variables = {
        "request": request
    }

    try:
        data = await execute_graphql(query, variables)
        market = data.get("market")

        if not market:
            return {"success": False, "error": "Market not found"}

        reserves = market.get("reserves", [])

        return {
            "success": True,
            "market": {
                "address": market["address"],
                "name": market["name"],
                "chain": market["chain"],
                "total_market_size_usd": market["totalMarketSize"],
                "total_available_liquidity_usd": market["totalAvailableLiquidity"],
                "emode_categories": [
                    {
                        "id": e["id"],
                        "label": e["label"],
                        "max_ltv": e["maxLTV"]["formatted"] + "%",
                        "liquidation_threshold": e["liquidationThreshold"]["formatted"] + "%",
                        "liquidation_penalty": e["liquidationPenalty"]["formatted"] + "%"
                    }
                    for e in market.get("eModeCategories", [])
                ],
                "reserves": [
                    {
                        "token": r["underlyingToken"],
                        "is_frozen": r["isFrozen"],
                        "is_paused": r["isPaused"],
                        "supply_info": {
                            "apy": r["supplyInfo"]["apy"]["formatted"] + "%",
                            "total_supply": r["supplyInfo"]["total"]["value"],
                            "supply_cap": r["supplyInfo"]["supplyCap"],
                            "supply_cap_reached": r["supplyInfo"]["supplyCapReached"],
                            "can_be_collateral": r["supplyInfo"]["canBeCollateral"],
                            "max_ltv": r["supplyInfo"]["maxLTV"]["formatted"] + "%",
                            "liquidation_threshold": r["supplyInfo"]["liquidationThreshold"]["formatted"] + "%",
                            "liquidation_bonus": r["supplyInfo"]["liquidationBonus"]["formatted"] + "%"
                        } if r.get("supplyInfo") else None,
                        "borrow_info": {
                            "apy": r["borrowInfo"]["apy"]["formatted"] + "%",
                            "total_borrow": r["borrowInfo"]["total"],
                            "borrow_cap": r["borrowInfo"]["borrowCap"],
                            "borrow_cap_reached": r["borrowInfo"]["borrowCapReached"],
                            "borrowing_state": r["borrowInfo"]["borrowingState"],
                            "available_liquidity": r["borrowInfo"]["availableLiquidity"]
                        } if r.get("borrowInfo") else None
                    }
                    for r in reserves
                ]
            }
        }
    except Exception as e:
        logger.error(f"Error fetching market details: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# USER POSITION TOOLS
# ============================================================================

@mcp.tool()
async def get_user_positions(
    user_address: str,
    chain_ids: list[int] | None = None
) -> dict[str, Any]:
    """
    Get all Aave positions for a user across specified chains.

    Args:
        user_address: The user's wallet address (e.g., '0x742d35cc...')
        chain_ids: List of chain IDs to query. Defaults to major chains.

    Returns the user's supply positions, borrow positions, and overall health factor.
    """
    if chain_ids is None:
        chain_ids = [1, 137, 42161, 10, 8453]

    # First get markets to know which ones to query
    markets_query = """
    query Markets($request: MarketsRequest!) {
        markets(request: $request) {
            address
            chain {
                chainId
            }
        }
    }
    """

    try:
        markets_data = await execute_graphql(markets_query, {"request": {"chainIds": chain_ids}})
        markets = markets_data.get("markets", [])

        # Build market list for user queries
        market_list = [
            {"address": m["address"], "chainId": m["chain"]["chainId"]}
            for m in markets
        ]

        if not market_list:
            return {"success": True, "supplies": [], "borrows": [], "message": "No markets found on specified chains"}

        # Query user supplies
        supplies_query = """
        query UserSupplies($request: UserSuppliesRequest!) {
            userSupplies(request: $request) {
                market {
                    address
                    name
                    chain {
                        name
                        chainId
                    }
                }
                currency {
                    address
                    symbol
                    name
                }
                balance {
                    amount {
                        value
                    }
                    usd
                }
                apy {
                    value
                    formatted
                }
                isCollateral
                canBeCollateral
            }
        }
        """

        supplies_data = await execute_graphql(supplies_query, {
            "request": {
                "markets": market_list,
                "user": user_address,
                "collateralsOnly": False,
                "orderBy": {"balance": "DESC"}
            }
        })

        # Query user borrows
        borrows_query = """
        query UserBorrows($request: UserBorrowsRequest!) {
            userBorrows(request: $request) {
                market {
                    address
                    name
                    chain {
                        name
                        chainId
                    }
                }
                currency {
                    address
                    symbol
                    name
                }
                debt {
                    amount {
                        value
                    }
                    usd
                }
                apy {
                    value
                    formatted
                }
            }
        }
        """

        borrows_data = await execute_graphql(borrows_query, {
            "request": {
                "markets": market_list,
                "user": user_address,
                "orderBy": {"debt": "DESC"}
            }
        })

        supplies = supplies_data.get("userSupplies", [])
        borrows = borrows_data.get("userBorrows", [])

        # Calculate totals
        total_supply_usd = sum(
            float(s.get("balance", {}).get("usd", 0) or 0)
            for s in supplies
        )
        total_borrow_usd = sum(
            float(b.get("debt", {}).get("usd", 0) or 0)
            for b in borrows
        )

        return {
            "success": True,
            "user_address": user_address,
            "summary": {
                "total_supply_usd": f"${total_supply_usd:,.2f}",
                "total_borrow_usd": f"${total_borrow_usd:,.2f}",
                "net_worth_usd": f"${total_supply_usd - total_borrow_usd:,.2f}",
                "supply_positions_count": len(supplies),
                "borrow_positions_count": len(borrows)
            },
            "supplies": [
                {
                    "market": s["market"]["name"],
                    "chain": s["market"]["chain"]["name"],
                    "token": s["currency"]["symbol"],
                    "balance": s["balance"]["amount"]["value"],
                    "balance_usd": s["balance"]["usd"],
                    "apy": s["apy"]["formatted"] + "%",
                    "is_collateral": s["isCollateral"],
                    "can_be_collateral": s["canBeCollateral"]
                }
                for s in supplies
            ],
            "borrows": [
                {
                    "market": b["market"]["name"],
                    "chain": b["market"]["chain"]["name"],
                    "token": b["currency"]["symbol"],
                    "debt": b["debt"]["amount"]["value"],
                    "debt_usd": b["debt"]["usd"],
                    "apy": b["apy"]["formatted"] + "%"
                }
                for b in borrows
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching user positions: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_user_market_state(
    market_address: str,
    chain_id: int,
    user_address: str
) -> dict[str, Any]:
    """
    Get detailed user state for a specific Aave market including health factor.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        user_address: The user's wallet address
    
    Returns detailed position data including health factor, liquidation risk, and borrowing power.
    """
    query = """
    query UserMarketState($request: UserMarketStateRequest!) {
        userMarketState(request: $request) {
            healthFactor
            netWorth {
                amount {
                    value
                }
                usd
            }
            totalCollateral {
                amount {
                    value
                }
                usd
            }
            totalDebt {
                amount {
                    value
                }
                usd
            }
            availableToBorrow {
                amount {
                    value
                }
                usd
            }
            currentLiquidationThreshold
            currentLtv
            eMode {
                id
                label
            }
        }
    }
    """
    
    variables = {
        "request": {
            "market": market_address,
            "user": user_address,
            "chainId": chain_id
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        state = data.get("userMarketState")
        
        if not state:
            return {"success": False, "error": "User state not found"}
        
        health_factor = state.get("healthFactor")
        health_status = "Safe"
        if health_factor:
            hf = float(health_factor)
            if hf < 1.0:
                health_status = "LIQUIDATABLE"
            elif hf < 1.1:
                health_status = "CRITICAL"
            elif hf < 1.5:
                health_status = "At Risk"
        
        return {
            "success": True,
            "user_address": user_address,
            "market_address": market_address,
            "chain_id": chain_id,
            "health_factor": health_factor,
            "health_status": health_status,
            "net_worth_usd": state.get("netWorth", {}).get("usd"),
            "total_collateral_usd": state.get("totalCollateral", {}).get("usd"),
            "total_debt_usd": state.get("totalDebt", {}).get("usd"),
            "available_to_borrow_usd": state.get("availableToBorrow", {}).get("usd"),
            "current_ltv": format_percent(state.get("currentLtv")),
            "liquidation_threshold": format_percent(state.get("currentLiquidationThreshold")),
            "emode": state.get("eMode")
        }
    except Exception as e:
        logger.error(f"Error fetching user market state: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_user_transaction_history(
    market_address: str,
    chain_id: int,
    user_address: str,
    page_size: int = 20
) -> dict[str, Any]:
    """
    Get transaction history for a user on a specific Aave market.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        user_address: The user's wallet address
        page_size: Number of transactions to return (default: 20)
    
    Returns a list of historical transactions including supplies, borrows, repays, and withdrawals.
    """
    query = """
    query UserTransactionHistory($request: UserTransactionHistoryRequest!) {
        userTransactionHistory(request: $request) {
            items {
                __typename
                txHash
                timestamp
                ... on SupplyItem {
                    amount {
                        amount {
                            value
                            currency {
                                symbol
                            }
                        }
                        usd
                    }
                }
                ... on WithdrawItem {
                    amount {
                        amount {
                            value
                            currency {
                                symbol
                            }
                        }
                        usd
                    }
                }
                ... on BorrowItem {
                    amount {
                        amount {
                            value
                            currency {
                                symbol
                            }
                        }
                        usd
                    }
                }
                ... on RepayItem {
                    amount {
                        amount {
                            value
                            currency {
                                symbol
                            }
                        }
                        usd
                    }
                }
            }
            pageInfo {
                hasNextPage
            }
        }
    }
    """
    
    variables = {
        "request": {
            "market": market_address,
            "user": user_address,
            "chainId": chain_id,
            "pageSize": f"SIZE_{page_size}" if page_size in [10, 20, 50] else "SIZE_20"
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        history = data.get("userTransactionHistory", {})
        
        items = history.get("items", [])
        formatted_items = []
        
        for item in items:
            formatted_item = {
                "type": item.get("__typename", "Unknown").replace("Item", ""),
                "tx_hash": item.get("txHash"),
                "timestamp": item.get("timestamp"),
            }
            
            amount = item.get("amount", {})
            if amount:
                formatted_item["amount"] = amount.get("amount", {}).get("value")
                formatted_item["symbol"] = amount.get("amount", {}).get("currency", {}).get("symbol")
                formatted_item["usd"] = amount.get("usd")
            
            formatted_items.append(formatted_item)
        
        return {
            "success": True,
            "user_address": user_address,
            "transactions": formatted_items,
            "count": len(formatted_items),
            "has_more": history.get("pageInfo", {}).get("hasNextPage", False)
        }
    except Exception as e:
        logger.error(f"Error fetching transaction history: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# RESERVE/ASSET TOOLS
# ============================================================================

@mcp.tool()
async def get_reserve_details(
    market_address: str,
    token_address: str,
    chain_id: int
) -> dict[str, Any]:
    """
    Get detailed information about a specific reserve (asset) in an Aave market.
    
    Args:
        market_address: The pool address for the market
        token_address: The underlying token address
        chain_id: The blockchain chain ID
    
    Returns comprehensive reserve data including APYs, caps, and risk parameters.
    """
    query = """
    query Reserve($request: ReserveRequest!) {
        reserve(request: $request) {
            underlyingToken {
                address
                symbol
                name
                decimals
                imageUrl
            }
            aToken {
                address
                symbol
            }
            variableDebtToken {
                address
                symbol
            }
            supplyApy
            borrowApy
            totalSupply {
                amount {
                    value
                }
                usd
            }
            totalBorrow {
                amount {
                    value
                }
                usd
            }
            supplyCap {
                amount {
                    value
                }
                usd
            }
            borrowCap {
                amount {
                    value
                }
                usd
            }
            availableLiquidity {
                amount {
                    value
                }
                usd
            }
            utilizationRate
            ltv
            liquidationThreshold
            liquidationPenalty
            reserveFactor
            isActive
            isFrozen
            isPaused
            borrowingEnabled
            usageAsCollateralEnabled
            isFlashLoanEnabled
        }
    }
    """
    
    variables = {
        "request": {
            "market": market_address,
            "underlyingToken": token_address,
            "chainId": chain_id
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        reserve = data.get("reserve")
        
        if not reserve:
            return {"success": False, "error": "Reserve not found"}
        
        return {
            "success": True,
            "reserve": {
                "token": reserve["underlyingToken"],
                "atoken": reserve["aToken"],
                "debt_token": reserve["variableDebtToken"],
                "rates": {
                    "supply_apy": format_percent(reserve["supplyApy"]),
                    "borrow_apy": format_percent(reserve["borrowApy"]),
                    "utilization": format_percent(reserve["utilizationRate"])
                },
                "liquidity": {
                    "total_supply": reserve["totalSupply"],
                    "total_borrow": reserve["totalBorrow"],
                    "available": reserve["availableLiquidity"],
                    "supply_cap": reserve["supplyCap"],
                    "borrow_cap": reserve["borrowCap"]
                },
                "risk_parameters": {
                    "ltv": format_percent(reserve["ltv"]),
                    "liquidation_threshold": format_percent(reserve["liquidationThreshold"]),
                    "liquidation_penalty": format_percent(reserve["liquidationPenalty"]),
                    "reserve_factor": format_percent(reserve["reserveFactor"])
                },
                "status": {
                    "is_active": reserve["isActive"],
                    "is_frozen": reserve["isFrozen"],
                    "is_paused": reserve["isPaused"],
                    "borrowing_enabled": reserve["borrowingEnabled"],
                    "collateral_enabled": reserve["usageAsCollateralEnabled"],
                    "flash_loan_enabled": reserve["isFlashLoanEnabled"]
                }
            }
        }
    except Exception as e:
        logger.error(f"Error fetching reserve details: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_apy_history(
    market_address: str,
    token_address: str,
    chain_id: int,
    apy_type: str = "supply",
    time_window: str = "ONE_MONTH"
) -> dict[str, Any]:
    """
    Get historical APY data for a reserve.
    
    Args:
        market_address: The pool address for the market
        token_address: The underlying token address
        chain_id: The blockchain chain ID
        apy_type: Either 'supply' or 'borrow'
        time_window: Time period - ONE_WEEK, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR
    
    Returns historical APY samples over the specified time window.
    """
    if apy_type == "supply":
        query = """
        query SupplyAPYHistory($request: SupplyAPYHistoryRequest!) {
            supplyAPYHistory(request: $request) {
                date
                avgRate
            }
        }
        """
        query_name = "supplyAPYHistory"
    else:
        query = """
        query BorrowAPYHistory($request: BorrowAPYHistoryRequest!) {
            borrowAPYHistory(request: $request) {
                date
                avgRate
            }
        }
        """
        query_name = "borrowAPYHistory"
    
    variables = {
        "request": {
            "market": market_address,
            "underlyingToken": token_address,
            "chainId": chain_id,
            "window": time_window
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        history = data.get(query_name, [])
        
        if not history:
            return {"success": True, "history": [], "message": "No historical data available"}
        
        formatted_history = [
            {
                "date": h["date"],
                "apy": format_percent(h["avgRate"])
            }
            for h in history
        ]
        
        return {
            "success": True,
            "apy_type": apy_type,
            "time_window": time_window,
            "history": formatted_history,
            "data_points": len(formatted_history)
        }
    except Exception as e:
        logger.error(f"Error fetching APY history: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# TRANSACTION PREPARATION TOOLS
# ============================================================================

@mcp.tool()
async def prepare_supply_transaction(
    market_address: str,
    chain_id: int,
    token_address: str,
    amount: str,
    sender_address: str
) -> dict[str, Any]:
    """
    Prepare a supply transaction for an Aave market.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        token_address: The token address to supply
        amount: Amount to supply in token units (e.g., '100' for 100 USDC)
        sender_address: The wallet address that will send the transaction
    
    Returns the transaction data needed to execute the supply, including any required approvals.
    
    Note: This returns transaction data that must be signed and sent by a wallet.
    """
    query = """
    query Supply($request: SupplyRequest!) {
        supply(request: $request) {
            __typename
            ... on TransactionRequest {
                to
                data
                value
                chainId
            }
            ... on ApprovalRequired {
                reason
                requiredAmount
                currentAllowance
                approval {
                    to
                    data
                    value
                    chainId
                }
                originalTransaction {
                    to
                    data
                    value
                    chainId
                }
            }
            ... on InsufficientBalanceError {
                required {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
                available {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
            }
        }
    }
    """
    
    variables = {
        "request": {
            "market": market_address,
            "chainId": chain_id,
            "amount": {
                "erc20": {
                    "currency": token_address,
                    "value": amount
                }
            },
            "sender": sender_address
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        result = data.get("supply")
        
        if not result:
            return {"success": False, "error": "Failed to prepare supply transaction"}
        
        result_type = result.get("__typename")
        
        if result_type == "TransactionRequest":
            return {
                "success": True,
                "type": "ready",
                "message": "Transaction ready to sign",
                "transaction": {
                    "to": result["to"],
                    "data": result["data"],
                    "value": result["value"],
                    "chainId": result["chainId"]
                }
            }
        elif result_type == "ApprovalRequired":
            return {
                "success": True,
                "type": "approval_required",
                "message": f"Token approval required: {result['reason']}",
                "required_amount": result["requiredAmount"],
                "current_allowance": result["currentAllowance"],
                "approval_transaction": {
                    "to": result["approval"]["to"],
                    "data": result["approval"]["data"],
                    "value": result["approval"]["value"],
                    "chainId": result["approval"]["chainId"]
                },
                "supply_transaction": {
                    "to": result["originalTransaction"]["to"],
                    "data": result["originalTransaction"]["data"],
                    "value": result["originalTransaction"]["value"],
                    "chainId": result["originalTransaction"]["chainId"]
                }
            }
        elif result_type == "InsufficientBalanceError":
            return {
                "success": False,
                "type": "insufficient_balance",
                "message": "Insufficient token balance",
                "required": format_token_amount(result["required"]),
                "available": format_token_amount(result["available"])
            }
        else:
            return {"success": False, "error": f"Unknown response type: {result_type}"}
            
    except Exception as e:
        logger.error(f"Error preparing supply transaction: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def prepare_borrow_transaction(
    market_address: str,
    chain_id: int,
    token_address: str,
    amount: str,
    sender_address: str
) -> dict[str, Any]:
    """
    Prepare a borrow transaction for an Aave market.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        token_address: The token address to borrow
        amount: Amount to borrow in token units (e.g., '100' for 100 USDC)
        sender_address: The wallet address that will send the transaction
    
    Returns the transaction data needed to execute the borrow.
    Requires the user to have sufficient collateral deposited.
    
    Note: This returns transaction data that must be signed and sent by a wallet.
    """
    query = """
    query Borrow($request: BorrowRequest!) {
        borrow(request: $request) {
            __typename
            ... on TransactionRequest {
                to
                data
                value
                chainId
            }
            ... on ApprovalRequired {
                reason
                requiredAmount
                currentAllowance
                approval {
                    to
                    data
                    value
                    chainId
                }
                originalTransaction {
                    to
                    data
                    value
                    chainId
                }
            }
            ... on InsufficientBalanceError {
                required {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
                available {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
            }
        }
    }
    """
    
    variables = {
        "request": {
            "market": market_address,
            "chainId": chain_id,
            "amount": {
                "erc20": {
                    "currency": token_address,
                    "value": amount
                }
            },
            "sender": sender_address
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        result = data.get("borrow")
        
        if not result:
            return {"success": False, "error": "Failed to prepare borrow transaction"}
        
        result_type = result.get("__typename")
        
        if result_type == "TransactionRequest":
            return {
                "success": True,
                "type": "ready",
                "message": "Borrow transaction ready to sign",
                "transaction": {
                    "to": result["to"],
                    "data": result["data"],
                    "value": result["value"],
                    "chainId": result["chainId"]
                }
            }
        elif result_type == "ApprovalRequired":
            return {
                "success": True,
                "type": "approval_required",
                "message": f"Approval required: {result['reason']}",
                "approval_transaction": {
                    "to": result["approval"]["to"],
                    "data": result["approval"]["data"],
                    "value": result["approval"]["value"],
                    "chainId": result["approval"]["chainId"]
                },
                "borrow_transaction": {
                    "to": result["originalTransaction"]["to"],
                    "data": result["originalTransaction"]["data"],
                    "value": result["originalTransaction"]["value"],
                    "chainId": result["originalTransaction"]["chainId"]
                }
            }
        elif result_type == "InsufficientBalanceError":
            return {
                "success": False,
                "type": "insufficient_collateral",
                "message": "Insufficient collateral or borrowing power",
                "required": format_token_amount(result.get("required")),
                "available": format_token_amount(result.get("available"))
            }
        else:
            return {"success": False, "error": f"Unknown response type: {result_type}"}
            
    except Exception as e:
        logger.error(f"Error preparing borrow transaction: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def prepare_repay_transaction(
    market_address: str,
    chain_id: int,
    token_address: str,
    amount: str,
    sender_address: str,
    repay_max: bool = False
) -> dict[str, Any]:
    """
    Prepare a repay transaction for an Aave market.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        token_address: The token address to repay
        amount: Amount to repay in token units, or ignored if repay_max is True
        sender_address: The wallet address that will send the transaction
        repay_max: If True, repays the entire debt position
    
    Returns the transaction data needed to execute the repay.
    
    Note: This returns transaction data that must be signed and sent by a wallet.
    """
    query = """
    query Repay($request: RepayRequest!) {
        repay(request: $request) {
            __typename
            ... on TransactionRequest {
                to
                data
                value
                chainId
            }
            ... on ApprovalRequired {
                reason
                requiredAmount
                currentAllowance
                approval {
                    to
                    data
                    value
                    chainId
                }
                originalTransaction {
                    to
                    data
                    value
                    chainId
                }
            }
            ... on InsufficientBalanceError {
                required {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
                available {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
            }
        }
    }
    """
    
    # Build amount input
    if repay_max:
        amount_input = {
            "erc20": {
                "currency": token_address,
                "value": {"max": True}
            }
        }
    else:
        amount_input = {
            "erc20": {
                "currency": token_address,
                "value": {"exact": amount}
            }
        }
    
    variables = {
        "request": {
            "market": market_address,
            "chainId": chain_id,
            "amount": amount_input,
            "sender": sender_address
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        result = data.get("repay")
        
        if not result:
            return {"success": False, "error": "Failed to prepare repay transaction"}
        
        result_type = result.get("__typename")
        
        if result_type == "TransactionRequest":
            return {
                "success": True,
                "type": "ready",
                "message": "Repay transaction ready to sign",
                "transaction": {
                    "to": result["to"],
                    "data": result["data"],
                    "value": result["value"],
                    "chainId": result["chainId"]
                }
            }
        elif result_type == "ApprovalRequired":
            return {
                "success": True,
                "type": "approval_required",
                "message": f"Token approval required: {result['reason']}",
                "approval_transaction": {
                    "to": result["approval"]["to"],
                    "data": result["approval"]["data"],
                    "value": result["approval"]["value"],
                    "chainId": result["approval"]["chainId"]
                },
                "repay_transaction": {
                    "to": result["originalTransaction"]["to"],
                    "data": result["originalTransaction"]["data"],
                    "value": result["originalTransaction"]["value"],
                    "chainId": result["originalTransaction"]["chainId"]
                }
            }
        elif result_type == "InsufficientBalanceError":
            return {
                "success": False,
                "type": "insufficient_balance",
                "message": "Insufficient token balance to repay",
                "required": format_token_amount(result.get("required")),
                "available": format_token_amount(result.get("available"))
            }
        else:
            return {"success": False, "error": f"Unknown response type: {result_type}"}
            
    except Exception as e:
        logger.error(f"Error preparing repay transaction: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def prepare_withdraw_transaction(
    market_address: str,
    chain_id: int,
    token_address: str,
    amount: str,
    sender_address: str,
    withdraw_max: bool = False
) -> dict[str, Any]:
    """
    Prepare a withdraw transaction for an Aave market.
    
    Args:
        market_address: The pool address for the market
        chain_id: The blockchain chain ID
        token_address: The token address to withdraw
        amount: Amount to withdraw in token units, or ignored if withdraw_max is True
        sender_address: The wallet address that will send the transaction
        withdraw_max: If True, withdraws the entire supply position
    
    Returns the transaction data needed to execute the withdrawal.
    
    Note: This returns transaction data that must be signed and sent by a wallet.
    """
    query = """
    query Withdraw($request: WithdrawRequest!) {
        withdraw(request: $request) {
            __typename
            ... on TransactionRequest {
                to
                data
                value
                chainId
            }
            ... on ApprovalRequired {
                reason
                approval {
                    to
                    data
                    value
                    chainId
                }
                originalTransaction {
                    to
                    data
                    value
                    chainId
                }
            }
            ... on InsufficientBalanceError {
                required {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
                available {
                    amount {
                        value
                        currency {
                            symbol
                        }
                    }
                    usd
                }
            }
        }
    }
    """
    
    # Build amount input
    if withdraw_max:
        amount_input = {
            "erc20": {
                "currency": token_address,
                "value": {"max": True}
            }
        }
    else:
        amount_input = {
            "erc20": {
                "currency": token_address,
                "value": {"exact": amount}
            }
        }
    
    variables = {
        "request": {
            "market": market_address,
            "chainId": chain_id,
            "amount": amount_input,
            "sender": sender_address
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        result = data.get("withdraw")
        
        if not result:
            return {"success": False, "error": "Failed to prepare withdraw transaction"}
        
        result_type = result.get("__typename")
        
        if result_type == "TransactionRequest":
            return {
                "success": True,
                "type": "ready",
                "message": "Withdraw transaction ready to sign",
                "transaction": {
                    "to": result["to"],
                    "data": result["data"],
                    "value": result["value"],
                    "chainId": result["chainId"]
                }
            }
        elif result_type == "ApprovalRequired":
            return {
                "success": True,
                "type": "approval_required",
                "message": f"Approval required: {result['reason']}",
                "approval_transaction": {
                    "to": result["approval"]["to"],
                    "data": result["approval"]["data"],
                    "value": result["approval"]["value"],
                    "chainId": result["approval"]["chainId"]
                },
                "withdraw_transaction": {
                    "to": result["originalTransaction"]["to"],
                    "data": result["originalTransaction"]["data"],
                    "value": result["originalTransaction"]["value"],
                    "chainId": result["originalTransaction"]["chainId"]
                }
            }
        elif result_type == "InsufficientBalanceError":
            return {
                "success": False,
                "type": "insufficient_balance",
                "message": "Insufficient supply balance to withdraw",
                "required": format_token_amount(result.get("required")),
                "available": format_token_amount(result.get("available"))
            }
        else:
            return {"success": False, "error": f"Unknown response type: {result_type}"}
            
    except Exception as e:
        logger.error(f"Error preparing withdraw transaction: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# VAULT TOOLS
# ============================================================================

@mcp.tool()
async def get_vaults(
    vault_addresses: list[str] | None = None,
    owner_addresses: list[str] | None = None,
    page_size: int = 10
) -> dict[str, Any]:
    """
    Get a list of Aave vaults (yield-generating strategies).

    Args:
        vault_addresses: List of specific vault addresses to query.
        owner_addresses: List of owner addresses to filter vaults by.
        page_size: Number of vaults to return (10 or 50, default: 10)

    Note: You must provide either vault_addresses or owner_addresses.

    Returns available vaults with their APR, balance, and underlying assets.
    """
    query = """
    query Vaults($request: VaultsRequest!) {
        vaults(request: $request) {
            items {
                address
                chainId
                shareName
                shareSymbol
                owner
                vaultApr {
                    value
                    formatted
                }
                fee {
                    value
                    formatted
                }
                balance {
                    amount {
                        value
                    }
                    usd
                }
                usedReserve {
                    underlyingToken {
                        address
                        symbol
                        name
                    }
                }
            }
            pageInfo {
                prev
                next
            }
        }
    }
    """

    # Build criteria - exactly one of vaults or ownedBy is required
    if vault_addresses:
        criteria = {"vaults": vault_addresses}
    elif owner_addresses:
        criteria = {"ownedBy": owner_addresses}
    else:
        return {
            "success": False,
            "error": "You must provide either vault_addresses or owner_addresses to query vaults"
        }

    variables = {
        "request": {
            "criteria": criteria,
            "pageSize": "FIFTY" if page_size >= 50 else "TEN"
        }
    }

    try:
        data = await execute_graphql(query, variables)
        result = data.get("vaults", {})

        vaults = result.get("items", [])
        formatted_vaults = [
            {
                "address": v["address"],
                "chain_id": v["chainId"],
                "share_name": v["shareName"],
                "share_symbol": v["shareSymbol"],
                "underlying_asset": v.get("usedReserve", {}).get("underlyingToken") if v.get("usedReserve") else None,
                "apr": v["vaultApr"]["formatted"] + "%" if v.get("vaultApr") else "N/A",
                "balance_usd": v.get("balance", {}).get("usd"),
                "fee": v["fee"]["formatted"] + "%" if v.get("fee") else "N/A",
                "owner": v.get("owner")
            }
            for v in vaults
        ]

        page_info = result.get("pageInfo", {})
        return {
            "success": True,
            "vaults": formatted_vaults,
            "count": len(formatted_vaults),
            "has_more": page_info.get("next") is not None
        }
    except Exception as e:
        logger.error(f"Error fetching vaults: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_vault_details(
    vault_address: str,
    chain_id: int,
    user_address: str | None = None
) -> dict[str, Any]:
    """
    Get detailed information about a specific Aave vault.

    Args:
        vault_address: The vault contract address
        chain_id: The blockchain chain ID
        user_address: Optional user address to include user-specific data

    Returns comprehensive vault data including APR, balance, fees, and user position if provided.
    """
    query = """
    query Vault($request: VaultRequest!) {
        vault(request: $request) {
            address
            chainId
            shareName
            shareSymbol
            owner
            vaultApr {
                value
                formatted
            }
            fee {
                value
                formatted
            }
            balance {
                amount {
                    value
                }
                usd
            }
            usedReserve {
                market {
                    address
                    name
                }
                underlyingToken {
                    address
                    symbol
                    name
                    decimals
                }
            }
            userShares {
                shares {
                    amount {
                        value
                    }
                    usd
                }
                balance {
                    amount {
                        value
                    }
                    usd
                }
            }
        }
    }
    """

    request = {
        "by": {"address": vault_address},
        "chainId": chain_id
    }
    if user_address:
        request["user"] = user_address

    variables = {"request": request}

    try:
        data = await execute_graphql(query, variables)
        vault = data.get("vault")

        if not vault:
            return {"success": False, "error": "Vault not found"}

        result = {
            "success": True,
            "vault": {
                "address": vault["address"],
                "chain_id": vault["chainId"],
                "share_name": vault["shareName"],
                "share_symbol": vault["shareSymbol"],
                "underlying_asset": vault.get("usedReserve", {}).get("underlyingToken") if vault.get("usedReserve") else None,
                "market": vault.get("usedReserve", {}).get("market") if vault.get("usedReserve") else None,
                "apr": vault["vaultApr"]["formatted"] + "%" if vault.get("vaultApr") else "N/A",
                "balance": vault.get("balance"),
                "fee": vault["fee"]["formatted"] + "%" if vault.get("fee") else "N/A",
                "owner": vault.get("owner")
            }
        }

        if vault.get("userShares"):
            result["user_position"] = {
                "shares": vault["userShares"]["shares"],
                "balance": vault["userShares"]["balance"]
            }

        return result
    except Exception as e:
        logger.error(f"Error fetching vault details: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# GHO STABLECOIN TOOLS
# ============================================================================

@mcp.tool()
async def get_gho_balance(user_address: str) -> dict[str, Any]:
    """
    Get the sGHO (staked GHO) balance for a user.
    
    Args:
        user_address: The user's wallet address
    
    Returns the user's sGHO balance and its USD value.
    GHO is Aave's native stablecoin.
    """
    query = """
    query SavingsGhoBalance($request: SavingsGhoBalanceRequest!) {
        savingsGhoBalance(request: $request) {
            amount {
                value
                currency {
                    symbol
                    name
                }
            }
            usd
        }
    }
    """
    
    variables = {
        "request": {
            "user": user_address
        }
    }
    
    try:
        data = await execute_graphql(query, variables)
        balance = data.get("savingsGhoBalance")
        
        if not balance:
            return {
                "success": True,
                "user_address": user_address,
                "balance": "0",
                "balance_usd": "0"
            }
        
        return {
            "success": True,
            "user_address": user_address,
            "token": balance["amount"]["currency"],
            "balance": balance["amount"]["value"],
            "balance_usd": balance["usd"]
        }
    except Exception as e:
        logger.error(f"Error fetching GHO balance: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# RESOURCES
# ============================================================================

@mcp.resource("aave://chains")
async def chains_resource() -> str:
    """
    List of all supported blockchain networks for Aave V3.
    """
    result = await get_supported_chains()
    return json.dumps(result, indent=2)


@mcp.resource("aave://markets/{chain_id}")
async def markets_resource(chain_id: int) -> str:
    """
    Aave V3 markets for a specific chain.
    """
    result = await get_markets([chain_id])
    return json.dumps(result, indent=2)


@mcp.resource("aave://common-addresses")
async def common_addresses_resource() -> str:
    """
    Common Aave V3 market addresses and chain IDs for quick reference.
    """
    return json.dumps({
        "chain_ids": CHAIN_IDS,
        "known_markets": KNOWN_MARKETS,
        "usage": "Use these addresses with the get_market_details tool"
    }, indent=2)


# ============================================================================
# PROMPTS
# ============================================================================

@mcp.prompt()
def analyze_user_positions(user_address: str) -> str:
    """
    Analyze a user's Aave positions across all chains.
    
    Args:
        user_address: The wallet address to analyze
    """
    return f"""Please analyze the Aave V3 positions for wallet address {user_address}.

1. First, use get_user_positions to fetch all supply and borrow positions across major chains.
2. For any chain where the user has positions, use get_user_market_state to get the health factor.
3. Provide a comprehensive summary including:
   - Total supplied value (USD)
   - Total borrowed value (USD)
   - Net worth
   - Health factor status and any liquidation risks
   - Recommendations for improving the position's health or yield

Be specific about which chains and markets the user is active in."""


@mcp.prompt()
def find_best_yield(asset_symbol: str, amount: str) -> str:
    """
    Find the best yield opportunities for a specific asset.
    
    Args:
        asset_symbol: The token symbol (e.g., 'USDC', 'ETH', 'WBTC')
        amount: The amount to deposit
    """
    return f"""Please help me find the best yield opportunities for {amount} {asset_symbol} on Aave V3.

1. Use get_markets to fetch all available markets across major chains (Ethereum, Polygon, Arbitrum, Optimism, Base).
2. For each market, identify the supply APY for {asset_symbol}.
3. Compare the yields and provide:
   - A ranked list of markets by supply APY
   - The current supply caps and utilization
   - Any relevant incentives or bonus rewards
   - Gas cost considerations for each chain
   - Your recommendation for where to deposit

Focus on safety and yield optimization."""


@mcp.prompt()
def prepare_defi_strategy(
    user_address: str,
    strategy_type: str = "yield"
) -> str:
    """
    Create a DeFi strategy using Aave.
    
    Args:
        user_address: The wallet address
        strategy_type: 'yield' for earning, 'leverage' for leveraged positions, 'hedge' for risk management
    """
    strategies = {
        "yield": """Focus on:
- Finding the highest yield opportunities for idle assets
- Considering risk-adjusted returns
- Evaluating gas costs vs expected returns""",
        "leverage": """Focus on:
- Current collateral and borrowing power
- Health factor management (keep above 1.5 for safety)
- Recursive supply/borrow strategies
- Liquidation risk assessment""",
        "hedge": """Focus on:
- Current positions and their risks
- Strategies to reduce liquidation risk
- Diversification across assets and chains
- Using E-Mode for correlated assets"""
    }
    
    strategy_guidance = strategies.get(strategy_type, strategies["yield"])
    
    return f"""Please create an Aave V3 {strategy_type} strategy for wallet {user_address}.

1. First, analyze current positions using get_user_positions.
2. Check health factors across active markets using get_user_market_state.
3. Research available opportunities using get_markets and get_reserve_details.

{strategy_guidance}

Provide:
- Current position analysis
- Recommended actions with specific steps
- Expected outcomes (APY, risk levels)
- Transaction preparation guidance using the prepare_* tools

Always prioritize capital safety and explain the risks involved."""


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
