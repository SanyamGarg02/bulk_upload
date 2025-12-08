import streamlit as st
import pandas as pd
import re
import io

# ========== HELPERS ==========

def clean_metal(value):
    if pd.isna(value):
        return ""
    value = str(value)
    if "white" in value.lower() and "yellow" in value.lower():
        return "Two tone gold"
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
    "Bracelets": "Bracelet",
    "bangle": "Bracelet",
    "necklace (chain)": "Necklace",
    "necklace": "Necklace",
    "neck-pndt": "Necklace",
    "ring": "Ring",
    "earring pair": "Earring",
    "Earrings": "Earring",
    "pendant": "Pendant",
    "brooch": "Brooch",
    "accessories": "Accessories",
}
DEFAULT_CATEGORY = "Others"

def detect_category(detail):
    if pd.isna(detail):
        return DEFAULT_CATEGORY
    d = str(detail).strip().lower()
    if "earring" in d:
        return "Earring"
    for k, v in CATEGORY_MAP.items():
        if k in d:
            return v
    return DEFAULT_CATEGORY

def parse_size(size_val, category):
    """Returns (size_length, size_width, size_unit, standard_size)"""
    if pd.isna(size_val):
        return "", "", "", ""
    size_str = str(size_val).strip().lower().replace(" ", "")
    if category == "Ring":
        if re.match(r"^\d+(\.\d+)?$", size_str):
            return "", "", "", size_str
        return "", "", "", size_str
    match_inch = re.match(r"^(\d+\.?\d*)\"?$", size_str)
    if match_inch:
        length = match_inch.group(1)
        return length, "", "cm", ""
    match_double = re.match(r"^(\d+\.?\d*)[*xX](\d+\.?\d*)(cm|mm)?$", size_str)
    if match_double:
        l = match_double.group(1)
        w = match_double.group(2)
        u = match_double.group(3) if match_double.group(3) else ""
        return l, w, u, ""
    match_single = re.match(r"^(\d+\.?\d*)(cm|mm)?$", size_str)
    if match_single:
        l = match_single.group(1)
        u = match_single.group(2) if match_single.group(2) else ""
        return l, "", u, ""
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

# ========== EXPECTED VENDOR FIELDS (what your logic currently reads) ==========
# These are the 'expected_field' names that the mapping CSV should provide mappings for.
EXPECTED_VENDOR_FIELDS = [
    "TAG NO","gem gem sale price","METAL","METAL CARAT","DETAILS","STONE TYPE",
    "SIZE","METAL WT.","STOCK TYPE2","SD PCS","COLLECTION","CLR","CT","SD WT.",
    "LAB","CERT","SHAPE","CRT","C","P","S","FLO","TREATMENT","ORIGIN"
]

def load_mapping_df(mapping_file):
    """
    mapping_file: uploaded file containing two columns:
      expected_field,vendor_column
    If missing or empty the function returns identity mapping.
    """
    if mapping_file is None:
        # identity mapping
        return {f: f for f in EXPECTED_VENDOR_FIELDS}
    try:
        mdf = pd.read_csv(mapping_file, dtype=str).fillna("")
    except Exception:
        # try excel
        mdf = pd.read_excel(mapping_file, dtype=str).fillna("")
    # Normalize columns: first col expected_field, second col vendor_column
    cols = list(mdf.columns)
    if len(cols) < 2:
        st.error("Mapping file must have at least two columns: expected_field and vendor_column")
        return {f: f for f in EXPECTED_VENDOR_FIELDS}
    m = {}
    for _, r in mdf.iterrows():
        exp = str(r[cols[0]]).strip()
        vend = str(r[cols[1]]).strip()
        if exp:
            m[exp] = vend if vend else exp
    # ensure fallback for all expected fields
    for f in EXPECTED_VENDOR_FIELDS:
        if f not in m:
            m[f] = f
    return m

