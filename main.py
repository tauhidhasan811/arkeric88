from langchain_core.messages import HumanMessage

from src.graph.graph import graph

result = graph.invoke(
    {
        "messages": [
            HumanMessage(
                content="tell about the weather today "
            )
        ]
    }
)

print(
    result["messages"][-1].content
)