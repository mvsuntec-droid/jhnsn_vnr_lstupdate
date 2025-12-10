import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Buy Line → Vendor Name Mapper", layout="wide")

# ----------------------------------------
# Session state: persistent mapping
# ----------------------------------------
if "master_map" not in st.session_state:
    # master_map will hold: [code_norm, Buy Line, Vendor Name]
    st.session_state.master_map = pd.DataFrame(
        columns=["code_norm", "Buy Line", "Vendor Name"]
    )


# ----------------------------------------
# Helper: normalize a Buy Line / code
# ----------------------------------------
def normalize_code(x):
    """
    Normalize buy-line / manufacturer codes to a comparable string.

    - handles floats like 996539.0 -> "996539"
    - handles strings like "046135" -> "46135"
    - if not numeric, keeps the original string
    """
    if pd.isna(x):
        return None
    s = str(x).strip()
    try:
        # Convert numeric-looking values to int -> string
        val = int(float(s))
        return str(val)
    except Exception:
        # Not numeric: just return as stripped string
        return s


# ----------------------------------------
# Update master mapping from File 1
# ----------------------------------------
def update_master_mapping(df_map: pd.DataFrame):
    """
    Update the in-memory master mapping using a mapping dataframe
    that has columns: 'Buy Line', 'Vendor Name'.

    If the same Buy Line appears multiple times (in current or past uploads),
    the *last* occurrence wins.
    """
    # Normalize input columns
    df_map = df_map.copy()
    df_map.columns = [c.strip() for c in df_map.columns]

    if "Buy Line" not in df_map.columns or "Vendor Name" not in df_map.columns:
        st.error("Mapping file must contain columns: 'Buy Line' and 'Vendor Name'.")
        return

    # Drop completely empty rows in Buy Line
    df_map = df_map.dropna(subset=["Buy Line"])

    # Add normalized code
    df_map["code_norm"] = df_map["Buy Line"].apply(normalize_code)

    # Prepare clean mapping dataframe
    df_map = df_map[["code_norm", "Buy Line", "Vendor Name"]]

    # Combine with existing master
    combined = pd.concat([st.session_state.master_map, df_map], ignore_index=True)

    # Keep only the last record per code_norm (latest upload wins)
    combined = combined.drop_duplicates(subset=["code_norm"], keep="last")

    st.session_state.master_map = combined


# ----------------------------------------
# Apply mapping to File 2
# ----------------------------------------
def apply_mapping_to_file2(df2: pd.DataFrame) -> pd.DataFrame:
    """
    Replace manufacturer_Name in File 2 with Vendor Name using the master mapping.

    - manufacturer_Name (codes) are normalized to code_norm.
    - Master mapping uses code_norm -> Vendor Name.
    - If match found, manufacturer_Name becomes Vendor Name.
    - If no match, manufacturer_Name stays as original code.
    """
    if "manufacturer_Name" not in df2.columns:
        st.error("File 2 must contain column 'manufacturer_Name'.")
        return df2

    df2 = df2.copy()

    # Normalize manufacturer_Name into code_norm
    df2["code_norm"] = df2["manufacturer_Name"].apply(normalize_code)

    master = st.session_state.master_map

    if master.empty:
        st.warning("Master mapping is empty – upload File 1 first.")
        return df2

    # Merge
    merged = df2.merge(
        master[["code_norm", "Vendor Name"]],
        how="left",
        on="code_norm",
    )

    # Replace manufacturer_Name:
    # - where we have a Vendor Name, use that
    # - otherwise keep original manufacturer_Name
    merged["manufacturer_Name"] = np.where(
        merged["Vendor Name"].notna(),
        merged["Vendor Name"],
        merged["manufacturer_Name"],
    )

    # Drop helper columns
    merged = merged.drop(columns=["Vendor Name", "code_norm"], errors="ignore")

    return merged


# ----------------------------------------
# STREAMLIT UI
# ----------------------------------------

st.title("🔗 Buy Line → Vendor Name Mapper (Excel/CSV)")

st.markdown(
    """
This tool uses **File 1 (REPORT_ODBC)** as a master mapping of **Buy Line → Vendor Name**  
and updates the **manufacturer_Name** column in **File 2** (your data file).

- File 1 columns: **Buy Line**, **Vendor Name**  
- File 2 must contain: **manufacturer_Name** (holding the Buy Line codes)  
- If the same Buy Line appears multiple times in File 1, the **last entry wins**.
"""
)

# ======================
# STEP 1 – Upload File 1
# ======================
st.header("📘 Step 1 – Upload / Refresh Buy Line Mapping (File 1)")

file1 = st.file_uploader(
    "Upload REPORT_ODBC mapping file (Excel or CSV)",
    type=["xlsx", "xls", "csv"],
    key="file1",
)

if file1 is not None:
    if file1.name.lower().endswith(".csv"):
        df_map = pd.read_csv(file1)
    else:
        df_map = pd.read_excel(file1)

    update_master_mapping(df_map)
    st.success("Mapping file uploaded and master mapping updated.")

st.subheader("Current Master Mapping (latest rows win per code)")
if st.session_state.master_map.empty:
    st.info("No mapping loaded yet.")
else:
    st.dataframe(st.session_state.master_map.head(50), use_container_width=True)


# ======================
# STEP 2 – Upload File 2
# ======================
st.header("📗 Step 2 – Upload Data File (File 2) to Update manufacturer_Name")

file2 = st.file_uploader(
    "Upload File 2 (Excel or CSV – the data file with manufacturer_Name column)",
    type=["xlsx", "xls", "csv"],
    key="file2",
)

if file2 is not None:
    if file2.name.lower().endswith(".csv"):
        df2 = pd.read_csv(file2)
    else:
        df2 = pd.read_excel(file2)

    st.write("### Preview of Uploaded File 2")
    st.dataframe(df2.head(20), use_container_width=True)

    if st.button("🔄 Apply Mapping to manufacturer_Name"):
        updated_df = apply_mapping_to_file2(df2)

        st.success("Mapping applied! manufacturer_Name now shows Vendor Name where matched.")

        st.write("### Updated File 2 Preview")
        st.dataframe(updated_df.head(20), use_container_width=True)

        # Prepare Excel download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            updated_df.to_excel(writer, index=False, sheet_name="UpdatedData")
        buffer.seek(0)

        st.download_button(
            label="⬇ Download Updated File 2 (Excel)",
            data=buffer,
            file_name="file2_manufacturer_mapped.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ======================
# STEP 3 – Download Master Mapping
# ======================
st.header("📄 Step 3 – Download Current Master Mapping")

if st.session_state.master_map.empty:
    st.info("No mapping to download yet.")
else:
    map_buffer = io.BytesIO()
    with pd.ExcelWriter(map_buffer, engine="openpyxl") as writer:
        st.session_state.master_map.to_excel(
            writer, index=False, sheet_name="MasterMapping"
        )
    map_buffer.seek(0)

    st.download_button(
        label="⬇ Download Master Mapping (Excel)",
        data=map_buffer,
        file_name="master_buyline_vendor_mapping.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
