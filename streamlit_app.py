import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Mapper", layout="wide")

# -------------------------------------------------
# SIMPLE AUTH (USERNAME / PASSWORD)
# -------------------------------------------------
VALID_USERNAME = "matt"
VALID_PASSWORD = "Interlynx123"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Mapper - Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_btn = st.button("Login")

    if login_btn:
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            st.session_state.authenticated = True
            st.experimental_rerun()
        else:
            st.error("Invalid username or password.")
    # Stop here if not authenticated
    st.stop()

# -------------------------------------------------
# FROM THIS POINT ON, USER IS AUTHENTICATED
# -------------------------------------------------

st.title("Mapper")

# Session state for mapper ONLY (File 1).
# We DO NOT store File 2 or the updated data in session_state.
if "master_map" not in st.session_state:
    st.session_state.master_map = pd.DataFrame(
        columns=["code_norm", "Buy Line", "Vendor Name"]
    )


# ----------------------------------------
# NORMALIZE BUY LINE & MANUFACTURER CODES
# ----------------------------------------
def normalize_code(value):
    """
    Convert any numeric-like value to a clean comparable code.
    Examples:
        996539.0  → "996539"
        "12,945"  → "12945"
        "046135"  → "46135"
        "782113"  → "782113"
    """
    if pd.isna(value):
        return None

    s = str(value).strip()
    s = s.replace(",", "")  # remove commas

    try:
        num = int(float(s))
        return str(num)
    except Exception:
        return s


# ----------------------------------------
# UPDATE MASTER MAPPING FROM FILE 1
# ----------------------------------------
def update_master_mapping(df_map: pd.DataFrame):
    df_map = df_map.copy()
    df_map.columns = [c.strip() for c in df_map.columns]

    if "Buy Line" not in df_map.columns or "Vendor Name" not in df_map.columns:
        st.error("File 1 must contain columns: 'Buy Line' and 'Vendor Name'.")
        return

    df_map = df_map.dropna(subset=["Buy Line"])
    df_map["code_norm"] = df_map["Buy Line"].apply(normalize_code)
    df_map = df_map[["code_norm", "Buy Line", "Vendor Name"]]

    combined = pd.concat([st.session_state.master_map, df_map], ignore_index=True)
    combined = combined.drop_duplicates(subset=["code_norm"], keep="last")

    st.session_state.master_map = combined


# ----------------------------------------
# APPLY MAPPING TO FILE 2 (IN MEMORY ONLY)
# ----------------------------------------
def apply_mapping(df2: pd.DataFrame) -> pd.DataFrame:
    df2 = df2.copy()

    if "manufacturer_Name" not in df2.columns:
        st.error("File 2 must contain the column 'manufacturer_Name'.")
        return df2

    if st.session_state.master_map.empty:
        st.error("Upload File 1 (mapper) first.")
        return df2

    # Normalize codes in File 2
    df2["code_norm"] = df2["manufacturer_Name"].apply(normalize_code)

    # Build dictionary from mapper: code_norm -> Vendor Name
    map_dict = pd.Series(
        st.session_state.master_map["Vendor Name"].values,
        index=st.session_state.master_map["code_norm"],
    ).to_dict()

    # Map vendor names
    df2["mapped_vendor"] = df2["code_norm"].map(map_dict)

    # Replace manufacturer_Name where mapping exists; otherwise keep original
    df2["manufacturer_Name"] = np.where(
        df2["mapped_vendor"].notna(),
        df2["mapped_vendor"],
        df2["manufacturer_Name"],
    )

    # Remove helper columns so only clean data is in the export
    df2 = df2.drop(columns=["mapped_vendor", "code_norm"], errors="ignore")

    return df2


# ==========================
# STEP 1 — LOAD MAPPER FILE
# ==========================
st.header("Step 1 – Upload Mapper File (File 1)")

file1 = st.file_uploader(
    "Upload mapper file (Buy Line / Vendor Name)",
    type=["xlsx", "xls", "csv"],
    key="file1",
)

if file1:
    df_map = pd.read_csv(file1) if file1.name.lower().endswith(".csv") else pd.read_excel(file1)
    update_master_mapping(df_map)
    st.success("Mapper loaded.")

# ==========================
# STEP 2 — LOAD FILE 2
# ==========================
st.header("Step 2 – Upload Data File (File 2)")

file2 = st.file_uploader(
    "Upload data file (contains manufacturer_Name column)",
    type=["xlsx", "xls", "csv"],
    key="file2",
)

if file2:
    # File 2 stays ONLY in memory in this function scope
    df2 = pd.read_csv(file2) if file2.name.lower().endswith(".csv") else pd.read_excel(file2)

    st.subheader("Preview of File 2")
    st.dataframe(df2.head(20), use_container_width=True)

    if st.button("Apply Mapping and Generate Updated File"):
        updated_df = apply_mapping(df2)

        st.success("Mapping applied.")
        st.subheader("Preview of Updated Data")
        st.dataframe(updated_df.head(20), use_container_width=True)

        # Export to Excel in-memory only
        out_buffer = io.BytesIO()
        with pd.ExcelWriter(out_buffer, engine="openpyxl") as writer:
            updated_df.to_excel(writer, index=False, sheet_name="UpdatedFile")
        out_buffer.seek(0)

        st.download_button(
            label="Download Updated File",
            data=out_buffer,
            file_name="updated_file2_vendor_names.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
