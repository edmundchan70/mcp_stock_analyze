"""
Example: Using TradingView data functions with mcp-agent (FIXED VERSION)
-----------------------------------------------------------------------
This demonstrates how to use the tradingview_data functions
with agents in the mcp-agent framework.

FIXED: Uses agent-safe functions that return only serializable types.
"""

import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

# Import agent-safe functions (return only str or dict, not DataFrame)
from tradingview_data import get_stock_data_for_agent, get_stock_data_dict

# Initialize app
app = MCPApp(name="stock_data_agent", human_input_callback=None)


async def main():
    """Example: Agent using TradingView data functions."""
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Create an agent with access to TradingView data functions
        # IMPORTANT: Only use functions that return serializable types (str, dict)
        # NOT functions that return pandas DataFrame
        data_collector_agent = Agent(
            name="stock_data_collector",
            instruction="""You are a stock data collection specialist.
            
            You have access to functions that can retrieve historical stock data
            from TradingView. When a user requests stock data:
            
            1. Use get_stock_data_for_agent() to get readable stock data
               OR use get_stock_data_dict() to get structured JSON data
            
            2. The function will RETURN data (not print it)
            
            3. You will see the return value as text in the conversation
            
            4. Analyze the data and provide insights:
               - Current price
               - Price trends
               - Volume patterns
               - Key metrics
            
            Always specify the symbol and exchange clearly when calling functions.
            Common exchanges: NASDAQ, NYSE, NSE (India), etc.
            
            IMPORTANT: The functions return values that you can read and analyze.
            Use the returned data to answer questions and provide insights.
            """,
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Agent-safe functions
        )
        
        # Use the agent
        async with data_collector_agent:
            llm = await data_collector_agent.attach_llm(OpenAIAugmentedLLM)
            
            # Example query - the agent will call get_stock_data_for_agent() and see the result
            query = """Get the last 100 days of daily data for Apple (AAPL) on NASDAQ. 
            Then tell me:
            1. The current price
            2. The price range over this period
            3. The average volume
            4. Any notable trends"""
            
            logger.info(f"Query: {query}")
            result = await llm.generate_str(
                message=query,
                request_params=RequestParams(model="gpt-4o"),
            )
            
            logger.info(f"Result:\n{result}")
            print("\n" + "="*60)
            print("AGENT RESPONSE:")
            print("="*60)
            print(result)
            
            print("\n" + "="*60)
            print("HOW IT WORKS:")
            print("="*60)
            print("""
1. LLM sees user query: "Get AAPL data..."
2. LLM decides to call: get_stock_data_for_agent('AAPL', 'NASDAQ')
3. Function executes and RETURNS a string value
4. Return value is converted to text and added to conversation
5. LLM sees the data as text in the conversation
6. LLM analyzes the data and responds with insights
            
The key: Functions RETURN values, and the LLM reads these return values!

NOTE: We use get_stock_data_for_agent() instead of get_stock_data() because:
- get_stock_data() can return pandas DataFrame (not serializable)
- get_stock_data_for_agent() always returns string (serializable)
            """)


if __name__ == "__main__":
    # asyncio.run() creates an event loop and runs the async function
    # This is needed because main() is an async function
    # The error was NOT from asyncio.run(), but from trying to register
    # a function that returns pandas DataFrame (not serializable)
    asyncio.run(main())
