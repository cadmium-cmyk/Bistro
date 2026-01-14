import json
import os
import threading
import requests
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, GdkPixbuf, Gdk, GLib, Gio

from bistro.pages.add_recipe import AddRecipePage

class CollectionPage(Adw.Bin):
    MY_RECIPES_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "my_recipes.json")
    COCKTAILS_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "cocktails.json")
    MEALS_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "meals.json")

    def __init__(self, shopping_list_page=None):
        super().__init__()
        
        # Load resources locally to ensure icons are available
        base_path = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(base_path, "..", "..", "bistro.gresource")
        
        if os.path.exists(resource_path):
            try:
                resource = Gio.Resource.load(resource_path)
                try:
                    resource._register()
                except:
                    pass
            except Exception as e:
                print(f"Collection: Failed to load resource: {e}")

        # Ensure icon theme path
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        if not "/com/github/cadmiumcmyk/Bistro/icons" in icon_theme.get_resource_path():
             icon_theme.add_resource_path("/com/github/cadmiumcmyk/Bistro/icons")

        self.shopping_list_page = shopping_list_page
        self.filter_text = ""
        self.ensure_data_dir()
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_child(self.toast_overlay)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        # Header
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        controls.set_margin_top(24)
        controls.set_margin_bottom(12)
        controls.set_margin_start(24)
        controls.set_margin_end(24)
        main_box.append(controls)
        
        row_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.append(row_header)

        title = Gtk.Label(label="", css_classes=["title-2", "custom-title"])
        row_header.append(title)

        # Filter Entry
        search_entry = Gtk.SearchEntry(placeholder_text="Filter collection...")
        search_entry.set_hexpand(True)
        search_entry.connect("search-changed", self.on_filter_changed)
        row_header.append(search_entry)
        
        # Add Creation Button
        add_btn = Gtk.Button(label="Create New Recipe", icon_name="list-add-symbolic")
        add_btn.connect("clicked", self.on_add_clicked)
        row_header.append(add_btn)

        # Scrollable Content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.append(scroll)
        
        self.scroll_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.scroll_content.set_margin_top(12)
        self.scroll_content.set_margin_bottom(24)
        self.scroll_content.set_margin_start(24)
        self.scroll_content.set_margin_end(24)
        
        clamp = Adw.Clamp()
        clamp.set_child(self.scroll_content)
        scroll.set_child(clamp)

        self.refresh_all()

    def load_json(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Try default file
        basename = os.path.basename(filename)
        # my_recipes.json doesn't have a default
        if basename == "my_recipes.json":
            return []
            
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            default_file = os.path.join(base, "..", "..", basename)
            if os.path.exists(default_file):
                with open(default_file, 'r') as f:
                    return json.load(f)
        except:
            pass
            
        return {}

    def save_json(self, filename, data):
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except:
            pass

    def on_filter_changed(self, entry):
        self.filter_text = entry.get_text().strip().lower()
        self.refresh_all()

    def refresh_all(self):
        # Clear content
        while c := self.scroll_content.get_first_child():
            self.scroll_content.remove(c)
        
        self.build_my_creations(self.filter_text)
        self.build_cocktails(self.filter_text)
        self.build_meals(self.filter_text)
        
        if not self.scroll_content.get_first_child():
             msg = "No items found." if self.filter_text else "Collection is empty."
             self.scroll_content.append(Gtk.Label(label=msg, css_classes=["dim-label"]))

    def build_my_creations(self, filter_text=""):
        recipes = self.load_json(self.MY_RECIPES_FILE)
        if not recipes:
            return

        visible_count = 0
        group = Adw.PreferencesGroup(title="My Creations")
        
        for i, r in enumerate(recipes):
            if filter_text:
                name = r.get('name', '').lower()
                cat = r.get('category', '').lower()
                if filter_text not in name and filter_text not in cat:
                    continue
            group.add(self.create_custom_row(i, r))
            visible_count += 1
            
        if visible_count > 0:
            self.scroll_content.append(group)

    def ensure_data_dir(self):
        d = os.path.dirname(self.MY_RECIPES_FILE)
        if not os.path.exists(d):
            os.makedirs(d)

    def create_custom_row(self, index, data):
        row = Adw.ExpanderRow(title=data['name'])
        row.set_use_markup(False)
        row.set_subtitle(data.get('category', 'Custom'))
        row.add_prefix(Gtk.Image.new_from_icon_name("document-edit-symbolic"))
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Image
        if img_path := data.get('image_path'):
            if os.path.exists(img_path):
                img = Gtk.Picture.new_for_filename(img_path)
                img.set_size_request(150, 150)
                img.set_content_fit(Gtk.ContentFit.COVER)
                img.set_halign(Gtk.Align.CENTER)
                img.set_valign(Gtk.Align.CENTER)
                img.add_css_class("rounded-image")
                box.append(img)
        
        box.append(Gtk.Label(label=data.get('instructions', ''), wrap=True, xalign=0))
        
        ingredients = data.get('ingredients', [])
        if ingredients:
            ing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(ing_box)
            
            for ing in ingredients:
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                lbl = Gtk.Label(label=f"• {ing}", xalign=0, hexpand=True, css_classes=["dim-label"])
                btn = Gtk.Button(icon_name="list-add-symbolic")
                btn.add_css_class("flat")
                btn.set_tooltip_text("Add to Shopping List")
                if self.shopping_list_page:
                    btn.connect("clicked", self.on_add_to_list, ing)
                else:
                    btn.set_sensitive(False)
                row_box.append(lbl)
                row_box.append(btn)
                ing_box.append(row_box)
        
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(actions_box)

        export_btn = Gtk.Button(label="Export", icon_name="document-save-symbolic")
        export_btn.connect("clicked", self.on_export, data)
        actions_box.append(export_btn)

        del_btn = Gtk.Button(label="Delete", icon_name="user-trash-symbolic")
        del_btn.add_css_class("destructive-action")
        del_btn.set_hexpand(True)
        del_btn.set_halign(Gtk.Align.END)
        del_btn.connect("clicked", self.on_delete_custom, index)
        actions_box.append(del_btn)
        
        row.add_row(box)
        return row

    def on_delete_custom(self, btn, index):
        recipes = self.load_json(self.MY_RECIPES_FILE)
        if 0 <= index < len(recipes):
            del recipes[index]
            self.save_json(self.MY_RECIPES_FILE, recipes)
            self.refresh_all()
            self.toast_overlay.add_toast(Adw.Toast.new("Recipe deleted"))

    def build_cocktails(self, filter_text=""):
        favs = self.load_json(self.COCKTAILS_FILE)
        if not favs:
            return
            
        group = Adw.PreferencesGroup(title="Saved Cocktails")
        visible_count = 0
        
        for d_id, data in favs.items():
            if filter_text:
                name = data.get('strDrink', '').lower()
                cat = data.get('strCategory', '').lower()
                if filter_text not in name and filter_text not in cat:
                    continue
            group.add(self.create_cocktail_row(d_id, data))
            visible_count += 1
            
        if visible_count > 0:
            self.scroll_content.append(group)

    def create_cocktail_row(self, d_id, data):
        row = Adw.ExpanderRow(title=data['strDrink'])
        row.set_use_markup(False)
        row.set_subtitle(data.get('strCategory', 'Unknown'))
        row.add_prefix(Gtk.Image.new_from_icon_name("drinks-symbolic"))
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # Image
        img = Gtk.Picture()
        img.set_size_request(150, 150)
        img.set_content_fit(Gtk.ContentFit.COVER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)
        img.add_css_class("rounded-image")
        box.append(img)
        
        if thumb := data.get('strDrinkThumb'):
            threading.Thread(target=self.load_image, args=(f"{thumb}/preview", img), daemon=True).start()
        
        box.append(Gtk.Label(label=data.get('strInstructions',''), wrap=True, xalign=0))
        
        # Simplified display for collection
        ings = []
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

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(actions_box)

        export_btn = Gtk.Button(label="Export", icon_name="document-save-symbolic")
        export_btn.connect("clicked", self.on_export, data)
        actions_box.append(export_btn)
            
        del_btn = Gtk.Button(label="Unsave", icon_name="user-trash-symbolic")
        del_btn.add_css_class("destructive-action")
        del_btn.set_hexpand(True)
        del_btn.set_halign(Gtk.Align.END)
        del_btn.connect("clicked", self.on_delete_cocktail, d_id)
        actions_box.append(del_btn)
        
        row.add_row(box)
        return row

    def on_delete_cocktail(self, btn, d_id):
        favs = self.load_json(self.COCKTAILS_FILE)
        if d_id in favs:
            del favs[d_id]
            self.save_json(self.COCKTAILS_FILE, favs)
            self.refresh_all()
            self.toast_overlay.add_toast(Adw.Toast.new("Cocktail unsaved"))

    def build_meals(self, filter_text=""):
        favs = self.load_json(self.MEALS_FILE)
        if not favs:
            return
            
        group = Adw.PreferencesGroup(title="Saved Recipes")
        visible_count = 0
        
        for m_id, data in favs.items():
            if filter_text:
                name = data.get('strMeal', '').lower()
                cat = data.get('strCategory', '').lower()
                if filter_text not in name and filter_text not in cat:
                    continue
            group.add(self.create_meal_row(m_id, data))
            visible_count += 1
            
        if visible_count > 0:
            self.scroll_content.append(group)

    def create_meal_row(self, m_id, data):
        title = data.get('strMeal') or "Unknown"
        row = Adw.ExpanderRow(title=title)
        row.set_use_markup(False)
        row.set_subtitle(data.get('strCategory', 'Unknown'))
        row.add_prefix(Gtk.Image.new_from_icon_name("fast-food-symbolic")) # Generic icon
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Image
        img = Gtk.Picture()
        img.set_size_request(150, 150)
        img.set_content_fit(Gtk.ContentFit.COVER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_valign(Gtk.Align.CENTER)
        img.add_css_class("rounded-image")
        box.append(img)
        
        if thumb := data.get('strMealThumb'):
            threading.Thread(target=self.load_image, args=(f"{thumb}/preview", img), daemon=True).start()

        box.append(Gtk.Label(label=data.get('strInstructions',''), wrap=True, xalign=0))
        
        ings = []
        for i in range(1, 21):
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

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(actions_box)

        export_btn = Gtk.Button(label="Export", icon_name="document-save-symbolic")
        export_btn.connect("clicked", self.on_export, data)
        actions_box.append(export_btn)
            
        del_btn = Gtk.Button(label="Unsave", icon_name="user-trash-symbolic")
        del_btn.add_css_class("destructive-action")
        del_btn.set_hexpand(True)
        del_btn.set_halign(Gtk.Align.END)
        del_btn.connect("clicked", self.on_delete_meal, m_id)
        actions_box.append(del_btn)
        
        row.add_row(box)
        return row

    def on_delete_meal(self, btn, m_id):
        favs = self.load_json(self.MEALS_FILE)
        if m_id in favs:
            del favs[m_id]
            self.save_json(self.MEALS_FILE, favs)
            self.refresh_all()
            self.toast_overlay.add_toast(Adw.Toast.new("Meal unsaved"))

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

    def on_export(self, btn, data):
        def save_callback(dialog, result):
            try:
                file = dialog.save_finish(result)
                stream = file.replace(None, False, Gio.FileCreateFlags.NONE, None)
                
                # Construct text
                name = data.get('name') or data.get('strDrink') or data.get('strMeal') or "Recipe"
                category = data.get('category') or data.get('strCategory') or "Unknown"
                
                text = f"Title: {name}\nCategory: {category}\n\nIngredients:\n"
                
                # Ingredients
                if 'ingredients' in data: # Custom
                    for ing in data['ingredients']:
                         text += f"- {ing}\n"
                else: # API
                     for i in range(1, 21):
                        ing = data.get(f"strIngredient{i}")
                        if ing:
                            meas = (data.get(f"strMeasure{i}") or "").strip()
                            text += f"- {meas} {ing.strip()}\n"
                            
                text += f"\nInstructions:\n{data.get('instructions') or data.get('strInstructions') or ''}\n"
                
                stream.write_all(text.encode('utf-8'), None)
                stream.close(None)
                self.toast_overlay.add_toast(Adw.Toast.new("Exported"))
            except Exception as e:
                print(f"Export failed: {e}")
                self.toast_overlay.add_toast(Adw.Toast.new("Export failed"))

        dialog = Gtk.FileDialog()
        name = data.get('name') or data.get('strDrink') or data.get('strMeal') or "recipe"
        safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip()
        dialog.set_initial_name(f"{safe_name}.txt")
        dialog.save(self.get_root(), None, save_callback)

    def on_add_to_list(self, btn, text):
        if self.shopping_list_page.add_item(text):
            self.toast_overlay.add_toast(Adw.Toast.new(f"Added '{text}' to list"))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(f"'{text}' is already in list"))

    def on_add_clicked(self, btn):
        win = self.get_root()
        if hasattr(win, "push_page"):
            page = AddRecipePage(on_save_callback=self.refresh_all)
            win.push_page(page)
        else:
            print("Root window is not UnifiedWindow or missing push_page")
