import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

# =========================================================
# App Meta
# =========================================================
APP_NAME = "IHOP Catering Calculator"
APP_VERSION = "v2.0.2"

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


def init_state():
    if "lines" not in st.session_state:
        st.session_state.lines: List[OrderLine] = []
    if "edit_idx" not in st.session_state:
        st.session_state.edit_idx = None

    # Reset flags
    st.session_state.setdefault("_reset_combo", False)
    st.session_state.setdefault("_reset_alacarte", False)

    # Defaults (only set BEFORE widgets render)
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

    # Order meta defaults
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


def compute_pickup_and_ready(pickup_date, pickup_time) -> (datetime, datetime):
    pickup_dt = datetime.combine(pickup_date, pickup_time)
    ready_dt = pickup_dt - timedelta(minutes=10)
    return pickup_dt, ready_dt


# =========================================================
# Naming (your parlance)
# =========================================================
POTATOES_NAME = "Red Pots"
HAM_NAME = "Sampler Ham"

# =========================================================
# SKU / pack constants (from your order guide answers)
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
    "mayo_packets": {"sku": "65745", "ct_per_case": 200},
    "ketchup_packets": {"sku": "59007", "ct_per_case": 1000},
    "mustard_packets": {"sku": "55305", "ct_per_case": 500},
    "syrup_packets": {"sku": "605319", "ct_per_case": 200},
    "butter_packets": {"sku": "551715", "ct_per_case": 400},
    "powdered_sugar": {"sku": "336275", "bags_per_case": 12, "lbs_per_bag": 2, "oz_per_cup": 2},  # cups are 2oz
    "coffee_pack": {"sku": "1023877", "packs_per_case": 60, "packs_per_coffee_box": 2},
    "oj": {"sku": "267574", "bottles_per_case": 8, "oz_per_bottle": 59},
    "aj": {"sku": "147958", "bottles_per_case": 12, "oz_per_bottle": 32},
}

# =========================================================
# Combo Specs (kitchen-facing)
# NOTE: French Toast is tracked as SLICES internally (not triangles).
# Triangles appear in Plating Reference.
# =========================================================
PROTEINS = ["Bacon", "Pork Sausage Links", HAM_NAME]
GRIDDLE_CHOICES = ["Buttermilk Pancakes", "French Toast"]  # French Toast chosen implies slices

