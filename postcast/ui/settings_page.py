from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Adw, Gio, Gtk

from ..config import APP_VERSION
from ..config import data_dir
from ..interop import export_opml


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

        # --- storage group ---
        group = Adw.PreferencesGroup()
        group.set_title("Storage")
        group.set_description("Manage where downloaded episodes are stored.")

        self._dir_row = Adw.ActionRow()
        self._dir_row.set_title("Download folder")
        self._dir_row.set_subtitle(str(self.app._download_dir()))
        open_btn = Gtk.Button(label="Open")
        open_btn.add_css_class("flat")
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.set_tooltip_text("Open download folder")
        open_btn.connect("clicked", self._open_dir)
        self._dir_row.add_suffix(open_btn)
        group.add(self._dir_row)

        clear_btn_row = Adw.ActionRow()
        clear_btn_row.set_title("Clear downloads")
        clear_btn_row.set_subtitle("Delete all downloaded episode files")
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._clear_downloads)
        clear_btn_row.add_suffix(clear_btn)
        group.add(clear_btn_row)

        pref.add(group)

        backup = Adw.PreferencesGroup()
        backup.set_title("Backup and migration")
        backup.set_description("Move subscriptions and playback state between devices.")
        opml_path = data_dir() / "subscriptions.opml"
        export_row = Adw.ActionRow()
        export_row.set_title("Export subscriptions")
        export_row.set_subtitle(str(opml_path))
        export_btn = Gtk.Button(label="Export")
        export_btn.add_css_class("flat")
        export_btn.set_valign(Gtk.Align.CENTER)
        export_btn.connect("clicked", lambda *_: self._export_opml(opml_path))
        export_row.add_suffix(export_btn)
        backup.add(export_row)
        import_row = Adw.ActionRow()
        import_row.set_title("Import subscriptions")
        import_row.set_subtitle("Import the OPML file at the path above")
        import_btn = Gtk.Button(label="Import")
        import_btn.add_css_class("flat")
        import_btn.set_valign(Gtk.Align.CENTER)
        import_btn.connect("clicked", lambda *_: self.window.import_opml(opml_path))
        import_row.add_suffix(import_btn)
        backup.add(import_row)

        sync_path = data_dir() / "library-sync.json"
        export_state_row = Adw.ActionRow()
        export_state_row.set_title("Export library state")
        export_state_row.set_subtitle(str(sync_path))
        export_state_btn = Gtk.Button(label="Export")
        export_state_btn.add_css_class("flat")
        export_state_btn.set_valign(Gtk.Align.CENTER)
        export_state_btn.connect(
            "clicked", lambda *_: self.window.export_library(sync_path)
        )
        export_state_row.add_suffix(export_state_btn)
        backup.add(export_state_row)

        import_state_row = Adw.ActionRow()
        import_state_row.set_title("Merge library state")
        import_state_row.set_subtitle("Merge the JSON file at the path above")
        import_state_btn = Gtk.Button(label="Merge")
        import_state_btn.add_css_class("flat")
        import_state_btn.set_valign(Gtk.Align.CENTER)
        import_state_btn.connect(
            "clicked", lambda *_: self.window.import_library(sync_path)
        )
        import_state_row.add_suffix(import_state_btn)
        backup.add(import_state_row)
        pref.add(backup)

        stats = Adw.PreferencesGroup()
        stats.set_title("Listening")
        stats_row = Adw.ActionRow()
        stats_row.set_title("Statistics")
        stats_row.set_subtitle("Listening time and completed episodes")
        stats_btn = Gtk.Button(label="View")
        stats_btn.add_css_class("flat")
        stats_btn.set_valign(Gtk.Align.CENTER)
        stats_btn.connect("clicked", lambda *_: self.window.open_statistics())
        stats_row.add_suffix(stats_btn)
        stats.add(stats_row)
        pref.add(stats)

        # --- about group ---
        about = Adw.PreferencesGroup()
        about.set_title("About Postcast")
        about.set_description("A simple podcast player for mobile Linux.")

        about_btn_row = Adw.ActionRow()
        about_btn_row.set_title("Postcast")
        about_btn_row.set_subtitle(f"Version {APP_VERSION} · GPL-3.0-or-later")
        about_row = Gtk.Button(label="About")
        about_row.add_css_class("flat")
        about_row.set_valign(Gtk.Align.CENTER)
        about_row.connect("clicked", lambda *_: self.window.open_about())
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

    def _export_opml(self, path):
        export_opml(self.app.db, path)
        self.window.toast(f"Subscriptions exported to {path}.")
