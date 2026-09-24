import os
import json
import tempfile
import unittest
import shutil
from bistro.cookbook import (
    load_recipe_folder,
    save_recipe_folder,
    to_nextcloud_format,
    from_nextcloud_format,
    load_all_recipes_from_dir
)

class TestCookbook(unittest.TestCase):
    def test_load_sample_fig_old_fashioned(self):
        sample_path = "/tmp/file_attachments/Fig Old Fashioned"
        if os.path.exists(sample_path):
            recipe = load_recipe_folder(sample_path)
            self.assertIsNotNone(recipe)
            self.assertEqual(recipe["name"], "Fig Old Fashioned")
            self.assertEqual(recipe["category"], "Cocktails")
            self.assertEqual(len(recipe["ingredients"]), 4)
            self.assertEqual(len(recipe["recipeInstructions"]), 4)
            self.assertTrue(recipe["image_path"].endswith("full.jpg"))

    def test_load_recipe_folder_fixture(self):
        temp_dir = tempfile.mkdtemp()
        try:
            folder = os.path.join(temp_dir, "Test Recipe")
            os.makedirs(folder)
            recipe_data = {
                "@context": "http://schema.org",
                "@type": "Recipe",
                "name": "Test Recipe",
                "recipeCategory": "Dessert",
                "recipeIngredient": ["1 cup Sugar", "2 cups Flour"],
                "recipeInstructions": ["Mix ingredients.", "Bake at 350F."]
            }
            with open(os.path.join(folder, "recipe.json"), "w") as f:
                json.dump(recipe_data, f)
            with open(os.path.join(folder, "full.jpg"), "w") as f:
                f.write("dummy image data")

            recipe = load_recipe_folder(folder)
            self.assertIsNotNone(recipe)
            self.assertEqual(recipe["name"], "Test Recipe")
            self.assertEqual(recipe["category"], "Dessert")
            self.assertEqual(len(recipe["ingredients"]), 2)
            self.assertEqual(len(recipe["recipeInstructions"]), 2)
            self.assertTrue(recipe["image_path"].endswith("full.jpg"))
        finally:
            shutil.rmtree(temp_dir)

    def test_to_and_from_nextcloud_format(self):
        data = {
            "name": "Test Cocktail",
            "category": "Drinks",
            "ingredients": ["1 oz Rum", "2 oz Lime"],
            "instructions": "Mix together.\nServe chilled."
        }
        nc = to_nextcloud_format(data)
        self.assertEqual(nc["@type"], "Recipe")
        self.assertEqual(nc["@context"], "http://schema.org")
        self.assertEqual(nc["name"], "Test Cocktail")
        self.assertEqual(nc["recipeCategory"], "Drinks")
        self.assertEqual(nc["recipeIngredient"], ["1 oz Rum", "2 oz Lime"])
        self.assertEqual(nc["recipeInstructions"], ["Mix together.", "Serve chilled."])

        back = from_nextcloud_format(nc)
        self.assertEqual(back["name"], "Test Cocktail")
        self.assertEqual(back["category"], "Drinks")
        self.assertEqual(back["ingredients"], ["1 oz Rum", "2 oz Lime"])
        self.assertEqual(back["instructions"], "Mix together.\n\nServe chilled.")

    def test_save_and_load_recipe_folder(self):
        temp_dir = tempfile.mkdtemp()
        try:
            data = {
                "name": "Simple Mojito",
                "category": "Cocktails",
                "ingredients": ["Mint", "Rum", "Sugar", "Lime"],
                "instructions": "Muddle mint and sugar. Add rum and lime."
            }
            folder_path = save_recipe_folder(data, temp_dir)
            self.assertTrue(os.path.exists(os.path.join(folder_path, "recipe.json")))

            recipes = load_all_recipes_from_dir(temp_dir)
            self.assertEqual(len(recipes), 1)
            self.assertEqual(recipes[0]["name"], "Simple Mojito")
            self.assertEqual(recipes[0]["category"], "Cocktails")
            self.assertEqual(recipes[0]["ingredients"], ["Mint", "Rum", "Sugar", "Lime"])
        finally:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    unittest.main()
