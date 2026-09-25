import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk


def _format_seconds(seconds):
    hours, remainder = divmod(int(seconds or 0), 3600)
    minutes, _seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class StatisticsPage(Adw.NavigationPage):
    def __init__(self, window):
        super().__init__(title="Statistics")
        self.window = window
        self.app = window.app

        toolbar = Adw.ToolbarView.new()
        header = Adw.HeaderBar.new()
        toolbar.add_top_bar(header)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)

        summary = self.app.db.listening_summary()
        total = sum(row["seconds"] or 0 for row in summary)
        heading = Gtk.Label(label=f"Total listening time: {_format_seconds(total)}")
        heading.set_xalign(0)
        heading.add_css_class("title-2")
        content.append(heading)

        if not summary:
            empty = Adw.StatusPage.new()
            empty.set_icon_name("view-statistics-symbolic")
            empty.set_title("No listening data yet")
            empty.set_description("Start an episode to build your listening history.")
            content.append(empty)
        else:
            for row in summary:
                item = Adw.ActionRow()
                item.set_title(row["title"] or "Untitled podcast")
                item.set_subtitle(
                    f"{_format_seconds(row['seconds'])} · "
                    f"{row['completed'] or 0} completed"
                )
                content.append(item)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(content)
        toolbar.set_content(scroll)
        self.set_child(toolbar)
