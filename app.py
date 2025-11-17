import streamlit as st
import pandas as pd
import re
import io

# ========== HELPER FUNCTIONS ==========

def clean_metal(value):
    """Normalize metal description like '18K White & Yellow Gold' → 'Two tone gold'"""
    if pd.isna(value):
        return ""
    value = str(value)
    # Detect Two tone
    if "white" in value.lower() and "yellow" in value.lower():
        return "Two tone gold"
    # Remove karat mentions
    value = re.sub(r"\b(18K|14K|22K)\b", "", value, flags=re.IGNORECASE)
    value = value.replace("&", "and").strip()
    value = re.sub(r"\s+", " ", value)
    return value.title()


def format_gold_purity(value):
    if pd.isna(value) or value == "":
        return ""
    value = str(value).strip()
    if not value.lower().endswith("k"):
        return f"{value}K"
    return value.upper()


CATEGORY_MAP = {
    "bracelet": "Bracelet",
    "bangle": "Bracelet",
    "necklace (chain)": "Necklace",
    "necklace": "Necklace",
    "neck-pndt": "Necklace",
    "ring": "Ring",
    "earring pair": "Earring",
    "earring": "Earring",
    "pendant": "Pendant",
    "brooch": "Brooch",
    "accessories": "Accessories",
}
DEFAULT_CATEGORY = "Others"

def detect_category(detail):
    """Detect category more accurately"""
    if pd.isna(detail):
        return DEFAULT_CATEGORY
    d = str(detail).strip().lower()

    # ✅ Ensure earrings are not misclassified as rings
    if "earring" in d:
        return "Earring"
    for k, v in CATEGORY_MAP.items():
        if k in d:
            return v
    return DEFAULT_CATEGORY


def parse_size(size_val, category):
    """Parses size strings including inches and returns length, width, unit, and standard size for rings"""
    if pd.isna(size_val):
        return "", "", "", ""

    size_str = str(size_val).strip().lower().replace(" ", "")

    # ✅ Handle inches like 16" or 16.5"
    match_inch = re.match(r"^(\d+\.?\d*)\"?$", size_str)
    if match_inch:
        length = match_inch.group(1)
        return length, "", "cm", ""  # store inches as cm

    # ✅ Handle numeric ring size for category Ring
    if category == "Ring" and re.match(r"^\d+(\.\d+)?$", size_str):
        return "", "", "", size_str

    # ✅ Handle double dimension like 6CM*4, 5.5*4.5
    match_double = re.match(r"^(\d+\.?\d*)[*xX](\d+\.?\d*)(cm|mm)?$", size_str)
    if match_double:
        length = match_double.group(1)
        width = match_double.group(2)
        unit = match_double.group(3) if match_double.group(3) else ""
        return length, width, unit, ""

    # ✅ Handle single value like 18CM or 5.5MM
    match_single = re.match(r"^(\d+\.?\d*)(cm|mm)?$", size_str)
    if match_single:
        length = match_single.group(1)
        unit = match_single.group(2) if match_single.group(2) else ""
        return length, "", unit, ""

    return "", "", "", ""


def normalize_stone_type(value):
    if pd.isna(value):
        return ""
    val = str(value).lower().strip()
    if "diamond" in val:
        return "Diamond"
    if "ruby" in val:
        return "Ruby"
    if "emerald" in val:
        return "Emerald"
    if "padparadscha" in val:
        return "Padparadscha Sapphire"
    if "blue sapphire" in val:
        return "Blue Sapphire"
    if "sapphire" in val:
        return "Sapphire"
    if "chrysoberyl" in val:
        return "Chrysoberyl"
    if "tourmaline" in val:
        return "Tourmaline"
    if "aquamarine" in val:
        return "Aquamarine"
    if "pearl" in val:
        return "Pearl"
    if "jade" in val:
        return "Jade"
    return "Others"


# ========== MAIN PROCESS FUNCTION ==========