# ========== MAIN PROCESS FUNCTION ==========
def process_vendor_file(uploaded_file, mapping_dict):
    """
    uploaded_file: vendor CSV
    mapping_dict: dict mapping expected_field -> vendor column name in this file
    """
    df = pd.read_csv(uploaded_file, dtype=str).fillna("")
    out_df = pd.DataFrame()
    missing_diamond_rows = []

    for idx, row in df.iterrows():
        # build mapped_row so existing logic can use expected keys
        mapped_row = {}
        for expected in EXPECTED_VENDOR_FIELDS:
            vendor_col = mapping_dict.get(expected, expected)
            mapped_row[expected] = row.get(vendor_col, "")
        # now use mapped_row instead of original row
        uid = idx + 1
        sku = mapped_row.get("TAG NO", "").strip()
        price = mapped_row.get("gem gem sale price", "").strip()
        currency = "USD"
        metal = clean_metal(mapped_row.get("METAL", ""))
        gold_purity = format_gold_purity(mapped_row.get("METAL CARAT", ""))

        category = detect_category(mapped_row.get("DETAILS", ""))
        stone_type_raw = mapped_row.get("STONE TYPE", "")
        stone_type = normalize_stone_type(stone_type_raw)

        size_length, size_width, size_unit, standard_size = parse_size(
            mapped_row.get("SIZE", ""),
            category
        )

        total_weight = mapped_row.get("METAL WT.", "").strip()

        stock_type2 = mapped_row.get("STOCK TYPE2", "").strip().lower()
        if stock_type2 == "second hand":
            condition = "Excellent"
        elif stock_type2 == "new":
            condition = "Brand New"
        else:
            condition = "Excellent"

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
            "diamond_quantity": mapped_row.get("SD PCS", "").strip(),
        }

        # collection mapping
        collection_value = mapped_row.get("COLLECTION", "").strip()
        if collection_value:
            if category == "Ring":
                record["ring-style"] = collection_value
            elif category == "Bracelet":
                record["bracelet-style"] = collection_value
            elif category == "Necklace":
                record["necklace-style"] = collection_value
            elif category == "Pendant":
                record["pendant-style"] = collection_value
            elif category == "Earring":
                record["earring-style"] = collection_value
            elif category == "Brooch":
                record["brooch-style"] = collection_value
            elif category == "Accessories":
                record["accessories-style"] = collection_value

        # diamond logic
        if "diamond" in str(stone_type_raw).lower():
            clr = mapped_row.get("CLR", "").strip()
            ct_raw = mapped_row.get("CT", "").strip()
            sd_wt_raw = mapped_row.get("SD WT.", "").strip()

            def is_positive_number(s):
                try:
                    return float(s) > 0
                except:
                    return False

            if is_positive_number(ct_raw):
                diamond_weight = ct_raw
            elif is_positive_number(sd_wt_raw):
                diamond_weight = sd_wt_raw
            else:
                diamond_weight = ""

            if not diamond_weight:
                missing_diamond_rows.append(mapped_row.copy())

            if "fancy" in str(stone_type_raw).lower():
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
                "diamond_certification": mapped_row.get("LAB", "").strip(),
                "diamond_certification-number": mapped_row.get("CERT", "").strip(),
                "diamond_diamond-shape": mapped_row.get("SHAPE", "").strip(),
                "diamond_diamond-clarity": mapped_row.get("CRT", "").strip(),
                "diamond_diamond-cut": mapped_row.get("C", "").strip(),
                "diamond_diamond-polish": mapped_row.get("P", "").strip(),
                "diamond_diamond-symmetry": mapped_row.get("S", "").strip(),
                "diamond_diamond-fluoroscence": mapped_row.get("FLO", "").strip(),
                "diamond_center-stone": "Center stone",
                "gemstone_stone-type": "Diamond",
            })

        else:
            record["diamond_carat-weight"] = mapped_row.get("SD WT.", "").strip()
            record["diamond_center-stone"] = "Side stone"
            record.update({
                "gemstone_certification": mapped_row.get("LAB", "").strip(),
                "gemstone_certification-number": mapped_row.get("CERT", "").strip(),
                "gemstone_carat-weight": mapped_row.get("CT", "").strip(),
                "gemstone_gem-stone-shape": mapped_row.get("SHAPE", "").strip(),
                "gemstone_gem-stone-color": mapped_row.get("CLR", "").strip(),
                "gemstone_stone-type": normalize_stone_type(mapped_row.get("STONE TYPE", "")),
                "gemstone_center-stone": "Center stone",
            })

            if normalize_stone_type(mapped_row.get("STONE TYPE", "")) == "Pearl":
                record["gemstone_pearl-shape"] = mapped_row.get("SHAPE", "").strip()
                record["gemstone_pearl-color"] = mapped_row.get("CLR", "").strip()

            treatment_val = mapped_row.get("TREATMENT", "").strip()
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
                stone_type = normalize_stone_type(mapped_row.get("STONE TYPE", ""))
                if stone_type in gem_map:
                    record[gem_map[stone_type]] = treatment_val

            origin_val = mapped_row.get("ORIGIN", "").strip()
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
                stone_type = normalize_stone_type(mapped_row.get("STONE TYPE", ""))
                if stone_type in origin_map:
                    record[origin_map[stone_type]] = origin_val

        out_df = pd.concat([out_df, pd.DataFrame([record])], ignore_index=True)

    # required columns order (unchanged)
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

    for col in REQUIRED_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = ""

    out_df = out_df[REQUIRED_COLUMNS]

    return out_df, missing_diamond_rows

# ========== STREAMLIT UI ==========

st.set_page_config(page_title="GemGem Bulk Upload Mapper", layout="centered")
st.title("💎 GemGem Vendor → Bulk Upload Mapper")

st.markdown("**Step 1.** Upload vendor CSV. **Step 2.** (Optional) Upload mapping CSV if vendor columns differ.")
st.write("Mapping CSV format: two columns. Column1 = expected_field (one of the left values below). Column2 = vendor column name in this CSV.")
st.code(", ".join(EXPECTED_VENDOR_FIELDS))

uploaded_file = st.file_uploader("Upload Vendor CSV file", type=["csv", "xlsx"])
mapping_file = st.file_uploader("Upload Mapping CSV/Excel (optional)", type=["csv", "xlsx"])

if uploaded_file:
    if st.button("✨ MAGIC – Process File"):
        with st.spinner("Processing..."):
            mapping_dict = load_mapping_df(mapping_file)
            output_df, missing = process_vendor_file(uploaded_file, mapping_dict)

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
