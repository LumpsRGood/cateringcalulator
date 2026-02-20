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
APP_VERSION = "v3.0.3"

st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", layout="wide")

# =========================================================
# Data model
# =========================================================
@dataclass(frozen=True)
class LineKey:
    kind: str  # "combo" | "main" | "alacarte"
    item_id: str
    protein: Optional[str] = None
    griddle: Optional[str] = None
    beverage_type: Optional[str] = None  # cold beverage type


@dataclass
class OrderLine:
    key: LineKey
    label: str
    qty: int
    canon_id: str


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


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def build_canon_id(key: LineKey) -> str:
    if key.kind == "combo":
        return "combo|" + "|".join([_norm(key.item_id), _norm(key.protein), _norm(key.griddle)])
    if key.kind in ("main", "alacarte"):
        if _norm(key.item_id) == "cold_beverage":
            return f"{key.kind}|cold_beverage|" + _norm(key.beverage_type)
        return f"{key.kind}|" + _norm(key.item_id)
    return _norm(key.kind) + "|" + _norm(key.item_id)


# =========================================================
# Your naming / parlance
# =========================================================
POTATOES_NAME = "Red Pots"
HAM_NAME = "Sampler Ham"

# =========================================================
# Core choices
# =========================================================
PROTEINS = ["Bacon", "Pork Sausage Links", HAM_NAME]
GRIDDLE_CHOICES = ["Buttermilk Pancakes", "French Toast"]

# =========================================================
# Combo specs (scaled by tier)
# =========================================================
COMBO_TIERS = {
    "Small Combo Box": {
        "eggs_oz": 40,
        "red_pots_oz": 60,
        "protein_pcs": 20,
        "pancakes_pcs": 20,
        "ft_slices": 10,
        "half_pans_eggs": 1,
        "half_pans_red_pots": 1,
        "ihop_large_bases_protein": 1,
        "half_pans_pancakes": 1,
        "half_pans_ft": 2,
        "butter_packets": 10,
        "syrup_packets": 10,
        "ketchup_packets": 10,
        "powdered_sugar_cups_2oz": 1,  # 1 cup per 10 slices
        "serving_forks": 2,
        "serving_tongs": 2,
        "serving_spoons": 0,
    },
    "Medium Combo Box": {
        "eggs_oz": 80,
        "red_pots_oz": 120,
        "protein_pcs": 40,
        "pancakes_pcs": 40,
        "ft_slices": 20,
        "half_pans_eggs": 2,
        "half_pans_red_pots": 2,
        "ihop_large_bases_protein": 2,
        "half_pans_pancakes": 2,
        "half_pans_ft": 4,
        "butter_packets": 20,
        "syrup_packets": 20,
        "ketchup_packets": 20,
        "powdered_sugar_cups_2oz": 2,
        "serving_forks": 2,
        "serving_tongs": 2,
        "serving_spoons": 0,
    },
    "Large Combo Box": {
        "eggs_oz": 160,
        "red_pots_oz": 240,
        "protein_pcs": 80,
        "pancakes_pcs": 80,
        "ft_slices": 40,
        "half_pans_eggs": 4,
        "half_pans_red_pots": 4,
        "ihop_large_bases_protein": 4,
        "half_pans_pancakes": 4,
        "half_pans_ft": 8,
        "butter_packets": 40,
        "syrup_packets": 40,
        "ketchup_packets": 40,
        "powdered_sugar_cups_2oz": 4,
        "serving_forks": 8,
        "serving_tongs": 5,
        "serving_spoons": 0,
    },
}

# =========================================================
# MAIN items
# =========================================================
COLD_BEV_TYPES = ["Apple Juice", "Orange Juice", "Iced Tea", "Lemonade", "Soda"]

MAIN_ITEMS = [
    ("steakburgers_10", "Steakburgers (10 pcs)"),
    ("crispy_chx_sand_10", "Crispy Chicken Sandwiches (10 pcs)"),
    ("grilled_chx_sand_10", "Grilled Chicken Sandwiches (10 pcs)"),
    ("chicken_strips_40", "Chicken Strips (40 pcs)"),
    ("cold_beverage", "Cold Beverage (128 oz)"),
    ("coffee_box", "Coffee Box (96 oz)"),
]
MAIN_LABELS = [label for _, label in MAIN_ITEMS]
MAIN_LABEL_TO_ID = {label: item_id for item_id, label in MAIN_ITEMS}