def process_vendor_file(uploaded_file):
    df = pd.read_csv(uploaded_file, dtype=str).fillna("")
    out_df = pd.DataFrame()
    missing_diamond_rows = []

    for idx, row in df.iterrows():
        uid = idx + 1
        sku = row.get("TAG NO", "").strip()
        price = row.get("gem gem sale price", "").strip()
        currency = "USD"
        metal = clean_metal(row.get("METAL", ""))
        gold_purity = format_gold_purity(row.get("METAL CARAT", ""))
        category = detect_category(row.get("DETAILS", ""))
        stone_type_raw = row.get("STONE TYPE", "")
        stone_type = normalize_stone_type(stone_type_raw)
        size_length, size_width, size_unit, standard_size = parse_size(row.get("SIZE", ""), category)
        total_weight = row.get("METAL WT.", "").strip()

        # ✅ Condition mapping
        stock_type2 = row.get("STOCK TYPE2", "").strip().lower()
        if stock_type2 == "second hand":
            condition = "Excellent"
        elif stock_type2 == "new":
            condition = "Brand New"
        else:
            condition = "Excellent"

        # ✅ Label assignment
        label = "Fast Shipping, Verified Partner"
        if condition == "Brand New":
            label += ", New"

        record = {
            "uid": uid,
            "sku": sku,
            "category": category,
            "currency": currency,
            "price": price,
            "metal": metal,
            "gold-purity": gold_purity,
            "size-length": size_length,
            "size-width": size_width,
            "size-unit": size_unit,
            "standard-size": standard_size,
            "total-weight": total_weight,
            "condition": condition,
            "label": label,
            "have_master_piece": "No",
            "diamond_quantity": row.get("SD PCS", "").strip(),
        }

        # ========== DIAMOND MAPPING ==========
        if "diamond" in stone_type_raw.lower():
            clr = row.get("CLR", "").strip()
            ct_raw = row.get("CT", "").strip()
            sd_wt_raw = row.get("SD WT.", "").strip()

            # numeric zero check
            def is_positive_number(s):
                try:
                    return float(s) > 0
                except Exception:
                    return False

            if is_positive_number(ct_raw):
                diamond_weight = ct_raw
            elif is_positive_number(sd_wt_raw):
                diamond_weight = sd_wt_raw
            else:
                diamond_weight = ""

            if not diamond_weight:
                missing_diamond_rows.append(row.to_dict())

            if "fancy" in stone_type_raw.lower():
                diamond_color = "Fancy"
                diamond_fancy_opt = clr
                diamond_white_opt = ""
            else:
                diamond_color = "White"
                diamond_white_opt = clr
                diamond_fancy_opt = ""

            record.update({
                "diamond_carat-weight": diamond_weight,
                "diamond_diamond-color": diamond_color,
                "diamond_diamond-color-white-options": diamond_white_opt,
                "diamond_diamond-color-fancy-options": diamond_fancy_opt,
                "diamond_certification": row.get("LAB", "").strip(),
                "diamond_certification-number": row.get("CERT", "").strip(),
                "diamond_diamond-shape": row.get("SHAPE", "").strip(),
                "diamond_diamond-clarity": row.get("CRT", "").strip(),
                "diamond_diamond-cut": row.get("C", "").strip(),
                "diamond_diamond-polish": row.get("P", "").strip(),
                "diamond_diamond-symmetry": row.get("S", "").strip(),
                "diamond_diamond-fluoroscence": row.get("FLO", "").strip(),
                "diamond_center-stone": "Center stone",
                "gemstone_stone-type": "Diamond",
            })

        # ========== GEMSTONE MAPPING ==========
        else:
            record["diamond_carat-weight"] = row.get("SD WT.", "").strip()
            record["diamond_center-stone"] = "Side stone"
            record.update({
                "gemstone_certification": row.get("LAB", "").strip(),
                "gemstone_certification-number": row.get("CERT", "").strip(),
                "gemstone_carat-weight": row.get("CT", "").strip(),
                "gemstone_gem-stone-shape": row.get("SHAPE", "").strip(),
                "gemstone_gem-stone-color": row.get("CLR", "").strip(),
                "gemstone_stone-type": stone_type,
                "gemstone_center-stone": "Center stone",
            })

            if stone_type == "Pearl":
                record["gemstone_pearl-shape"] = row.get("SHAPE", "").strip()
                record["gemstone_pearl-color"] = row.get("CLR", "").strip()

            record["gemstone_stone-shape"] = row.get("SHAPE", "").strip()
            record["gemstone_stone-color"] = row.get("CLR", "").strip()

            treatment_val = row.get("TREATMENT", "").strip()
            if treatment_val:
                if treatment_val.lower() == "heated":
                    treatment_val = "Indication of heating"
                gem_map = {
                    "Ruby": "gemstone_ruby-enhancement",
                    "Sapphire": "gemstone_sapphire-enhancement",
                    "Blue Sapphire": "gemstone_blue-sapphire-enhancement",
                    "Emerald": "gemstone_emerald-enhancement",
                    "Chrysoberyl": "gemstone_chrysoberyl-enhancement",
                    "Tourmaline": "gemstone_tourmaline-enhancement",
                    "Aquamarine": "gemstone_aquamarine-enhancement",
                    "Padparadscha Sapphire": "gemstone_padparadscha-sapphire-enhancement",
                }
                if stone_type in gem_map:
                    record[gem_map[stone_type]] = treatment_val

            origin_val = row.get("ORIGIN", "").strip()
            if origin_val:
                origin_map = {
                    "Ruby": "gemstone_ruby-origin",
                    "Sapphire": "gemstone_sapphire-origin",
                    "Blue Sapphire": "gemstone_blue-sapphire-origin",
                    "Emerald": "gemstone_emerald-origin",
                    "Chrysoberyl": "gemstone_chrysoberyl-origin",
                    "Tourmaline": "gemstone_tourmaline-origin",
                    "Aquamarine": "gemstone_aquamarine-origin",
                    "Padparadscha Sapphire": "gemstone_padparadscha-sapphire-origin",
                    "Jade": "gemstone_jade-origin",
                    "Pearl": "gemstone_pearl-origin",
                }
                if stone_type in origin_map:
                    record[origin_map[stone_type]] = origin_val

        out_df = pd.concat([out_df, pd.DataFrame([record])], ignore_index=True)
    REQUIRED_COLUMNS = [
        "uid","sku","name","category","description","images","certificate_images","ruler_images",
        "currency","price","discounted_price","to_be_listed","have_master_piece","year-of-purchase",
        "condition","packaging-info","ring-style","brand","engagement-rings-solitaire-hashes",
        "engagement-rings-options","engagement-rings-other-hashes","metal","gender","total-weight",
        "standard-size","resize-from","resize-to","resize-supported","gold-purity","earring-style",
        "earring-type","earring-solitaire-hashes","earring-studs-options","earring-other-hashes",
        "bracelet-style","bracelet-style-other-hashes","size-length","size-width","size-unit",
        "necklace-style","necklace-style-other-hashes","pendant-style","pendant-style-solitaire-hashes",
        "pendant-style-object-hashes","brooch-style","brooch-style-hashes","accessories-style","label",
        "diamond_quantity","diamond_certification","diamond_certification-number","diamond_carat-weight",
        "diamond_diamond-shape","diamond_diamond-color","diamond_diamond-color-white-options",
        "diamond_diamond-color-fancy-options","diamond_diamond-clarity","diamond_diamond-cut",
        "diamond_diamond-polish","diamond_diamond-symmetry","diamond_diamond-fluoroscence",
        "diamond_diamond-girdle","diamond_average-color","diamond_average-clarity",
        "diamond_approximate-carat-weight","diamond_center-stone","diamond_diamond-grade",
        "gemstone_quantity","gemstone_gold-purity","gemstone_certification","gemstone_certification-number",
        "gemstone_carat-weight","gemstone_diamond-color-fancy-options","gemstone_gem-stone-shape",
        "gemstone_gem-stone-color","gemstone_gem-stone-clarity","gemstone_gem-stone-cut",
        "gemstone_pearl-shape","gemstone_pearl-color","gemstone_pearl-clarity","gemstone_pearl-lustre",
        "gemstone_stone-type","gemstone_stone-type-pearl-options","gemstone_ruby-color",
        "gemstone_ruby-origin","gemstone_ruby-enhancement","gemstone_blue-sapphire-color",
        "gemstone_blue-sapphire-origin","gemstone_blue-sapphire-enhancement","gemstone_emerald-color",
        "gemstone_emerald-origin","gemstone_emerald-enhancement","gemstone_chrysoberyl-origin",
        "gemstone_chrysoberyl-enhancement","gemstone_tourmaline-origin","gemstone_tourmaline-enhancement",
        "gemstone_aquamarine-origin","gemstone_aquamarine-enhancement","gemstone_sapphire-origin",
        "gemstone_sapphire-enhancement","gemstone_padparadscha-sapphire-color",
        "gemstone_padparadscha-sapphire-origin","gemstone_padparadscha-sapphire-enhancement",
        "gemstone_approximate-carat-weight","gemstone_center-stone","gemstone_jade-color",
        "gemstone_jade-origin","gemstone_diamond-grade","gemstone_chrysoberyl-color",
        "gemstone_tourmaline-color","gemstone_aquamarine-color","gemstone_jade-clarity",
        "gemstone_pearl-origin"
    ]

    # Add any missing required columns as empty strings
    for col in REQUIRED_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = ""
    return out_df, missing_diamond_rows


# ========== STREAMLIT UI ==========

st.set_page_config(page_title="GemGem Bulk Upload Mapper", layout="centered")
st.title("💎 GemGem Vendor → Bulk Upload Mapper")

uploaded_file = st.file_uploader("Upload Vendor CSV file", type=["csv"])

if uploaded_file:
    if st.button("✨ MAGIC – Process File"):
        with st.spinner("Processing... Please wait..."):
            output_df, missing = process_vendor_file(uploaded_file)

        st.success("✅ Mapping complete!")
        csv_buf = io.StringIO()
        output_df.to_csv(csv_buf, index=False)
        st.download_button(
            label="📥 Download Output CSV",
            data=csv_buf.getvalue(),
            file_name="gemgem_upload.csv",
            mime="text/csv"
        )

        if missing:
            miss_buf = io.StringIO()
            pd.DataFrame(missing).to_csv(miss_buf, index=False)
            st.download_button(
                label="⚠️ Download Missing Diamond Weights CSV",
                data=miss_buf.getvalue(),
                file_name="missing_diamond_weight.csv",
                mime="text/csv"
            )
