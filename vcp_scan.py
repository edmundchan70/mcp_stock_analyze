"""
VCP (Volatility Contraction Pattern) Scanner

This script identifies VCP patterns in stock data, tracking contractions,
pivot points, and historical VCP setups.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

from models import (
    Contraction,
    PivotPoint,
    VCPSetup,
    StockReportEntry,
    VCPReport,
    ScanMetadata,
    ScanSummary,
    VCPSerializer,
)


def sma(series: pd.Series, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return series.rolling(window).mean()


def find_swing_points(
    df: pd.DataFrame,
    window: int = 5,
    min_price_change: float = 0.015,
) -> Tuple[List[PivotPoint], List[PivotPoint]]:
    """
    Find swing highs and lows with improved accuracy.
    Uses high/low columns for more accurate pivot detection.

    Args:
        df: DataFrame with price data
        window: Lookback/lookahead window for extrema detection
        min_price_change: Minimum price change to consider a swing

    Returns:
        Tuple of (swing_highs, swing_lows) as lists of PivotPoint objects
    """
    highs = df["high"].values
    lows = df["low"].values
    dates = df["datetime"].values

    swing_highs: List[PivotPoint] = []
    swing_lows: List[PivotPoint] = []

    # Find local highs using high column
    for i in range(window, len(highs) - window):
        # Check if it's a local high
        is_high = True
        for j in range(i - window, i + window + 1):
            if j != i and highs[j] >= highs[i]:
                is_high = False
                break

        if is_high:
            # Check if price change is significant
            if i > 0 and abs(highs[i] - highs[i - window]) / highs[i - window] >= min_price_change:
                swing_highs.append(PivotPoint(
                    date=str(dates[i]),
                    price=float(highs[i]),
                    type='high',
                    index=i,
                ))

    # Find local lows using low column
    for i in range(window, len(lows) - window):
        # Check if it's a local low
        is_low = True
        for j in range(i - window, i + window + 1):
            if j != i and lows[j] <= lows[i]:
                is_low = False
                break

        if is_low:
            # Check if price change is significant
            if i > 0 and abs(lows[i] - lows[i - window]) / lows[i - window] >= min_price_change:
                swing_lows.append(PivotPoint(
                    date=str(dates[i]),
                    price=float(lows[i]),
                    type='low',
                    index=i,
                ))

    return swing_highs, swing_lows


def find_contractions(
    df: pd.DataFrame,
    swing_highs: List[PivotPoint],
    swing_lows: List[PivotPoint],
    lookback: int = 3,
) -> List[Contraction]:
    """
    Identify contractions from swing points.

    Args:
        df: DataFrame with price data
        swing_highs: List of swing high pivot points
        swing_lows: List of swing low pivot points
        lookback: Number of recent contractions to analyze

    Returns:
        List of Contraction objects
    """
    if len(swing_highs) < lookback or len(swing_lows) < lookback:
        return []

    contractions: List[Contraction] = []

    # Analyze the most recent swing points
    recent_highs = swing_highs[-lookback:]

    for i, high_pivot in enumerate(recent_highs):
        # Find the next low after this high
        next_lows = [low for low in swing_lows if low.index > high_pivot.index]

        if not next_lows:
            continue

        low_pivot = next_lows[0]

        # Calculate contraction depth
        depth = (high_pivot.price - low_pivot.price) / high_pivot.price * 100

        # Find the actual start and end dates (first day of high to last day of low)
        high_start_idx = max(0, high_pivot.index - 5)
        low_end_idx = min(len(df) - 1, low_pivot.index + 5)

        # Get the actual high/low prices in the range
        high_range = df.iloc[high_pivot.index : low_pivot.index + 1]["high"]
        low_range = df.iloc[high_pivot.index : low_pivot.index + 1]["low"]

        actual_high = high_range.max()
        actual_low = low_range.min()
        actual_high_date = df.iloc[high_range.idxmax()]["datetime"]
        actual_low_date = df.iloc[low_range.idxmin()]["datetime"]

        # Calculate average volume for this contraction period
        avg_volume = df.iloc[high_pivot.index : low_pivot.index + 1]["volume"].mean()

        # Number from oldest (1) to newest (3+)
        contraction_num = i + 1

        contractions.append(Contraction(
            number=contraction_num,
            high_price=actual_high,
            low_price=actual_low,
            high_date=str(actual_high_date),
            low_date=str(actual_low_date),
            depth=depth,
            start_date=str(df.iloc[high_pivot.index]["datetime"]),
            end_date=str(df.iloc[low_pivot.index]["datetime"]),
            avg_volume=avg_volume,
        ))

    return contractions


def check_trend(df: pd.DataFrame, analysis_idx: int) -> bool:
    """Check if stock is in uptrend at given index."""
    if analysis_idx < 200:
        return False

    row = df.iloc[analysis_idx]
    return (row["close"] > row["SMA50"] > row["SMA150"] > row["SMA200"])


def check_near_highs(df: pd.DataFrame, analysis_idx: int, threshold: float = 0.9) -> bool:
    """Check if price is near 52-week high."""
    if analysis_idx < 252:
        return False

    recent_data = df.iloc[max(0, analysis_idx - 252) : analysis_idx + 1]
    high_52w = recent_data["close"].max()
    current_price = df.iloc[analysis_idx]["close"]

    return current_price >= threshold * high_52w


def scan_vcp_from_dataframe(df: pd.DataFrame, lookback_periods: int = 3) -> Optional[VCPSetup]:
    """
    Scan for VCP patterns in the provided DataFrame.

    Args:
        df: DataFrame with columns: datetime (or datetime index), open, high, low, close, volume
        lookback_periods: Number of contractions to analyze

    Returns:
        VCPSetup object with detailed analysis, or None if insufficient data
    """
    # Make a copy to avoid modifying original
    df = df.copy()

    # Handle datetime column or index
    if isinstance(df.index, pd.DatetimeIndex):
        # Reset index to make datetime a column
        df = df.reset_index()
        # Check which column is the datetime (usually first column or named 'index')
        datetime_col = None
        # Check if first column is datetime-like
        if len(df.columns) > 0:
            first_col = df.columns[0]
            if pd.api.types.is_datetime64_any_dtype(df[first_col]):
                datetime_col = first_col
        # Check for common datetime column names
        for col in ['datetime', 'date', 'time', 'index']:
            if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
                datetime_col = col
                break

        if datetime_col and datetime_col != "datetime":
            df.rename(columns={datetime_col: "datetime"}, inplace=True)
        elif "datetime" not in df.columns:
            # Fallback: use first column or create from index
            if len(df.columns) > 0:
                first_col = df.columns[0]
                if first_col not in ["open", "high", "low", "close", "volume"]:
                    df.rename(columns={first_col: "datetime"}, inplace=True)
                    df["datetime"] = pd.to_datetime(df["datetime"])
                else:
                    # Create datetime from original index
                    df.insert(0, "datetime", pd.to_datetime(df.index))
            else:
                df.insert(0, "datetime", pd.to_datetime(df.index))
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
    elif "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
    else:
        raise ValueError("DataFrame must have 'datetime' column or DatetimeIndex")

    if len(df) < 200:
        return None

    # Calculate moving averages
    df["SMA50"] = sma(df["close"], 50)
    df["SMA150"] = sma(df["close"], 150)
    df["SMA200"] = sma(df["close"], 200)

    # Find swing points
    swing_highs, swing_lows = find_swing_points(df)

    if len(swing_highs) < lookback_periods or len(swing_lows) < lookback_periods:
        print(f"Insufficient swing points: Found {len(swing_highs)} highs, {len(swing_lows)} lows")
        return None

    # Find contractions
    contractions = find_contractions(df, swing_highs, swing_lows, lookback_periods)

    if len(contractions) < lookback_periods:
        print(f"Insufficient contractions: Found {len(contractions)}")
        return None

    # Analyze the most recent valid point
    analysis_idx = len(df) - 1
    analysis_date = str(df.iloc[analysis_idx]["datetime"])

    # Check conditions
    # Note: contractions[0] is oldest, contractions[-1] is newest
    # For VCP: newest contraction should be smallest (most contracted)
    trend_valid = check_trend(df, analysis_idx)
    volatility_contracting = (
        len(contractions) >= 3
        and contractions[2].depth < contractions[1].depth < contractions[0].depth
    )
    volume_contracting = (
        len(contractions) >= 3
        and contractions[2].avg_volume < contractions[1].avg_volume < contractions[0].avg_volume
    )
    near_highs = check_near_highs(df, analysis_idx)

    is_valid = trend_valid and volatility_contracting and volume_contracting and near_highs

    # Combine all pivot points
    all_pivots = swing_highs + swing_lows
    all_pivots.sort(key=lambda x: x.index)

    return VCPSetup(
        contractions=contractions,
        pivot_points=all_pivots[-10:],  # Last 10 pivot points
        is_valid=is_valid,
        trend_valid=trend_valid,
        volatility_contracting=volatility_contracting,
        volume_contracting=volume_contracting,
        near_highs=near_highs,
        analysis_date=analysis_date,
    )


def format_pivot_points(pivot_points: List[PivotPoint]) -> List[str]:
    """
    Format pivot points into readable lines, grouping nearby pivots of the same type.

    Args:
        pivot_points: List of pivot points to format

    Returns:
        List of formatted strings for display
    """
    if not pivot_points:
        return ["No pivot points detected"]

    lines: List[str] = []
    processed_indices: set[int] = set()

    for pivot in pivot_points:
        if pivot.index in processed_indices:
            continue

        pivot_type = "HIGH" if pivot.type == 'high' else "LOW "

        # Find nearby pivots of the same type (within 3 days)
        nearby_pivots = [
            p
            for p in pivot_points
            if p.type == pivot.type and abs(p.index - pivot.index) <= 3 and p.index not in processed_indices
        ]

        if len(nearby_pivots) > 1:
            prices = [p.price for p in nearby_pivots]
            dates = [p.date for p in nearby_pivots]
            min_price = min(prices)
            max_price = max(prices)
            if abs(max_price - min_price) / min_price > 0.01:
                lines.append(f"  {pivot_type}: ${min_price:.2f} - ${max_price:.2f} (Range: {dates[0]} to {dates[-1]})")
            else:
                avg_price = sum(prices) / len(prices)
                lines.append(f"  {pivot_type}: ${avg_price:.2f} (Range: {dates[0]} to {dates[-1]})")
            processed_indices.update([p.index for p in nearby_pivots])
        else:
            lines.append(f"  {pivot_type}: ${pivot.price:.2f} on {pivot.date}")
            processed_indices.add(pivot.index)

    return lines


def scan_vcp(csv_path: str, lookback_periods: int = 3) -> Optional[VCPSetup]:
    """
    Scan for VCP patterns in the provided CSV file.

    Args:
        csv_path: Path to CSV file with columns: datetime, open, high, low, close, volume
        lookback_periods: Number of contractions to analyze

    Returns:
        VCPSetup object with detailed analysis, or None if insufficient data
    """
    # Load and prepare data
    df = pd.read_csv(csv_path)
    return scan_vcp_from_dataframe(df, lookback_periods)


def analyze_vcp_for_agent(
    symbol: str,
    exchange: str,
    interval: str = "daily",
    n_bars: int = 300,
    lookback_periods: int = 3,
) -> str:
    """
    Agent-safe function to analyze VCP pattern for a stock.

    This function fetches stock data and analyzes it for VCP patterns,
    returning a formatted string report suitable for LLM consumption.

    Args:
        symbol: Stock symbol (e.g., 'AAPL', 'TSLA')
        exchange: Exchange name (e.g., 'NASDAQ', 'NYSE')
        interval: Data interval (default: 'daily')
        n_bars: Number of bars to retrieve (default: 300 for sufficient data)
        lookback_periods: Number of contractions to analyze (default: 3)

    Returns:
        Formatted string with VCP analysis results
    """
    try:
        # Import here to avoid circular imports
        from tradingview_data import get_stock_data

        # Fetch stock data
        df = get_stock_data(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            n_bars=n_bars,
            return_format="dataframe",
        )

        # Ensure required columns exist
        required_cols = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_cols):
            return f"Error: DataFrame missing required columns. Found: {list(df.columns)}"

        # Analyze VCP pattern
        setup = scan_vcp_from_dataframe(df, lookback_periods)

        if setup is None:
            return (
                f"VCP Analysis for {symbol} ({exchange}):\n"
                f"Insufficient data or no VCP pattern detected.\n"
                f"Data points available: {len(df)}\n"
                f"Note: VCP analysis requires at least 200 data points and sufficient swing points."
            )

        # Format results as string
        result_lines = [
            f"VCP Analysis for {symbol} ({exchange})",
            "=" * 80,
            f"Analysis Date: {setup.analysis_date}",
            f"Previous VCP Setup: {'Yes' if setup.is_valid else 'No'}",
            "",
            "Condition Checks:",
            f"  Trend Valid (Close > SMA50 > SMA150 > SMA200): {setup.trend_valid}",
            f"  Volatility Contracting: {setup.volatility_contracting}",
            f"  Volume Contracting: {setup.volume_contracting}",
            f"  Near 52-Week Highs (>90%): {setup.near_highs}",
            "",
            "Contractions (Oldest to Newest):",
            "-" * 80,
        ]

        sorted_contractions = setup.sorted_contractions()
        for contraction in sorted_contractions:
            result_lines.extend([
                f"Contraction #{contraction.number}:",
                f"  High Price: ${contraction.high_price:.2f} (Date: {contraction.high_date})",
                f"  Low Price:  ${contraction.low_price:.2f} (Date: {contraction.low_date})",
                f"  Depth:      {contraction.depth:.2f}%",
                f"  Start Date: {contraction.start_date}",
                f"  End Date:   {contraction.end_date}",
                f"  Avg Volume: {contraction.avg_volume:,.0f}",
                "",
            ])

        result_lines.extend([
            "Recent Pivot Points:",
            "-" * 80,
        ])

        # Format and add pivot points using shared helper
        result_lines.extend(format_pivot_points(setup.pivot_points))

        return "\n".join(result_lines)

    except Exception as e:
        return f"Error analyzing VCP for {symbol} ({exchange}): {str(e)}"


def print_vcp_report(setup: VCPSetup) -> None:
    """Print a detailed VCP analysis report."""
    print("=" * 80)
    print("VCP PATTERN ANALYSIS REPORT")
    print("=" * 80)
    print(f"\nAnalysis Date: {setup.analysis_date}")
    print(f"\nPrevious VCP Setup: {'Yes' if setup.is_valid else 'No'}")
    print("\n" + "-" * 80)

    # Print condition checks
    print("\nCondition Checks:")
    print(f"  ✓ Trend Valid (Close > SMA50 > SMA150 > SMA200): {setup.trend_valid}")
    print(f"  ✓ Volatility Contracting: {setup.volatility_contracting}")
    print(f"  ✓ Volume Contracting: {setup.volume_contracting}")
    print(f"  ✓ Near 52-Week Highs (>90%): {setup.near_highs}")

    # Print contractions (sorted by number, oldest first)
    print("\n" + "-" * 80)
    print("\nContractions (Oldest to Newest):")
    print("-" * 80)

    sorted_contractions = setup.sorted_contractions()
    for contraction in sorted_contractions:
        print(f"\nContraction #{contraction.number}:")
        print(f"  High Price: ${contraction.high_price:.2f} (Date: {contraction.high_date})")
        print(f"  Low Price:  ${contraction.low_price:.2f} (Date: {contraction.low_date})")
        print(f"  Depth:      {contraction.depth:.2f}%")
        print(f"  Start Date: {contraction.start_date}")
        print(f"  End Date:   {contraction.end_date}")
        print(f"  Avg Volume: {contraction.avg_volume:,.0f}")

    # Print pivot points
    print("\n" + "-" * 80)
    print("\nRecent Pivot Points:")
    print("-" * 80)

    for line in format_pivot_points(setup.pivot_points):
        print(line)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    result = scan_vcp("alnt.csv")
    if result:
        print_vcp_report(result)
    else:
        print("No VCP pattern detected or insufficient data.")