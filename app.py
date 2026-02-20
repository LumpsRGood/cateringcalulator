import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# PDF (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit

# =========================================================
# App Meta
# =========================================================
APP_NAME = "IHOP Catering Calculator"
APP_VERSION = "v2.0.3"

st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", layout="wide")

# =========================================================
# Data model
# =========================================================
@dataclass(frozen=True)
class LineKey:
    kind: str  # "combo" or "alacarte"
    item_id: str
    protein: Optional[str] = None
    griddle: Optional[str] = None
    beverage_type: Optional[str] = None  # for cold beverage bag


@dataclass
class OrderLine:
    key: LineKey
    label: str
    qty: int


# =========================================================
# Helpers
# =========================================================
def ceil_to_increment(x: float, inc: float) -> float:
    return math.ceil(x / inc) * inc


def friendly_round_up(x: float, inc: float = 0.5, tiny_over: float = 0.05) -> float:
    """
    Your rule:
    - Default: round UP to next increment (ex: 1.16 -> 1.5 when inc=0.5)
    - Exception: if it's barely over a clean number (ex: 5.01), round down to the clean number
    """
    nearest_down = math.floor(x / inc) * inc
    if x - nearest_down <= tiny_over:
        return nearest_down
    return ceil_to_increment(x, inc)


def ounces_to_lbs(oz: float) -> float:
    return oz / 16.0


def compute_pickup_and_ready(pickup_date, pickup_time) -> Tuple[datetime, datetime]:
    pickup_dt = datetime.combine(pickup_date, pickup_time)
    ready_dt = pickup_dt - timedelta(minutes=10)
    return pickup_dt, ready_dt


def init_state():
    if "lines" not in st.session_state:
        st.session_state.lines: List[OrderLine] = []
    if "edit_idx" not in st.session_state:
        st.session_state.edit_idx = None

    st.session_state.setdefault("_reset_combo", False)
    st.session_state.setdefault("_reset_alacarte", False)

    # Defaults before widgets render
    if st.session_state._reset_combo:
        st.session_state.combo_tier = list(COMBO_TIERS.keys())[0]
        st.session_state.combo_protein = PROTEINS[0]
        st.session_state.combo_griddle = GRIDDLE_CHOICES[0]
        st.session_state.combo_qty = 1
        st.session_state._reset_combo = False
    else:
        st.session_state.setdefault("combo_tier", list(COMBO_TIERS.keys())[0])
        st.session_state.setdefault("combo_protein", PROTEINS[0])
        st.session_state.setdefault("combo_griddle", GRIDDLE_CHOICES[0])
        st.session_state.setdefault("combo_qty", 1)

    if st.session_state._reset_alacarte:
        st.session_state.al_item = ALACARTE_LABELS[0]
        st.session_state.al_qty = 1
        st.session_state._reset_alacarte = False
    else:
        st.session_state.setdefault("al_item", ALACARTE_LABELS[0])
        st.session_state.setdefault("al_qty", 1)

    st.session_state.setdefault("pickup_date", datetime.now().date())
    st.session_state.setdefault("pickup_time", datetime.now().replace(second=0, microsecond=0).time())


def merge_or_add_line(new_line: OrderLine):
    for i, line in enumerate(st.session_state.lines):
        if line.key == new_line.key:
            st.session_state.lines[i].qty += new_line.qty
            return
    st.session_state.lines.append(new_line)


def remove_line(idx: int):
    st.session_state.lines.pop(idx)
    if st.session_state.edit_idx == idx:
        st.session_state.edit_idx = None


def reset_combo_form():
    st.session_state._reset_combo = True


def reset_alacarte_form():
    st.session_state._reset_alacarte = True


# =========================================================
# Naming (your parlance)
# =========================================================
POTATOES_NAME = "Red Pots"
HAM_NAME = "Sampler Ham"

# =========================================================
# SKU / pack constants
# =========================================================
SKU = {
    "eggs": {"sku": "775616", "units_per_case": 2, "lbs_per_unit": 20},          # 2/20lb
    "red_pots": {"sku": "39332", "bags_per_case": 6, "lbs_per_bag": 6},          # 6/6lb
    "bacon": {"sku": "423530", "cases_unit": "case", "lbs_per_case": 25},        # 1/25lb
    "sausage": {"sku": "652253", "bags_per_case": 2, "lbs_per_bag": 10},         # 2/10lb
    "ham": {"sku": "577234", "packs_per_case": 8, "lbs_per_pack": 3},            # 8/3lb
    "pancake_mix": {"sku": "993457", "lbs_per_bag": 45},                         # 1/45lb
    "ft_bread": {"sku": "101757", "loaves_per_case": 12, "oz_per_loaf": 30, "slices_per_loaf": 9},
    "chicken_strips": {"sku": "646261", "bags_per_case": 6, "lbs_per_bag": 5, "oz_per_piece": 3},
    "fries": {"sku": "525302", "bags_per_case": 6, "lbs_per_bag": 6, "oz_per_portion": 6},
    "onion_rings": {"sku": "589431", "bags_per_case": 8, "lbs_per_bag": 2.5, "oz_per_ring": 1.25},
    "steakburgers": {"sku": "798706", "patties_per_case": 60, "oz_per_patty": 5.33},
    "burger_buns": {"sku": "1000660", "buns_per_case": 96},                      # 24/4ct -> 96
}

