from langchain_core.tools import tool

@tool
def get_cityinfo(temperature: int) -> str:
    """Return a city name when the temperature is above 40°C."""

    if temperature > 40:
        return "Dhaka"

    return "No city found"