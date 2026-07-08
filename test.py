import requests
from src.config.config_env import settings    



def _extract_photo_urls(place: dict, api_key: str, max_photos: int = 4) -> list[str]:
    """Return up to `max_photos` direct image URLs for a place, if any exist."""
    photos = place.get("photos", [])
    urls = []
    for photo in photos[:max_photos]:
        resource_name = photo.get("name")
        if resource_name:
            urls.append(
                f"https://places.googleapis.com/v1/{resource_name}/media"
                f"?key={api_key}&maxHeightPx=400"
            )
    return urls

def get_cityinfo(city_name: str) -> dict:
    """Look up basic info for a city by name.
 
    Returns a dict with: city_name, country, lat, lng, and photos
    (up to 4 image URLs). Use this tool when you need image lists for a city
    and return the `photos` list as an array of image URLs in the final JSON.
    """
    api_key = settings.google_api_key
    print(api_key)
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.addressComponents,"
            "places.location,"
            "places.photos"
        ),
    }
    payload = {
        "textQuery": city_name,
        "includedType": "locality",
        "languageCode": "en",
    }
 
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return {"error": f"{response.status_code}: {response.text}"}
 
        places = response.json().get("places", [])
        if not places:
            return {"error": f"No city found for '{city_name}'."}
 
        place = places[0]
 
        # Extract country from address components
        country = "N/A"
        for component in place.get("addressComponents", []):
            if "country" in component.get("types", []):
                country = component.get("longText", "N/A")
                break
 
        location = place.get("location", {})
 
        return {
            "city_name": place.get("displayName", {}).get("text", city_name),
            "country": country,
            "lat": location.get("latitude"),
            "lng": location.get("longitude"),
            "photos": _extract_photo_urls(place, api_key) or ["No photos available"],
        }
 
    except Exception as e:
        return {"error": str(e)}
    


print(get_cityinfo("Dhaka"))