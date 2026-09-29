import json
import os
import shutil
import threading
import requests
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, GdkPixbuf, Gdk, GLib, Gio

from bistro.pages.add_recipe import AddRecipePage
from bistro.cookbook import (
    load_all_recipes_from_dir,
    save_recipe_folder,
    delete_recipe_folder,
    to_nextcloud_format,
    migrate_legacy_storage
)
from bistro.nextcloud import NextcloudSync

class CollectionPage(Adw.Bin):
    BISTRO_DIR = os.path.join(GLib.get_user_data_dir(), "bistro")
    MY_RECIPES_DIR = os.path.join(GLib.get_user_data_dir(), "bistro", "recipes")
    SETTINGS_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "settings.json")

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

        # Sync Button
        self.sync_btn = Gtk.Button(label="Sync", icon_name="emblem-synchronizing-symbolic")
        self.sync_btn.set_tooltip_text("Sync with Nextcloud Server")
        self.sync_btn.connect("clicked", self.on_sync_clicked)
        row_header.append(self.sync_btn)

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

    def ensure_data_dir(self):
        if not os.path.exists(self.BISTRO_DIR):
            os.makedirs(self.BISTRO_DIR, exist_ok=True)
        if not os.path.exists(self.MY_RECIPES_DIR):
            os.makedirs(self.MY_RECIPES_DIR, exist_ok=True)
        migrate_legacy_storage(self.BISTRO_DIR)

    def load_settings(self):
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def on_filter_changed(self, entry):
        self.filter_text = entry.get_text().strip().lower()
        self.refresh_all()

    def refresh_all(self):
        self.ensure_data_dir()
        # Clear content
        while c := self.scroll_content.get_first_child():
            self.scroll_content.remove(c)

        recipes = load_all_recipes_from_dir(self.MY_RECIPES_DIR)

        if not recipes:
            msg = "No items found." if self.filter_text else "Collection is empty."
            self.scroll_content.append(Gtk.Label(label=msg, css_classes=["dim-label"]))
            return

        # Group recipes by category
        categories = {}
        for r in recipes:
            cat = r.get('category') or r.get('recipeCategory') or "General"
            if not cat.strip():
                cat = "General"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)

        total_visible = 0
        for cat_name in sorted(categories.keys()):
            group_recipes = categories[cat_name]
            group = Adw.PreferencesGroup(title=cat_name)
            cat_visible = 0

            for recipe in group_recipes:
                if self.filter_text:
                    name = recipe.get('name', '').lower()
                    cat = (recipe.get('category') or recipe.get('recipeCategory') or '').lower()
                    desc = recipe.get('description', '').lower()
                    if self.filter_text not in name and self.filter_text not in cat and self.filter_text not in desc:
                        continue

                group.add(self.create_recipe_row(recipe))
                cat_visible += 1
                total_visible += 1

            if cat_visible > 0:
                self.scroll_content.append(group)

        if total_visible == 0:
            msg = "No items found." if self.filter_text else "Collection is empty."
            self.scroll_content.append(Gtk.Label(label=msg, css_classes=["dim-label"]))

    def create_recipe_row(self, data):
        title = data.get('name', 'Untitled Recipe')
        row = Adw.ExpanderRow(title=title)
        row.set_use_markup(False)
        category = data.get('category') or data.get('recipeCategory') or 'General'
        row.set_subtitle(category)

        # Icon based on category or default
        cat_lower = category.lower()
        icon_name = "document-edit-symbolic"
        if "drink" in cat_lower or "cocktail" in cat_lower:
            icon_name = "drinks-symbolic"
        elif "meal" in cat_lower or "food" in cat_lower or "main" in cat_lower:
            icon_name = "fast-food-symbolic"

        row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))

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

        # Instructions / Description
        instr = data.get('instructions') or data.get('description') or ''
        if instr:
            box.append(Gtk.Label(label=instr, wrap=True, xalign=0))

        # Ingredients
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
        del_btn.connect("clicked", self.on_delete_recipe, data)
        actions_box.append(del_btn)

        row.add_row(box)
        return row

    def on_delete_recipe(self, btn, recipe_data):
        folder_path = recipe_data.get('folder_path')
        if folder_path and delete_recipe_folder(folder_path):
            self.refresh_all()
            self.toast_overlay.add_toast(Adw.Toast.new("Recipe deleted"))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new("Failed to delete recipe"))

    def on_export(self, btn, data):
        def save_callback(dialog, result):
            try:
                file = dialog.save_finish(result)
                stream = file.replace(None, False, Gio.FileCreateFlags.NONE, None)

                nc_json = to_nextcloud_format(data)
                text = json.dumps(nc_json, indent=4)

                stream.write_all(text.encode('utf-8'), None)
                stream.close(None)
                self.toast_overlay.add_toast(Adw.Toast.new("Exported Nextcloud Cookbook JSON"))
            except Exception as e:
                print(f"Export failed: {e}")
                self.toast_overlay.add_toast(Adw.Toast.new("Export failed"))

        dialog = Gtk.FileDialog()
        name = data.get('name') or "recipe"
        safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '-', '_')]).strip()
        dialog.set_initial_name(f"{safe_name}.json")
        dialog.save(self.get_root(), None, save_callback)

    def on_add_to_list(self, btn, text):
        if self.shopping_list_page and self.shopping_list_page.add_item(text):
            self.toast_overlay.add_toast(Adw.Toast.new(f"Added '{text}' to list"))
        else:
            self.toast_overlay.add_toast(Adw.Toast.new(f"'{text}' is already in list"))

    def on_add_clicked(self, btn):
        win = self.get_root()
        if hasattr(win, "push_page"):
            page = AddRecipePage(on_save_callback=self.refresh_all)
            win.push_page(page)

    def on_sync_clicked(self, btn):
        settings = self.load_settings()
        if not settings.get("nc_sync_enabled"):
            self.toast_overlay.add_toast(Adw.Toast.new("Nextcloud Sync is disabled in Preferences."))
            return

        self.sync_btn.set_sensitive(False)
        self.toast_overlay.add_toast(Adw.Toast.new("Syncing with Nextcloud..."))

        def do_sync():
            client = NextcloudSync(
                server_url=settings.get("nc_url", ""),
                username=settings.get("nc_username", ""),
                password=settings.get("nc_password", ""),
                remote_folder=settings.get("nc_folder", "Recipes")
            )
            ok, stats, msg = client.sync(local_recipes_dir=self.MY_RECIPES_DIR)

            def finish():
                self.sync_btn.set_sensitive(True)
                self.refresh_all()
                self.toast_overlay.add_toast(Adw.Toast.new(msg))
                return False

            GLib.idle_add(finish)

        threading.Thread(target=do_sync, daemon=True).start()
