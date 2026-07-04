from langchain_core.messages import HumanMessage

from src.graph.graph import graph

result = graph.invoke(
    {
        "messages": [
            HumanMessage(
                content="can you give me one single image link of dhaka city "
            )
        ]
    }
)

print(
    result["messages"][-1].content
)