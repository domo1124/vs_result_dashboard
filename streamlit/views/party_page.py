"""
views/party_page.py  ─ パーティ別分析ページ

URL パス "party_{pid}" から my_party_id を特定し、
該当パーティの詳細ダッシュボードを表示する。
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from urllib.parse import urlparse

# ─────────────────────────────────────────
# party_id の特定
#   st.context.url_path  →  "party_1"  "party_42" など
#   ※ Streamlit 1.37 以上が必要
# ─────────────────────────────────────────
current_url = st.context.url
try:
    selected_party_id = urlparse(current_url).path.strip("/")
except (ValueError, IndexError):
    st.error("パーティIDをURLから取得できませんでした。")
    st.stop()
# ─────────────────────────────────────────
# session_state からデータ取得
# ─────────────────────────────────────────
result   : pd.DataFrame = st.session_state["battles"]
vs_party : pd.DataFrame = st.session_state["vs_party_pokemon"]
my_party : pd.DataFrame = st.session_state["my_party_pokemon"]

# ─────────────────────────────────────────
# フィルタリング
# ─────────────────────────────────────────
df = result[result["my_party_id"] == selected_party_id].copy()
 
# シーズンフィルター（サイドバー）
season_list = ["全シーズン"] + sorted(result["season"].dropna().unique().tolist())
selected_season = st.sidebar.selectbox("シーズン", season_list, key=f"season_{selected_party_id}")
if selected_season != "全シーズン":
    df = df[df["season"] == selected_season]
 
# ─────────────────────────────────────────
# 自パーティ情報
# ─────────────────────────────────────────
my_members = (
    my_party[my_party["party_id"] == selected_party_id]
    .sort_values("party_num")
)
 
# ─────────────────────────────────────────
# サイドバー: 自パーティ一覧
# ─────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown(f"### パーティ {selected_party_id} の構成")
for _, row in my_members.iterrows():
    item_html = (
        f"<br><span style='color:#888;font-size:11px;'>🎒 {row['item_name']}</span>"
        if pd.notna(row.get("item_name")) else ""
    )
    st.sidebar.markdown(
        f"""
        <div style="border:1px solid #ddd;border-radius:8px;
                    padding:6px 10px;margin-bottom:5px;font-size:13px;">
        <b>{int(row['party_num'])}. {row['pokemon_name']}</b>{item_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
 
# ─────────────────────────────────────────
# サマリー指標
# ─────────────────────────────────────────
total    = len(df)
wins     = int(df["is_win"].sum())
losses   = total - wins
win_rate = wins / total * 100 if total > 0 else 0
 
st.title(f"パーティ {selected_party_id} の分析")
 
m1, m2, m3, m4 = st.columns(4)
m1.metric("総対戦数", f"{total} 試合")
m2.metric("勝利数",   f"{wins} 勝",  f"{win_rate:.1f}%")
m3.metric("敗北数",   f"{losses} 敗")
m4.metric("勝率",     f"{win_rate:.1f}%")
 
st.divider()
 
# ─────────────────────────────────────────
# 中間データ作成
# ─────────────────────────────────────────
# 相手の選出（long 形式）
vs_select_long = pd.melt(
    df,
    id_vars=["vs_datetime_str", "result", "is_win", "my_select1"],
    value_vars=["vs_select1", "vs_select2", "vs_select3"],
    var_name="slot",
    value_name="vs_pokemon",
).dropna(subset=["vs_pokemon"])
 
# 相手パーティ（party_id で結合）
vs_merged = df.merge(
    vs_party, on="vs_datetime_str", how="left"
)
 
# ─────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────
def bar_chart(series: pd.Series, title: str, color: str = "#378ADD", top_n: int = 10):
    """上位 top_n の横棒グラフを返す"""
    plot_df = series.nlargest(top_n).reset_index()
    plot_df.columns = ["ポケモン", "回数"]
    fig = px.bar(
        plot_df[::-1],
        x="回数", y="ポケモン",
        orientation="h",
        title=title,
        color_discrete_sequence=[color],
        text="回数",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        margin=dict(l=0, r=20, t=36, b=0),
        yaxis_title=None, xaxis_title=None,
        height=330, title_font_size=13,
    )
    return fig
 
 
# ─────────────────────────────────────────
# タブ
# ─────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 選出率分析",
    "🏆 WIN / LOSS 比較",
    "🎯 初手分析",
    "👻 選出外分析",
    "🔀 組み合わせ分析",
])
 
