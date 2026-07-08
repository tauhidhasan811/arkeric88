import requests
from langchain_core.tools import tool
from src.config import config





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
 
 
 
@tool
def get_cityinfo(city_name: str) -> dict:
    """Look up basic info for a city by name.
 
    Returns a dict with: city_name, country, lat, lng, and photos
    (up to 4 image URLs). Use this tool when you need image lists for a city
    and return the `photos` list as an array of image URLs in the final JSON.
    """
    api_key = config.Settings.google_api_key
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
 
 
@tool
def get_detailed_tourist_places(location_name: str) -> list[dict]:
    """Search for tourist attractions in a given location.
 
    Returns a list of dicts, each with: name, address, phone, photos
    (up to 4 image URLs), and available_time (weekday opening hours).
    Use this tool to fetch image arrays for attractions and include the
    returned `photos` values in the image field of your response.
    """
    api_key = config.Settings.google_api_key
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.nationalPhoneNumber,"
            "places.regularOpeningHours,"
            "places.photos"
        ),
    }
    payload = {
        "textQuery": f"tourist attractions in {location_name}",
        "includedType": "tourist_attraction",
        "languageCode": "en",
    }
 
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return [{"error": f"{response.status_code}: {response.text}"}]
 
        places = response.json().get("places", [])
        results = []
 
        for place in places:
            weekday_descriptions = place.get("regularOpeningHours", {}).get(
                "weekdayDescriptions", []
            )
            results.append(
                {
                    "name": place.get("displayName", {}).get("text", "N/A"),
                    "address": place.get("formattedAddress", "No address available"),
                    "phone": place.get("nationalPhoneNumber", "No phone number listed"),
                    "photos": _extract_photo_urls(place, api_key) or ["No photos available"],
                    "available_time": weekday_descriptions
                    or ["Hours not available or open 24/7"],
                }
            )
 
        return results
 
    except Exception as e:
        return [{"error": str(e)}]
 
 
@tool
def get_it_companies(location_name: str) -> list[dict]:
    """Search for top IT/software companies in a given location.
 
    Returns a list of dicts, each with: name, address, phone, photos
    (up to 4 image URLs), and office_hours (weekday opening hours).
    Use this tool when you need real business/place images and preserve the
    `photos` list as an array in the final JSON.
    """
    api_key = config.Settings.google_api_key
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.nationalPhoneNumber,"
            "places.regularOpeningHours,"
            "places.photos"
        ),
    }
    payload = {
        "textQuery": f"top software IT companies in {location_name}",
        "languageCode": "en",
    }
 
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return [{"error": f"{response.status_code}: {response.text}"}]
 
        places = response.json().get("places", [])
        results = []
 
        for place in places:
            weekday_descriptions = place.get("regularOpeningHours", {}).get(
                "weekdayDescriptions", []
            )
            results.append(
                {
                    "name": place.get("displayName", {}).get("text", "N/A"),
                    "address": place.get("formattedAddress", "No address listed"),
                    "phone": place.get("nationalPhoneNumber", "No phone number listed"),
                    "photos": _extract_photo_urls(place, api_key) or ["No photos available"],
                    "office_hours": weekday_descriptions or ["Hours not listed"],
                }
            )
 
        return results
 
    except Exception as e:
        return [{"error": str(e)}]
 
 
@tool
def get_google_hotels_sorted_by_rating(location_name: str) -> list[dict]:
    """Search for hotels/resorts in a given location, sorted by rating (highest first).
 
    Returns a list of dicts, each with: name, rating, phone, price_level,
    address, photos (up to 4 image URLs), and coords (lat/lng).
    Use this tool to gather hotel image arrays and include the returned
    `photos` list in your response instead of inventing URLs.
    """
    api_key = config.Settings.google_api_key
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.priceLevel,"
            "places.location,"
            "places.rating,"
            "places.nationalPhoneNumber,"
            "places.photos"
        ),
    }
    payload = {
        "textQuery": f"resorts in {location_name}",
        "includedType": "hotel",
        "pageSize": 10,
    }
 
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            return [{"error": f"{response.status_code}: {response.text}"}]
 
        places = response.json().get("places", [])
        if not places:
            return []
 
        hotel_list = []
        for place in places:
            coords = place.get("location", {})
            hotel_list.append(
                {
                    "name": place.get("displayName", {}).get("text", "N/A"),
                    "rating": place.get("rating", 0.0),
                    "phone": place.get("nationalPhoneNumber", "No phone number listed"),
                    "price_level": place.get("priceLevel", "NOT_AVAILABLE"),
                    "address": place.get("formattedAddress", "No address listed"),
                    "photos": _extract_photo_urls(place, api_key) or ["No photo available"],
                    "coords": {
                        "lat": coords.get("latitude"),
                        "lng": coords.get("longitude"),
                    },
                }
            )
 
        hotel_list.sort(key=lambda h: h["rating"], reverse=True)
        return hotel_list
 
    except Exception as e:
        return [{"error": str(e)}]
 
 
@tool
def calculate_distance_routes_api(origin_address: str, destination_address: str) -> dict:
    """Calculate driving distance and duration between two addresses.
 
    Returns a dict with: origin, destination, distance_km, duration_hours,
    and duration_minutes.
    """
    api_key = config.Settings.google_api_key
    if not api_key:
        return {"error": "Missing Google Maps API key."}
 
    url = "https://routes.googleapis.com/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.legs.distanceMeters,routes.legs.duration",
    }
    payload = {
        "origin": {"address": origin_address},
        "destination": {"address": destination_address},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
 
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
 
        data = response.json()
        leg = data["routes"][0]["legs"][0]
 
        distance_km = leg["distanceMeters"] / 1000
        duration_seconds = int(leg["duration"].rstrip("s"))
 
        return {
            "origin": origin_address,
            "destination": destination_address,
            "distance_km": round(distance_km, 2),
            "duration_hours": round(duration_seconds / 3600, 2),
            "duration_minutes": round(duration_seconds / 60),
        }
 
    except (KeyError, IndexError):
        return {"error": "Could not parse route details.", "raw": data}
    except Exception as e:
        return {"error": str(e)}