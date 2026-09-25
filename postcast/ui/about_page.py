import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, Gtk

from ..config import APP_VERSION


class AboutPage(Adw.NavigationPage):
    """In-app About screen so mobile users always have a back affordance."""

    def __init__(self, window):
        super().__init__(title="About Postcast")
        self.window = window

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(24)
        content.set_margin_bottom(24)

        icon = Gtk.Image.new_from_icon_name("io.postcast.Postcast")
        icon.set_pixel_size(96)
        icon.set_halign(Gtk.Align.CENTER)
        content.append(icon)

        name = Gtk.Label(label="Postcast")
        name.add_css_class("title-1")
        name.set_halign(Gtk.Align.CENTER)
        content.append(name)

        version = Gtk.Label(label=f"Version {APP_VERSION}")
        version.add_css_class("dim-label")
        version.set_halign(Gtk.Align.CENTER)
        content.append(version)

        description = Gtk.Label(
            label="A focused podcast player for Linux phones and desktops."
        )
        description.set_wrap(True)
        description.set_justify(Gtk.Justification.CENTER)
        description.set_halign(Gtk.Align.CENTER)
        content.append(description)

        details = Adw.PreferencesGroup()
        details.set_title("Details")
        license_row = Adw.ActionRow()
        license_row.set_title("License")
        license_row.set_subtitle("GPL-3.0-or-later")
        details.add(license_row)
        platform_row = Adw.ActionRow()
        platform_row.set_title("Platform")
        platform_row.set_subtitle("Linux · GTK4 · Libadwaita")
        details.add(platform_row)
        content.append(details)

        links = Adw.PreferencesGroup()
        links.set_title("Project")
        source_row = Adw.ActionRow()
        source_row.set_title("Source code")
        source_row.set_subtitle("github.com/jbriones95/linux-podcast")
        source_button = Gtk.Button(label="Open")
        source_button.add_css_class("flat")
        source_button.set_valign(Gtk.Align.CENTER)
        source_button.connect(
            "clicked",
            lambda *_: Gio.AppInfo.launch_default_for_uri(
                "https://github.com/jbriones95/linux-podcast"
            ),
        )
        source_row.add_suffix(source_button)
        links.add(source_row)
        content.append(links)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)
