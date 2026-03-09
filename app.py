import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import pandas as pd
import io
import re
import base64

# --- 1. 認証設定（Secrets対応に書き換え） ---
def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    # Streamlit Secretsから認証情報を取得
    if "gcp_service_account" in st.secrets:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        st.error("Secretsに'gcp_service_account'が設定されていません。")
        st.stop()
    return gspread.authorize(creds)

# --- 2. データの読み書き ---
def load_data(sheet_url):
    client = get_gspread_client()
    sh = client.open_by_url(sheet_url)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if "達成日時" in df.columns:
        df["達成日時"] = pd.to_datetime(df["達成日時"], errors='coerce').dt.strftime('%Y-%m-%d').replace('NaT', '')
    return df, worksheet

# --- 3. メインUI ---
st.set_page_config(page_title="サッカー練習管理", layout="wide")

# ログイン機能
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("ログイン")
    u = st.text_input("ID")
    p = st.text_input("PASS", type="password")
    if st.button("ログイン"):
        if u == st.secrets["LOGIN_ID"] and p == st.secrets["LOGIN_PASS"]:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("IDまたはパスワードが違います")
    st.stop()

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1G539DPoba2GW68XlQfV-l2syF4Q5mOnLtULl700qAeU/edit#gid=0"

try:
    df, worksheet = load_data(SPREADSHEET_URL)
    
    if "selected_no" not in st.session_state:
        st.session_state.selected_no = None

    # --- 詳細画面（動画再生画面） ---
    if st.session_state.selected_no is not None:
        no = st.session_state.selected_no
        row_idx = df[df["No"] == no].index[0]
        row_data = df.iloc[row_idx]
        
        st.title(f"🎬 No.{no}: {row_data['技名']} の動画管理")
        if st.button("⬅ 一覧に戻る"):
            st.session_state.selected_no = None
            st.rerun()

        st.markdown("---")
        st.info("※現在、動画再生機能は調整中です。")
        st.write(f"技名: {row_data['技名']}")
        st.write(f"参考動画URL: {row_data['参考動画']}")
        st.write(f"トレーニング動画URL: {row_data['トレーニング動画']}")

    # --- 一覧画面 ---
    else:
        st.title("⚽ サッカートレーニング管理")
        
        display_df = df.copy()
        display_df.insert(0, "選択", False)
        
        edited_df = st.data_editor(
            display_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "選択": st.column_config.CheckboxColumn("選択", default=False),
                "No": st.column_config.NumberColumn("No", disabled=True),
            }
        )

        # チェックボックスによる遷移
        if not edited_df[edited_df["選択"] == True].empty:
            st.session_state.selected_no = edited_df[edited_df["選択"] == True].iloc[0]["No"]
            st.rerun()

        # データ更新
        current_data = edited_df.drop(columns=["選択"])
        if not df.equals(current_data):
            final_df = current_data.fillna("")
            data_to_update = [final_df.columns.values.tolist()] + final_df.values.tolist()
            worksheet.update(data_to_update)
            st.rerun()

except Exception as e:
    st.error(f"エラー: {e}")
