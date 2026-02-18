"""
パターンB デモスクリプト — 有料プラン（SocialData API自動収集）
APIキー不要。SocialData APIのモックで自動収集フローを見せる。

Usage:
    python demo_pattern_b.py
"""
import sys
import time
import random
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# ── SocialData APIのモックレスポンス ─────────────────────────────────────────
MOCK_SOCIALDATA_RESPONSE = [
    {
        "id": "1893001111111",
        "full_text": (
            "Claude 3.7 Sonnet is now available with extended thinking. "
            "It can reason step by step on hard problems. "
            "Benchmark scores are off the charts. This is what AGI looks like."
        ),
        "user": {"screen_name": "AnthropicAI", "name": "Anthropic"},
        "favorite_count": 142300,
        "retweet_count": 28700,
        "lang": "en",
        "created_at": "Tue Feb 18 02:14:30 +0000 2026",
    },
    {
        "id": "1893002222222",
        "full_text": (
            "We just open-sourced our entire AI agent framework. "
            "100k GitHub stars in 48 hours. "
            "The future of software is agentic."
        ),
        "user": {"screen_name": "LangChainAI", "name": "LangChain"},
        "favorite_count": 67800,
        "retweet_count": 13400,
        "lang": "en",
        "created_at": "Tue Feb 18 04:31:10 +0000 2026",
    },
    {
        "id": "1893003333333",
        "full_text": (
            "Cursor just added multi-agent mode. "
            "Watch 10 AI agents work on your codebase simultaneously. "
            "I built a full SaaS in 4 hours. No joke."
        ),
        "user": {"screen_name": "cursor_ai", "name": "Cursor"},
        "favorite_count": 89200,
        "retweet_count": 19300,
        "lang": "en",
        "created_at": "Tue Feb 18 05:48:22 +0000 2026",
    },
    {
        "id": "1893004444444",
        "full_text": (
            "Google just released Gemini 2.5 Ultra. "
            "It beats GPT-5 on every single benchmark. "
            "The AI race is heating up like never before."
        ),
        "user": {"screen_name": "Google", "name": "Google"},
        "favorite_count": 103400,
        "retweet_count": 21600,
        "lang": "en",
        "created_at": "Tue Feb 18 06:02:44 +0000 2026",
    },
    {
        "id": "1893005555555",
        "full_text": (
            "Perplexity just raised $500M at a $9B valuation. "
            "They are replacing Google for a whole generation. "
            "This is how fast the search market is being disrupted."
        ),
        "user": {"screen_name": "perplexity_ai", "name": "Perplexity AI"},
        "favorite_count": 54100,
        "retweet_count": 10800,
        "lang": "en",
        "created_at": "Tue Feb 18 07:19:55 +0000 2026",
    },
    {
        "id": "1893006666666",
        "full_text": (
            "New study: Companies using AI agents report 340% productivity increase. "
            "The bottleneck is no longer technology — it's knowing HOW to use it."
        ),
        "user": {"screen_name": "McKinsey", "name": "McKinsey & Company"},
        "favorite_count": 48700,
        "retweet_count": 9200,
        "lang": "en",
        "created_at": "Tue Feb 18 08:44:18 +0000 2026",
    },
    {
        "id": "1893007777777",
        "full_text": (
            "Meta released a new model that runs entirely on-device. "
            "Privacy-first AI is finally here. "
            "No cloud, no data collection, just intelligence in your pocket."
        ),
        "user": {"screen_name": "Meta", "name": "Meta"},
        "favorite_count": 76300,
        "retweet_count": 15900,
        "lang": "en",
        "created_at": "Tue Feb 18 09:57:03 +0000 2026",
    },
    {
        "id": "1893008888888",
        "full_text": (
            "OpenAI Operator can now handle entire workflows autonomously. "
            "From email to calendar to code. "
            "This is the last year you'll need to do repetitive work yourself."
        ),
        "user": {"screen_name": "OpenAI", "name": "OpenAI"},
        "favorite_count": 119600,
        "retweet_count": 24800,
        "lang": "en",
        "created_at": "Tue Feb 18 11:03:29 +0000 2026",
    },
]