COMBO_TIERS = {
    "Small Combo Box": {
        "eggs_oz": 40,
        "red_pots_oz": 60,
        "protein_pcs": 20,
        "pancakes_pcs": 20,
        "ft_slices": 10,               # 10 slices -> 20 triangles
        "half_pans_eggs": 1,
        "half_pans_red_pots": 1,
        "large_bases_protein": 1,
        "half_pans_pancakes": 1,
        "half_pans_ft": 2,
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
        "half_pans_eggs": 2,
        "half_pans_red_pots": 2,
        "large_bases_protein": 2,
        "half_pans_pancakes": 2,
        "half_pans_ft": 4,
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
        "half_pans_eggs": 4,
        "half_pans_red_pots": 4,
        "large_bases_protein": 4,
        "half_pans_pancakes": 4,
        "half_pans_ft": 8,
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
        ("steakburgers_10", "Steakburgers (10 pcs)", {"steakburgers_pcs": 10, "auto_buns": 10, "auto_cond_burger": 10}),
        ("crispy_chx_sand_10", "Crispy Chicken Sandwiches (10 pcs)", {"auto_buns": 10, "auto_cond_burger": 10}),
        ("grilled_chx_sand_10", "Grilled Chicken Sandwiches (10 pcs)", {"auto_buns": 10, "auto_cond_burger": 10}),
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

            # Packaging totals (internal keys)
            add("half_pans", (spec["half_pans_eggs"] + spec["half_pans_red_pots"]) * qty)
            add("large_bases", spec["large_bases_protein"] * qty)
            if griddle == "Buttermilk Pancakes":
                add("half_pans", spec["half_pans_pancakes"] * qty)
            else:
                add("half_pans", spec["half_pans_ft"] * qty)

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
                add("half_pans", 1 * qty)
                add("serving_tongs", 1 * qty)
                add("ketchup_ct", 10 * qty)

            if "onion_rings_from_oz" in spec:
                rings = (spec["onion_rings_from_oz"] * qty) / SKU["onion_rings"]["oz_per_ring"]
                add("onion_rings_rings", math.ceil(rings - 1e-9))
                add("half_pans", 2 * qty)
                add("serving_tongs", 1 * qty)
                add("ketchup_ct", 10 * qty)

            if "steakburgers_pcs" in spec:
                add("steakburgers_pcs", spec["steakburgers_pcs"] * qty)
            if "auto_buns" in spec:
                add("buns_ct", spec["auto_buns"] * qty)
            if "auto_cond_burger" in spec:
                n = spec["auto_cond_burger"] * qty
                add("mayo_ct", n)
                add("ketchup_ct", n)
                add("mustard_ct", n)
                add("serving_tongs", 2 * qty)
                add("spoons", 2 * qty)
                add("plates", 10 * qty)

            if "coffee_boxes" in spec:
                boxes = spec["coffee_boxes"] * qty
                add("coffee_boxes", boxes)
                add("coffee_packs", boxes * SKU["coffee_pack"]["packs_per_coffee_box"])
                add("coffee_boxes_packaging", boxes)

            if "cold_bags" in spec:
                bags = spec["cold_bags"] * qty
                bev_type = line.key.beverage_type or "Unknown"
                add(f"cold_bags::{bev_type}", bags)

    return totals


# =========================================================
# Prep language formatting helpers (for output)
# =========================================================
def eggs_prep_line(eggs_oz: float) -> str:
    lbs = ounces_to_lbs(eggs_oz)
    quarts = lbs * 0.465
    quarts_r = friendly_round_up(quarts, inc=0.5, tiny_over=0.05)
    cambros_4qt = quarts_r / 4.0
    return f"Scrambled Eggs: {quarts_r:g} qt ({cambros_4qt:.1f} of a 4-qt Cambro)"


def bag_overflow_line(total_oz: float, oz_per_bag: float, oz_per_portion: Optional[float], label: str) -> str:
    lbs = ounces_to_lbs(total_oz)
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05) if lbs > 0 else 0

    if oz_per_portion:
        portions = total_oz / oz_per_portion
        portions_int = int(math.ceil(portions - 1e-9))
        main = f"{label}: {int(total_oz)} oz ({portions_int} portions/{lbs_r:g} lb)"
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
            f"{main}\n\nOpen: {full_bags} bag{'s' if full_bags != 1 else ''} PLUS "
            f"{int(rem_oz)} oz ({rem_portions_int} portions/{rem_lbs_r:g} lb)"
        )

    return (
        f"{main}\n\nOpen: {full_bags} bag{'s' if full_bags != 1 else ''} PLUS "
        f"{int(rem_oz)} oz ({rem_lbs_r:g} lb)"
    )


