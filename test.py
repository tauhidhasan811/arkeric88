from src.config.config_openai import GetOpenAILlm

llm = GetOpenAILlm()

print(llm.invoke("per km cost in doller in paris in all type of transposr and give a list of dict a dn one ticket price, public + taxis/ride share/etc, average trip distance(3 km").content)