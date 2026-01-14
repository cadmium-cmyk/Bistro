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

try:
    from recipe_scrapers import scrape_me
except ImportError:
    scrape_me = None

class AddRecipePage(Adw.NavigationPage):
    MY_RECIPES_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "my_recipes.json")

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
        inst_view.set_size_request(-1, 200) # Taller for long recipes
        inst_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        frame = Gtk.Frame()
        frame.set_child(inst_view)
        box.append(frame)
        
        # Toast overlay for this page? 
        # Actually UnifiedWindow doesn't have a global toast overlay easily accessible unless we pass it.
        # But we are leaving the page on save, so toasts might be lost if we don't show them on the parent.
        # For errors, we might want a local toast overlay.
        # Let's wrap the ToolbarView in a ToastOverlay?
        # Adw.NavigationPage -> Adw.ToastOverlay -> Adw.ToolbarView
        
        # Re-parent
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
            
            # Download image if available
            img_path = None
            if image_url:
                try:
                    r = requests.get(image_url, stream=True)
                    if r.status_code == 200:
                        dest_dir = os.path.join(GLib.get_user_data_dir(), "bistro", "user_images")
                        if not os.path.exists(dest_dir):
                            os.makedirs(dest_dir)
                        ext = os.path.splitext(image_url)[1] or ".jpg"
                        # Clean extension
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
        
        # Clear ingredients
        for row in list(self.ingredient_rows):
            self.remove_ing(row)
            
        if ingredients:
            for ing in ingredients:
                self.add_ingredient_row(ing)
        else:
            self.add_ingredient_row() # Ensure at least one
            
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
        
        # We need a parent window for the dialog. 
        # self.get_root() works if the page is attached.
        dialog.open(self.get_root(), None, open_callback)

    def load_json(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_json(self, filename, data):
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=4)
        except:
            pass

    def on_save(self, btn):
        name = self.name_entry.get_text().strip()
        if not name:
            self.toast_overlay.add_toast(Adw.Toast.new("Name is required"))
            return
        
        ings = [r.get_text().strip() for r in self.ingredient_rows if r.get_text().strip()]
        start, end = self.inst_buffer.get_bounds()
        instructions = self.inst_buffer.get_text(start, end, True).strip()
        
        # Load existing
        recipes = self.load_json(self.MY_RECIPES_FILE)
        
        saved_img_path = None
        if self.selected_image_path and os.path.exists(self.selected_image_path):
            # Copy to user_images
            try:
                dest_dir = os.path.join(GLib.get_user_data_dir(), "bistro", "user_images")
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir)
                ext = os.path.splitext(self.selected_image_path)[1]
                import shutil
                import uuid
                new_filename = f"{uuid.uuid4()}{ext}"
                dest_path = os.path.join(dest_dir, new_filename)
                shutil.copy(self.selected_image_path, dest_path)
                saved_img_path = dest_path
            except Exception as e:
                print(f"Failed to copy image: {e}")

        new_recipe = {
            "name": name, 
            "category": self.cat_entry.get_text().strip(),
            "ingredients": ings, 
            "instructions": instructions,
            "image_path": saved_img_path
        }
        recipes.append(new_recipe)
        self.save_json(self.MY_RECIPES_FILE, recipes)
        
        if self.on_save_callback:
            self.on_save_callback()
            
        # Pop self
        # We need to find the navigation view. 
        # Adw.NavigationPage does not have a 'pop' method directly, 
        # but the parent (NavigationView) does.
        # But we can assume we are in a navigation view?
        # Or simpler:
        # self.get_parent() is likely the NavigationView (or an intermediate widget?).
        # Actually we can't reliably traverse up to find NavigationView easily in python safely without checking types.
        # But wait, Adw.NavigationView has `pop()`.
        # Usually we pass the controller or find it.
        # Since I am writing the window code, I can pass the navigation view to the constructor?
        # OR: I can use `Adw.NavigationView.find_and_pop(self)`? No such method.
        # `Adw.NavigationView.pop()` pops the top. Since we are the top, it works.
        # How to get the NavigationView?
        # `widget.get_ancestor(Adw.NavigationView)`
        
        nav = self.get_ancestor(Adw.NavigationView)
        if nav:
            nav.pop()
