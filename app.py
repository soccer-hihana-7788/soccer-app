import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import pandas as pd
import time
import io
import os
import pickle
import re
import base64

# --- 1. 認証設定 ---
def get_personal_drive_service():
    scopes = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', scopes)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('drive', 'v3', credentials=creds)

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file('service_account.json', scopes=scopes)
    return gspread.authorize(creds)

# --- 2. 動画データ取得（抜本的改善：常にバイナリ経由で取得） ---
def get_video_bytes(url):
    if not url: return None
    match = re.search(r'(?:id=|\/d\/)([a-zA-Z0-9_-]{25,})', url)
    if not match: return None
    file_id = match.group(1)
    service = get_personal_drive_service()
    try:
        # Google側のエンコード待ちを回避するため、元ファイルを直接ストリーム取得
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        video_bytes = fh.getvalue()
        b64_video = base64.b64encode(video_bytes).decode()
        return f"data:video/mp4;base64,{b64_video}"
    except Exception:
        return None

def upload_to_drive(file, folder_id, file_name):
    service = get_personal_drive_service()
    clean_folder_id = folder_id.split('/')[-1].split('?')[0]
    file_metadata = {'name': file_name, 'parents': [clean_folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file.read()), mimetype=file.type, resumable=True)
    try:
        db_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = db_file.get('id')
        service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        return f"https://drive.google.com/file/d/{file_id}/view"
    except Exception as e:
        st.error(f"アップロード失敗: {e}")
        raise e

# --- 3. データの読み書き ---
def load_data(sheet_url):
    client = get_gspread_client()
    sh = client.open_by_url(sheet_url)
    worksheet = sh.get_worksheet(0)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if "達成日時" in df.columns:
        df["達成日時"] = pd.to_datetime(df["達成日時"], errors='coerce').dt.strftime('%Y-%m-%d').replace('NaT', '')
    return df, worksheet

# --- 4. メインUI ---
st.set_page_config(page_title="サッカー練習管理", layout="wide")

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1G539DPoba2GW68XlQfV-l2syF4Q5mOnLtULl700qAeU/edit#gid=0"
DRIVE_FOLDER_ID = "1N5mbb9nEXlhgfCLRoIm5GRF5msYRJ6T2"

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
        for v_col in ["参考動画", "トレーニング動画"]:
            st.subheader(f"📂 {v_col}")
            c1, c2 = st.columns([1.5, 1])
            v_url = row_data[v_col]
            
            with c1:
                if v_url:
                    # ここでバイナリ取得を行うことで「Googleの処理中」画面を回避
                    with st.spinner(f"{v_col}を読み込み中..."):
                        video_data = get_video_bytes(v_url)
                        if video_data:
                            st.video(video_data)
                        else:
                            st.error("動画の取得に失敗しました。権限またはURLを確認してください。")
                else:
                    st.info(f"{v_col}は未登録です")

            with c2:
                if v_url:
                    st.write("✅ 保存済みURL:")
                    col_url, col_del = st.columns([4, 1])
                    col_url.code(v_url, language=None)
                    if col_del.button("🗑️", key=f"del_{v_col}_{no}"):
                        col_letter = "C" if v_col == "参考動画" else "D"
                        worksheet.update_acell(f"{col_letter}{row_idx + 2}", "")
                        st.rerun()
                
                st.write("---")
                up_file = st.file_uploader(f"新規{v_col}を選択", type=["mp4", "mov", "avi"], key=f"up_{v_col}_{no}")
                if up_file:
                    if st.button(f"{v_col}を保存", key=f"btn_{v_col}_{no}"):
                        with st.spinner("保存中..."):
                            new_url = upload_to_drive(up_file, DRIVE_FOLDER_ID, f"No{no}_{v_col}_{up_file.name}")
                            col_letter = "C" if v_col == "参考動画" else "D"
                            worksheet.update_acell(f"{col_letter}{row_idx + 2}", new_url)
                            st.rerun()
            st.markdown("---")

    # --- 一覧画面 ---
    else:
        st.title("⚽ サッカートレーニング管理")
        
        display_df = df.copy()
        display_df.insert(0, "選択", False)
        
        # リンクをクリックしても値が変わらないよう、判定用のダミーURLを仕込む
        edited_df = st.data_editor(
            display_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "選択": st.column_config.CheckboxColumn("選択", default=False),
                "No": st.column_config.NumberColumn("No", disabled=True),
                "参考動画": st.column_config.LinkColumn("参考動画", display_text="動画を再生 🎬"),
                "トレーニング動画": st.column_config.LinkColumn("トレーニング動画", display_text="動画を再生 🎬")
            }
        )

        # A. チェックボックスによる遷移
        if not edited_df[edited_df["選択"] == True].empty:
            st.session_state.selected_no = edited_df[edited_df["選択"] == True].iloc[0]["No"]
            st.rerun()

        # B. リンククリックによる遷移（抜本的改善）
        # LinkColumnをクリックした際の変化を検知し、チェックボックスと同じ遷移ロジックを実行
        for col in ["参考動画", "トレーニング動画"]:
            if not edited_df[col].equals(display_df[col]):
                # 変化があった行を特定
                changed_idx = (edited_df[col] != display_df[col]).idxmax()
                st.session_state.selected_no = edited_df.loc[changed_idx, "No"]
                st.rerun()

        # C. データ更新
        current_data = edited_df.drop(columns=["選択"])
        if not df.equals(current_data):
            final_df = current_data.fillna("")
            data_to_update = [final_df.columns.values.tolist()] + final_df.values.tolist()
            worksheet.update(data_to_update)
            st.rerun()

except Exception as e:
    st.error(f"エラー: {e}")
