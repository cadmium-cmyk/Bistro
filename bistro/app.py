import sys
import os
import json
import threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from bistro.window import UnifiedWindow
from bistro.cookbook import migrate_legacy_storage
from bistro.nextcloud import NextcloudSync

class UnifiedApp(Adw.Application):
    SETTINGS_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "settings.json")
    BISTRO_DIR = os.path.join(GLib.get_user_data_dir(), "bistro")

    def __init__(self):
        super().__init__(application_id="com.github.cadmiumcmyk.Bistro", flags=0)

    def load_settings(self):
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_setting(self, key, default=None):
        settings = self.load_settings()
        return settings.get(key, default)

    def save_settings(self, key, value):
        settings = self.load_settings()
        settings[key] = value
        
        d = os.path.dirname(self.SETTINGS_FILE)
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def save_settings_dict(self, new_settings):
        settings = self.load_settings()
        settings.update(new_settings)
        d = os.path.dirname(self.SETTINGS_FILE)
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings dict: {e}")

    def do_startup(self):
        Adw.Application.do_startup(self)

        # Ensure directory and migrate legacy storage if needed
        os.makedirs(self.BISTRO_DIR, exist_ok=True)
        try:
            migrate_legacy_storage(self.BISTRO_DIR)
        except Exception as e:
            print(f"Migration error on startup: {e}")

        # Load resources
        base_path = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(base_path, "..", "bistro.gresource")
        
        if not os.path.exists(resource_path):
             if os.path.exists("bistro.gresource"):
                 resource_path = "bistro.gresource"

        if os.path.exists(resource_path):
            try:
                resource = Gio.Resource.load(resource_path)
                resource._register()
            except Exception as e:
                print(f"Failed to load resource: {e}")

        # Load CSS from resource
        css_provider = Gtk.CssProvider()
        try:
            css_provider.load_from_resource("/com/github/cadmiumcmyk/Bistro/style.css")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception as e:
            print(f"Failed to load CSS: {e}")

        # Set up icon search path
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_resource_path("/com/github/cadmiumcmyk/Bistro")
        
        # Setup actions
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit)
        self.add_action(quit_action)
        
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)

        pref_action = Gio.SimpleAction.new("preferences", None)
        pref_action.connect("activate", self.on_preferences)
        self.add_action(pref_action)
        
        # Theme action
        settings = self.load_settings()
        current_theme = settings.get("theme", "system")
        
        # Apply startup theme
        manager = Adw.StyleManager.get_default()
        if current_theme == "light":
            manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        elif current_theme == "dark":
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        theme_action = Gio.SimpleAction.new_stateful("theme", GLib.VariantType.new("s"), GLib.Variant("s", current_theme))
        theme_action.connect("activate", self.on_theme)
        self.add_action(theme_action)

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = UnifiedWindow(application=self)
        win.present()

    def on_quit(self, action, param):
        self.quit()

    def on_about(self, action, param):
        dialog = Adw.AboutWindow(transient_for=self.get_active_window())
        dialog.set_application_name("Bistro")
        dialog.set_version("1.0")
        dialog.set_developer_name("Developer")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.set_comments("A simple app to find drinks and recipes with Nextcloud Cookbook sync.")
        dialog.set_website("https://github.com/cadmium-cmyk/Bistro/")
        dialog.present()

    def on_theme(self, action, param):
        action.set_state(param)
        val = param.get_string()
        manager = Adw.StyleManager.get_default()
        if val == "system":
            manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
        elif val == "light":
            manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        elif val == "dark":
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        
        self.save_settings("theme", val)

    def on_preferences(self, action, param):
        win = self.get_active_window()
        pref_win = Adw.PreferencesWindow(transient_for=win, modal=True, title="Preferences")
        page = Adw.PreferencesPage(title="Nextcloud Sync", icon_name="emblem-synchronizing-symbolic")
        pref_win.add(page)

        group = Adw.PreferencesGroup(title="Nextcloud Server Connection")
        page.add(group)

        settings = self.load_settings()

        enable_switch = Adw.SwitchRow(title="Enable Nextcloud Sync")
        enable_switch.set_active(settings.get("nc_sync_enabled", False))
        group.add(enable_switch)

        url_row = Adw.EntryRow(title="Server URL")
        url_row.set_text(settings.get("nc_url", ""))
        group.add(url_row)

        user_row = Adw.EntryRow(title="Username")
        user_row.set_text(settings.get("nc_username", ""))
        group.add(user_row)

        pass_row = Adw.PasswordEntryRow(title="Password / App Password")
        pass_row.set_text(settings.get("nc_password", ""))
        group.add(pass_row)

        folder_row = Adw.EntryRow(title="Remote Folder")
        folder_row.set_text(settings.get("nc_folder", "Recipes"))
        group.add(folder_row)

        status_label = Gtk.Label(label="", wrap=True, css_classes=["dim-label"], margin_top=8, margin_bottom=8)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=12)

        test_btn = Gtk.Button(label="Test Connection")
        test_btn.add_css_class("suggested-action")

        sync_btn = Gtk.Button(label="Sync Now")

        btn_box.append(test_btn)
        btn_box.append(sync_btn)

        action_row = Adw.ActionRow(title="Actions")
        action_row.add_suffix(btn_box)
        group.add(action_row)

        group.add(Adw.ActionRow(title="Status", child=status_label))

        def save_pref_state():
            self.save_settings_dict({
                "nc_sync_enabled": enable_switch.get_active(),
                "nc_url": url_row.get_text().strip(),
                "nc_username": user_row.get_text().strip(),
                "nc_password": pass_row.get_text().strip(),
                "nc_folder": folder_row.get_text().strip() or "Recipes"
            })

        enable_switch.connect("notify::active", lambda w, p: save_pref_state())
        url_row.connect("changed", lambda w: save_pref_state())
        user_row.connect("changed", lambda w: save_pref_state())
        pass_row.connect("changed", lambda w: save_pref_state())
        folder_row.connect("changed", lambda w: save_pref_state())

        def on_test_clicked(btn):
            save_pref_state()
            test_btn.set_sensitive(False)
            status_label.set_label("Testing connection...")

            def do_test():
                client = NextcloudSync()
                ok, msg = client.test_connection(
                    server_url=url_row.get_text().strip(),
                    username=user_row.get_text().strip(),
                    password=pass_row.get_text().strip(),
                    remote_folder=folder_row.get_text().strip() or "Recipes"
                )
                def finish_test():
                    test_btn.set_sensitive(True)
                    status_label.set_label(msg)
                    return False
                GLib.idle_add(finish_test)

            threading.Thread(target=do_test, daemon=True).start()

        def on_sync_clicked(btn):
            save_pref_state()
            sync_btn.set_sensitive(False)
            status_label.set_label("Syncing with Nextcloud...")

            def do_sync():
                client = NextcloudSync()
                local_dir = os.path.join(self.BISTRO_DIR, "recipes")
                ok, stats, msg = client.sync(
                    server_url=url_row.get_text().strip(),
                    username=user_row.get_text().strip(),
                    password=pass_row.get_text().strip(),
                    remote_folder=folder_row.get_text().strip() or "Recipes",
                    local_recipes_dir=local_dir
                )
                def finish_sync():
                    sync_btn.set_sensitive(True)
                    status_label.set_label(msg)
                    if win and hasattr(win, "collection_page"):
                        win.collection_page.refresh_all()
                    return False
                GLib.idle_add(finish_sync)

            threading.Thread(target=do_sync, daemon=True).start()

        test_btn.connect("clicked", on_test_clicked)
        sync_btn.connect("clicked", on_sync_clicked)

        pref_win.present()

if __name__ == "__main__":
    app = UnifiedApp()
    sys.exit(app.run(sys.argv))
