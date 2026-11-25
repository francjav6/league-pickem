"""Regression checks for the Pick'em scoring policy (isolated in-memory database)."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import unittest
from main import Base, engine, SessionLocal, User, Matchup, Pick, calculate_user_week, cumulative_points_through

class ScoringTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user = User(name="Test", pin_hash="unused")
        self.db.add(self.user)
        self.db.flush()
        self.games = [Matchup(week=1, team_a=f"A{i}", team_b=f"B{i}", winner_choice="A") for i in range(7)]
        self.db.add_all(self.games)
        self.db.flush()
    def tearDown(self):
        self.db.close()
    def test_missing_is_neutral(self):
        for i, choice in enumerate(["A", "A", "A", "B", "B"]):
            self.db.add(Pick(user_id=self.user.id, matchup_id=self.games[i].id, choice=choice))
        self.db.flush()
        result = calculate_user_week(self.db, self.user, 1)
        self.assertEqual((result["correct"], result["wrong"], result["missing"], result["points"]), (3, 2, 2, 20))
        self.assertEqual(cumulative_points_through(self.db, self.user, 1), (20, 1))
    def test_no_picks_zero(self):
        result = calculate_user_week(self.db, self.user, 1)
        self.assertEqual(result["points"], 0)
        self.assertEqual(result["missing"], 7)
    def test_wrong_still_penalized(self):
        self.db.add(Pick(user_id=self.user.id, matchup_id=self.games[0].id, choice="B"))
        self.db.flush()
        self.assertEqual(calculate_user_week(self.db, self.user, 1)["points"], -5)
    def test_incomplete_week_not_scored(self):
        self.games[0].winner_choice = None
        self.db.flush()
        self.assertIsNone(calculate_user_week(self.db, self.user, 1))

if __name__ == "__main__":
    unittest.main()