# =========================================================
# Combo Specs (kitchen-facing)
# =========================================================
PROTEINS = ["Bacon", "Pork Sausage Links", HAM_NAME]
GRIDDLE_CHOICES = ["Buttermilk Pancakes", "French Toast"]

# You asked: no “Feeds X”. Keep the label relatable, but you previously wanted something like "Small Combo Box (6-10)".
# If you want those ranges back, edit the keys below.
COMBO_TIERS = {
    "Small Combo Box": {
        "eggs_oz": 40,
        "red_pots_oz": 60,
        "protein_pcs": 20,
        "pancakes_pcs": 20,
        "ft_slices": 10,
        # packaging totals (clarity wording later)
        "aluminum_pans_eggs": 1,
        "aluminum_pans_red_pots": 1,
        "ihop_plastic_bases_protein": 1,
        "aluminum_pans_pancakes": 1,
        "aluminum_pans_ft": 2,
        # condiments / serveware
        "butter_packets": 10,
        "syrup_packets": 10,
        "ketchup_packets": 10,
        "powdered_sugar_cups_2oz": 1,  # 1 cup per 10 slices
        "serving_forks": 2,
        "serving_tongs": 2,
        "plates": 10,
    },
    "Medium Combo Box": {
        "eggs_oz": 80,
        "red_pots_oz": 120,
        "protein_pcs": 40,
        "pancakes_pcs": 40,
        "ft_slices": 20,
        "aluminum_pans_eggs": 2,
        "aluminum_pans_red_pots": 2,
        "ihop_plastic_bases_protein": 2,
        "aluminum_pans_pancakes": 2,
        "aluminum_pans_ft": 4,
        "butter_packets": 20,
        "syrup_packets": 20,
        "ketchup_packets": 20,
        "powdered_sugar_cups_2oz": 2,
        "serving_forks": 2,
        "serving_tongs": 2,
        "plates": 20,
    },
    "Large Combo Box": {
        "eggs_oz": 160,
        "red_pots_oz": 240,
        "protein_pcs": 80,
        "pancakes_pcs": 80,
        "ft_slices": 40,
        "aluminum_pans_eggs": 4,
        "aluminum_pans_red_pots": 4,
        "ihop_plastic_bases_protein": 4,
        "aluminum_pans_pancakes": 4,
        "aluminum_pans_ft": 8,
        "butter_packets": 40,
        "syrup_packets": 40,
        "ketchup_packets": 40,
        "powdered_sugar_cups_2oz": 4,
        "serving_forks": 8,
        "serving_tongs": 5,
        "plates": 40,
    },
}

# =========================================================
# À la carte menu
# =========================================================
COLD_BEV_TYPES = ["Apple Juice", "Orange Juice", "Iced Tea", "Lemonade", "Soda"]
COLD_BEV_OZ = 128

ALACARTE_GROUPS = [
    ("Griddle Faves", [
        ("pancakes_20", "Buttermilk Pancakes (20 pcs)", {"pancakes_pcs": 20}),
        ("ft_10_slices", "French Toast (10 slices)", {"ft_slices": 10}),
    ]),
    ("Breakfast Proteins & Sides", [
        ("eggs_40oz", "Scrambled Eggs (40 oz)", {"eggs_oz": 40}),
        ("red_pots_40oz", f"{POTATOES_NAME} (40 oz)", {"red_pots_oz": 40}),
        ("bacon_20", "Bacon (20 pcs)", {"bacon_pcs": 20}),
        ("sausage_20", "Pork Sausage Links (20 pcs)", {"sausage_pcs": 20}),
        ("ham_20", f"{HAM_NAME} (20 pcs)", {"ham_pcs": 20}),
    ]),
    ("Lunch / Savory", [
        ("chix_strips_40", "Chicken Strips (40 pcs)", {"chix_strips_pcs": 40}),
        ("fries_60oz", "French Fries (60 oz)", {"fries_oz": 60}),
        ("onion_rings_std", "Onion Rings (prep by ring count)", {"onion_rings_from_oz": 60}),
    ]),
    ("Burgers & Chicken (10 pcs)", [
        ("steakburgers_10", "Steakburgers (10 pcs)", {"steakburgers_pcs": 10, "auto_buns": 10}),
        ("crispy_chx_sand_10", "Crispy Chicken Sandwiches (10 pcs)", {"auto_buns": 10}),
        ("grilled_chx_sand_10", "Grilled Chicken Sandwiches (10 pcs)", {"auto_buns": 10}),
    ]),
    ("Beverages", [
        ("coffee_box", "Coffee Box (96 oz)", {"coffee_boxes": 1}),
        ("cold_bag", "Cold Beverage Bag (128 oz)", {"cold_bags": 1}),
    ]),
]

