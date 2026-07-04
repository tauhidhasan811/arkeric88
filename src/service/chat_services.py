from src.graph.graph import graph


def get_ai_response(Prompt: dict) -> str:
    result = graph.invoke(Prompt)
    return result["messages"][-1].content