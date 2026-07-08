import requests
from langchain_core.tools import tool
from src.config import config
@tool
def get_cityinfo(temperature: int) -> str:
    """Return a city name when the temperature is above 40°C."""

    if temperature > 40:
        return "Dhaka"

    return "No city found"

@tool
def get_detailed_tourist_places(used_for, location_name):
    url = "https://places.googleapis.com/v1/places:searchText"
    
    # Updated FieldMask to include photos, phone number, and regular opening hours
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": config.Settings.google_api_key,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.nationalPhoneNumber,"
            "places.regularOpeningHours,"
            "places.photos"
        )
    }
    
    payload = {
        "textQuery": f"{used_for} in {location_name}",
        "includedType": "tourist_attraction", 
        "languageCode": "en"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        place_data = {}
        all_places = []
        if response.status_code == 200:
            data = response.json()
            places = data.get("places", [])
            
            if not places:
                print(f"No tourist places found for '{location_name}'.")
                return
            
            print(f"--- Detailed Tourist Places in {location_name} ---\n")
            for index, place in enumerate(places, 1):
                name = place.get("displayName", {}).get("text", "N/A")
                phone = place.get("nationalPhoneNumber", "No phone number listed")
                
                # Extract Opening Hours
                opening_hours = place.get("regularOpeningHours", {})
                weekday_descriptions = opening_hours.get("weekdayDescriptions", [])
                
                # Extract Photo References (Google returns an array of photo objects)
                photos = place.get("photos", [])
                photo_info = "No photos available"
                if photos:
                    # Getting the resource name of the primary/first photo
                    photo_resource_name = photos[0].get("name")
                    # You can construct a Direct Image URL using this resource name
                    photo_info = f"https://places.googleapis.com/v1/{photo_resource_name}/media?key={api_key}&maxHeightPx=400"

                place_data['name'] = name
                place_data['phone'] = phone
                place_data['photo_info'] = photo_info
                
                
                days = []
                if weekday_descriptions:
                    for day in weekday_descriptions:
                        days.apend(day)
                else:
                    print("       Hours not available or open 24/7")
                print("-" * 50)

                place_data['avaiable_time'] = days

            return place_data
                
        else:
            print(f"Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

