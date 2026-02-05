"""
TradingView Data Retrieval Module
---------------------------------
Provides reusable functions for fetching stock data from TradingView
that can be used by agents and MCP servers.
"""

from typing import Optional, Dict, Any, Literal
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Singleton instance for TvDatafeed (optional credentials)
_tv_instance: Optional[TvDatafeed] = None


def get_tv_instance(
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> TvDatafeed:
    """
    Get or create a singleton TvDatafeed instance.
    
    Args:
        username: TradingView username (optional, for authenticated access)
        password: TradingView password (optional, for authenticated access)
    
    Returns:
        TvDatafeed instance
    """
    global _tv_instance
    if _tv_instance is None:
        if username and password:
            _tv_instance = TvDatafeed(username=username, password=password)
        else:
            _tv_instance = TvDatafeed()
    return _tv_instance


def get_stock_data(
    symbol: str,
    exchange: str,
    interval: Literal["daily", "weekly", "monthly", "1min", "5min", "15min", "30min", "1hour", "4hour"] = "daily",
    n_bars: int = 100,
    username: Optional[str] = None,
    password: Optional[str] = None,
    save_to_csv: bool = False,
    output_dir: Optional[str] = None,
    return_format: Literal["dataframe", "string", "summary"] = "dataframe",
) -> pd.DataFrame | str:
    """
    Retrieve historical stock data from TradingView.
    
    **IMPORTANT FOR AGENTS**: This function RETURNS data (not prints).
    The return value is what the LLM sees in the conversation.
    
    This function is designed to be used by agents and can be registered
    as a local function for agent tool calling.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL', 'TSLA', 'NIFTY')
        exchange: Exchange name (e.g., 'NASDAQ', 'NYSE', 'NSE')
        interval: Data interval. Options: 'daily', 'weekly', 'monthly', 
                 '1min', '5min', '15min', '30min', '1hour', '4hour'
        n_bars: Number of bars to retrieve (default: 100)
        username: TradingView username (optional)
        password: TradingView password (optional)
        save_to_csv: Whether to save data to CSV file (default: False)
        output_dir: Directory to save CSV (default: current directory)
        return_format: Format to return data:
            - 'dataframe': Return pandas DataFrame (default, for analysis)
            - 'string': Return formatted string (good for LLM readability)
            - 'summary': Return concise summary (quick insights)
    
    Returns:
        - If return_format='dataframe': pandas DataFrame
        - If return_format='string': Formatted string with summary and recent data
        - If return_format='summary': Concise one-line summary
        
    Raises:
        ValueError: If invalid parameters provided
        Exception: If data retrieval fails
    
    Example:
        >>> # For agents (LLM-readable format)
        >>> data = get_stock_data('AAPL', 'NASDAQ', return_format='string')
        >>> 
        >>> # For analysis (DataFrame)
        >>> df = get_stock_data('AAPL', 'NASDAQ', return_format='dataframe')
    """
    # Map interval strings to TvDatafeed Interval enum
    interval_map = {
        "daily": Interval.in_daily,
        "weekly": Interval.in_weekly,
        "monthly": Interval.in_monthly,
        "1min": Interval.in_1_minute,
        "5min": Interval.in_5_minute,
        "15min": Interval.in_15_minute,
        "30min": Interval.in_30_minute,
        "1hour": Interval.in_1_hour,
        "4hour": Interval.in_4_hour,
    }
    
    if interval not in interval_map:
        raise ValueError(
            f"Invalid interval: {interval}. "
            f"Valid options: {list(interval_map.keys())}"
        )
    
    if n_bars <= 0:
        raise ValueError(f"n_bars must be positive, got {n_bars}")
    
    try:
        # Get TvDatafeed instance
        tv = get_tv_instance(username=username, password=password)
        
        # Retrieve data
        logger.info(f"Fetching {n_bars} {interval} bars for {symbol} on {exchange}")
        data = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=interval_map[interval],
            n_bars=n_bars,
        )
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df.set_index('datetime', inplace=True)
            elif df.index.name == 'datetime' or df.index.dtype == 'object':
                df.index = pd.to_datetime(df.index)
        
        # Sort by date (oldest first)
        df.sort_index(inplace=True)
        
        # Log summary
        logger.info(
            f"Retrieved {len(df)} bars for {symbol} "
            f"from {df.index[0]} to {df.index[-1]}"
        )
        
        # Save to CSV if requested
        if save_to_csv:
            output_dir = output_dir or "."
            filename = f"{symbol}_{interval}_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = f"{output_dir}/{filename}"
            df.to_csv(filepath)
            logger.info(f"Data saved to {filepath}")
        
        # Return in requested format
        if return_format == "string":
            # Return as formatted string for LLM readability
            summary = (
                f"Stock Data for {symbol} on {exchange}\n"
                f"Interval: {interval}\n"
                f"Total bars: {len(df)}\n"
                f"Date range: {df.index[0]} to {df.index[-1]}\n"
                f"Current price: ${df['close'].iloc[-1]:.2f}\n"
                f"Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}\n"
                f"Average volume: {df['volume'].mean():,.0f}\n\n"
                f"Recent data (last 10 bars):\n"
                f"{df.tail(10).to_string()}\n\n"
                f"Full data available in DataFrame format."
            )
            return summary
        elif return_format == "summary":
            # Return concise summary for quick insights
            return (
                f"{symbol} ({exchange}): "
                f"Current: ${df['close'].iloc[-1]:.2f}, "
                f"Range: ${df['low'].min():.2f}-${df['high'].max():.2f}, "
                f"Volume: {df['volume'].mean():,.0f} avg, "
                f"Bars: {len(df)}"
            )
        else:
            # Return DataFrame (default)
            return df
        
    except Exception as e:
        logger.error(f"Failed to retrieve data for {symbol} on {exchange}: {str(e)}")
        raise


