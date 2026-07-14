from fastapi import APIRouter, HTTPException
from src.core.prompt_templete import PromptGenerator
from src.service.chat_services import get_ai_response
from app.schemas.city_body import (
    InputData,
    RegenerateInputData,
    RegenerateActivityInputData,
    TourPlanRequestData,
    StayInfo,
)
from src.core.data_processor import ProcessData
from src.session.city_session_store import CitySessionStore, ActivitySessionStore
from src.tools.tools import get_cityinfo, get_detailed_tourist_places, get_google_hotels_sorted_by_rating, calculate_distance_routes_api, get_nearby_restaurants
from src.core.image_registry import image_registry
import re
router = APIRouter()


def _parse_ai_response(response_text: str) -> dict:
    """Parse AI response text and convert to structured dict."""
    try:
        return ProcessData.EnsureDict(response_text)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


def _merge_regenerated_field(
    previous_response: dict,
    generated_response: dict,
    update_field_name: str,
) -> dict:
    """Merge regenerated field into previous response."""
    if update_field_name not in generated_response:
        raise HTTPException(
            status_code=502,
            detail=f"AI response did not include '{update_field_name}'.",
        )
    updated_response = previous_response.copy()
    updated_response[update_field_name] = generated_response[update_field_name]
    return updated_response


def _enrich_city_suggestions(suggested_cities: list) -> list:
    """
    Enrich LLM-proposed city suggestions with real data from get_cityinfo tool.
    For each city in the list:
    1. Call get_cityinfo with the city name
    2. Merge the tool's verified country, lat, lng, and photos list into the city dict
    3. If the tool errors, fall back to empty image list and null coordinates
    The LLM output should never contain city_image, latitude, or longitude -
    those are supplied entirely by this enrichment step.
    """
    enriched = []
    for city in suggested_cities:
        city_name = city.get("city_name", "")
        if not city_name:
            continue
        # Default values in case tool fails
        tool_country = None
        tool_photos = []
        tool_lat = None
        tool_lng = None
        try:
            result = get_cityinfo.invoke({"city_name": city_name})
            if result and "error" not in result:
                tool_country = result.get("country")
                tool_photos = result.get("photos", [])
                # Ensure photos is always a clean list[str]
                if not isinstance(tool_photos, list):
                    tool_photos = []
                else:
                    tool_photos = _clean_photos(tool_photos)
                location = result.get("lat")
                if location is not None:
                    tool_lat = float(location)
                location = result.get("lng")
                if location is not None:
                    tool_lng = float(location)
        except Exception:
            # Tool failure - keep defaults (empty photos, null coords)
            pass
        # country_name priority: tool's verified value > LLM's guess
        merged_country = tool_country if tool_country else city.get("country_name")
        enriched.append({
            "city_name": city_name,
            "country_name": merged_country,
            "city_image": tool_photos,
            "latitude": tool_lat,
            "longitude": tool_lng,
            "number_of_days": city.get("number_of_days"),
            "description": city.get("description", ""),
        })
    return enriched

# ==================== TOUR PLAN ENRICHMENT HELPERS ====================


def _find_hotel(
    city_name: str,
    total_budget: float,
    num_nights: int,
    profile_search_query: str = "",
) -> dict:
    """
    Find the best-rated hotel in the city that fits within the user's total budget.
    1. Call get_google_hotels_sorted_by_rating for the city
    2. Try best-rated first, then fall back to cheaper options if budget allows
    3. Returns hotel dict with name, address, rating, price_level, photos, coords
    """
    try:
        hotels = get_google_hotels_sorted_by_rating.invoke({
            "location_name": city_name,
            "search_query": profile_search_query or None,
        })
        if not hotels or "error" in hotels[0]:
            # Fallback: return a placeholder
            return _fallback_hotel(city_name)
        # Estimate hotel cost: if price_level indicates a numeric range, use mid-point
        # Otherwise assume ~$150/night as a reasonable estimate
        best_hotel = hotels[0]
        hotel_cost_per_night = _estimate_hotel_cost(best_hotel)
        total_hotel_cost = hotel_cost_per_night * num_nights
        # If the best hotel fits within budget (leaving at least some for activities),
        # return it. Otherwise try cheaper options.
        if total_hotel_cost < total_budget * 0.7:  # Leaves 30%+ for activities
            return best_hotel
        # Try cheaper hotels
        for hotel in hotels[1:]:
            hotel_cost_per_night = _estimate_hotel_cost(hotel)
            total_hotel_cost = hotel_cost_per_night * num_nights
            if total_hotel_cost < total_budget * 0.5:
                return hotel
        # If nothing fits well, return the cheapest available
        return hotels[-1] if len(hotels) > 1 else best_hotel
    except Exception:
        return _fallback_hotel(city_name)


