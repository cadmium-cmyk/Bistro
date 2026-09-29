import os
import json
import shutil
from datetime import datetime, timezone

def sanitize_filename(name):
    if not name:
        name = "Recipe"
    return "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip() or "Recipe"

def to_nextcloud_format(data):
    """
    Converts internal recipe dict or raw data to Nextcloud Cookbook JSON schema dict.
    """
    name = data.get('name') or data.get('strDrink') or data.get('strMeal') or "Untitled Recipe"
    category = data.get('recipeCategory') or data.get('category') or data.get('strCategory') or ""
    description = data.get('description') or ""

    # Ingredients
    raw_ingredients = data.get('recipeIngredient') or data.get('ingredients')
    ingredients = []
    if isinstance(raw_ingredients, list):
        ingredients = [str(i).strip() for i in raw_ingredients if str(i).strip()]
    elif isinstance(raw_ingredients, str):
        ingredients = [i.strip() for i in raw_ingredients.split('\n') if i.strip()]
    else:
        # Fallback for API drinks / meals (strIngredient1..20)
        for i in range(1, 21):
            ing = data.get(f"strIngredient{i}")
            if ing and str(ing).strip():
                meas = (data.get(f"strMeasure{i}") or "").strip()
                ingredients.append(f"{meas} {str(ing).strip()}".strip())

    # Instructions
    raw_instructions = data.get('recipeInstructions') or data.get('instructions') or data.get('strInstructions')
    instructions = []
    if isinstance(raw_instructions, list):
        instructions = [str(i).strip() for i in raw_instructions if str(i).strip()]
    elif isinstance(raw_instructions, str):
        lines = [line.strip() for line in raw_instructions.split('\n') if line.strip()]
        instructions = lines if lines else ([raw_instructions.strip()] if raw_instructions.strip() else [])
    else:
        instructions = []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    date_created = data.get('dateCreated') or now_iso
    date_modified = data.get('dateModified') or now_iso

    image_url = data.get('imageUrl') or data.get('strDrinkThumb') or data.get('strMealThumb') or data.get('image', '')
    if isinstance(image_url, list):
        image_url = image_url[0] if image_url else ''

    recipe_json = {
        "@context": "http://schema.org",
        "@type": "Recipe",
        "name": name,
        "description": description,
        "recipeCategory": category,
        "keywords": data.get('keywords', ''),
        "recipeIngredient": ingredients,
        "recipeInstructions": instructions,
        "dateCreated": date_created,
        "dateModified": date_modified,
        "datePublished": data.get('datePublished', None),
        "prepTime": data.get('prepTime', None),
        "cookTime": data.get('cookTime', None),
        "totalTime": data.get('totalTime', None),
        "recipeYield": data.get('recipeYield', 1),
        "url": data.get('url', ''),
        "image": image_url,
        "imageUrl": image_url,
        "printImage": data.get('printImage', True),
        "nutrition": data.get('nutrition', []),
        "tool": data.get('tool', []),
        "id": str(data.get('id') or data.get('idDrink') or data.get('idMeal') or '')
    }
    return recipe_json

def from_nextcloud_format(data, folder_path=None):
    """
    Converts Nextcloud Cookbook JSON dict to internal Bistro recipe dict representation.
    Normalizes fields like name, category, ingredients, instructions, image_path, folder_path.
    """
    name = data.get('name') or "Untitled Recipe"
    category = data.get('recipeCategory') or data.get('category') or ""

    raw_ing = data.get('recipeIngredient', [])
    if isinstance(raw_ing, list):
        ingredients = [str(i).strip() for i in raw_ing if str(i).strip()]
    elif isinstance(raw_ing, str):
        ingredients = [i.strip() for i in raw_ing.split('\n') if i.strip()]
    else:
        ingredients = []

    raw_inst = data.get('recipeInstructions', [])
    if isinstance(raw_inst, list):
        instructions_list = [str(i).strip() for i in raw_inst if str(i).strip()]
        instructions_text = "\n\n".join(instructions_list)
    elif isinstance(raw_inst, str):
        instructions_text = raw_inst.strip()
        instructions_list = [line.strip() for line in raw_inst.split('\n') if line.strip()]
    else:
        instructions_text = ""
        instructions_list = []

    image_path = None
    if folder_path and os.path.isdir(folder_path):
        for img_name in ['full.jpg', 'full.png', 'thumb.jpg', 'thumb.png', 'image.jpg', 'image.png']:
            candidate = os.path.join(folder_path, img_name)
            if os.path.exists(candidate):
                image_path = candidate
                break

    return {
        "name": name,
        "category": category,
        "description": data.get('description', ''),
        "ingredients": ingredients,
        "instructions": instructions_text,
        "recipeInstructions": instructions_list,
        "recipeIngredient": ingredients,
        "recipeCategory": category,
        "image_path": image_path,
        "folder_path": folder_path,
        "raw_schema": data,
        "is_nextcloud": True,
        "id": str(data.get('id', ''))
    }

