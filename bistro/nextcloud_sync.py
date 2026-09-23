import os
import json
import requests

class NextcloudSyncService:
    def __init__(self, server_url="", username="", password=""):
        self.server_url = (server_url or "").strip().rstrip("/")
        self.username = (username or "").strip()
        self.password = (password or "").strip()

    def is_configured(self):
        return bool(self.server_url and self.username and self.password)

    def _get_api_bases(self):
        """Returns list of candidate base API URLs."""
        if not self.server_url:
            return []

        base = self.server_url
        candidates = []
        if "/apps/cookbook/api/v1" in base:
            candidates.append(base)
        else:
            candidates.append(f"{base}/index.php/apps/cookbook/api/v1")
            candidates.append(f"{base}/apps/cookbook/api/v1")
        return candidates

    def _request(self, method, endpoint, **kwargs):
        """Helper to send authenticated requests trying candidate API bases."""
        if not self.is_configured():
            raise ValueError("Nextcloud credentials are not fully configured.")

        kwargs.setdefault("auth", (self.username, self.password))
        kwargs.setdefault("timeout", 15)

        bases = self._get_api_bases()
        last_exception = None

        for base in bases:
            url = f"{base}/{endpoint.lstrip('/')}"
            try:
                response = requests.request(method, url, **kwargs)
                if response.status_code == 404:
                    continue
                return response
            except requests.RequestException as e:
                last_exception = e

        if last_exception:
            raise last_exception
        raise requests.RequestException("404 Not Found from Nextcloud Cookbook endpoints")

    def test_connection(self):
        """Tests connection to Nextcloud Cookbook API."""
        if not self.is_configured():
            return False, "URL, username, and password are required."
        try:
            res = self._request("GET", "recipes")
            if res.status_code == 200:
                return True, "Successfully connected to Nextcloud Cookbook!"
            elif res.status_code in (401, 403):
                return False, "Authentication failed. Check username and password."
            else:
                return False, f"Server returned status {res.status_code}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    @staticmethod
    def nc_recipe_to_bistro(nc_recipe):
        """Converts Nextcloud Cookbook recipe JSON object to Bistro recipe dictionary."""
        raw_instructions = nc_recipe.get("recipeInstructions", "")
        if isinstance(raw_instructions, list):
            instructions_list = []
            for item in raw_instructions:
                if isinstance(item, dict):
                    text = item.get("text", "") or item.get("name", "")
                    if text:
                        instructions_list.append(text)
                elif isinstance(item, str):
                    if item.strip():
                        instructions_list.append(item.strip())
            instructions = "\n".join(instructions_list)
        else:
            instructions = str(raw_instructions or "").strip()

        raw_ingredients = nc_recipe.get("recipeIngredient", [])
        ingredients = []
        if isinstance(raw_ingredients, list):
            for ing in raw_ingredients:
                if isinstance(ing, str) and ing.strip():
                    ingredients.append(ing.strip())
                elif isinstance(ing, dict):
                    ing_str = ing.get("text") or ing.get("name") or ""
                    if ing_str.strip():
                        ingredients.append(ing_str.strip())

        name = nc_recipe.get("name") or "Untitled Recipe"
        category = nc_recipe.get("recipeCategory") or nc_recipe.get("category") or ""
        if isinstance(category, list):
            category = ", ".join(category)

        nc_id = str(nc_recipe.get("id") or "")

        return {
            "name": name,
            "category": str(category),
            "ingredients": ingredients,
            "instructions": instructions,
            "image_path": None,
            "nc_id": nc_id
        }

    @staticmethod
    def bistro_to_nc_recipe(bistro_recipe):
        """Converts Bistro recipe dictionary to Nextcloud Cookbook JSON payload."""
        instructions = bistro_recipe.get("instructions", "")
        if isinstance(instructions, str):
            inst_lines = [line.strip() for line in instructions.split("\n") if line.strip()]
        elif isinstance(instructions, list):
            inst_lines = instructions
        else:
            inst_lines = []

        ingredients = bistro_recipe.get("ingredients", [])
        if not isinstance(ingredients, list):
            ingredients = []

        payload = {
            "name": bistro_recipe.get("name", "Untitled"),
            "recipeCategory": bistro_recipe.get("category", ""),
            "recipeIngredient": ingredients,
            "recipeInstructions": inst_lines if inst_lines else ([instructions] if instructions else []),
            "description": "",
            "recipeYield": 1,
        }
        if bistro_recipe.get("nc_id"):
            payload["id"] = str(bistro_recipe["nc_id"])
        return payload

    def fetch_remote_recipes(self):
        """Fetches all recipes from Nextcloud Cookbook."""
        res = self._request("GET", "recipes")
        if res.status_code != 200:
            raise RuntimeError(f"Failed to fetch recipes: status {res.status_code}")

        data = res.json()

        if isinstance(data, dict) and "recipes" in data:
            stubs = data["recipes"]
        elif isinstance(data, list):
            stubs = data
        else:
            stubs = []

        remote_recipes = []
        for stub in stubs:
            recipe_id = None
            if isinstance(stub, dict):
                recipe_id = stub.get("id")
            elif isinstance(stub, (str, int)):
                recipe_id = stub

            if recipe_id is not None:
                try:
                    detail_res = self._request("GET", f"recipes/{recipe_id}")
                    if detail_res.status_code == 200:
                        detail_data = detail_res.json()
                        remote_recipes.append(detail_data)
                    else:
                        if isinstance(stub, dict) and stub.get("name"):
                            remote_recipes.append(stub)
                except Exception:
                    if isinstance(stub, dict) and stub.get("name"):
                        remote_recipes.append(stub)

        return remote_recipes

    def push_recipe(self, bistro_recipe):
        """Pushes a local Bistro recipe to Nextcloud Cookbook. Returns new/updated nc_id."""
        payload = self.bistro_to_nc_recipe(bistro_recipe)
        nc_id = bistro_recipe.get("nc_id")

        if nc_id:
            res = self._request("PUT", f"recipes/{nc_id}", json=payload)
            if res.status_code in (200, 201, 204):
                return nc_id

        res = self._request("POST", "recipes", json=payload)
        if res.status_code in (200, 201):
            try:
                data = res.json()
                if isinstance(data, (int, str)):
                    return str(data)
                elif isinstance(data, dict):
                    return str(data.get("id") or nc_id)
            except Exception:
                pass
            return str(res.text).strip().strip('"')
        else:
            raise RuntimeError(f"Failed to push recipe '{bistro_recipe.get('name')}': {res.status_code}")

    def sync(self, my_recipes_file):
        """Performs two-way sync with local my_recipes.json file.
        Returns tuple: (pushed_count, pulled_count, updated_count)
        """
        if not self.is_configured():
            raise ValueError("Nextcloud credentials are not configured.")

        local_recipes = []
        if os.path.exists(my_recipes_file):
            try:
                with open(my_recipes_file, 'r', encoding='utf-8') as f:
                    local_recipes = json.load(f)
            except Exception:
                local_recipes = []

        local_by_id = {str(r.get("nc_id")): r for r in local_recipes if r.get("nc_id")}
        local_by_name = {r.get("name", "").lower().strip(): r for r in local_recipes if r.get("name")}

        remote_list = self.fetch_remote_recipes()

        pushed_count = 0
        pulled_count = 0
        updated_count = 0

        remote_ids_seen = set()

        for remote_json in remote_list:
            converted = self.nc_recipe_to_bistro(remote_json)
            nc_id = converted.get("nc_id")
            if nc_id:
                remote_ids_seen.add(nc_id)

            name_key = converted["name"].lower().strip()

            if nc_id and nc_id in local_by_id:
                target = local_by_id[nc_id]
                target["name"] = converted["name"]
                target["category"] = converted["category"]
                target["ingredients"] = converted["ingredients"]
                target["instructions"] = converted["instructions"]
                updated_count += 1
            elif name_key in local_by_name:
                target = local_by_name[name_key]
                target["nc_id"] = nc_id
                target["category"] = converted["category"] or target.get("category", "")
                target["ingredients"] = converted["ingredients"] or target.get("ingredients", [])
                target["instructions"] = converted["instructions"] or target.get("instructions", "")
                local_by_id[nc_id] = target
                updated_count += 1
            else:
                local_recipes.append(converted)
                if nc_id:
                    local_by_id[nc_id] = converted
                local_by_name[name_key] = converted
                pulled_count += 1

        for local_r in local_recipes:
            if not local_r.get("nc_id"):
                try:
                    new_id = self.push_recipe(local_r)
                    if new_id:
                        local_r["nc_id"] = str(new_id)
                        pushed_count += 1
                except Exception as e:
                    print(f"Failed to push local recipe {local_r.get('name')}: {e}")

        os.makedirs(os.path.dirname(my_recipes_file), exist_ok=True)
        with open(my_recipes_file, 'w', encoding='utf-8') as f:
            json.dump(local_recipes, f, indent=4)

        return (pushed_count, pulled_count, updated_count)
