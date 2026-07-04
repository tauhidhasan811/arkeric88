from src.config.config_openai import GetOpenAILlm


def get_ai_response(prompt: str) -> str:
    response = GetOpenAILlm().invoke(prompt)
    content = getattr(response, "content", None)

    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    return str(content or "")