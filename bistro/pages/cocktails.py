import json
import os
import threading
import requests
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, GLib, Gdk, GdkPixbuf

from bistro.cookbook import (
    load_all_recipes_from_dir,
    save_recipe_folder,
    delete_recipe_folder,
    sanitize_filename
)

class CocktailPage(Adw.Bin):
    MY_RECIPES_DIR = os.path.join(GLib.get_user_data_dir(), "bistro", "recipes")

    def __init__(self, shopping_list_page=None):
        super().__init__()
        self.shopping_list_page = shopping_list_page
        self.ensure_data_dir()
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

        title = Gtk.Label(label="Find a Drink", css_classes=["title-2", "custom-title"])
        controls.append(title)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(row)

        self.rand_btn = Gtk.Button(icon_name="media-playlist-shuffle-symbolic", tooltip_text="Surprise Me!")
        self.rand_btn.connect("clicked", self.on_random)

        # Search Type
        search_model = Gtk.StringList.new(["Name", "Ingredient"])
        self.search_type = Gtk.DropDown(model=search_model)
        self.search_type.set_valign(Gtk.Align.CENTER)
        row.append(self.search_type)

        entry = Gtk.SearchEntry(placeholder_text="Search cocktails...")
        entry.set_hexpand(True)
        entry.connect("search-changed", self.on_search)
        row.append(entry)
        row.append(self.rand_btn)

        self.spinner = Gtk.Spinner()
        main_box.append(self.spinner)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_vexpand(True)
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

    def ensure_data_dir(self):
        if not os.path.exists(self.MY_RECIPES_DIR):
            os.makedirs(self.MY_RECIPES_DIR, exist_ok=True)

    def load_saved_recipes(self):
        return load_all_recipes_from_dir(self.MY_RECIPES_DIR)

    def is_saved(self, drink_data):
        name = drink_data.get('strDrink') or drink_data.get('name')
        if not name:
            return False, None
        saved = self.load_saved_recipes()
        for r in saved:
            if r.get('name', '').lower() == name.lower():
                return True, r.get('folder_path')
        return False, None

    def on_random(self, btn):
        self.clear_list()
        self.spinner.start()
        btn.set_sensitive(False)
        self.scroll.set_visible(False)
        self.last_query = None
        threading.Thread(target=self.do_fetch, args=("https://www.thecocktaildb.com/api/json/v1/1/random.php", True, None), daemon=True).start()

    def on_search(self, entry):
        q = entry.get_text().strip()
        self.clear_list()

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
            url = f"https://www.thecocktaildb.com/api/json/v1/1/filter.php?i={q}"
        else:
            url = f"https://www.thecocktaildb.com/api/json/v1/1/search.php?s={q}"

        threading.Thread(target=self.do_fetch, args=(url, False, q), daemon=True).start()

    def do_fetch(self, url, is_random, query_used):
        results = []
        seen_ids = set()

        # Local Search (only if not random)
        if not is_random and query_used:
            q_lower = query_used.lower()
            saved_recipes = self.load_saved_recipes()
            for r in saved_recipes:
                name = r.get('name', '').lower()
                cat = (r.get('category') or r.get('recipeCategory') or '').lower()
                if 'cocktail' in cat or 'drink' in cat or q_lower in name:
                    if q_lower in name:
                        results.append(r)
                        if r.get('id'):
                            seen_ids.add(str(r.get('id')))

        # API Fetch
        try:
            r = requests.get(url, timeout=10)
            api_data = r.json().get('drinks')
            if api_data:
                for d in api_data:
                    d_id = str(d.get('idDrink', ''))
                    if d_id not in seen_ids:
                        results.append(d)
        except Exception:
            pass

        if is_random:
            GLib.idle_add(self.rand_btn.set_sensitive, True)

        GLib.idle_add(self.update_ui, results, query_used)

    def update_ui(self, drinks, query_used):
        self.spinner.stop()

        if query_used is not None and query_used != self.last_query:
            return False

        self.scroll.set_visible(True)

        if not drinks:
            self.show_status("No drinks found.")
        else:
            for d in drinks:
                self.results_list.append(self.create_row(d))
        return False

    def create_row(self, data):
        title_text = data.get('strDrink') or data.get('name') or "Unknown"
        category = data.get('strCategory') or data.get('category') or "Cocktails"

        row = Adw.ExpanderRow(title=title_text)
        row.set_use_markup(False)
        row.set_subtitle(category)

        saved, folder_path = self.is_saved(data)
        fav = Gtk.Button(icon_name="starred-symbolic" if saved else "non-starred-symbolic", valign=Gtk.Align.CENTER)
        fav.add_css_class("flat")
        fav.connect("clicked", self.toggle_fav, data)
        row.add_suffix(fav)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        img = Gtk.Picture()
        img.set_size_request(150, 150)
        img.set_content_fit(Gtk.ContentFit.COVER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)
        img.add_css_class("rounded-image")
        box.append(img)

        thumb = data.get('strDrinkThumb')
        if thumb:
            threading.Thread(target=self.load_image, args=(f"{thumb}/preview", img), daemon=True).start()
        elif img_path := data.get('image_path'):
             if os.path.exists(img_path):
                 img.set_filename(img_path)

        is_full = 'strInstructions' in data or 'instructions' in data or ('ingredients' in data and isinstance(data['ingredients'], list))

        if is_full:
            self.populate_details_box(box, data)
        elif 'idDrink' in data:
            spinner = Gtk.Spinner()
            spinner.set_margin_top(12)
            spinner.set_margin_bottom(12)
            box.append(spinner)
            row.connect("notify::expanded", self.on_row_expanded, data['idDrink'], box, spinner)

        row.add_row(box)
        return row

    def on_row_expanded(self, row, param, drink_id, box, spinner):
        if row.get_expanded() and not getattr(row, "loaded", False):
            row.loaded = True
            spinner.start()
            threading.Thread(target=self.fetch_details, args=(drink_id, box, spinner), daemon=True).start()

    def fetch_details(self, drink_id, box, spinner):
        try:
            r = requests.get(f"https://www.thecocktaildb.com/api/json/v1/1/lookup.php?i={drink_id}", timeout=10)
            data = r.json()
            if data and data.get('drinks'):
                details = data['drinks'][0]
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
            for i in range(1, 16):
                if ing := data.get(f"strIngredient{i}"):
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
        if self.shopping_list_page and self.shopping_list_page.add_item(text):
            self.toast_overlay.add_toast(Adw.Toast.new(f"Added '{text}' to list"))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(f"'{text}' is already in list"))

    def toggle_fav(self, btn, data):
        saved, folder_path = self.is_saved(data)
        if saved:
            if folder_path and delete_recipe_folder(folder_path):
                btn.set_icon_name("non-starred-symbolic")
                self.toast_overlay.add_toast(Adw.Toast.new("Removed from Collection"))
            else:
                self.toast_overlay.add_toast(Adw.Toast.new("Failed to remove"))
        else:
            # Save to Nextcloud Cookbook format
            # Ensure category is set
            if 'category' not in data and 'strCategory' in data:
                data['category'] = data['strCategory']
            if not data.get('category'):
                data['category'] = "Cocktails"

            save_recipe_folder(data, self.MY_RECIPES_DIR)
            btn.set_icon_name("starred-symbolic")
            self.toast_overlay.add_toast(Adw.Toast.new("Saved to Collection (Nextcloud format)"))

    def load_image(self, url, widget):
        try:
            r = requests.get(url, timeout=10)
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
