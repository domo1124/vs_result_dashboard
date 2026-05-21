import glob
import json
import os
from datetime import datetime

# 1. 対象のフォルダパスを指定してファイル一覧を取得
folder_path = 'party_snap_json'
json_files = glob.glob(os.path.join(folder_path, '*.json'))

all_items = []

# 2. 各ファイルを順番に読み込んで1つのリストに結合
for file_path in json_files:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # データがリスト型（[]）の場合
            if isinstance(data, list):
                all_items.extend(data)
            # データが単一の辞書型（{}）の場合、リストに入れて結合
            elif isinstance(data, dict):
                all_items.append(data)
                
    except Exception as e:
        print(f"ファイル読み込みエラー [{os.path.basename(file_path)}]: {e}")

# 3. vs_date の値でソート（日付順）
sorted_items = sorted(all_items, key=lambda x: str(x.get('vs_date', '')))

# 4. ソートされたデータから value値のみを表示
print("--- vs_dateでソートしたすべての値 (Values) ---")
for item in sorted_items:
    for val in item.values():
        print(val)