def _estimate_hotel_cost(hotel: dict) -> float:
    """Estimate nightly hotel cost from price_level or return a default."""
    price_str = hotel.get("price_level", "NOT_AVAILABLE")
    # Google price levels: PRICE_LEVEL_UNSPECIFIED=0, INEXPENSIVE=1, MODERATE=2, EXPENSIVE=3, LUXURY=4
    price_map = {
        "PRICE_LEVEL_UNSPECIFIED": 100,
        "PRICE_LEVEL_INEXPENSIVE": 80,
        "PRICE_LEVEL_MODERATE": 150,
        "PRICE_LEVEL_EXPENSIVE": 250,
        "PRICE_LEVEL_LUXURY": 400,
        "NOT_AVAILABLE": 150,
    }
    return price_map.get(price_str, 150)


def _fallback_hotel(city_name: str) -> dict:
    """Return a fallback hotel object when the tool fails."""
    return {
        "name": f"Hotel in {city_name}",
        "address": f"City Center, {city_name}",
        "rating": 0.0,
        "price_level": "NOT_AVAILABLE",
        "photos": [],
        "coords": {"lat": 0.0, "lng": 0.0},
    }
_PHOTO_SENTINELS = {"No photos available", "No photo available"}
_MEAL_SCHEDULE = {
    "Breakfast": ("08:00 AM - 09:00 AM", 18),
    "Lunch": ("12:30 PM - 01:30 PM", 30),
    "Dinner": ("07:00 PM - 08:30 PM", 55),
}


def _dump_tour_plan(tour_plan: list) -> list:
    """Convert Pydantic/dataclass tour plan objects to plain dicts."""
    dumped = []
    for day in tour_plan or []:
        day_dict = day.model_dump() if hasattr(day, "model_dump") else dict(day)
        dumped.append(day_dict)
    return dumped


def _normalize_place_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _place_key(place: dict) -> str:
    name = _normalize_place_text(place.get("name") or place.get("activity_name", ""))
    address = _normalize_place_text(place.get("address") or place.get("activity_address", ""))
    return f"{name}|{address}" if name or address else ""


def _clean_photos(photos: list) -> list:
    if not isinstance(photos, list):
        return []
    return [
        image_registry.resolve(photo)
        for photo in photos
        if isinstance(photo, str) and photo not in _PHOTO_SENTINELS
    ]


def _is_tool_error_list(results: list) -> bool:
    return bool(results and isinstance(results[0], dict) and "error" in results[0])


def _build_profile_search_context(questions_answers) -> str:
    """Create positive Google Places terms from all experience-shaping answers."""
    nightly_budget = questions_answers.budget_per_person_per_night
    if nightly_budget is None:
        nightly_budget = questions_answers.effective_total_budget / questions_answers.trip_length_days
    if nightly_budget <= 150:
        budget_tier = "entry budget"
    elif nightly_budget <= 400:
        budget_tier = "premium"
    elif nightly_budget <= 1000:
        budget_tier = "luxury"
    else:
        budget_tier = "ultra luxury"
    terms = [
        questions_answers.experience_kind,
        questions_answers.travel_style,
        questions_answers.trip_organization,
        questions_answers.life_season,
        " ".join(questions_answers.preferred_environments),
        f"{questions_answers.energy_level} energy",
        budget_tier,
        "wellness restorative experiences",
    ]
    return " ".join(str(term).strip() for term in terms if str(term).strip())


def _fetch_attraction_dataset(city_name: str, profile_search_query: str = "") -> list[dict]:
    """Fetch all relevant attractions once for the whole itinerary."""
    try:
        results = get_detailed_tourist_places.invoke({
            "location_name": city_name,
            "search_query": profile_search_query or None,
        })
        if not results or _is_tool_error_list(results):
            return []
        return results
    except Exception:
        return []


def _activity_is_meal(activity: dict) -> bool:
    name = (activity.get("activity_name") or "").lower()
    return any(meal.lower() in name for meal in _MEAL_SCHEDULE)