def get_stock_data_dict(
    symbol: str,
    exchange: str,
    interval: str = "daily",
    n_bars: int = 100,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve stock data and return as a dictionary (JSON-serializable).
    
    **RECOMMENDED FOR AGENTS**: This function returns data in a format
    that's easy for LLMs to parse and understand.
    
    Args:
        symbol: Stock symbol
        exchange: Exchange name
        interval: Data interval (see get_stock_data for options)
        n_bars: Number of bars to retrieve
        username: TradingView username (optional)
        password: TradingView password (optional)
    
    Returns:
        Dictionary with keys: 'symbol', 'exchange', 'interval', 'data', 'summary'
        where 'data' is a list of dicts with OHLCV data
    """
    """
    Retrieve stock data and return as a dictionary (JSON-serializable).
    
    Useful for agents that need structured data in dictionary format.
    
    Args:
        symbol: Stock symbol
        exchange: Exchange name
        interval: Data interval (see get_stock_data for options)
        n_bars: Number of bars to retrieve
        username: TradingView username (optional)
        password: TradingView password (optional)
    
    Returns:
        Dictionary with keys: 'symbol', 'exchange', 'interval', 'data', 'summary'
        where 'data' is a list of dicts with OHLCV data
    """
    df = get_stock_data(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        n_bars=n_bars,
        username=username,
        password=password,
    )
    
    # Convert DataFrame to list of dicts
    data_records = []
    for idx, row in df.iterrows():
        record = {
            "datetime": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
            "open": float(row.get("open", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "close": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
        }
        data_records.append(record)
    
    return {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "data": data_records,
        "summary": {
            "total_bars": len(df),
            "date_range": {
                "start": str(df.index[0]),
                "end": str(df.index[-1]),
            },
            "price_range": {
                "min": float(df["low"].min()),
                "max": float(df["high"].max()),
            },
            "current_price": float(df["close"].iloc[-1]),
            "average_volume": float(df["volume"].mean()),
        },
    }


def get_stock_data_for_agent(
    symbol: str,
    exchange: str,
    interval: Literal["daily", "weekly", "monthly", "1min", "5min", "15min", "30min", "1hour", "4hour"] = "daily",
    n_bars: int = 100,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Agent-safe wrapper for get_stock_data() that always returns a string.
    
    This function is specifically designed for use with mcp-agent.
    It always returns a string (never DataFrame) to avoid Pydantic serialization issues.
    
    Args:
        symbol: Stock symbol
        exchange: Exchange name
        interval: Data interval
        n_bars: Number of bars to retrieve
        username: TradingView username (optional)
        password: TradingView password (optional)
    
    Returns:
        Formatted string with stock data summary and recent data
    """
    return get_stock_data(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        n_bars=n_bars,
        username=username,
        password=password,
        return_format="string",  # Always return string for agents
    )


def get_multiple_symbols(
    symbols: list[tuple[str, str]],
    interval: str = "daily",
    n_bars: int = 100,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Retrieve data for multiple symbols at once.
    
    Args:
        symbols: List of (symbol, exchange) tuples
        interval: Data interval
        n_bars: Number of bars per symbol
        username: TradingView username (optional)
        password: TradingView password (optional)
    
    Returns:
        Dictionary mapping symbol to DataFrame
    """
    results = {}
    for symbol, exchange in symbols:
        try:
            df = get_stock_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                n_bars=n_bars,
                username=username,
                password=password,
            )
            results[symbol] = df
        except Exception as e:
            logger.warning(f"Failed to retrieve {symbol}: {str(e)}")
            results[symbol] = None
    
    return results