# ── タブ1: 選出率分析 ─────────────────────
with tab1:
    # ① 選出率 TOP 10
    #   選出率 = 選出回数 / そのポケモンがパーティに入っていた対戦数
    select_cnt = vs_select_long["vs_pokemon"].value_counts()

    # パーティ在籍回数: vs_merged は battle × party_member の long 形式なので
    # vs_datetime_str でユニーク化してからカウント
    party_appear_cnt = (
        vs_merged.dropna(subset=["pokemon_name"])
        .drop_duplicates(subset=["vs_datetime_str", "pokemon_name"])
        ["pokemon_name"]
        .value_counts()
    )

    select_rate = (
        (select_cnt / party_appear_cnt)
        .dropna()
        .mul(100)
        .round(1)
    )
    select_df   = (
        pd.DataFrame({
            "回数":          select_cnt,
            "パーティ在籍数": party_appear_cnt,
            "選出率(%)":     select_rate,
        })
        .nlargest(10, "回数")
        .reset_index()
        .rename(columns={"vs_pokemon": "ポケモン"})
    )
 
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**① 相手の選出回数 TOP 10**")
        st.dataframe(select_df, use_container_width=True, hide_index=True)
    with c2:
        st.plotly_chart(bar_chart(select_cnt, "選出回数 TOP 10", "#378ADD"),
                        use_container_width=True)
 
    st.divider()
 
    # ⑥ 相手初手 TOP 10（全試合）
    c3, c4 = st.columns(2)
    first_cnt = df["vs_select1"].value_counts()
    with c3:
        st.markdown("**⑥ 相手が最初に出してきたポケモン TOP 10**")
        st.dataframe(
            first_cnt.nlargest(10).reset_index()
                .rename(columns={"vs_select1": "ポケモン", "count": "回数"}),
            use_container_width=True, hide_index=True,
        )
    with c4:
        st.plotly_chart(bar_chart(first_cnt, "相手初手 TOP 10", "#7F77DD"),
                        use_container_width=True)
 
# ── タブ2: WIN / LOSS 比較 ───────────────
with tab2:
    win_sel   = vs_select_long[vs_select_long["is_win"]]
    loss_sel  = vs_select_long[~vs_select_long["is_win"]]
    win_party_df  = vs_merged[vs_merged["is_win"]]
    loss_party_df = vs_merged[~vs_merged["is_win"]]
 
    st.markdown("##### 選出ポケモン (WIN vs LOSS)")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(bar_chart(win_sel["vs_pokemon"].value_counts(),
                                  "③ WIN時 選出 TOP 10", "#1D9E75"),
                        use_container_width=True)
    with c2:
        st.plotly_chart(bar_chart(loss_sel["vs_pokemon"].value_counts(),
                                  "② LOSS時 選出 TOP 10", "#E24B4A"),
                        use_container_width=True)
 
    st.markdown("##### パーティに存在したポケモン (WIN vs LOSS)")
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(
            bar_chart(win_party_df["pokemon_name"].value_counts(),
                      "⑤ WIN時 パーティ存在 TOP 10", "#5DCAA5"),
            use_container_width=True,
        )
    with c4:
        st.plotly_chart(
            bar_chart(loss_party_df["pokemon_name"].value_counts(),
                      "④ LOSS時 パーティ存在 TOP 10", "#D85A30"),
            use_container_width=True,
        )
 
    st.markdown("##### 勝敗別 比較表")
    compare = pd.DataFrame({
        "WIN時選出":  win_sel["vs_pokemon"].value_counts(),
        "LOSS時選出": loss_sel["vs_pokemon"].value_counts(),
    }).fillna(0).astype(int).sort_values("WIN時選出", ascending=False).head(20)
    st.dataframe(compare, use_container_width=True)
 
