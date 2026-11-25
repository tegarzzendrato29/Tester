import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Inventaris Pabrik Roti", layout="wide")

# --- KONEKSI GOOGLE SHEETS ---
@st.cache_resource
def init_connection():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    # Pastikan file credentials.json berada di folder yang sama
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    return client

client = init_connection()
SHEET_NAME = "Stok Bahan Baku Pembuatan Roti" # Sesuaikan dengan nama file Google Sheets Anda

def load_data():
    sheet_stok = client.open(SHEET_NAME).worksheet("Stok")
    
    # Ambil ringkasan total resep (Baris 5, Kolom E & F)
    total_original = sheet_stok.acell("E5").value
    total_coklat = sheet_stok.acell("F5").value
    
    # Ambil data tabel utama mulai baris ke-7
    raw_values = sheet_stok.get("A7:I12")
    headers = raw_values[0]
    rows = raw_values[1:]
    
    df = pd.DataFrame(rows, columns=headers)
    
    # Bersihkan format angka (hapus titik ribuan dan koma desimal ala format ID)
    num_cols = [
        "Stok Awal", "Stok Min", "Kebutuhan Per 1 Resep Original",
        "Kebutuhan Per 1 Resep Coklat", "Terpakai Resep Original",
        "Terpakai Resep Coklat", "Stok Sekarang"
    ]
    for col in num_cols:
        df[col] = (
            df[col]
            .replace("", "0")
            .str.replace(".", "", regex=False)
            .str.replace(",", "", regex=False)
            .astype(float)
        )
    return df, total_original, total_coklat

def tambah_produksi(varian, jumlah):
    sheet_produksi = client.open(SHEET_NAME).worksheet("Produksi")
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_produksi.append_row([tanggal, varian, jumlah])

# --- UI DASHBOARD ---
st.title("🍞 Dashboard Inventaris & Produksi Pabrik Roti")
st.markdown("Sinkronisasi real-time dengan Google Sheets.")

try:
    df_stok, tot_ori, tot_cok = load_data()

    # --- SIDEBAR: FORM INPUT RESEP PRODUKSI ---
    st.sidebar.header("📝 Input Produksi Baru")
    with st.sidebar.form("form_produksi", clear_on_submit=True):
        varian_input = st.selectbox("Pilih Varian Roti", ["Original", "Coklat"])
        jumlah_input = st.number_input("Jumlah Resep yang Dibuat", min_value=1, step=1, value=1)
        submit_btn = st.form_submit_button("Catat Produksi")
        
        if submit_btn:
            # Validasi apakah stok mencukupi sebelum eksekusi
            kolom_kebutuhan = f"Kebutuhan Per 1 Resep {varian_input}"
            bahan_kurang = []
            
            for idx, row in df_stok.iterrows():
                butuh = row[kolom_kebutuhan] * jumlah_input
                if row["Stok Sekarang"] < butuh:
                    bahan_kurang.append(f"{row['Nama Barang']} (Butuh: {butuh:,.0f}, Sisa: {row['Stok Sekarang']:,.0f})")
            
            if bahan_kurang:
                st.sidebar.error("Stok tidak mencukupi untuk produksi ini:\n- " + "\n- ".join(bahan_kurang))
            else:
                tambah_produksi(varian_input, jumlah_input)
                st.sidebar.success(f"Berhasil mencatat {jumlah_input} resep {varian_input}!")
                st.rerun()

    # --- METRIK RINGKASAN ---
    col1, col2, col3 = st.columns(3)
    jml_menipis = len(df_stok[df_stok["Status"] == "Menipis"])
    
    col1.metric("Total Resep Original Diproduksi", f"{tot_ori} Resep")
    col2.metric("Total Resep Coklat Diproduksi", f"{tot_cok} Resep")
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
        hide_index=True
    )

    # --- TOMBOL REFRESH MANUAL ---
    if st.button("🔄 Sinkronkan Ulang Data"):
        st.rerun()

except Exception as e:
    st.error(f"Gagal terhubung ke Google Sheets. Pastikan file credentials.json valid dan sheet sudah dibagikan ke email Service Account. Detail error: {e}")