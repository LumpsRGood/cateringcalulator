import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="IHOP Catering Calculator", layout="wide")

# =========================================================
# Data model
# =========================================================

@dataclass(frozen=True)
class LineKey:
    """Unique key for merging identical lines."""
    kind: str  # "combo" or "alacarte"
    item_id: str
    protein: Optional[str] = None
    griddle: Optional[str] = None

@dataclass
class OrderLine:
    key: LineKey
    label: str
    qty: int


# =========================================================
# Specs (based on IHOP plating/packaging guide)
# =========================================================
# IMPORTANT: counts/oz here are "per 1 unit" of the selected item.
# Combo boxes are tiered: Small, Medium, Large.
# - Eggs: 40/80/160 oz
# - Potatoes: 60/120/240 oz
# - Protein: 20/40/80 pcs
# - Pancakes: 20/40/80 pcs
# - French Toast: 10/20/40 pcs
# Packaging for combos (per tier):
# - Eggs: 1/2/4 half pans
# - Potatoes: 1/2/4 half pans
# - Protein: 1/2/4 large bases
# - Pancakes: 1/2/4 half pans
# - French Toast: 2/4/8 half pans
# Condiments for combos (per tier):
# - Butter: 10/20/40
# - Syrup: 10/20/40
# - Ketchup: 10/20/40
# - Powdered sugar souffle (French toast only): 2/4/8
# Serveware for combos (per tier):
# - Serving forks: 2/2/8
# - Serving tongs: 2/2/5
# - Plates: 10/20/40

PROTEINS = ["Bacon (20 pcs)", "Pork Sausage Links (20 pcs)", "Ham Slices (20 pcs)"]
GRIDDLE_CHOICES = ["Buttermilk Pancakes (20 pcs)", "French Toast (10 pcs)"]

COMBO_TIERS = {
    "Small Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 40,
            "Breakfast Potatoes (oz)": 60,
            "Protein (pcs)": 20,
            "Buttermilk Pancakes (pcs)": 20,
            "French Toast (pcs)": 10,
        },
        "packaging": {"Half Pans": 1 + 1 + 1 + 2, "Large Bases": 1},  # eggs + potatoes + pancakes + french toast
        "condiments": {
            "Butter Packets": 10,
            "Syrup Packets": 10,
            "Ketchup Packets": 10,
            "Powdered Sugar Souffle (2 oz)": 2,  # only if french toast selected
        },
        "serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 10},
    },
    "Medium Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 80,
            "Breakfast Potatoes (oz)": 120,
            "Protein (pcs)": 40,
            "Buttermilk Pancakes (pcs)": 40,
            "French Toast (pcs)": 20,
        },
        "packaging": {"Half Pans": 2 + 2 + 2 + 4, "Large Bases": 2},
        "condiments": {
            "Butter Packets": 20,
            "Syrup Packets": 20,
            "Ketchup Packets": 20,
            "Powdered Sugar Souffle (2 oz)": 4,
        },
        "serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 20},
    },
    "Large Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 160,
            "Breakfast Potatoes (oz)": 240,
            "Protein (pcs)": 80,
            "Buttermilk Pancakes (pcs)": 80,
            "French Toast (pcs)": 40,
        },
        "packaging": {"Half Pans": 4 + 4 + 4 + 8, "Large Bases": 4},
        "condiments": {
            "Butter Packets": 40,
            "Syrup Packets": 40,
            "Ketchup Packets": 40,
            "Powdered Sugar Souffle (2 oz)": 8,
        },
        "serveware": {"Serving Forks": 8, "Serving Tongs": 5, "Plates": 40},
    },
}

