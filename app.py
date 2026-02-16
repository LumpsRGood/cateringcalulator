import pandas as pd
import streamlit as st
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
# Combo options (name-only so counts scale by tier)
# =========================================================
PROTEINS = ["Bacon", "Pork Sausage Links", "Ham Slices"]
GRIDDLE_CHOICES = ["Buttermilk Pancakes", "French Toast"]

# =========================================================
# Combo tier specs (per 1 combo of that size)
# Quantities & packaging match the plating/packaging guide.
# =========================================================
COMBO_TIERS = {
    "Small Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 40,
            "Breakfast Potatoes (oz)": 60,
            "Protein (pcs)": 20,
            "Buttermilk Pancakes (pcs)": 20,
            "French Toast (pcs)": 10,
        },
        "condiments": {
            "Butter Packets": 10,
            "Syrup Packets": 10,
            "Ketchup Packets": 10,
            "Powdered Sugar Souffle (2 oz)": 2,  # French toast only
        },
        "serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 10},
        "packaging_ref": {
            "Eggs Half Pans": 1,
            "Potatoes Half Pans": 1,
            "Protein Large Bases": 1,
            "Pancakes Half Pans": 1,
            "French Toast Half Pans": 2,
        },
    },
    "Medium Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 80,
            "Breakfast Potatoes (oz)": 120,
            "Protein (pcs)": 40,
            "Buttermilk Pancakes (pcs)": 40,
            "French Toast (pcs)": 20,
        },
        "condiments": {
            "Butter Packets": 20,
            "Syrup Packets": 20,
            "Ketchup Packets": 20,
            "Powdered Sugar Souffle (2 oz)": 4,
        },
        "serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 20},
        "packaging_ref": {
            "Eggs Half Pans": 2,
            "Potatoes Half Pans": 2,
            "Protein Large Bases": 2,
            "Pancakes Half Pans": 2,
            "French Toast Half Pans": 4,
        },
    },
    "Large Combo Box": {
        "food": {
            "Scrambled Eggs (oz)": 160,
            "Breakfast Potatoes (oz)": 240,
            "Protein (pcs)": 80,
            "Buttermilk Pancakes (pcs)": 80,
            "French Toast (pcs)": 40,
        },
        "condiments": {
            "Butter Packets": 40,
            "Syrup Packets": 40,
            "Ketchup Packets": 40,
            "Powdered Sugar Souffle (2 oz)": 8,
        },
        "serveware": {"Serving Forks": 8, "Serving Tongs": 5, "Plates": 40},
        "packaging_ref": {
            "Eggs Half Pans": 4,
            "Potatoes Half Pans": 4,
            "Protein Large Bases": 4,
            "Pancakes Half Pans": 4,
            "French Toast Half Pans": 8,
        },
    },
}

