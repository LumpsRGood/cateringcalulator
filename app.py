import math
import pandas as pd
import streamlit as st

st.set_page_config(page_title="IHOP Catering Prep Calculator", layout="wide")

st.title("IHOP Catering Prep Calculator")
st.caption("Dropdown entry for managers. Calculates food + packaging + condiments. Trusts ordered utensils, but recommends based on headcount when mismatched.")

# -----------------------------
# Catalog (based on Packaging/Plating Guide)
# Units:
# - oz for many items
# - pcs for count items
# Packaging:
# - half_pan, large_base, soup_cup, pouch, coffee_box
# Condiments/serveware:
# - butter_pkt, syrup_pkt, ketchup_pkt, powdered_sugar_souffle
# - plates
# - serving_tongs, serving_forks, spoons
# -----------------------------

CATALOG = [
    # Breakfast Combo Boxes (Small/Medium/Large)
    {
        "Item": "Breakfast Combo Box - Small (6-10)",
        "Food": {"Scrambled Eggs (oz)": 40, "Breakfast Potatoes (oz)": 60, "Protein (pcs)": 20, "Pancakes (pcs)": 20, "French Toast (pcs)": 10},
        "Packaging": {"Half Pans": 1 + 1 + 1 + 2, "Large Bases": 1},  # eggs 1, potatoes 1, pancakes 1, french toast 2 half pans
        "Condiments": {"Butter Packets": 10, "Syrup Packets": 10, "Ketchup Packets": 10, "Powdered Sugar Souffle (2oz)": 2},
        "Serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 10},
        "Notes": "Combo chart baseline. Protein is bacon/sausage/ham."
    },
    {
        "Item": "Breakfast Combo Box - Medium (15-20)",
        "Food": {"Scrambled Eggs (oz)": 80, "Breakfast Potatoes (oz)": 120, "Protein (pcs)": 40, "Pancakes (pcs)": 40, "French Toast (pcs)": 20},
        "Packaging": {"Half Pans": 2 + 2 + 2 + 4, "Large Bases": 2},
        "Condiments": {"Butter Packets": 20, "Syrup Packets": 20, "Ketchup Packets": 20, "Powdered Sugar Souffle (2oz)": 4},
        "Serveware": {"Serving Forks": 2, "Serving Tongs": 2, "Plates": 20},
        "Notes": "Combo chart baseline. Protein is bacon/sausage/ham."
    },
    {
        "Item": "Breakfast Combo Box - Large (30-40)",
        "Food": {"Scrambled Eggs (oz)": 160, "Breakfast Potatoes (oz)": 240, "Protein (pcs)": 80, "Pancakes (pcs)": 80, "French Toast (pcs)": 40},
        "Packaging": {"Half Pans": 4 + 4 + 4 + 8, "Large Bases": 4},
        "Condiments": {"Butter Packets": 40, "Syrup Packets": 40, "Ketchup Packets": 40, "Powdered Sugar Souffle (2oz)": 8},
        "Serveware": {"Serving Forks": 8, "Serving Tongs": 5, "Plates": 40},
        "Notes": "Combo chart baseline. Protein is bacon/sausage/ham."
    },

    # A la carte: Griddle faves
    {
        "Item": "Buttermilk Pancakes (Feeds 6-10)",
        "Food": {"Pancakes (pcs)": 20},
        "Packaging": {"Half Pans": 1},
        "Condiments": {"Syrup Packets": 10, "Butter Packets": 10},
        "Serveware": {"Serving Tongs": 1, "Plates": 10},
        "Notes": "A la carte griddle faves."
    },
    {
        "Item": "French Toast (Feeds 6-10)",
        "Food": {"French Toast (pcs)": 10},
        "Packaging": {"Half Pans": 2},
        "Condiments": {"Syrup Packets": 10, "Butter Packets": 10, "Powdered Sugar Souffle (2oz)": 2},
        "Serveware": {"Serving Tongs": 1, "Plates": 10},
        "Notes": "A la carte griddle faves."
    },
    {
        "Item": "Strawberry/Blueberry Topping",
        "Food": {},
        "Packaging": {"Large Bases": 1},
        "Condiments": {},
        "Serveware": {"Serving Forks": 1},
        "Notes": "Topping base."
    },

    # Burritos
    {
        "Item": "Classic Breakfast Burritos (10 pcs)",
        "Food": {"Breakfast Burritos (pcs)": 10},
        "Packaging": {"Half Pans": 2},
        "Condiments": {"Salsa Soup Cups": 2},
        "Serveware": {"Spoons": 2},
        "Notes": "Feeds 10."
    },

    # Chicken Strips
    {
        "Item": "Chicken Strips (40 pcs)",
        "Food": {"Chicken Strips (pcs)": 40},
        "Packaging": {"Half Pans": 1},
        "Condiments": {"BBQ Soup Cup": 1, "IHOP Sauce Soup Cup": 1, "Ranch Soup Cup": 1},
        "Serveware": {"Serving Tongs": 1, "Spoons": 3, "Plates": 10},
        "Notes": "Feeds 10."
    },

    # Sides (feeds 6-10)
    {
        "Item": "Fresh Fruit (Feeds 6-10)",
        "Food": {"Fresh Fruit (oz)": 40},
        "Packaging": {"Large Bases": 1},
        "Condiments": {},
        "Serveware": {"Serving Forks": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "French Fries (Feeds 6-10)",
        "Food": {"French Fries (oz)": 60},
        "Packaging": {"Half Pans": 1},
        "Condiments": {"Ketchup Packets": 10},
        "Serveware": {"Serving Tongs": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Onion Rings (Feeds 6-10)",
        "Food": {"Onion Rings (oz)": 60},
        "Packaging": {"Half Pans": 2},
        "Condiments": {"Ketchup Packets": 10},
        "Serveware": {"Serving Tongs": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Scrambled Eggs (Feeds 6-10)",
        "Food": {"Scrambled Eggs (oz)": 40},
        "Packaging": {"Half Pans": 1},
        "Condiments": {},
        "Serveware": {"Serving Forks": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Breakfast Potatoes (Feeds 6-10)",
        "Food": {"Breakfast Potatoes (oz)": 40},
        "Packaging": {"Half Pans": 1},
        "Condiments": {"Ketchup Packets": 10},
        "Serveware": {"Serving Forks": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Bacon (Feeds 6-10)",
        "Food": {"Bacon (pcs)": 20},
        "Packaging": {"Large Bases": 1},
        "Condiments": {},
        "Serveware": {"Serving Tongs": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Sausage Links (Feeds 6-10)",
        "Food": {"Sausage Links (pcs)": 20},
        "Packaging": {"Large Bases": 1},
        "Condiments": {},
        "Serveware": {"Serving Tongs": 1},
        "Notes": "Feeds 6-10."
    },
    {
        "Item": "Ham Slices (Feeds 6-10)",
        "Food": {"Ham Slices (pcs)": 20},
        "Packaging": {"Large Bases": 1},
        "Condiments": {},
        "Serveware": {"Serving Tongs": 1},
        "Notes": "Feeds 6-10."
    },

    # Beverages
    {
        "Item": "Coffee Box (96 oz)",
        "Food": {"Coffee (oz)": 96},
        "Packaging": {"Coffee Boxes": 1},
        "Condiments": {"Sugars": 10, "Creamers": 10},
        "Serveware": {"Hot Cups + Lids + Sleeves": 10, "Stirrers": 10},
        "Notes": "Hot beverage container."
    },
    {
        "Item": "Cold Beverage Pouch (128 oz)",
        "Food": {"Cold Beverage (oz)": 128},
        "Packaging": {"Beverage Pouches": 1},
        "Condiments": {},
        "Serveware": {"Cold Cups + Lids": 10, "Wrapped Straws": 10},
        "Notes": "Iced tea/juice/lemonade/fountain drink pouch."
    },
]

CATALOG_DF = pd.DataFrame(CATALOG)

def merge_dicts_sum(dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out

def multiply_dict(d, n):
    return {k: v * n for k, v in d.items()}

# -----------------------------
# Order builder
# -----------------------------
left, right = st.columns([1, 1])

with left:
    st.subheader("Build the Order")
    headcount = st.number_input("Headcount (if provided on the order)", min_value=0, value=0, step=1)

    ordered_utensils = st.number_input(
        "Utensils ordered (trust this number)",
        min_value=0, value=0, step=1,
        help="We will trust what was ordered, but we’ll recommend based on headcount if there’s a mismatch."
    )

    st.divider()

    item = st.selectbox("Add item", CATALOG_DF["Item"].tolist())
    qty = st.number_input("Quantity", min_value=1, value=1, step=1)

    if "lines" not in st.session_state:
        st.session_state.lines = []

    add = st.button("Add to order", type="primary")
    if add:
        st.session_state.lines.append({"Item": item, "Qty": int(qty)})

    if st.session_state.lines:
        st.write("Current order lines:")
        st.dataframe(pd.DataFrame(st.session_state.lines), use_container_width=True, hide_index=True)
        if st.button("Clear order"):
            st.session_state.lines = []

with right:
    st.subheader("Prep Output")

    if not st.session_state.lines:
        st.info("Add items on the left to see totals.")
    else:
        # Expand order lines into totals
        food_dicts = []
        packaging_dicts = []
        cond_dicts = []
        serve_dicts = []

        for line in st.session_state.lines:
            row = CATALOG_DF[CATALOG_DF["Item"] == line["Item"]].iloc[0].to_dict()
            n = line["Qty"]
            food_dicts.append(multiply_dict(row["Food"], n))
            packaging_dicts.append(multiply_dict(row["Packaging"], n))
            cond_dicts.append(multiply_dict(row["Condiments"], n))
            serve_dicts.append(multiply_dict(row["Serveware"], n))

        total_food = merge_dicts_sum(food_dicts)
        total_packaging = merge_dicts_sum(packaging_dicts)
        total_condiments = merge_dicts_sum(cond_dicts)
        total_serveware = merge_dicts_sum(serve_dicts)

        # Recommended utensil count based on headcount (simple rule: 1 utensil set per person)
        recommended_utensils = headcount if headcount > 0 else 0

        # Mismatch logic (only warn if both provided)
        if headcount > 0 and ordered_utensils > 0:
            if ordered_utensils < headcount:
                st.warning(f"Utensil check: Ordered {ordered_utensils}, but headcount is {headcount}. Recommend at least {recommended_utensils}.")
            elif ordered_utensils > headcount * 1.25:
                st.info(f"Utensil check: Ordered {ordered_utensils} for headcount {headcount}. That’s plenty. (Recommend ~{recommended_utensils}.)")
            else:
                st.success("Utensil check: Ordered utensils look aligned with headcount.")
        elif headcount > 0 and ordered_utensils == 0:
            st.warning(f"No utensil count entered. Recommend ~{recommended_utensils} utensil sets for headcount {headcount}.")

        # Display totals in clean sections
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("### Food Totals")
            food_df = pd.DataFrame([{"Item": k, "Total": v} for k, v in total_food.items()]).sort_values("Item")
            st.dataframe(food_df, use_container_width=True, hide_index=True)

            st.markdown("### Packaging Totals")
            pack_df = pd.DataFrame([{"Packaging": k, "Total": v} for k, v in total_packaging.items()]).sort_values("Packaging")
            st.dataframe(pack_df, use_container_width=True, hide_index=True)

        with c2:
            st.markdown("### Condiments")
            cond_df = pd.DataFrame([{"Condiment": k, "Total": v} for k, v in total_condiments.items()]).sort_values("Condiment")
            st.dataframe(cond_df, use_container_width=True, hide_index=True)

            st.markdown("### Serveware")
            serve_df = pd.DataFrame([{"Serveware": k, "Total": v} for k, v in total_serveware.items()]).sort_values("Serveware")
            # Add utensil set reporting
            extra = []
            if ordered_utensils > 0:
                extra.append({"Serveware": "Utensil Sets (ordered)", "Total": int(ordered_utensils)})
            if recommended_utensils > 0:
                extra.append({"Serveware": "Utensil Sets (recommended)", "Total": int(recommended_utensils)})
            if extra:
                serve_df = pd.concat([serve_df, pd.DataFrame(extra)], ignore_index=True)
            st.dataframe(serve_df, use_container_width=True, hide_index=True)

        st.divider()

        # Export
        export_rows = []
        def add_section(section_name, d):
            for k, v in d.items():
                export_rows.append({"Section": section_name, "Name": k, "Total": v})

        add_section("Food", total_food)
        add_section("Packaging", total_packaging)
        add_section("Condiments", total_condiments)
        add_section("Serveware", total_serveware)

        if ordered_utensils > 0:
            export_rows.append({"Section": "Serveware", "Name": "Utensil Sets (ordered)", "Total": int(ordered_utensils)})
        if recommended_utensils > 0:
            export_rows.append({"Section": "Serveware", "Name": "Utensil Sets (recommended)", "Total": int(recommended_utensils)})

        export_df = pd.DataFrame(export_rows)
        csv = export_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download Prep Sheet (CSV)", data=csv, file_name="catering_prep_sheet.csv", mime="text/csv")

with st.expander("Admin: Edit catalog (optional)"):
    st.write("If you ever want to add/remove items or adjust quantities, edit the CATALOG list in app.py.")
    st.caption("We kept it simple for managers; customization can stay with you.")
