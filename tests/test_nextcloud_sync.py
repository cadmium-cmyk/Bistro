import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bistro.nextcloud_sync import NextcloudSyncService

class TestNextcloudSync(unittest.TestCase):

    def test_is_configured(self):
        svc1 = NextcloudSyncService("", "", "")
        self.assertFalse(svc1.is_configured())

        svc2 = NextcloudSyncService("https://cloud.example.com", "user", "pass")
        self.assertTrue(svc2.is_configured())

    def test_get_api_bases(self):
        svc1 = NextcloudSyncService("https://cloud.example.com/", "u", "p")
        bases1 = svc1._get_api_bases()
        self.assertIn("https://cloud.example.com/index.php/apps/cookbook/api/v1", bases1)
        self.assertIn("https://cloud.example.com/apps/cookbook/api/v1", bases1)

        svc2 = NextcloudSyncService("https://cloud.example.com/index.php/apps/cookbook/api/v1", "u", "p")
        bases2 = svc2._get_api_bases()
        self.assertEqual(bases2, ["https://cloud.example.com/index.php/apps/cookbook/api/v1"])

    def test_nc_recipe_to_bistro(self):
        nc_data = {
            "id": "42",
            "name": "Spaghetti Carbonara",
            "recipeCategory": "Pasta",
            "recipeIngredient": ["200g spaghetti", "100g pancetta", "2 eggs"],
            "recipeInstructions": ["Boil pasta.", "Fry pancetta.", "Mix with eggs and cheese."]
        }
        bistro_recipe = NextcloudSyncService.nc_recipe_to_bistro(nc_data)
        self.assertEqual(bistro_recipe["name"], "Spaghetti Carbonara")
        self.assertEqual(bistro_recipe["category"], "Pasta")
        self.assertEqual(bistro_recipe["nc_id"], "42")
        self.assertEqual(len(bistro_recipe["ingredients"]), 3)
        self.assertIn("Boil pasta.\nFry pancetta.", bistro_recipe["instructions"])

    def test_bistro_to_nc_recipe(self):
        bistro_data = {
            "name": "Pancakes",
            "category": "Breakfast",
            "ingredients": ["1 cup flour", "1 cup milk", "1 egg"],
            "instructions": "Mix ingredients.\nCook on skillet.",
            "nc_id": "101"
        }
        nc_payload = NextcloudSyncService.bistro_to_nc_recipe(bistro_data)
        self.assertEqual(nc_payload["name"], "Pancakes")
        self.assertEqual(nc_payload["recipeCategory"], "Breakfast")
        self.assertEqual(nc_payload["id"], "101")
        self.assertEqual(nc_payload["recipeIngredient"], ["1 cup flour", "1 cup milk", "1 egg"])
        self.assertEqual(nc_payload["recipeInstructions"], ["Mix ingredients.", "Cook on skillet."])

    @patch("requests.request")
    def test_connection_success(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.return_value = mock_resp

        svc = NextcloudSyncService("https://cloud.example.com", "user", "pass")
        success, msg = svc.test_connection()
        self.assertTrue(success)
        self.assertIn("Successfully connected", msg)

    @patch("requests.request")
    def test_connection_auth_failure(self, mock_req):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_req.return_value = mock_resp

        svc = NextcloudSyncService("https://cloud.example.com", "user", "badpass")
        success, msg = svc.test_connection()
        self.assertFalse(success)
        self.assertIn("Authentication failed", msg)

    @patch("requests.request")
    def test_two_way_sync(self, mock_req):
        def mock_request_side_effect(method, url, **kwargs):
            resp = MagicMock()
            if method == "GET" and url.endswith("/recipes"):
                resp.status_code = 200
                resp.json.return_value = [
                    {
                        "id": "1",
                        "name": "Remote Soup",
                        "recipeCategory": "Soup",
                        "recipeIngredient": ["Water", "Carrots"],
                        "recipeInstructions": ["Boil water.", "Add carrots."]
                    }
                ]
            elif method == "GET" and "/recipes/1" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "id": "1",
                    "name": "Remote Soup",
                    "recipeCategory": "Soup",
                    "recipeIngredient": ["Water", "Carrots"],
                    "recipeInstructions": ["Boil water.", "Add carrots."]
                }
            elif method == "POST" and url.endswith("/recipes"):
                resp.status_code = 201
                resp.json.return_value = "2"
            else:
                resp.status_code = 404
            return resp

        mock_req.side_effect = mock_request_side_effect

        svc = NextcloudSyncService("https://cloud.example.com", "user", "pass")

        with tempfile.TemporaryDirectory() as tmpdir:
            recipes_file = os.path.join(tmpdir, "my_recipes.json")
            initial_local = [
                {
                    "name": "Local Cake",
                    "category": "Dessert",
                    "ingredients": ["Flour", "Sugar"],
                    "instructions": "Bake cake."
                }
            ]
            with open(recipes_file, "w", encoding="utf-8") as f:
                json.dump(initial_local, f)

            pushed, pulled, updated = svc.sync(recipes_file)

            self.assertEqual(pushed, 1)
            self.assertEqual(pulled, 1)

            with open(recipes_file, "r", encoding="utf-8") as f:
                synced_data = json.load(f)

            self.assertEqual(len(synced_data), 2)
            names = [r["name"] for r in synced_data]
            self.assertIn("Local Cake", names)
            self.assertIn("Remote Soup", names)

            cake = next(r for r in synced_data if r["name"] == "Local Cake")
            self.assertEqual(cake["nc_id"], "2")

if __name__ == "__main__":
    unittest.main()
