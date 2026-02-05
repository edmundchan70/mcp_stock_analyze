"""
Example: Using TradingView data functions with mcp-agent (DEBUG VERSION)
-----------------------------------------------------------------------
This version includes extensive debugging to see what's happening.
"""

import asyncio
import sys
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from mcp_agent.workflows.llm.augmented_llm import RequestParams

# Import agent-safe functions
from tradingview_data import get_stock_data_for_agent, get_stock_data_dict

# Initialize app
app = MCPApp(name="stock_data_agent", human_input_callback=None)


async def main():
    """Example: Agent using TradingView data functions with debugging."""
    print("="*70)
    print("STARTING AGENT EXAMPLE WITH DEBUGGING")
    print("="*70)
    
    try:
        async with app.run() as analyzer_app:
            context = analyzer_app.context
            logger = analyzer_app.logger
            
            print("\n[DEBUG] App context initialized")
            print(f"[DEBUG] Logger: {logger}")
            
            # Create an agent with access to TradingView data functions
            print("\n[DEBUG] Creating agent...")
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
""",
                functions=[get_stock_data_for_agent, get_stock_data_dict],
            )
            
            print("[DEBUG] Agent created")
            print(f"[DEBUG] Agent functions: {[f.__name__ for f in data_collector_agent.functions]}")
            
            # Use the agent
            print("\n[DEBUG] Entering agent context...")
            async with data_collector_agent:
                print("[DEBUG] Agent context entered")
                
                print("[DEBUG] Attaching LLM...")
                llm = await data_collector_agent.attach_llm(OpenAIAugmentedLLM)
                print("[DEBUG] LLM attached")
                
                # Example query
                query = """Get the last 100 days of daily data for Apple (AAPL) on NASDAQ. 
Then tell me:
1. The current price
2. The price range over this period
3. The average volume
4. Any notable trends"""
                
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
                        request_params=RequestParams(model="gpt-4o", max_iterations=10),
                    )
                    
                    print("\n" + "="*70)
                    print("AGENT RESPONSE RECEIVED")
                    print("="*70)
                    
                    if result:
                        print(f"\n{result}\n")
                        logger.info(f"Result:\n{result}")
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
                print("DEBUGGING INFO")
                print("="*70)
                print("""
How it works:
1. LLM sees user query
2. LLM decides to call get_stock_data_for_agent('AAPL', 'NASDAQ', n_bars=100)
3. Function executes and RETURNS a string value
4. Return value is converted to text and added to conversation
5. LLM sees the data as text in the conversation
6. LLM analyzes the data and responds with insights
                """)
            
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
    print("\nStarting agent example...")
    print("Make sure you have:")
    print("1. OpenAI API key in mcp_agent.secrets.yaml")
    print("2. Internet connection for TradingView data")
    print("3. Required packages installed\n")
    
    asyncio.run(main())