# ── タブ3: 初手分析 ──────────────────────
with tab3:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            bar_chart(df[df["is_win"]]["vs_select1"].value_counts(),
                      "⑫ WIN時 相手初手 TOP 10", "#1D9E75"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            bar_chart(df[~df["is_win"]]["vs_select1"].value_counts(),
                      "⑪ LOSS時 相手初手 TOP 10", "#E24B4A"),
            use_container_width=True,
        )
 
    st.divider()
    st.markdown("**相手初手ポケモン別 勝率**")
    first_stats = (
        df.groupby("vs_select1")
        .agg(対戦数=("is_win", "count"), 勝利数=("is_win", "sum"))
        .assign(勝率=lambda x: (x["勝利数"] / x["対戦数"] * 100).round(1))
        .sort_values("対戦数", ascending=False)
        .head(20)
        .reset_index()
        .rename(columns={"vs_select1": "相手初手"})
    )
    st.dataframe(first_stats, use_container_width=True, hide_index=True)
 
# ── タブ4: 選出外分析 ────────────────────
with tab4:
    # ⑦ 選出されたが初手でなかった
    not_first     = vs_select_long[vs_select_long["slot"] != "vs_select1"]
    not_first_cnt = not_first["vs_pokemon"].value_counts()
 
    # ⑧ パーティにいて出てこなかった（vs_party_pokemon から差分）
    not_selected_rows = []
    for _, row in df.iterrows():
        selected = {row["vs_select1"], row["vs_select2"], row["vs_select3"]}
        selected = {p for p in selected if pd.notna(p)}
        party_members = (
            vs_party[vs_party["vs_datetime_str"] == row["vs_datetime_str"]]["pokemon_name"].tolist()
        )
        for poke in party_members:
            if poke not in selected:
                not_selected_rows.append({"pokemon": poke, "is_win": row["is_win"]})
    not_sel_df = pd.DataFrame(not_selected_rows)
 
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            bar_chart(not_first_cnt,
                      "⑦ 選出されたが初手に出なかった TOP 10", "#BA7517"),
            use_container_width=True,
        )
    with c2:
        if not not_sel_df.empty:
            st.plotly_chart(
                bar_chart(not_sel_df["pokemon"].value_counts(),
                          "⑧ パーティにいて出てこなかった TOP 10", "#888780"),
                use_container_width=True,
            )
        else:
            st.info("vs_party_pokemon.csv との紐付けデータが不足しています。")
 
# ── タブ5: 組み合わせ分析 ────────────────
with tab5:
    combo = df[["my_select1", "vs_select1", "is_win"]].copy()
    combo["組み合わせ"] = combo["my_select1"] + " × " + combo["vs_select1"]
 
    win_combo  = combo[combo["is_win"]]["組み合わせ"].value_counts().reset_index()
    loss_combo = combo[~combo["is_win"]]["組み合わせ"].value_counts().reset_index()
    win_combo.columns  = ["組み合わせ", "回数"]
    loss_combo.columns = ["組み合わせ", "回数"]
 
    def combo_bar(df_c, title, color):
        fig = px.bar(
            df_c.head(10)[::-1],
            x="回数", y="組み合わせ",
            orientation="h", title=title,
            color_discrete_sequence=[color], text="回数",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(height=360, margin=dict(l=0, r=20, t=36, b=0),
                          yaxis_title=None, xaxis_title=None, title_font_size=13)
        return fig
 
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(combo_bar(win_combo,  "⑩ WIN時 初手組み合わせ TOP 10",  "#1D9E75"),
                        use_container_width=True)
    with c2:
        st.plotly_chart(combo_bar(loss_combo, "⑨ LOSS時 初手組み合わせ TOP 10", "#E24B4A"),
                        use_container_width=True)
 
    st.divider()
    st.markdown("**組み合わせ別 勝率テーブル**")
    combo_stats = (
        combo.groupby("組み合わせ")
        .agg(対戦数=("is_win", "count"), 勝利数=("is_win", "sum"))
        .assign(勝率=lambda x: (x["勝利数"] / x["対戦数"] * 100).round(1))
        .sort_values("対戦数", ascending=False)
        .head(20)
        .reset_index()
    )
    st.dataframe(combo_stats, use_container_width=True, hide_index=True)