from src.config.config_openai import GetOpenAILlm

llm = GetOpenAILlm()

def chatbot(state):
    response = llm.invoke(
        state['messages']
    )

    return{
        "messages": [response]
    }