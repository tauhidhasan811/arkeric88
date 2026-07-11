import requests
from langchain_core.tools import tool
from src.config.config_env import settings
from src.core.image_registry import image_registry

def calculate_distance_routes_api(origin_address: str, destination_address: str) -> dict:

    api_key = settings.google_api_key
    if not api_key:
        return {"error": "Missing Google Maps API key."}
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
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
        response = requests.post(url, json=payload, headers=headers, timeout=20)
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
    

dist = calculate_distance_routes_api("Dhaka", "Chittagong")

print(dist)



"""
def _extract_photo_urls(place: dict, api_key: str, max_photos: int = 4) -> list[str]:

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


def _extract_photo_ids(place: dict, api_key: str, max_photos: int = 4) -> list[str]:

    return image_registry.register_many(_extract_photo_urls(place, api_key, max_photos))



def get_google_hotels_sorted_by_rating(location_name: str) -> list[dict]:

    api_key = settings.google_api_key
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
        response = requests.post(url, headers=headers, json=payload, timeout=20)
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
                    "photos": _extract_photo_ids(place, api_key) or ["No photo available"],
                    "coords": {
                        "lat": coords.get("latitude"),
                        "lng": coords.get("longitude"),
                    },
                }
            )
        hotel_list.sort(key=lambda h: h["rating"], reverse=True)
        print("=" * 100)
        print(" " * 40, "Hotel Information")
        print("=" * 100)
        print(hotel_list)
        return hotel_list
    except Exception as e:
        return [{"error": str(e)}]


locations = get_google_hotels_sorted_by_rating("dhaka")

print(locations)"""