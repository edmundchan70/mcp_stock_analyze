"""
MCP-Agent Template: Stock Data Analysis with TradingView
---------------------------------------------------------
Complete template showing how to use TradingView data functions
with mcp-agent framework for stock analysis workflows.

This template demonstrates:
1. Simple agent with TradingView functions
2. Orchestrator workflow with multiple agents
3. Quality-controlled data collection
4. Comprehensive analysis workflow
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.orchestrator.orchestrator import Orchestrator
from mcp_agent.workflows.llm.augmented_llm import RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.evaluator_optimizer.evaluator_optimizer import (
    EvaluatorOptimizerLLM,
    QualityRating,
)

# Import our TradingView data functions
# IMPORTANT: Use agent-safe functions (return str/dict, not DataFrame)
from tradingview_data import (
    get_stock_data_for_agent,  # Agent-safe: always returns str
    get_stock_data_dict,       # Agent-safe: returns dict
    get_stock_data,            # For programmatic use (returns DataFrame)
    get_multiple_symbols,
)

# Configuration
OUTPUT_DIR = "stock_reports"
SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
EXCHANGE = sys.argv[2] if len(sys.argv) > 2 else "NASDAQ"

# Initialize MCPApp
app = MCPApp(name="stock_analyzer_mcp", human_input_callback=None)


async def example_1_simple_agent():
    """
    Example 1: Simple Agent with TradingView Functions
    -------------------------------------------------
    Basic usage: Agent can call TradingView functions directly.
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Simple Agent with TradingView Functions")
    print("="*70)
    
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Create a simple data collection agent
        data_agent = Agent(
            name="stock_data_agent",
            instruction=f"""You are a stock data specialist for {SYMBOL} on {EXCHANGE}.
            
            You have access to TradingView data functions:
            - get_stock_data(): Get stock data (returns DataFrame or formatted string)
            - get_stock_data_dict(): Get stock data as JSON-serializable dictionary
            
            When asked to get stock data:
            1. Use get_stock_data() with return_format='string' for readable output
            2. Analyze the returned data
            3. Provide insights about price, volume, and trends
            
            Remember: Functions RETURN values that you can read and analyze.
            """,
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Agent-safe functions
        )
        
        async with data_agent:
            llm = await data_agent.attach_llm(OpenAIAugmentedLLM)
            
            query = f"Get the last 100 days of daily data for {SYMBOL} on {EXCHANGE}. Tell me the current price, price range, and average volume."
            
            logger.info(f"Query: {query}")
            result = await llm.generate_str(
                message=query,
                request_params=RequestParams(model="gpt-4o"),
            )
            
            print(f"\nAgent Response:\n{result}\n")