# A la carte groups with explicit count/oz in labels
ALACARTE_GROUPS = [
    ("Griddle Faves", [
        ("pancakes_20", "Buttermilk Pancakes (20 pcs)",
         {"Buttermilk Pancakes (pcs)": 20},
         {"Half Pans": 1},
         {"Syrup Packets": 10, "Butter Packets": 10},
         {"Serving Tongs": 1, "Plates": 10}),
        ("french_toast_10", "French Toast (10 pcs)",
         {"French Toast (pcs)": 10},
         {"Half Pans": 2},
         {"Syrup Packets": 10, "Butter Packets": 10, "Powdered Sugar Souffle (2 oz)": 2},
         {"Serving Tongs": 1, "Plates": 10}),
        ("berry_topping", "Strawberry/Blueberry Topping (1 base)",
         {},
         {"Large Bases": 1},
         {},
         {"Serving Forks": 1}),
    ]),
    ("Breakfast Proteins & Sides", [
        ("eggs_40oz", "Scrambled Eggs (40 oz)",
         {"Scrambled Eggs (oz)": 40},
         {"Half Pans": 1},
         {},
         {"Serving Forks": 1}),
        ("potatoes_40oz", "Breakfast Potatoes (40 oz)",
         {"Breakfast Potatoes (oz)": 40},
         {"Half Pans": 1},
         {"Ketchup Packets": 10},
         {"Serving Forks": 1}),
        ("bacon_20", "Bacon (20 pcs)",
         {"Bacon (pcs)": 20},
         {"Large Bases": 1},
         {},
         {"Serving Tongs": 1}),
        ("psl_20", "Pork Sausage Links (20 pcs)",
         {"Pork Sausage Links (pcs)": 20},
         {"Large Bases": 1},
         {},
         {"Serving Tongs": 1}),
        ("ham_20", "Ham Slices (20 pcs)",
         {"Ham Slices (pcs)": 20},
         {"Large Bases": 1},
         {},
         {"Serving Tongs": 1}),
        ("fruit_40oz", "Fresh Fruit (40 oz)",
         {"Fresh Fruit (oz)": 40},
         {"Large Bases": 1},
         {},
         {"Serving Forks": 1}),
    ]),
    ("Burritos", [
        ("burritos_10", "Classic Breakfast Burritos (10 pcs)",
         {"Breakfast Burritos (pcs)": 10},
         {"Half Pans": 2},
         {"Salsa Soup Cups": 2},
         {"Spoons": 2}),
    ]),
    ("Lunch / Savory", [
        ("chix_strips_40", "Chicken Strips (40 pcs)",
         {"Chicken Strips (pcs)": 40},
         {"Half Pans": 1},
         {"BBQ Soup Cup": 1, "IHOP Sauce Soup Cup": 1, "Ranch Soup Cup": 1},
         {"Serving Tongs": 1, "Spoons": 3, "Plates": 10}),
        ("fries_60oz", "French Fries (60 oz)",
         {"French Fries (oz)": 60},
         {"Half Pans": 1},
         {"Ketchup Packets": 10},
         {"Serving Tongs": 1}),
        ("onion_rings_60oz", "Onion Rings (60 oz)",
         {"Onion Rings (oz)": 60},
         {"Half Pans": 2},
         {"Ketchup Packets": 10},
         {"Serving Tongs": 1}),
    ]),
    ("Beverages", [
        ("coffee_96oz", "Coffee Box (96 oz)",
         {"Coffee (oz)": 96},
         {"Coffee Boxes": 1},
         {"Sugars": 10, "Creamers": 10},
         {"Hot Cups + Lids + Sleeves": 10, "Stirrers": 10}),
        ("cold_pouch_128oz", "Cold Beverage Pouch (128 oz)",
         {"Cold Beverage (oz)": 128},
         {"Beverage Pouches": 1},
         {},
         {"Cold Cups + Lids": 10, "Wrapped Straws": 10}),
    ]),
]

# Flattened lookup for alacarte
ALACARTE_LOOKUP = {}
ALACARTE_MENU = []
for group, items in ALACARTE_GROUPS:
    ALACARTE_MENU.append(("— " + group + " —", None))
    for (item_id, label, food, packaging, condiments, serveware) in items:
        ALACARTE_LOOKUP[item_id] = {
            "label": label,
            "food": food,
            "packaging": packaging,
            "condiments": condiments,
            "serveware": serveware,
            "group": group,
        }
        ALACARTE_MENU.append((label, item_id))


# =========================================================
# Helpers
# =========================================================

