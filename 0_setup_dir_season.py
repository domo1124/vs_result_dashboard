import argparse
from datetime import datetime, timedelta
import os
import sys

# サポートする日付フォーマット
DATE_FORMATS = ["%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"]


def parse_date(date_str):
    """文字列を指定されたフォーマットのいずれかでdatetimeオブジェクトに変換する"""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # どのフォーマットにもマッチしなかった場合
    print(
        f"エラー: 日付 '{date_str}' のフォーマットが正しくありません。",
        file=sys.stderr,
    )
    print(f"対応フォーマット: 20260518, 2026-05-18, 2026/05/18", file=sys.stderr)
    sys.exit(1)


def main():
    # コマンドライン引数の設定
    parser = argparse.ArgumentParser(
        description="シーズンと期間に応じたディレクトリを生成します。"
    )
    parser.add_argument("season", help="シーズン名 (例: season1)")
    parser.add_argument("start_date", help="開始日 (例: 20260518)")
    parser.add_argument("end_date", help="終了日 (例: 20260520)")

    args = parser.parse_args()

    # 日付のパース
    start_dt = parse_date(args.start_date)
    end_dt = parse_date(args.end_date)

    if start_dt > end_dt:
        print(
            "エラー: 開始日は終了日より前の日付を指定してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    # ベースとなるディレクトリパス (data/シーズン名)
    base_dir = os.path.join("data", args.season)

    # 開始日から終了日まで1日ずつ処理
    current_dt = start_dt
    created_count = 0

    while current_dt <= end_dt:
        # ディレクトリ名用の一意なフォーマット（%Y%m%d）に統一
        date_dir_name = current_dt.strftime("%Y%m%d")

        # 作成するサブディレクトリのリスト
        sub_dirs = ["videos", "screenshots"]

        for sub_dir in sub_dirs:
            # パスを結合 (data/シーズン名/yyyymmdd/サブディレクトリ)
            target_path = os.path.join(base_dir, date_dir_name, sub_dir)

            # ディレクトリの作成 (既に存在していてもエラーにしない)
            os.makedirs(target_path, exist_ok=True)

        current_dt += timedelta(days=1)
        created_count += 1

    print(f"成功: {args.season} の配下に {created_count}日分のディレクトリを作成しました。")


if __name__ == "__main__":
    main()