ALACARTE_LOOKUP: Dict[str, Dict] = {}
ALACARTE_LABELS: List[str] = []
AL_LABEL_TO_ID: Dict[str, str] = {}

for group_name, items in ALACARTE_GROUPS:
    for item_id, label, payload in items:
        ALACARTE_LOOKUP[item_id] = {"label": label, "payload": payload, "group": group_name}
        ALACARTE_LABELS.append(label)
        AL_LABEL_TO_ID[label] = item_id


# =========================================================
# Totals building
# =========================================================
def compute_order_totals(lines: List[OrderLine]) -> Dict[str, float]:
    totals: Dict[str, float] = {}

    def add(k: str, v: float):
        totals[k] = totals.get(k, 0) + v

    for line in lines:
        qty = int(line.qty)

        if line.key.kind == "combo":
            tier = line.key.item_id
            protein = line.key.protein
            griddle = line.key.griddle
            spec = COMBO_TIERS[tier]

            add("eggs_oz", spec["eggs_oz"] * qty)
            add("red_pots_oz", spec["red_pots_oz"] * qty)

            if protein == "Bacon":
                add("bacon_pcs", spec["protein_pcs"] * qty)
            elif protein == "Pork Sausage Links":
                add("sausage_pcs", spec["protein_pcs"] * qty)
            elif protein == HAM_NAME:
                add("ham_pcs", spec["protein_pcs"] * qty)

            if griddle == "Buttermilk Pancakes":
                add("pancakes_pcs", spec["pancakes_pcs"] * qty)
            else:
                add("ft_slices", spec["ft_slices"] * qty)
                add("powdered_sugar_cups_2oz", spec["powdered_sugar_cups_2oz"] * qty)

            add("butter_ct", spec["butter_packets"] * qty)
            add("syrup_ct", spec["syrup_packets"] * qty)
            add("ketchup_ct", spec["ketchup_packets"] * qty)

            add("serving_forks", spec["serving_forks"] * qty)
            add("serving_tongs", spec["serving_tongs"] * qty)
            add("plates", spec["plates"] * qty)

            # Packaging totals (clear wording)
            add("aluminum_pans", (spec["aluminum_pans_eggs"] + spec["aluminum_pans_red_pots"]) * qty)
            add("ihop_plastic_bases", spec["ihop_plastic_bases_protein"] * qty)
            if griddle == "Buttermilk Pancakes":
                add("aluminum_pans", spec["aluminum_pans_pancakes"] * qty)
            else:
                add("aluminum_pans", spec["aluminum_pans_ft"] * qty)

        else:
            spec = ALACARTE_LOOKUP[line.key.item_id]["payload"]

            if "pancakes_pcs" in spec:
                add("pancakes_pcs", spec["pancakes_pcs"] * qty)

            if "ft_slices" in spec:
                add("ft_slices", spec["ft_slices"] * qty)
                cups = (spec["ft_slices"] * qty) / 10.0
                add("powdered_sugar_cups_2oz", math.ceil(cups - 1e-9))

            if "eggs_oz" in spec:
                add("eggs_oz", spec["eggs_oz"] * qty)

            if "red_pots_oz" in spec:
                add("red_pots_oz", spec["red_pots_oz"] * qty)

            if "bacon_pcs" in spec:
                add("bacon_pcs", spec["bacon_pcs"] * qty)
            if "sausage_pcs" in spec:
                add("sausage_pcs", spec["sausage_pcs"] * qty)
            if "ham_pcs" in spec:
                add("ham_pcs", spec["ham_pcs"] * qty)

            if "chix_strips_pcs" in spec:
                add("chix_strips_pcs", spec["chix_strips_pcs"] * qty)

            if "fries_oz" in spec:
                add("fries_oz", spec["fries_oz"] * qty)
                add("aluminum_pans", 1 * qty)
                add("serving_tongs", 1 * qty)
                add("ketchup_ct", 10 * qty)

            if "onion_rings_from_oz" in spec:
                rings = (spec["onion_rings_from_oz"] * qty) / SKU["onion_rings"]["oz_per_ring"]
                add("onion_rings_rings", math.ceil(rings - 1e-9))
                add("aluminum_pans", 2 * qty)
                add("serving_tongs", 1 * qty)
                add("ketchup_ct", 10 * qty)

            if "steakburgers_pcs" in spec:
                add("steakburgers_pcs", spec["steakburgers_pcs"] * qty)
            if "auto_buns" in spec:
                add("buns_ct", spec["auto_buns"] * qty)

            if "coffee_boxes" in spec:
                add("coffee_boxes", spec["coffee_boxes"] * qty)

            if "cold_bags" in spec:
                bags = spec["cold_bags"] * qty
                bev_type = line.key.beverage_type or "Unknown"
                add(f"cold_bags::{bev_type}", bags)

    return totals


