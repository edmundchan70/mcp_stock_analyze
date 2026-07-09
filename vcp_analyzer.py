"""
VCP Analysis Agent - Stock Volatility Contraction Pattern Analyzer
-----------------------------------------------------------------------
This agent analyzes stocks for VCP (Volatility Contraction Pattern) setups using:
1. TradingView data retrieval (tradingview_data.py)
2. VCP pattern detection (vcp_scan.py)

HOW TO RUN:
-----------
1. Activate your virtual environment:
   - Windows: venv\Scripts\activate
   - Linux/Mac: source venv/bin/activate

2. Ensure you have:
   - OpenRouter API key set (OPENROUTER_API_KEY environment variable or .env file)
   - Internet connection for TradingView data
   - All required packages installed (see requirements.txt)

3. Run the script:
   python vcp_analyzer.py

4. When prompted, enter:
   - Stock symbol (e.g., AAPL, TSLA, MSFT)
   - Exchange (e.g., NASDAQ, NYSE)

5. The agent will:
   - Fetch historical stock data from TradingView
   - Analyze VCP patterns
   - Report contractions, pivot points, and pattern validity

REQUIREMENTS:
------------
- Python 3.10+
- Virtual environment with packages from requirements.txt
- OpenRouter API key
- Internet connection
"""

import asyncio
import os
import sys
from typing import Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

# Load environment variables from .env file
load_dotenv()

# Import agent-safe functions
from tradingview_data import get_stock_data_for_agent, get_stock_data_dict
from vcp_scan import analyze_vcp_for_agent


class MissingEnvironmentVariableError(Exception):
    """Raised when a required environment variable is missing."""
    
    def __init__(self, variable_name: str, message: Optional[str] = None):
        """
        Initialize the exception.
        
        Args:
            variable_name: Name of the missing environment variable
            message: Optional custom error message
        """
        self.variable_name = variable_name
        if message is None:
            message = (
                f"Missing required environment variable: {variable_name}\n"
                f"Please set {variable_name} in your environment or .env file.\n"
                f"For example: export {variable_name}=your_api_key_here"
            )
        super().__init__(message)


def check_environment_variables() -> None:
    """
    Check that all required environment variables are set.
    
    Raises:
        MissingEnvironmentVariableError: If any required environment variable is missing
    """
    required_vars = {
        "OPENROUTER_API_KEY": (
            "OpenRouter API key is required for using OpenAIAugmentedLLM via OpenRouter. "
            "You can set it via:\n"
            "  1. Environment variable: export OPENROUTER_API_KEY=your_key\n"
            "  2. .env file: OPENROUTER_API_KEY=your_key\n"
        ),
    }
    
    missing_vars = []
    for var_name, error_message in required_vars.items():
        value = os.getenv(var_name)
        if not value or value.strip() == "":
            missing_vars.append((var_name, error_message))
    
    if missing_vars:
        error_messages = []
        for var_name, error_message in missing_vars:
            error_messages.append(f"\n{var_name}:\n  {error_message}")
        
        full_message = (
            "Missing required environment variable(s):\n" + "\n".join(error_messages)
        )
        raise MissingEnvironmentVariableError(
            variable_name=", ".join([var for var, _ in missing_vars]),
            message=full_message
        )


def configure_openrouter() -> None:
    """
    Configure environment variables for OpenRouter compatibility with the mcp_agent framework.
    
    The mcp_agent framework's OpenAIAugmentedLLM reads from OPENAI_* environment variables.
    Since OpenRouter is OpenAI-compatible, we map OPENROUTER_API_KEY to OPENAI_API_KEY
    and set the base URL to OpenRouter's endpoint.
    """
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_api_key:
        os.environ["OPENAI_API_KEY"] = openrouter_api_key
    
    # Set OpenRouter base URL for OpenAI-compatible API
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"


# Initialize app
app = MCPApp(name="stock_data_agent", human_input_callback=None)