def red_pots_prep_line(total_oz: float) -> str:
    return bag_overflow_line(
        total_oz=total_oz,
        oz_per_bag=SKU["red_pots"]["lbs_per_bag"] * 16,
        oz_per_portion=SKU["fries"]["oz_per_portion"],
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
    return f"Bacon: {int(bacon_pcs)} slices ({lbs_r:g} lb)"


def sausage_prep_line(sausage_pcs: float) -> str:
    lbs = sausage_pcs / 20.0
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"Pork Sausage Links: {int(sausage_pcs)} links ({lbs_r:g} lb)"


def ham_prep_line(ham_pcs: float) -> str:
    lbs = ounces_to_lbs(ham_pcs * 1.0)
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"{HAM_NAME}: {int(ham_pcs)} pcs ({lbs_r:g} lb)"


def chicken_strips_prep_line(pcs: float) -> str:
    lbs = ounces_to_lbs(pcs * SKU["chicken_strips"]["oz_per_piece"])
    lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
    return f"Chicken Strips: {int(pcs)} pcs ({lbs_r:g} lb)"


def pancakes_prep_line(pancakes_pcs: float) -> str:
    return f"Buttermilk Pancakes: {int(pancakes_pcs)} pancakes"


def ft_prep_line_slices(ft_slices: float) -> str:
    return f"French Toast: {int(ft_slices)} slices"


def onion_rings_prep_line(rings: float) -> str:
    return f"Onion Rings: {int(rings)} rings"


def powdered_sugar_prep_line(cups: float) -> str:
    return f"Powdered Sugar: {int(cups)} (2 oz) cups"


# =========================================================
# Inventory Impact (separate frame)
# =========================================================
def inventory_impact(totals: Dict[str, float]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    def add_row(item: str, sku: str, impact: str):
        rows.append({"Item": item, "SKU": sku, "Impact": impact})

    eggs_oz = totals.get("eggs_oz", 0)
    if eggs_oz > 0:
        lbs = ounces_to_lbs(eggs_oz)
        quarts = lbs * 0.465
        quarts_r = friendly_round_up(quarts, inc=0.5, tiny_over=0.05)
        bag_lbs = SKU["eggs"]["lbs_per_unit"]
        bag_fraction = lbs / bag_lbs
        case_fraction = lbs / (SKU["eggs"]["units_per_case"] * bag_lbs)
        add_row("Scrambled Eggs", SKU["eggs"]["sku"], f"{quarts_r:g} qt (≈ {bag_fraction:.2f} bag, {case_fraction:.2f} case)")

    rp_oz = totals.get("red_pots_oz", 0)
    if rp_oz > 0:
        bag_oz = SKU["red_pots"]["lbs_per_bag"] * 16
        full_bags = int(rp_oz // bag_oz)
        rem_oz = rp_oz - full_bags * bag_oz
        if full_bags == 0:
            add_row(POTATOES_NAME, SKU["red_pots"]["sku"], f"{int(rp_oz)} oz total")
        else:
            add_row(POTATOES_NAME, SKU["red_pots"]["sku"], f"Open {full_bags} bag(s) + {int(rem_oz)} oz")

    bacon_pcs = totals.get("bacon_pcs", 0)
    if bacon_pcs > 0:
        lbs = bacon_pcs / 9.0
        lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
        case_fraction = lbs / SKU["bacon"]["lbs_per_case"]
        add_row("Bacon", SKU["bacon"]["sku"], f"{lbs_r:g} lb (≈ {case_fraction:.2f} case)")

    sausage_pcs = totals.get("sausage_pcs", 0)
    if sausage_pcs > 0:
        lbs = sausage_pcs / 20.0
        lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
        bag_fraction = lbs / SKU["sausage"]["lbs_per_bag"]
        add_row("Pork Sausage Links", SKU["sausage"]["sku"], f"{lbs_r:g} lb (≈ {bag_fraction:.2f} bag)")

    ham_pcs = totals.get("ham_pcs", 0)
    if ham_pcs > 0:
        lbs = ounces_to_lbs(ham_pcs * 1.0)
        lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
        pack_fraction = lbs / SKU["ham"]["lbs_per_pack"]
        add_row(HAM_NAME, SKU["ham"]["sku"], f"{lbs_r:g} lb (≈ {pack_fraction:.2f} pack)")

    pancakes = totals.get("pancakes_pcs", 0)
    if pancakes > 0:
        lbs_mix = pancakes / (738.0 / 45.0)
        lbs_mix_r = friendly_round_up(lbs_mix, inc=0.5, tiny_over=0.05)
        bag_fraction = lbs_mix / SKU["pancake_mix"]["lbs_per_bag"]
        add_row("Pancake Mix", SKU["pancake_mix"]["sku"], f"{lbs_mix_r:g} lb mix (≈ {bag_fraction:.2f} bag)")

    ft_slices = totals.get("ft_slices", 0)
    if ft_slices > 0:
        loaves_needed = int(math.ceil(ft_slices / SKU["ft_bread"]["slices_per_loaf"] - 1e-9))
        add_row("French Toast Bread", SKU["ft_bread"]["sku"], f"{int(ft_slices)} slices → {loaves_needed} loaf/loaves")

    ps_cups = totals.get("powdered_sugar_cups_2oz", 0)
    if ps_cups > 0:
        cups_per_bag = (SKU["powdered_sugar"]["lbs_per_bag"] * 16) / SKU["powdered_sugar"]["oz_per_cup"]
        bags_needed = int(math.ceil(ps_cups / cups_per_bag - 1e-9))
        add_row("Powdered Sugar", SKU["powdered_sugar"]["sku"], f"{int(ps_cups)} cups (2 oz) → {bags_needed} bag(s)")

    strips = totals.get("chix_strips_pcs", 0)
    if strips > 0:
        lbs = ounces_to_lbs(strips * SKU["chicken_strips"]["oz_per_piece"])
        lbs_r = friendly_round_up(lbs, inc=0.5, tiny_over=0.05)
        bags_needed = int(math.ceil(lbs / SKU["chicken_strips"]["lbs_per_bag"] - 1e-9))
        add_row("Chicken Strips", SKU["chicken_strips"]["sku"], f"{lbs_r:g} lb → {bags_needed} bag(s)")

    fries_oz = totals.get("fries_oz", 0)
    if fries_oz > 0:
        bag_oz = SKU["fries"]["lbs_per_bag"] * 16
        full_bags = int(fries_oz // bag_oz)
        rem_oz = fries_oz - full_bags * bag_oz
        if full_bags == 0:
            add_row("French Fries", SKU["fries"]["sku"], f"{int(fries_oz)} oz total")
        else:
            add_row("French Fries", SKU["fries"]["sku"], f"Open {full_bags} bag(s) + {int(rem_oz)} oz")

    rings = totals.get("onion_rings_rings", 0)
    if rings > 0:
        rings_per_bag = int((SKU["onion_rings"]["lbs_per_bag"] * 16) / SKU["onion_rings"]["oz_per_ring"])
        full_bags = int(rings // rings_per_bag)
        rem = int(rings - full_bags * rings_per_bag)
        if full_bags == 0:
            add_row("Onion Rings", SKU["onion_rings"]["sku"], f"{int(rings)} rings total")
        else:
            add_row("Onion Rings", SKU["onion_rings"]["sku"], f"Open {full_bags} bag(s) + {rem} rings")

    burg = totals.get("steakburgers_pcs", 0)
    if burg > 0:
        case_fraction = burg / SKU["steakburgers"]["patties_per_case"]
        add_row("Steakburger Patties", SKU["steakburgers"]["sku"], f"{int(burg)} patties (≈ {case_fraction:.2f} case)")

    buns = totals.get("buns_ct", 0)
    if buns > 0:
        case_fraction = buns / SKU["burger_buns"]["buns_per_case"]
        add_row("Burger Buns", SKU["burger_buns"]["sku"], f"{int(buns)} buns (≈ {case_fraction:.2f} case)")

    if totals.get("mayo_ct", 0) > 0:
        add_row("Mayo Packets", SKU["mayo_packets"]["sku"], f"{int(totals['mayo_ct'])} packets")
    if totals.get("ketchup_ct", 0) > 0:
        add_row("Ketchup Packets", SKU["ketchup_packets"]["sku"], f"{int(totals['ketchup_ct'])} packets")
    if totals.get("mustard_ct", 0) > 0:
        add_row("Mustard Packets", SKU["mustard_packets"]["sku"], f"{int(totals['mustard_ct'])} packets")
    if totals.get("syrup_ct", 0) > 0:
        add_row("Syrup Packets", SKU["syrup_packets"]["sku"], f"{int(totals['syrup_ct'])} packets")
    if totals.get("butter_ct", 0) > 0:
        add_row("Butter Packets", SKU["butter_packets"]["sku"], f"{int(totals['butter_ct'])} packets")

    if totals.get("coffee_packs", 0) > 0:
        packs = int(totals["coffee_packs"])
        case_fraction = packs / SKU["coffee_pack"]["packs_per_case"]
        add_row("Coffee Packs", SKU["coffee_pack"]["sku"], f"{packs} packs (≈ {case_fraction:.2f} case)")

    for k, v in totals.items():
        if not k.startswith("cold_bags::"):
            continue
        bev_type = k.split("::", 1)[1]
        bags = int(v)
        oz_needed = bags * COLD_BEV_OZ
        if bev_type == "Orange Juice":
            bottles = math.ceil(oz_needed / SKU["oj"]["oz_per_bottle"] - 1e-9)
            add_row("Orange Juice for Cold Bags", SKU["oj"]["sku"], f"{bags} bag(s) → {bottles} bottle(s)")
        elif bev_type == "Apple Juice":
            bottles = math.ceil(oz_needed / SKU["aj"]["oz_per_bottle"] - 1e-9)
            add_row("Apple Juice for Cold Bags", SKU["aj"]["sku"], f"{bags} bag(s) → {bottles} bottle(s)")

    return rows


# =========================================================
# UI
# =========================================================
init_state()

st.title(f"{APP_NAME} {APP_VERSION}")
st.caption("Manager-friendly dropdown entry. Prep totals + plating reference + inventory impact.")

main, _ = st.columns([1, 1])

with main:
    st.subheader("Build Order")

    st.markdown("### Timing")
    pickup_date = st.date_input("Pickup date", key="pickup_date")
    pickup_time = st.time_input("Pickup time", key="pickup_time")

    pickup_dt, ready_dt = compute_pickup_and_ready(pickup_date, pickup_time)
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
    bev_type = None
    if al_id == "cold_bag":
        bev_type = st.selectbox("Cold beverage type", COLD_BEV_TYPES, index=0, key="cold_bev_type")

    if st.button("Add À La Carte", use_container_width=True):
        item_id = AL_LABEL_TO_ID[al_item]
        if item_id == "cold_bag":
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
                    al_labels = ALACARTE_LABELS
                    default_index = al_labels.index(current_base_label) if current_base_label in al_labels else 0

                    new_label_base = edit.selectbox("Item", al_labels, index=default_index, key=f"edit_al_{idx}")
                    new_item_id = AL_LABEL_TO_ID[new_label_base]

                    new_bev = None
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
# OUTPUT
# =========================================================
st.subheader("Prep Output (Print / Download)")

if not st.session_state.lines:
    st.caption("Build an order above to generate the prep sheet.")
else:
    totals = compute_order_totals(st.session_state.lines)
    pickup_dt, ready_dt = compute_pickup_and_ready(st.session_state.pickup_date, st.session_state.pickup_time)

    st.markdown("## 1) Order Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ready time", ready_dt.strftime("%Y-%m-%d %I:%M %p"))
    c2.metric("Pickup time", pickup_dt.strftime("%Y-%m-%d %I:%M %p"))
    c3.metric("Headcount", int(headcount))
    c4.metric("Utensil sets ordered", int(ordered_utensils))

    recommended_utensils = int(headcount) if headcount and headcount > 0 else 0
    if headcount > 0:
        st.caption(f"Utensil sets recommended: {recommended_utensils}")

    if headcount > 0 and ordered_utensils > 0:
        if ordered_utensils < headcount:
            st.error(f"Utensil check: Ordered {int(ordered_utensils)} but headcount is {int(headcount)}. Recommend at least {int(recommended_utensils)}.")
        elif ordered_utensils > headcount * 1.25:
            st.info(f"Utensil check: Ordered {int(ordered_utensils)} for headcount {int(headcount)}. That’s plenty. Recommend ~{int(recommended_utensils)}.")
        else:
            st.success("Utensil check: Ordered utensils look aligned with headcount.")
    elif headcount > 0 and ordered_utensils == 0:
        st.warning(f"No utensil count entered. Recommend ~{int(recommended_utensils)} utensil sets for headcount {int(headcount)}.")

    st.markdown("## 2) Food Totals (Prep)")
    prep_lines: List[str] = []

    if totals.get("eggs_oz", 0) > 0:
        prep_lines.append(eggs_prep_line(totals["eggs_oz"]))
    if totals.get("red_pots_oz", 0) > 0:
        prep_lines.append(red_pots_prep_line(totals["red_pots_oz"]))
    if totals.get("bacon_pcs", 0) > 0:
        prep_lines.append(bacon_prep_line(totals["bacon_pcs"]))
    if totals.get("sausage_pcs", 0) > 0:
        prep_lines.append(sausage_prep_line(totals["sausage_pcs"]))
    if totals.get("ham_pcs", 0) > 0:
        prep_lines.append(ham_prep_line(totals["ham_pcs"]))
    if totals.get("pancakes_pcs", 0) > 0:
        prep_lines.append(pancakes_prep_line(totals["pancakes_pcs"]))
    if totals.get("ft_slices", 0) > 0:
        prep_lines.append(ft_prep_line_slices(totals["ft_slices"]))
    if totals.get("chix_strips_pcs", 0) > 0:
        prep_lines.append(chicken_strips_prep_line(totals["chix_strips_pcs"]))
    if totals.get("fries_oz", 0) > 0:
        prep_lines.append(fries_prep_line(totals["fries_oz"]))
    if totals.get("onion_rings_rings", 0) > 0:
        prep_lines.append(onion_rings_prep_line(totals["onion_rings_rings"]))
    if totals.get("steakburgers_pcs", 0) > 0:
        prep_lines.append(f"Steakburgers: {int(totals['steakburgers_pcs'])} patties")
    if totals.get("buns_ct", 0) > 0:
        prep_lines.append(f"Burger Buns: {int(totals['buns_ct'])} buns")
    if totals.get("powdered_sugar_cups_2oz", 0) > 0:
        prep_lines.append(powdered_sugar_prep_line(totals["powdered_sugar_cups_2oz"]))

    if totals.get("coffee_boxes", 0) > 0:
        boxes = int(totals["coffee_boxes"])
        packs = int(totals.get("coffee_packs", 0))
        prep_lines.append(f"Coffee: {boxes} box(es) (brew packs: {packs})")

    for k, v in totals.items():
        if k.startswith("cold_bags::"):
            bev = k.split("::", 1)[1]
            bags = int(v)
            prep_lines.append(f"Cold Beverage Bag: {bags} bag(s) | {bev} ({bags * COLD_BEV_OZ} oz total)")

    for line in prep_lines:
        st.write("• " + line)

    # =====================================================
    # Packaging Totals (WORDING FIX)
    # - Anything "pan" => Aluminum
    # - Anything "base" => IHOP plastic
    # =====================================================
    st.markdown("## 3) Packaging Totals")
    pack_rows = []
    if totals.get("half_pans", 0) > 0:
        pack_rows.append({"Packaging": "Aluminum Half Pans", "Total": int(totals["half_pans"])})
    if totals.get("large_bases", 0) > 0:
        pack_rows.append({"Packaging": "IHOP Plastic Large Bases", "Total": int(totals["large_bases"])})
    if pack_rows:
        st.dataframe(pd.DataFrame(pack_rows), width="stretch", hide_index=True)
    else:
        st.caption("No packaging totals calculated for this order.")

    st.markdown("## 4) Condiments")
    cond_map = [
        ("butter_ct", "Butter Packets"),
        ("syrup_ct", "Syrup Packets"),
        ("ketchup_ct", "Ketchup Packets"),
        ("mayo_ct", "Mayo Packets"),
        ("mustard_ct", "Mustard Packets"),
        ("powdered_sugar_cups_2oz", "Powdered Sugar (2 oz cups)"),
    ]
    cond_rows = []
    for key, label in cond_map:
        if totals.get(key, 0) > 0:
            cond_rows.append({"Condiment": label, "Total": int(totals[key])})
    if cond_rows:
        st.dataframe(pd.DataFrame(cond_rows), width="stretch", hide_index=True)
    else:
        st.caption("No condiment totals calculated for this order.")

    st.markdown("## 5) Serveware")
    serve_keys = [
        ("plates", "Plates"),
        ("serving_tongs", "Serving Tongs"),
        ("serving_forks", "Serving Forks"),
        ("spoons", "Spoons"),
    ]
    serve_rows = []
    for key, label in serve_keys:
        if totals.get(key, 0) > 0:
            serve_rows.append({"Serveware": label, "Total": int(totals[key])})

    if ordered_utensils and ordered_utensils > 0:
        serve_rows.append({"Serveware": "Utensil Sets (ordered)", "Total": int(ordered_utensils)})
    if recommended_utensils and recommended_utensils > 0:
        serve_rows.append({"Serveware": "Utensil Sets (recommended)", "Total": int(recommended_utensils)})

    if serve_rows:
        st.dataframe(pd.DataFrame(serve_rows), width="stretch", hide_index=True)
    else:
        st.caption("No serveware totals calculated for this order.")

    st.markdown("## 6) Plating Reference (Guest-Facing)")
    plating_lines = []
    if totals.get("ft_slices", 0) > 0:
        triangles = int(totals["ft_slices"] * 2)
        plating_lines.append(f"French Toast: {triangles} triangles (from {int(totals['ft_slices'])} slices)")
    if totals.get("pancakes_pcs", 0) > 0:
        plating_lines.append(f"Buttermilk Pancakes: {int(totals['pancakes_pcs'])} pancakes")
    if totals.get("onion_rings_rings", 0) > 0:
        plating_lines.append(f"Onion Rings: {int(totals['onion_rings_rings'])} rings")
    if totals.get("steakburgers_pcs", 0) > 0:
        plating_lines.append(f"Steakburgers: {int(totals['steakburgers_pcs'])} assembled")

    if plating_lines:
        for line in plating_lines:
            st.write("• " + line)
    else:
        st.caption("No plating-specific items triggered.")

    st.markdown("## 7) Inventory Impact")
    inv_box = st.container(border=True)
    inv_rows = inventory_impact(totals)
    if inv_rows:
        inv_box.dataframe(pd.DataFrame(inv_rows), width="stretch", hide_index=True)
    else:
        inv_box.caption("No tracked inventory items triggered by this order.")

    st.divider()
    st.markdown("## Download")

    export_rows: List[Dict[str, str]] = []
    export_rows.append({"Section": "Order Meta", "Name": "Ready time", "Total": ready_dt.isoformat(sep=" ", timespec="minutes")})
    export_rows.append({"Section": "Order Meta", "Name": "Pickup time", "Total": pickup_dt.isoformat(sep=" ", timespec="minutes")})
    export_rows.append({"Section": "Order Meta", "Name": "Headcount", "Total": str(int(headcount))})
    export_rows.append({"Section": "Order Meta", "Name": "Utensil sets ordered", "Total": str(int(ordered_utensils))})

    for line in st.session_state.lines:
        export_rows.append({"Section": "Order Lines", "Name": line.label, "Total": str(line.qty)})

    for k, v in sorted(totals.items(), key=lambda x: x[0]):
        export_rows.append({"Section": "Computed Totals", "Name": k, "Total": str(v)})

    for r in inv_rows:
        export_rows.append({"Section": "Inventory Impact", "Name": f"{r['Item']} (SKU {r['SKU']})", "Total": r["Impact"]})

    export_df = pd.DataFrame(export_rows)
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Full Output (CSV)",
        data=csv_bytes,
        file_name=f"catering_output_{APP_VERSION}.csv",
        mime="text/csv",
        use_container_width=True,
    )
