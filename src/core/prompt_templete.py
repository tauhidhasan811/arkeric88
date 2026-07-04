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

REQUIREMENTS:
1. Suggest cities that align with their feeling, energy level, travel style, and environment preferences.
2. Respect budget constraints (${questions_answers.budget_per_person_per_night}/night).
3. Consider trip duration ({questions_answers.trip_length_days} days).
4. Avoid activities they restricted/cannot do.
5. Match the "season of life" they're in emotionally.

RESPONSE FORMAT (JSON ONLY):
{{
    "suggested_cities": [
        {{
            "city_name": "City Name",
            "country_name": "Country",
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

IMPORTANT:
1. Do NOT repeat: {previous_cities}
2. Still match their travel style, budget, and preferences.
3. Consider alternative environments or regions.
4. Respect all their constraints.

RESPONSE FORMAT (JSON ONLY):
{{
    "suggested_cities": [
        {{
            "city_name": "City Name",
            "country_name": "Country",
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
        
        prompt = f"""
You are an expert tour planner. Create a detailed {trip_length_days}-day itinerary for {selected_city}.

USER PROFILE:
{qa_summary}

REQUIREMENTS:
1. Create {trip_length_days} days of activities.
2. Match their travel style: {questions_answers.travel_style}
3. Fit their energy level: {questions_answers.energy_level}
4. Stay within budget: ${questions_answers.budget_per_person_per_night}/night
5. AVOID these activities: {', '.join(questions_answers.activity_restrictions)}
6. Prefer these environments: {', '.join(questions_answers.preferred_environments)}
7. Include time (start - end), location, cost, and brief description for each activity.

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
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>
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

REQUIREMENTS (same as before):
1. Match travel style: {questions_answers.travel_style}
2. Match energy level: {questions_answers.energy_level}
3. Stay within budget: ${questions_answers.budget_per_person_per_night}/night
4. AVOID: {', '.join(questions_answers.activity_restrictions)}
5. Include time, location, cost, and description for each activity.

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
                    "activity_time": "HH:MM AM - HH:MM PM",
                    "activity_cost": <cost in USD>
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