async def main():
    """VCP Analysis Agent using TradingView data and VCP pattern detection."""
    print("="*70)
    print("VCP ANALYSIS AGENT")
    print("="*70)
    
    # Check environment variables before proceeding
    print("\n[DEBUG] Checking environment variables...")
    print(f"[DEBUG] .env file loaded: {os.path.exists('.env')}")
    api_key_present = bool(os.getenv("OPENROUTER_API_KEY"))
    print(f"[DEBUG] OPENROUTER_API_KEY found: {api_key_present}")
    if api_key_present:
        key_preview = os.getenv("OPENROUTER_API_KEY", "")[:20] + "..." if len(os.getenv("OPENROUTER_API_KEY", "")) > 20 else os.getenv("OPENROUTER_API_KEY", "")
        print(f"[DEBUG] API Key preview: {key_preview}")
    
    try:
        check_environment_variables()
        print("[DEBUG] All required environment variables are set")
    except MissingEnvironmentVariableError as e:
        print(f"\n[ERROR] Environment variable check failed:")
        print(f"{str(e)}\n")
        print("\n[DEBUG] Troubleshooting:")
        print("1. Make sure .env file exists in the project root")
        print("2. Check .env file format: OPENROUTER_API_KEY=your_key_here (no quotes, no spaces around =)")
        print("3. Verify the file is named exactly '.env' (not '.env.txt' or similar)")
        sys.exit(1)
    
    # Configure OpenRouter settings before initializing the app context
    configure_openrouter()
    print("[DEBUG] OpenRouter configured: base_url=https://openrouter.ai/api/v1")
    
    try:
        async with app.run() as analyzer_app:
            context = analyzer_app.context
            logger = analyzer_app.logger
            
            print("\n[DEBUG] App context initialized")
            print(f"[DEBUG] Logger: {logger}")
            
            # Get ticker information from user
            print("\n" + "="*70)
            print("STOCK VCP ANALYSIS AGENT")
            print("="*70)
            print("\nPlease provide the following information:")
            
            symbol = input("Enter stock symbol (e.g., AAPL, TSLA): ").strip().upper()
            exchange = input("Enter exchange (e.g., NASDAQ, NYSE): ").strip().upper()
            
            if not symbol or not exchange:
                print("\n[ERROR] Symbol and exchange are required!")
                sys.exit(1)
            
            print(f"\n[INFO] Analyzing {symbol} on {exchange}...")
            print("[INFO] This may take a moment to fetch data and analyze VCP patterns...\n")
            
            # Create an agent with access to TradingView data and VCP analysis functions
            print("[DEBUG] Creating agent...")
            vcp_analyzer_agent = Agent(
                name="vcp_analyzer",
                instruction="""You are a VCP (Volatility Contraction Pattern) analysis specialist.

You have access to functions that can:
1. Retrieve historical stock data from TradingView
2. Analyze VCP patterns in stock data

When analyzing a stock for VCP patterns, you MUST:
1. First call get_stock_data_for_agent() to retrieve the stock data (use at least 300 bars for accurate VCP analysis)
2. Then call analyze_vcp_for_agent() to perform VCP pattern analysis
3. Read and interpret the VCP analysis results carefully
4. Provide a comprehensive summary including:
   - Whether a valid VCP setup exists
   - Details about each contraction (depth, dates, prices)
   - Pivot points identified
   - Overall pattern assessment

IMPORTANT: 
- Always call the functions to get real data. Do not make up data.
- For VCP analysis, use at least 300 bars (n_bars=300) to ensure sufficient historical data
- The VCP analysis will show contractions numbered from oldest (#1) to newest (#3+)
- A valid VCP setup requires: uptrend, contracting volatility, contracting volume, and near 52-week highs

Provide clear, actionable insights about the VCP pattern detected.

ON 
### Trading Insights and Recommendations
- Imagine your self as Mark Minervini, a famous stock market investor that created the VCP pattern.
- Rate the stock as A+ for Text book VCP setup. A for a good VCP setup. B for a fair VCP setup. N/A for no VCP setup.
- 
""",
                functions=[get_stock_data_for_agent, get_stock_data_dict, analyze_vcp_for_agent],
            )
            
            print("[DEBUG] Agent created")
            print(f"[DEBUG] Agent functions: {[f.__name__ for f in vcp_analyzer_agent.functions]}")
            
            # Use the agent
            print("[DEBUG] Entering agent context...")
            async with vcp_analyzer_agent:
                print("[DEBUG] Agent context entered")
                
                print("[DEBUG] Attaching LLM...")
                llm = await vcp_analyzer_agent.attach_llm(OpenAIAugmentedLLM)
                print("[DEBUG] LLM attached")
                
                # Build query with user-provided ticker
                query = f"""Analyze the VCP (Volatility Contraction Pattern) for {symbol} on {exchange}.

Please:
1. Retrieve at least 300 days of daily data for {symbol} on {exchange}
2. Perform a comprehensive VCP pattern analysis
3. Report:
   - Whether a valid VCP setup exists (Previous VCP Setup: Yes/No)
   - Details of each contraction (#1, #2, #3, etc.) with their depths, dates, and prices
   - All pivot points identified
   - Overall assessment of the pattern
   - Any trading insights or recommendations

Provide a clear, detailed analysis of the VCP pattern."""
                
                print("\n" + "="*70)
                print("SENDING QUERY TO AGENT")
                print("="*70)
                print(f"Query: {query}\n")
                
                logger.info(f"Query: {query}")
                
                print("[DEBUG] Calling llm.generate_str()...")
                print("[DEBUG] This may take a moment as the LLM processes the request...")
                
                try:
                    result = await llm.generate_str(
                        message=query,
                        request_params=RequestParams(
                            model="deepseek/deepseek-v4-flash",
                            max_iterations=10,
                        ),
                    )
                    
                    print("\n" + "="*70)
                    print("AGENT RESPONSE RECEIVED")
                    print("="*70)
                    
                    if result:
                        print(f"\n{result}\n")
                        logger.info(f"Result:\n{result}")
                        
                        # Save report to file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        report_filename = f"VCP_Report_{symbol}_{exchange}_{timestamp}.txt"
                        report_path = Path(report_filename)
                        
                        # Create report content
                        report_content = f"""
                                VCP ANALYSIS REPORT
                                {'=' * 80}
                                Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                                Symbol: {symbol}
                                Exchange: {exchange}
                                {'=' * 80}

                                {result}

                                {'=' * 80}
                                End of Report
                                {'=' * 80}
                                """
                        try:
                            with open(report_path, 'w', encoding='utf-8') as f:
                                f.write(report_content)
                            print(f"\n[SUCCESS] Report saved to: {report_filename}")
                            logger.info(f"Report saved to: {report_filename}")
                        except Exception as e:
                            print(f"\n[WARNING] Failed to save report: {str(e)}")
                            logger.warning(f"Failed to save report: {str(e)}")
                    else:
                        print("\n[WARNING] Result is empty or None!")
                        logger.warning("Result is empty or None")
                    
                except Exception as e:
                    print(f"\n[ERROR] Exception during LLM generation: {str(e)}")
                    print(f"[ERROR] Exception type: {type(e).__name__}")
                    import traceback
                    traceback.print_exc()
                    logger.error(f"Error during generation: {str(e)}", exc_info=True)
                    raise
                
                print("\n" + "="*70)
                print("ANALYSIS COMPLETE")
                print("="*70)
            
            print("\n[DEBUG] Exited agent context")
        
        print("\n[DEBUG] Exited app context")
        
    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "="*70)
    print("COMPLETED")
    print("="*70)


if __name__ == "__main__":
    print("\nStarting VCP Analysis Agent...")
    print("Make sure you have:")
    print("1. OpenRouter API key set (via OPENROUTER_API_KEY env var or .env file)")
    print("2. Internet connection for TradingView data")
    print("3. Required packages installed")
    print("4. Virtual environment activated (venv)\n")
    
    try:
        asyncio.run(main())
    except MissingEnvironmentVariableError as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrupted by user")
        sys.exit(0)