# =========================================================
# Prep language formatting helpers (for output + PDF)
# =========================================================
def eggs_prep_line(eggs_oz: float) -> str:
    # Inferred conversion: ~0.465 qt per lb
    lbs = ounces_to_lbs(eggs_oz)
    quarts = lbs * 0.465
    quarts_r = friendly_round_up(quarts, inc=0.5, tiny_over=0.05)
    cambros_4qt = quarts_r / 4.0
    return f"Scrambled Eggs: {quarts_r:g} qt (≈ {cambros_4qt:.1f} of a 4-qt Cambro)"


def bag_overflow_line(total_oz: float, oz_per_bag: float, oz_per_portion: Optional[float], label: str) -> str:
    """
    Show:
    - Always: total oz (portions / lbs)
    - Only if > 1 bag: "Open: X bag(s) PLUS Y oz ..."
    For under 1 bag, do NOT show bag text.
    """
    lbs = ounces_to_lbs(total_oz)
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05) if lbs > 0 else 0

    if oz_per_portion:
        portions = total_oz / oz_per_portion
        portions_int = int(math.ceil(portions - 1e-9))
        main = f"{label}: {int(total_oz)} oz ({portions_int} portions / {lbs_r:g} lb)"
    else:
        main = f"{label}: {int(total_oz)} oz ({lbs_r:g} lb)"

    if total_oz <= oz_per_bag + 1e-9:
        return main

    full_bags = int(total_oz // oz_per_bag)
    rem_oz = total_oz - (full_bags * oz_per_bag)
    rem_lbs = ounces_to_lbs(rem_oz)
    rem_lbs_r = friendly_round_up(rem_lbs, inc=0.5, tiny_over=0.05) if rem_lbs > 0 else 0

    if oz_per_portion:
        rem_portions = rem_oz / oz_per_portion
        rem_portions_int = int(math.ceil(rem_portions - 1e-9))
        return (
            f"{main}\nOpen: {full_bags} bag{'s' if full_bags != 1 else ''} PLUS "
            f"{int(rem_oz)} oz ({rem_portions_int} portions / {rem_lbs_r:g} lb)"
        )

    return (
        f"{main}\nOpen: {full_bags} bag{'s' if full_bags != 1 else ''} PLUS "
        f"{int(rem_oz)} oz ({rem_lbs_r:g} lb)"
    )


def red_pots_prep_line(total_oz: float) -> str:
    return bag_overflow_line(
        total_oz=total_oz,
        oz_per_bag=SKU["red_pots"]["lbs_per_bag"] * 16,
        oz_per_portion=SKU["fries"]["oz_per_portion"],  # 6 oz portion logic
        label=POTATOES_NAME
    )


def fries_prep_line(total_oz: float) -> str:
    return bag_overflow_line(
        total_oz=total_oz,
        oz_per_bag=SKU["fries"]["lbs_per_bag"] * 16,
        oz_per_portion=SKU["fries"]["oz_per_portion"],
        label="French Fries"
    )


def bacon_prep_line(bacon_pcs: float) -> str:
    lbs = bacon_pcs / 9.0
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"Bacon: {int(bacon_pcs)} slices (≈ {lbs_r:g} lb)"


def sausage_prep_line(sausage_pcs: float) -> str:
    lbs = sausage_pcs / 20.0
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"Pork Sausage Links: {int(sausage_pcs)} links (≈ {lbs_r:g} lb)"


def ham_prep_line(ham_pcs: float) -> str:
    lbs = ounces_to_lbs(ham_pcs * 1.0)  # 1 oz per quarter slice
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"{HAM_NAME}: {int(ham_pcs)} pcs (≈ {lbs_r:g} lb)"


def chicken_strips_prep_line(pcs: float) -> str:
    # placeholder: 3 oz each, but you said we can adjust later
    lbs = ounces_to_lbs(pcs * 3.0)
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"Chicken Strips: {int(pcs)} pcs (≈ {lbs_r:g} lb)"


def pancakes_prep_line(pancakes_pcs: float) -> str:
    return f"Buttermilk Pancakes: {int(pancakes_pcs)} pancakes"


def ft_prep_line_slices(ft_slices: float) -> str:
    return f"French Toast: {int(ft_slices)} slices"


def onion_rings_prep_line(rings: float) -> str:
    return f"Onion Rings: {int(rings)} rings"


def powdered_sugar_prep_line(cups: float) -> str:
    return f"Powdered Sugar: {int(cups)} (2 oz) cups"


def build_prep_lines(totals: Dict[str, float]) -> List[str]:
    lines: List[str] = []

    if totals.get("eggs_oz", 0) > 0:
        lines.append(eggs_prep_line(totals["eggs_oz"]))
    if totals.get("red_pots_oz", 0) > 0:
        lines.append(red_pots_prep_line(totals["red_pots_oz"]))
    if totals.get("bacon_pcs", 0) > 0:
        lines.append(bacon_prep_line(totals["bacon_pcs"]))
    if totals.get("sausage_pcs", 0) > 0:
        lines.append(sausage_prep_line(totals["sausage_pcs"]))
    if totals.get("ham_pcs", 0) > 0:
        lines.append(ham_prep_line(totals["ham_pcs"]))
    if totals.get("pancakes_pcs", 0) > 0:
        lines.append(pancakes_prep_line(totals["pancakes_pcs"]))
    if totals.get("ft_slices", 0) > 0:
        lines.append(ft_prep_line_slices(totals["ft_slices"]))
    if totals.get("chix_strips_pcs", 0) > 0:
        lines.append(chicken_strips_prep_line(totals["chix_strips_pcs"]))
    if totals.get("fries_oz", 0) > 0:
        lines.append(fries_prep_line(totals["fries_oz"]))
    if totals.get("onion_rings_rings", 0) > 0:
        lines.append(onion_rings_prep_line(totals["onion_rings_rings"]))
    if totals.get("steakburgers_pcs", 0) > 0:
        lines.append(f"Steakburgers: {int(totals['steakburgers_pcs'])} patties")
    if totals.get("buns_ct", 0) > 0:
        lines.append(f"Burger Buns: {int(totals['buns_ct'])} buns")
    if totals.get("powdered_sugar_cups_2oz", 0) > 0:
        lines.append(powdered_sugar_prep_line(totals["powdered_sugar_cups_2oz"]))

    if totals.get("coffee_boxes", 0) > 0:
        boxes = int(totals["coffee_boxes"])
        lines.append(f"Coffee: {boxes} box(es)")

    for k, v in totals.items():
        if k.startswith("cold_bags::"):
            bev = k.split("::", 1)[1]
            bags = int(v)
            lines.append(f"Cold Beverage Bag: {bags} bag(s) | {bev} ({bags * COLD_BEV_OZ} oz total)")

    return lines


# =========================================================
# PDF Generation (day-of sheet)
# - NO plating reference
# - NO inventory impact
# - NO CSV download
# =========================================================
def _pdf_draw_section_title(c: canvas.Canvas, title: str, x: float, y: float) -> float:
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, title)
    return y - 14