def _seed_used_place_keys(existing_plan: list | None, exclude_day: int | None = None) -> set[str]:
    used_place_keys = set()
    for day in _dump_tour_plan(existing_plan or []):
        if exclude_day is not None and day.get("day") == exclude_day:
            continue
        for activity in day.get("activities", []):
            if _activity_is_meal(activity):
                continue
            key = _place_key({
                "name": activity.get("activity_name", ""),
                "address": activity.get("activity_address", ""),
            })
            if key:
                used_place_keys.add(key)
    return used_place_keys


def _enrich_activities(
    tour_plan: list,
    city_name: str,
    existing_plan: list | None = None,
    day_to_regenerate: int | None = None,
    profile_search_query: str = "",
) -> list:
    """Enrich activities from one shared, profile-led dataset and avoid repeats."""
    attraction_dataset = _fetch_attraction_dataset(city_name, profile_search_query)
    used_place_keys = _seed_used_place_keys(existing_plan, day_to_regenerate)
    enriched_plan = []
    for day in tour_plan:
        enriched_day = {
            "day": day.get("day"),
            "activities": [],
        }
        for activity in day.get("activities", []):
            if _activity_is_meal(activity):
                continue
            activity_name = activity.get("activity_name", "")
            activity_location = activity.get("activity_location", "")
            verified_name = activity_name
            verified_address = "N/A"
            verified_photos = []
            best_match = _find_best_match(
                attraction_dataset,
                activity_name,
                activity_location,
                used_place_keys=used_place_keys,
            )
            if best_match:
                verified_name = best_match.get("name", activity_name)
                verified_address = best_match.get("address", "N/A")
                verified_photos = _clean_photos(best_match.get("photos", []))
                match_key = _place_key(best_match)
                if match_key:
                    used_place_keys.add(match_key)
            enriched_activity = {
                "activity_name": verified_name,
                "activity_description": activity.get("activity_description", ""),
                "activity_location": activity.get("activity_location", ""),
                "activity_address": verified_address,
                "activity_image": verified_photos,
                "activity_time": activity.get("activity_time", ""),
                "activity_cost": activity.get("activity_cost", 0),
                "distance_from_previous_km": None,
            }
            enriched_day["activities"].append(enriched_activity)
        enriched_plan.append(enriched_day)
    return enriched_plan


def _find_best_match(
    results: list,
    activity_name: str,
    location_hint: str = "",
    used_place_keys: set[str] | None = None,
) -> dict | None:
    """Find the best unused place for an activity, falling back only if necessary."""
    if not results:
        return None
    used_place_keys = used_place_keys or set()
    activity_lower = _normalize_place_text(activity_name)
    location_lower = _normalize_place_text(location_hint)
    scored = []
    for place in results:
        key = _place_key(place)
        name = _normalize_place_text(place.get("name", ""))
        address = _normalize_place_text(place.get("address", ""))
        score = 0
        if activity_lower == name:
            score += 100
        elif activity_lower and activity_lower in name:
            score += 50
        elif name and name in activity_lower:
            score += 35
        activity_tokens = set(activity_lower.split())
        name_tokens = set(name.split())
        if activity_tokens and name_tokens:
            score += len(activity_tokens & name_tokens) * 6
        if location_lower and (location_lower in address or location_lower in name):
            score += 20
        already_used = key in used_place_keys
        scored.append((already_used, score, place))
    unused_matches = [item for item in scored if not item[0]]
    candidates = unused_matches or scored
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][2] if candidates else None


def _start_minutes(time_range: str) -> int | None:
    match = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)", time_range or "", re.IGNORECASE)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    suffix = match.group(3).upper()
    if suffix == "PM" and hour != 12:
        hour += 12
    elif suffix == "AM" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _choose_anchor(activities: list, meal_name: str, hotel_address: str, city_name: str) -> str:
    real_activities = [activity for activity in activities if not _activity_is_meal(activity)]
    if not real_activities:
        return hotel_address or city_name
    if meal_name == "Breakfast":
        anchor = real_activities[0]
    elif meal_name == "Dinner":
        anchor = real_activities[-1]
    else:
        anchor = min(
            real_activities,
            key=lambda activity: abs((_start_minutes(activity.get("activity_time", "")) or 720) - 720),
        )
    return (
        anchor.get("activity_address")
        if anchor.get("activity_address") and anchor.get("activity_address") != "N/A"
        else anchor.get("activity_location")
        or hotel_address
        or city_name
    )


