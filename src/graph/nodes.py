from src.config.config_openai import GetOpenAILlm
from src.tools.get_city import get_cityinfo
from src.tools.get_weather import get_current_weather

tools = [get_current_weather, get_cityinfo]
llm = GetOpenAILlm().bind_tools(tools)

def chatbot(state):
    response = llm.invoke(
        state['messages']
    )

    return{
        "messages": [response]
    }