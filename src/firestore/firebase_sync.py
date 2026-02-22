"""
X Auto Post System — Firestore → バックエンド同期

ダッシュボード（Firebase Hosting）で行われた操作を
バックエンドのJSONファイルに反映する同期パイプライン:
  - queue_decisions → QueueManager (approve / skip_with_reason)
  - selection_preferences → config/selection_preferences.json
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import PROJECT_ROOT

JST = ZoneInfo("Asia/Tokyo")

PREFS_PATH = PROJECT_ROOT / "config" / "selection_preferences.json"


def _parse_csv(val: str) -> list[str]:
    """CSV文字列をリストに変換（空白トリム）"""
    return [v.strip() for v in val.split(",") if v.strip()] if val else []


def map_preferences_to_local(raw: dict, local_prefs: dict) -> list[str]:
    """
    ダッシュボードから取得したフラットなプリファレンスデータを
    ローカルJSON構造にマッピングする。

    queue_sync.py の sync_preferences() と同じ変換ロジック。

    Args:
        raw: Firestore/Sheetsから取得したフラットデータ
        local_prefs: 既存のローカルプリファレンス（mutateされる）

    Returns:
        更新されたキーのリスト
    """
    updated_keys = []

    # weekly_focus
    if raw.get("weekly_focus"):
        wf = local_prefs.setdefault("weekly_focus", {})
        wf["directive"] = raw["weekly_focus"]
        updated_keys.append("weekly_focus")
    if raw.get("focus_keywords"):
        wf = local_prefs.setdefault("weekly_focus", {})
        wf["focus_keywords"] = _parse_csv(raw["focus_keywords"])
        updated_keys.append("focus_keywords")
    if raw.get("focus_accounts"):
        wf = local_prefs.setdefault("weekly_focus", {})
        wf["focus_accounts"] = _parse_csv(raw["focus_accounts"])
        updated_keys.append("focus_accounts")

    # topic_preferences
    if raw.get("preferred_topics"):
        tp = local_prefs.setdefault("topic_preferences", {})
        tp["preferred"] = _parse_csv(raw["preferred_topics"])
        updated_keys.append("preferred_topics")
    if raw.get("avoid_topics"):
        tp = local_prefs.setdefault("topic_preferences", {})
        tp["avoid"] = _parse_csv(raw["avoid_topics"])
        updated_keys.append("avoid_topics")

    # account_overrides
    if raw.get("boosted_accounts"):
        ao = local_prefs.setdefault("account_overrides", {})
        ao["boosted"] = _parse_csv(raw["boosted_accounts"])
        updated_keys.append("boosted_accounts")
    if raw.get("blocked_accounts"):
        ao = local_prefs.setdefault("account_overrides", {})
        ao["blocked"] = _parse_csv(raw["blocked_accounts"])
        updated_keys.append("blocked_accounts")

    # threshold_overrides
    to = local_prefs.setdefault("threshold_overrides", {})
    if raw.get("min_likes_override"):
        try:
            to["min_likes"] = int(raw["min_likes_override"])
            updated_keys.append("min_likes_override")
        except ValueError:
            pass
    if raw.get("max_age_hours_override"):
        try:
            to["max_age_hours"] = int(raw["max_age_hours_override"])
            updated_keys.append("max_age_hours_override")
        except ValueError:
            pass
    if raw.get("max_tweets_override"):
        try:
            to["max_tweets"] = int(raw["max_tweets_override"])
            updated_keys.append("max_tweets_override")
        except ValueError:
            pass

    # extra_keywords → keyword_weights に追加
    if raw.get("extra_keywords"):
        kw = local_prefs.setdefault("keyword_weights", {})
        for keyword in _parse_csv(raw["extra_keywords"]):
            if keyword not in kw:
                kw[keyword] = 2.0  # 新規キーワードはweight 2.0
                updated_keys.append(f"keyword:{keyword}")

    # prompt_overrides — ダッシュボードからの引用RTプロンプト設定
    prompt_fields = [
        "prompt_persona_name", "prompt_first_person", "prompt_position",
        "prompt_differentiator", "prompt_tone", "prompt_style_patterns",
        "prompt_ng_words", "prompt_custom_directive", "prompt_enabled_templates",
    ]
    po = local_prefs.setdefault("prompt_overrides", {})
    for field in prompt_fields:
        if raw.get(field):
            key = field.replace("prompt_", "", 1)  # prompt_tone → tone
            po[key] = raw[field]
            updated_keys.append(field)

    return updated_keys


class FirebaseSync:
    """Firestore → ローカルJSON同期"""

    def __init__(self, firestore_client, queue_manager=None):
        """
        Args:
            firestore_client: FirestoreClient インスタンス
            queue_manager: QueueManager インスタンス（省略時は自動生成）
        """
        self.fc = firestore_client
        self._queue = queue_manager

    def _get_queue(self):
        """QueueManagerの遅延初期化"""
        if self._queue is None:
            from src.collect.queue_manager import QueueManager
            self._queue = QueueManager()
        return self._queue

    def sync_queue_decisions(self, uid: str = "") -> dict:
        """
        Firestore users/{uid}/queue_decisions → QueueManager に反映

        ダッシュボードからの承認/スキップ操作をローカルキューに適用し、
        処理済みの決定をFirestoreから削除する。

        Args:
            uid: 特定ユーザーのみ同期する場合に指定。空の場合は全ユーザー。

        Returns:
            {"approved": int, "skipped": int, "not_found": int, "errors": list}
        """
        if uid:
            decisions = self.fc.get_queue_decisions(uid=uid)
        else:
            decisions = self.fc.get_queue_decisions()  # 全ユーザー

        if not decisions:
            return {"approved": 0, "skipped": 0, "not_found": 0, "errors": []}

        queue = self._get_queue()
        result = {
            "approved": 0,
            "skipped": 0,
            "not_found": 0,
            "errors": [],
        }
        # UID別に処理済みIDを追跡
        processed_by_uid: dict[str, list[str]] = {}

        for decision in decisions:
            tweet_id = decision.get("tweet_id", "")
            action = decision.get("action", "")
            dec_uid = decision.get("uid", uid)

            if not tweet_id or not action:
                result["errors"].append(f"無効な決定データ: {decision}")
                continue

            try:
                if action == "approve":
                    if queue.approve(tweet_id):
                        result["approved"] += 1
                        processed_by_uid.setdefault(dec_uid, []).append(tweet_id)
                    else:
                        result["not_found"] += 1

                elif action == "skip":
                    skip_reason = decision.get("skip_reason", "")
                    if queue.skip_with_reason(tweet_id, reason=skip_reason):
                        result["skipped"] += 1
                        processed_by_uid.setdefault(dec_uid, []).append(tweet_id)
                    else:
                        result["not_found"] += 1

                else:
                    result["errors"].append(f"不明なアクション: {action} (tweet: {tweet_id})")

            except Exception as e:
                result["errors"].append(f"処理エラー ({tweet_id}): {e}")

        # 処理済みの決定をFirestoreから削除（UID別）
        for dec_uid, tweet_ids in processed_by_uid.items():
            if tweet_ids and dec_uid:
                try:
                    self.fc.mark_decisions_processed(tweet_ids, uid=dec_uid)
                except Exception as e:
                    result["errors"].append(f"Firestore削除エラー (uid={dec_uid}): {e}")

        return result

    def sync_selection_preferences(self, uid: str) -> dict:
        """
        Firestore selection_preferences/{uid} → config/selection_preferences.json

        ダッシュボードからの設定変更をローカルJSONに反映する。

        Args:
            uid: Firebase Auth UID

        Returns:
            {"updated_keys": list[str], "unchanged": int}
        """
        raw = self.fc.get_selection_preferences(uid)
        if not raw:
            return {"updated_keys": [], "unchanged": 0}

        # 既存プリファレンス読み込み
        try:
            with open(PREFS_PATH, "r", encoding="utf-8") as f:
                local_prefs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            local_prefs = {}

        # フィールドマッピング（共通ロジック）
        updated_keys = map_preferences_to_local(raw, local_prefs)

        # 更新日時
        if updated_keys:
            local_prefs["updated_at"] = datetime.now(JST).isoformat()[:10]
            local_prefs["updated_by"] = "firebase_sync"

        # 保存
        with open(PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(local_prefs, f, ensure_ascii=False, indent=2)

        return {
            "updated_keys": updated_keys,
            "unchanged": len(raw) - len(updated_keys),
        }
