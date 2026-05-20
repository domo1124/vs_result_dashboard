import streamlit as st

# app.pyで読み込んだデータを取得
df = st.session_state.get("main_df")

# 今、サイドバーでどのパーティ（タイトル）がクリックされたかを取得
# 例: 「⚔️ パーティ P1」というタイトルから「P1」の部分だけを抽出
current_page_title = st.active_page["title"]
current_party_id = current_page_title.replace("⚔️ パーティ ", "")

st.title(f"⚔️ パーティ分析 [{current_party_id}]")
st.write(f"パーティID: **{current_party_id}** の詳細データを表示しています。")

if df is not None and "party_id" in df.columns:
    # 読み込んだ全データから、今選ばれているパーティIDのデータだけを絞り込む（フィルタリング）
    party_df = df[df["party_id"] == current_party_id]

    # あとはこの「party_df」を使って、このパーティ専用のダッシュボードを描画するだけ！
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("このパーティの戦績一覧")
        st.dataframe(party_df, use_container_width=True)

    with col2:
        st.subheader("特定の持ち物や選出の勝率推移")
        # 例: Mega StoneやChoice Scarfなどの勝率分析をここに書く
        st.metric(label="このパーティでの試合数", value=f"{len(party_df)} 戦")
else:
    st.write("該当するデータが見つかりません。")