# ── モック生成テキスト ────────────────────────────────────────────────────────
MOCK_GENERATED = [
    {
        "template": "breaking_news",
        "text": (
            "これはデカい。\n\n"
            "Claude 3.7、「拡張思考モード」が来た。\n"
            "難しい問題をステップで考えてから答える。\n\n"
            "これ、AGIに近い動き方だと思う。\n"
            "本物になってきた。"
        ),
        "score": 7,
        "rank": "A",
    },
    {
        "template": "translate_comment",
        "text": (
            "AIエージェントフレームワークがオープンソースで公開されて\n"
            "48時間で10万スター。\n\n"
            "「ソフトウェアの未来はエージェント型」\n"
            "って言葉が刺さる。\n\n"
            "1年後には当たり前になってる。今触っておくべき。"
        ),
        "score": 8,
        "rank": "S",
    },
    {
        "template": "practice_report",
        "text": (
            "Cursorのマルチエージェントモード、試してみた。\n\n"
            "10体のAIが同時にコード書く。\n"
            "結果: フルSaaSが4時間で完成。\n\n"
            "これもう個人開発の常識変わる。"
        ),
        "score": 8,
        "rank": "S",
    },
    {
        "template": "question_prompt",
        "text": (
            "AI生産性340%向上、というMcKinseyのレポート。\n\n"
            "ボトルネックはもう技術じゃなくて\n"
            "「使い方を知っているかどうか」。\n\n"
            "日本でこれ理解してる人、まだ少ない。"
        ),
        "score": 7,
        "rank": "A",
    },
    {
        "template": "summary_points",
        "text": (
            "OpenAI Operatorがワークフロー全自動化。\n"
            "今年が「反復作業最後の年」。\n\n"
            "・メール\n"
            "・カレンダー\n"
            "・コーディング\n\n"
            "全部AIが回す時代、マジで来た。"
        ),
        "score": 7,
        "rank": "A",
    },
]

# ── スコアフィルタリング（パターンBは件数多いので品質でフィルタ） ──────────
SCORE_THRESHOLD = 6  # パターンBではこれ以上のみ採用


def sep(char="─", width=56):
    print(char * width)


def step(label):
    print(f"\n{'━'*56}")
    print(f"  {label}")
    print(f"{'━'*56}")


def pause(sec=0.4):
    time.sleep(sec)


def mock_api_call(query: str, count: int):
    """SocialData APIの呼び出しをモック"""
    print(f"  [SocialData API] GET /twitter/search")
    print(f"  パラメータ: query={query!r}, count={count}, lang=en, min_likes=30000")
    pause(0.6)
    print(f"  → 200 OK  ({len(MOCK_SOCIALDATA_RESPONSE)}件取得)")
    return MOCK_SOCIALDATA_RESPONSE