def _find_restaurant_for_meal(
    anchor_location: str,
    meal_name: str,
    used_restaurant_keys: set[str],
    city_name: str,
) -> dict:
    try:
        restaurants = get_nearby_restaurants.invoke({
            "location_name": anchor_location or city_name,
            "meal_type": meal_name.lower(),
        })
        if restaurants and not _is_tool_error_list(restaurants):
            for restaurant in restaurants:
                key = _place_key(restaurant)
                if key and key not in used_restaurant_keys:
                    used_restaurant_keys.add(key)
                    return restaurant
            restaurant = restaurants[0]
            key = _place_key(restaurant)
            if key:
                used_restaurant_keys.add(key)
            return restaurant
    except Exception:
        pass
    fallback = {
        "name": f"{meal_name} stop",
        "address": anchor_location or city_name,
        "photos": [],
    }
    used_restaurant_keys.add(_place_key(fallback))
    return fallback


def _meal_activity(meal_name: str, restaurant: dict, anchor_location: str) -> dict:
    time_window, cost = _MEAL_SCHEDULE[meal_name]
    restaurant_name = restaurant.get("name") or f"{meal_name} stop"
    address = restaurant.get("address") or anchor_location or "N/A"
    return {
        "activity_name": f"{meal_name} at {restaurant_name}",
        "activity_description": f"A convenient {meal_name.lower()} stop near the day's planned route.",
        "activity_location": restaurant_name,
        "activity_address": address,
        "activity_image": _clean_photos(restaurant.get("photos", [])),
        "activity_time": time_window,
        "activity_cost": cost,
        "distance_from_previous_km": None,
    }


def _add_daily_meals(tour_plan: list, hotel_address: str, city_name: str) -> list:
    used_restaurant_keys = set()
    for day in tour_plan:
        activities = [activity for activity in day.get("activities", []) if not _activity_is_meal(activity)]
        meal_activities = []
        for meal_name in _MEAL_SCHEDULE:
            anchor = _choose_anchor(activities, meal_name, hotel_address, city_name)
            restaurant = _find_restaurant_for_meal(anchor, meal_name, used_restaurant_keys, city_name)
            meal_activities.append(_meal_activity(meal_name, restaurant, anchor))
        day["activities"] = sorted(
            [*activities, *meal_activities],
            key=lambda activity: _start_minutes(activity.get("activity_time", "")) or 24 * 60,
        )
    return tour_plan


def _merge_tour_plan_days(existing_plan: list, replacement_days: list) -> list:
    replacement_by_day = {day.get("day"): day for day in replacement_days}
    merged = []
    replaced_days = set()
    for day in _dump_tour_plan(existing_plan):
        day_number = day.get("day")
        if day_number in replacement_by_day:
            merged.append(replacement_by_day[day_number])
            replaced_days.add(day_number)
        else:
            merged.append(day)
    for day in replacement_days:
        if day.get("day") not in replaced_days:
            merged.append(day)
    merged.sort(key=lambda day: day.get("day") or 0)
    return merged


def _calculate_distances(tour_plan: list, hotel_address: str) -> list:
    """
    For each day, calculate real distances using calculate_distance_routes_api:
    - First activity: from hotel address to that activity's real address
    - Every subsequent activity: from previous activity's real address to current
    - Chain resets at the start of each new day (back to hotel)
    If a tool lookup fails, distance_from_previous_km stays None.
    """
    for day in tour_plan:
        activities = day.get("activities", [])
        previous_address = hotel_address
        for activity in activities:
            current_address = activity.get("activity_address", "N/A")
            if current_address and current_address != "N/A":
                try:
                    distance_result = calculate_distance_routes_api.invoke({
                        "origin_address": previous_address,
                        "destination_address": current_address,
                    })
                    if "error" not in distance_result:
                        activity["distance_from_previous_km"] = distance_result.get("distance_km")
                    else:
                        activity["distance_from_previous_km"] = None
                except Exception:
                    activity["distance_from_previous_km"] = None
            else:
                activity["distance_from_previous_km"] = None
            # Update previous_address for chaining (use tool-verified address even if N/A)
            previous_address = current_address if current_address and current_address != "N/A" else previous_address
    return tour_plan


