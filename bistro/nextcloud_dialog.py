import os
import threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from bistro.nextcloud_sync import NextcloudSyncService

class NextcloudSyncDialog(Adw.PreferencesWindow):
    def __init__(self, parent_window, app, on_sync_complete_callback=None):
        super().__init__()
        if parent_window:
            self.set_transient_for(parent_window)
            self.set_modal(True)
        self.set_title("Nextcloud Sync")
        self.set_default_size(500, 450)

        self.app = app
        self.on_sync_complete_callback = on_sync_complete_callback

        settings = self.app.load_settings() if self.app else {}
        nc_url = settings.get("nc_url", "")
        nc_user = settings.get("nc_username", "")
        nc_pass = settings.get("nc_password", "")

        # Page
        page = Adw.PreferencesPage()
        self.add(page)

        # Credentials Group
        cred_group = Adw.PreferencesGroup(title="Nextcloud Cookbook Connection")
        page.add(cred_group)

        self.url_row = Adw.EntryRow(title="Server URL")
        self.url_row.set_text(nc_url)
        self.url_row.connect("changed", self.on_credentials_changed)
        cred_group.add(self.url_row)

        self.user_row = Adw.EntryRow(title="Username")
        self.user_row.set_text(nc_user)
        self.user_row.connect("changed", self.on_credentials_changed)
        cred_group.add(self.user_row)

        self.pass_row = Adw.PasswordEntryRow(title="Password / App Password")
        self.pass_row.set_text(nc_pass)
        self.pass_row.connect("changed", self.on_credentials_changed)
        cred_group.add(self.pass_row)

        # Actions Group
        action_group = Adw.PreferencesGroup(title="Actions")
        page.add(action_group)

        # Test Connection Row
        test_row = Adw.ActionRow(title="Test Connection", subtitle="Verify credentials with server")
        self.test_btn = Gtk.Button(label="Test")
        self.test_btn.set_valign(Gtk.Align.CENTER)
        self.test_btn.connect("clicked", self.on_test_connection)
        test_row.add_suffix(self.test_btn)
        action_group.add(test_row)

        # Sync Row
        sync_row = Adw.ActionRow(title="Synchronize Recipes", subtitle="Two-way sync with Nextcloud Cookbook")
        self.sync_btn = Gtk.Button(label="Sync Now")
        self.sync_btn.add_css_class("suggested-action")
        self.sync_btn.set_valign(Gtk.Align.CENTER)
        self.sync_btn.connect("clicked", self.on_sync_now)
        sync_row.add_suffix(self.sync_btn)
        action_group.add(sync_row)

    def add_toast_msg(self, message):
        try:
            toast = Adw.Toast.new(message)
            self.add_toast(toast)
        except Exception:
            print(f"NextcloudSyncDialog: {message}")

    def save_credentials(self):
        if not self.app:
            return
        url = self.url_row.get_text().strip()
        user = self.user_row.get_text().strip()
        pwd = self.pass_row.get_text().strip()

        self.app.save_settings("nc_url", url)
        self.app.save_settings("nc_username", user)
        self.app.save_settings("nc_password", pwd)

    def on_credentials_changed(self, entry):
        self.save_credentials()

    def get_service(self):
        url = self.url_row.get_text().strip()
        user = self.user_row.get_text().strip()
        pwd = self.pass_row.get_text().strip()
        return NextcloudSyncService(url, user, pwd)

    def on_test_connection(self, btn):
        self.save_credentials()
        btn.set_sensitive(False)
        self.sync_btn.set_sensitive(False)

        def thread_target():
            service = self.get_service()
            success, msg = service.test_connection()
            GLib.idle_add(self.on_test_finish, success, msg, btn)

        threading.Thread(target=thread_target, daemon=True).start()

    def on_test_finish(self, success, msg, btn):
        btn.set_sensitive(True)
        self.sync_btn.set_sensitive(True)
        self.add_toast_msg(msg)
        return False

    def on_sync_now(self, btn):
        self.save_credentials()
        service = self.get_service()
        if not service.is_configured():
            self.add_toast_msg("Please configure URL, username, and password first.")
            return

        btn.set_sensitive(False)
        self.test_btn.set_sensitive(False)

        def thread_target():
            try:
                my_recipes_file = os.path.join(GLib.get_user_data_dir(), "bistro", "my_recipes.json")
                pushed, pulled, updated = service.sync(my_recipes_file)
                msg = f"Sync complete! Pushed: {pushed}, Pulled: {pulled}, Updated: {updated}"
                success = True
            except Exception as e:
                msg = f"Sync failed: {str(e)}"
                success = False

            GLib.idle_add(self.on_sync_finish, success, msg)

        threading.Thread(target=thread_target, daemon=True).start()

    def on_sync_finish(self, success, msg):
        self.sync_btn.set_sensitive(True)
        self.test_btn.set_sensitive(True)
        self.add_toast_msg(msg)

        if success and self.on_sync_complete_callback:
            self.on_sync_complete_callback()
        return False