def _pdf_draw_wrapped_lines(
    c: canvas.Canvas,
    lines: List[str],
    x: float,
    y: float,
    max_width: float,
    font_name: str = "Helvetica",
    font_size: int = 10,
    leading: int = 12,
    bullet: bool = True,
    bottom_margin: float = 0.75 * inch,
) -> float:
    c.setFont(font_name, font_size)
    for raw in lines:
        prefix = "• " if bullet else ""
        # wrap each paragraph (including possible embedded newlines)
        for para in str(raw).split("\n"):
            wrapped = simpleSplit(prefix + para, font_name, font_size, max_width)
            for w in wrapped:
                if y <= bottom_margin:
                    c.showPage()
                    y = letter[1] - 0.75 * inch
                    c.setFont(font_name, font_size)
                c.drawString(x, y, w)
                y -= leading
            prefix = "  " if bullet else ""  # subsequent wrapped lines align
    return y


def generate_day_of_pdf(
    order_lines: List[OrderLine],
    pickup_dt: datetime,
    ready_dt: datetime,
    headcount: int,
    utensils_ordered: int,
    totals: Dict[str, float],
) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    left = 0.75 * inch
    right = 0.75 * inch
    top = height - 0.75 * inch
    bottom = 0.75 * inch
    usable_w = width - left - right

    y = top

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, f"{APP_NAME} (Day-Of Sheet)")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - right, y, f"{APP_VERSION}")
    y -= 18

    # Header block
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Timing")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Ready Time:  {ready_dt.strftime('%Y-%m-%d %I:%M %p')}")
    y -= 12
    c.drawString(left, y, f"Pickup Time: {pickup_dt.strftime('%Y-%m-%d %I:%M %p')}")
    y -= 14

    # Headcount + utensils
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Counts")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Headcount: {int(headcount)}")
    y -= 12
    c.drawString(left, y, f"Utensil sets ordered: {int(utensils_ordered)}")
    y -= 12

    recommended = int(headcount) if headcount and headcount > 0 else 0
    if recommended > 0:
        c.drawString(left, y, f"Utensil sets recommended: {recommended}")
        y -= 12

        # mismatch note (simple)
        if utensils_ordered > 0 and utensils_ordered < headcount:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(left, y, f"NOTE: Ordered {utensils_ordered} but headcount is {headcount}.")
            c.setFont("Helvetica", 10)
            y -= 12

    y -= 6
    c.line(left, y, width - right, y)
    y -= 16

    # Section 1: Order Summary
    y = _pdf_draw_section_title(c, "1) Order Summary", left, y)
    summary_lines = [f"{ol.label}  (Qty {ol.qty})" for ol in order_lines]
    y = _pdf_draw_wrapped_lines(c, summary_lines, left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    # Section 2: Food Prep Totals
    y = _pdf_draw_section_title(c, "2) Food Prep Totals", left, y)
    prep_lines = build_prep_lines(totals)
    y = _pdf_draw_wrapped_lines(c, prep_lines, left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    # Section 3: Packaging Totals (clarified wording)
    y = _pdf_draw_section_title(c, "3) Packaging Totals", left, y)
    pack_lines = []
    if totals.get("aluminum_pans", 0) > 0:
        pack_lines.append(f"Aluminum: {int(totals['aluminum_pans'])} pans")
    if totals.get("ihop_plastic_bases", 0) > 0:
        pack_lines.append(f"IHOP Plastic: {int(totals['ihop_plastic_bases'])} bases")
    if not pack_lines:
        pack_lines = ["None"]
    y = _pdf_draw_wrapped_lines(c, pack_lines, left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    # Section 4: Condiments
    y = _pdf_draw_section_title(c, "4) Condiments", left, y)
    cond = []
    if totals.get("butter_ct", 0) > 0:
        cond.append(f"Butter packets: {int(totals['butter_ct'])}")
    if totals.get("syrup_ct", 0) > 0:
        cond.append(f"Syrup packets: {int(totals['syrup_ct'])}")
    if totals.get("ketchup_ct", 0) > 0:
        cond.append(f"Ketchup packets: {int(totals['ketchup_ct'])}")
    if totals.get("powdered_sugar_cups_2oz", 0) > 0:
        cond.append(f"Powdered sugar (2 oz cups): {int(totals['powdered_sugar_cups_2oz'])}")
    if not cond:
        cond = ["None"]
    y = _pdf_draw_wrapped_lines(c, cond, left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    # Section 5: Serveware
    y = _pdf_draw_section_title(c, "5) Serveware", left, y)
    serve = []
    if totals.get("plates", 0) > 0:
        serve.append(f"Plates: {int(totals['plates'])}")
    if totals.get("serving_tongs", 0) > 0:
        serve.append(f"Serving tongs: {int(totals['serving_tongs'])}")
    if totals.get("serving_forks", 0) > 0:
        serve.append(f"Serving forks: {int(totals['serving_forks'])}")
    # spoons aren't currently added by this build (kept for future)
    if utensils_ordered > 0:
        serve.append(f"Utensil sets (ordered): {int(utensils_ordered)}")
    if recommended > 0:
        serve.append(f"Utensil sets (recommended): {int(recommended)}")
    if not serve:
        serve = ["None"]
    y = _pdf_draw_wrapped_lines(c, serve, left, y, usable_w, bullet=True, bottom_margin=bottom)

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(width - right, bottom - 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')} • {APP_VERSION}")

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================================================
# UI
# =========================================================
init_state()

st.title(f"{APP_NAME} {APP_VERSION}")
st.caption("Dropdown entry for managers. Day-of output focuses on prep, packaging, condiments, serveware.")

with st.container():
    st.subheader("Build Order")

    st.markdown("### Timing")
    st.date_input("Pickup date", key="pickup_date")
    st.time_input("Pickup time", key="pickup_time")
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)

    t1, t2 = st.columns(2)
    t1.metric("Ready time", ready_dt.strftime("%Y-%m-%d %I:%M %p"))
    t2.metric("Pickup time", pickup_dt.strftime("%Y-%m-%d %I:%M %p"))

    st.divider()

    headcount = st.number_input("Headcount (if provided)", min_value=0, value=0, step=1)
    ordered_utensils = st.number_input("Utensil sets ordered (trust this number)", min_value=0, value=0, step=1)

    st.divider()
    st.markdown("### — Breakfast Combo Boxes —")
    combo_tier = st.selectbox("Combo size", list(COMBO_TIERS.keys()), key="combo_tier")
    combo_protein = st.selectbox("Protein", PROTEINS, key="combo_protein")
    combo_griddle = st.selectbox("Griddle item", GRIDDLE_CHOICES, key="combo_griddle")
    combo_qty = st.number_input("Combo quantity", min_value=1, value=int(st.session_state.combo_qty), step=1, key="combo_qty")

    if st.button("Add Combo", type="primary", use_container_width=True):
        label = f"{combo_tier} | {combo_protein} | {combo_griddle}"
        key = LineKey(kind="combo", item_id=combo_tier, protein=combo_protein, griddle=combo_griddle)
        merge_or_add_line(OrderLine(key=key, label=label, qty=int(combo_qty)))
        reset_combo_form()
        st.rerun()

    st.divider()
    st.markdown("### — À La Carte Items —")
    al_item = st.selectbox("Select item", ALACARTE_LABELS, key="al_item")
    al_qty = st.number_input("À la carte quantity", min_value=1, value=int(st.session_state.al_qty), step=1, key="al_qty")

    al_id = AL_LABEL_TO_ID[al_item]
    if al_id == "cold_bag":
        st.selectbox("Cold beverage type", COLD_BEV_TYPES, index=0, key="cold_bev_type")

    if st.button("Add À La Carte", use_container_width=True):
        item_id = AL_LABEL_TO_ID[al_item]

        if item_id == "cold_bag":
            bev_type = st.session_state.get("cold_bev_type", COLD_BEV_TYPES[0])
            label = f"{al_item} | {bev_type}"
            key = LineKey(kind="alacarte", item_id=item_id, beverage_type=bev_type)
        else:
            label = al_item
            key = LineKey(kind="alacarte", item_id=item_id)

        merge_or_add_line(OrderLine(key=key, label=label, qty=int(al_qty)))
        reset_alacarte_form()
        st.rerun()

with st.sidebar:
    st.subheader("Current Order")

    if not st.session_state.lines:
        st.info("Add items to build an order.")
    else:
        for idx, line in enumerate(st.session_state.lines):
            box = st.container(border=True)
            c1, c2 = box.columns([5, 2])

            with c1:
                st.markdown(f"**{line.label}**")
                st.caption(f"Qty: {line.qty}")
            with c2:
                if st.button("Edit", key=f"edit_{idx}"):
                    st.session_state.edit_idx = idx
                    st.rerun()
                if st.button("Remove", key=f"remove_{idx}"):
                    remove_line(idx)
                    st.rerun()

            if st.session_state.edit_idx == idx:
                edit = st.container(border=True)
                edit.markdown("**Edit Line**")
                new_qty = edit.number_input("Quantity", min_value=1, value=int(line.qty), step=1, key=f"edit_qty_{idx}")

                if line.key.kind == "combo":
                    new_tier = edit.selectbox(
                        "Combo size",
                        list(COMBO_TIERS.keys()),
                        index=list(COMBO_TIERS.keys()).index(line.key.item_id),
                        key=f"edit_tier_{idx}",
                    )
                    new_protein = edit.selectbox(
                        "Protein",
                        PROTEINS,
                        index=PROTEINS.index(line.key.protein),
                        key=f"edit_protein_{idx}",
                    )
                    new_griddle = edit.selectbox(
                        "Griddle item",
                        GRIDDLE_CHOICES,
                        index=GRIDDLE_CHOICES.index(line.key.griddle),
                        key=f"edit_griddle_{idx}",
                    )
                    new_label = f"{new_tier} | {new_protein} | {new_griddle}"
                    new_key = LineKey(kind="combo", item_id=new_tier, protein=new_protein, griddle=new_griddle)
                else:
                    current_base_label = line.label.split(" | ", 1)[0] if " | " in line.label else line.label
                    default_index = ALACARTE_LABELS.index(current_base_label) if current_base_label in ALACARTE_LABELS else 0
                    new_label_base = edit.selectbox("Item", ALACARTE_LABELS, index=default_index, key=f"edit_al_{idx}")
                    new_item_id = AL_LABEL_TO_ID[new_label_base]

                    if new_item_id == "cold_bag":
                        existing_bev = line.key.beverage_type or COLD_BEV_TYPES[0]
                        new_bev = edit.selectbox(
                            "Cold beverage type",
                            COLD_BEV_TYPES,
                            index=COLD_BEV_TYPES.index(existing_bev),
                            key=f"edit_bev_{idx}",
                        )
                        new_label = f"{new_label_base} | {new_bev}"
                        new_key = LineKey(kind="alacarte", item_id=new_item_id, beverage_type=new_bev)
                    else:
                        new_label = new_label_base
                        new_key = LineKey(kind="alacarte", item_id=new_item_id)

                s1, s2 = edit.columns(2)
                if s1.button("Save", key=f"save_{idx}", type="primary"):
                    st.session_state.lines.pop(idx)
                    st.session_state.edit_idx = None
                    merge_or_add_line(OrderLine(key=new_key, label=new_label, qty=int(new_qty)))
                    st.rerun()

                if s2.button("Cancel", key=f"cancel_{idx}"):
                    st.session_state.edit_idx = None
                    st.rerun()

        st.divider()
        if st.button("Clear Entire Order", type="secondary", use_container_width=True):
            st.session_state.lines = []
            st.session_state.edit_idx = None
            st.rerun()

st.divider()

# =========================================================
# OUTPUT (on-screen) + PDF
# =========================================================
st.subheader("Day-Of Output")

if not st.session_state.lines:
    st.caption("Build an order above to generate the day-of sheet.")
else:
    totals = compute_order_totals(st.session_state.lines)
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)

    # 1) Order Summary
    st.markdown("## 1) Order Summary")
    for ol in st.session_state.lines:
        st.write(f"• {ol.label} (Qty {ol.qty})")

    # Counts + utensil note (simple)
    st.markdown("### Counts")
    st.write(f"• Headcount: {int(headcount)}")
    st.write(f"• Utensil sets ordered: {int(ordered_utensils)}")
    if headcount > 0:
        st.write(f"• Utensil sets recommended: {int(headcount)}")
        if ordered_utensils > 0 and ordered_utensils < headcount:
            st.error(f"Utensil mismatch: ordered {int(ordered_utensils)} but headcount is {int(headcount)}.")

    st.divider()

    # 2) Food Prep Totals
    st.markdown("## 2) Food Prep Totals")
    prep_lines = build_prep_lines(totals)
    for line in prep_lines:
        # preserve any embedded newlines
        if "\n" in line:
            first, rest = line.split("\n", 1)
            st.write("• " + first)
            for sub in rest.split("\n"):
                st.write("  " + sub)
        else:
            st.write("• " + line)

    st.divider()

    # 3) Packaging Totals (clarified)
    st.markdown("## 3) Packaging Totals")
    pack_rows = []
    if totals.get("aluminum_pans", 0) > 0:
        pack_rows.append({"Packaging": "Aluminum", "Total": f"{int(totals['aluminum_pans'])} pans"})
    if totals.get("ihop_plastic_bases", 0) > 0:
        pack_rows.append({"Packaging": "IHOP Plastic", "Total": f"{int(totals['ihop_plastic_bases'])} bases"})
    if pack_rows:
        st.dataframe(pd.DataFrame(pack_rows), width="stretch", hide_index=True)
    else:
        st.caption("No packaging totals calculated for this order.")

    # 4) Condiments
    st.markdown("## 4) Condiments")
    cond_rows = []
    if totals.get("butter_ct", 0) > 0:
        cond_rows.append({"Condiment": "Butter packets", "Total": int(totals["butter_ct"])})
    if totals.get("syrup_ct", 0) > 0:
        cond_rows.append({"Condiment": "Syrup packets", "Total": int(totals["syrup_ct"])})
    if totals.get("ketchup_ct", 0) > 0:
        cond_rows.append({"Condiment": "Ketchup packets", "Total": int(totals["ketchup_ct"])})
    if totals.get("powdered_sugar_cups_2oz", 0) > 0:
        cond_rows.append({"Condiment": "Powdered sugar (2 oz cups)", "Total": int(totals["powdered_sugar_cups_2oz"])})
    if cond_rows:
        st.dataframe(pd.DataFrame(cond_rows), width="stretch", hide_index=True)
    else:
        st.caption("No condiment totals calculated for this order.")

    # 5) Serveware
    st.markdown("## 5) Serveware")
    serve_rows = []
    if totals.get("plates", 0) > 0:
        serve_rows.append({"Serveware": "Plates", "Total": int(totals["plates"])})
    if totals.get("serving_tongs", 0) > 0:
        serve_rows.append({"Serveware": "Serving tongs", "Total": int(totals["serving_tongs"])})
    if totals.get("serving_forks", 0) > 0:
        serve_rows.append({"Serveware": "Serving forks", "Total": int(totals["serving_forks"])})
    if ordered_utensils > 0:
        serve_rows.append({"Serveware": "Utensil sets (ordered)", "Total": int(ordered_utensils)})
    if headcount > 0:
        serve_rows.append({"Serveware": "Utensil sets (recommended)", "Total": int(headcount)})
    if serve_rows:
        st.dataframe(pd.DataFrame(serve_rows), width="stretch", hide_index=True)
    else:
        st.caption("No serveware totals calculated for this order.")

    st.divider()

    # PDF Download (replaces CSV)
    st.subheader("Print / PDF")
    pdf_bytes = generate_day_of_pdf(
        order_lines=st.session_state.lines,
        pickup_dt=pickup_dt,
        ready_dt=ready_dt,
        headcount=int(headcount),
        utensils_ordered=int(ordered_utensils),
        totals=totals,
    )

    st.download_button(
        "Download Day-Of PDF",
        data=pdf_bytes,
        file_name=f"day_of_catering_{APP_VERSION}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
