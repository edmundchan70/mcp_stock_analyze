"""
Quick test to verify TradingView function works
"""

from tradingview_data import get_stock_data_for_agent

print("Testing get_stock_data_for_agent()...")
print("="*60)

try:
    result = get_stock_data_for_agent('AAPL', 'NASDAQ', n_bars=10)
    print("\n✅ Function works!")
    print(f"\nResult type: {type(result)}")
    print(f"Result length: {len(result)} characters")
    print("\nFirst 500 characters:")
    print(result[:500])
    print("\n" + "="*60)
except Exception as e:
    print(f"\n❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
