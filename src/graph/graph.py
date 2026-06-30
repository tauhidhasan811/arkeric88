from langgraph.graph import StateGraph, START, END
from src.graph.nodes import chatbot
from src.graph.state import ChatState

builder = StateGraph(ChatState)
builder.add_node(
    "chatbot",
    chatbot
)

builder.add_edge(START, "chatbot")

builder.add_edge( "chatbot", END)

graph = builder.compile()