from datetime import date
from pydantic import BaseModel
from typing import List, Optional


# ==================== QUESTION & ANSWER SCHEMA ====================

class QuestionAnswers(BaseModel):
    """User's answers to tour preference questions."""
    # How are you feeling today?
    todays_feeling: str

    # What kind of experience is calling to you?
    experience_kind: str

    # What's your energy like for this trip?
    energy_level: str

    # How do you want to experience this journey?
    travel_style: str

    # How would you like your trip to be organized?
    trip_organization: str

    # Are there any activities you'd like to avoid or can't do?
    activity_restrictions: list[str]

    # Which word best describes the season you're in right now?
    life_season: str

    # What environment speaks to your soul?
    preferred_environments: list[str]

    # Your birthdate
    birthdate: date

    # Total trip budget (covers hotel + all activities for the entire trip)
    total_trip_budget: float

    # How many days are you planning to travel?
    trip_length_days: int


# ==================== CITY SUGGESTION REQUEST/RESPONSE ====================

class InputData(BaseModel):
    """Input for generating city suggestions (initial Q&A flow)."""
    questions_answers: QuestionAnswers
    preferred_destinations: Optional[str] = None  # e.g., "beach", "mountains"
    hope_of_this_trip: str  # e.g., "relaxation", "adventure"


class RegenerateInputData(BaseModel):
    """Input for regenerating city suggestions."""
    session_id: str
    user_instruction: str  # User's preference for regeneration (e.g., "more adventure", "budget options")


# ==================== STAY / HOTEL SCHEMA ====================

class StayInfo(BaseModel):
    """Hotel/resort where the user stays during the trip."""
    name: str
    address: str
    rating: float
    price_level: str
    photos: List[str] = []
    coords: Optional[dict] = None


# ==================== ACTIVITY/TOUR PLAN REQUEST/RESPONSE ====================

class TourPlanActivityInput(BaseModel):
    """Single activity in a day."""
    activity_name: str
    activity_description: str
    activity_location: str
    activity_address: str = "N/A"
    activity_image: List[str] = []
    activity_time: str  # e.g., "9:00 AM - 12:00 PM"
    activity_cost: float = 0.0
    distance_from_previous_km: Optional[float] = None


class TourPlanDayInput(BaseModel):
    """Activities for a single day."""
    day: int
    activities: List[TourPlanActivityInput]


class TourPlanRequestData(BaseModel):
    """Request payload for generating a day-wise tour plan for a chosen city."""
    session_id: str
    selected_city: str


class TourPlanInput(BaseModel):
    """Complete tour plan (all days)."""
    suggested_city: "CitySuggestionInput"
    tour_plan: List[TourPlanDayInput]


class CitySuggestionInput(BaseModel):
    """Suggested city details."""
    city_name: str
    country_name: str
    number_of_days: int
    description: Optional[str] = None
    city_image: List[str] = []
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RegenerateActivityInputData(BaseModel):
    """Input for regenerating activities (tour plan)."""
    activity_session_id: str
    day_to_regenerate: Optional[int] = None  # If None, regenerate entire plan. If int, regenerate only that day.
    user_instruction: str  # e.g., "more budget-friendly activities", "more adventurous Day 2"


# ==================== RESPONSE SCHEMAS ====================

class CitySuggestionResponse(BaseModel):
    """Response after generating city suggestions."""
    session_id: str
    suggested_cities: List[CitySuggestionInput]
    response: dict  # Full AI response (for reference)


class TourPlanResponse(BaseModel):
    """Response after generating tour plan."""
    activity_session_id: str
    city: str
    stay: StayInfo
    tour_plan: List[TourPlanDayInput]
    total_cost_estimate: float = 0.0
    packing_tips: str = ""
    travel_tips: str = ""
    response: dict  # Full AI response (for reference)
    source: str  # "generated" or "cached"


class SessionDetailsResponse(BaseModel):
    """Response when fetching full session details."""
    session_id: str
    questions_answers: dict
    suggested_cities: List[CitySuggestionInput]
    regeneration_history: List[dict]


class ActivitySessionDetailsResponse(BaseModel):
    """Response when fetching full activity session details."""
    activity_session_id: str
    parent_session_id: str
    city: str
    tour_plan: List[TourPlanDayInput]
    regeneration_history: List[dict]