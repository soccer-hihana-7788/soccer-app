import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import pandas as pd
import io

# --- 1. 認証設定（Secretsから新しい鍵を読み込む） ---
def get_gspread_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    if "gcp_service_account" in st.secrets:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        st.error("StreamlitのSecretsに 'gcp_service_account' が設定されていません。")
        st.stop()
    return gspread.authorize(creds), creds

# --- 2. データの読み込み関数 ---
def load_data(sheet_url):
    client, creds = get_gspread_client()
    sh = client.open_by_url(sheet_url)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    if "達成日時" in df.columns:
        df["達成日時"] = pd.to_datetime(df["達成日時"], errors='coerce').dt.strftime('%Y-%m-%d').replace('NaT', '')
    return df, worksheet, creds

# --- 3. メインUI ---
st.set_page_config(page_title="サッカー練習管理", layout="wide")

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1G539DPoba2GW68XlQfV-l2syF4Q5mOnLtULl700qAeU/edit#gid=0"

try:
    df, worksheet, creds = load_data(SPREADSHEET_URL)
    
    if "selected_no" not in st.session_state:
        st.session_state.selected_no = None

    # --- A. 詳細画面（動画アップロード機能を追加） ---
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
        
        # --- 動画アップロード機能 ---
        st.subheader("📹 トレーニング動画のアップロード")
        uploaded_file = st.file_uploader("動画ファイルを選択してください (mp4, movなど)", type=["mp4", "mov", "avi"])

        if uploaded_file is not None:
            if st.button("Googleドライブに保存してURLを更新"):
                try:
                    with st.spinner("アップロード中..."):
                        # Google Drive APIの設定
                        drive_service = build('drive', 'v3', credentials=creds)
                        
                        file_metadata = {'name': f"No{no}_{row_data['技名']}_{uploaded_file.name}"}
                        media = MediaIoBaseUpload(io.BytesIO(uploaded_file.read()), mimetype=uploaded_file.type, resumable=True)
                        
                        # ドライブにファイルを保存
                        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
                        file_id = file.get('id')
                        
                        # 誰でも閲覧できるように権限を設定（必要に応じて）
                        drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'viewer'}).execute()
                        
                        video_url = file.get('webViewLink')
                        
                        # スプレッドシートの「トレーニング動画」列（通常はE列やF列など列番号を確認してください）
                        # 1行目はヘッダーなので、row_idx + 2 行目に書き込みます
                        # 以下の 'トレーニング動画' がスプレッドシートの何列目にあるかを自動判定して更新
                        col_idx = df.columns.get_loc("トレーニング動画") + 1
                        worksheet.update_cell(row_idx + 2, col_idx, video_url)
                        
                        st.success(f"アップロード完了！URLを更新しました。")
                        st.balloons()
                        st.rerun()
                except Exception as e:
                    st.error(f"アップロードエラー: {e}")

        st.markdown("---")
        st.write(f"**現在のトレーニング動画URL:** {row_data['トレーニング動画']}")

    # --- B. 一覧画面 ---
    else:
        st.title("⚽ サッカートレーニング管理一覧")
        
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

        if not edited_df[edited_df["選択"] == True].empty:
            st.session_state.selected_no = edited_df[edited_df["選択"] == True].iloc[0]["No"]
            st.rerun()

        current_data = edited_df.drop(columns=["選択"])
        if not df.equals(current_data):
            final_df = current_data.fillna("")
            data_to_update = [final_df.columns.values.tolist()] + final_df.values.tolist()
            worksheet.update(data_to_update)
            st.success("スプレッドシートを更新しました！")
            st.rerun()

except Exception as e:
    st.error(f"接続エラーが発生しました。スプレッドシートの共有設定やSecretsを確認してください。")
    st.info(f"エラー詳細: {e}")
