import argparse
import configparser
import re
import sqlite3
import json
import os
import sys
import glob
import subprocess
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
VALID_RANKS = ["mo", "s", "h", "m"]
RANK_LABELS = {"mo": "モンスターボール", "s": "スーパーボール", "h": "ハイパーボール", "m": "マスターボール"}
SEP_HEAVY   = "═" * 62
SEP_LIGHT   = "─" * 62
RESULT_MAP  = {"w": "WIN", "l": "LOSS"}


# ─────────────────────────────────────────────────────────────────────────────
# 設定ファイル（config.ini / configparser）
# ─────────────────────────────────────────────────────────────────────────────
def load_config(config_path: str) -> configparser.ConfigParser:
    path = Path(config_path)
    if not path.exists():
        print(f"[ERROR] 設定ファイルが見つかりません: {config_path}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")

    required: dict[str, list[str]] = {
        "spreadsheet": ["id", "credentials",
                        "battle_result_sheet", "vs_party_sheet",
                        "my_party_sheet", "season_sheet"],
        "data"        : ["data_dir", "sqlite", "party_json"],
    }
    for section, keys in required.items():
        if section not in config:
            print(f"[ERROR] config.ini に [{section}] セクションがありません")
            sys.exit(1)
        for key in keys:
            if key not in config[section]:
                print(f"[ERROR] config.ini の [{section}] に '{key}' がありません")
                sys.exit(1)

    return config


# ─────────────────────────────────────────────────────────────────────────────
# ファイル名パース
# ─────────────────────────────────────────────────────────────────────────────
def parse_filename_and_calc_time(basename: str) -> str | None:
    """
    ファイル名から vs_datetime を抽出する。
    例: "2026-05-11 18-39-56-00.08.37.529" → "20260511_184933"
    """
    match = re.match(
        r"(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2})-(\d{2}\.\d{2}\.\d{2}\.\d{3})",
        basename,
    )
    if not match:
        return None
    start_str  = match.group(1)
    offset_str = match.group(2)

    start_dt     = datetime.strptime(start_str, "%Y-%m-%d %H-%M-%S")
    h, m, s, ms  = map(int, offset_str.split("."))
    offset_delta = timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms)
    final_time   = start_dt + offset_delta + timedelta(seconds=2)
    return final_time.strftime("%Y%m%d_%H%M%S")


# ─────────────────────────────────────────────────────────────────────────────
# 引数・日付パース
# ─────────────────────────────────────────────────────────────────────────────
def parse_date_arg(date_str: str) -> datetime:
    for fmt in ["%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"日付フォーマットが不正です: '{date_str}'\n"
        "対応形式: YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD"
    )


def get_current_season(df: pd.DataFrame, date_str: datetime) -> str:
    df.columns = df.columns.str.strip()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"]   = pd.to_datetime(df["end_date"])
    target_date = pd.to_datetime(date_str, format="%Y%m%d")
    condition   = (df["start_date"] <= target_date) & (target_date <= df["end_date"])
    filtered_df = df[condition]
    return next(iter(filtered_df.sort_values(by="end_date", ascending=False)["name"]), None)


