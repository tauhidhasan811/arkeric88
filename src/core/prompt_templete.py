import json
from typing import List, Optional
from app.schemas.city_body import QuestionAnswers, CitySuggestionInput, TourPlanDayInput


class PromptGenerator:
    """Generate prompts for AI to suggest cities and create tour plans."""

    # ==================== CITY SUGGESTION PROMPTS ====================

    @staticmethod
    def gen_city_suggestion_prompt(
        questions_answers: QuestionAnswers,
        preferred_destinations: Optional[str] = None,
        hope_of_this_trip: str = "",
    ) -> str:
        """
        Generate prompt to suggest cities based on user's Q&A.

        First time flow: User answers all questions → AI recommends best cities.
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()

        additional_context = ""
        if preferred_destinations:
            additional_context += f"\nPreferred regions/types: {preferred_destinations}"
        if hope_of_this_trip:
            additional_context += f"\nWhat they hope to achieve: {hope_of_this_trip}"

        prompt = f"""
            You are an expert travel advisor. Based on the user's profile and preferences below, 
            suggest the 3-5 BEST cities/destinations that match their needs.

            USER PROFILE:
            {qa_summary}
            {additional_context}

            {tool_usage_rules}

            REQUIREMENTS:
            1. Suggest cities that align with their feeling, energy level, travel style, and environment preferences.
            2. Respect budget constraints (${questions_answers.budget_per_person_per_night}/night).
            3. Consider trip duration ({questions_answers.trip_length_days} days).
            4. Avoid activities they restricted/cannot do.
            5. Match the "season of life" they're in emotionally.
            6. For each city, provide a representative image URL, its country, and its latitude/longitude coordinates.

            RESPONSE FORMAT (JSON ONLY):
            {{
                "suggested_cities": [
                    {{
                        "city_name": "City Name",
                        "country_name": "Country",
                        "city_image": ["<image URL from tool output>", "<optional second image URL from tool output>"],
                        "latitude": <float>,
                        "longitude": <float>,
                        "number_of_days": <recommended number of days>,
                        "description": "<1-2 sentence explanation of why this city matches their profile>"
                    }}
                ],
                "reasoning": "<Overall reasoning for these suggestions>"
            }}

            Respond ONLY with valid JSON, no preamble.
            """
        return prompt

    @staticmethod
    def regenerate_city_suggestion_prompt(
        questions_answers: QuestionAnswers,
        previous_suggestions: List[CitySuggestionInput],
        user_instruction: str = "",
    ) -> str:
        """
        Generate prompt to get different city suggestions.

        Regenerate flow: Keep Q&A, suggest different cities (exclude previous ones).
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()
        previous_cities = ", ".join([c.city_name for c in previous_suggestions])

        instruction_context = ""
        if user_instruction:
            instruction_context = f"\nUser's additional instruction: {user_instruction}"

        prompt = f"""
You are an expert travel advisor. The user previously received these suggestions:
{previous_cities}

Now, provide 3-5 DIFFERENT cities that still match their profile.

USER PROFILE:
{qa_summary}
{instruction_context}

{tool_usage_rules}

IMPORTANT:
1. Do NOT repeat: {previous_cities}
2. Still match their travel style, budget, and preferences.
3. Consider alternative environments or regions.
4. Respect all their constraints.
5. For each city, provide a representative image URL, its country, and its latitude/longitude coordinates.

RESPONSE FORMAT (JSON ONLY):
{{
    "suggested_cities": [
        {{
            "city_name": "City Name",
            "country_name": "Country",
            "city_image": ["<image URL from tool output>", "<optional second image URL from tool output>"],
            "latitude": <float>,
            "longitude": <float>,
            "number_of_days": <recommended days>,
            "description": "<1-2 sentence explanation>"
        }}
    ],
    "reasoning": "<Why these are good alternatives>"
}}

Respond ONLY with valid JSON, no preamble.
"""
        return prompt

    # ==================== TOUR PLAN / ACTIVITY PROMPTS ====================

    @staticmethod
    def gen_tour_plan_prompt(
        questions_answers: QuestionAnswers,
        selected_city: str,
        trip_length_days: int,
    ) -> str:
        """
        Generate prompt for day-wise activity itinerary.

        Generate flow: User selected a city → AI creates day-by-day activities.
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()

        prompt = f"""
You are an expert tour planner. Create a detailed {trip_length_days}-day itinerary for {selected_city}.

USER PROFILE:
{qa_summary}

{tool_usage_rules}

REQUIREMENTS:
1. Create {trip_length_days} days of activities.
2. Match their travel style: {questions_answers.travel_style}
3. Fit their energy level: {questions_answers.energy_level}
4. Stay within budget: ${questions_answers.budget_per_person_per_night}/night
5. AVOID these activities: {', '.join(questions_answers.activity_restrictions)}
6. Prefer these environments: {', '.join(questions_answers.preferred_environments)}
7. Include time (start - end), location, address, cost, image, and brief description for each activity.
8. DISTANCE CALCULATION RULE (apply within each day separately):
   - The FIRST activity of each day has "distance_from_previous_km": 0 (it is the starting point for that day).
   - Every activity AFTER the first must have its distance calculated from the PREVIOUS activity's location
     to its own location — NOT from the hotel, city center, or day's starting point.
     Example: Day 1 has activities A, B, C, D.
       - A.distance_from_previous_km = 0
       - B.distance_from_previous_km = distance(A → B)
       - C.distance_from_previous_km = distance(B → C)
       - D.distance_from_previous_km = distance(C → D)
   - Each new day restarts this chain at 0 for its first activity.