def _check_budget(
    tour_plan: list,
    hotel: dict,
    num_nights: int,
    total_budget: float,
) -> tuple:
    """
    Calculate total cost and verify it's within budget.
    Total cost = (hotel price_per_night -- num_nights) + sum of all activity costs.
    Returns (total_cost, is_within_budget).
    """
    # Calculate hotel total
    hotel_cost_per_night = _estimate_hotel_cost(hotel)
    hotel_total = hotel_cost_per_night * num_nights
    # Sum all activity costs
    activities_total = 0.0
    for day in tour_plan:
        for activity in day.get("activities", []):
            activities_total += activity.get("activity_cost", 0)
    total_cost = hotel_total + activities_total
    is_within_budget = total_cost <= total_budget
    return total_cost, is_within_budget


def _build_final_response(
    hotel: dict,
    tour_plan: list,
    total_cost: float,
    packing_tips: str,
    travel_tips: str,
    activity_session_id: str,
    city_name: str,
    source: str,
) -> dict:
    """Build the final response matching the required schema."""
    return {
        "activity_session_id": activity_session_id,
        "city": city_name,
        "stay": StayInfo(
            name=hotel.get("name", "N/A"),
            address=hotel.get("address", "N/A"),
            rating=hotel.get("rating", 0.0),
            price_level=hotel.get("price_level", "NOT_AVAILABLE"),
            photos=_clean_photos(hotel.get("photos", [])),
            coords=hotel.get("coords"),
        ),
        "tour_plan": tour_plan,
        "total_cost_estimate": round(total_cost, 2),
        "packing_tips": packing_tips,
        "travel_tips": travel_tips,
        "source": source,
    }

# ==================== CITY SUGGESTION FLOW ====================

@router.post("/get_suggested_city")


