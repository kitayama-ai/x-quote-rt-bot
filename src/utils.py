"""
X Auto Post System — 共通ユーティリティ

リトライ機構、アトミックファイル操作など。
"""
import json
import shutil
import time
from pathlib import Path


def retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 2.0, label: str = ""):
    """
    指数バックオフ付きリトライ

    Args:
        fn: 実行する関数（引数なし）
        max_retries: 最大リトライ回数
        base_delay: 初回待機秒数
        label: ログ用ラベル

    Returns:
        fn() の戻り値

    Raises:
        最後の試行で発生した例外
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                print(f"  ⚠️ {label}リトライ {attempt + 1}/{max_retries} ({delay:.0f}秒後): {e}")
                time.sleep(delay)
            else:
                print(f"  ❌ {label}全{max_retries}回リトライ失敗: {e}")
    raise last_error


def safe_json_load(path: Path) -> list | dict:
    """
    安全なJSON読み込み（破損時はバックアップから復元）

    Args:
        path: JSONファイルのパス

    Returns:
        パースされたJSONデータ
    """
    backup_path = path.with_suffix(".json.bak")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  ⚠️ JSON破損検出: {path.name} — {e}")
        # バックアップから復元を試みる
        if backup_path.exists():
            print(f"  🔄 バックアップから復元: {backup_path.name}")
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 復元成功 → 本ファイルを上書き
                atomic_json_save(path, data)
                return data
            except Exception:
                pass
        # バックアップもなし → 空リストで初期化
        print(f"  🆕 空データで再初期化: {path.name}")
        atomic_json_save(path, [])
        return []
    except FileNotFoundError:
        return []


def atomic_json_save(path: Path, data: list | dict):
    """
    アトミックなJSON書き込み（中断時の破損防止）

    1. 一時ファイルに書き込み
    2. 既存ファイルをバックアップ
    3. 一時ファイルをリネーム

    Args:
        path: 保存先パス
        data: 保存するデータ
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    backup_path = path.with_suffix(".json.bak")

    # 1. 一時ファイルに書き込み
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 2. 既存ファイルをバックアップ
    if path.exists():
        shutil.copy2(path, backup_path)

    # 3. 一時ファイルを本ファイルにリネーム（アトミック）
    tmp_path.replace(path)
