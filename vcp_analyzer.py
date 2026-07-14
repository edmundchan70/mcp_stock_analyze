"""
VCP Analysis Agent - Stock Volatility Contraction Pattern Analyzer
-----------------------------------------------------------------------
Multi-agent system using OpenRouter:
1. Data Retrieval Agent (deepseek/deepseek-v4-flash) - fetches stock data with retries
2. VCP Analysis Agent (anthropic/claude-sonnet-4.5) - analyzes VCP patterns

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

# Load environment variables from .env file FIRST (before any imports)
load_dotenv()

# Import agent-safe functions
from tradingview_data import get_stock_data_for_agent, get_stock_data_dict
from vcp_scan import analyze_vcp_for_agent

# Import Pydantic models
from models import DataResult, AnalysisResult


# =============================================================================
# Environment Setup
# =============================================================================

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
    """Check that all required environment variables are set.

    Raises:
        MissingEnvironmentVariableError: If any required environment variable is missing
    """
    required_var = "OPENROUTER_API_KEY"
    value = os.getenv(required_var)
    if not value or value.strip() == "":
        message = (
            f"Missing required environment variable: {required_var}\n"
            f"OpenRouter API key is required.\n"
            f"Please set it via:\n"
            f"  1. Environment variable: export {required_var}=your_key\n"
            f"  2. .env file: {required_var}=your_key"
        )
        raise MissingEnvironmentVariableError(variable_name=required_var, message=message)


def configure_openrouter() -> None:
    """Configure environment variables for OpenRouter compatibility.

    The mcp_agent framework's OpenAIAugmentedLLM reads from OPENAI_* env vars.
    Since OpenRouter is OpenAI-compatible, we map OPENROUTER_API_KEY to OPENAI_API_KEY
    and set the base URL to OpenRouter's endpoint.
    """
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_api_key:
        os.environ["OPENAI_API_KEY"] = openrouter_api_key
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"


# =============================================================================
# Agent 1: Data Retrieval Agent
# =============================================================================

async def run_data_retrieval_agent(
    app,
    symbol: str,
    exchange: str,
    logger
) -> DataResult:
    """Run the Data Retrieval Agent to fetch stock data from TradingView.

    This agent uses deepseek/deepseek-v4-flash and has retry logic built into
    its prompt instructions. It can ask the user for clarification if the
    symbol/exchange combination yields no data.

    Args:
        app: The MCPApp instance
        symbol: Stock symbol (e.g., 'AAPL')
        exchange: Exchange name (e.g., 'NASDAQ')
        logger: Logger instance

    Returns:
        DataResult with success status, data, or error message
    """
    from mcp_agent.app import MCPApp
    from mcp_agent.agents.agent import Agent
    from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
    from mcp_agent.workflows.llm.augmented_llm import RequestParams

    print("\n" + "=" * 70)
    print("PHASE 1: DATA RETRIEVAL AGENT")
    print(f"Model: deepseek/deepseek-v4-flash")
    print("=" * 70)

    data_retrieval_agent = Agent(
        name="data_retriever",
        instruction="""You are a **Stock Data Retrieval Specialist**.

Your ONLY job is to fetch historical stock data from TradingView for VCP analysis.

**Available Functions:**
1. `get_stock_data_for_agent(symbol, exchange, interval, n_bars)` - Returns formatted stock data string
2. `get_stock_data_dict(symbol, exchange, interval, n_bars)` - Returns dict with stock data

**MANDATORY RULES:**
1. Always request at least 300 bars (n_bars=300) with daily interval
2. You MUST call one of the data functions. Do NOT make up data.
3. After calling the function, EVALUATE the result:
   - If the data has at least 300 rows and required columns → SUCCESS. Report the data summary.
   - If data is empty, error, or insufficient → RETRY up to 3 times total
   
**RETRY LOGIC (max 3 attempts total):**
- Attempt 1: Call get_stock_data_for_agent() with original parameters
- If result is error/empty → Attempt 2: Retry same call
- If still failing → Attempt 3: Try with different parameters (e.g., n_bars=500)
- If all 3 attempts fail → Report failure

