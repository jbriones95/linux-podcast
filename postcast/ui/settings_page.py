from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, Gtk

from ..config import APP_VERSION


class SettingsPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Settings")
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        pref = Adw.PreferencesPage.new()
        pref.set_margin_top(16)

        # --- downloads group ---
        group = Adw.PreferencesGroup()
        group.set_title("Downloads")

        self._dir_row = Adw.ActionRow()
        self._dir_row.set_title("Download folder")
        self._dir_row.set_subtitle(str(self.app._download_dir()))
        open_btn = Gtk.Button(label="Open")
        open_btn.connect("clicked", self._open_dir)
        self._dir_row.add_suffix(open_btn)
        group.add(self._dir_row)

        clear_btn_row = Adw.ActionRow()
        clear_btn_row.set_title("Clear downloads")
        clear_btn_row.set_subtitle("Delete all downloaded episode files")
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", self._clear_downloads)
        clear_btn_row.add_suffix(clear_btn)
        group.add(clear_btn_row)

        pref.add(group)

        # --- about group ---
        about = Adw.PreferencesGroup()
        about.set_title("About")

        about_btn_row = Adw.ActionRow()
        about_btn_row.set_title("About Postcast")
        about_btn_row.set_subtitle(f"Version {APP_VERSION}")
        about_row = Gtk.Button(label="About")
        about_row.connect("clicked", self._show_about)
        about_btn_row.add_suffix(about_row)
        about.add(about_btn_row)

        pref.add(about)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(pref)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    # ---------- actions ----------
    def _open_dir(self, *args):
        Gio.AppInfo.launch_default_for_uri(Path(self.app._download_dir()).as_uri())

    def _clear_downloads(self, *args):
        dlg = Adw.AlertDialog.new(
            "Clear downloads?",
            "This deletes all downloaded episode audio files from disk.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("clear", "Clear")
        dlg.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")

        def on_response(d, resp):
            if resp != "clear":
                return
            for pod in self.app.db.podcasts():
                for ep in self.app.db.episodes(pod.id):
                    if ep.downloaded_path:
                        import os
                        try:
                            os.remove(ep.downloaded_path)
                        except OSError:
                            pass
                        self.app.db.clear_download(ep.id)
            self.window.toast("Downloads cleared.")
            self.window.refresh_current_page()

        dlg.connect("response", on_response)
        dlg.present(self.window)

    def _show_about(self, *args):
        about = Adw.AboutWindow.new()
        about.set_application_icon("io.postcast.Postcast")
        about.set_application_name("Postcast")
        about.set_version(APP_VERSION)
        about.set_comments("Podcast player for postmarketOS")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_transient_for(self.window)
        about.present()
