from langgraph.graph import StateGraph, START, END
from src.graph.nodes import chatbot
from src.graph.state import ChatState
from tools.tools import get_cityinfo
from src.tools.get_weather import get_current_weather
from langgraph.prebuilt import ToolNode, tools_condition

builder = StateGraph(ChatState)


builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode([get_current_weather, get_cityinfo]))



builder.add_edge(START, "chatbot")

builder.add_conditional_edges("chatbot", tools_condition)

builder.add_edge("tools", "chatbot")

# builder.add_edge( "chatbot", END)

graph = builder.compile()