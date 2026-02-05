"""
Main entry point for stock data retrieval.
Can be used standalone or imported by agents.
"""

from tradingview_data import get_stock_data, get_stock_data_dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Standalone usage example."""
    # Get user input
    symbol = input('Enter the symbol: ').strip().upper()
    exchange = input('Enter the exchange: ').strip().upper()
    
    # Optional: TradingView credentials (leave empty for unauthenticated access)
    username = None  # Set to your TradingView username if needed
    password = None   # Set to your TradingView password if needed
    
    try:
        # Retrieve data
        df = get_stock_data(
            symbol=symbol,
            exchange=exchange,
            interval='daily',
            n_bars=100,
            username=username,
            password=password,
            save_to_csv=True,  # Save to CSV file
        )
        
        # Display summary
        print(f"\n{'='*60}")
        print(f"Data Summary for {symbol} on {exchange}")
        print(f"{'='*60}")
        print(f"Total bars: {len(df)}")
        print(f"Date range: {df.index[0]} to {df.index[-1]}")
        print(f"Current price: ${df['close'].iloc[-1]:.2f}")
        print(f"Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
        print(f"Average volume: {df['volume'].mean():,.0f}")
        print(f"\nFirst 5 rows:")
        print(df.head())
        print(f"\nData saved to: {symbol}_daily_*.csv")
        
    except Exception as e:
        logger.error(f"Error retrieving data: {str(e)}")
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