async def get_suggested_city(input_data: InputData):
    """
    GENERATE: First time user answers questions -> get city suggestions.
    - Stores Q&A and city suggestion in session.
    - Returns session_id for future regenerate calls.
    """
    try:
        # Persist the legacy top-level region inside the 12-answer profile so
        # regeneration and itinerary generation retain the same hard constraint.
        questions_answers = input_data.questions_answers
        if not questions_answers.preferred_region and input_data.preferred_destinations:
            questions_answers = questions_answers.model_copy(
                update={"preferred_region": input_data.preferred_destinations}
            )
        prompt = PromptGenerator.gen_city_suggestion_prompt(
            questions_answers=questions_answers,
            preferred_destinations=input_data.preferred_destinations,
            hope_of_this_trip=input_data.hope_of_this_trip,
        )
        # Call AI to get city suggestions
        response_text = get_ai_response(prompt)
        response = _parse_ai_response(response_text)
        # Enrich LLM suggestions with real data from get_cityinfo tool
        raw_cities = response.get("suggested_cities", [])
        enriched_cities = _enrich_city_suggestions(raw_cities)
        # Replace LLM-only output with enriched version in the response dict
        response["suggested_cities"] = enriched_cities
        # Create session and store Q&A + enriched suggestions
        session = CitySessionStore.create(
            questions_answers=questions_answers,
            suggested_cities=enriched_cities,
            response=response,
        )
        return {
            "session_id": session.session_id,
            "suggested_cities": session.suggested_cities,
            "response": session.response,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.post("/regenerate_suggested_city")


async def regenerate_suggested_city(regenerate_data: RegenerateInputData):
    """
    REGENERATE: User wants different city suggestions (same Q&A, new suggestions).
    - Retrieves previous Q&A from session.
    - Calls AI again (optionally excluding previous suggestions).
    - Overwrites suggested_cities in session.
    - Keeps Q&A history intact.
    """
    # Fetch existing session
    session = CitySessionStore.get(regenerate_data.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        # Build regenerate prompt using stored Q&A
        prompt = PromptGenerator.regenerate_city_suggestion_prompt(
            questions_answers=session.questions_answers,
            previous_suggestions=session.suggested_cities,
            user_instruction=regenerate_data.user_instruction,
        )
        # Call AI for new suggestions
        response_text = get_ai_response(prompt)
        generated_response = _parse_ai_response(response_text)
        # Enrich new LLM suggestions with real data from get_cityinfo tool
        raw_cities = generated_response.get("suggested_cities", [])
        enriched_cities = _enrich_city_suggestions(raw_cities)
        generated_response["suggested_cities"] = enriched_cities
        # Merge new suggestions into response
        response = _merge_regenerated_field(
            previous_response=session.response,
            generated_response=generated_response,
            update_field_name="suggested_cities",
        )
        # Update session with new suggestions
        updated_session = CitySessionStore.update_response(
            session_id=regenerate_data.session_id,
            response=response,
            update_field_name="suggested_cities",
            user_instruction=regenerate_data.user_instruction or "",
        )
        if updated_session is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return {
            "session_id": updated_session.session_id,
            "suggested_cities": updated_session.suggested_cities,
            "response": updated_session.response,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

# ==================== ACTIVITY/TOUR PLAN FLOW ====================

@router.post("/get_tour_plan")


async def get_tour_plan(request_data: TourPlanRequestData):
    """
    GENERATE: First time -> create day-wise activity plan for selected city.
    Two-step pattern:
    1. LLM proposes activity names, descriptions, areas, times, costs
    2. Tool enrichment: hotel lookup, address/photos enrichment, distance calculation, budget check
    Returns: stay, tour_plan (with enriched addresses/images/distances), total_cost_estimate.
    """
    # Fetch parent city session
    city_session = CitySessionStore.get(request_data.session_id)
    if city_session is None:
        raise HTTPException(status_code=404, detail="City session not found.")
    try:
        # Check if activity session already exists for this city (to avoid re-generation)
        activity_session = ActivitySessionStore.get_by_city(
            session_id=request_data.session_id,
            city_name=request_data.selected_city,
        )
        if activity_session is not None:
            # Activities already generated -> return cached version
            return {
                "activity_session_id": activity_session.activity_session_id,
                "city": activity_session.city,
                "stay": activity_session.stay,
                "tour_plan": activity_session.tour_plan,
                "total_cost_estimate": activity_session.total_cost_estimate,
                "packing_tips": activity_session.packing_tips,
                "travel_tips": activity_session.travel_tips,
                "source": "cached",
            }
        # === STEP 1: LLM proposes activities (names, descriptions, areas, times, costs only) ===
        prompt = PromptGenerator.gen_tour_plan_prompt(
            questions_answers=city_session.questions_answers,
            selected_city=request_data.selected_city,
            trip_length_days=city_session.questions_answers.trip_length_days,
        )
        response_text = get_ai_response(prompt)
        response = _parse_ai_response(response_text)
        llm_tour_plan = response.get("tour_plan", [])
        packing_tips = response.get("packing_tips", "")
        travel_tips = response.get("travel_tips", "")
        # === STEP 2a: Tool - Find hotel ===
        budget = city_session.questions_answers.effective_total_budget
        num_nights = city_session.questions_answers.trip_length_days
        city_name = request_data.selected_city
        profile_search_query = _build_profile_search_context(city_session.questions_answers)
        hotel = _find_hotel(city_name, budget, num_nights, profile_search_query)
        hotel["photos"] = _clean_photos(hotel.get("photos", []))
        hotel_address = hotel.get("address", f"City Center, {city_name}")
        # === STEP 2b: Tool - Enrich activities with real addresses & photos ===
        enriched_plan = _enrich_activities(
            llm_tour_plan, city_name, profile_search_query=profile_search_query
        )
        enriched_plan = _add_daily_meals(enriched_plan, hotel_address, city_name)
        # === STEP 2c: Tool - Calculate real distances ===
        enriched_plan = _calculate_distances(enriched_plan, hotel_address)
        # === STEP 5: Budget check ===
        total_cost, is_within_budget = _check_budget(
            enriched_plan, hotel, num_nights, budget
        )
        # If over budget, try to find a cheaper hotel
        if not is_within_budget:
            # Try cheaper hotels
            try:
                all_hotels = get_google_hotels_sorted_by_rating.invoke({
                    "location_name": city_name,
                    "search_query": profile_search_query,
                })
                if all_hotels and "error" not in all_hotels[0]:
                    # Sort by estimated price ascending
                    all_hotels_with_price = [
                        (h, _estimate_hotel_cost(h) * num_nights)
                        for h in all_hotels
                    ]
                    all_hotels_with_price.sort(key=lambda x: x[1])
                    for cheaper_hotel, _ in all_hotels_with_price:
                        test_cost, test_budget = _check_budget(
                            enriched_plan, cheaper_hotel, num_nights, budget
                        )
                        if test_budget:
                            hotel = cheaper_hotel
                            hotel["photos"] = _clean_photos(hotel.get("photos", []))
                            hotel_address = hotel.get("address", f"City Center, {city_name}")
                            # Recalculate distances since hotel changed
                            enriched_plan = _calculate_distances(enriched_plan, hotel_address)
                            total_cost = test_cost
                            is_within_budget = True
                            break
            except Exception:
                pass
        # Replace total_cost_estimate in response with actual hotel+activities total
        response["total_cost_estimate"] = round(total_cost, 2)
        # === STEP 6: Store in session ===
        # Create new activity session with enriched data
        activity_session = ActivitySessionStore.create(
            parent_session_id=request_data.session_id,
            city_name=request_data.selected_city,
            tour_plan=enriched_plan,
            response=response,
            stay_data=hotel,
            total_cost_estimate=round(total_cost, 2),
            packing_tips=packing_tips,
            travel_tips=travel_tips,
        )
        return _build_final_response(
            hotel=hotel,
            tour_plan=enriched_plan,
            total_cost=total_cost,
            packing_tips=packing_tips,
            travel_tips=travel_tips,
            activity_session_id=activity_session.activity_session_id,
            city_name=city_name,
            source="generated",
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

@router.post("/regenerate_tour_plan")


async def regenerate_tour_plan(regenerate_data: RegenerateActivityInputData):
    """
    REGENERATE: User wants different day-wise activities (same city, new plan).
    Same two-step pattern as generate:
    1. LLM proposes new activity names/descriptions/areas/times/costs
    2. Tool enrichment: address/photos lookup, distance recalculation, budget re-check
    """
    # Fetch activity session
    activity_session = ActivitySessionStore.get(regenerate_data.activity_session_id)
    if activity_session is None:
        raise HTTPException(status_code=404, detail="Activity session not found.")
    # Fetch parent city session for Q&A
    city_session = CitySessionStore.get(activity_session.parent_session_id)
    if city_session is None:
        raise HTTPException(status_code=404, detail="Parent city session not found.")
    try:
        # === STEP 1: LLM proposes new activities ===
        prompt = PromptGenerator.regenerate_tour_plan_prompt(
            questions_answers=city_session.questions_answers,
            city_name=activity_session.city,
            current_tour_plan=activity_session.tour_plan,
            day_to_regenerate=regenerate_data.day_to_regenerate,
            user_instruction=regenerate_data.user_instruction,
        )
        response_text = get_ai_response(prompt)
        generated_response = _parse_ai_response(response_text)
        llm_tour_plan = generated_response.get("tour_plan", [])
        # === STEP 2: Tool enrichment ===
        city_name = activity_session.city
        budget = city_session.questions_answers.effective_total_budget
        num_nights = city_session.questions_answers.trip_length_days
        profile_search_query = _build_profile_search_context(city_session.questions_answers)
        # Reuse the existing hotel from the stored response if available
        hotel_data = activity_session.stay
        if hotel_data:
            hotel = {
                "name": hotel_data.name,
                "address": hotel_data.address,
                "rating": hotel_data.rating,
                "price_level": hotel_data.price_level,
                "photos": hotel_data.photos,
                "coords": hotel_data.coords,
            }
        else:
            hotel = _find_hotel(city_name, budget, num_nights, profile_search_query)
        hotel["photos"] = _clean_photos(hotel.get("photos", []))
        hotel_address = hotel.get("address", f"City Center, {city_name}")
        # Enrich activities with real data
        enriched_plan = _enrich_activities(
            llm_tour_plan,
            city_name,
            existing_plan=activity_session.tour_plan,
            day_to_regenerate=regenerate_data.day_to_regenerate,
            profile_search_query=profile_search_query,
        )
        enriched_plan = _add_daily_meals(enriched_plan, hotel_address, city_name)
        # Calculate distances for the regenerated days, then merge if needed.
        enriched_plan = _calculate_distances(enriched_plan, hotel_address)
        full_tour_plan = (
            _merge_tour_plan_days(activity_session.tour_plan, enriched_plan)
            if regenerate_data.day_to_regenerate is not None
            else enriched_plan
        )
        # Budget check
        total_cost, is_within_budget = _check_budget(
            full_tour_plan, hotel, num_nights, budget
        )
        if not is_within_budget:
            try:
                all_hotels = get_google_hotels_sorted_by_rating.invoke({
                    "location_name": city_name,
                    "search_query": profile_search_query,
                })
                if all_hotels and "error" not in all_hotels[0]:
                    all_hotels_with_price = [
                        (h, _estimate_hotel_cost(h) * num_nights)
                        for h in all_hotels
                    ]
                    all_hotels_with_price.sort(key=lambda x: x[1])
                    for cheaper_hotel, _ in all_hotels_with_price:
                        candidate_full_plan = (
                            _merge_tour_plan_days(activity_session.tour_plan, enriched_plan)
                            if regenerate_data.day_to_regenerate is not None
                            else enriched_plan
                        )
                        test_cost, test_budget = _check_budget(
                            candidate_full_plan, cheaper_hotel, num_nights, budget
                        )
                        if test_budget:
                            hotel = cheaper_hotel
                            hotel["photos"] = _clean_photos(hotel.get("photos", []))
                            hotel_address = hotel.get("address", f"City Center, {city_name}")
                            enriched_plan = _calculate_distances(enriched_plan, hotel_address)
                            full_tour_plan = (
                                _merge_tour_plan_days(activity_session.tour_plan, enriched_plan)
                                if regenerate_data.day_to_regenerate is not None
                                else enriched_plan
                            )
                            total_cost = test_cost
                            is_within_budget = True
                            break
            except Exception:
                pass
        generated_response["total_cost_estimate"] = round(total_cost, 2)
        generated_response["tour_plan"] = full_tour_plan
        # Merge enriched tour plan into response
        response = _merge_regenerated_field(
            previous_response=activity_session.response,
            generated_response=generated_response,
            update_field_name="tour_plan",
        )
        # Update activity session with enriched data
        updated_session = ActivitySessionStore.update_response(
            activity_session_id=regenerate_data.activity_session_id,
            response=response,
            day_to_regenerate=regenerate_data.day_to_regenerate,
            user_instruction=regenerate_data.user_instruction or "",
            stay_data=hotel,
            total_cost_estimate=round(total_cost, 2),
        )
        if updated_session is None:
            raise HTTPException(status_code=404, detail="Activity session not found.")
        return _build_final_response(
            hotel=hotel,
            tour_plan=full_tour_plan,
            total_cost=total_cost,
            packing_tips=activity_session.packing_tips if hasattr(activity_session, 'packing_tips') else "",
            travel_tips=activity_session.travel_tips if hasattr(activity_session, 'travel_tips') else "",
            activity_session_id=updated_session.activity_session_id,
            city_name=city_name,
            source="regenerated",
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

# ==================== SESSION MANAGEMENT ====================

@router.get("/session/{session_id}")


async def get_session_details(session_id: str):
    """Get full session details: Q&A, suggestions, and regeneration history."""
    session = CitySessionStore.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session.session_id,
        "questions_answers": session.questions_answers.model_dump(),
        "suggested_cities": [city.model_dump() for city in session.suggested_cities],
        "regeneration_history": session.history,
    }

@router.get("/activity_session/{activity_session_id}")


async def get_activity_session_details(activity_session_id: str):
    """Get full activity session details: city, tour plan, and regeneration history."""
    session = ActivitySessionStore.get(activity_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Activity session not found.")
    return {
        "activity_session_id": session.activity_session_id,
        "parent_session_id": session.parent_session_id,
        "city": session.city,
        "stay": session.stay,
        "tour_plan": [day.model_dump() for day in session.tour_plan],
        "total_cost_estimate": session.total_cost_estimate,
        "packing_tips": session.packing_tips,
        "travel_tips": session.travel_tips,
        "regeneration_history": session.history,
    }

@router.delete("/session/{session_id}")


async def delete_session(session_id: str):
    """Delete a city session and all linked activity sessions."""
    if not CitySessionStore.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    ActivitySessionStore.delete_by_parent(session_id)
    return {"message": "Session and all linked activity sessions deleted successfully."}

@router.delete("/activity_session/{activity_session_id}")


async def delete_activity_session(activity_session_id: str):
    """Delete an activity session (does NOT delete parent city session)."""
    if not ActivitySessionStore.delete(activity_session_id):
        raise HTTPException(status_code=404, detail="Activity session not found.")
    return {"message": "Activity session deleted successfully."}