# =========================================================
# À La Carte groups + items
# Each item defines:
# - food totals (oz/pcs)
# - packaging totals (Half Pans, Large Bases, Soup Cups, etc.)
# - condiments totals (packets/cups)
# - serveware totals (plates, tongs, forks, spoons, cups, etc.)
# =========================================================

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

    ("Burgers & Chicken (10 pcs)", [
        ("steakburgers_10", "Steakburgers (10 pcs)",
         {"Steakburgers (pcs)": 10},
         {"Half Pans": 1},
         {"Mayo Packets": 10, "Ketchup Packets": 10, "Mustard Packets": 10,
          "BBQ Soup Cup": 1, "IHOP Sauce Soup Cup": 1, "Pickle Chips (pcs)": 50},
         {"Serving Tongs": 2, "Spoons": 2, "Plates": 10}),
        ("crispy_chx_sand_10", "Crispy Chicken Sandwiches (10 pcs)",
         {"Crispy Chicken Sandwiches (pcs)": 10},
         {"Half Pans": 1},
         {"Mayo Packets": 10, "Ketchup Packets": 10, "Mustard Packets": 10,
          "BBQ Soup Cup": 1, "IHOP Sauce Soup Cup": 1, "Pickle Chips (pcs)": 50},
         {"Serving Tongs": 2, "Spoons": 2, "Plates": 10}),
        ("grilled_chx_sand_10", "Grilled Chicken Sandwiches (10 pcs)",
         {"Grilled Chicken Sandwiches (pcs)": 10},
         {"Half Pans": 1},
         {"Mayo Packets": 10, "Ketchup Packets": 10, "Mustard Packets": 10,
          "BBQ Soup Cup": 1, "IHOP Sauce Soup Cup": 1, "Pickle Chips (pcs)": 50},
         {"Serving Tongs": 2, "Spoons": 2, "Plates": 10}),
        ("sandwich_toppings_halfpan", "Sandwich Toppings (1 half pan)",
         {},
         {"Half Pans": 1},
         {},
         {}),
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

# Flatten for lookup + dropdown
ALACARTE_LOOKUP: Dict[str, Dict] = {}
ALACARTE_LABELS: List[str] = []
ALACARTE_LABEL_TO_ID: Dict[str, str] = {}
GROUPED_OPTIONS: List[str] = []  # For display only, but we’ll use a single selectbox list

for group_name, items in ALACARTE_GROUPS:
    # We'll simulate grouping by inserting a visual divider label (not selectable)
    GROUPED_OPTIONS.append(f"— {group_name} —")
    for item_id, label, food, packaging, condiments, serveware in items:
        ALACARTE_LOOKUP[item_id] = {
            "label": label,
            "food": food,
            "packaging": packaging,
            "condiments": condiments,
            "serveware": serveware,
            "group": group_name,
        }
        ALACARTE_LABELS.append(label)
        ALACARTE_LABEL_TO_ID[label] = item_id
        GROUPED_OPTIONS.append(label)


# =========================================================
# Helper functions
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
    if "combo_tier" not in st.session_state:
        st.session_state.combo_tier = list(COMBO_TIERS.keys())[0]
    if "combo_protein" not in st.session_state:
        st.session_state.combo_protein = PROTEINS[0]
    if "combo_griddle" not in st.session_state:
        st.session_state.combo_griddle = GRIDDLE_CHOICES[0]
    if "combo_qty" not in st.session_state:
        st.session_state.combo_qty = 1
    if "al_label" not in st.session_state:
        st.session_state.al_label = ALACARTE_LABELS[0]
    if "al_qty" not in st.session_state:
        st.session_state.al_qty = 1

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
    st.session_state.combo_tier = list(COMBO_TIERS.keys())[0]  # Small
    st.session_state.combo_protein = PROTEINS[0]
    st.session_state.combo_griddle = GRIDDLE_CHOICES[0]
    st.session_state.combo_qty = 1

def reset_alacarte_form():
    st.session_state.al_label = ALACARTE_LABELS[0]
    st.session_state.al_qty = 1

def build_totals(lines: List[OrderLine]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
    total_food: Dict[str, float] = {}
    total_packaging: Dict[str, float] = {}
    total_condiments: Dict[str, float] = {}
    total_serveware: Dict[str, float] = {}

    for line in lines:
        qty = int(line.qty)

        if line.key.kind == "combo":
            tier = line.key.item_id
            protein = line.key.protein
            griddle = line.key.griddle
            spec = COMBO_TIERS[tier]

            # Food: eggs + potatoes + chosen protein + chosen griddle
            base_food = {
                "Scrambled Eggs (oz)": spec["food"]["Scrambled Eggs (oz)"],
                "Breakfast Potatoes (oz)": spec["food"]["Breakfast Potatoes (oz)"],
            }

            # Specific protein bucket
            if protein:
                base_food = dict_add(base_food, {f"{protein} (pcs)": spec["food"]["Protein (pcs)"]})

            # Griddle bucket
            if griddle == "Buttermilk Pancakes":
                base_food = dict_add(base_food, {"Buttermilk Pancakes (pcs)": spec["food"]["Buttermilk Pancakes (pcs)"]})
            elif griddle == "French Toast":
                base_food = dict_add(base_food, {"French Toast (pcs)": spec["food"]["French Toast (pcs)"]})

            # Packaging: eggs + potatoes always, plus protein base, plus chosen griddle half pans
            eggs_hp = spec["packaging_ref"]["Eggs Half Pans"]
            pot_hp = spec["packaging_ref"]["Potatoes Half Pans"]
            protein_bases = spec["packaging_ref"]["Protein Large Bases"]
            pancakes_hp = spec["packaging_ref"]["Pancakes Half Pans"]
            ft_hp = spec["packaging_ref"]["French Toast Half Pans"]

            packaging = {"Half Pans": eggs_hp + pot_hp, "Large Bases": protein_bases}
            if griddle == "Buttermilk Pancakes":
                packaging["Half Pans"] += pancakes_hp
            elif griddle == "French Toast":
                packaging["Half Pans"] += ft_hp

            # Condiments: butter/syrup/ketchup always; powdered sugar only for French toast
            cond = {
                "Butter Packets": spec["condiments"]["Butter Packets"],
                "Syrup Packets": spec["condiments"]["Syrup Packets"],
                "Ketchup Packets": spec["condiments"]["Ketchup Packets"],
            }
            if griddle == "French Toast":
                cond["Powdered Sugar Souffle (2 oz)"] = spec["condiments"]["Powdered Sugar Souffle (2 oz)"]

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

    return total_food, total_packaging, total_condiments, total_serveware


# =========================================================
# UI
# =========================================================

init_state()

st.title("IHOP Catering Calculator")
st.caption("Simple dropdown entry for managers. Generates a single-page prep sheet with totals and a CSV download.")

left, right = st.columns([1, 1])

with left:
    st.subheader("Build Order")

    headcount = st.number_input("Headcount (if provided)", min_value=0, value=0, step=1)
    ordered_utensils = st.number_input("Utensil sets ordered (trust this number)", min_value=0, value=0, step=1)

    st.divider()

    st.markdown("### — Breakfast Combo Boxes —")
    combo_tier = st.selectbox("Combo size", list(COMBO_TIERS.keys()), index=list(COMBO_TIERS.keys()).index(st.session_state.combo_tier), key="combo_tier")
    combo_protein = st.selectbox("Protein", PROTEINS, index=PROTEINS.index(st.session_state.combo_protein), key="combo_protein")
    combo_griddle = st.selectbox("Griddle item", GRIDDLE_CHOICES, index=GRIDDLE_CHOICES.index(st.session_state.combo_griddle), key="combo_griddle")
    combo_qty = st.number_input("Combo quantity", min_value=1, value=int(st.session_state.combo_qty), step=1, key="combo_qty")

    if st.button("Add Combo", type="primary", use_container_width=True):
        label = f"{combo_tier} | {combo_protein} | {combo_griddle}"
        key = LineKey(kind="combo", item_id=combo_tier, protein=combo_protein, griddle=combo_griddle)
        merge_or_add_line(OrderLine(key=key, label=label, qty=int(combo_qty)))
        reset_combo_form()
        st.rerun()

    st.divider()

    st.markdown("### — À La Carte Items —")

    # Show grouped list, but prevent selecting group headers by filtering in UI:
    # We'll render a selectbox that includes only real item labels, and show a group legend above.
    # (Streamlit selectbox can't truly disable options, so we keep the UX clean.)
    # If you really want visible group headers inside the dropdown later, we can build a custom component.
    st.caption("Tip: Items are grouped below; use the dropdown to select an item.")
    group_help = []
    for g, items in ALACARTE_GROUPS:
        group_help.append(f"• {g} ({len(items)})")
    st.caption("Groups: " + "  |  ".join(group_help))

    al_label = st.selectbox("Select item", ALACARTE_LABELS, index=ALACARTE_LABELS.index(st.session_state.al_label), key="al_label")
    al_qty = st.number_input("À la carte quantity", min_value=1, value=int(st.session_state.al_qty), step=1, key="al_qty")

    if st.button("Add À La Carte", use_container_width=True):
        item_id = ALACARTE_LABEL_TO_ID[al_label]
        key = LineKey(kind="alacarte", item_id=item_id)
        merge_or_add_line(OrderLine(key=key, label=al_label, qty=int(al_qty)))
        reset_alacarte_form()
        st.rerun()

with right:
    st.subheader("Current Order")

    if not st.session_state.lines:
        st.info("Add items on the left to build an order.")
    else:
        for idx, line in enumerate(st.session_state.lines):
            box = st.container(border=True)
            c1, c2, c3 = box.columns([6, 2, 2])

            with c1:
                st.markdown(f"**{line.label}**")
            with c2:
                st.markdown(f"Qty: **{line.qty}**")
            with c3:
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
                    new_tier = edit.selectbox("Combo size", list(COMBO_TIERS.keys()),
                                              index=list(COMBO_TIERS.keys()).index(line.key.item_id),
                                              key=f"edit_tier_{idx}")
                    new_protein = edit.selectbox("Protein", PROTEINS,
                                                 index=PROTEINS.index(line.key.protein),
                                                 key=f"edit_protein_{idx}")
                    new_griddle = edit.selectbox("Griddle item", GRIDDLE_CHOICES,
                                                 index=GRIDDLE_CHOICES.index(line.key.griddle),
                                                 key=f"edit_griddle_{idx}")
                    new_label = f"{new_tier} | {new_protein} | {new_griddle}"
                    new_key = LineKey(kind="combo", item_id=new_tier, protein=new_protein, griddle=new_griddle)
                else:
                    current_label = line.label
                    default_index = ALACARTE_LABELS.index(current_label) if current_label in ALACARTE_LABELS else 0
                    new_label = edit.selectbox("Item", ALACARTE_LABELS, index=default_index, key=f"edit_al_{idx}")
                    new_id = ALACARTE_LABEL_TO_ID[new_label]
                    new_key = LineKey(kind="alacarte", item_id=new_id)

                s1, s2 = edit.columns(2)
                if s1.button("Save", key=f"save_{idx}", type="primary"):
                    # Remove old line, then merge/add new
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
# Output (single page)
# =========================================================
st.subheader("Prep Output (Print / Download)")

if not st.session_state.lines:
    st.caption("Build an order above to generate the prep sheet.")
else:
    total_food, total_packaging, total_condiments, total_serveware = build_totals(st.session_state.lines)

    recommended_utensils = int(headcount) if headcount and headcount > 0 else 0

    # Guardrail: combos + extra breakfast components
    has_combo = any(l.key.kind == "combo" for l in st.session_state.lines)
    has_breakfast_components = any(
        (l.key.kind == "alacarte" and l.key.item_id in {"eggs_40oz", "potatoes_40oz", "bacon_20", "psl_20", "ham_20"})
        for l in st.session_state.lines
    )
    if has_combo and has_breakfast_components:
        st.warning("Quick check: You have Combo Boxes plus extra breakfast components à la carte. Totally fine if intentional.")

    # 1) Order Summary
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

    # 2) Food Totals
    st.markdown("## 2) Food Totals")
    food_df = pd.DataFrame([{"Item": k, "Total": v} for k, v in sorted(total_food.items(), key=lambda x: x[0])])
    st.dataframe(food_df, width="stretch", hide_index=True)

    # 3) Packaging Totals
    st.markdown("## 3) Packaging Totals")
    pack_df = pd.DataFrame([{"Packaging": k, "Total": v} for k, v in sorted(total_packaging.items(), key=lambda x: x[0])])
    st.dataframe(pack_df, width="stretch", hide_index=True)

    # 4) Condiments
    st.markdown("## 4) Condiments")
    cond_df = pd.DataFrame([{"Condiment": k, "Total": v} for k, v in sorted(total_condiments.items(), key=lambda x: x[0])])
    st.dataframe(cond_df, width="stretch", hide_index=True)

    # 5) Serveware
    st.markdown("## 5) Serveware")
    serve_items = dict(total_serveware)
    if ordered_utensils and ordered_utensils > 0:
        serve_items["Utensil Sets (ordered)"] = int(ordered_utensils)
    if recommended_utensils and recommended_utensils > 0:
        serve_items["Utensil Sets (recommended)"] = int(recommended_utensils)

    serve_df = pd.DataFrame([{"Serveware": k, "Total": v} for k, v in sorted(serve_items.items(), key=lambda x: x[0])])
    st.dataframe(serve_df, width="stretch", hide_index=True)

    st.divider()

    # Download
    st.markdown("## Download")
    export_rows = []

    def add_section(section: str, d: Dict[str, float]):
        for k, v in d.items():
            export_rows.append({"Section": section, "Name": k, "Total": v})

    add_section("Food", total_food)
    add_section("Packaging", total_packaging)
    add_section("Condiments", total_condiments)
    add_section("Serveware", serve_items)

    export_df = pd.DataFrame(export_rows)
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Prep Sheet (CSV)",
        data=csv_bytes,
        file_name="catering_prep_sheet.csv",
        mime="text/csv",
        use_container_width=True,
    )
