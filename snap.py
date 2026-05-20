import sys
import os
import glob
import re
from datetime import datetime, timedelta
from pathlib import Path
import cv2

def get_target_date_str(input_arg=None):
    """引数から日付を解析し、yyyymmdd 形式の文字列を返す"""
    if not input_arg:
        today = datetime.now().strftime("%Y%m%d")
        print(f"引数が指定されていないため、今日の日付を使用します: {today}")
        return today

    date_formats = ["%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"]
    for fmt in date_formats:
        try:
            return datetime.strptime(input_arg, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
            
    print(f"エラー: 日付の形式が正しくありません: '{input_arg}'")
    print("入力例: 20260516, 2026-05-16")
    sys.exit(1)

def parse_filename_and_calc_time(basename):
    # 正規表現で構造を抽出
    # グループ1: 2026-05-11 18-39-56 (開始日時)
    # グループ2: 00.08.37.529 (動画内オフセット)
    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2})-(\d{2}\.\d{2}\.\d{2}\.\d{3})", basename)
    
    if not match:
        return None

    start_str = match.group(1)   # "2026-05-11 18-39-56"
    offset_str = match.group(2)  # "00.08.37.529"

    # 1. 開始時刻を変換
    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H-%M-%S")

    # 2. オフセット(hh.mm.ss.ms)をtimedeltaに変換
    h, m, s, ms = map(int, offset_str.split('.'))
    offset_delta = timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms)

    # 3. 実際の時刻 = 開始時刻 + オフセット + スクショ位置(2秒)
    final_time = start_dt + offset_delta + timedelta(seconds=2)
    
    return final_time.strftime("%Y%m%d_%H%M%S_%f")[:-3]

def capture_with_timestamp(video_dir: Path, output_dir: Path):

    # 指定されたディレクトリ配下の mp4 ファイルを取得
    video_files = list(video_dir.glob("*.mp4"))
    print(f"解析対象ファイル一覧: {[f.name for f in video_files]}")
    
    for video_path in video_files:
        basename = video_path.name
        time_part = parse_filename_and_calc_time(basename)
        
        if not time_part:
            print(f"スキップ (ファイル名不一致): {basename}")
            continue
            
        save_filename = f"{time_part}.jpg" 
        print(f"解析中: {basename}")

        try:
            # OpenCVで5秒後のフレームを抽出
            # ※ video_path は Path オブジェクトなので str() で文字列に変換して渡す
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # 5秒後の位置へシーク
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))
            ret, frame = cap.read()

            if ret:
                save_path = output_dir / save_filename
                cv2.imwrite(str(save_path), frame)
                print(f"保存完了: {save_path}")
            else:
                print(f"エラー: フレームの読み込みに失敗しました: {basename}")
            
            cap.release()

        except Exception as e:
            print(f"ファイル {basename} の解析に失敗しました: {e}")

if __name__ == "__main__":
    # 1. コマンドライン引数から日付（yyyymmdd）を取得
    input_arg = sys.argv[1] if len(sys.argv) > 1 else None
    target_date = get_target_date_str(input_arg)

    print(f"=== 処理開始 [対象日付: {target_date}] ===")
    
    # 2. ./data/*/yyyymmdd/videos にマッチするディレクトリを全検索
    data_dir = Path("./data")
    video_dirs = list(data_dir.glob(f"*/{target_date}/videos"))

    if not video_dirs:
        print(f"エラー: 対象の動画フォルダが見つかりません: ./data/*/{target_date}/videos")
        sys.exit(1)

    # 3. マッチした各ディレクトリに対してループ処理を実行
    for video_dir in video_dirs:
        # video_dir の 1つ上の階層（yyyymmdd）を取得し、同階層に screenshots フォルダを定義
        base_dir = video_dir.parent
        screenshot_dir = base_dir / "screenshots"

        # 保存先フォルダが存在しない場合は自動作成
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- フォルダ処理中: {video_dir} ---")
        try:
            capture_with_timestamp(video_dir, screenshot_dir)
        except Exception as e:
            print(f"エラー: {video_dir} の処理中にエラーが発生しました: {e}")
        
    print("\nすべての処理が完了しました！")