import xml.etree.ElementTree as ET
from pathlib import Path


def export_opml(db, path):
    """Write subscribed feeds in the standard OPML 2.0 format."""
    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "Postcast subscriptions"
    body = ET.SubElement(root, "body")
    for podcast in db.podcasts():
        ET.SubElement(
            body,
            "outline",
            type="rss",
            text=podcast.title or podcast.feed_url,
            title=podcast.title or podcast.feed_url,
            xmlUrl=podcast.feed_url,
            htmlUrl=podcast.link or "",
        )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
    return output


def import_opml(path):
    """Return unique feed URLs from an OPML file."""
    root = ET.parse(path).getroot()
    urls = []
    for outline in root.iter("outline"):
        url = outline.get("xmlUrl", "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls
