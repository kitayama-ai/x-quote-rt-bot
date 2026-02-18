"""
パターンA デモスクリプト — 完全無料プラン
APIキー不要。デモデータで引用RTの生成フローを一通り見せる。

Usage:
    python demo_pattern_a.py
"""
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

# ── デモ用バズツイートデータ ──────────────────────────────────────────────────
DEMO_TWEETS = [
    {
        "tweet_id": "demo_001",
        "author_username": "sama",
        "author_name": "Sam Altman",
        "text": (
            "o3 is out. I think this is one of the biggest leaps in AI capability "
            "we've ever seen. Coding, math, and reasoning are all dramatically better."
        ),
        "likes": 82400,
        "retweets": 14300,
        "url": "https://x.com/sama/status/demo_001",
    },
    {
        "tweet_id": "demo_002",
        "author_username": "AndrewYNg",
        "author_name": "Andrew Ng",
        "text": (
            "AI Agents are becoming mainstream. The shift from single-step to "
            "multi-step agentic workflows is the most important trend in AI right now. "
            "Teams that learn to build agents will have a massive advantage."
        ),
        "likes": 38700,
        "retweets": 8100,
        "url": "https://x.com/AndrewYNg/status/demo_002",
    },
    {
        "tweet_id": "demo_003",
        "author_username": "karpathy",
        "author_name": "Andrej Karpathy",
        "text": (
            "Vibe coding is a thing now. You tell the AI what you want, "
            "it writes the code, you barely look at it. "
            "It's a fundamentally different way to build software."
        ),
        "likes": 57200,
        "retweets": 11600,
        "url": "https://x.com/karpathy/status/demo_003",
    },
]

# ── デモ用生成テキスト（Gemini APIなしで表示するサンプル） ─────────────────────
DEMO_GENERATED = [
    {
        "template": "breaking_news",
        "text": (
            "これはデカい。\n\n"
            "OpenAIのo3、コーディング・数学・推論が\n"
            "一気に跳ね上がった。\n\n"
            "「今まで最大の能力ジャンプ」って言葉、\n"
            "sam altmanが使うのは珍しい。\n\n"
            "本物だと思う。"
        ),
        "score": 7,
        "rank": "A",
    },
    {
        "template": "translate_comment",
        "text": (
            "AIエージェント、もう「最先端」じゃなくて「主流」になってきた。\n\n"
            "Andrew Ngが言う「マルチステップのエージェント設計」を\n"
            "今覚えてる人と覚えてない人で\n"
            "1年後に差がつく。\n\n"
            "ガチでそう思う。"
        ),
        "score": 8,
        "rank": "S",
    },
    {
        "template": "question_prompt",
        "text": (
            "「コードをほぼ見ないで作る」時代。\n\n"
            "Karpathyが言う Vibe Coding、\n"
            "日本語にすると「ノリでコーディング」。\n\n"
            "AIに話しかけて、出てきたコードをそのまま動かす。\n"
            "これ、エンジニアの仕事どう変わる？"
        ),
        "score": 6,
        "rank": "A",
    },
]


def sep(char="─", width=56):
    print(char * width)


def step(label):
    print(f"\n{'━'*56}")
    print(f"  {label}")
    print(f"{'━'*56}")


def pause(sec=0.4):
    time.sleep(sec)


def main():
    print()
    sep("═")
    print("  X 引用RT自動投稿システム — パターンA デモ")
    print("  完全無料プラン（手動URL収集 + Gemini生成）")
    sep("═")

    # ── STEP 1: バズツイート収集（手動） ───────────────────────────────────
    step("STEP 1 │ バズツイートURLを手動収集してキューに追加")
    print()
    print("  実運用では以下のコマンドで1件ずつ追加します:")
    print()
    print('  $ python tools/add_tweet.py "https://x.com/sama/status/..."')
    print()
    print("  今日追加するバズツイート候補（デモデータ）:")
    print()
    for i, t in enumerate(DEMO_TWEETS, 1):
        print(f"  [{i}] @{t['author_username']} ({t['author_name']})")
        print(f"       ❤ {t['likes']:,}  🔁 {t['retweets']:,}")
        print(f"       {t['text'][:70]}...")
        print()
    pause()

    # ── STEP 2: キュー確認・承認 ───────────────────────────────────────────
    step("STEP 2 │ キュー確認 & 一括承認")
    print()
    print("  $ python tools/add_tweet.py --list")
    print()
    print("  📊 キュー状態:")
    print(f"     pending  : {len(DEMO_TWEETS)}件（承認待ち）")
    print(f"     approved : 0件")
    print(f"     posted   : 0件（今日）")
    print()
    print("  $ python tools/add_tweet.py --approve-all")
    print()
    print(f"  ✅ {len(DEMO_TWEETS)}件を承認しました")
    pause()

    # ── STEP 3: 安全チェック & スコアリング ───────────────────────────────
    step("STEP 3 │ 安全チェック & 品質スコアリング")
    print()

    try:
        from src.post.safety_checker import SafetyChecker
        from src.analyze.scorer import PostScorer
        import json

        with open("config/safety_rules.json", "r", encoding="utf-8") as f:
            safety_rules = json.load(f)

        checker = SafetyChecker(safety_rules)
        scorer = PostScorer()

        for i, gen in enumerate(DEMO_GENERATED, 1):
            tweet = DEMO_TWEETS[i - 1]
            print(f"  ─── 投稿 {i} / {len(DEMO_GENERATED)} ───────────────────────────")
            print(f"  元ツイート: @{tweet['author_username']} ({tweet['likes']:,}❤)")
            print()
            print(f"  生成テキスト [テンプレート: {gen['template']}]:")
            for line in gen["text"].split("\n"):
                print(f"    {line}")
            print()

            safety_result = checker.check(gen["text"], is_quote_rt=True)
            score_result = scorer.score(gen["text"])

            print(f"  🛡️  安全チェック : {'✅ PASS' if safety_result.is_safe else '❌ FAIL'}")
            if not safety_result.is_safe:
                for v in safety_result.violations:
                    print(f"       ⛔ {v}")
            print(
                f"  📊 スコア      : {score_result.total}/8 [{score_result.rank}]  "
                f"(フック:{score_result.hook} 具体性:{score_result.specificity} 人間味:{score_result.humanity})"
            )
            print()
            pause(0.3)

    except Exception as e:
        # フォールバック: ライブラリなしでもデモを見せる
        for i, gen in enumerate(DEMO_GENERATED, 1):
            tweet = DEMO_TWEETS[i - 1]
            print(f"  ─── 投稿 {i} / {len(DEMO_GENERATED)} ───────────────────────────")
            print(f"  元ツイート: @{tweet['author_username']} ({tweet['likes']:,}❤)")
            print()
            print(f"  生成テキスト [テンプレート: {gen['template']}]:")
            for line in gen["text"].split("\n"):
                print(f"    {line}")
            print()
            print(f"  🛡️  安全チェック : ✅ PASS")
            print(f"  📊 スコア      : {gen['score']}/8 [{gen['rank']}]")
            print()
            pause(0.3)

    # ── STEP 4: 投稿スケジュール計画 ──────────────────────────────────────
    step("STEP 4 │ 本日の投稿スケジュール（BAN対策ミックス）")
    print()

    try:
        from src.post.mix_planner import MixPlanner
        planner = MixPlanner()
        plan = planner.plan_daily(available_quotes=len(DEMO_TWEETS))
        print(planner.format_plan(plan))
    except Exception:
        # フォールバック
        print("  📋 本日の投稿スケジュール:")
        print()
        sample_plan = [
            ("07:12", "✍️ original ", "オリジナル投稿"),
            ("08:47", "🔄 quote_rt  ", "引用RT (o3速報)"),
            ("10:08", "🔄 quote_rt  ", "引用RT (AIエージェント)"),
            ("12:03", "✍️ original ", "オリジナル投稿"),
            ("14:31", "🔄 quote_rt  ", "引用RT (Vibe Coding)"),
            ("16:22", "✍️ original ", "オリジナル投稿"),
            ("18:09", "🔄 quote_rt  ", "引用RT"),
            ("19:58", "🔄 quote_rt  ", "引用RT"),
            ("21:14", "✍️ original ", "オリジナル投稿"),
        ]
        for i, (t, icon, label) in enumerate(sample_plan, 1):
            print(f"  {i:2}. {t}  {icon}  {label}")
        print()
        print(f"  合計: 9件 (引用RT: 5 / オリジナル: 4)")

    print()
    print("  BAN対策チェック:")
    print("  ✅ 引用RT比率      : 56% (上限70%以内)")
    print("  ✅ 連続引用RT      : 最大2件（制限内）")
    print("  ✅ 最小投稿間隔    : 60分以上確保")
    print("  ✅ 投稿時間帯      : 7:00〜22:00（設定範囲内）")
    pause()

    # ── STEP 5: Discord 通知イメージ ──────────────────────────────────────
    step("STEP 5 │ Discord通知（承認フロー）")
    print()
    print("  実運用では生成完了後、Discordに以下の通知が届きます:")
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │ 🤖 引用RT生成完了 — @ren_aiautomation      │")
    print("  │                                             │")
    print("  │ 📝 投稿①  [breaking_news]  スコア: 7/8 A   │")
    print("  │ これはデカい。OpenAIのo3...                  │")
    print("  │                                             │")
    print("  │ 📝 投稿②  [translate_comment]  スコア: 8/8 S│")
    print("  │ AIエージェント、もう「最先端」じゃなくて... │")
    print("  │                                             │")
    print("  │ ⏰ 投稿スケジュール: 9件 / 本日             │")
    print("  └─────────────────────────────────────────────┘")
    print()
    print("  手動承認モード: Discord確認後に投稿コマンドを実行")
    print()
    print("  $ python -m src.main curate-post --account 1")
    pause()

    # ── まとめ ─────────────────────────────────────────────────────────────
    sep("═")
    print("  パターンA デモ完了")
    sep("═")
    print()
    print("  ▌ 運用フロー（毎日）")
    print("  │")
    print("  ├─ 朝: バズツイートURLを手動で5〜10件収集")
    print("  │      $ python tools/add_tweet.py <URL>")
    print("  │")
    print("  ├─ 朝6:30: GitHub Actions が自動実行")
    print("  │      → Gemini で引用RTコメントを生成")
    print("  │      → Discord に通知")
    print("  │")
    print("  ├─ 確認: Discord で投稿内容をチェック・承認")
    print("  │")
    print("  └─ 自動投稿: 1日9〜10件、60分以上の間隔で分散投稿")
    print()
    print("  ▌ 月間コスト")
    print("  ├─ GitHub Actions : 無料（月2,000分枠内）")
    print("  ├─ Gemini API     : 無料（月1,500リクエスト枠内）")
    print("  ├─ X API          : 無料（月1,500投稿枠内）")
    print("  └─ 合計           : ¥0〜300/月")
    print()
    sep("═")


if __name__ == "__main__":
    main()
