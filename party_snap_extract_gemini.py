import argparse
import glob
import json
import os
import re
import shutil  # 追加：ファイルの移動用
import time  # 追加：待機時間（sleep）用
from datetime import datetime
from enum import Enum
from PIL import Image
from pydantic import BaseModel
from google import genai
import configparser
import pandas as pd

config = configparser.ConfigParser()
config_file = 'config.ini'
config.read(config_file, encoding='utf-8')
spreadsheet_info = config['spreadsheet']
pokemon_list_url = f"{spreadsheet_info['url']}{spreadsheet_info['pokemon_list_export_csv']}" 
gemini_api_key = config['gemini']['api_key']
gemini_model = config['gemini']['model']
# ==========================================
# 1. ポケモン一覧リスト
# ==========================================
df = pd.read_csv(pokemon_list_url)
ALLOW_POKEMON_LIST = df['pokemon_name'].tolist()
pokemon_list_text = "\n".join(ALLOW_POKEMON_LIST)

# 2. 生成したEnumを型として指定
class OpponentParty(BaseModel):
    pokemon_1: str
    pokemon_2: str
    pokemon_3: str
    pokemon_4: str
    pokemon_5: str
    pokemon_6: str

# ==========================================
# 3. 日付文字列の正規化関数
# ==========================================
def normalize_date(date_str):
    formats = ["%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"対応していない日付フォーマットです: {date_str}")

# ==========================================
# 4. メイン処理
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="選出画面から対戦相手のパーティを抽出するスクリプト")
    parser.add_argument("dates", nargs="+", help="抽出対象の日付 (例: 20260520)")
    parser.add_argument("--output", default="party_results.json", help="出力するJSONファイル名")
    args = parser.parse_args()

    client = genai.Client(api_key=gemini_api_key)
    
    prompt = f"""
    添付された画像はポケモン対戦の選出画面の左半分（対戦相手のパーティ）です。
    上から順に6匹のポケモン名を抽出してください。
    また色違いポケモンの場合もあり得るので、厳密にチェックしてください。

    【重要ルール】
    ポケモン名は、必ず以下の「許可されたポケモンリスト」にある文字列と完全に一致するもの（大文字・小文字、スペースも同様）のみを使用してください。リストにないポケモン名を出力してはいけません。
    
    ▼許可されたポケモンリスト：
    {pokemon_list_text}
    """

    results = []
    time_pattern = re.compile(r"(\d{8}_\d{6})")
    
    # 複数日付が渡された場合に備え、出力ファイル名に使う最初の有効な日付を保持する変数
    first_valid_date = None

    for date_str in args.dates:
        try:
            yyyymmdd = normalize_date(date_str)
            if first_valid_date is None:
                first_valid_date = yyyymmdd
        except ValueError as e:
            print(f"スキップ: {e}")
            continue
            
        # 画像の探索ルート
        search_pattern = f"./data/*/{yyyymmdd}/screenshots/*.jpg"
        image_paths = glob.glob(search_pattern)
        
        if not image_paths:
            print(f"[{yyyymmdd}] 該当する画像が見つかりませんでした: {search_pattern}")
            continue
            
        image_paths.sort()
        
        for img_path in image_paths:
            filename = os.path.basename(img_path)
            print(f"処理中: {img_path}")
            
            match = time_pattern.search(filename)
            vs_date = match.group(1) if match else "unknown_date"

            # 移動先となる snapshots/done ディレクトリのパス（画像と同じ階層の done を想定）
            # もしプロジェクト直下に集約したい場合は、直接 "./snapshots/done" などに変更してください
            img_dir = os.path.dirname(img_path)
            done_dir = os.path.join(img_dir, "done")

            try:
                with Image.open(img_path) as img:
                    left = 1920 - 373
                    right = 1920 - 70
                    top = 1080 - 938
                    bottom = 908
                    cropped_img = img.crop((left, top, right, bottom))                
                
                # --- [ここからリトライ処理の組み込み] ---
                max_retries = 3      # 最大リトライ回数
                retry_delay = 40     # 最初のエラー時の待機秒数
                response = None

                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model=gemini_model,
                            contents=[cropped_img, prompt],
                            config={
                                "response_mime_type": "application/json",
                                "response_schema": OpponentParty,
                                "temperature": 0.1,
                            }
                        )
                        break  # 成功したらリトライ用のループを抜ける
                        
                    except Exception as api_err:
                        err_msg = str(api_err)
                        if "503" in err_msg or "UNAVAILABLE" in err_msg:
                            print(f"  [警告] サーバー混雑中 (503) を検知しました。")
                            if attempt < max_retries - 1:
                                print(f"  {retry_delay}秒後に再試行します... (試行回数: {attempt + 1}/{max_retries})")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                raise api_err
                        elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                            print(f" Code : 429 60秒後に再試行します...")
                            time.sleep(60)
                            raise api_err
                
                if response is None:
                    print(f"× エラー ({filename}): サーバーから応答が得られませんでした。スキップします。")
                    continue
                # --- [ここまでリトライ処理] ---
                
                # APIの出力（JSON文字列）をPython辞書にパース
                party_data = json.loads(response.text)
                
                result_record = {"vs_date": vs_date}
                result_record.update(party_data)
                results.append(result_record)

                # 解析がすべて成功した画像のみを done ディレクトリへ移動
                os.makedirs(done_dir, exist_ok=True)
                dest_path = os.path.join(done_dir, filename)
                shutil.move(img_path, dest_path)
                print(f"  -> 成功：画像を移動しました: {dest_path}")

            except Exception as e:
                print(f"エラー ({filename}): {e}")
            
            time.sleep(1)

    # 有効な処理結果が1件以上ある場合に出力ファイル名を組み立て
    if results:
        # 実行時のタイムスタンプ (yyyymmddhhmmss)
        current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix_date = first_valid_date if first_valid_date else "00000000"
        
        # 新しい出力ファイル名を作成 (例: 20260520_20260520132700_party_results.json)
        output_filename = f"{prefix_date}_{current_timestamp}_{args.output}"
    else:
        output_filename = args.output

    with open(f"./party_snap_json/{output_filename}", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\n処理完了: {len(results)}件のデータを {output_filename} に保存しました。")

if __name__ == "__main__":
    main()