async def example_2_orchestrator_workflow():
    """
    Example 2: Orchestrator Workflow with Multiple Agents
    ------------------------------------------------------
    Advanced usage: Orchestrator coordinates multiple specialized agents.
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Orchestrator Workflow with Multiple Agents")
    print("="*70)
    
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Agent 1: Data Collector
        data_collector = Agent(
            name="data_collector",
            instruction=f"""Collect comprehensive stock data for {SYMBOL} on {EXCHANGE}.
            
            Use get_stock_data_for_agent() to retrieve:
            - At least 200 days of daily data
            - Always returns readable string format
            
            Provide complete data including:
            - Current price
            - Price history
            - Volume data
            - Date ranges
            """,
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Agent-safe functions
        )
        
        # Agent 2: Technical Analyst
        technical_analyst = Agent(
            name="technical_analyst",
            instruction=f"""Analyze technical aspects of {SYMBOL} stock data.
            
            Based on the data provided:
            1. Identify price trends (uptrend, downtrend, sideways)
            2. Analyze volume patterns
            3. Calculate key metrics (volatility, price changes)
            4. Identify support and resistance levels
            5. Provide technical insights
            """,
            server_names=[],  # No external tools, just analysis
        )
        
        # Agent 3: Report Writer
        report_writer = Agent(
            name="report_writer",
            instruction=f"""Create a comprehensive stock analysis report for {SYMBOL}.
            
            Structure the report with:
            1. Executive Summary (current price, key metrics)
            2. Data Overview (date range, data points)
            3. Technical Analysis (trends, patterns, insights)
            4. Key Findings (main observations)
            5. Recommendations (if applicable)
            
            Use markdown formatting.
            """,
            server_names=[],
        )
        
        # Create Orchestrator
        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[data_collector, technical_analyst, report_writer],
            plan_type="iterative",  # Dynamic planning
        )
        
        # Define the task
        task = f"""Create a comprehensive stock analysis for {SYMBOL} on {EXCHANGE}:
        
        1. Use data_collector to get at least 200 days of daily stock data
        2. Use technical_analyst to analyze the data and provide technical insights
        3. Use report_writer to create a well-formatted analysis report
        
        The final report should be comprehensive and include all key metrics and insights.
        """
        
        logger.info(f"Starting orchestrator workflow for {SYMBOL}")
        result = await orchestrator.generate_str(
            message=task,
            request_params=RequestParams(model="gpt-4o"),
        )
        
        print(f"\nOrchestrator Result:\n{result}\n")


async def example_3_quality_controlled_collection():
    """
    Example 3: Quality-Controlled Data Collection
    -----------------------------------------------
    Uses EvaluatorOptimizerLLM to ensure data quality before analysis.
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Quality-Controlled Data Collection")
    print("="*70)
    
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Data Collection Agent
        data_collector = Agent(
            name="data_collector",
            instruction=f"""Collect stock data for {SYMBOL} on {EXCHANGE}.
            
            Use get_stock_data() with:
            - n_bars=200 (minimum)
            - return_format='string' for readable output
            - Include all required data points
            
            Provide complete data with:
            - Current price
            - Historical prices
            - Volume data
            - Date information
            """,
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Agent-safe functions
        )
        
        # Data Quality Evaluator
        data_evaluator = Agent(
            name="data_evaluator",
            instruction=f"""Evaluate the quality of stock data collection for {SYMBOL}.
            
            Check for:
            1. COMPLETENESS: All required data present (price, volume, dates)
            2. ACCURACY: Data is specific and verifiable
            3. CURRENCY: Data is recent (within last trading day)
            4. FORMAT: Data is readable and well-formatted
            
            Rate as:
            - EXCELLENT: All criteria met perfectly
            - GOOD: All required data present, minor gaps acceptable
            - FAIR: Most data present but missing some elements
            - POOR: Missing critical data
            
            If rating is below GOOD, specify what needs to be improved.
            """,
            server_names=[],
        )
        
        # Quality Controller (EvaluatorOptimizerLLM)
        quality_controller = EvaluatorOptimizerLLM(
            optimizer=data_collector,
            evaluator=data_evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.GOOD,
            max_refinements=3,
        )
        
        # Analyst Agent
        analyst = Agent(
            name="analyst",
            instruction=f"""Analyze the verified stock data for {SYMBOL}.
            
            Based on the high-quality data provided:
            1. Calculate key metrics (price changes, volatility)
            2. Identify trends and patterns
            3. Provide investment insights
            4. Highlight key findings
            """,
            server_names=[],
        )
        
        # Create Orchestrator
        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[quality_controller, analyst],
            plan_type="iterative",
        )
        
        task = f"""Analyze {SYMBOL} on {EXCHANGE}:
        
        1. Use the quality_controller to collect and verify stock data
           (it will automatically ensure data quality)
        2. Use analyst to provide comprehensive analysis based on the verified data
        
        Ensure the analysis is based on high-quality, verified data.
        """
        
        logger.info(f"Starting quality-controlled analysis for {SYMBOL}")
        result = await orchestrator.generate_str(
            message=task,
            request_params=RequestParams(model="gpt-4o"),
        )
        
        print(f"\nQuality-Controlled Analysis Result:\n{result}\n")


