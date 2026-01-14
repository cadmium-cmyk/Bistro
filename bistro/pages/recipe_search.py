import json
import os
import threading
import requests
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, GLib, Gdk, GdkPixbuf

class RecipeSearchPage(Adw.Bin):
    FAV_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "meals.json")
    MY_RECIPES_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "my_recipes.json")

    def __init__(self, shopping_list_page=None):
        super().__init__()
        self.shopping_list_page = shopping_list_page
        self.ensure_data_dir()
        self.favorites = self.load_favorites_from_disk()
        self.last_query = None
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_child(self.toast_overlay)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        # Controls
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        controls.set_margin_top(24)
        controls.set_margin_bottom(12)
        controls.set_margin_start(24)
        controls.set_margin_end(24)
        main_box.append(controls)
        
        title = Gtk.Label(label="Find a Meal", css_classes=["title-2", "custom-title"])
        controls.append(title)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(row)
        
        self.rand_btn = Gtk.Button(icon_name="media-playlist-shuffle-symbolic", tooltip_text="Surprise Me!")
        self.rand_btn.connect("clicked", self.on_random)
        
        # Search Type
        search_model = Gtk.StringList.new(["Name", "Ingredient", "Category"])
        self.search_type = Gtk.DropDown(model=search_model)
        self.search_type.set_valign(Gtk.Align.CENTER)
        row.append(self.search_type)

        entry = Gtk.SearchEntry(placeholder_text="Search recipes...")
        entry.set_hexpand(True)
        entry.connect("search-changed", self.on_search)
        row.append(entry)
        row.append(self.rand_btn)

        # Removed Favorites button as it is moved to Collection page

        self.spinner = Gtk.Spinner()
        main_box.append(self.spinner)
        
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_vexpand(True)
        # Hide results initially
        self.scroll.set_visible(False) 
        main_box.append(self.scroll)

        # Status Page for empty state
        self.status_page = Adw.StatusPage()
        self.status_page.set_title("Search to get started")
        self.status_page.set_icon_name("system-search-symbolic")
        self.status_page.set_vexpand(True)
        main_box.append(self.status_page)
        
        self.results_list = Gtk.ListBox()
        self.results_list.add_css_class("boxed-list")
        self.results_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.results_list.set_margin_top(12)
        self.results_list.set_margin_bottom(24)
        self.results_list.set_margin_start(24)
        self.results_list.set_margin_end(24)
        
        clamp = Adw.Clamp()
        clamp.set_child(self.results_list)
        self.scroll.set_child(clamp)

    def load_favorites_from_disk(self):
        # 1. Try user file
        if os.path.exists(self.FAV_FILE):
            try:
                with open(self.FAV_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # 2. Try default file in pkgdatadir
        try:
            # base_path: .../bistro/pages/recipe_search.py -> .../bistro/pages
            # root: .../bistro
            # pkgdatadir (installed): .../
            base = os.path.dirname(os.path.abspath(__file__))
            default_file = os.path.join(base, "..", "..", "meals.json")
            if os.path.exists(default_file):
                with open(default_file, 'r') as f:
                    return json.load(f)
        except:
            pass
            
        return {}

    def save_favorites_to_disk(self):
        try:
            with open(self.FAV_FILE, 'w') as f:
                json.dump(self.favorites, f, indent=4)
        except:
            pass

    def on_random(self, btn):
        self.clear_list()
        self.spinner.start()
        btn.set_sensitive(False)
        self.scroll.set_visible(False)
        # Reset last_query so pending searches are ignored if they return
        self.last_query = None
        threading.Thread(target=self.do_fetch, args=("https://www.themealdb.com/api/json/v1/1/random.php", True, None, None), daemon=True).start()

    def on_search(self, entry):
        q = entry.get_text().strip()
        self.clear_list()
        
        # Update last_query
        self.last_query = q
        
        if not q:
            self.scroll.set_visible(False)
            self.status_page.set_visible(True)
            return
        
        self.status_page.set_visible(False)
        self.spinner.start()
        self.scroll.set_visible(False)
        
        selected = self.search_type.get_selected_item().get_string()
        if selected == "Ingredient":
            url = f"https://www.themealdb.com/api/json/v1/1/filter.php?i={q}"
        elif selected == "Category":
            url = f"https://www.themealdb.com/api/json/v1/1/filter.php?c={q}"
        else:
            url = f"https://www.themealdb.com/api/json/v1/1/search.php?s={q}"

        favorites_copy = self.favorites.copy()
        threading.Thread(target=self.do_fetch, args=(url, False, q, favorites_copy), daemon=True).start()

    def load_my_recipes(self):
        if os.path.exists(self.MY_RECIPES_FILE):
            try:
                with open(self.MY_RECIPES_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def do_fetch(self, url, is_random, query_used, favorites_snapshot=None):
        results = []
        seen_ids = set()

        # 1. Local Search (only if not random)
        if not is_random and query_used and favorites_snapshot is not None:
            q_lower = query_used.lower()
            
            # Search Favorites (Meals)
            for m_id, data in favorites_snapshot.items():
                name = data.get('strMeal', '').lower()
                if q_lower in name:
                    results.append(data)
                    seen_ids.add(m_id)
            
            # Search My Recipes (Custom)
            custom_recipes = self.load_my_recipes()
            for r in custom_recipes:
                name = r.get('name', '').lower()
                if q_lower in name:
                    results.append(r)
        
        # 2. API Fetch
        try:
            r = requests.get(url)
            api_data = r.json().get('meals')
            if api_data:
                for m in api_data:
                    m_id = m.get('idMeal')
                    if m_id not in seen_ids:
                        results.append(m)
        except:
            pass
        
        if is_random:
            GLib.idle_add(self.rand_btn.set_sensitive, True)
        GLib.idle_add(self.update_ui, results, query_used)

    def update_ui(self, meals, query_used):
        self.spinner.stop()
        
        # If this result corresponds to a stale query, ignore it
        if query_used is not None and query_used != self.last_query:
            return False
            
        self.scroll.set_visible(True) # Show results area
        
        if not meals:
            self.show_status("No recipes found.")
        else:
            for m in meals:
                self.results_list.append(self.create_row(m))
        return False

    def ensure_data_dir(self):
        d = os.path.dirname(self.FAV_FILE)
        if not os.path.exists(d):
            os.makedirs(d)

    def create_row(self, data):
        title_text = data.get('strMeal') or data.get('name') or "Unknown"
        category = data.get('strCategory') or data.get('category') or "Unknown"
        area = data.get('strArea')
        subtitle = f"{category} ({area})" if area else category
        
        row = Adw.ExpanderRow(title=title_text)
        row.set_use_markup(False)
        row.set_subtitle(subtitle)
        
        m_id = data.get('idMeal')
        if m_id:
            is_fav = m_id in self.favorites
            fav = Gtk.Button(icon_name="starred-symbolic" if is_fav else "non-starred-symbolic", valign=Gtk.Align.CENTER)
            fav.add_css_class("flat")
            fav.connect("clicked", self.toggle_fav, m_id, data)
            row.add_suffix(fav)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Add image here
        img = Gtk.Picture()
        img.set_size_request(150, 150)
        img.set_content_fit(Gtk.ContentFit.COVER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)
        img.add_css_class("rounded-image")
        box.append(img)
        
        thumb = data.get('strMealThumb')
        if thumb:
            threading.Thread(target=self.load_image, args=(f"{thumb}/preview", img), daemon=True).start()
        elif img_path := data.get('image_path'):
             if os.path.exists(img_path):
                 img.set_filename(img_path)

        # Check completeness
        is_full = 'strInstructions' in data or 'instructions' in data or ('ingredients' in data and isinstance(data['ingredients'], list))
        
        if is_full:
            self.populate_details_box(box, data)
        else:
            # Lazy loading
            spinner = Gtk.Spinner()
            spinner.set_margin_top(12)
            spinner.set_margin_bottom(12)
            box.append(spinner)
            row.connect("notify::expanded", self.on_row_expanded, data['idMeal'], box, spinner)

        row.add_row(box)
        return row

    def on_row_expanded(self, row, param, meal_id, box, spinner):
        if row.get_expanded() and not getattr(row, "loaded", False):
            row.loaded = True
            spinner.start()
            threading.Thread(target=self.fetch_details, args=(meal_id, box, spinner), daemon=True).start()

    def fetch_details(self, meal_id, box, spinner):
        try:
            r = requests.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}")
            data = r.json()
            if data and data.get('meals'):
                details = data['meals'][0]
                GLib.idle_add(self.update_row_details, box, spinner, details)
                return
        except Exception as e:
            print(f"Fetch details failed: {e}")
        
        GLib.idle_add(self.update_row_details, box, spinner, None)

    def update_row_details(self, box, spinner, data):
        spinner.stop()
        box.remove(spinner)
        
        if data:
            self.populate_details_box(box, data)
        else:
            box.append(Gtk.Label(label="Failed to load details.", css_classes=["error"]))
        return False

    def populate_details_box(self, box, data):
        instr = data.get('strInstructions') or data.get('instructions') or ''
        if instr:
            box.append(Gtk.Label(label=instr, wrap=True, xalign=0))
        
        ings = []
        if 'ingredients' in data and isinstance(data['ingredients'], list):
            for x in data['ingredients']:
                ings.append(f"• {x}")
        else:
            for i in range(1, 21): # MealDB has up to 20 ingredients
                if ing := data.get(f"strIngredient{i}"):
                    if not ing.strip(): continue
                    meas = (data.get(f"strMeasure{i}") or "").strip()
                    ings.append(f"• {meas} {ing.strip()}")
        
        if ings:
            ing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(ing_box)
            
            for ing_str in ings:
                 text = ing_str.lstrip("• ").strip()
                 
                 row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                 lbl = Gtk.Label(label=f"• {text}", xalign=0, hexpand=True, css_classes=["dim-label"])
                 btn = Gtk.Button(icon_name="list-add-symbolic")
                 btn.add_css_class("flat")
                 btn.set_tooltip_text("Add to Shopping List")
                 if self.shopping_list_page:
                    btn.connect("clicked", self.on_add_to_list, text)
                 else:
                    btn.set_sensitive(False)
                 
                 row_box.append(lbl)
                 row_box.append(btn)
                 ing_box.append(row_box)

    def on_add_to_list(self, btn, text):
        if self.shopping_list_page.add_item(text):
            self.toast_overlay.add_toast(Adw.Toast.new(f"Added '{text}' to list"))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(f"'{text}' is already in list"))

    def toggle_fav(self, btn, m_id, data):
        # Reload favorites to ensure sync? Or assume single threaded usage
        # Ideally we should signal the collection page, but file watch or reload on focus might work
        # For now just update local state and file
        if m_id in self.favorites:
            del self.favorites[m_id]
            btn.set_icon_name("non-starred-symbolic")
            self.toast_overlay.add_toast(Adw.Toast.new("Removed"))
        else:
            self.favorites[m_id] = data
            btn.set_icon_name("starred-symbolic")
            self.toast_overlay.add_toast(Adw.Toast.new("Saved"))
        self.save_favorites_to_disk()

    def load_image(self, url, widget):
        try:
            r = requests.get(url)
            GLib.idle_add(self.set_image_texture, widget, r.content)
        except:
            pass

    def set_image_texture(self, widget, data):
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            widget.set_paintable(Gdk.Texture.new_for_pixbuf(loader.get_pixbuf()))
        except:
            pass
        return False

    def show_status(self, msg):
        self.results_list.append(Gtk.Label(label=msg, margin_top=40, css_classes=["dim-label"]))

    def clear_list(self): 
        while c := self.results_list.get_first_child():
            self.results_list.remove(c)
