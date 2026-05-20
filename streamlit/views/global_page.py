import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter

# ================================================================
# 共通ユーティリティ
# ================================================================
def win_rate(sub: pd.DataFrame) -> float:
    if len(sub) == 0:
        return 0.0
    return round(len(sub[sub["result"] == "WIN"]) / len(sub) * 100, 1)

def delta_color(v: float) -> str:
    return "normal" if v >= 50 else "inverse"

PLOTLY_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor ="rgba(0,0,0,0)",
    font_color   ="#aaa",
    margin       =dict(l=0, r=0, t=10, b=0),
)

def render_analysis_tab(df,df_vs_party,season_name):
    # ---- 縦持ち vs_party を使える形に変換 -----------------------
    # has_party: party_id / party_num / pokemon_name の3カラムが最低限あればOK
    has_party = (
        df_vs_party is not None
        and {"party_id", "party_num", "pokemon_name"}.issubset(df_vs_party.columns)
    )

    if has_party:
        # 対戦記録の vs_party_id と party シートの party_id をマージ
        # → 各試合に相手パーティ6匹を紐付け
        party_long = df_vs_party.copy()
        party_long = party_long.rename(columns={"party_id": "vs_party_id"})
        df_with_party = df.merge(party_long[["vs_party_id","pokemon_name"]],
                                 on="vs_party_id", how="left")
        # 相手パーティ在籍回数（ユニークな試合×pokemon）
        # 同一試合で同じポケモンが重複カウントされないよう VSID で dedup
        party_count = Counter(
            df_with_party.drop_duplicates(subset=["VSID","pokemon_name"])
            ["pokemon_name"].dropna()
        )
    else:
        party_count = Counter()

    # ----------------------------------------------------------------
    # ② -1  相手の選出ポケモンランキング TOP 15
    #        同数の場合: 相手パーティ在籍回数が多い順
    # ----------------------------------------------------------------
    st.markdown(f"# 選出ポケモン分析：Season {season_name}")
    st.markdown("#### 🔴 相手 選出ポケモン TOP 15")
    st.caption("同数の場合は相手パーティに入っていた回数が多い方を優先")

    vs_sel = pd.concat([
        df["vs_select1"], df["vs_select2"], df["vs_select3"]
    ]).dropna()
    sel_count = Counter(vs_sel)

    if has_party:
        party_poke = df_with_party.drop_duplicates(subset=["VSID","pokemon_name"])["pokemon_name"].dropna()
        party_count_for_tiebreak = Counter(party_poke)
    else:
        party_count_for_tiebreak = Counter()

    sel_df = (pd.DataFrame(sel_count.items(), columns=["pokemon", "selected"])
              .assign(party_count=lambda d: d["pokemon"].map(party_count_for_tiebreak).fillna(0).astype(int))
              .sort_values(["selected", "party_count"], ascending=False)
              .head(15)
              .reset_index(drop=True))
    sel_df.index += 1

    total_battles = len(df)
    sel_df["選出率"] = (sel_df["selected"] / total_battles * 100).round(1).astype(str) + "%"

    fig1 = go.Figure(go.Bar(
        x=sel_df["selected"][::-1],
        y=sel_df["pokemon"][::-1],
        orientation="h",
        marker=dict(
            color=sel_df["selected"][::-1],
            colorscale=[[0,"#1e1e40"],[1,"#7c6aff"]],
        ),
        text=sel_df["選出率"][::-1],
        textposition="outside",
        hovertemplate="%{y}<br>選出: %{x}回<extra></extra>",
    ))
    fig1.update_layout(**PLOTLY_BASE, height=420,
                       xaxis=dict(gridcolor="#1e1e32"),
                       yaxis=dict(tickfont=dict(size=12)))
    st.plotly_chart(fig1, use_container_width=True,key=f"fig1_{season_name}")

    # ----------------------------------------------------------------
    # ② -2  相手パーティ在籍ポケモン（5回以上）
    # ----------------------------------------------------------------
    st.markdown("#### 🔵 相手パーティ内ポケモン（5回以上）")

    if has_party:
        party_df = (pd.DataFrame(party_count.items(), columns=["pokemon", "count"])
                    .query("count >= 5")
                    .sort_values("count", ascending=False)
                    .reset_index(drop=True))
        party_df.index += 1

        if party_df.empty:
            st.info("5回以上パーティに入っていたポケモンはいません。")
        else:
            fig2 = go.Figure(go.Bar(
                x=party_df["count"][::-1],
                y=party_df["pokemon"][::-1],
                orientation="h",
                marker=dict(
                    color=party_df["count"][::-1],
                    colorscale=[[0,"#1e2040"],[1,"#00c2ff"]],
                ),
                text=party_df["count"][::-1].astype(str) + "回",
                textposition="outside",
                hovertemplate="%{y}<br>在籍: %{x}回<extra></extra>",
            ))
            fig2.update_layout(**PLOTLY_BASE,
                               height=max(300, len(party_df) * 26 + 60),
                               xaxis=dict(gridcolor="#1e1e32"),
                               yaxis=dict(tickfont=dict(size=12)))
            st.plotly_chart(fig2, use_container_width=True,key=f"fig2_{season_name}")
    else:
        st.warning("⚠️ vs_party シートが未接続のため表示できません。`df_vs_party` を設定してください。")

    # ----------------------------------------------------------------
    # ② -3  相手の先発ポケモン TOP 10
    # ----------------------------------------------------------------
    st.markdown("#### ⚡ 相手 先発ポケモン TOP 10")
    st.caption("vs_select1（相手の1番目に出てきたポケモン）")

    lead_count = Counter(df["vs_select1"].dropna())
    lead_df = (pd.DataFrame(lead_count.items(), columns=["pokemon", "count"])
               .sort_values("count", ascending=False)
               .head(10)
               .reset_index(drop=True))
    lead_df.index += 1
    lead_df["先発率"] = (lead_df["count"] / total_battles * 100).round(1).astype(str) + "%"

    fig3 = go.Figure(go.Bar(
        x=lead_df["count"][::-1],
        y=lead_df["pokemon"][::-1],
        orientation="h",
        marker=dict(
            color=lead_df["count"][::-1],
            colorscale=[[0,"#201a10"],[1,"#ffd700"]],
        ),
        text=lead_df["先発率"][::-1],
        textposition="outside",
        hovertemplate="%{y}<br>先発: %{x}回<extra></extra>",
    ))
    fig3.update_layout(**PLOTLY_BASE, height=340,
                       xaxis=dict(gridcolor="#1e1e32"),
                       yaxis=dict(tickfont=dict(size=12)))
    st.plotly_chart(fig3, use_container_width=True,key=f"fig3_{season_name}")

    # --- 補足テーブル ---
    with st.expander("テーブルで確認"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("相手選出 TOP15")
            st.dataframe(sel_df[["pokemon","selected","選出率"]]
                         .rename(columns={"pokemon":"ポケモン","selected":"選出数"}),
                         hide_index=False)
        with c2:
            if has_party and not party_df.empty:
                st.caption("パーティ在籍（5回以上）")
                st.dataframe(party_df.rename(columns={"pokemon":"ポケモン","count":"在籍数"}),
                             hide_index=False)
        with c3:
            st.caption("先発 TOP10")
            st.dataframe(lead_df[["pokemon","count","先発率"]]
                         .rename(columns={"pokemon":"ポケモン","count":"先発数"}),
                         hide_index=False)

# app.pyで読み込んだデータを取得
df = st.session_state.get("battles")
active_season = st.session_state.get("active_season")
season_list = st.session_state.get("season_list")
vs_party_df = st.session_state.get("vs_party_pokemon")
st.set_page_config(page_title="Battle Dashboard", layout="wide")

# つくりたい2つのタブを定義
tab_battle, tab_select = st.tabs(["対戦成績", "選出ポケモン分析"])

# ================================================================
# ① 対戦成績タブ
# ================================================================
with tab_battle:
    st.header(f"シーズン:{active_season}")
    df_active_season = df[df["season"] == active_season]
    df_master = df[
        (df["rank"] == "ハイパーボール") & 
        (df["season"] == active_season)
    ]
    wr_all    = win_rate(df)
    wr_master = win_rate(df_master)

    # --- サマリーカード ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("全体 勝率",    f"{wr_all}%",
                  f"{len(df_active_season[df_active_season['result']=='WIN'])}勝 {len(df_active_season[df_active_season['result']=='LOSS'])}敗")
    with c2:
        st.metric("MB級 勝率",   f"{wr_master}%",
                  f"{len(df_master[df_master['result']=='WIN'])}勝 {len(df_master[df_master['result']=='LOSS'])}敗")
    with c3:
        st.metric("総試合数",    len(df_active_season),    f"MB級 {len(df_master)}戦")

    st.markdown("---")
    # --- 勝率推移 ---
    st.markdown("#### 勝率推移")

    df_trend = df_active_season.copy()
    df_trend["date"] = pd.to_datetime(df_trend["vs_datetime"]).dt.strftime("%Y-%m-%d")

    # 日別集計 → 累計勝率
    daily = (df_trend.groupby("date")
             .agg(wins=("result", lambda x: (x == "WIN").sum()),
                  total=("result", "count"))
             .reset_index())
    daily["cum_wins"]  = daily["wins"].cumsum()
    daily["cum_total"] = daily["total"].cumsum()
    daily["wr"]        = (daily["cum_wins"] / daily["cum_total"] * 100).round(1)
    daily["daily_wr"]  = (daily["wins"] / daily["total"] * 100).round(1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["wr"],
        name="累計勝率", mode="lines+markers",
        line=dict(color="#7c6aff", width=2.5),
        marker=dict(size=5, color="#a99fff"),
        hovertemplate="%{x}<br>累計勝率: %{y}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["daily_wr"],
        name="日別勝率", opacity=0.25,
        marker_color="#00c2ff",
        customdata=daily[["wins","total"]].assign(loses=lambda d: d["total"]-d["wins"]).values,
        hovertemplate="%{x}<br>%{customdata[0]}勝%{customdata[2]}敗<extra></extra>",
    ))
    fig.add_hline(y=50, line_dash="dot", line_color="#444", line_width=1)
    fig.update_layout(
        **PLOTLY_BASE,
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(range=[0, 100], ticksuffix="%", gridcolor="#1e1e32", zeroline=False),
        xaxis=dict(type="category", gridcolor="#1e1e32"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")
    # --- 直近5試合 ---
    st.markdown("#### 直近5試合")

    recent5 = df.sort_values("vs_datetime", ascending=False).head(5)

    for _, row in recent5.iterrows():
        is_win   = row["result"] == "WIN"
        bg_color = "rgba(0,229,118,0.05)"  if is_win else "rgba(255,68,85,0.05)"
        bd_color = "#00e57640"              if is_win else "#ff445540"
        res_color= "#00e576"               if is_win else "#ff4455"

        dt_str = pd.to_datetime(row["vs_datetime"]).strftime("%m/%d %H:%M")

        # ポケモンバッジHTML
        def badges(pokes, color):
            return " ".join(
                f'<span style="background:#1e1e30;border:1px solid {color}33;'
                f'border-radius:10px;padding:2px 9px;font-size:11px;color:#bbb;">'
                f'{p}</span>'
                for p in pokes if pd.notna(p)
            )

        my_badges  = badges([row["my_select1"], row["my_select2"], row["my_select3"]], "#7c6aff")
        vs_badges  = badges([row["vs_select1"], row["vs_select2"], row["vs_select3"]], "#ff6b6b")

        html = f"""
        <div style="background:{bg_color};border:1px solid {bd_color};
                    border-radius:12px;padding:12px 16px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:16px;font-weight:800;color:{res_color};">
              {'✓ 勝利' if is_win else '✗ 敗北'}
            </span>
            <span style="font-size:11px;color:#555;">{dt_str} · {row['rank']}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:11px;color:#7c6aff;width:28px;flex-shrink:0;">自分</span>
              {my_badges}
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:11px;color:#ff6b6b;width:28px;flex-shrink:0;">相手</span>
              {vs_badges}
            </div>
          </div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

# ================================================================
# ② 選出分析タブ
# ================================================================
with tab_select:
    target_list = []
    target_list.append(active_season)
    for i in reversed(season_list):
        target_list.append(i)
    tabs = st.tabs(target_list)
    for tab, season in zip(tabs, target_list):
        with tab:
            # フィルタリングされたデータを取得
            target_df = df[df["season"] == season]
            target_ids = target_df['vs_party_id'].unique()
            extracted_vs_party_df = vs_party_df[vs_party_df['party_id'].isin(target_ids)]
            
            # 関数にシーズン名を渡して描画
            render_analysis_tab(target_df,extracted_vs_party_df, season)



