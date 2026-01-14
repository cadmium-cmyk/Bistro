import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk

from bistro.pages.cocktails import CocktailPage
from bistro.pages.recipe_search import RecipeSearchPage
from bistro.pages.collection import CollectionPage
from bistro.pages.shopping_list import ShoppingListPage
from bistro.pages.add_recipe import AddRecipePage

class UnifiedWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Load resources locally to ensure icons are available
        base_path = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(base_path, "..", "bistro.gresource")
        
        if os.path.exists(resource_path):
            try:
                resource = Gio.Resource.load(resource_path)
                # Registering multiple times is safe (handled by GLib) or might throw if already registered
                # We catch exception just in case
                try:
                    resource._register()
                except:
                    pass
            except Exception as e:
                print(f"Window: Failed to load resource: {e}")

        # Ensure icon theme path
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        if not "/com/github/cadmiumcmyk/Bistro/icons" in icon_theme.get_resource_path():
             icon_theme.add_resource_path("/com/github/cadmiumcmyk/Bistro/icons")
        
        self.set_title("Bistro")
        self.set_default_size(500, 900)
        
        self.nav_view = Adw.NavigationView()
        self.set_content(self.nav_view)

        # Main Page
        self.main_page = Adw.NavigationPage(title="Bistro", tag="main")
        self.nav_view.add(self.main_page)

        # Main content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_page.set_child(content_box)
        
        # Header Bar
        header = Adw.HeaderBar()
        content_box.append(header)
        
        # Add Recipe Button
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.connect("clicked", self.on_add_clicked)
        header.pack_start(add_btn)

        # View Switcher in Title
        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)
        
        self.header_switcher = Adw.ViewSwitcher()
        self.header_switcher.set_stack(self.stack)
        self.header_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self.header_switcher)
        
        # Menu Button
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        
        # Create Menu Model
        menu_model = Gio.Menu()
        
        # Theme Section
        theme_section = Gio.Menu()
        theme_section.append("System", "app.theme('system')")
        theme_section.append("Light", "app.theme('light')")
        theme_section.append("Dark", "app.theme('dark')")
        menu_model.append_section("Theme", theme_section)

        menu_model.append("About", "app.about")
        menu_model.append("Quit", "app.quit")
        menu_btn.set_menu_model(menu_model)
        
        header.pack_end(menu_btn)
        
        # Shopping List
        self.shopping_list_page = ShoppingListPage()

        # Pages
        # Cocktails
        page1 = self.stack.add_titled(CocktailPage(self.shopping_list_page), "cocktails", "Cocktails")
        page1.set_icon_name("drinks-symbolic")
        
        # Recipes (replacing Breweries)
        page2 = self.stack.add_titled(RecipeSearchPage(self.shopping_list_page), "recipes", "Recipes")
        page2.set_icon_name("fast-food-symbolic")
        
        # Collection (replacing My Recipes)
        self.collection_page = CollectionPage(self.shopping_list_page)
        page3 = self.stack.add_titled(self.collection_page, "collection", "Collection")
        page3.set_icon_name("starred-symbolic")
        
        # Shopping List
        page4 = self.stack.add_titled(self.shopping_list_page, "shopping_list", "Shopping List")
        page4.set_icon_name("feather-tag-symbolic")
        
        content_box.append(self.stack)
        
        # Connect to stack switching to refresh collection
        self.stack.connect("notify::visible-child", self.on_stack_switch)

        # Adaptive UI: Bottom Switcher for narrow screens
        self.bottom_switcher = Adw.ViewSwitcherBar()
        self.bottom_switcher.set_stack(self.stack)
        content_box.append(self.bottom_switcher)

        # Breakpoint
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 500px"))
        breakpoint.add_setter(self.header_switcher, "visible", False)
        breakpoint.add_setter(self.bottom_switcher, "reveal", True)
        self.add_breakpoint(breakpoint)

    def on_stack_switch(self, stack, param):
        if stack.get_visible_child() == self.collection_page:
            self.collection_page.refresh_all()

    def on_add_clicked(self, btn):
        page = AddRecipePage(on_save_callback=self.collection_page.refresh_all)
        self.push_page(page)

    def push_page(self, page):
        self.nav_view.push(page)
