from langchain_core.messages import SystemMessage

from src.config.config_openai import GetOpenAILlm
from src.tools.get_weather import get_current_weather
from src.tools.tools import (
    calculate_distance_routes_api,
    get_cityinfo,
    get_detailed_tourist_places,
    get_google_hotels_sorted_by_rating,
    get_it_companies,
)

SYSTEM_PROMPT = """You are a travel planning assistant. Use the available tools whenever the user needs real place data, hotels, attractions, routes, or image URLs. When a tool returns a photos list, preserve it as an array of image URLs in your final JSON and do not invent URLs. Prefer tool output over guessing."""

tools = [
    get_current_weather,
    get_cityinfo,
    get_detailed_tourist_places,
    get_it_companies,
    get_google_hotels_sorted_by_rating,
    calculate_distance_routes_api,
]
llm = GetOpenAILlm().bind_tools(tools)


def chatbot(state):
    messages = list(state.get("messages", []))
    if not any(getattr(message, "type", None) == "system" for message in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT), *messages]

    response = llm.invoke(messages)

    return {"messages": [response]}