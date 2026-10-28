import unittest
from types import SimpleNamespace
from datetime import datetime, timezone

from app.routers.users import router, get_me, admin_test
from app.dependencies.auth import get_current_user
from app.schemas import UserResponse


class UserStability(unittest.TestCase):
    def test_profile_route_returns_profile_and_uses_normal_authentication(self):
        route = next(route for route in router.routes if route.path == "/users/me")
        self.assertIs(route.endpoint, get_me)
        self.assertIs(route.dependant.dependencies[0].call, get_current_user)
        user = SimpleNamespace(id=1, name="Test user", email="test@example.com", role="Customer",
                               is_active=True, create_at=datetime.now(timezone.utc))
        profile = UserResponse.model_validate(route.endpoint(user))
        self.assertEqual(profile.id, 1)
        self.assertEqual(profile.role, "Customer")

    def test_admin_route_remains_separate(self):
        route = next(route for route in router.routes if route.path == "/users/admin-test")
        self.assertIs(route.endpoint, admin_test)
        self.assertIsNot(route.dependant.dependencies[0].call, get_current_user)


if __name__ == "__main__":
    unittest.main(verbosity=2)