RESPONSE FORMAT (JSON ONLY):
{{
    "tour_plan": [
        {{
            "day": 1,
            "activities": [
                {{
                    "activity_name": "Activity Name",
                    "activity_description": "What you'll do",
                    "activity_location": "Exact location in city",
                    "activity_address": "Full street address if available",
                    "activity_image": ["<image URL from tool output>", "<optional second image URL from tool output>"],
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>,
                    "distance_from_previous_km": <0 for first activity of the day, otherwise distance from the previous activity>
                }}
            ]
        }}
    ],
    "total_cost_estimate": <estimated total for all days>,
    "packing_tips": "<Brief packing advice for this city>",
    "travel_tips": "<Brief travel advice>"
}}

Respond ONLY with valid JSON, no preamble.
"""
        return prompt

    @staticmethod
    def regenerate_tour_plan_prompt(
        questions_answers: QuestionAnswers,
        city_name: str,
        current_tour_plan: List[TourPlanDayInput],
        day_to_regenerate: Optional[int] = None,
        user_instruction: str = "",
    ) -> str:
        """
        Generate prompt to get different activities.

        Regenerate flow: Keep city, regenerate activities (all or single day).
        """
        qa_summary = PromptGenerator._build_qa_summary(questions_answers)
        tool_usage_rules = PromptGenerator._build_tool_usage_guidance()

        scope = f"Day {day_to_regenerate}" if day_to_regenerate else "the entire itinerary"
        instruction_context = ""
        if user_instruction:
            instruction_context = f"\nUser's request: {user_instruction}"

        current_plan_summary = PromptGenerator._build_plan_summary(current_tour_plan)

        prompt = f"""
You are an expert tour planner. Regenerate activities for {city_name}.
Previously suggested itinerary:
{current_plan_summary}

Now provide DIFFERENT activities for {scope} while keeping the rest the same.

USER PROFILE:
{qa_summary}
{instruction_context}

{tool_usage_rules}

REQUIREMENTS (same as before):
1. Match travel style: {questions_answers.travel_style}
2. Match energy level: {questions_answers.energy_level}
3. Stay within budget: ${questions_answers.budget_per_person_per_night}/night
4. AVOID: {', '.join(questions_answers.activity_restrictions)}
5. Include time, location, address, image, cost, and description for each activity.
6. DISTANCE CALCULATION RULE (apply within each regenerated day separately):
   - The FIRST activity of the day has "distance_from_previous_km": 0.
   - Every activity AFTER the first must have its distance calculated from the PREVIOUS activity's
     location to its own location (chained, not from a fixed origin).
     Example: A.distance_from_previous_km = 0, B = distance(A → B), C = distance(B → C), etc.

RESPONSE FORMAT (JSON ONLY):
{{
    "tour_plan": [
        {{
            "day": <day number>,
            "activities": [
                {{
                    "activity_name": "Different Activity Name",
                    "activity_description": "What you'll do",
                    "activity_location": "Exact location",
                    "activity_address": "Full street address if available",
                    "activity_image": ["<image URL from tool output>", "<optional second image URL from tool output>"],
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>,
                    "distance_from_previous_km": <0 for first activity of the day, otherwise distance from the previous activity>
                }}
            ]
        }}
    ],
    "reasoning": "<Why these are good alternatives>"
}}

Respond ONLY with valid JSON, no preamble.
"""
        return prompt

    # ==================== HELPER METHODS ====================

    @staticmethod
    def _build_tool_usage_guidance() -> str:
        """Return explicit tool-use guidance for image-related travel data."""
        return """
TOOL USAGE FOR IMAGES:
1. When the request needs real place data, attractions, hotels, or routes, call the relevant tool first.
2. Preserve the tool's returned `photos` list as an array of image URLs in the final JSON.
3. Never invent image URLs; only use URLs returned by the tools.
4. For city suggestions, use `get_cityinfo` and put its `photos` list into `city_image`.
5. For activities, attractions, and hotels, use the matching place tool and put its `photos` list into the image field.
"""

    @staticmethod
    def _build_qa_summary(qa: QuestionAnswers) -> str:
        """Build human-readable summary of Q&A."""
        return f"""
- Current feeling: {qa.todays_feeling}
- Desired experience: {qa.experience_kind}
- Energy level: {qa.energy_level}
- Travel style: {qa.travel_style}
- Trip organization preference: {qa.trip_organization}
- Restricted activities: {', '.join(qa.activity_restrictions) if qa.activity_restrictions else 'None'}
- Season of life: {qa.life_season}
- Preferred environments: {', '.join(qa.preferred_environments)}
- Age (from birthdate): {PromptGenerator._calculate_age(qa.birthdate)}
- Budget per night: ${qa.budget_per_person_per_night}
- Trip duration: {qa.trip_length_days} days
"""

    @staticmethod
    def _build_plan_summary(tour_plan: List[TourPlanDayInput]) -> str:
        """Build human-readable summary of current tour plan."""
        summary = ""
        for day_plan in tour_plan:
            summary += f"\nDay {day_plan.day}:\n"
            for activity in day_plan.activities:
                summary += f"  - {activity.activity_name} ({activity.activity_time}) @ {activity.activity_location} (${activity.activity_cost})\n"
        return summary

    @staticmethod
    def _calculate_age(birthdate) -> int:
        """Calculate age from birthdate."""
        from datetime import date
        today = date.today()
        return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))