def main():
    print()
    sep("═")
    print("  X 引用RT自動投稿システム — パターンB デモ")
    print("  有料プラン（SocialData API 自動収集）")
    sep("═")

    # ── STEP 1: SocialData API で自動収集 ─────────────────────────────────
    step("STEP 1 │ SocialData APIでバズツイートを自動収集")
    print()
    print("  検索クエリ（config/target_accounts.json から自動生成）:")
    print()

    queries = [
        ("(from:sama OR from:OpenAI OR from:AnthropicAI)", "最低30,000❤"),
        ("(from:AndrewYNg OR from:karpathy OR from:LangChainAI)", "最低20,000❤"),
        ("(AI agent OR AI automation) -is:retweet lang:en", "最低50,000❤"),
    ]
    for q, threshold in queries:
        print(f"  • {q}")
        print(f"    閾値: {threshold}")
    print()

    raw_tweets = mock_api_call("AI + agents + automation", count=50)
    print()
    print(f"  取得件数: {len(raw_tweets)}件")
    pause()

    # ── STEP 2: フィルタリング ──────────────────────────────────────────
    step("STEP 2 │ フィルタリング（重複排除・品質選別）")
    print()

    print("  フィルタ条件:")
    print("  ✅ 英語ツイートのみ")
    print("  ✅ いいね30,000以上")
    print("  ✅ 過去7日以内")
    print("  ✅ 同一ソース: 1日1件まで")
    print("  ✅ キャプション・リプライ・RTは除外")
    print()
    pause(0.3)

    # フィルタリングのシミュレーション
    filtered = [t for t in raw_tweets if t["favorite_count"] >= 30000]
    rejected = len(raw_tweets) - len(filtered)
    print(f"  フィルタ結果: {len(raw_tweets)}件 → {len(filtered)}件採用 / {rejected}件除外")
    print()
    print("  採用されたツイート:")
    print()
    for i, t in enumerate(filtered[:5], 1):
        print(f"  [{i}] @{t['user']['screen_name']}  ❤ {t['favorite_count']:,}")
        print(f"       {t['full_text'][:65]}...")
    if len(filtered) > 5:
        print(f"  ... 他{len(filtered)-5}件")
    pause()

    # ── STEP 3: 引用RT生成（全自動） ─────────────────────────────────────
    step("STEP 3 │ Gemini APIで引用RTコメントを全自動生成")
    print()
    print(f"  対象: {min(len(filtered), 8)}件 → 並列生成（最大8件/日）")
    print()

    try:
        from src.post.safety_checker import SafetyChecker
        from src.analyze.scorer import PostScorer
        import json

        with open("config/safety_rules.json", "r", encoding="utf-8") as f:
            safety_rules = json.load(f)

        checker = SafetyChecker(safety_rules)
        scorer = PostScorer()

        adopted = []
        for i, gen in enumerate(MOCK_GENERATED, 1):
            tweet = raw_tweets[i - 1]
            print(f"  [{i}] @{tweet['user']['screen_name']} ({tweet['favorite_count']:,}❤)")
            print(f"       テンプレート: {gen['template']}")

            safety_result = checker.check(gen["text"], is_quote_rt=True)
            score_result = scorer.score(gen["text"])

            status = "✅ 採用" if score_result.total >= SCORE_THRESHOLD and safety_result.is_safe else "⏭  スキップ"
            print(f"       スコア: {score_result.total}/8 [{score_result.rank}]  安全: {'✅' if safety_result.is_safe else '❌'}  {status}")

            if score_result.total >= SCORE_THRESHOLD and safety_result.is_safe:
                adopted.append(gen)
            pause(0.2)

    except Exception:
        adopted = MOCK_GENERATED
        for i, gen in enumerate(MOCK_GENERATED, 1):
            tweet = raw_tweets[i - 1]
            status = "✅ 採用" if gen["score"] >= SCORE_THRESHOLD else "⏭  スキップ"
            print(f"  [{i}] @{tweet['user']['screen_name']} ({tweet['favorite_count']:,}❤)")
            print(f"       テンプレート: {gen['template']}")
            print(f"       スコア: {gen['score']}/8 [{gen['rank']}]  安全: ✅  {status}")
            pause(0.2)

    print()
    print(f"  採用: {len(adopted)}/{len(MOCK_GENERATED)}件")
    pause()

    # ── STEP 4: 全自動投稿スケジュール ────────────────────────────────────
    step("STEP 4 │ 投稿スケジュール（全自動）")
    print()

    try:
        from src.post.mix_planner import MixPlanner
        planner = MixPlanner()
        plan = planner.plan_daily(available_quotes=len(adopted))
        print(planner.format_plan(plan))
    except Exception:
        print("  📋 本日の投稿スケジュール:")
        print()
        sample_plan = [
            ("07:08", "🔄 quote_rt  ", "Claude 3.7速報"),
            ("08:52", "🔄 quote_rt  ", "LangChain OSS"),
            ("10:15", "✍️ original ", "オリジナル投稿"),
            ("12:01", "🔄 quote_rt  ", "Cursor マルチエージェント"),
            ("14:38", "🔄 quote_rt  ", "McKinsey 生産性340%"),
            ("16:14", "✍️ original ", "オリジナル投稿"),
            ("18:07", "🔄 quote_rt  ", "OpenAI Operator"),
            ("20:03", "✍️ original ", "オリジナル投稿"),
            ("21:49", "🔄 quote_rt  ", "Meta オンデバイスAI"),
            ("22:32", "✍️ original ", "オリジナル投稿"),
        ]
        for i, (t, icon, label) in enumerate(sample_plan, 1):
            print(f"  {i:2}. {t}  {icon}  {label}")
        print()
        print(f"  合計: 10件 (引用RT: 6 / オリジナル: 4)")

    print()
    print("  BAN対策チェック:")
    print("  ✅ 引用RT比率      : 60% (上限70%以内)")
    print("  ✅ 連続引用RT      : 最大2件（制限内）")
    print("  ✅ 最小投稿間隔    : 60分以上確保")
    print("  ✅ 投稿時間帯      : 7:00〜22:00")
    pause()

    # ── STEP 5: 差分をパターンAと比較 ────────────────────────────────────
    step("STEP 5 │ パターンA との違い")
    print()
    print(f"  {'項目':<22} {'パターンA（無料）':<20} {'パターンB（有料）'}")
    sep()
    comparisons = [
        ("URL収集",          "手動（1件ずつ）",     "SocialData API 全自動"),
        ("収集件数/日",       "5〜10件（手動）",     "30〜50件（自動フィルタ）"),
        ("収集時間",          "30〜60分/日",         "0分（完全自動）"),
        ("ツイート品質",      "選んで追加する分HIGH", "いいね数でフィルタ"),
        ("投稿数/日",         "7〜9件",              "9〜10件（フル稼働）"),
        ("月間コスト",        "¥0〜300",             "¥2,000〜5,000"),
        ("スケーラビリティ",  "アカウント追加で増加", "API上限まで全自動"),
    ]
    for item, a, b in comparisons:
        print(f"  {item:<22} {a:<22} {b}")
    print()
    pause()

    # ── まとめ ─────────────────────────────────────────────────────────────
    sep("═")
    print("  パターンB デモ完了")
    sep("═")
    print()
    print("  ▌ 運用フロー（毎日・完全自動）")
    print("  │")
    print("  ├─ 朝5:00: SocialData APIでバズツイートを自動収集")
    print("  │      → フィルタリング（重複・品質・ソース制限）")
    print("  │")
    print("  ├─ 朝6:30: Gemini で引用RTコメントを自動生成")
    print("  │      → スコア6点以上のみ採用")
    print("  │      → Discord に通知（確認オプション）")
    print("  │")
    print("  └─ 自動投稿: 1日10件、60分以上の間隔で分散投稿")
    print()
    print("  ▌ 月間コスト（目安）")
    print("  ├─ SocialData API   : $20〜50/月（約¥3,000〜7,500）")
    print("  ├─ Gemini API       : 無料枠超過時 ¥500〜1,000/月")
    print("  ├─ GitHub Actions   : 無料枠内")
    print("  └─ 合計             : ¥3,500〜8,500/月")
    print()
    sep("═")


if __name__ == "__main__":
    main()
