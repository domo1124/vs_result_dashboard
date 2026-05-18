import os
import glob
import re
import shutil

# 設定（環境に合わせて変更してください）
SRC_DIR = "D:/pokemon_videos"
DEST_BASE_PATTERN = "data/*" # シーズン部分はワイルドカード

def main():
    # 1. 移動元のディレクトリが存在するか確認
    if not os.path.exists(SRC_DIR):
        print(f"エラー: 移動元ディレクトリ '{SRC_DIR}' が見つかりません。")
        return

    # 2. 移動元からすべての mp4 ファイルを取得
    mp4_files = glob.glob(os.path.join(SRC_DIR, "*.mp4"))

    if not mp4_files:
        print(f"'{SRC_DIR}' 配下に mp4 ファイルが見つかりませんでした。")
        return

    # ファイル名先頭の「YYYY-MM-DD」を抽出する正規表現
    date_pattern = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
    
    moved_count = 0

    for file_path in mp4_files:
        file_name = os.path.basename(file_path)
        match = date_pattern.match(file_name)

        if not match:
            print(f"スキップ: '{file_name}' に日付プレフィックス(YYYY-MM-DD)がありません。")
            continue

        # ハイフンを取り除いて「YYYYMMDD」に変換
        year, month, day = match.groups()
        target_date_str = f"{year}{month}{day}"

        # 3. 移動先候補（data/*/YYYYMMDD/）を検索 (videosは挟まない)
        dest_search_path = os.path.join(DEST_BASE_PATTERN, target_date_str)
        matched_dest_dirs = glob.glob(dest_search_path)

        if not matched_dest_dirs:
            print(f"スキップ: '{file_name}' に対応する移動先ディレクトリが見つかりません。 (期待値: data/*/{target_date_str}/)")
            continue

        # 4. マッチした日付ディレクトリへファイルを移動（複数ファイルもループで順次処理されます）
        for i, dest_dir in enumerate(matched_dest_dirs):
            dest_file_path = os.path.join(dest_dir, file_name)

            # 同名ファイルの重複チェック
            if os.path.exists(dest_file_path):
                print(f"重複スキップ: '{dest_file_path}' は既に存在しています。")
                continue

            if i == 0:
                # 1つ目のマッチ先には「移動」
                shutil.move(file_path, dest_file_path)
                print(f"移動完了: {file_name} -> {dest_dir}/")
                moved_count += 1
            else:
                # 万が一、別シーズンに同じ日付ディレクトリが重複して存在した場合は「コピー」で配る
                shutil.copy2(file_path, dest_file_path)
                print(f"コピー完了 (複数シーズンにマッチ): {file_name} -> {dest_dir}/")

    print(f"\n処理終了: 合計 {moved_count} 個のファイルを移動しました。")

if __name__ == "__main__":
    main()