**USER CLARIFICATION:**
If after 3 retries the data still fails, ask the user to verify the symbol/exchange:
Example: "No data found for 'TSLC' on NASDAQ. Did you mean 'TSLA'? (y/n): "
- If user says yes → retry with corrected symbol
- If user says no → ask for correct values and retry
- Limit clarification rounds to 3

**SUCCESS CRITERIA:**
- Must confirm data contains at least 300 rows of daily data
- Must confirm open, high, low, close, volume columns exist
- Report key stats: date range, price range, average volume

**OUTPUT FORMAT (for success):**
```
DATA RETRIEVAL SUCCESSFUL
Symbol: {symbol}
Exchange: {exchange}
Data Points: {count}
Date Range: {start} to {end}
Price Range: ${low} - ${high}
Avg Volume: {volume}
```

**OUTPUT FORMAT (for failure):**
```
DATA RETRIEVAL FAILED
Symbol: {symbol}
Exchange: {exchange}
Attempts: {count}
Error: {details}
```
""",
        functions=[get_stock_data_for_agent, get_stock_data_dict],
    )

    async with data_retrieval_agent:
        llm = await data_retrieval_agent.attach_llm(OpenAIAugmentedLLM)

        query = f"""
Fetch daily stock data for {symbol} on {exchange}.

Call get_stock_data_for_agent(symbol="{symbol}", exchange="{exchange}", interval="daily", n_bars=300).

If the data is empty or contains an error, retry up to 3 times.
If ALL retries fail, ask the user if the symbol is correct.

Report the data summary or failure clearly.
"""
        print(f"[INFO] Data Retrieval Agent fetching {symbol} on {exchange}...")

        try:
            result = await llm.generate_str(
                message=query,
                request_params=RequestParams(
                    model="deepseek/deepseek-v4-flash",
                    max_iterations=15,
                ),
            )
        except Exception as e:
            return DataResult(
                success=False,
                symbol=symbol,
                exchange=exchange,
                error=f"Data Retrieval Agent LLM error: {str(e)}",
                attempts=3,
            )

    # Parse result to determine success/failure
    if result and "DATA RETRIEVAL SUCCESSFUL" in result:
        print("\n[SUCCESS] Data retrieval completed.")
        return DataResult(
            success=True,
            symbol=symbol,
            exchange=exchange,
            data_summary=result,
            agent_response=result,
            error="",
            attempts=1,
        )
    else:
        print(f"\n[ERROR] Data retrieval failed or incomplete.")
        return DataResult(
            success=False,
            symbol=symbol,
            exchange=exchange,
            data_summary="",
            agent_response=result or "No response from agent",
            error=result or "Data retrieval failed after retries",
            attempts=3,
        )


# =============================================================================
# Agent 2: VCP Analysis Agent
# =============================================================================

async def run_vcp_analysis_agent(
    app,
    symbol: str,
    exchange: str,
    logger
) -> AnalysisResult:
    """Run the VCP Analysis Agent to analyze VCP patterns.

    This agent uses anthropic/claude-sonnet-4.5 for superior reasoning
    and trading analysis. It calls analyze_vcp_for_agent() for pattern detection.

    Args:
        app: The MCPApp instance
        symbol: Stock symbol (e.g., 'AAPL')
        exchange: Exchange name (e.g., 'NASDAQ')
        logger: Logger instance

    Returns:
        AnalysisResult with report and rating
    """
    from mcp_agent.app import MCPApp
    from mcp_agent.agents.agent import Agent
    from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
    from mcp_agent.workflows.llm.augmented_llm import RequestParams

    print("\n" + "=" * 70)
    print("PHASE 2: VCP ANALYSIS AGENT")
    print(f"Model: anthropic/claude-sonnet-4.5")
    print("=" * 70)

    vcp_analysis_agent = Agent(
        name="vcp_analyst",
        instruction="""You are **Mark Minervini**, a world-renowned stock market investor who created the VCP (Volatility Contraction Pattern) strategy. You are also a VCP pattern analysis specialist.

