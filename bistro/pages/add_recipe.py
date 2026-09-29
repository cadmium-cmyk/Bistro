import os
import json
import threading
import requests
import shutil
import uuid
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

from bistro.cookbook import save_recipe_folder
from bistro.nextcloud import NextcloudSync

try:
    from recipe_scrapers import scrape_me
except ImportError:
    scrape_me = None

def trigger_auto_sync():
    settings_file = os.path.join(GLib.get_user_data_dir(), "bistro", "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            if settings.get("nc_sync_enabled"):
                local_dir = os.path.join(GLib.get_user_data_dir(), "bistro", "recipes")
                client = NextcloudSync(
                    server_url=settings.get("nc_url", ""),
                    username=settings.get("nc_username", ""),
                    password=settings.get("nc_password", ""),
                    remote_folder=settings.get("nc_folder", "Recipes")
                )
                threading.Thread(target=client.sync, kwargs={"local_recipes_dir": local_dir}, daemon=True).start()
        except Exception as e:
            print(f"Auto-sync error: {e}")

class AddRecipePage(Adw.NavigationPage):
    MY_RECIPES_DIR = os.path.join(GLib.get_user_data_dir(), "bistro", "recipes")

    def __init__(self, on_save_callback=None):
        super().__init__(title="New Recipe", tag="add_recipe")
        self.on_save_callback = on_save_callback
        
        # Toolbar View
        toolbar_view = Adw.ToolbarView()
        self.set_child(toolbar_view)
        
        # Header Bar
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        
        # Save Button
        save_btn = Gtk.Button(label="Save", css_classes=["suggested-action"])
        save_btn.connect("clicked", self.on_save)
        header.pack_end(save_btn)
        
        # Content
        scroll = Gtk.ScrolledWindow()
        toolbar_view.set_content(scroll)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        scroll.set_child(box)

        # Import Section
        if scrape_me:
            import_group = Adw.PreferencesGroup(title="Import from URL")
            box.append(import_group)
            
            self.url_entry = Adw.EntryRow(title="URL")
            import_btn = Gtk.Button(label="Import")
            import_btn.add_css_class("suggested-action")
            import_btn.set_valign(Gtk.Align.CENTER)
            import_btn.connect("clicked", self.on_import)
            self.url_entry.add_suffix(import_btn)
            import_group.add(self.url_entry)
            
            # Progress spinner
            self.spinner = Gtk.Spinner()
            self.url_entry.add_suffix(self.spinner)

        # Fields
        info_group = Adw.PreferencesGroup()
        box.append(info_group)

        self.name_entry = Adw.EntryRow(title="Name")
        info_group.add(self.name_entry)
        
        self.cat_entry = Adw.EntryRow(title="Category")
        info_group.add(self.cat_entry)
        
        # Image selection
        img_group = Adw.PreferencesGroup(title="Image")
        box.append(img_group)
        
        img_row = Adw.ActionRow(title="Recipe Image")
        img_group.add(img_row)
        
        self.selected_image_path = None
        self.img_label = Gtk.Label(label="None selected")
        img_row.add_suffix(self.img_label)
        
        img_btn = Gtk.Button(icon_name="folder-open-symbolic")
        img_btn.add_css_class("flat")
        img_btn.connect("clicked", self.on_select_image)
        img_row.add_suffix(img_btn)
        
        # Ingredients
        self.ing_group = Adw.PreferencesGroup(title="Ingredients")
        box.append(self.ing_group)
        self.ingredient_rows = []

        add_ing_btn = Gtk.Button(label="Add Ingredient", margin_top=4)
        add_ing_btn.connect("clicked", lambda x: self.add_ingredient_row())
        box.append(add_ing_btn)
        
        self.add_ingredient_row()

        # Instructions
        box.append(Gtk.Label(label="Instructions", xalign=0, css_classes=["heading"]))
        
        self.inst_buffer = Gtk.TextBuffer()
        inst_view = Gtk.TextView(buffer=self.inst_buffer)
        inst_view.set_size_request(-1, 200)
        inst_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        frame = Gtk.Frame()
        frame.set_child(inst_view)
        box.append(frame)
        
        self.set_child(None)
        self.toast_overlay = Adw.ToastOverlay()
        self.set_child(self.toast_overlay)
        self.toast_overlay.set_child(toolbar_view)

    def add_ingredient_row(self, text=""):
        row = Adw.EntryRow(title=f"Item {len(self.ingredient_rows) + 1}")
        if text:
            row.set_text(text)
        del_icon = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        del_icon.add_css_class("flat")
        del_icon.connect("clicked", lambda x: self.remove_ing(row))
        row.add_suffix(del_icon)
        self.ing_group.add(row)
        self.ingredient_rows.append(row)

    def remove_ing(self, row):
        self.ing_group.remove(row)
        if row in self.ingredient_rows:
            self.ingredient_rows.remove(row)

    def on_import(self, btn):
        url = self.url_entry.get_text().strip()
        if not url:
            return
            
        btn.set_sensitive(False)
        self.spinner.start()
        threading.Thread(target=self.do_scrape, args=(url, btn), daemon=True).start()

    def do_scrape(self, url, btn):
        try:
            scraper = scrape_me(url)
            title = scraper.title()
            ingredients = scraper.ingredients()
            instructions = scraper.instructions()
            image_url = scraper.image()
            
            img_path = None
            if image_url:
                try:
                    r = requests.get(image_url, stream=True, timeout=10)
                    if r.status_code == 200:
                        dest_dir = os.path.join(GLib.get_user_data_dir(), "bistro", "user_images")
                        if not os.path.exists(dest_dir):
                            os.makedirs(dest_dir)
                        ext = os.path.splitext(image_url)[1] or ".jpg"
                        if '?' in ext: ext = ext.split('?')[0]
                        if not ext: ext = ".jpg"
                        
                        img_path = os.path.join(dest_dir, f"{uuid.uuid4()}{ext}")
                        with open(img_path, 'wb') as f:
                            r.raw.decode_content = True
                            shutil.copyfileobj(r.raw, f)
                except Exception as e:
                    print(f"Image download failed: {e}")

            GLib.idle_add(self.populate_form, title, ingredients, instructions, img_path, btn)
        except Exception as e:
            print(f"Scrape failed: {e}")
            GLib.idle_add(self.show_scrape_error, str(e), btn)

    def populate_form(self, title, ingredients, instructions, img_path, btn):
        self.spinner.stop()
        btn.set_sensitive(True)
        
        if title:
            self.name_entry.set_text(title)
        
        for row in list(self.ingredient_rows):
            self.remove_ing(row)
            
        if ingredients:
            for ing in ingredients:
                self.add_ingredient_row(ing)
        else:
            self.add_ingredient_row()
            
        if instructions:
            self.inst_buffer.set_text(instructions)
            
        if img_path and os.path.exists(img_path):
            self.selected_image_path = img_path
            self.img_label.set_label(os.path.basename(img_path))
            
        self.toast_overlay.add_toast(Adw.Toast.new("Recipe imported!"))
        return False

    def show_scrape_error(self, msg, btn):
        self.spinner.stop()
        btn.set_sensitive(True)
        self.toast_overlay.add_toast(Adw.Toast.new(f"Import failed: {msg}"))
        return False

    def on_select_image(self, btn):
        def open_callback(dialog, result):
            try:
                file = dialog.open_finish(result)
                self.selected_image_path = file.get_path()
                self.img_label.set_label(os.path.basename(self.selected_image_path))
            except Exception as e:
                print(f"Image selection failed: {e}")

        dialog = Gtk.FileDialog()
        dialog.set_title("Select Image")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filter_img = Gtk.FileFilter()
        filter_img.set_name("Images")
        filter_img.add_mime_type("image/*")
        filters.append(filter_img)
        dialog.set_filters(filters)
        
        dialog.open(self.get_root(), None, open_callback)

    def on_save(self, btn):
        name = self.name_entry.get_text().strip()
        if not name:
            self.toast_overlay.add_toast(Adw.Toast.new("Name is required"))
            return
        
        ings = [r.get_text().strip() for r in self.ingredient_rows if r.get_text().strip()]
        start, end = self.inst_buffer.get_bounds()
        instructions = self.inst_buffer.get_text(start, end, True).strip()
        
        new_recipe = {
            "name": name, 
            "category": self.cat_entry.get_text().strip(),
            "ingredients": ings, 
            "instructions": instructions,
            "image_path": self.selected_image_path
        }

        if not os.path.exists(self.MY_RECIPES_DIR):
            os.makedirs(self.MY_RECIPES_DIR, exist_ok=True)

        save_recipe_folder(new_recipe, self.MY_RECIPES_DIR)
        trigger_auto_sync()
        
        if self.on_save_callback:
            self.on_save_callback()
            
        nav = self.get_ancestor(Adw.NavigationView)
        if nav:
            nav.pop()
