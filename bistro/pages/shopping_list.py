import json
import os
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

class ShoppingListPage(Adw.Bin):
    DATA_FILE = os.path.join(GLib.get_user_data_dir(), "bistro", "shopping_list.json")

    def __init__(self):
        super().__init__()
        self.ensure_data_dir()
        self.items = self.load_items()
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_child(self.toast_overlay)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        # Header / Title
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        header.set_margin_top(24)
        header.set_margin_bottom(12)
        header.set_margin_start(24)
        header.set_margin_end(24)
        main_box.append(header)
        
        title = Gtk.Label(label="Shopping List", css_classes=["title-2", "custom-title"])
        header.append(title)
        
        # List
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_margin_top(12)
        self.list_box.set_margin_bottom(24)
        self.list_box.set_margin_start(24)
        self.list_box.set_margin_end(24)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.list_box)
        main_box.append(scroll)
        
        self.refresh_list()

    def ensure_data_dir(self):
        d = os.path.dirname(self.DATA_FILE)
        if not os.path.exists(d):
            os.makedirs(d)

    def load_items(self):
        if os.path.exists(self.DATA_FILE):
            try:
                with open(self.DATA_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_items(self):
        try:
            with open(self.DATA_FILE, 'w') as f:
                json.dump(self.items, f, indent=4)
        except:
            pass

    def add_item(self, item_text):
        if item_text not in self.items:
            self.items.append(item_text)
            self.save_items()
            self.refresh_list()
            return True # Added
        return False # Duplicate

    def remove_item(self, row, item_text):
        if item_text in self.items:
            self.items.remove(item_text)
            self.save_items()
            self.refresh_list() 

    def refresh_list(self):
        # Clear
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
            
        if not self.items:
             self.list_box.append(Gtk.Label(label="Your shopping list is empty.", margin_top=20, css_classes=["dim-label"]))
             return

        for item in self.items:
            row = Adw.ActionRow(title=item)
            btn = Gtk.Button(icon_name="user-trash-symbolic")
            btn.add_css_class("flat")
            btn.connect("clicked", lambda b, i=item, r=row: self.remove_item(r, i))
            row.add_suffix(btn)
            self.list_box.append(row)