**Available Functions:**
1. `analyze_vcp_for_agent(symbol, exchange, interval, n_bars, lookback_periods)` - Performs VCP analysis and returns a detailed report

**Your Task:**
You will be given a stock symbol and exchange. You MUST:
1. Call `analyze_vcp_for_agent()` with the symbol, exchange, interval="daily", n_bars=300, lookback_periods=3
2. Read and interpret the VCP analysis results carefully
3. Provide comprehensive trading insights

**Important Rules:**
- ALWAYS call the function to get real data. Do NOT make up or hallucinate data.
- If the VCP analysis returns an error, report the error clearly.

**Your Analysis Must Cover:**
1. **VCP Pattern Assessment:**
   - Whether a valid VCP setup exists (Previous VCP Setup: Yes/No)
   - Details of each contraction (#1 oldest → #3+ newest): depth %, dates, prices
   - All pivot points identified
   
2. **Condition Checks:**
   - Trend validity (Close > SMA50 > SMA150 > SMA200)
   - Volatility contraction pattern
   - Volume contraction
   - Near 52-week highs (>90%)

3. **Pattern Rating:**
   - **A+**: Textbook VCP setup - all conditions met, perfect contraction sequence
   - **A**: Good VCP setup - most conditions met, minor imperfections
   - **B**: Fair VCP setup - some conditions met, needs more development
   - **N/A**: No VCP setup detected

4. **Trading Insights:**
   - Key support and resistance levels
   - Volume analysis
   - Risk assessment
   - Potential entry considerations
   - What to watch for next

5. **Overall Assessment:**
   - Clear summary of the pattern quality
   - Actionable recommendations

**OUTPUT FORMAT:**
Start with: "### VCP ANALYSIS REPORT"
Then provide your full analysis.
End with: "**Pattern Rating:** [A+/A/B/N/A]"
""",
        functions=[analyze_vcp_for_agent],
    )

    async with vcp_analysis_agent:
        llm = await vcp_analysis_agent.attach_llm(OpenAIAugmentedLLM)

        query = f"""
Analyze the VCP (Volatility Contraction Pattern) for {symbol} on {exchange}.

Call analyze_vcp_for_agent(symbol="{symbol}", exchange="{exchange}", interval="daily", n_bars=300, lookback_periods=3).

Then provide:
1. Your assessment of whether this is a valid VCP setup
2. Details of each contraction (depth, dates, prices)
3. Pattern rating (A+, A, B, or N/A)
4. Trading insights and recommendations
5. Overall assessment

Be thorough and specific. Reference specific numbers from the analysis.
"""
        print(f"[INFO] VCP Analysis Agent analyzing {symbol} on {exchange}...")

        try:
            result = await llm.generate_str(
                message=query,
                request_params=RequestParams(
                    model="anthropic/claude-sonnet-4.5",
                    max_iterations=10,
                ),
            )
        except Exception as e:
            return AnalysisResult(
                success=False,
                report="",
                rating="N/A",
                error=f"VCP Analysis Agent LLM error: {str(e)}",
            )

    if result:
        print("\n[SUCCESS] VCP Analysis completed.")

        # Extract rating from result
        rating = "N/A"
        for line in result.split("\n"):
            if "Pattern Rating" in line or "pattern rating" in line.lower():
                # Extract A+, A, B, or N/A
                for r in ["A+", "A", "B", "N/A"]:
                    if r in line:
                        rating = r
                        break

        return AnalysisResult(
            success=True,
            report=result,
            rating=rating,
            error="",
        )
    else:
        return AnalysisResult(
            success=False,
            report="",
            rating="N/A",
            error="VCP Analysis Agent returned empty result",
        )


# =============================================================================
# Report Formatter
# =============================================================================

def save_report(
    symbol: str,
    exchange: str,
    data_result: DataResult,
    analysis_result: Optional[AnalysisResult],
) -> str:
    """Save the analysis report to a file.

    Args:
        symbol: Stock symbol
        exchange: Exchange name
        data_result: Result from Data Retrieval Agent
        analysis_result: Result from VCP Analysis Agent (None if data failed)

    Returns:
        Path to the saved report file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"VCP_Report_{symbol}_{exchange}_{timestamp}.txt"
    report_path = Path(report_filename)

    report_lines = [
        "=" * 80,
        "VCP ANALYSIS REPORT",
        "=" * 80,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Symbol: {symbol}",
        f"Exchange: {exchange}",
        f"Data Agent: deepseek/deepseek-v4-flash",
        f"Analysis Agent: anthropic/claude-sonnet-4.5",
        f"Provider: OpenRouter",
        "=" * 80,
        "",
        "--- DATA RETRIEVAL ---",
        "",
    ]

    if data_result.success:
        report_lines.append(f"Status: SUCCESS")
        report_lines.append(f"Attempts: {data_result.attempts}")
        report_lines.append(f"")
        report_lines.append(data_result.data_summary)
    else:
        report_lines.append(f"Status: FAILED")
        report_lines.append(f"Attempts: {data_result.attempts}")
        report_lines.append(f"Error: {data_result.error}")
        report_lines.append(f"")
        report_lines.append("--- RAW AGENT RESPONSE ---")
        report_lines.append(data_result.agent_response)

    report_lines.extend([
        "",
        "=" * 80,
        "",
        "--- VCP ANALYSIS ---",
        "",
    ])

    if analysis_result and analysis_result.success:
        report_lines.append(analysis_result.report)
    else:
        error_msg = analysis_result.error if analysis_result else "Skipped due to data retrieval failure"
        report_lines.append(f"Status: SKIPPED")
        report_lines.append(f"Reason: {error_msg}")

    report_lines.extend([
        "",
        "=" * 80,
        "End of Report",
        "=" * 80,
    ])

    report_content = "\n".join(report_lines)

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"\n[SUCCESS] Report saved to: {report_filename}")
    except Exception as e:
        print(f"\n[WARNING] Failed to save report: {str(e)}")

    return report_filename