def load_recipe_folder(folder_path):
    """
    Loads recipe.json from a Nextcloud Cookbook recipe folder and returns the normalized internal recipe dict.
    """
    recipe_json_path = os.path.join(folder_path, "recipe.json")
    if not os.path.exists(recipe_json_path):
        return None

    try:
        with open(recipe_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return from_nextcloud_format(data, folder_path=folder_path)
    except Exception as e:
        print(f"Error loading recipe from {folder_path}: {e}")
        return None

def load_all_recipes_from_dir(base_dir):
    """
    Scans base_dir for subdirectories containing recipe.json (Nextcloud Cookbook standard).
    Supports both flat (base_dir/RecipeName/recipe.json) and category-nested
    (base_dir/Category/RecipeName/recipe.json) directory layouts.
    Returns a list of normalized internal recipe dicts.
    """
    recipes = []
    if not os.path.exists(base_dir) or not os.path.isdir(base_dir):
        return recipes

    for root, dirs, files in os.walk(base_dir):
        if "recipe.json" in files:
            recipe = load_recipe_folder(root)
            if recipe:
                recipes.append(recipe)
    return recipes

def save_recipe_folder(data, base_dir):
    """
    Saves a recipe as a Nextcloud Cookbook recipe folder under base_dir.
    Creates folder <base_dir>/<sanitized_name>/, recipe.json, full.jpg (if image provided).
    Returns path to the recipe folder.
    """
    nc_data = to_nextcloud_format(data)
    folder_name = sanitize_filename(nc_data['name'])
    folder_path = os.path.join(base_dir, folder_name)

    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)

    recipe_json_path = os.path.join(folder_path, "recipe.json")
    with open(recipe_json_path, 'w', encoding='utf-8') as f:
        json.dump(nc_data, f, indent=4)

    # Handle image copying if image_path is in data and exists
    src_image = data.get('image_path')
    if src_image and os.path.exists(src_image):
        ext = os.path.splitext(src_image)[1].lower()
        if not ext:
            ext = ".jpg"
        target_img_name = f"full{ext}"
        dest_path = os.path.join(folder_path, target_img_name)
        if os.path.abspath(src_image) != os.path.abspath(dest_path):
            try:
                shutil.copy(src_image, dest_path)
            except Exception as e:
                print(f"Failed to copy image to recipe folder: {e}")

    return folder_path

def delete_recipe_folder(folder_path):
    """
    Deletes a Nextcloud Cookbook recipe folder from disk.
    """
    if folder_path and os.path.exists(folder_path) and os.path.isdir(folder_path):
        try:
            shutil.rmtree(folder_path)
            return True
        except Exception as e:
            print(f"Failed to delete recipe directory {folder_path}: {e}")
            return False
    return False

def migrate_legacy_storage(base_app_dir):
    """
    Migrates legacy JSON files (my_recipes.json, cocktails.json, meals.json)
    to Nextcloud Cookbook recipe folders under base_app_dir/recipes/.
    Removes legacy files after successful migration.
    """
    recipes_dir = os.path.join(base_app_dir, "recipes")
    os.makedirs(recipes_dir, exist_ok=True)

    # 1. Migrate my_recipes.json
    my_recipes_file = os.path.join(base_app_dir, "my_recipes.json")
    if os.path.exists(my_recipes_file):
        try:
            with open(my_recipes_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if isinstance(items, list):
                for item in items:
                    save_recipe_folder(item, recipes_dir)
            os.remove(my_recipes_file)
        except Exception as e:
            print(f"Error migrating {my_recipes_file}: {e}")

    # 2. Migrate cocktails.json
    cocktails_file = os.path.join(base_app_dir, "cocktails.json")
    if os.path.exists(cocktails_file):
        try:
            with open(cocktails_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if isinstance(items, dict):
                for c_id, item in items.items():
                    save_recipe_folder(item, recipes_dir)
            elif isinstance(items, list):
                for item in items:
                    save_recipe_folder(item, recipes_dir)
            os.remove(cocktails_file)
        except Exception as e:
            print(f"Error migrating {cocktails_file}: {e}")

    # 3. Migrate meals.json
    meals_file = os.path.join(base_app_dir, "meals.json")
    if os.path.exists(meals_file):
        try:
            with open(meals_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
            if isinstance(items, dict):
                for m_id, item in items.items():
                    save_recipe_folder(item, recipes_dir)
            elif isinstance(items, list):
                for item in items:
                    save_recipe_folder(item, recipes_dir)
            os.remove(meals_file)
        except Exception as e:
            print(f"Error migrating {meals_file}: {e}")
