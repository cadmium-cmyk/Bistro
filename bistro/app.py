import sys
import os
import json
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib

from bistro.window import UnifiedWindow

class UnifiedApp(Adw.Application):
    SETTINGS_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "settings.json")

    def __init__(self):
        super().__init__(application_id="com.github.cadmiumcmyk.Bistro", flags=0)

    def load_settings(self):
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_settings(self, key, value):
        settings = self.load_settings()
        settings[key] = value
        
        d = os.path.dirname(self.SETTINGS_FILE)
        if not os.path.exists(d):
            os.makedirs(d)
            
        try:
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def do_startup(self):
        Adw.Application.do_startup(self)

        # Load resources
        base_path = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(base_path, "..", "bistro.gresource")
        
        if not os.path.exists(resource_path):
             # Try building directory or current dir fallback
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
        dialog.set_comments("A simple app to find drinks and recipes.")
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

if __name__ == "__main__":
    app = UnifiedApp()
    sys.exit(app.run(sys.argv))