# =========================================================
# À LA CARTE (hidden unless expanded)
# =========================================================
ALACARTE_GROUPS = [
    ("Griddle (Optional)", [
        ("pancakes_20", "Buttermilk Pancakes (20 pcs)", {"pancakes_pcs": 20}),
        ("ft_10_slices", "French Toast (10 slices)", {"ft_slices": 10}),
    ]),
    ("Breakfast (Optional)", [
        ("eggs_40oz", "Scrambled Eggs (40 oz)", {"eggs_oz": 40}),
        ("red_pots_40oz", f"{POTATOES_NAME} (40 oz)", {"red_pots_oz": 40}),
        ("bacon_20", "Bacon (20 pcs)", {"bacon_pcs": 20}),
        ("sausage_20", "Pork Sausage Links (20 pcs)", {"sausage_pcs": 20}),
        ("ham_20", f"{HAM_NAME} (20 pcs)", {"ham_pcs": 20}),
    ]),
    ("Lunch (Optional)", [
        ("fries_60oz", "French Fries (60 oz)", {"fries_oz": 60}),
        ("onion_rings_approx", "Onion Rings (approx. 24 rings)", {"onion_rings_rings": 24}),
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
# Session state
# =========================================================
def init_state():
    if "lines" not in st.session_state:
        st.session_state.lines: List[OrderLine] = []
    if "edit_idx" not in st.session_state:
        st.session_state.edit_idx = None

    st.session_state.setdefault("_reset_combo", False)
    st.session_state.setdefault("_reset_main", False)
    st.session_state.setdefault("_reset_alacarte", False)

    # Main-page Build Order defaults
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

    if st.session_state._reset_main:
        st.session_state.main_item = MAIN_LABELS[0]
        st.session_state.main_qty = 1
        st.session_state.cold_bev_type_main = COLD_BEV_TYPES[0]
        st.session_state._reset_main = False
    else:
        st.session_state.setdefault("main_item", MAIN_LABELS[0])
        st.session_state.setdefault("main_qty", 1)
        st.session_state.setdefault("cold_bev_type_main", COLD_BEV_TYPES[0])

    if st.session_state._reset_alacarte:
        st.session_state.al_item = ALACARTE_LABELS[0]
        st.session_state.al_qty = 1
        st.session_state._reset_alacarte = False
    else:
        st.session_state.setdefault("al_item", ALACARTE_LABELS[0])
        st.session_state.setdefault("al_qty", 1)

    # Timing / counts defaults
    st.session_state.setdefault("pickup_date", datetime.now().date())
    st.session_state.setdefault("pickup_time", datetime.now().replace(second=0, microsecond=0).time())
    st.session_state.setdefault("headcount", 0)

    # SOP guest request toggles (default ON)
    st.session_state.setdefault("req_plates", True)
    st.session_state.setdefault("req_utensils", True)
    st.session_state.setdefault("req_napkins", True)


def merge_or_add_line(new_line: OrderLine):
    for i, line in enumerate(st.session_state.lines):
        if getattr(line, "canon_id", "") == new_line.canon_id:
            st.session_state.lines[i].qty += new_line.qty
            return
    st.session_state.lines.append(new_line)


def remove_line(idx: int):
    st.session_state.lines.pop(idx)
    if st.session_state.edit_idx == idx:
        st.session_state.edit_idx = None


def reset_combo_form():
    st.session_state._reset_combo = True


def reset_main_form():
    st.session_state._reset_main = True


def reset_alacarte_form():
    st.session_state._reset_alacarte = True


# =========================================================
# Buckets
# =========================================================
def _add(d: Dict[str, float], k: str, v: float):
    d[k] = d.get(k, 0) + v


def compute_buckets(lines: List[OrderLine]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
    food: Dict[str, float] = {}
    packaging: Dict[str, float] = {}
    guestware: Dict[str, float] = {}
    service: Dict[str, float] = {}
    cond: Dict[str, float] = {}

    def F(k, v): _add(food, k, v)
    def P(k, v): _add(packaging, k, v)
    def G(k, v): _add(guestware, k, v)
    def S(k, v): _add(service, k, v)
    def C(k, v): _add(cond, k, v)

    for line in lines:
        qty = int(line.qty)

        # Combo Boxes
        if line.key.kind == "combo":
            tier = line.key.item_id
            protein = line.key.protein
            griddle = line.key.griddle
            spec = COMBO_TIERS[tier]

            F("Scrambled Eggs (oz)", spec["eggs_oz"] * qty)
            F(f"{POTATOES_NAME} (oz)", spec["red_pots_oz"] * qty)

            if protein == "Bacon":
                F("Bacon (pcs)", spec["protein_pcs"] * qty)
                P("IHOP Large Plastic Base", spec["ihop_large_bases_protein"] * qty)
            elif protein == "Pork Sausage Links":
                F("Pork Sausage Links (pcs)", spec["protein_pcs"] * qty)
                P("IHOP Large Plastic Base", spec["ihop_large_bases_protein"] * qty)
            elif protein == HAM_NAME:
                F(f"{HAM_NAME} (pcs)", spec["protein_pcs"] * qty)
                P("IHOP Large Plastic Base", spec["ihop_large_bases_protein"] * qty)

            if griddle == "Buttermilk Pancakes":
                F("Buttermilk Pancakes (pcs)", spec["pancakes_pcs"] * qty)
                P("Aluminum ½ Pans", spec["half_pans_pancakes"] * qty)
            else:
                F("French Toast (slices)", spec["ft_slices"] * qty)
                P("Aluminum ½ Pans", spec["half_pans_ft"] * qty)
                C("Powdered Sugar Cups (2 oz)", spec["powdered_sugar_cups_2oz"] * qty)

            P("Aluminum ½ Pans", (spec["half_pans_eggs"] + spec["half_pans_red_pots"]) * qty)

            C("Butter Packets", spec["butter_packets"] * qty)
            C("Syrup Packets", spec["syrup_packets"] * qty)
            C("Ketchup Packets", spec["ketchup_packets"] * qty)

            # Service utensils (serving tools) are always needed
            S("Serving Tongs", spec["serving_tongs"] * qty)
            S("Serving Forks", spec["serving_forks"] * qty)
            if spec.get("serving_spoons", 0) > 0:
                S("Serving Spoons", spec["serving_spoons"] * qty)

        # Main items (sandwiches, strips, beverages)
        elif line.key.kind == "main":
            item = line.key.item_id

            if item in ("steakburgers_10", "crispy_chx_sand_10", "grilled_chx_sand_10"):
                if item == "steakburgers_10":
                    F("Steakburger Patties (pcs)", 10 * qty)
                else:
                    F("Chicken Sandwiches (pcs)", 10 * qty)

                F("Buns (pcs)", 10 * qty)
                F("Tomato Slices (pcs)", 20 * qty)
                F("Red Onion Rings (pcs)", 20 * qty)
                F("Lettuce Leaves (pcs)", 10 * qty)
                F("Pickle Chips (pcs)", 50 * qty)

                P("Aluminum ½ Pans", 2 * qty)     # sandwiches + toppings
                P("Soup Cups (8 oz)", 3 * qty)    # IHOP + BBQ + pickles

                # Serving tools are always needed
                S("Serving Tongs", 2 * qty)
                S("Serving Spoons", 2 * qty)

                C("Mayo Packets", 10 * qty)
                C("Ketchup Packets", 10 * qty)
                C("Mustard Packets", 10 * qty)

            elif item == "chicken_strips_40":
                F("Chicken Strips (pcs)", 40 * qty)
                P("Aluminum ½ Pans", 1 * qty)
                P("Soup Cups (8 oz)", 3 * qty)    # BBQ + IHOP + Ranch

                S("Serving Tongs", 1 * qty)
                S("Serving Spoons", 3 * qty)

            elif item == "cold_beverage":
                bev = line.key.beverage_type or "Cold Beverage"
                F(f"Cold Beverage (128 oz) - {bev}", 1 * qty)
                P("Beverage Pouches", 1 * qty)
                # Cups/lids/straws are guest-request items; handled by headcount toggles

            elif item == "coffee_box":
                F("Coffee Box (96 oz)", 1 * qty)
                P("Hot Beverage Containers", 1 * qty)
                # Cups/lids/sleeves/stirrers/sugar/creamer can be treated as guest-request items; handled by toggles

        # À la carte
        elif line.key.kind == "alacarte":
            spec = ALACARTE_LOOKUP[line.key.item_id]["payload"]

            if "pancakes_pcs" in spec:
                F("Buttermilk Pancakes (pcs)", spec["pancakes_pcs"] * qty)
                P("Aluminum ½ Pans", 2 * qty)
                C("Butter Packets", 20 * qty)
                C("Syrup Packets", 20 * qty)
                S("Serving Tongs", 2 * qty)

            if "ft_slices" in spec:
                F("French Toast (slices)", spec["ft_slices"] * qty)
                P("Aluminum ½ Pans", 2 * qty)
                C("Butter Packets", 10 * qty)
                C("Syrup Packets", 10 * qty)
                C("Powdered Sugar Cups (2 oz)", 1 * qty)
                S("Serving Tongs", 1 * qty)

            if "eggs_oz" in spec:
                F("Scrambled Eggs (oz)", spec["eggs_oz"] * qty)
                P("Aluminum ½ Pans", 1 * qty)

            if "red_pots_oz" in spec:
                F(f"{POTATOES_NAME} (oz)", spec["red_pots_oz"] * qty)
                P("Aluminum ½ Pans", 1 * qty)

            if "bacon_pcs" in spec:
                F("Bacon (pcs)", spec["bacon_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

            if "sausage_pcs" in spec:
                F("Pork Sausage Links (pcs)", spec["sausage_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

            if "ham_pcs" in spec:
                F(f"{HAM_NAME} (pcs)", spec["ham_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

            if "fries_oz" in spec:
                F("French Fries (oz)", spec["fries_oz"] * qty)
                P("Aluminum ½ Pans", 1 * qty)
                S("Serving Tongs", 1 * qty)
                C("Ketchup Packets", 10 * qty)

            if "onion_rings_rings" in spec:
                F("Onion Rings (rings)", spec["onion_rings_rings"] * qty)
                P("Aluminum ½ Pans", 2 * qty)
                S("Serving Tongs", 1 * qty)
                C("Ketchup Packets", 10 * qty)

    return food, packaging, guestware, service, cond


def apply_headcount_guestware(
    guestware: Dict[str, float],
    cond: Dict[str, float],
    headcount: int,
    req_plates: bool,
    req_utensils: bool,
    req_napkins: bool,
    has_cold_bev: bool,
    has_hot_bev: bool,
):
    """
    SOP guest-request logic:
    - If requested, calculate based on headcount.
    - If not requested, do not include.
    """
    hc = int(headcount or 0)
    if hc <= 0:
        return

    if req_plates:
        _add(guestware, "Paper Plates", hc)

    if req_utensils:
        _add(guestware, "Utensil Sets", hc)

    if req_napkins:
        _add(guestware, "Napkins", hc)

    # Beverages: only include cups/lids/straws if utensils are requested (or you can separate later)
    if req_utensils:
        if has_cold_bev:
            _add(guestware, "Cold Cups", hc)
            _add(guestware, "Cold Lids", hc)
            _add(guestware, "Straws", hc)
        if has_hot_bev:
            _add(guestware, "Hot Cups", hc)
            _add(guestware, "Hot Lids", hc)
            _add(guestware, "Sleeves", hc)
            _add(guestware, "Stirrers", hc)
            _add(cond, "Sugar Packets", hc)
            _add(cond, "Creamers", hc)


# =========================================================
# Prep formatting helpers (Food Prep Totals)
# =========================================================
def eggs_prep_line_from_oz(eggs_oz: float) -> str:
    # Inferred conversion earlier: ~0.465 qt per lb
    lbs = ounces_to_lbs(eggs_oz)
    quarts = lbs * 0.465
    quarts_r = friendly_round_up(quarts, inc=0.5, tiny_over=0.05)
    cambros_4qt = quarts_r / 4.0
    return f"Scrambled Eggs: {quarts_r:g} qt (≈ {cambros_4qt:.1f} of a 4-qt Cambro)"


def oz_line(label: str, oz: float) -> str:
    lbs = ounces_to_lbs(oz)
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05) if lbs > 0 else 0
    return f"{label}: {int(oz)} oz (≈ {lbs_r:g} lb)"


def build_food_prep_lines(food: Dict[str, float]) -> List[str]:
    lines: List[str] = []

    eggs_oz = food.get("Scrambled Eggs (oz)", 0)
    if eggs_oz:
        lines.append(eggs_prep_line_from_oz(eggs_oz))

    rp_oz = food.get(f"{POTATOES_NAME} (oz)", 0)
    if rp_oz:
        lines.append(oz_line(POTATOES_NAME, rp_oz))

    fries_oz = food.get("French Fries (oz)", 0)
    if fries_oz:
        lines.append(oz_line("French Fries", fries_oz))

    count_keys = [
        "Buttermilk Pancakes (pcs)",
        "French Toast (slices)",
        "Bacon (pcs)",
        "Pork Sausage Links (pcs)",
        f"{HAM_NAME} (pcs)",
        "Chicken Strips (pcs)",
        "Steakburger Patties (pcs)",
        "Chicken Sandwiches (pcs)",
        "Buns (pcs)",
        "Tomato Slices (pcs)",
        "Red Onion Rings (pcs)",
        "Lettuce Leaves (pcs)",
        "Pickle Chips (pcs)",
        "Onion Rings (rings)",
    ]
    for k in count_keys:
        v = food.get(k, 0)
        if v:
            label = k.replace(" (pcs)", "").replace(" (slices)", "").replace(" (rings)", "")
            lines.append(f"{label}: {int(v)}")

    for k, v in food.items():
        if k.startswith("Cold Beverage (128 oz)"):
            lines.append(f"{k}: {int(v)}")

    coffee_boxes = food.get("Coffee Box (96 oz)", 0)
    if coffee_boxes:
        lines.append(f"Coffee Box (96 oz): {int(coffee_boxes)}")

    return lines


# =========================================================
# PDF Generation (Day-Of Sheet)
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
        for para in str(raw).split("\n"):
            wrapped = simpleSplit(prefix + para, font_name, font_size, max_width)
            for w in wrapped:
                if y <= bottom_margin:
                    c.showPage()
                    y = letter[1] - 0.75 * inch
                    c.setFont(font_name, font_size)
                c.drawString(x, y, w)
                y -= leading
            prefix = "  " if bullet else ""
    return y


def generate_day_of_pdf(
    order_lines: List[OrderLine],
    pickup_dt: datetime,
    ready_dt: datetime,
    headcount: int,
    req_plates: bool,
    req_utensils: bool,
    req_napkins: bool,
    food: Dict[str, float],
    packaging: Dict[str, float],
    guestware: Dict[str, float],
    service: Dict[str, float],
    cond: Dict[str, float],
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

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, f"{APP_NAME} (Day-Of Sheet)")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - right, y, f"{APP_VERSION}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Timing")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Ready Time:  {ready_dt.strftime('%Y-%m-%d %I:%M %p')}")
    y -= 12
    c.drawString(left, y, f"Pickup Time: {pickup_dt.strftime('%Y-%m-%d %I:%M %p')}")
    y -= 14

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Counts")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Headcount: {int(headcount)}")
    y -= 12
    c.drawString(left, y, f"Guest requested plates: {'Yes' if req_plates else 'No'}")
    y -= 12
    c.drawString(left, y, f"Guest requested utensils: {'Yes' if req_utensils else 'No'}")
    y -= 12
    c.drawString(left, y, f"Guest requested napkins: {'Yes' if req_napkins else 'No'}")
    y -= 12

    y -= 6
    c.line(left, y, width - right, y)
    y -= 16

    y = _pdf_draw_section_title(c, "1) Order Summary", left, y)
    summary_lines = [f"{ol.label}  (Qty {ol.qty})" for ol in order_lines]
    y = _pdf_draw_wrapped_lines(c, summary_lines, left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "2) Food Prep Totals", left, y)
    prep_lines = build_food_prep_lines(food)
    y = _pdf_draw_wrapped_lines(c, prep_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "3) Packaging", left, y)
    pack_lines = []
    for k in ["Aluminum ½ Pans", "IHOP Large Plastic Base", "Soup Cups (8 oz)", "Beverage Pouches", "Hot Beverage Containers"]:
        v = packaging.get(k, 0)
        if v:
            pack_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, pack_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "4) Plates & Cups", left, y)
    g_lines = []
    for k in ["Paper Plates", "Utensil Sets", "Napkins", "Cold Cups", "Cold Lids", "Hot Cups", "Hot Lids", "Sleeves", "Straws", "Stirrers"]:
        v = guestware.get(k, 0)
        if v:
            g_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, g_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "5) Service Utensils", left, y)
    s_lines = []
    for k in ["Serving Tongs", "Serving Spoons", "Serving Forks"]:
        v = service.get(k, 0)
        if v:
            s_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, s_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "6) Condiment Bag", left, y)
    c_lines = []
    for k in [
        "Butter Packets",
        "Syrup Packets",
        "Ketchup Packets",
        "Mustard Packets",
        "Mayo Packets",
        "Sugar Packets",
        "Creamers",
        "Powdered Sugar Cups (2 oz)",
    ]:
        v = cond.get(k, 0)
        if v:
            c_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, c_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(width - right, bottom - 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')} • {APP_VERSION}")

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================================================
# App Start
# =========================================================
init_state()

st.title(f"{APP_NAME} {APP_VERSION}")
st.caption("Operational mode. Additive math. No SKUs. Toppings and beverage packaging are automatic.")

# =========================================================
# MAIN PAGE TOP: Timing (col1) + Headcount (col2)
# =========================================================
top1, top2 = st.columns(2)

with top1:
    st.subheader("Timing")
    st.date_input("Pickup date", key="pickup_date")
    st.time_input("Pickup time", key="pickup_time")
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)
    st.metric("Ready time", ready_dt.strftime("%Y-%m-%d %I:%M %p"))
    st.metric("Pickup time", pickup_dt.strftime("%Y-%m-%d %I:%M %p"))

with top2:
    st.subheader("Headcount")
    st.number_input("Headcount (if provided)", min_value=0, value=int(st.session_state.headcount), step=1, key="headcount")

    st.markdown("**Guest Requested**")
    st.toggle("Plates", key="req_plates")
    st.toggle("Utensils", key="req_utensils")
    st.toggle("Napkins", key="req_napkins")

st.divider()

# =========================================================
# MAIN PAGE: Build Order
# =========================================================
st.subheader("Build Order")

st.markdown("### Breakfast Combo Boxes")
b1, b2, b3, b4 = st.columns([3, 3, 3, 2])
with b1:
    st.selectbox("Combo size", list(COMBO_TIERS.keys()), key="combo_tier")
with b2:
    st.selectbox("Protein", PROTEINS, key="combo_protein")
with b3:
    st.selectbox("Griddle item", GRIDDLE_CHOICES, key="combo_griddle")
with b4:
    st.number_input("Qty", min_value=1, value=int(st.session_state.combo_qty), step=1, key="combo_qty")

if st.button("Add Combo", type="primary", use_container_width=True):
    tier = st.session_state.combo_tier
    protein = st.session_state.combo_protein
    griddle = st.session_state.combo_griddle
    qty = int(st.session_state.combo_qty)

    label = f"{tier} | {protein} | {griddle}"
    key = LineKey(kind="combo", item_id=tier, protein=protein, griddle=griddle)
    canon_id = build_canon_id(key)
    merge_or_add_line(OrderLine(key=key, label=label, qty=qty, canon_id=canon_id))
    reset_combo_form()
    st.rerun()

st.divider()

st.markdown("### Sandwiches, Strips, Beverages")
m1, m2, m3 = st.columns([6, 2, 4])

with m1:
    st.selectbox("Select item", MAIN_LABELS, key="main_item")
with m2:
    st.number_input("Qty", min_value=1, value=int(st.session_state.main_qty), step=1, key="main_qty")
with m3:
    main_item_id = MAIN_LABEL_TO_ID[st.session_state.main_item]
    if main_item_id == "cold_beverage":
        st.selectbox("Cold beverage type", COLD_BEV_TYPES, key="cold_bev_type_main")
    else:
        st.caption("")

if st.button("Add Item", type="primary", use_container_width=True):
    item_id = MAIN_LABEL_TO_ID[st.session_state.main_item]
    qty = int(st.session_state.main_qty)

    if item_id == "cold_beverage":
        bev_type = st.session_state.get("cold_bev_type_main", COLD_BEV_TYPES[0])
        label = f"{st.session_state.main_item} | {bev_type}"
        key = LineKey(kind="main", item_id=item_id, beverage_type=bev_type)
    else:
        label = st.session_state.main_item
        key = LineKey(kind="main", item_id=item_id)

    canon_id = build_canon_id(key)
    merge_or_add_line(OrderLine(key=key, label=label, qty=qty, canon_id=canon_id))
    reset_main_form()
    st.rerun()

st.divider()

with st.container(border=True):
    st.markdown("### Additional Options")
    st.caption("Rare use. Only open this section if the order includes extra items.")

    with st.expander("➕ À La Carte Items (Optional)  Click to open", expanded=False):
        a1, a2 = st.columns([6, 2])
        with a1:
            st.selectbox("À la carte item", ALACARTE_LABELS, key="al_item")
        with a2:
            st.number_input("Qty", min_value=1, value=int(st.session_state.al_qty), step=1, key="al_qty")

        if st.button("Add À La Carte", use_container_width=True):
            item_id = AL_LABEL_TO_ID[st.session_state.al_item]
            qty = int(st.session_state.al_qty)
            label = st.session_state.al_item
            key = LineKey(kind="alacarte", item_id=item_id)
            canon_id = build_canon_id(key)
            merge_or_add_line(OrderLine(key=key, label=label, qty=qty, canon_id=canon_id))
            reset_alacarte_form()
            st.rerun()

st.divider()

# =========================================================
# SIDEBAR: Current Order ONLY
# =========================================================
with st.sidebar:
    st.subheader("Current Order")

    if not st.session_state.lines:
        st.info("No items yet. Build the order on the main screen.")
    else:
        for idx, line in enumerate(st.session_state.lines):
            box = st.container(border=True)
            c1, c2 = box.columns([5, 2])

            with c1:
                st.markdown(f"**{line.label}**")
                st.caption(f"Qty: {line.qty}")

            with c2:
                if st.button("✏️", key=f"edit_{idx}", help="Edit item"):
                    st.session_state.edit_idx = idx
                    st.rerun()
                if st.button("🗑️", key=f"remove_{idx}", help="Remove item"):
                    remove_line(idx)
                    st.rerun()

            if st.session_state.edit_idx == idx:
                edit = st.container(border=True)
                edit.markdown("**Edit Line**")
                new_qty = edit.number_input(
                    "Quantity",
                    min_value=1,
                    value=int(line.qty),
                    step=1,
                    key=f"edit_qty_{idx}",
                )

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

                elif line.key.kind == "main":
                    base_label = line.label.split(" | ", 1)[0] if " | " in line.label else line.label
                    default_index = MAIN_LABELS.index(base_label) if base_label in MAIN_LABELS else 0
                    new_main_label = edit.selectbox(
                        "Item",
                        MAIN_LABELS,
                        index=default_index,
                        key=f"edit_main_{idx}",
                    )
                    new_item_id = MAIN_LABEL_TO_ID[new_main_label]
                    if new_item_id == "cold_beverage":
                        existing_bev = line.key.beverage_type or COLD_BEV_TYPES[0]
                        new_bev = edit.selectbox(
                            "Cold beverage type",
                            COLD_BEV_TYPES,
                            index=COLD_BEV_TYPES.index(existing_bev),
                            key=f"edit_main_bev_{idx}",
                        )
                        new_label = f"{new_main_label} | {new_bev}"
                        new_key = LineKey(kind="main", item_id=new_item_id, beverage_type=new_bev)
                    else:
                        new_label = new_main_label
                        new_key = LineKey(kind="main", item_id=new_item_id)

                else:  # alacarte
                    base_label = line.label
                    default_index = ALACARTE_LABELS.index(base_label) if base_label in ALACARTE_LABELS else 0
                    new_al_label = edit.selectbox(
                        "Item",
                        ALACARTE_LABELS,
                        index=default_index,
                        key=f"edit_al_{idx}",
                    )
                    new_item_id = AL_LABEL_TO_ID[new_al_label]
                    new_label = new_al_label
                    new_key = LineKey(kind="alacarte", item_id=new_item_id)

                new_canon_id = build_canon_id(new_key)

                s1, s2 = edit.columns(2)
                if s1.button("Save", key=f"save_{idx}", type="primary"):
                    st.session_state.lines.pop(idx)
                    st.session_state.edit_idx = None
                    merge_or_add_line(OrderLine(key=new_key, label=new_label, qty=int(new_qty), canon_id=new_canon_id))
                    st.rerun()

                if s2.button("Cancel", key=f"cancel_{idx}"):
                    st.session_state.edit_idx = None
                    st.rerun()

        st.divider()
        if st.button("Clear Entire Order", type="secondary", use_container_width=True):
            st.session_state.lines = []
            st.session_state.edit_idx = None
            st.rerun()

# =========================================================
# OUTPUT + PDF
# =========================================================
st.subheader("Day-Of Output")

if not st.session_state.lines:
    st.caption("Build an order above to generate the day-of sheet.")
else:
    food, packaging, guestware, service, cond = compute_buckets(st.session_state.lines)

    # Determine if beverages exist (for cups/lids logic)
    has_cold_bev = any(l.key.kind == "main" and l.key.item_id == "cold_beverage" for l in st.session_state.lines)
    has_hot_bev = any(l.key.kind == "main" and l.key.item_id == "coffee_box" for l in st.session_state.lines)

    apply_headcount_guestware(
        guestware=guestware,
        cond=cond,
        headcount=int(st.session_state.headcount),
        req_plates=bool(st.session_state.req_plates),
        req_utensils=bool(st.session_state.req_utensils),
        req_napkins=bool(st.session_state.req_napkins),
        has_cold_bev=has_cold_bev,
        has_hot_bev=has_hot_bev,
    )

    st.markdown("## Food Prep Totals")
    prep_lines = build_food_prep_lines(food)
    for line in prep_lines or ["None"]:
        st.write(f"• {line}")

    st.divider()

    st.markdown("## Packaging")
    pack_rows = []
    for k in ["Aluminum ½ Pans", "IHOP Large Plastic Base", "Soup Cups (8 oz)", "Beverage Pouches", "Hot Beverage Containers"]:
        v = packaging.get(k, 0)
        if v:
            pack_rows.append({"Packaging": k, "Total": int(v)})
    if pack_rows:
        st.dataframe(pd.DataFrame(pack_rows), width="stretch", hide_index=True)
    else:
        st.caption("None")

    st.markdown("## Plates & Cups")
    guest_rows = []
    for k in ["Paper Plates", "Utensil Sets", "Napkins", "Cold Cups", "Cold Lids", "Hot Cups", "Hot Lids", "Sleeves", "Straws", "Stirrers"]:
        v = guestware.get(k, 0)
        if v:
            guest_rows.append({"Item": k, "Total": int(v)})
    if guest_rows:
        st.dataframe(pd.DataFrame(guest_rows), width="stretch", hide_index=True)
    else:
        st.caption("None")

    st.markdown("## Condiment Bag")
    cond_rows = []
    for k in [
        "Butter Packets",
        "Syrup Packets",
        "Ketchup Packets",
        "Mustard Packets",
        "Mayo Packets",
        "Sugar Packets",
        "Creamers",
        "Powdered Sugar Cups (2 oz)",
    ]:
        v = cond.get(k, 0)
        if v:
            cond_rows.append({"Condiment": k, "Total": int(v)})
    if cond_rows:
        st.dataframe(pd.DataFrame(cond_rows), width="stretch", hide_index=True)
    else:
        st.caption("None")

    st.markdown("## Service Utensils")
    serv_rows = []
    for k in ["Serving Tongs", "Serving Spoons", "Serving Forks"]:
        v = service.get(k, 0)
        if v:
            serv_rows.append({"Utensil": k, "Total": int(v)})
    if serv_rows:
        st.dataframe(pd.DataFrame(serv_rows), width="stretch", hide_index=True)
    else:
        st.caption("None")

    st.divider()

    st.subheader("Print / PDF")
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)

    pdf_bytes = generate_day_of_pdf(
        order_lines=st.session_state.lines,
        pickup_dt=pickup_dt,
        ready_dt=ready_dt,
        headcount=int(st.session_state.headcount),
        req_plates=bool(st.session_state.req_plates),
        req_utensils=bool(st.session_state.req_utensils),
        req_napkins=bool(st.session_state.req_napkins),
        food=food,
        packaging=packaging,
        guestware=guestware,
        service=service,
        cond=cond,
    )

    st.download_button(
        "Download Day-Of PDF",
        data=pdf_bytes,
        file_name=f"day_of_catering_{APP_VERSION}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
