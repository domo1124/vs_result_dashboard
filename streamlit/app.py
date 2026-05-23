import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from typing import Tuple

# ============================================================
# 設定
# ============================================================
SPREADSHEET_ID = st.secrets["spreadsheet"]["id"]

# シート名の定数
SHEET_BATTLES        = "battle_result"
SHEET_PARTY_LIST     = "myparty_analysis_list"
SHEET_SEASON         = "season"
SHEET_VS_PARTY       = "vs_party_pokemon"
SHEET_MY_PARTY       = "my_party_pokemon"

# ============================================================
# gspread クライアント（キャッシュで使い回す）
# ============================================================

@st.cache_resource
def _get_gspread_client() -> gspread.Client:
    """
    secrets.toml の [gcp_service_account] からサービスアカウント認証し、
    gspread クライアントを返す。アプリ起動時に1回だけ実行される。

    secrets.toml の記載例:
        [spreadsheet]
        id = "SPREADSHEET_ID"

        [gcp_service_account]
        type                        = "service_account"
        project_id                  = "your-project"
        private_key_id              = "..."
        private_key                 = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
        client_email                = "xxx@yyy.iam.gserviceaccount.com"
        client_id                   = "..."
        auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
        token_uri                   = "https://oauth2.googleapis.com/token"
        auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
        client_x509_cert_url        = "https://www.googleapis.com/robot/v1/metadata/x509/..."
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes,
    )
    return gspread.authorize(creds)


def _read_sheet(sheet_name: str, dtype=str) -> pd.DataFrame:
    """
    指定シートの全データを DataFrame で返す共通関数。
    非公開シートも gspread 経由で読み取れる。
    空セル（gspread が返す "" や "None"）は NaN に統一する。
    """
    gc = _get_gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if dtype is not None and not df.empty:
        df = df.astype(dtype)
    if not df.empty:
        # dtype=str にすると空セルが "" になるため NaN に置換
        df = df.replace({"": pd.NA, "None": pd.NA, "nan": pd.NA})
    return df


# ============================================================
# データ読み込み（キャッシュ付き）
# ============================================================

@st.cache_data(ttl=3600)
def load_battles() -> pd.DataFrame:
    """対戦記録シートを読み込む"""
    try:
        df = _read_sheet(SHEET_BATTLES)
        df = _clean_battles(df)
        return df
    except Exception as e:
        st.error(f"対戦記録の読み込みに失敗しました: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_parties() -> list:
    """パーティ一覧シートを読み込む"""
    try:
        df = _read_sheet(SHEET_PARTY_LIST)
        return _target_parties(df)
    except Exception as e:
        st.error(f"パーティ情報の読み込みに失敗しました: {e}")
        return []


@st.cache_data(ttl=3600)
def load_season() -> Tuple[list, str]:
    """シーズン情報シートを読み込む"""
    try:
        df = _read_sheet(SHEET_SEASON, dtype=None)
        return _target_season(df)
    except Exception as e:
        st.error(f"開催中のシーズン読み込みに失敗しました: {e}")
        return [], "error"


@st.cache_data(ttl=3600)
def load_vs_party_pokemon() -> pd.DataFrame:
    """相手パーティ一覧シートを読み込む"""
    try:
        df = _read_sheet(SHEET_VS_PARTY)
        return _clean_party_pokemon(df)
    except Exception as e:
        st.error(f"相手パーティ一覧の読み込みに失敗しました: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_my_party_pokemon() -> pd.DataFrame:
    """自分のパーティ一覧シートを読み込む"""
    try:
        df = _read_sheet(SHEET_MY_PARTY)
        return _clean_party_pokemon(df)
    except Exception as e:
        st.error(f"自分のパーティ一覧の読み込みに失敗しました: {e}")
        return pd.DataFrame()


# ============================================================
# クレンジング（列名・型をここで統一）
# ============================================================

def _clean_battles(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    if "vs_datetime" in df.columns:
        # 元の文字列をリレーション用キーとして保持してから datetime に変換
        df["vs_datetime_str"] = df["vs_datetime"].astype(str).str.strip()
        df["vs_datetime"] = pd.to_datetime(
            df["vs_datetime"], format="%Y%m%d_%H%M%S", errors="coerce"
        )
    if "result" in df.columns:
        df["result"] = df["result"].str.strip()
        df["is_win"] = df["result"] == "WIN"
    return df.dropna(how="all")


def _clean_party_pokemon(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    if "vs_datetime" in df.columns:
        # battles 側の vs_datetime_str と型を揃えるため str に統一
        df["vs_datetime_str"] = df["vs_datetime"].astype(str).str.strip()
    return df.dropna(how="all")


def _target_parties(df: pd.DataFrame) -> list:
    df.columns = df.columns.str.strip()
    return sorted(df["party_id"].dropna().unique())


def _target_season(df: pd.DataFrame) -> Tuple[list, str]:
    df.columns = df.columns.str.strip()
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["active"] = df["active"].astype(bool)
    target_season = (
        df[df["active"] == False]
        .sort_values(by="end_date", ascending=False)
        .head(2)
    )
    active_season = next(
        iter(
            df[df["active"] == True]
            .sort_values(by="end_date", ascending=False)["name"]
        ),
        None,
    )
    return target_season["name"].values.tolist(), active_season


# ============================================================
# キャッシュをクリアして再読み込みするボタン（任意で使う）
# ============================================================

def reload_button():
    if st.button("🔄 データを再読み込み"):
        st.cache_data.clear()
        st.rerun()


# ============================================================
# 動作確認用（このファイルを直接 streamlit run したとき）
# ============================================================

if __name__ == "__main__":
    reload_button()
    battles          = load_battles()
    my_party_ids     = load_parties()
    season_list, active_season = load_season()
    vs_party_pokemon = load_vs_party_pokemon()
    my_party_pokemon = load_my_party_pokemon()
    # ナビゲーション（サイドバーメニュー）の定義
    pages_dict = {
        "全体メニュー": [
            st.Page("views/global_page.py", title="📊 全体ダッシュボード", icon="📈")
        ]
    }

    # パーティ別ページ（IDの数だけ自動生成）
    party_pages = []
    for pid in my_party_ids:
        page_obj = st.Page(
            "views/party_page.py",
            title=f"⚔️ パーティ {pid}",
            icon="👥",
            url_path=f"{pid}",
        )
        party_pages.append(page_obj)

    pages_dict["パーティ別分析"] = party_pages

    pg = st.navigation(pages_dict)
    st.session_state["battles"]          = battles
    st.session_state["active_season"]    = active_season
    st.session_state["season_list"]      = season_list
    st.session_state["vs_party_pokemon"] = vs_party_pokemon
    st.session_state["my_party_pokemon"] = my_party_pokemon
    pg.run()