# =============================================================================
# Main Orchestrator
# =============================================================================

async def main():
    """Main orchestrator - runs Data Retrieval Agent then VCP Analysis Agent."""
    from mcp_agent.app import MCPApp

    print("=" * 70)
    print("VCP ANALYSIS SYSTEM (Multi-Agent)")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Environment Check
    # ------------------------------------------------------------------
    print("\n[DEBUG] Checking environment variables...")
    print(f"[DEBUG] .env file loaded: {os.path.exists('.env')}")
    api_key_present = bool(os.getenv("OPENROUTER_API_KEY"))
    print(f"[DEBUG] OPENROUTER_API_KEY found: {api_key_present}")
    if api_key_present:
        key_preview = os.getenv("OPENROUTER_API_KEY", "")[:15] + "..." if len(os.getenv("OPENROUTER_API_KEY", "")) > 15 else os.getenv("OPENROUTER_API_KEY", "")
        print(f"[DEBUG] API Key preview: {key_preview}")

    try:
        check_environment_variables()
        print("[DEBUG] All required environment variables are set")
    except MissingEnvironmentVariableError as e:
        print(f"\n[ERROR] {str(e)}")
        print("\n[DEBUG] Troubleshooting:")
        print("1. Make sure .env file exists in the project root")
        print("2. Check .env file format: OPENROUTER_API_KEY=your_key_here (no quotes, no spaces around =)")
        print("3. Verify the file is named exactly '.env' (not '.env.txt' or similar)")
        sys.exit(1)

    configure_openrouter()
    print("[DEBUG] OpenRouter configured: base_url=https://openrouter.ai/api/v1")

    # ------------------------------------------------------------------
    # User Input
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STOCK VCP ANALYSIS")
    print("=" * 70)
    print("\nPlease provide the following information:")

    symbol = input("Enter stock symbol (e.g., AAPL, TSLA): ").strip().upper()
    exchange = input("Enter exchange (e.g., NASDAQ, NYSE): ").strip().upper()

    if not symbol or not exchange:
        print("\n[ERROR] Symbol and exchange are required!")
        sys.exit(1)

    print(f"\n[INFO] Starting analysis for {symbol} on {exchange}...\n")

    # ------------------------------------------------------------------
    # Agent 1: Data Retrieval Phase
    # ------------------------------------------------------------------
    data_app = MCPApp(name="data_retrieval_app", human_input_callback=None)
    data_result: DataResult

    try:
        async with data_app.run() as ctx:
            logger = ctx.logger
            logger.info(f"Data Retrieval Agent starting for {symbol} on {exchange}")

            data_result = await run_data_retrieval_agent(
                app=data_app,
                symbol=symbol,
                exchange=exchange,
                logger=logger,
            )

            if data_result.success:
                print("\n[INFO] Data retrieval successful. Proceeding to analysis phase...")
            else:
                print(f"\n[ERROR] Data retrieval failed after {data_result.attempts} attempts.")
                print(f"[ERROR] {data_result.error}")
    except Exception as e:
        print(f"\n[FATAL ERROR] Data Retrieval App failed: {str(e)}")
        import traceback
        traceback.print_exc()
        data_result = DataResult(
            success=False,
            symbol=symbol,
            exchange=exchange,
            error=f"Data Retrieval App error: {str(e)}",
            attempts=3,
        )

    # ------------------------------------------------------------------
    # Agent 2: VCP Analysis Phase (only if data retrieval succeeded)
    # ------------------------------------------------------------------
    analysis_result: Optional[AnalysisResult] = None

    if data_result.success:
        analysis_app = MCPApp(name="vcp_analysis_app", human_input_callback=None)

        try:
            async with analysis_app.run() as ctx:
                logger = ctx.logger
                logger.info(f"VCP Analysis Agent starting for {symbol} on {exchange}")

                analysis_result = await run_vcp_analysis_agent(
                    app=analysis_app,
                    symbol=symbol,
                    exchange=exchange,
                    logger=logger,
                )

                if analysis_result.success:
                    print(f"\n[INFO] VCP Analysis successful. Rating: {analysis_result.rating}")
                else:
                    print(f"\n[ERROR] VCP Analysis failed: {analysis_result.error}")
        except Exception as e:
            print(f"\n[FATAL ERROR] VCP Analysis App failed: {str(e)}")
            import traceback
            traceback.print_exc()
            analysis_result = AnalysisResult(
                success=False,
                error=f"VCP Analysis App error: {str(e)}",
            )
    else:
        print(f"\n[INFO] Skipping VCP Analysis due to data retrieval failure.")

    # ------------------------------------------------------------------
    # Generate Report
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("GENERATING FINAL REPORT")
    print("=" * 70)

    report_file = save_report(symbol, exchange, data_result, analysis_result)

    # Print summary to console
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Symbol: {symbol}")
    print(f"Exchange: {exchange}")
    print(f"Data Retrieval: {'✅ SUCCESS' if data_result.success else '❌ FAILED'}")
    if analysis_result:
        print(f"VCP Analysis: {'✅ SUCCESS' if analysis_result.success else '❌ FAILED'}")
        if analysis_result.success:
            print(f"Pattern Rating: {analysis_result.rating}")
    print(f"Report saved to: {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    print("\nStarting Multi-Agent VCP Analysis System...")
    print("=" * 70)
    print("Architecture:")
    print("  Agent 1: Data Retrieval  → deepseek/deepseek-v4-flash")
    print("  Agent 2: VCP Analysis    → anthropic/claude-sonnet-4.5")
    print("  Provider: OpenRouter")
    print("=" * 70)
    print("\nPrerequisites:")
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