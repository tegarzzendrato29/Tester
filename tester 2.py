import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Inventaris Pabrik Roti", layout="wide")

# --- KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def init_connection():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    sa_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in sa_info and isinstance(sa_info["private_key"], str):
        sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")

    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    return gspread.authorize(creds)

client = init_connection()
SHEET_NAME = "Stok Bahan Baku Pembuatan Roti"

def parse_number(val):
    if val is None:
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = s.replace(".", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 3 and all(p.isdigit() for p in parts):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

@st.cache_data(ttl=10)
def load_data(cache_buster=0):
    sh = client.open(SHEET_NAME)
    sheet_stok = sh.worksheet("Stok")

    total_original = parse_number(sheet_stok.acell("E5").value)
    total_coklat = parse_number(sheet_stok.acell("F5").value)

    raw_values = sheet_stok.get("A7:I12")
    headers = raw_values[0]
    rows = raw_values[1:]

    df = pd.DataFrame(rows, columns=headers)

    num_cols = [
        "Stok Awal",
        "Stok Min",
        "Kebutuhan Per 1 Resep Original",
        "Kebutuhan Per 1 Resep Coklat",
        "Terpakai Resep Original",
        "Terpakai Resep Coklat",
        "Stok Sekarang",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_number)

    return df, total_original, total_coklat, datetime.now().strftime("%H:%M:%S")

def tambah_produksi(varian, jumlah):
    sh = client.open(SHEET_NAME)
    sheet_produksi = sh.worksheet("Produksi")
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_produksi.append_row([tanggal, varian, jumlah])
    st.cache_data.clear()

# --- UI DASHBOARD ---
st.title("🍞 Dashboard Inventaris & Produksi Pabrik Roti")

# Kontrol Auto-Update di Sidebar
st.sidebar.header("⚙️ Pengaturan Sinkronisasi")
auto_update = st.sidebar.toggle("Auto-Update dari Google Sheets", value=True)
interval_detik = st.sidebar.slider("Interval Update (detik)", min_value=5, max_value=60, value=10, step=5)

if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

try:
    df_stok, tot_ori, tot_cok, last_sync = load_data(st.session_state.refresh_counter)
    st.caption(f"Sinkronisasi real-time dengan Google Sheets • Terakhir diperbarui: **{last_sync}**")

    # --- SIDEBAR: FORM INPUT RESEP PRODUKSI ---
    st.sidebar.divider()
    st.sidebar.header("📝 Input Produksi Baru")
    with st.sidebar.form("form_produksi", clear_on_submit=True):
        varian_input = st.selectbox("Pilih Varian Roti", ["Original", "Coklat"])
        jumlah_input = st.number_input("Jumlah Resep yang Dibuat", min_value=1, step=1, value=1)
        submit_btn = st.form_submit_button("Catat Produksi")

        if submit_btn:
            kolom_kebutuhan = f"Kebutuhan Per 1 Resep {varian_input}"
            bahan_kurang = []

            for _, row in df_stok.iterrows():
                butuh = row[kolom_kebutuhan] * jumlah_input
                if row["Stok Sekarang"] < butuh:
                    bahan_kurang.append(
                        f"{row['Nama Barang']} (Butuh: {butuh:,.0f}, Sisa: {row['Stok Sekarang']:,.0f})"
                    )

            if bahan_kurang:
                st.sidebar.error(
                    "Stok tidak mencukupi untuk produksi ini:\n- " + "\n- ".join(bahan_kurang)
                )
            else:
                tambah_produksi(varian_input, jumlah_input)
                st.session_state.refresh_counter += 1
                st.sidebar.success(f"Berhasil mencatat {jumlah_input} resep {varian_input}!")
                st.rerun()

    # --- METRIK RINGKASAN ---
    col1, col2, col3 = st.columns(3)
    jml_menipis = len(df_stok[df_stok["Status"] == "Menipis"])

    col1.metric("Total Resep Original Diproduksi", f"{tot_ori:,.0f} Resep")
    col2.metric("Total Resep Coklat Diproduksi", f"{tot_cok:,.0f} Resep")
    col3.metric("Bahan Baku Status Menipis", f"{jml_menipis} Item", delta_color="inverse")

    st.divider()

    # --- TABEL STOK REAL-TIME ---
    st.subheader("📦 Status Stok Bahan Baku Saat Ini")

    def highlight_status(row):
        if row["Status"] == "Menipis":
            return ["background-color: #fff59d; color: black"] * len(row)
        return ["background-color: #a5d6a7; color: black"] * len(row)

    st.dataframe(
        df_stok.style.apply(highlight_status, axis=1).format({
            "Stok Awal": "{:,.0f}",
            "Stok Min": "{:,.0f}",
            "Kebutuhan Per 1 Resep Original": "{:,.0f}",
            "Kebutuhan Per 1 Resep Coklat": "{:,.0f}",
            "Terpakai Resep Original": "{:,.0f}",
            "Terpakai Resep Coklat": "{:,.0f}",
            "Stok Sekarang": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    if st.button("🔄 Sinkronkan Ulang Sekarang"):
        st.cache_data.clear()
        st.session_state.refresh_counter += 1
        st.rerun()

    # --- LOOP AUTO-UPDATE TANPA REFRESH TAB BROWSER ---
    if auto_update:
        time.sleep(interval_detik)
        st.cache_data.clear()
        st.session_state.refresh_counter += 1
        st.rerun()

except Exception as e:
    st.error(
        f"Gagal terhubung ke Google Sheets. Pastikan Secrets sudah benar dan sheet dibagikan sebagai Editor ke email Service Account. Detail: {e}"
    )