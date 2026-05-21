import streamlit as st
from streamlit_gsheets import GSheetsConnection
import streamlit as st
import pandas as pd

# ============================================================
# 設定：スプレッドシートのURLをここに貼る
# ============================================================
SPREADSHEET_ID = st.secrets["spreadsheet"]["id"]
# シートごとのgid（スプレッドシート下部タブを右クリック→「シートのリンクをコピー」で確認）
SHEET_GID = {
    "battles": "1903861099", # resultシート
    "myparty_analysis_list": "915221700", 
    "season": "722242110",
    "vs_party_pokemon": "705459567",
    "my_party_pokemon": "1298543501"
}
# ============================================================
# URL生成
# ============================================================

def _build_url(sheet_key: str) -> str:
    gid = SHEET_GID[sheet_key]
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
        f"/export?format=csv&gid={gid}"
    )

# ============================================================
# データ読み込み（キャッシュ付き）
# ============================================================

@st.cache_data(ttl=3600)
def load_battles() -> pd.DataFrame:
    """対戦記録シートを読み込む"""
    try:
        df = pd.read_csv(_build_url("battles"))
        df = _clean_battles(df)
        return df
    except Exception as e:
        st.error(f"対戦記録の読み込みに失敗しました: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_parties() -> list:
    try:
        df = pd.read_csv(_build_url("myparty_analysis_list"))
        my_party_ids = _target_parties(df)
        return my_party_ids
    except Exception as e:
        st.error(f"パーティ情報の読み込みに失敗しました: {e}")
        return []

@st.cache_data(ttl=3600)
def load_season()  -> Tuple[list, str]:
    try:
        df = pd.read_csv(_build_url("season"))
        season_list, active_season = _target_season(df)
        return season_list, active_season
    except Exception as e:
        st.error(f"開催中のシーズン読み込みに失敗しました: {e}")
        return [],"error"

@st.cache_data(ttl=3600)
def load_vs_party_pokemon() -> pd.DataFrame:
    """相手パーティ一覧のシートを読み込む"""
    try:
        df = pd.read_csv(_build_url("vs_party_pokemon"))
        df = _clean_party_pokemon(df)
        return df
    except Exception as e:
        st.error(f"相手パーティ一覧の読み込みに失敗しました: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_my_party_pokemon() -> pd.DataFrame:
    """自分のパーティ一覧のシートを読み込む"""
    try:
        df = pd.read_csv(_build_url("my_party_pokemon"))
        df = _clean_party_pokemon(df)
        return df
    except Exception as e:
        st.error(f"相手パーティ一覧の読み込みに失敗しました: {e}")
        return pd.DataFrame()
# ============================================================
# クレンジング（列名・型をここで統一）
# ============================================================

def _clean_battles(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip() # 列名の空白除去
    if "vs_datetime" in df.columns:
        df["vs_datetime"] =  pd.to_datetime(df['vs_datetime'], format='%Y%m%d_%H%M%S', errors="coerce")
    if "result" in df.columns:
        df["result"] = df["result"].str.strip() # 「勝」「負」などの空白除去
        df["is_win"] = df["result"] == "WIN"
    return df.dropna(how="all") # 完全に空の行を除去

def _clean_party_pokemon(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip() # 列名の空白除去
    return df.dropna(how="all") # 完全に空の行を除去

def _target_parties(df: pd.DataFrame) -> list:
    df.columns = df.columns.str.strip()
    my_party_ids = sorted(df["party_id"].dropna().unique())
    return my_party_ids

def _target_season(df: pd.DataFrame) -> Tuple[list, str]:
    df.columns = df.columns.str.strip() # 列名の空白除去
    df['end_date'] = pd.to_datetime(df['end_date'])
    #開催中のシーズンと直近2回のシーズンを取得
    target_season = df[df['active'] == False].sort_values(by='end_date', ascending=False).head(2)
    active_season = next(iter(df[df['active'] == True].sort_values(by='end_date', ascending=False)['name']), None)
    return target_season['name'].values.tolist(),active_season

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
    battles = load_battles()
    my_party_ids = load_parties()
    season_list,active_season = load_season()
    vs_party_pokemon=load_vs_party_pokemon()
    my_party_pokemon=load_my_party_pokemon()
    # 3. ナビゲーション（サイドバーメニュー）の定義
    # 「全体ページ」を登録
    pages_dict = {
        "全体メニュー": [
            st.Page(
                "views/global_page.py", title="📊 全体ダッシュボード", icon="📈"
            )
        ]
    }
    # ── パーティ別ページ（IDの数だけ自動生成）
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

    # 4. ナビゲーションを実行（これでサイドバーが自動生成されます）
    pg = st.navigation(pages_dict)
    st.session_state["battles"] = battles
    st.session_state["active_season"] = active_season
    st.session_state["season_list"] = season_list
    st.session_state["vs_party_pokemon"] = vs_party_pokemon
    st.session_state["my_party_pokemon"] = my_party_pokemon
    pg.run()