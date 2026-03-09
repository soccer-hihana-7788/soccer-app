import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd

# --- 1. 認証設定（Secretsから新しい鍵を読み込む） ---
def get_gspread_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    # Streamlit Secretsから [gcp_service_account] を取得
    if "gcp_service_account" in st.secrets:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        st.error("StreamlitのSecretsに 'gcp_service_account' が設定されていません。")
        st.stop()
    return gspread.authorize(creds)

# --- 2. データの読み込み関数 ---
def load_data(sheet_url):
    client = get_gspread_client()
    sh = client.open_by_url(sheet_url)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    # 日付の整形（列が存在する場合）
    if "達成日時" in df.columns:
        df["達成日時"] = pd.to_datetime(df["達成日時"], errors='coerce').dt.strftime('%Y-%m-%d').replace('NaT', '')
    return df, worksheet

# --- 3. メインUI ---
st.set_page_config(page_title="サッカー練習管理", layout="wide")

# スプレッドシートのURL
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1G539DPoba2GW68XlQfV-l2syF4Q5mOnLtULl700qAeU/edit#gid=0"

try:
    # 起動時に自動でデータを読み込み（ログイン画面はスキップ）
    df, worksheet = load_data(SPREADSHEET_URL)
    
    if "selected_no" not in st.session_state:
        st.session_state.selected_no = None

    # --- A. 詳細画面（動画再生など） ---
    if st.session_state.selected_no is not None:
        no = st.session_state.selected_no
        row_idx = df[df["No"] == no].index[0]
        row_data = df.iloc[row_idx]
        
        st.title(f"🎬 No.{no}: {row_data['技名']}")
        if st.button("⬅ 一覧に戻る"):
            st.session_state.selected_no = None
            st.rerun()

        st.markdown("---")
        st.write(f"**技名:** {row_data['技名']}")
        st.write(f"**参考動画:** {row_data['参考動画']}")
        st.write(f"**トレーニング動画:** {row_data['トレーニング動画']}")
        st.info("※動画表示機能は、URLの形式に合わせて別途調整可能です。")

    # --- B. 一覧画面 ---
    else:
        st.title("⚽ サッカートレーニング管理一覧")
        
        # 編集用データフレームの準備
        display_df = df.copy()
        display_df.insert(0, "選択", False)
        
        edited_df = st.data_editor(
            display_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "選択": st.column_config.CheckboxColumn("選択", default=False),
                "No": st.column_config.NumberColumn("No", disabled=True),
                "参考動画": st.column_config.LinkColumn("参考動画"),
                "トレーニング動画": st.column_config.LinkColumn("トレーニング動画")
            }
        )

        # チェックボックスが押されたら詳細へ
        if not edited_df[edited_df["選択"] == True].empty:
            st.session_state.selected_no = edited_df[edited_df["選択"] == True].iloc[0]["No"]
            st.rerun()

        # データが編集されたらスプレッドシートを更新
        current_data = edited_df.drop(columns=["選択"])
        if not df.equals(current_data):
            final_df = current_data.fillna("")
            # ヘッダーを含めて一括更新
            data_to_update = [final_df.columns.values.tolist()] + final_df.values.tolist()
            worksheet.update(data_to_update)
            st.success("スプレッドシートを更新しました！")
            st.rerun()

except Exception as e:
    st.error(f"接続エラーが発生しました。スプレッドシートの共有設定やSecretsを確認してください。")
    st.info(f"エラー詳細: {e}")