# ─────────────────────────────────────────────────────────────────────────────
# SQLite
# ─────────────────────────────────────────────────────────────────────────────
def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS battle_result (
            vs_datetime  TEXT PRIMARY KEY,
            rank         TEXT,
            result       TEXT,
            my_party_id  TEXT,
            my_select1   TEXT,
            my_select2   TEXT,
            my_select3   TEXT,
            vs_select1   TEXT,
            vs_select2   TEXT,
            vs_select3   TEXT,
            season       TEXT,
            vs_date      TEXT
        );
        CREATE TABLE IF NOT EXISTS my_party_pokemon (
            party_id     TEXT,
            party_num    INTEGER,
            item_name    TEXT,
            pokemon_name TEXT,
            personality  TEXT,
            H TEXT, A TEXT, B TEXT, C TEXT, D TEXT, S TEXT,
            w1 TEXT, w2 TEXT, w3 TEXT, w4 TEXT
        );
        CREATE TABLE IF NOT EXISTS vs_party_pokemon (
            vs_datetime  TEXT,
            party_num    INTEGER,
            item_name    TEXT,
            pokemon_name TEXT,
            PRIMARY KEY (vs_datetime, party_num)
        );
    """)
    conn.commit()


def get_existing_vs_datetimes(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT vs_datetime FROM battle_result").fetchall()
    return {r[0] for r in rows}


def party_id_exists(conn: sqlite3.Connection, party_id: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM my_party_pokemon WHERE party_id = ?", (party_id,)
    ).fetchone()
    return row[0] == 6


def get_my_pokemon(
    conn: sqlite3.Connection, party_id: str, indices: list[int]
) -> list[str | None]:
    result = []
    for idx in indices:
        row = conn.execute(
            "SELECT pokemon_name FROM my_party_pokemon WHERE party_id=? AND party_num=?",
            (party_id, idx),
        ).fetchone()
        result.append(row[0] if row else f"[party_num={idx} 未登録]")
    return result


def save_records(
    conn: sqlite3.Connection,
    records: list[dict],
) -> None:
    """
    battle_result と vs_party_pokemon を一括保存する。
    vs_datetime が PRIMARY KEY なので同じ vs_datetime は上書きされる。
    """
    conn.executemany(
        """
        INSERT OR REPLACE INTO battle_result
            (vs_datetime, rank, result, my_party_id,
             my_select1, my_select2, my_select3,
             vs_select1, vs_select2, vs_select3,
             season, vs_date)
        VALUES
            (:vs_datetime, :rank, :result, :my_party_id,
             :my_select1, :my_select2, :my_select3,
             :vs_select1, :vs_select2, :vs_select3,
             :season, :vs_date)
        """,
        records,
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# スプレッドシート接続・読み書き（gspread）
# ─────────────────────────────────────────────────────────────────────────────
def _get_gspread():
    """gspread をインポートして返す。未インストールの場合はエラー終了。"""
    try:
        import gspread
        return gspread
    except ImportError:
        print("[ERROR] gspread がインストールされていません。")
        print("        pip install gspread でインストールしてください。")
        sys.exit(1)

def get_gspread_client(credentials_path: str):
    """
    credentials.json からサービスアカウントで認証し、
    gspread クライアントを返す。起動時に1回だけ呼ぶ。
    """
    gspread = _get_gspread()
    try:
        gc = gspread.service_account(filename=credentials_path)
        return gc
    except Exception as e:
        print(f"[ERROR] gspread 認証に失敗しました: {e}")
        sys.exit(1)


def read_sheet_as_df(
    gc,
    spreadsheet_id: str,
    sheet_name: str,
    dtype=str,
) -> pd.DataFrame:
    """
    スプレッドシートの1シートを DataFrame で返す。
    非公開シートも gspread 経由で読み取れる。

    Parameters
    ----------
    gc              : get_gspread_client() で取得したクライアント
    spreadsheet_id  : スプレッドシートID
    sheet_name      : シート名
    dtype           : 全列に適用する型（None で変換しない）
    """
    gspread = _get_gspread()
    try:
        ws   = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
        data = ws.get_all_records()
        df   = pd.DataFrame(data)
        if dtype is not None and not df.empty:
            df = df.astype(dtype)
        return df
    except gspread.exceptions.WorksheetNotFound:
        print(f"  [WARNING] シート '{sheet_name}' が見つかりません。空のDataFrameを返します。")
        return pd.DataFrame()
    except Exception as e:
        print(f"  [ERROR] シート '{sheet_name}' の読み込みに失敗しました: {e}")
        sys.exit(1)


def sync_to_spreadsheet(
    conn: sqlite3.Connection,
    gc,
    spreadsheet_id: str,
    table_sheet_map: dict[str, str],
) -> None:
    """
    SQLite の各テーブルをスプレッドシートの同名シートに truncate して全件書き込む。

    Parameters
    ----------
    conn            : SQLite 接続
    gc              : get_gspread_client() で取得したクライアント
    spreadsheet_id  : スプレッドシートID
    table_sheet_map : {テーブル名: シート名}
                      例: {"battle_result": "battle_result",
                           "vs_party_pokemon": "vs_party_pokemon"}
    """
    gspread = _get_gspread()

    try:
        sh = gc.open_by_key(spreadsheet_id)
    except Exception as e:
        print(f"  [ERROR] スプレッドシートへの接続に失敗しました: {e}")
        return

    for table_name, sheet_name in table_sheet_map.items():
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

            # シートを取得（存在しなければ新規作成）
            try:
                ws = sh.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet(title=sheet_name, rows=1, cols=len(df.columns))

            # truncate → ヘッダー + 全レコードを書き込む
            ws.clear()
            if df.empty:
                ws.update(range_name="A1",values=[df.columns.tolist()])
            else:
                data = [df.columns.tolist()] + df.fillna("").values.tolist()
                ws.update(range_name="A1", values=data)

            print(f"  ✓ SS同期完了 [{sheet_name}]: {len(df)} 件")

        except Exception as e:
            print(f"  [ERROR] シート '{sheet_name}' の同期に失敗しました: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# JSON スナップ
# ─────────────────────────────────────────────────────────────────────────────
def import_json_snaps_to_db(json_dir: str, conn: sqlite3.Connection) -> int:
    """
    json_dir 配下の全 JSON を読み込み、vs_party_pokemon テーブルに保存する。
    - vs_datetime が既存の場合はスキップ（重複保存なし）
    - 保存に成功した JSON ファイルは <json_dir>/done/ へ移動する
    - 保存件数を返す
    """
    import shutil
    if not os.path.isdir(json_dir):
        print(f"  [WARNING] JSONディレクトリが見つかりません: {json_dir}")
        return 0

    done_dir = os.path.join(json_dir, "done")
    os.makedirs(done_dir, exist_ok=True)

    saved_total = 0

    for jf in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [WARNING] JSON読み込み失敗: {jf} ({e})")
            continue

        entries = data if isinstance(data, list) else [data]
        saved_in_file = 0

        for entry in entries:
            vs_datetime = entry.get("vs_date")
            if not vs_datetime:
                continue

            # 既存チェック: vs_datetime が既に vs_party_pokemon にある場合はスキップ
            exists = conn.execute(
                "SELECT 1 FROM vs_party_pokemon WHERE vs_datetime = ? LIMIT 1",
                (vs_datetime,),
            ).fetchone()
            if exists:
                continue

            # pokemon_1〜6 を vs_party_pokemon テーブルへ保存
            rows = []
            for party_num in range(1, 7):
                rows.append({
                    "vs_datetime" : vs_datetime,
                    "party_num"   : party_num,
                    "item_name"   : None,
                    "pokemon_name": entry.get(f"pokemon_{party_num}"),
                })
            conn.executemany(
                """
                INSERT OR IGNORE INTO vs_party_pokemon
                    (vs_datetime, party_num, item_name, pokemon_name)
                VALUES
                    (:vs_datetime, :party_num, :item_name, :pokemon_name)
                """,
                rows,
            )
            conn.commit()
            saved_in_file += 1

        saved_total += saved_in_file

        # ファイル内の全エントリが DB に保存済み（または今回保存した）なら done へ移動
        all_stored = all(
            conn.execute(
                "SELECT 1 FROM vs_party_pokemon WHERE vs_datetime = ? LIMIT 1",
                (e.get("vs_date"),),
            ).fetchone()
            for e in entries if e.get("vs_date")
        )
        if all_stored:
            dest = os.path.join(done_dir, os.path.basename(jf))
            shutil.move(jf, dest)
            print(f"  -> done へ移動: {os.path.basename(jf)}  ({saved_in_file} 件新規保存)")
        else:
            print(f"  -> 一部スキップ（未処理エントリあり）: {os.path.basename(jf)}")

    return saved_total


def get_vs_from_db(
    conn: sqlite3.Connection, vs_datetime: str, indices: list[int]
) -> tuple[list[str | None], dict]:
    """
    vs_party_pokemon テーブルから vs_datetime に対応するパーティを取得し、
    indices で指定された party_num のポケモン名リストと全パーティ dict を返す。
    """
    rows = conn.execute(
        "SELECT party_num, pokemon_name FROM vs_party_pokemon "
        "WHERE vs_datetime = ? ORDER BY party_num",
        (vs_datetime,),
    ).fetchall()
    entry = {f"pokemon_{r[0]}": r[1] for r in rows}
    print(entry)
    pokemons = [entry.get(f"pokemon_{i}") for i in indices]
    return pokemons, entry


def make_vs_party_pokemon(entry: dict) -> str:
    return "/".join(entry.get(f"pokemon_{i}", "") for i in range(1, 7))


# ─────────────────────────────────────────────────────────────────────────────
# MP4 ファイル取得
# ─────────────────────────────────────────────────────────────────────────────
def get_mp4_files(data_dir: str, date: datetime) -> list[Path]:
    target_date_str = date.strftime("%Y%m%d")
    base            = Path(data_dir)
    video_dirs      = list(base.glob(f"*/{target_date_str}/videos"))

    if not video_dirs:
        return []

    mp4_files: list[Path] = []
    for video_dir in video_dirs:
        mp4_files.extend(video_dir.glob("*.mp4"))

    return sorted(mp4_files)


# ─────────────────────────────────────────────────────────────────────────────
# 動画再生（Windows 専用・非ブロッキング）
# ─────────────────────────────────────────────────────────────────────────────
def open_video_windows(filepath) -> None:
    try:
        os.startfile(os.path.abspath(filepath))   # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen(
            ["powershell", "-Command", f'Start-Process "{os.path.abspath(filepath)}"'],
            creationflags=subprocess.CREATE_NO_WINDOW,   # type: ignore[attr-defined]
        )
    except Exception as e:
        print(f"  [WARNING] 動画を開けませんでした: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CUI 入力ヘルパー
# ─────────────────────────────────────────────────────────────────────────────
def prompt(text: str, validator=None, error_msg: str = "入力が不正です。") -> str:
    while True:
        try:
            val = input(text).strip()
        except KeyboardInterrupt:
            print("\n  中断しました。")
            sys.exit(0)
        if validator is None or validator(val):
            return val
        print(f"  ✗ {error_msg}")


def prompt_result() -> str:
    val = prompt(
        "  対戦結果    (w=WIN / l=LOSS) > ",
        lambda v: v.lower() in ["w", "l"],
        "w か l を入力してください",
    ).lower()
    return RESULT_MAP[val]


def prompt_rank() -> str:
    opts = "  ".join(f"{k}={v}" for k, v in RANK_LABELS.items())
    val  = prompt(
        f"  ランク帯    ({opts}) > ",
        lambda v: v.lower() in VALID_RANKS,
        f"次のいずれかを入力してください: {' / '.join(VALID_RANKS)}",
    ).lower()
    return RANK_LABELS[val]


def prompt_party_id(conn: sqlite3.Connection) -> str:
    while True:
        val = input("  自分のパーティID > ").strip()
        if party_id_exists(conn, val):
            return val
        print(f"  ✗ パーティID '{val}' はDBに存在しないかメンバーが不足しています")


def prompt_my_selection(
    label: str,
    conn: sqlite3.Connection,
    party_id: str,
) -> list[int]:
    """自分の選出: カンマ区切り3つ(1-6)。入力前にパーティのポケモン名一覧を表示する"""
    # パーティメンバーを party_num 順に取得して表示
    rows = conn.execute(
        "SELECT party_num, pokemon_name FROM my_party_pokemon "
        "WHERE party_id = ? ORDER BY party_num",
        (party_id,),
    ).fetchall()
    print(f"  ─ 自分のパーティ ({party_id}) ─")
    for row in rows:
        print(f"    {row[0]}: {row[1]}")

    def validate(val: str) -> bool:
        parts = [p.strip() for p in val.split(",")]
        if len(parts) != 3:
            return False
        try:
            return all(1 <= int(p) <= 6 for p in parts)
        except ValueError:
            return False

    val = prompt(
        f"  {label} (例: 2,6,1) > ",
        validate,
        "1〜6 の数値をカンマ区切りで3つ入力してください（例: 2,6,1）",
    )
    return [int(p.strip()) for p in val.split(",")]


def prompt_vs_selection(
    label: str,
    conn: sqlite3.Connection,
    vs_datetime: str,
) -> list[int | None]:
    """相手の選出: カンマ区切り1〜3つ(1-6)、不足分は None で補完。
    入力前に SQLite の vs_party_pokemon から相手パーティのポケモン名一覧を表示する"""
    # SQLite から相手パーティを取得して表示
    rows = conn.execute(
        "SELECT party_num, pokemon_name FROM vs_party_pokemon "
        "WHERE vs_datetime = ? ORDER BY party_num",
        (vs_datetime,),
    ).fetchall()
    entry = {int(r[0]): r[1] for r in rows}
    print("  ─ 相手のパーティ ─")
    for i in range(1, 7):
        name = entry.get(i, "（不明）")
        print(f"    {i}: {name}")

    def validate(val: str) -> bool:
        parts = [p.strip() for p in val.split(",")]
        if len(parts) == 0:
            return False
        try:
            return all(1 <= int(p) <= 6 for p in parts)
        except ValueError:
            return False

    val     = prompt(
        f"  {label} (例: 2,6,1  ※1〜3つ) > ",
        validate,
        "1〜6 の数値をカンマ区切りで入力してください（例: 2,6,1）",
    )
    vp_list = [int(p.strip()) for p in val.split(",")]
    # 3個未満なら None で補完
    while len(vp_list) < 3:
        vp_list.append(None)
    return vp_list


def confirm_record(record: dict) -> bool:
    print()
    print(f"  ┌─ 入力内容確認 {'─'*44}")
    fields = [
        ("結果",          record["result"]),
        ("ランク",        record["rank"]),
        ("自分パーティID",record["my_party_id"]),
        ("自分選出",      f'{record["my_select1"]} / {record["my_select2"]} / {record["my_select3"]}'),
        ("相手選出",      f'{record["vs_select1"]} / {record["vs_select2"]} / {record["vs_select3"]}'),
        ("相手パーティ",  record["vs_party_pokemon"]),
        ("vs_datetime",   record["vs_datetime"]),
        ("シーズン",      record["season"]),
    ]
    for label, val in fields:
        print(f"  │  {label:<14}: {val}")
    print(f"  └{'─'*58}")
    ans = prompt(
        "  この内容で確定しますか？ (y=確定 / n=再入力) > ",
        lambda v: v.lower() in ["y", "n"],
        "y か n を入力してください",
    )
    return ans.lower() == "y"


# ─────────────────────────────────────────────────────────────────────────────
# 1ファイル分のデータ入力（再入力対応）
# ─────────────────────────────────────────────────────────────────────────────
def input_one_battle(
    conn: sqlite3.Connection,
    vs_datetime: str,
    target_season: str,
    fixed_rank: str | None,
) -> tuple[dict, list[dict]] | None:
    """
    動画1本分のデータを CUI で入力し、確認後に (battle_record, vs_party_records) を返す。
    's' でスキップ(None返却) / 確認で 'n' を選ぶと最初からやり直す。

    相手パーティは SQLite の vs_party_pokemon テーブルから取得する。
    vs_party_records は vs_datetime をキーとして vs_party_pokemon に保存する6行。
    """
    while True:
        print()
        skip_check = input("  [s=スキップ / Enter=入力開始] > ").strip().lower()
        if skip_check == "s":
            return None

        # ── ランク
        rank = fixed_rank if fixed_rank else prompt_rank()

        # ── 自分のパーティID
        my_party_id = prompt_party_id(conn)

        # ── 自分の選出（3つ必須）: パーティのポケモン名を表示してから入力
        my_indices = prompt_my_selection("自分の選出 (party_num)", conn, my_party_id)

        # ── 相手の選出（1〜3つ許容）: JSON スナップのポケモン名を表示してから入力
        vs_indices = prompt_vs_selection("相手の選出 (JSON pokemon番号)", conn, vs_datetime)

        # ── 対戦結果（相手の選出確認後に入力）
        result = prompt_result()

        # ── 自分のポケモン名を DB から取得
        my_pokemons = get_my_pokemon(conn, my_party_id, my_indices)
        my_select1, my_select2, my_select3 = my_pokemons

        # ── 相手ポケモンを DB から取得
        vs_pokemons, vs_entry = get_vs_from_db(conn, vs_datetime, vs_indices)
        vs_select1, vs_select2, vs_select3 = vs_pokemons

        if not vs_entry:
            print(f"  [WARNING] JSONスナップに vs_datetime={vs_datetime} のデータがありません")

        # ── vs_party_pokemon (pokemon_1〜6 スラッシュ結合、表示用)
        vs_party_pokemon = make_vs_party_pokemon(vs_entry)

        # ── vs_party_pokemon テーブル用レコード
        #    紐づけキーは vs_datetime（VSID / party_id 廃止）
        vs_party_records: list[dict] = []
        if vs_entry:
            for party_num in range(1, 7):
                vs_party_records.append({
                    "vs_datetime" : vs_datetime,
                    "party_num"   : party_num,
                    "pokemon_id"  : None,
                    "item_name"   : None,
                    "pokemon_name": vs_entry.get(f"pokemon_{party_num}"),
                })

        # ── battle_result レコード作成（VSID なし・vs_datetime が PK）
        record = {
            "vs_datetime" : vs_datetime,
            "rank"        : rank,
            "result"      : result,
            "my_party_id" : my_party_id,
            "my_select1"  : my_select1,
            "my_select2"  : my_select2,
            "my_select3"  : my_select3,
            "vs_select1"  : vs_select1,
            "vs_select2"  : vs_select2,
            "vs_select3"  : vs_select3,
            "season"      : target_season,
            "vs_date"     : vs_datetime[:8],
            # 確認画面表示用（DB保存列には含まれない）
            "vs_party_pokemon": vs_party_pokemon,
        }

        if confirm_record(record):
            # vs_party_pokemon は DB 保存列に不要なので除去してから返す
            record.pop("vs_party_pokemon")
            return record, vs_party_records

        print()
        print("  ↩ 最初から再入力します...")


# ─────────────────────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="ポケモン対戦動画を見ながらデータを記録するツール（Windows）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("date",  help="対象日付 (YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD)")
    parser.add_argument("--rank", "-r", choices=VALID_RANKS,
                        help="ランク帯。指定しない場合は動画ごとに確認")
    parser.add_argument("--config", "-c", default="config.ini",
                        help="設定ファイルのパス（デフォルト: config.ini）")
    parser.add_argument("--skip-existing", action="store_true",
                        help="DB に登録済みの vs_datetime をスキップする")
    args = parser.parse_args()

    # ── 設定ファイル読み込み ──────────────────────────────────────────────────
    config           = load_config(args.config)
    spreadsheet_info = config["spreadsheet"]
    spreadsheet_id   = spreadsheet_info["id"]
    credentials_path = spreadsheet_info["credentials"]

    data_info     = config["data"]
    data_dir      = data_info["data_dir"]
    db_path       = data_info["sqlite"]
    json_snap_dir = data_info["party_json"]

    # ── gspread クライアントを起動時に1回だけ作成 ────────────────────────────
    print("  スプレッドシートに接続中...")
    gc = get_gspread_client(credentials_path)
    print("  接続完了。")

    # ── 1. 日付パース & 対象ファイル抽出 ─────────────────────────────────────
    try:
        target_date = parse_date_arg(args.date)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    mp4_files = get_mp4_files(data_dir, target_date)
    if not mp4_files:
        print(
            f"[ERROR] {data_dir}/*/{target_date.strftime('%Y%m%d')}/videos に"
            " MP4 ファイルが見つかりません"
        )
        sys.exit(1)

    # ── 2. SQLite 初期化 & スプレッドシートから初期データ同期 ─────────────────
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    print("  スプレッドシートからデータを読み込み中...")
    battle_result_df = read_sheet_as_df(gc, spreadsheet_id, spreadsheet_info["battle_result_sheet"])
    battle_result_df.to_sql("battle_result", con=conn, if_exists="replace", index=False)
    print("  battle_result を更新しました。")

    my_party_df = read_sheet_as_df(gc, spreadsheet_id, spreadsheet_info["my_party_sheet"])
    my_party_df.to_sql("my_party_pokemon", con=conn, if_exists="replace", index=False)
    print("  my_party_pokemon を更新しました。")

    vs_party_df = read_sheet_as_df(gc, spreadsheet_id, spreadsheet_info["vs_party_sheet"])
    vs_party_df.to_sql("vs_party_pokemon", con=conn, if_exists="replace", index=False)
    print("  vs_party_pokemon を更新しました。")

    season_df     = read_sheet_as_df(gc, spreadsheet_id, spreadsheet_info["season_sheet"], dtype=None)
    target_season = get_current_season(season_df, target_date)

    # ── 3. JSON スナップを SQLite に取り込み（vs_party_pokemon に保存） ─────────
    print("  JSONスナップを読み込み中...")
    snap_saved = import_json_snaps_to_db(json_snap_dir, conn)
    print(f"  JSONスナップ: {snap_saved} 件 新規保存（done へ移動済み）")

    # 起動サマリー
    print()
    print(SEP_HEAVY)
    print(f"  設定ファイル    : {args.config}")
    print(f"  対象日付        : {target_date.strftime('%Y-%m-%d')}")
    print(f"  シーズン        : {target_season}")
    print(f"  動画ファイル数  : {len(mp4_files)} 件")
    print(f"  DB              : {db_path}")
    print(f"  JSONスナップ dir: {json_snap_dir}")
    print(f"  ランク          : {RANK_LABELS[args.rank] if args.rank else '都度入力'}")
    print(SEP_HEAVY)

    existing         = get_existing_vs_datetimes(conn) if args.skip_existing else set()
    records:          list[dict] = []
    all_vs_party_rec: list[dict] = []
    skipped:          list[str]  = []

    # ── 4〜14. 動画ごとのループ ───────────────────────────────────────────────
    for file_idx, mp4_path in enumerate(mp4_files):
        basename    = Path(mp4_path).stem
        vs_datetime = parse_filename_and_calc_time(basename)

        print()
        print(SEP_HEAVY)
        print(f"  [{file_idx + 1}/{len(mp4_files)}]  {basename}")

        if vs_datetime is None:
            print("  [SKIP] ファイル名から vs_datetime を抽出できませんでした")
            skipped.append(mp4_path)
            input("  Enter で次へ > ")
            continue

        print(f"  vs_datetime : {vs_datetime}")

        if args.skip_existing and vs_datetime in existing:
            print("  [SKIP] 既にDBに登録済みです")
            skipped.append(mp4_path)
            continue

        print(SEP_LIGHT)
        print("  ▶ 動画を開きます。動画を見ながら以下を入力してください。")
        print("    s + Enter でこの動画をスキップできます。")
        print(SEP_LIGHT)

        open_video_windows(mp4_path)

        result = input_one_battle(
            conn, vs_datetime, target_season, RANK_LABELS[args.rank]
        )

        if result is None:
            print("  → スキップしました")
            skipped.append(mp4_path)
            continue

        record, vs_party_recs = result
        records.append(record)
        all_vs_party_rec.extend(vs_party_recs)

        if file_idx < len(mp4_files) - 1:
            print()
            input("  現在の動画を閉じて、準備ができたら Enter を押してください > ")
        else:
            print()
            print("  全ての動画の入力が完了しました。")

    # ── 15. SQLite 保存 → スプレッドシートへ truncate 同期 ───────────────────
    print()
    print(SEP_HEAVY)
    if records:
        save_records(conn, records)
        print(f"  ✓ 対戦記録    : {len(records)} 件 → {db_path}")
        print(f"  ✓ 相手パーティ: {len(all_vs_party_rec)} 行")

        # 保存した2テーブルをスプレッドシートに truncate して同期
        print()
        print("  スプレッドシートへ同期中...")
        sync_to_spreadsheet(
            conn,
            gc             = gc,
            spreadsheet_id = spreadsheet_id,
            table_sheet_map = {
                "battle_result"   : "battle_result",
                "vs_party_pokemon": "vs_party_pokemon",
            },
        )
    else:
        print("  保存するデータがありません")

    if skipped:
        print(f"  スキップ: {len(skipped)} 件")
        for s in skipped:
            print(f"    {Path(s).name}")

    conn.close()
    print()
    print("  完了しました。")
    print(SEP_HEAVY)


if __name__ == "__main__":
    main()