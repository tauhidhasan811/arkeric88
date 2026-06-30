from langchain_core.messages import HumanMessage

from src.graph.graph import graph

result = graph.invoke(
    {
        "messages": [
            HumanMessage(
                content="Hello!"
            )
        ]
    }
)

print(
    result["messages"][-1].content
)