async def example_4_comprehensive_workflow():
    """
    Example 4: Comprehensive Workflow (Full VCP Pattern Analysis Setup)
    --------------------------------------------------------------------
    Complete workflow similar to the financial analyzer example.
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Comprehensive Workflow (VCP Pattern Analysis Setup)")
    print("="*70)
    
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Create output directory
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{SYMBOL.lower()}_analysis_{timestamp}.md"
        output_path = os.path.join(OUTPUT_DIR, output_file)
        
        # 1. Data Collection Agent
        data_collector = Agent(
            name="data_collector",
            instruction=f"""Collect comprehensive stock data for {SYMBOL} on {EXCHANGE}.
            
            Use get_stock_data_for_agent() to retrieve:
            - Minimum 200 days of daily data (preferably 6-12 months)
            - Always returns readable string format
            - Include OHLCV data (Open, High, Low, Close, Volume)
            
            Provide complete data with proper formatting.
            """,
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Agent-safe functions
        )
        
        # 2. Data Quality Evaluator
        data_evaluator = Agent(
            name="data_evaluator",
            instruction=f"""Evaluate stock data quality for {SYMBOL}.
            
            Check for completeness, accuracy, and currency.
            Rate as EXCELLENT/GOOD/FAIR/POOR.
            """,
            server_names=[],
        )
        
        # 3. Quality Controller
        quality_controller = EvaluatorOptimizerLLM(
            optimizer=data_collector,
            evaluator=data_evaluator,
            llm_factory=OpenAIAugmentedLLM,
            min_rating=QualityRating.GOOD,
        )
        
        # 4. Technical Analyst
        technical_analyst = Agent(
            name="technical_analyst",
            instruction=f"""Perform technical analysis on {SYMBOL} data.
            
            Analyze:
            - Price trends and patterns
            - Volume analysis
            - Support/resistance levels
            - Volatility patterns
            - Potential VCP (Volatility Contraction Pattern) formations
            """,
            server_names=[],
        )
        
        # 5. Comprehensive Analyst
        comprehensive_analyst = Agent(
            name="comprehensive_analyst",
            instruction=f"""Provide comprehensive analysis for {SYMBOL}.
            
            Combine technical analysis with:
            - Key metrics summary
            - Trend identification
            - Pattern recognition
            - Investment insights
            - Risk assessment
            """,
            server_names=[],
        )
        
        # 6. Report Writer
        report_writer = Agent(
            name="report_writer",
            instruction=f"""Create a professional stock analysis report for {SYMBOL}.
            
            Report structure:
            # {SYMBOL} Stock Analysis Report
            ## Executive Summary
            ## Data Overview
            ## Technical Analysis
            ## Key Findings
            ## Investment Insights
            ## Risk Factors
            ## Conclusion
            
            Save to: {output_path}
            """,
            server_names=["filesystem"] if "filesystem" in context.config.mcp.servers else [],
        )
        
        # Configure filesystem if available
        if "filesystem" in context.config.mcp.servers:
            context.config.mcp.servers["filesystem"].args.extend([os.getcwd()])
            logger.info("Filesystem server configured")
        
        # Create Orchestrator
        orchestrator = Orchestrator(
            llm_factory=OpenAIAugmentedLLM,
            available_agents=[
                quality_controller,
                technical_analyst,
                comprehensive_analyst,
                report_writer,
            ],
            plan_type="iterative",
        )
        
        task = f"""Create a comprehensive stock analysis report for {SYMBOL} on {EXCHANGE}:
        
        1. Use quality_controller to collect and verify high-quality stock data
           (minimum 200 days, preferably 6-12 months)
        
        2. Use technical_analyst to perform technical analysis on the data
        
        3. Use comprehensive_analyst to synthesize findings and provide insights
        
        4. Use report_writer to create a professional markdown report
           and save it to: {output_path}
        
        The final report should be comprehensive, well-formatted, and include
        all key metrics, technical analysis, and investment insights.
        """
        
        logger.info(f"Starting comprehensive analysis workflow for {SYMBOL}")
        try:
            result = await orchestrator.generate_str(
                message=task,
                request_params=RequestParams(model="gpt-4o"),
            )
            
            if os.path.exists(output_path):
                logger.info(f"Report successfully generated: {output_path}")
                print(f"\n✅ Report saved to: {output_path}\n")
            else:
                logger.warning(f"Report may not have been saved to {output_path}")
                print(f"\n⚠️  Report may not have been saved. Check logs.\n")
            
            print(f"Workflow Result:\n{result[:500]}...\n")  # Show first 500 chars
            
        except Exception as e:
            logger.error(f"Error during workflow: {str(e)}")
            print(f"\n❌ Error: {str(e)}\n")


async def main():
    """Main entry point - run different examples."""
    
    print("\n" + "="*70)
    print("MCP-AGENT TEMPLATE: Stock Analysis with TradingView")
    print("="*70)
    print(f"\nSymbol: {SYMBOL}")
    print(f"Exchange: {EXCHANGE}")
    print("\nAvailable Examples:")
    print("1. Simple Agent (basic usage)")
    print("2. Orchestrator Workflow (multiple agents)")
    print("3. Quality-Controlled Collection (with evaluator)")
    print("4. Comprehensive Workflow (full analysis)")
    print("\n" + "="*70)
    
    # Uncomment the example you want to run:
    
    # Example 1: Simple agent
    await example_1_simple_agent()
    
    # Example 2: Orchestrator workflow
    # await example_2_orchestrator_workflow()
    
    # Example 3: Quality-controlled collection
    # await example_3_quality_controlled_collection()
    
    # Example 4: Comprehensive workflow
    # await example_4_comprehensive_workflow()


if __name__ == "__main__":
    asyncio.run(main())