def dict_add(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out

def dict_mul(d: Dict[str, float], n: int) -> Dict[str, float]:
    return {k: v * n for k, v in d.items()}

def init_state():
    if "lines" not in st.session_state:
        st.session_state.lines: List[OrderLine] = []
    if "edit_idx" not in st.session_state:
        st.session_state.edit_idx = None

def merge_or_add_line(new_line: OrderLine):
    """Merge identical line keys by summing quantity."""
    for i, line in enumerate(st.session_state.lines):
        if line.key == new_line.key:
            st.session_state.lines[i].qty += new_line.qty
            return
    st.session_state.lines.append(new_line)

def remove_line(idx: int):
    st.session_state.lines.pop(idx)
    if st.session_state.edit_idx == idx:
        st.session_state.edit_idx = None

def build_totals(lines: List[OrderLine]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
    total_food: Dict[str, float] = {}
    total_packaging: Dict[str, float] = {}
    total_condiments: Dict[str, float] = {}
    total_serveware: Dict[str, float] = {}

    for line in lines:
        qty = line.qty
        if line.key.kind == "combo":
            tier = line.key.item_id  # "Small Combo Box" etc
            protein = line.key.protein
            griddle = line.key.griddle

            spec = COMBO_TIERS[tier]
            # Food: eggs + potatoes + chosen protein + chosen griddle
            base_food = {
                "Scrambled Eggs (oz)": spec["food"]["Scrambled Eggs (oz)"],
                "Breakfast Potatoes (oz)": spec["food"]["Breakfast Potatoes (oz)"],
                "Protein (pcs)": spec["food"]["Protein (pcs)"],
            }

            # Expand protein name into a specific bucket (helps later)
            if protein:
                base_food = dict_add(base_food, {f"{protein.replace(' (20 pcs)','')} (pcs)": spec["food"]["Protein (pcs)"]})

            # Griddle choice
            if griddle == "Buttermilk Pancakes (20 pcs)":
                base_food = dict_add(base_food, {"Buttermilk Pancakes (pcs)": spec["food"]["Buttermilk Pancakes (pcs)"]})
            elif griddle == "French Toast (10 pcs)":
                base_food = dict_add(base_food, {"French Toast (pcs)": spec["food"]["French Toast (pcs)"]})

            # Packaging: eggs + potatoes + protein + chosen griddle
            # Start with eggs + potatoes half pans, plus protein bases
            # We reconstruct packaging per selection to avoid counting both griddles.
            eggs_hp = {"Small Combo Box": 1, "Medium Combo Box": 2, "Large Combo Box": 4}[tier]
            pot_hp = {"Small Combo Box": 1, "Medium Combo Box": 2, "Large Combo Box": 4}[tier]
            protein_bases = {"Small Combo Box": 1, "Medium Combo Box": 2, "Large Combo Box": 4}[tier]
            pancakes_hp = {"Small Combo Box": 1, "Medium Combo Box": 2, "Large Combo Box": 4}[tier]
            french_toast_hp = {"Small Combo Box": 2, "Medium Combo Box": 4, "Large Combo Box": 8}[tier]

            packaging = {"Half Pans": eggs_hp + pot_hp, "Large Bases": protein_bases}
            if griddle == "Buttermilk Pancakes (20 pcs)":
                packaging["Half Pans"] += pancakes_hp
            elif griddle == "French Toast (10 pcs)":
                packaging["Half Pans"] += french_toast_hp

            # Condiments: butter/syrup/ketchup always; powdered sugar only if french toast
            cond = {
                "Butter Packets": spec["condiments"]["Butter Packets"],
                "Syrup Packets": spec["condiments"]["Syrup Packets"],
                "Ketchup Packets": spec["condiments"]["Ketchup Packets"],
            }
            if griddle == "French Toast (10 pcs)":
                cond["Powdered Sugar Souffle (2 oz)"] = spec["condiments"]["Powdered Sugar Souffle (2 oz)"]

            # Serveware from tier
            serve = dict(spec["serveware"])

            total_food = dict_add(total_food, dict_mul(base_food, qty))
            total_packaging = dict_add(total_packaging, dict_mul(packaging, qty))
            total_condiments = dict_add(total_condiments, dict_mul(cond, qty))
            total_serveware = dict_add(total_serveware, dict_mul(serve, qty))

        else:
            spec = ALACARTE_LOOKUP[line.key.item_id]
            total_food = dict_add(total_food, dict_mul(spec["food"], qty))
            total_packaging = dict_add(total_packaging, dict_mul(spec["packaging"], qty))
            total_condiments = dict_add(total_condiments, dict_mul(spec["condiments"], qty))
            total_serveware = dict_add(total_serveware, dict_mul(spec["serveware"], qty))

    # Clean up helper key if present
    if "Protein (pcs)" in total_food:
        # It's a generic helper. Keep the specific protein buckets.
        total_food.pop("Protein (pcs)", None)

    return total_food, total_packaging, total_condiments, total_serveware


# =========================================================
# UI
# =========================================================

init_state()

left, right = st.columns([1, 1])

with left:
    st.subheader("Build Order")

    headcount = st.number_input("Headcount (if provided)", min_value=0, value=0, step=1)
    ordered_utensils = st.number_input("Utensil sets ordered (trust this number)", min_value=0, value=0, step=1)

    st.divider()

    st.markdown("### — Breakfast Combo Boxes —")
    combo_tier = st.selectbox("Combo size", list(COMBO_TIERS.keys()), index=0)
    combo_protein = st.selectbox("Protein", PROTEINS, index=0)
    combo_griddle = st.selectbox("Griddle item", GRIDDLE_CHOICES, index=0)
    combo_qty = st.number_input("Combo quantity", min_value=1, value=1, step=1)

    add_combo = st.button("Add Combo", type="primary", use_container_width=True)
    if add_combo:
        label = f"{combo_tier} | {combo_protein.replace(' (20 pcs)','')} | {combo_griddle.split(' (')[0]}"
        key = LineKey(kind="combo", item_id=combo_tier, protein=combo_protein, griddle=combo_griddle)
        merge_or_add_line(OrderLine(key=key, label=label, qty=int(combo_qty)))

        # Reset behavior (per your spec)
        st.session_state["_reset_combo"] = True
        st.rerun()

    # Reset combo selectors after add
    if st.session_state.get("_reset_combo"):
        st.session_state["_reset_combo"] = False
        # Streamlit selectboxes reset only via key or rerun logic; we're already rerunning.
        # We keep defaults (Small, first protein, first griddle). Quantity default is 1.

    st.divider()

    st.markdown("### — À La Carte Items —")
    # Render grouped menu using a selectbox with labels; disabled "headers" won't be selectable,
    # so we emulate by mapping labels->id and excluding headers from selection options.
    alacarte_options = [label for (label, item_id) in ALACARTE_MENU if item_id is not None]
    alacarte_label_to_id = {label: item_id for (label, item_id) in ALACARTE_MENU if item_id is not None}

    alacarte_pick_label = st.selectbox("Select item", alacarte_options, index=0)
    alacarte_qty = st.number_input("À la carte quantity", min_value=1, value=1, step=1)

    add_alacarte = st.button("Add À La Carte", use_container_width=True)
    if add_alacarte:
        item_id = alacarte_label_to_id[alacarte_pick_label]
        key = LineKey(kind="alacarte", item_id=item_id)
        merge_or_add_line(OrderLine(key=key, label=alacarte_pick_label, qty=int(alacarte_qty)))
        st.rerun()

with right:
    st.subheader("Current Order")

    if not st.session_state.lines:
        st.info("Add items on the left to build an order.")
    else:
        # Display and allow edit/remove
        for idx, line in enumerate(st.session_state.lines):
            row = st.container(border=True)
            c1, c2, c3 = row.columns([6, 2, 2])

            with c1:
                st.markdown(f"**{line.label}**")

            with c2:
                st.markdown(f"Qty: **{line.qty}**")

            with c3:
                edit = st.button("Edit", key=f"edit_{idx}")
                remove = st.button("Remove", key=f"remove_{idx}")

            if remove:
                remove_line(idx)
                st.rerun()

            if edit:
                st.session_state.edit_idx = idx
                st.rerun()

            if st.session_state.edit_idx == idx:
                row2 = st.container(border=True)
                st.markdown("**Edit Line**")

                # Editable fields differ for combo vs alacarte
                new_qty = row2.number_input("Quantity", min_value=1, value=int(line.qty), step=1, key=f"edit_qty_{idx}")

                if line.key.kind == "combo":
                    new_tier = row2.selectbox("Combo size", list(COMBO_TIERS.keys()),
                                             index=list(COMBO_TIERS.keys()).index(line.key.item_id),
                                             key=f"edit_tier_{idx}")
                    new_protein = row2.selectbox("Protein", PROTEINS,
                                                 index=PROTEINS.index(line.key.protein),
                                                 key=f"edit_protein_{idx}")
                    new_griddle = row2.selectbox("Griddle item", GRIDDLE_CHOICES,
                                                 index=GRIDDLE_CHOICES.index(line.key.griddle),
                                                 key=f"edit_griddle_{idx}")
                    new_label = f"{new_tier} | {new_protein.replace(' (20 pcs)','')} | {new_griddle.split(' (')[0]}"
                    new_key = LineKey(kind="combo", item_id=new_tier, protein=new_protein, griddle=new_griddle)
                else:
                    # Alacarte: choose a different item if needed
                    al_labels = [l for (l, i) in ALACARTE_MENU if i is not None]
                    current_label = line.label
                    default_index = al_labels.index(current_label) if current_label in al_labels else 0
                    new_label = row2.selectbox("Item", al_labels, index=default_index, key=f"edit_al_{idx}")
                    new_id = alacarte_label_to_id[new_label]
                    new_key = LineKey(kind="alacarte", item_id=new_id)

                s1, s2 = row2.columns([1, 1])
                if s1.button("Save", key=f"save_{idx}", type="primary"):
                    # Remove old line, then merge/add new
                    old = st.session_state.lines.pop(idx)
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
# Output (single page)
# =========================================================
st.subheader("Prep Output (Print / Download)")

if not st.session_state.lines:
    st.caption("Build an order above to generate the prep sheet.")
else:
    total_food, total_packaging, total_condiments, total_serveware = build_totals(st.session_state.lines)

    # Utensil recommendation logic (simple, per your spec)
    recommended_utensils = int(headcount) if headcount and headcount > 0 else 0

    # Guardrail warning: combos + extra breakfast components a la carte
    has_combo = any(l.key.kind == "combo" for l in st.session_state.lines)
    has_breakfast_components = any(
        (l.key.kind == "alacarte" and l.key.item_id in {"eggs_40oz", "potatoes_40oz", "bacon_20", "psl_20", "ham_20"})
        for l in st.session_state.lines
    )
    if has_combo and has_breakfast_components:
        st.warning("Quick check: You have Combo Boxes plus extra breakfast components à la carte. Totally fine if intentional.")

    # Order Summary
    st.markdown("## 1) Order Summary")
    s1, s2, s3 = st.columns(3)
    s1.metric("Headcount", int(headcount))
    s2.metric("Utensil sets ordered", int(ordered_utensils))
    s3.metric("Utensil sets recommended", int(recommended_utensils))

    if headcount > 0 and ordered_utensils > 0:
        if ordered_utensils < headcount:
            st.error(f"Utensil check: Ordered {int(ordered_utensils)} but headcount is {int(headcount)}. Recommend at least {int(recommended_utensils)}.")
        elif ordered_utensils > headcount * 1.25:
            st.info(f"Utensil check: Ordered {int(ordered_utensils)} for headcount {int(headcount)}. That’s plenty. Recommend ~{int(recommended_utensils)}.")
        else:
            st.success("Utensil check: Ordered utensils look aligned with headcount.")
    elif headcount > 0 and ordered_utensils == 0:
        st.warning(f"No utensil count entered. Recommend ~{int(recommended_utensils)} utensil sets for headcount {int(headcount)}.")

    # Food Totals
    st.markdown("## 2) Food Totals")
    food_df = pd.DataFrame(
        [{"Item": k, "Total": v} for k, v in sorted(total_food.items(), key=lambda x: x[0])]
    )
    st.dataframe(food_df, width="stretch", hide_index=True)

    # Packaging Totals
    st.markdown("## 3) Packaging Totals")
    pack_df = pd.DataFrame(
        [{"Packaging": k, "Total": v} for k, v in sorted(total_packaging.items(), key=lambda x: x[0])]
    )
    st.dataframe(pack_df, width="stretch", hide_index=True)

    # Condiments
    st.markdown("## 4) Condiments")
    cond_df = pd.DataFrame(
        [{"Condiment": k, "Total": v} for k, v in sorted(total_condiments.items(), key=lambda x: x[0])]
    )
    st.dataframe(cond_df, width="stretch", hide_index=True)

    # Serveware
    st.markdown("## 5) Serveware")
    serve_items = dict(total_serveware)
    if ordered_utensils and ordered_utensils > 0:
        serve_items["Utensil Sets (ordered)"] = int(ordered_utensils)
    if recommended_utensils and recommended_utensils > 0:
        serve_items["Utensil Sets (recommended)"] = int(recommended_utensils)

    serve_df = pd.DataFrame(
        [{"Serveware": k, "Total": v} for k, v in sorted(serve_items.items(), key=lambda x: x[0])]
    )
    st.dataframe(serve_df, width="stretch", hide_index=True)

    st.divider()

    # Download Prep Sheet
    st.markdown("## Download")
    export_rows = []

    def add_section(section: str, d: Dict[str, float], name_col: str):
        for k, v in d.items():
            export_rows.append({"Section": section, name_col: k, "Total": v})

    add_section("Food", total_food, "Name")
    add_section("Packaging", total_packaging, "Name")
    add_section("Condiments", total_condiments, "Name")
    add_section("Serveware", serve_items, "Name")

    export_df = pd.DataFrame(export_rows)
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Prep Sheet (CSV)",
        data=csv_bytes,
        file_name="catering_prep_sheet.csv",
        mime="text/csv",
        use_container_width=True,
    )
