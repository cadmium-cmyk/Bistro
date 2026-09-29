import os
import tempfile
import unittest
import shutil
import urllib.parse
from unittest.mock import patch, MagicMock
from bistro.nextcloud import NextcloudSync
from bistro.cookbook import save_recipe_folder, load_all_recipes_from_dir

class TestNextcloudSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.client = NextcloudSync("https://cloud.example.com", "user", "pass", "Recipes")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("requests.get")
    def test_test_connection_rest_api_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        ok, msg = self.client.test_connection()
        self.assertTrue(ok)
        self.assertIn("REST API", msg)

    @patch("requests.request")
    @patch("requests.get")
    def test_test_connection_webdav_success(self, mock_get, mock_req):
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 404
        mock_get.return_value = mock_get_resp

        mock_req_resp = MagicMock()
        mock_req_resp.status_code = 207
        mock_req.return_value = mock_req_resp

        ok, msg = self.client.test_connection()
        self.assertTrue(ok)
        self.assertIn("WebDAV", msg)

    @patch("requests.request")
    @patch("requests.get")
    def test_test_connection_auth_failure(self, mock_get, mock_req):
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 401
        mock_get.return_value = mock_get_resp

        mock_req_resp = MagicMock()
        mock_req_resp.status_code = 401
        mock_req.return_value = mock_req_resp

        ok, msg = self.client.test_connection()
        self.assertFalse(ok)
        self.assertIn("Authentication failed", msg)

    @patch("requests.post")
    @patch("requests.get")
    def test_sync_rest_api(self, mock_get, mock_post):
        save_recipe_folder({"name": "Local Recipe", "category": "Test"}, self.temp_dir)

        mock_list_resp = MagicMock()
        mock_list_resp.status_code = 200
        mock_list_resp.json.return_value = [
            {"id": "101", "name": "Remote Recipe"}
        ]

        mock_detail_resp = MagicMock()
        mock_detail_resp.status_code = 200
        mock_detail_resp.json.return_value = {
            "name": "Remote Recipe",
            "recipeCategory": "Remote",
            "recipeIngredient": ["Water", "Salt"],
            "recipeInstructions": ["Mix"]
        }

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post.return_value = mock_post_resp

        def get_side_effect(url, **kwargs):
            if "101" in url:
                return mock_detail_resp
            return mock_list_resp

        mock_get.side_effect = get_side_effect

        ok, stats, msg = self.client.sync(local_recipes_dir=self.temp_dir)
        self.assertTrue(ok)
        self.assertEqual(stats["downloaded"], 1)
        self.assertEqual(stats["uploaded"], 1)

        local_recipes = load_all_recipes_from_dir(self.temp_dir)
        names = [r["name"] for r in local_recipes]
        self.assertIn("Remote Recipe", names)
        self.assertIn("Local Recipe", names)

    @patch("requests.put")
    @patch("requests.get")
    @patch("requests.request")
    def test_sync_webdav_with_spaces_in_filename(self, mock_req, mock_get, mock_put):
        # REST API fails
        mock_api_resp = MagicMock()
        mock_api_resp.status_code = 404
        mock_get.return_value = mock_api_resp

        # Create a local recipe with spaces in name
        save_recipe_folder({"name": "Fig Old Fashioned", "category": "Cocktails"}, self.temp_dir)

        xml_content = b"""<?xml version="1.0" encoding="utf-8"?>
        <d:multistatus xmlns:d="DAV:">
            <d:response>
                <d:href>/remote.php/dav/files/user/Recipes/</d:href>
                <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
            </d:response>
        </d:multistatus>"""

        mock_prop_resp = MagicMock()
        mock_prop_resp.status_code = 207
        mock_prop_resp.content = xml_content

        mock_mkcol_resp = MagicMock()
        mock_mkcol_resp.status_code = 201

        def req_side_effect(method, url, **kwargs):
            if method == "PROPFIND":
                return mock_prop_resp
            elif method == "MKCOL":
                return mock_mkcol_resp
            return mock_prop_resp

        mock_req.side_effect = req_side_effect

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 201
        mock_put.return_value = mock_put_resp

        ok, stats, msg = self.client.sync(local_recipes_dir=self.temp_dir)
        self.assertTrue(ok)
        self.assertEqual(stats["uploaded"], 1)

        # Verify MKCOL and PUT calls included URL-encoded folder name
        mkcol_urls = [call.args[1] for call in mock_req.call_args_list if call.args[0] == "MKCOL"]
        put_urls = [call.args[0] for call in mock_put.call_args_list]

        self.assertTrue(any("Fig%20Old%20Fashioned" in url for url in mkcol_urls))
        self.assertTrue(any("Fig%20Old%20Fashioned/recipe.json" in url for url in put_urls))

if __name__ == "__main__":
    unittest.main()
