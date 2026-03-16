import base64
import io
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from pypdf import PdfReader, PdfWriter

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


APP_NAME = "Catering Calculator"
APP_VERSION = "v3.2"

st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", layout="wide")


# =========================================================
# Data model
# =========================================================

@dataclass(frozen=True)
class LineKey:
    kind: str
    item_id: str
    protein: Optional[str] = None
    griddle: Optional[str] = None
    beverage_type: Optional[str] = None


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
    nearest_down = math.floor(x / inc) * inc
    if x - nearest_down <= tiny_over:
        return nearest_down
    return ceil_to_increment(x, inc)


def ounces_to_lbs(oz: float) -> float:
    return oz / 16.0


def compute_pickup_and_ready(pickup_date, pickup_time):
    pickup_dt = datetime.combine(pickup_date, pickup_time)
    ready_dt = pickup_dt - timedelta(minutes=10)
    return pickup_dt, ready_dt


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def build_canon_id(key: LineKey) -> str:

    if key.kind == "combo":
        return "combo|" + "|".join([
            _norm(key.item_id),
            _norm(key.protein),
            _norm(key.griddle)
        ])

    if key.kind in ("main", "alacarte"):

        if _norm(key.item_id) == "cold_beverage":
            return f"{key.kind}|cold_beverage|" + _norm(key.beverage_type)

        return f"{key.kind}|{_norm(key.item_id)}"

    return _norm(key.kind) + "|" + _norm(key.item_id)


def _add(d: Dict[str, float], k: str, v: float):
    d[k] = d.get(k, 0) + v


def _drop(d: Dict[str, float], k: str):
    if k in d:
        d.pop(k, None)

# =========================================================
# Meat / bag helpers
# =========================================================

SAUSAGE_LINK_OZ = 0.8
SAUSAGE_BAG_LB = 10.0

BACON_CASE_LB = 25.0
BACON_SERVINGS_PER_CASE = 225
BACON_SLICES_PER_SERVING = 2
BACON_SLICE_OZ = (BACON_CASE_LB * 16.0) / (BACON_SERVINGS_PER_CASE * BACON_SLICES_PER_SERVING)


