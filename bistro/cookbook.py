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
        # If instructions are multiline text, split by newline or keep as list of paragraphs/steps
        lines = [line.strip() for line in raw_instructions.split('\n') if line.strip()]
        instructions = lines if lines else ([raw_instructions.strip()] if raw_instructions.strip() else [])
    else:
        instructions = []

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    date_created = data.get('dateCreated') or now_iso
    date_modified = now_iso

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
        "image": data.get('image', ''),
        "imageUrl": data.get('imageUrl', ''),
        "printImage": data.get('printImage', True),
        "nutrition": data.get('nutrition', []),
        "tool": data.get('tool', []),
        "id": str(data.get('id', ''))
    }
    return recipe_json

def from_nextcloud_format(data, folder_path=None):
    """
    Converts Nextcloud Cookbook JSON dict to internal Bistro recipe dict representation.
    Normalizes fields like name, category, ingredients, instructions, image_path, folder_path.
    """
    name = data.get('name') or "Untitled Recipe"
    category = data.get('recipeCategory') or ""

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
        "is_nextcloud": True
    }

def load_recipe_folder(folder_path):
    """
    Loads recipe.json from a Nextcloud Cookbook recipe folder and returns the normalized internal recipe dict.
    """
    recipe_json_path = os.path.join(folder_path, "recipe.json")
    if not os.path.exists(recipe_json_path):
        return None

    with open(recipe_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return from_nextcloud_format(data, folder_path=folder_path)

def load_all_recipes_from_dir(base_dir):
    """
    Scans base_dir for subdirectories containing recipe.json (Nextcloud Cookbook standard).
    Returns a list of normalized internal recipe dicts.
    """
    recipes = []
    if not os.path.exists(base_dir) or not os.path.isdir(base_dir):
        return recipes

    for entry in sorted(os.listdir(base_dir)):
        folder_path = os.path.join(base_dir, entry)
        if os.path.isdir(folder_path):
            recipe = load_recipe_folder(folder_path)
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
    if src_image and os.path.exists(src_image) and os.path.abspath(src_image) != os.path.abspath(os.path.join(folder_path, "full.jpg")):
        ext = os.path.splitext(src_image)[1].lower()
        if not ext:
            ext = ".jpg"
        target_img_name = f"full{ext}"
        dest_path = os.path.join(folder_path, target_img_name)
        try:
            shutil.copy(src_image, dest_path)
        except Exception as e:
            print(f"Failed to copy image to recipe folder: {e}")

    return folder_path
