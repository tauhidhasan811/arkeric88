import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class TravelPlannerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        self.responses = iter([
            '{"suggested_cities":[{"city_name":"Paris","country_name":"France","number_of_days":3,"description":"Romantic"}],"reasoning":"first"}',
            '{"suggested_cities":[{"city_name":"Tokyo","country_name":"Japan","number_of_days":4,"description":"Energetic"}],"reasoning":"second"}',
            '{"tour_plan":[{"day":1,"activities":[{"activity_name":"Museum","activity_description":"Visit","activity_location":"Louvre","activity_time":"10:00","activity_cost":20}]}],"total_cost_estimate":20,"packing_tips":"light","travel_tips":"walk"}',
            '{"tour_plan":[{"day":1,"activities":[{"activity_name":"Cafe","activity_description":"Coffee","activity_location":"Center","activity_time":"11:00","activity_cost":10}]}],"reasoning":"updated"}',
        ])

    def test_city_and_tour_session_flow(self) -> None:
        def fake_ai(prompt: str) -> str:
            return next(self.responses)

        with patch("app.router.city_content_route.get_ai_response", side_effect=fake_ai):
            initial = self.client.post(
                "/get_suggested_city",
                json={
                    "questions_answers": {
                        "todays_feeling": "curious",
                        "experience_kind": "culture",
                        "energy_level": "medium",
                        "travel_style": "slow",
                        "trip_organization": "loose",
                        "activity_restrictions": ["crowds"],
                        "life_season": "exploration",
                        "preferred_environments": ["cities", "parks"],
                        "birthdate": "1990-01-01",
                        "budget_per_person_per_night": 120.0,
                        "trip_length_days": 3,
                    },
                    "preferred_destinations": "europe",
                    "hope_of_this_trip": "relax",
                },
            )
            self.assertEqual(initial.status_code, 200)
            session_id = initial.json()["session_id"]

            regenerated = self.client.post(
                "/regenerate_suggested_city",
                json={"session_id": session_id, "user_instruction": "more energetic"},
            )
            self.assertEqual(regenerated.status_code, 200)
            self.assertEqual(regenerated.json()["suggested_cities"][0]["city_name"], "Tokyo")

            plan = self.client.post(
                "/get_tour_plan",
                json={"session_id": session_id, "selected_city": "Paris"},
            )
            self.assertEqual(plan.status_code, 200)
            self.assertEqual(plan.json()["source"], "generated")

            plan_regenerated = self.client.post(
                "/regenerate_tour_plan",
                json={
                    "activity_session_id": plan.json()["activity_session_id"],
                    "day_to_regenerate": 1,
                    "user_instruction": "more relaxed",
                },
            )
            self.assertEqual(plan_regenerated.status_code, 200)
            self.assertEqual(plan_regenerated.json()["tour_plan"][0]["activities"][0]["activity_name"], "Cafe")

            details = self.client.get(f"/session/{session_id}")
            self.assertEqual(details.status_code, 200)
            self.assertEqual(len(details.json()["suggested_cities"]), 1)


if __name__ == "__main__":
    unittest.main()