def containers_plus_remainder_from_pcs(
    name: str,
    pcs: float,
    pc_oz: float,
    container_lb: float,
    container_name: str,
    piece_name: str,
) -> str:
    if not pcs:
        return ""

    pcs_i = int(round(pcs))
    total_oz = pcs_i * pc_oz
    total_lb = total_oz / 16.0

    full = int(total_lb // container_lb)
    rem_lb = total_lb - (full * container_lb)

    if full == 0:
        return f"{name}: {pcs_i} {piece_name} (≈ {total_lb:.2f} lb)"

    if rem_lb <= 0.01:
        word = container_name if full == 1 else f"{container_name}s"
        return f"{name}: {full} {word}"

    rem_oz = rem_lb * 16.0
    rem_pcs = int(round(rem_oz / pc_oz))
    word = container_name if full == 1 else f"{container_name}s"
    return f"{name}: {full} {word} PLUS {rem_pcs} {piece_name} (≈ {rem_lb:.2f} lb)"


def bag_and_portion_line_from_oz(
    name: str,
    total_oz: float,
    portion_oz: float,
    bag_lb: float,
) -> str:
    if not total_oz:
        return ""

    total_lb = ounces_to_lbs(total_oz)
    total_portions = int(round(total_oz / portion_oz))

    full_bags = int(total_lb // bag_lb)
    rem_lb = total_lb - (full_bags * bag_lb)
    rem_oz = rem_lb * 16

    if full_bags == 0:
        return f"{name}: {int(total_oz)} oz ({total_portions} portions / {total_lb:.2f} lb)"

    if rem_oz <= 0.01:
        bag_word = "bag" if full_bags == 1 else "bags"
        return f"{name}: {full_bags} {bag_word}"

    rem_portions = int(round(rem_oz / portion_oz))
    bag_word = "bag" if full_bags == 1 else "bags"
    return f"{name}: {full_bags} {bag_word} PLUS {int(round(rem_oz))} oz ({rem_portions} portions / {rem_lb:.2f} lb)"


def eggs_prep_line_from_oz(eggs_oz: float) -> str:
    if not eggs_oz:
        return ""

    total_lb = ounces_to_lbs(eggs_oz)
    bag_lb = 20.0
    qt_per_lb = 0.465

    full_bags = int(total_lb // bag_lb)
    rem_lb = total_lb - (full_bags * bag_lb)

    rem_qt = rem_lb * qt_per_lb
    rem_qt_r = friendly_round_up(rem_qt, inc=0.5, tiny_over=0.05)

    total_qt = total_lb * qt_per_lb
    total_qt_r = friendly_round_up(total_qt, inc=0.5, tiny_over=0.05)

    if full_bags == 0:
        return f"Scrambled Eggs: {total_qt_r:g} qt"

    if rem_qt_r <= 0:
        bag_word = "bag" if full_bags == 1 else "bags"
        return f"Scrambled Eggs: {full_bags} {bag_word}"

    bag_word = "bag" if full_bags == 1 else "bags"
    return f"Scrambled Eggs: {full_bags} {bag_word} PLUS {rem_qt_r:g} qt"

def merge_order_with_checklist(order_pdf_bytes: bytes) -> bytes:
    writer = PdfWriter()

    # Add generated order PDF pages
    order_reader = PdfReader(io.BytesIO(order_pdf_bytes))
    for page in order_reader.pages:
        writer.add_page(page)

    # Append static checklist PDF if present
    checklist_path = Path(__file__).with_name("checklist.pdf")
    if checklist_path.exists():
        checklist_reader = PdfReader(str(checklist_path))
        for page in checklist_reader.pages:
            writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()

# =========================================================
# Naming
# =========================================================

POTATOES_NAME = "Red Pots"
HAM_NAME = "Sampler Ham"

PROTEINS = [
    "Bacon",
    "Pork Sausage Links",
    HAM_NAME,
]

GRIDDLE_CHOICES = [
    "Buttermilk Pancakes",
    "French Toast",
]

# =========================================================
# Combo specs
# =========================================================

COMBO_TIERS = {

    "Small Combo Box": {
        "servings": 10,
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
        "powdered_sugar_cups_2oz": 1,
        "serving_forks": 2,
        "serving_tongs": 2,
        "serving_spoons": 0,
    },

    "Medium Combo Box": {
        "servings": 20,
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
        "servings": 40,
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
# Main items
# =========================================================

COLD_BEV_TYPES = [
    "Apple Juice",
    "Orange Juice",
    "Iced Tea",
    "Lemonade",
    "Soda",
]

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

MAIN_SERVINGS = {
    "steakburgers_10": 10,
    "crispy_chx_sand_10": 10,
    "grilled_chx_sand_10": 10,
    "chicken_strips_40": 10,
}

# =========================================================
# À la carte groups
# =========================================================

ALACARTE_GROUPS = [

    ("Griddle (Optional)", [

        ("pancakes_20", "Buttermilk Pancakes (20 pcs)", {
            "pancakes_pcs": 20,
            "servings": 20
        }),

        ("ft_10_slices", "French Toast (10 slices)", {
            "ft_slices": 10,
            "servings": 10
        }),
    ]),

    ("Breakfast (Optional)", [

        ("eggs_40oz", "Scrambled Eggs (40 oz)", {
            "eggs_oz": 40,
            "servings": 10
        }),

        ("red_pots_40oz", f"{POTATOES_NAME} (40 oz)", {
            "red_pots_oz": 40,
            "servings": 10
        }),

        ("bacon_20", "Bacon (20 pcs)", {
            "bacon_pcs": 20,
            "servings": 10
        }),

        ("sausage_20", "Pork Sausage Links (20 pcs)", {
            "sausage_pcs": 20,
            "servings": 10
        }),

        ("ham_20", f"{HAM_NAME} (20 pcs)", {
            "ham_pcs": 20,
            "servings": 10
        }),

        ("burritos_10", "Classic Breakfast Burritos (10 pcs)", {
            "burritos_pcs": 10,
            "servings": 10
        }),

        ("donut_dippers_70", "Donut Dippers (70 pcs)", {
            "donut_holes_pcs": 70,
            "servings": 10
        }),
    ]),

    ("Lunch (Optional)", [

        ("fries_60oz", "French Fries (60 oz)", {
            "fries_oz": 60,
            "servings": 10
        }),

        ("onion_rings_approx", "Onion Rings (approx. 24 rings)", {
            "onion_rings_rings": 24,
            "servings": 10
        }),

        ("fruit_40oz", "Fresh Fruit (40 oz)", {
            "fruit_oz": 40,
            "servings": 10
        }),

        ("salad_10", "Salad (10 servings)", {
            "salad_10": 1,
            "servings": 10
        }),
    ]),

    ("Toppings / Cold Items (Optional)", [

        ("strawberry_topping_40oz", "Strawberry Topping (40 oz)", {
            "strawberry_topping_oz": 40,
            "servings": 0
        }),

        ("blueberry_topping_40oz", "Blueberry Topping (40 oz)", {
            "blueberry_topping_oz": 40,
            "servings": 0
        }),
    ]),
]

ALACARTE_LOOKUP = {}
ALACARTE_LABELS = []
AL_LABEL_TO_ID = {}

for group_name, items in ALACARTE_GROUPS:
    for item_id, label, payload in items:

        ALACARTE_LOOKUP[item_id] = {
            "label": label,
            "payload": payload,
            "group": group_name,
        }

        ALACARTE_LABELS.append(label)
        AL_LABEL_TO_ID[label] = item_id

# =========================================================
# Order calculation engine
# =========================================================

def compute_order_data(lines):

    total_servings = 0

    food = {}
    packaging = {}
    guestware = {}
    service = {}
    cond = {}

    prep_blocks = {}

    def F(k,v): _add(food,k,v)
    def P(k,v): _add(packaging,k,v)
    def G(k,v): _add(guestware,k,v)
    def S(k,v): _add(service,k,v)
    def C(k,v): _add(cond,k,v)

    def ensure_block(key,title):
        if key not in prep_blocks:
            prep_blocks[key] = {
                "title": title,
                "lines": [],
                "pack_label": None,
                "pack_count": 0
            }

        return prep_blocks[key]

    for line in lines:

        qty = int(line.qty)

        # =========================================================
        # COMBOS
        # =========================================================

        if line.key.kind == "combo":

            tier = line.key.item_id
            protein = line.key.protein
            griddle = line.key.griddle

            spec = COMBO_TIERS[tier]

            total_servings += spec["servings"] * qty

            # eggs
            F("Scrambled Eggs (oz)", spec["eggs_oz"] * qty)
            P("Aluminum ½ Pans", spec["half_pans_eggs"] * qty)

            blk = ensure_block("eggs","Scrambled Eggs")
            blk["lines"].append(f'{spec["eggs_oz"]*qty} oz')
            blk["pack_label"] = "Aluminum ½ Pans"
            blk["pack_count"] += spec["half_pans_eggs"] * qty

            # red pots
            F(f"{POTATOES_NAME} (oz)", spec["red_pots_oz"] * qty)
            P("Aluminum ½ Pans", spec["half_pans_red_pots"] * qty)

            blk = ensure_block("red_pots",POTATOES_NAME)
            blk["lines"].append(f'{spec["red_pots_oz"]*qty} oz')
            blk["pack_label"] = "Aluminum ½ Pans"
            blk["pack_count"] += spec["half_pans_red_pots"] * qty

            # protein

            if protein == "Bacon":

                F("Bacon (pcs)", spec["protein_pcs"] * qty)

                blk = ensure_block("bacon","Bacon")
                blk["lines"].append(f'{spec["protein_pcs"]*qty} slices')

            elif protein == "Pork Sausage Links":

                F("Pork Sausage Links (pcs)", spec["protein_pcs"] * qty)

                blk = ensure_block("sausage","Pork Sausage Links")
                blk["lines"].append(f'{spec["protein_pcs"]*qty} links')

            else:

                F(f"{HAM_NAME} (pcs)", spec["protein_pcs"] * qty)

                blk = ensure_block("ham",HAM_NAME)
                blk["lines"].append(f'{spec["protein_pcs"]*qty} pcs')

            P("IHOP Large Plastic Base", spec["ihop_large_bases_protein"] * qty)

            # griddle

            if griddle == "Buttermilk Pancakes":

                F("Buttermilk Pancakes (pcs)", spec["pancakes_pcs"] * qty)

                blk = ensure_block("pancakes", "Buttermilk Pancakes")
                blk["qty_total"] = blk.get("qty_total", 0) + (spec["pancakes_pcs"] * qty)
                blk["unit"] = "pcs"
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += spec["half_pans_pancakes"] * qty

                P("Aluminum ½ Pans", spec["half_pans_pancakes"] * qty)

            else:

                F("French Toast (slices)", spec["ft_slices"] * qty)

                blk = ensure_block("french_toast", "French Toast")
                blk["lines"] = []
                blk["qty_total"] = blk.get("qty_total", 0) + (spec["ft_slices"] * qty)
                blk["unit"] = "slices"
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += spec["half_pans_ft"] * qty

                P("Aluminum ½ Pans", spec["half_pans_ft"] * qty)

                C("Powdered Sugar Cups (2 oz)", spec["powdered_sugar_cups_2oz"] * qty)
            C("Butter Packets", spec["butter_packets"] * qty)
            C("Syrup Packets", spec["syrup_packets"] * qty)
            C("Ketchup Packets", spec["ketchup_packets"] * qty)

            S("Serving Tongs", spec["serving_tongs"] * qty)
            S("Serving Forks", spec["serving_forks"] * qty)

        # =========================================================
        # MAIN ITEMS
        # =========================================================

        elif line.key.kind == "main":

            item = line.key.item_id

            if item in MAIN_SERVINGS:
                total_servings += MAIN_SERVINGS[item] * qty

            if item == "chicken_strips_40":

                F("Chicken Strips (pcs)",40*qty)
                P("Aluminum ½ Pans",1*qty)

                blk = ensure_block("strips","Chicken Strips")
                blk["lines"].append(f"{40*qty} pcs")
                blk["pack_label"]="Aluminum ½ Pans"
                blk["pack_count"] += 1*qty

                P("Soup Cups (8 oz)",3*qty)

                S("Serving Tongs",1*qty)
                S("Serving Spoons",3*qty)

            elif item in ["steakburgers_10","crispy_chx_sand_10","grilled_chx_sand_10"]:

                F("Sandwiches (pcs)",10*qty)
                F("Buns (pcs)",10*qty)

                P("Aluminum ½ Pans",1*qty)
                P("IHOP Large Plastic Base",1*qty)

                blk = ensure_block("sandwich","Sandwiches")
                blk["lines"].append(f"{10*qty} pcs")
                blk["pack_label"]="Aluminum ½ Pans"
                blk["pack_count"] += qty

                # toppings half pan (no pickles)

                blk = ensure_block("sand_toppings","Sandwich Toppings")
                blk["lines"] = [
                    f"{20*qty} Tomato slices",
                    f"{20*qty} Red onion rings",
                    f"{10*qty} Lettuce leaves",
                ]
                blk["pack_label"]="Aluminum ½ Pans"
                blk["pack_count"] += qty

                # sauces and pickles cups

                P("Soup Cups (8 oz)",3*qty)

                blk = ensure_block("sand_sauces","Sauces / Pickles")
                blk["lines"] = [
                    "IHOP Sauce",
                    "BBQ Sauce",
                    "Pickle Chips"
                ]
                blk["pack_label"]="Soup Cups (8 oz)"
                blk["pack_count"] += 3*qty

            elif item == "cold_beverage":

                bev = line.key.beverage_type or "Cold Beverage"

                F(f"Cold Beverage - {bev}",qty)

                P("Beverage Pouches",qty)

                G("Cold Cups",10*qty)
                G("Cold Lids",10*qty)
                G("Straws",10*qty)

            elif item == "coffee_box":

                F("Coffee Box",qty)

                P("Hot Beverage Containers",qty)

                G("Hot Cups",10*qty)
                G("Hot Lids",10*qty)
                G("Sleeves",10*qty)
                G("Stirrers",10*qty)

                C("Sugar Packets",10*qty)
                C("Creamers",10*qty)

        # =========================================================
        # A LA CARTE
        # =========================================================

        elif line.key.kind == "alacarte":

            spec = ALACARTE_LOOKUP[line.key.item_id]["payload"]

            total_servings += spec.get("servings", 0) * qty

            if "fruit_oz" in spec:
                P("IHOP Large Plastic Base", 1 * qty)
                S("Serving Forks", 1 * qty)

                blk = ensure_block("fruit", "Fresh Fruit")
                blk["lines"].append(f"{spec['fruit_oz'] * qty} oz")
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

            if "pancakes_pcs" in spec:
                F("Buttermilk Pancakes (pcs)", spec["pancakes_pcs"] * qty)
                P("Aluminum ½ Pans", 2 * qty)
                C("Butter Packets", 20 * qty)
                C("Syrup Packets", 20 * qty)
                S("Serving Tongs", 2 * qty)

                blk = ensure_block("pancakes", "Buttermilk Pancakes")
                blk["lines"] = []
                blk["qty_total"] = blk.get("qty_total", 0) + (spec["pancakes_pcs"] * qty)
                blk["unit"] = "pcs"
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += (2 * qty)

            if "ft_slices" in spec:
                F("French Toast (slices)", spec["ft_slices"] * qty)
                P("Aluminum ½ Pans", 2 * qty)
                C("Butter Packets", 10 * qty)
                C("Syrup Packets", 10 * qty)
                C("Powdered Sugar Cups (2 oz)", 1 * qty)
                S("Serving Tongs", 1 * qty)

                blk = ensure_block("french_toast", "French Toast")
                blk["lines"] = []
                blk["qty_total"] = blk.get("qty_total", 0) + (spec["ft_slices"] * qty)
                blk["unit"] = "slices"
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += (2 * qty)

            if "eggs_oz" in spec:
                F("Scrambled Eggs (oz)", spec["eggs_oz"] * qty)
                P("Aluminum ½ Pans", 1 * qty)

                blk = ensure_block("eggs", "Scrambled Eggs")
                blk["lines"].append(f"{spec['eggs_oz'] * qty} oz")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += qty

            if "red_pots_oz" in spec:
                F("Red Pots (oz)", spec["red_pots_oz"] * qty)
                P("Aluminum ½ Pans", 1 * qty)

                blk = ensure_block("red_pots", POTATOES_NAME)
                blk["lines"].append(f"{spec['red_pots_oz'] * qty} oz")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += qty

            if "bacon_pcs" in spec:
                F("Bacon (pcs)", spec["bacon_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

                blk = ensure_block("bacon", "Bacon")
                blk["lines"].append(f"{spec['bacon_pcs'] * qty} slices")
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

            if "sausage_pcs" in spec:
                F("Pork Sausage Links (pcs)", spec["sausage_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

                blk = ensure_block("sausage", "Pork Sausage Links")
                blk["lines"].append(f"{spec['sausage_pcs'] * qty} links")
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

            if "ham_pcs" in spec:
                F("Sampler Ham (pcs)", spec["ham_pcs"] * qty)
                P("IHOP Large Plastic Base", 1 * qty)

                blk = ensure_block("ham", HAM_NAME)
                blk["lines"] = []
                blk["qty_total"] = blk.get("qty_total", 0) + (spec["ham_pcs"] * qty)
                blk["unit"] = "pcs"
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

            if "fries_oz" in spec:
                F("French Fries (oz)", spec["fries_oz"] * qty)

                P("Aluminum ½ Pans", 1 * qty)
                S("Serving Tongs", 1 * qty)

                C("Ketchup Packets", 10 * qty)

                blk = ensure_block("fries", "French Fries")
                blk["lines"].append(f"{spec['fries_oz'] * qty} oz")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += qty

            if "onion_rings_rings" in spec:
                F("Onion Rings", spec["onion_rings_rings"] * qty)

                P("Aluminum ½ Pans", 2 * qty)
                S("Serving Tongs", 1 * qty)

                blk = ensure_block("rings", "Onion Rings")
                blk["lines"].append(f"{spec['onion_rings_rings'] * qty} rings")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += 2 * qty

            if "donut_holes_pcs" in spec:
                F("Donut Dippers", spec["donut_holes_pcs"] * qty)

                P("Aluminum ½ Pans", 1 * qty)
                P("Soup Cups (8 oz)", 4 * qty)

                S("Serving Spoons", 4 * qty)
                S("Serving Tongs", 1 * qty)

                blk = ensure_block("donuts", "Donut Dippers")
                blk["lines"].append(f"{spec['donut_holes_pcs'] * qty} pcs")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += qty

                blk = ensure_block("donut_icings", "Icings")
                blk["lines"] = [
                    f"{2 * qty} Cream Cheese Icing Cups",
                    f"{2 * qty} Dulce de Leche Cups"
                ]
                blk["pack_label"] = "Soup Cups (8 oz)"
                blk["pack_count"] += 4 * qty

            if "burritos_pcs" in spec:
                F("Breakfast Burritos", spec["burritos_pcs"] * qty)

                P("Aluminum ½ Pans", 2 * qty)
                P("Soup Cups (8 oz)", 2 * qty)

                S("Serving Spoons", 2 * qty)

                blk = ensure_block("burritos", "Classic Breakfast Burritos")
                blk["lines"].append(f"{spec['burritos_pcs'] * qty} pcs")
                blk["pack_label"] = "Aluminum ½ Pans"
                blk["pack_count"] += 2 * qty

                blk = ensure_block("burrito_salsa", "Salsa")
                blk["lines"].append(f"{16 * qty} oz")
                blk["pack_label"] = "Soup Cups (8 oz)"
                blk["pack_count"] += 2 * qty

            if "salad_10" in spec:
                P("IHOP Large Plastic Base", 1 * qty)
                P("Soup Cups (8 oz)", 1 * qty)

                S("Serving Spoons", 1 * qty)
                S("Serving Tongs", 1 * qty)

                blk = ensure_block("salad", "Salad")
                blk["lines"] = [
                    f"{5 * qty} portions Lettuce Blend",
                    f"{5 * qty} oz Cheese",
                    f"{5 * qty} oz Tomatoes",
                    f"{8 * qty} Red Onion Rings (quartered)"
                ]
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

                blk = ensure_block("salad_dressing", "Dressing")
                blk["lines"] = [f"{8 * qty} oz"]
                blk["pack_label"] = "Soup Cups (8 oz)"
                blk["pack_count"] += qty

            if "strawberry_topping_oz" in spec:
                P("IHOP Large Plastic Base", 1 * qty)
                S("Serving Forks", 1 * qty)

                blk = ensure_block("strawberry", "Strawberry Topping")
                blk["lines"].append(f"{spec['strawberry_topping_oz'] * qty} oz")
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

            if "blueberry_topping_oz" in spec:
                P("IHOP Large Plastic Base", 1 * qty)
                S("Serving Forks", 1 * qty)

                blk = ensure_block("blueberry", "Blueberry Topping")
                blk["lines"].append(f"{spec['blueberry_topping_oz'] * qty} oz")
                blk["pack_label"] = "IHOP Large Plastic Base"
                blk["pack_count"] += qty

    return total_servings, food, packaging, guestware, service, cond, prep_blocks

# =========================================================
# Guest-requested toggles
# =========================================================

def apply_guest_requested_toggles(
    total_servings: int,
    guestware: Dict[str, float],
    service: Dict[str, float],
    req_plates: bool,
    req_utensils: bool,
    req_napkins: bool,
):
    if req_plates and total_servings > 0:
        _add(guestware, "Paper Plates", total_servings)

    if req_napkins and total_servings > 0:
        _add(guestware, "Napkins", total_servings)

    if req_utensils and total_servings > 0:
        _add(guestware, "Wrapped Cutlery Sets", total_servings)
    else:
        for k in ["Serving Tongs", "Serving Spoons", "Serving Forks"]:
            _drop(service, k)


# =========================================================
# Prep block formatting
# =========================================================
# =========================================================
# Prep block formatting
# =========================================================
def format_prep_block(block: Dict) -> Tuple[str, List[str], str]:
    title = block["title"]
    raw_lines = block.get("lines", [])

    stacked_titles = {
        "Sandwich Toppings",
        "Sauces / Pickles",
        "Icings",
        "Salad",
        "Dressing",
        "Salsa",
    }

    if "qty_total" in block:
        unit = block.get("unit", "")
        if unit:
            line1 = f"{title}: {int(block['qty_total'])} {unit}"
        else:
            line1 = f"{title}: {int(block['qty_total'])}"
        details = []

    elif title == "Scrambled Eggs" and raw_lines:
        total_oz = 0
        for line in raw_lines:
            if "oz" in line:
                total_oz += float(line.replace("oz", "").strip())
        line1 = eggs_prep_line_from_oz(total_oz)
        details = []

    elif title == "French Toast" and "qty_total" in block:
        slices = int(block["qty_total"])
        half_pans = math.ceil(slices / 10)

        line1 = f"{title}: {slices} slices"
        details = []

        block["pack_label"] = "Aluminum ½ Pans"
        block["pack_count"] = half_pans

    elif title == POTATOES_NAME and raw_lines:
        total_oz = 0
        for line in raw_lines:
            if "oz" in line:
                total_oz += float(line.replace("oz", "").strip())
        line1 = bag_and_portion_line_from_oz(
            name=title,
            total_oz=total_oz,
            portion_oz=6.0,
            bag_lb=6.0,
        )
        details = []

    elif title == "French Fries" and raw_lines:
        total_oz = 0
        for line in raw_lines:
            if "oz" in line:
                total_oz += float(line.replace("oz", "").strip())
        line1 = bag_and_portion_line_from_oz(
            name=title,
            total_oz=total_oz,
            portion_oz=6.0,
            bag_lb=6.0,
        )
        details = []

    elif title == "Fresh Fruit" and raw_lines:
        total_oz = 0
        for line in raw_lines:
            if "oz" in line:
                total_oz += float(line.replace("oz", "").strip())
        total_portions = int(round(total_oz / 4.0))
        total_lb = ounces_to_lbs(total_oz)
        line1 = f"{title}: {int(total_oz)} oz ({total_portions} portions / {total_lb:.2f} lb)"
        details = []

    elif title == "Bacon" and raw_lines:
        total_pcs = 0
        for line in raw_lines:
            if "slices" in line:
                total_pcs += int(line.replace("slices", "").strip())
        line1 = containers_plus_remainder_from_pcs(
            name=title,
            pcs=total_pcs,
            pc_oz=BACON_SLICE_OZ,
            container_lb=BACON_CASE_LB,
            container_name="case",
            piece_name="slices",
        )
        details = []

    elif title == "Pork Sausage Links" and raw_lines:
        total_pcs = 0
        for line in raw_lines:
            if "links" in line:
                total_pcs += int(line.replace("links", "").strip())
        line1 = containers_plus_remainder_from_pcs(
            name=title,
            pcs=total_pcs,
            pc_oz=SAUSAGE_LINK_OZ,
            container_lb=SAUSAGE_BAG_LB,
            container_name="bag",
            piece_name="links",
        )
        details = []

    elif title in stacked_titles:
        line1 = f"{title}:"
        details = raw_lines

    else:
        if raw_lines:
            line1 = f"{title}: {raw_lines[0]}"
            details = raw_lines[1:]
        else:
            line1 = f"{title}:"
            details = []

    pack_count = int(block.get("pack_count", 0))
    pack_label = block.get("pack_label", "")

    if pack_count > 0 and pack_label:
        label = pack_label
        if pack_count == 1:
            if label == "Aluminum ½ Pans":
                label = "Aluminum ½ Pan"
            elif label == "Soup Cups (8 oz)":
                label = "Soup Cup (8 oz)"
            elif label == "Beverage Pouches":
                label = "Beverage Pouch"
            elif label == "Hot Beverage Containers":
                label = "Hot Beverage Container"
        pack_line = f"Pack in: {pack_count} {label}"
    else:
        pack_line = ""

    return line1, details, pack_line

def get_sorted_prep_blocks(prep_blocks: Dict[str, Dict]) -> List[Dict]:
    return sorted(prep_blocks.values(), key=lambda x: x.get("title", ""))

# =========================================================
# PDF helpers
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


def _pdf_draw_prep_blocks(
    c: canvas.Canvas,
    prep_blocks: List[Dict],
    x: float,
    y: float,
    max_width: float,
    bottom_margin: float = 0.75 * inch,
) -> float:
    item_font = "Helvetica-Bold"
    item_size = 10
    detail_font = "Helvetica"
    detail_size = 10
    pack_font = "Helvetica-Bold"
    pack_size = 10
    leading = 12

    for block in prep_blocks:
        line1, details, pack_line = format_prep_block(block)

        block_lines: List[Tuple[str, str, int, float]] = []
        block_lines.append((line1, item_font, item_size, x))

        for d in details:
            block_lines.append((d, detail_font, detail_size, x + 14))

        if pack_line:
            block_lines.append((pack_line, pack_font, pack_size, x + 14))

        for text, font_name, font_size, draw_x in block_lines:
            wrapped = simpleSplit(text, font_name, font_size, max_width - (draw_x - x))

            for w in wrapped:
                if y <= bottom_margin:
                    c.showPage()
                    y = letter[1] - 0.75 * inch

                c.setFont(font_name, font_size)
                c.drawString(draw_x, y, w)
                y -= leading

        y -= 6

    return y


# =========================================================
# PDF generation
# =========================================================

def generate_day_of_pdf(
    order_lines: List[OrderLine],
    pickup_dt: datetime,
    ready_dt: datetime,
    headcount: int,
    total_servings: int,
    req_plates: bool,
    req_utensils: bool,
    req_napkins: bool,
    packaging: Dict[str, float],
    guestware: Dict[str, float],
    service: Dict[str, float],
    cond: Dict[str, float],
    prep_blocks: List[Dict],
) -> bytes:
    buffer = io.BytesIO()
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
    c.drawString(left, y, "Counts (Informational)")
    y -= 12
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Headcount: {int(headcount)}")
    y -= 12
    c.drawString(left, y, f"Total Servings (food only): {int(total_servings)}")
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
    y = _pdf_draw_prep_blocks(c, prep_blocks, left, y, usable_w, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "3) Packaging", left, y)
    pack_lines = []
    for k in ["Aluminum ½ Pans", "IHOP Large Plastic Base", "Soup Cups (8 oz)", "Beverage Pouches", "Hot Beverage Containers"]:
        v = packaging.get(k, 0)
        if v:
            pack_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, pack_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "4) Plates & Guest Items", left, y)
    guest_lines = []
    for k in ["Paper Plates", "Napkins", "Wrapped Cutlery Sets", "Cold Cups", "Cold Lids", "Straws", "Hot Cups", "Hot Lids", "Sleeves", "Stirrers"]:
        v = guestware.get(k, 0)
        if v:
            guest_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, guest_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "5) Service Utensils", left, y)
    service_lines = []
    for k in ["Serving Tongs", "Serving Spoons", "Serving Forks"]:
        v = service.get(k, 0)
        if v:
            service_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, service_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)
    y -= 10

    y = _pdf_draw_section_title(c, "6) Condiment Bag", left, y)
    cond_lines = []
    for k in [
        "Butter Packets", "Syrup Packets", "Ketchup Packets", "Mustard Packets",
        "Mayo Packets", "Sugar Packets", "Creamers", "Powdered Sugar Cups (2 oz)"
    ]:
        v = cond.get(k, 0)
        if v:
            cond_lines.append(f"{k}: {int(v)}")
    y = _pdf_draw_wrapped_lines(c, cond_lines or ["None"], left, y, usable_w, bullet=True, bottom_margin=bottom)

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(
        width - right,
        bottom - 8,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')} • {APP_VERSION}"
    )

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================================================
# Session state init
# =========================================================

def init_state():
    if "lines" not in st.session_state:
        st.session_state.lines = []
    if "edit_idx" not in st.session_state:
        st.session_state.edit_idx = None

    st.session_state.setdefault("_reset_combo", False)
    st.session_state.setdefault("_reset_main", False)
    st.session_state.setdefault("_reset_alacarte", False)

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

    st.session_state.setdefault("pickup_date", datetime.now().date())
    st.session_state.setdefault("pickup_time", datetime.now().replace(second=0, microsecond=0).time())
    st.session_state.setdefault("headcount", 0)
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
# App start & UI Layout
# =========================================================

init_state()

# 1. Helper function to load your local image into CSS
def get_image_base64(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except FileNotFoundError:
        return "" # Fallback if image isn't found

# Load the banner you saved in the folder
banner_b64 = get_image_base64("ihop_banner.jpg")
bg_url = f"data:image/jpeg;base64,{banner_b64}" if banner_b64 else "https://images.unsplash.com/photo-1555244162-803834f70033?q=80&w=2070&auto=format&fit=crop"

# 2. Inject Custom CSS
st.markdown(f"""
<style>
    .block-container {{ padding-top: 2rem; padding-bottom: 2rem; }}
    
    /* Hero Banner Styling */
    .hero-banner {{
        background: linear-gradient(to right, rgba(15, 23, 42, 0.85) 0%, rgba(15, 23, 42, 0.2) 50%, transparent 100%), url('{bg_url}');
        background-size: cover; 
        background-position: center right;
        padding: 3rem; 
        border-radius: 0.75rem; 
        color: white; 
        margin-bottom: 2rem;
        min-height: 220px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }}
    .hero-subtitle {{ color: #38bdf8; font-weight: bold; text-transform: uppercase; font-size: 0.875rem; letter-spacing: 0.1em; }}
    .hero-title {{ font-size: 2.5rem; font-weight: 900; margin: 0.5rem 0; color: white; }}
    .hero-text {{ color: #e2e8f0; max-width: 32rem; margin-bottom: 0; }}
    
    /* Sidebar Summary Card Styling */
    .summary-card {{
        background-color: #0579bd; color: white; padding: 2rem;
        border-radius: 0.75rem; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }}
    .summary-card h3 {{ color: white; margin-top: 0; font-weight: 800;}}
    .summary-row {{ display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.9rem; color: #e0f2fe; }}
    .summary-divider {{ border-top: 1px solid #38bdf8; margin: 1rem 0; }}
    .summary-value {{ font-weight: bold; color: white; }}
    
    /* Sticky Right Column */
    [data-testid="column"]:nth-of-type(2) {{
        position: sticky;
        top: 4rem;
        max-height: calc(100vh - 6rem);
        overflow-y: auto;
    }}
    [data-testid="column"]:nth-of-type(2)::-webkit-scrollbar {{
        width: 0px;
        background: transparent;
    }}

    /* Style the A La Carte Expander Header */
    [data-testid="stExpander"] details summary {{
        background-color: #0579bd; /* Peachtree Blue */
        border-radius: 0.5rem;
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }}
    [data-testid="stExpander"] details summary p {{
        color: white !important;
        font-weight: 800;
        font-size: 1.1rem;
    }}
    [data-testid="stExpander"] details summary svg {{
        color: white !important;
    }}
</style>
""", unsafe_allow_html=True)

# 3. Render Hero Section
st.markdown(f"""
<div class="hero-banner">
    <div class="hero-subtitle">Internal Tool</div>
    <div class="hero-title">{APP_NAME} {APP_VERSION}</div>
    <div class="hero-text">Calculate ingredient quantities, packaging requirements, and day-of prep workflows.</div>
</div>
""", unsafe_allow_html=True)

# Main Layout
col1, col2 = st.columns([2.2, 1], gap="large")

with col1:
    # --- 1. Event Timing & Details ---
    st.subheader("📅 Event Details")
    with st.container(border=True):
        t1, t2, t3 = st.columns(3)
        with t1: st.date_input("Pickup date", key="pickup_date")
        with t2: st.time_input("Pickup time", key="pickup_time")
        with t3: st.number_input("Headcount (Informational)", min_value=0, value=int(st.session_state.headcount), step=1, key="headcount")
        
        st.markdown("**Guest Requested Items**")
        g1, g2, g3 = st.columns(3)
        with g1: st.toggle("Plates", key="req_plates")
        with g2: st.toggle("Utensils (Wrapped Sets)", key="req_utensils")
        with g3: st.toggle("Napkins", key="req_napkins")

    # --- 2. Build Order ---
    st.subheader("🍽️ Build Order")
    
    with st.container(border=True):
        st.markdown("**🥞 Breakfast Combo Boxes**")
        b1, b2, b3, b4 = st.columns([3, 3, 3, 2])
        with b1: st.selectbox("Combo size", list(COMBO_TIERS.keys()), key="combo_tier")
        with b2: st.selectbox("Protein", PROTEINS, key="combo_protein")
        with b3: st.selectbox("Griddle item", GRIDDLE_CHOICES, key="combo_griddle")
        with b4: st.number_input("Qty", min_value=1, value=int(st.session_state.combo_qty), step=1, key="combo_qty")
        
        if st.button("Add Combo", type="primary", use_container_width=True):
            tier, protein, griddle, qty = st.session_state.combo_tier, st.session_state.combo_protein, st.session_state.combo_griddle, int(st.session_state.combo_qty)
            key = LineKey(kind="combo", item_id=tier, protein=protein, griddle=griddle)
            merge_or_add_line(OrderLine(key=key, label=f"{tier} | {protein} | {griddle}", qty=qty, canon_id=build_canon_id(key)))
            reset_combo_form()
            st.rerun()

    with st.container(border=True):
        st.markdown("**🍔 Sandwiches, Strips, Beverages**")
        m1, m2, m3 = st.columns([5, 2, 4])
        with m1: st.selectbox("Select item", MAIN_LABELS, key="main_item")
        with m2: st.number_input("Qty", min_value=1, value=int(st.session_state.main_qty), step=1, key="main_qty")
        with m3:
            if MAIN_LABEL_TO_ID[st.session_state.main_item] == "cold_beverage":
                st.selectbox("Beverage type", COLD_BEV_TYPES, key="cold_bev_type_main")
                
        if st.button("Add Main Item", type="primary", use_container_width=True):
            item_id, qty = MAIN_LABEL_TO_ID[st.session_state.main_item], int(st.session_state.main_qty)
            if item_id == "cold_beverage":
                bev = st.session_state.get("cold_bev_type_main", COLD_BEV_TYPES[0])
                key = LineKey(kind="main", item_id=item_id, beverage_type=bev)
                label = f"{st.session_state.main_item} | {bev}"
            else:
                key = LineKey(kind="main", item_id=item_id)
                label = st.session_state.main_item
            merge_or_add_line(OrderLine(key=key, label=label, qty=qty, canon_id=build_canon_id(key)))
            reset_main_form()
            st.rerun()

    with st.expander("➕ Additional À La Carte Options"):
        a1, a2 = st.columns([6, 2])
        with a1: st.selectbox("À la carte item", ALACARTE_LABELS, key="al_item")
        with a2: st.number_input("Qty", min_value=1, value=int(st.session_state.al_qty), step=1, key="al_qty")
        if st.button("Add À La Carte", use_container_width=True):
            item_id = AL_LABEL_TO_ID[st.session_state.al_item]
            key = LineKey(kind="alacarte", item_id=item_id)
            merge_or_add_line(OrderLine(key=key, label=st.session_state.al_item, qty=int(st.session_state.al_qty), canon_id=build_canon_id(key)))
            reset_alacarte_form()
            st.rerun()

with col2:
    # Compute totals dynamically for the sidebar
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)
    
    if st.session_state.lines:
        total_servings, food, packaging, guestware, service, cond, prep_blocks = compute_order_data(st.session_state.lines)
        apply_guest_requested_toggles(total_servings, guestware, service, st.session_state.req_plates, st.session_state.req_utensils, st.session_state.req_napkins)
        sorted_blocks = get_sorted_prep_blocks(prep_blocks)
        item_count = sum([line.qty for line in st.session_state.lines])
    else:
        total_servings = item_count = 0
        packaging = guestware = service = cond = {}
        sorted_blocks = []

    # --- Sticky Summary Sidebar ---
    st.markdown(f"""
    <div class="summary-card">
        <h3>📦 Order Build Summary</h3>
        <div class="summary-row"><span>Ready Time</span> <span class="summary-value">{ready_dt.strftime('%I:%M %p')}</span></div>
        <div class="summary-row"><span>Pickup Time</span> <span class="summary-value">{pickup_dt.strftime('%I:%M %p')}</span></div>
        <div class="summary-divider"></div>
        <div class="summary-row"><span>Headcount</span> <span class="summary-value">{int(st.session_state.headcount)} Guests</span></div>
        <div class="summary-row"><span>Total Servings</span> <span class="summary-value">{total_servings}</span></div>
        <div class="summary-row"><span>Line Items</span> <span class="summary-value">{item_count}</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    # --- Current Order Management (Moved to col2) ---
    if not st.session_state.lines:
        st.info("Build an order on the left to generate the day-of packet.")
    else:
        st.markdown("### 📝 Current Order")
        for idx, line in enumerate(st.session_state.lines):
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                with c1: 
                    st.markdown(f"**{line.label}**")
                    st.caption(f"Qty: {line.qty}")
                with c2: 
                    if st.button("🗑️", key=f"remove_{idx}", use_container_width=True):
                        remove_line(idx)
                        st.rerun()
                        
        if st.button("Clear Entire Order", type="secondary", use_container_width=True):
            st.session_state.lines, st.session_state.edit_idx = [], None
            st.rerun()

        st.divider()

        # Generate the PDF dynamically
        order_pdf = generate_day_of_pdf(
            order_lines=st.session_state.lines, pickup_dt=pickup_dt, ready_dt=ready_dt,
            headcount=int(st.session_state.headcount), total_servings=total_servings,
            req_plates=st.session_state.req_plates, req_utensils=st.session_state.req_utensils,
            req_napkins=st.session_state.req_napkins, packaging=packaging, guestware=guestware,
            service=service, cond=cond, prep_blocks=sorted_blocks,
        )
        final_pdf = merge_order_with_checklist(order_pdf)

        st.download_button(
            label="GENERATE ORDER SHEET",
            data=final_pdf,
            file_name=f"catering_packet_{APP_VERSION}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        st.caption("Confirming the prep list will lock the inventory requirements for this event date.")
