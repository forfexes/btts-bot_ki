"""Resize empty premium SVG masters without leaving unused tip slots.

No betting data or synthetic odds are inserted. The returned SVG is a clean
layout master; downstream renderers must insert verified tip data separately.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

ASSETS = Path(__file__).resolve().parent / "assets"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def compact_master(category: str, count: int) -> bytes:
    """Return an SVG master with exactly count empty rows and a moving footer.

    Supports the 10-slot Combo master (3..10 rows) and 6-slot Builder master
    (3..6 rows). Other categories are not silently treated as a Combo.
    """
    limits = {"combo": (3, 10), "builder": (3, 6)}
    if category not in limits:
        raise ValueError("Dynamic row layout is not configured for this category")
    low, high = limits[category]
    if not isinstance(count, int) or isinstance(count, bool) or not low <= count <= high:
        raise ValueError(f"{category} requires {low}..{high} rows")
    root = ET.parse(ASSETS / f"premium_{category}_blank.svg").getroot()
    rectangles = [el for el in root.findall(f"{{{NS}}}rect")
                  if el.get("x") == "42" and el.get("width") == "1038"]
    rows = [el for el in rectangles if float(el.get("y", "0")) < 1185]
    if len(rows) != high:
        raise ValueError(f"Expected {high} empty row slots; found {len(rows)}")
    # Remove unused slots rather than covering them with a blank rectangle.
    for row in rows[count:]:
        root.remove(row)
    # Move the result/footer panel and brand up by the exact vacated space.
    step = float(rows[1].get("y")) - float(rows[0].get("y"))
    shift = (high - count) * step
    footer = next((r for r in rectangles if r.get("y") == "1185"), None)
    if footer is None:
        raise ValueError("Footer panel missing")
    footer.set("y", str(int(1185 - shift)))
    texts = root.findall(f"{{{NS}}}text")
    brand = next((t for t in texts if "".join(t.itertext()).strip() == "@prophunter"), None)
    if brand is None:
        raise ValueError("Footer brand missing")
    brand.set("y", str(int(float(brand.get("y")) - shift)))
    # Crop lower canvas, including border, to match content without excess space.
    height = int(1402 - shift)
    root.set("height", str(height))
    root.set("viewBox", f"0 0 1122 {height}")
    for rect in rectangles:
        if rect.get("x") == "22" and rect.get("height") == "1365":
            rect.set("height", str(height - 37))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
