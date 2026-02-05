"""
Example: Using TradingView data functions with mcp-agent
---------------------------------------------------------
This demonstrates how to use the tradingview_data functions
with agents in the mcp-agent framework.

KEY CONCEPT: Functions RETURN values, and the LLM sees these
return values as text in the conversation.
"""

import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

# Import our TradingView data functions
# IMPORTANT: Use agent-safe functions that return only serializable types
from tradingview_data import get_stock_data_for_agent, get_stock_data_dict

# Initialize app
app = MCPApp(name="stock_data_agent", human_input_callback=None)


async def main():
    """Example: Agent using TradingView data functions."""
    async with app.run() as analyzer_app:
        context = analyzer_app.context
        logger = analyzer_app.logger
        
        # Create an agent with access to TradingView data functions
        # The agent can call these functions, and the LLM will see
        # the RETURN VALUES as text in the conversation
        data_collector_agent = Agent(
            name="stock_data_collector",
            instruction="""You are a stock data collection specialist.

You have access to functions that can retrieve historical stock data from TradingView.

When a user requests stock data, you MUST:
1. Call get_stock_data_for_agent(symbol='AAPL', exchange='NASDAQ', n_bars=100) to get the data
2. Read the returned data carefully
3. Analyze the data and provide a detailed response

IMPORTANT: You MUST call the function to get the data. Do not make up data.
The function will return formatted text with stock information that you can read and analyze.

After calling the function, provide:
- Current price
- Price range
- Average volume
- Notable trends

Always specify the symbol and exchange clearly when calling functions.
Common exchanges: NASDAQ, NYSE, NSE (India), etc.
""",
            functions=[get_stock_data_for_agent, get_stock_data_dict],  # Register agent-safe functions
        )
        
        # Use the agent
        async with data_collector_agent:
            llm = await data_collector_agent.attach_llm(OpenAIAugmentedLLM)
            
            # Example query - the agent will call get_stock_data() and see the result
            query = """Get the last 100 days of daily data for Apple (AAPL) on NASDAQ. 
            Then tell me:
            1. The current price
            2. The price range over this period
            3. The average volume
            4. Any notable trends"""
            
            logger.info(f"Query: {query}")
            print(f"\n[INFO] Sending query to agent...")
            print(f"[INFO] Query: {query}\n")
            
            try:
                result = await llm.generate_str(
                    message=query,
                    request_params=RequestParams(model="gpt-4o", max_iterations=10),
                )
                
                logger.info(f"Result:\n{result}")
                
                print("\n" + "="*60)
                print("AGENT RESPONSE:")
                print("="*60)
                
                if result:
                    print(result)
                else:
                    print("[WARNING] No response received from agent!")
                    print("[INFO] Check logs for more details")
                    
            except Exception as e:
                print(f"\n[ERROR] Exception occurred: {str(e)}")
                print(f"[ERROR] Type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                logger.error(f"Error: {str(e)}", exc_info=True)
                raise
            
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
            """)


if __name__ == "__main__":
    asyncio.run(main())
