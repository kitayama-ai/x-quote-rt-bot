// ============================================
// X Monetize Dashboard — Main Application
// ============================================

// === DATA LAYER ===
const DemoData = {
  accounts: [
    {
      id: "acc1",
      name: "NinjaGuild_Japan",
      handle: "@ngg_japan",
      color: "#6366f1",
      apiUrl: "",
    },
    {
      id: "acc2",
      name: "サブ垢",
      handle: "@sub_ai_tips",
      color: "#06b6d4",
      apiUrl: "",
    },
  ],
  generatePosts(accountId, days = 30) {
    const types = [
      "問題提起",
      "How to",
      "ストーリー",
      "リスト",
      "反常識",
      "権威引用",
      "宣伝",
    ];
    const hooks = [
      "ぶっちゃけ、AIに投稿を任せ始めてから世界変わった。",
      "正直、3時間かけて投稿作ってた自分がバカみたいだ。",
      "Claude Codeでnote記事を書いたら、3日で10部売れた話。",
      "「AI感」を消す5つのテクニック。これ知らない人多いけど...。",
      "副業の投稿を全自動にした結果、1日30分で済むようになった。",
      "GAS×スプシで投稿を自動化する方法を全部公開する。",
      "月100万とか言ってる人、正直信用してない。でも月5万なら再現できる。",
      "ChatGPTとClaude Code、どっちが副業に向いてるか比較した。",
      "フォロワー100人の壁を超えるためにやった3つのこと。",
      "マスターデータっていう概念、もっと広まるべき。",
      "AIに「自分の分身」を作らせる方法、noteにまとめました。",
      "投稿のエンゲージメント率を2倍にしたA/Bテストの結果。",
      "情報商材を買って後悔した過去があるから、正直に書く。",
      "1ヶ月で副業の作業時間を85%削減した具体的な手順。",
    ];
    const posts = [];
    const now = new Date();
    for (let i = 0; i < days * 2; i++) {
      const d = new Date(now);
      d.setDate(d.getDate() - Math.floor(i / 2));
      const isAm = i % 2 === 0;
      d.setHours(isAm ? 7 : 21, Math.floor(Math.random() * 30), 0);
      const baseLikes = accountId === "acc1" ? 30 : 15;
      const likes = Math.floor(Math.random() * baseLikes * 3 + baseLikes * 0.3);
      const rts = Math.floor(likes * (0.1 + Math.random() * 0.25));
      const replies = Math.floor(likes * (0.05 + Math.random() * 0.15));
      const type = types[Math.floor(Math.random() * types.length)];
      const text = hooks[Math.floor(Math.random() * hooks.length)];
      let rank = "C";
      if (likes > baseLikes * 2.5) rank = "S";
      else if (likes > baseLikes * 1.5) rank = "A";
      else if (likes > baseLikes * 0.8) rank = "B";
      posts.push({
        date: d,
        text,
        type,
        likes,
        rts,
        replies,
        rank,
        charCount: text.length,
      });
    }
    return posts.sort((a, b) => b.date - a.date);
  },
  generateFollowers(days = 30) {
    let f = 42;
    const data = [];
    for (let i = days; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      f += Math.floor(Math.random() * 6 - 1);
      if (f < 10) f = 10;
      data.push({ date: d, count: f });
    }
    return data;
  },
  generateFunnel() {
    return [
      { label: "インプレッション", value: 45200, color: "#6366f1" },
      { label: "プロフィール訪問", value: 1280, color: "#818cf8" },
      { label: "note ページ訪問", value: 384, color: "#06b6d4" },
      { label: "無料記事 読了", value: 192, color: "#22d3ee" },
      { label: "有料記事ページ", value: 96, color: "#f59e0b" },
      { label: "購入", value: 12, color: "#10b981" },
    ];
  },
  generateABTests() {
    return [
      {
        name: "フック: 数字 vs 自己開示",
        target: "フック",
        varA: "数字フック「3時間→30分」",
        varB: "自己開示「正直、しんどかった」",
        resultA: 45,
        resultB: 78,
        memo: "自己開示フックがいいね1.7倍。特に朝投稿で差が大きい。",
      },
      {
        name: "投稿時間: 7時 vs 8時",
        target: "投稿時間",
        varA: "朝7:00",
        varB: "朝8:00",
        resultA: 62,
        resultB: 41,
        memo: "7時の方が1.5倍。通勤前にチェックする層を捕捉できている。",
      },
      {
        name: "CTA: あり vs なし",
        target: "CTA",
        varA: "CTA付き「→プロフから」",
        varB: "CTAなし",
        resultA: 38,
        resultB: 52,
        memo: "CTAなしの方がいいね数は高い。宣伝感で敬遠される可能性。",
      },
    ];
  },
};

// === APP STATE ===
const State = {
  currentAccount: "acc1",
  currentView: "overview",
  dateRange: "30d",
  posts: [],
  notes: JSON.parse(localStorage.getItem("xm_notes") || "[]"),
  abTests: JSON.parse(localStorage.getItem("xm_abtests") || "null"),
  accounts: JSON.parse(localStorage.getItem("xm_accounts") || "null"),
  charts: {},
};

if (!State.accounts) {
  State.accounts = DemoData.accounts;
  localStorage.setItem("xm_accounts", JSON.stringify(State.accounts));
}
if (!State.abTests) {
  State.abTests = DemoData.generateABTests();
  localStorage.setItem("xm_abtests", JSON.stringify(State.abTests));
}

// === INIT ===
document.addEventListener("DOMContentLoaded", () => {
  initNav();
  initAccountSelector();
  initSidebar();
  loadAccountData();
  initForms();
});

// === NAVIGATION ===
function initNav() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      const view = item.dataset.view;
      switchView(view);
    });
  });
}

function switchView(view) {
  State.currentView = view;
  document
    .querySelectorAll(".nav-item")
    .forEach((n) => n.classList.toggle("active", n.dataset.view === view));
  document
    .querySelectorAll(".view")
    .forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  const titles = {
    overview: "オーバービュー",
    posts: "投稿パフォーマンス",
    analytics: "トレンド分析",
    funnel: "ファネル",
    abtest: "A/Bテスト",
    calendar: "コンテンツカレンダー",
    notes: "分析ノート",
    settings: "設定",
  };
  document.getElementById("topbarTitle").textContent = titles[view] || view;
  if (view === "funnel") renderFunnel();
  if (view === "abtest") renderABTests();
  if (view === "calendar") renderCalendar();
  if (view === "notes") renderNotes();
  if (view === "settings") renderSettings();
  if (view === "posts") renderPostsTable();
  if (view === "analytics") renderAnalyticsCharts();
}

// === SIDEBAR (MOBILE) ===
function initSidebar() {
  const sidebar = document.getElementById("sidebar");
  document
    .getElementById("hamburger")
    .addEventListener("click", () => sidebar.classList.add("open"));
  document
    .getElementById("sidebarClose")
    .addEventListener("click", () => sidebar.classList.remove("open"));
  document
    .querySelectorAll(".nav-item")
    .forEach((n) =>
      n.addEventListener("click", () => sidebar.classList.remove("open")),
    );
}

// === ACCOUNT SELECTOR ===
function initAccountSelector() {
  const btn = document.getElementById("accountCurrent");
  const list = document.getElementById("accountList");
  btn.addEventListener("click", () => list.classList.toggle("open"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".account-dropdown")) list.classList.remove("open");
  });
  renderAccountList();
}

function renderAccountList() {
  const list = document.getElementById("accountList");
  const allOpt = `<div class="account-option ${State.currentAccount === "all" ? "active" : ""}" data-id="all">
    <span class="account-avatar" style="background:linear-gradient(135deg,#6366f1,#06b6d4);font-size:0.7rem">ALL</span>
    <div class="account-info"><span class="account-name">全アカウント</span><span class="account-handle">サマリー表示</span></div></div>`;
  const opts = State.accounts
    .map(
      (
        a,
      ) => `<div class="account-option ${State.currentAccount === a.id ? "active" : ""}" data-id="${a.id}">
    <span class="account-avatar" style="background:${a.color}">${a.name[0]}</span>
    <div class="account-info"><span class="account-name">${a.name}</span><span class="account-handle">${a.handle}</span></div></div>`,
    )
    .join("");
  list.innerHTML = allOpt + opts;
  list.querySelectorAll(".account-option").forEach((opt) => {
    opt.addEventListener("click", () => {
      State.currentAccount = opt.dataset.id;
      list.classList.remove("open");
      updateAccountButton();
      loadAccountData();
    });
  });
}

function updateAccountButton() {
  const btn = document.getElementById("accountCurrent");
  if (State.currentAccount === "all") {
    btn.querySelector(".account-avatar").textContent = "ALL";
    btn.querySelector(".account-avatar").style.background =
      "linear-gradient(135deg,#6366f1,#06b6d4)";
    btn.querySelector(".account-name").textContent = "全アカウント";
    btn.querySelector(".account-handle").textContent = "サマリー表示";
  } else {
    const a = State.accounts.find((x) => x.id === State.currentAccount);
    if (a) {
      btn.querySelector(".account-avatar").textContent = a.name[0];
      btn.querySelector(".account-avatar").style.background = a.color;
      btn.querySelector(".account-name").textContent = a.name;
      btn.querySelector(".account-handle").textContent = a.handle;
    }
  }
  renderAccountList();
}

// === LOAD DATA ===
function loadAccountData() {
  const accId = State.currentAccount === "all" ? "acc1" : State.currentAccount;
  State.posts = DemoData.generatePosts(accId);
  renderOverview();
  if (State.currentView === "posts") renderPostsTable();
  if (State.currentView === "analytics") renderAnalyticsCharts();
  document.getElementById("multiAccountBar").style.display =
    State.currentAccount === "all" ? "block" : "none";
  if (State.currentAccount === "all") renderMultiAccountSummary();
}

// === KPI CARDS & SPARKLINES ===
function renderOverview() {
  const posts = State.posts;
  const totalLikes = posts.reduce((s, p) => s + p.likes, 0);
  const totalRts = posts.reduce((s, p) => s + p.rts, 0);
  const totalReplies = posts.reduce((s, p) => s + p.replies, 0);
  const followers = DemoData.generateFollowers();
  const currentF = followers[followers.length - 1].count;
  const prevF = followers[Math.max(0, followers.length - 8)].count;
  const avgEng = posts.length
    ? ((totalLikes + totalRts + totalReplies) / posts.length).toFixed(1)
    : 0;
  const impressions = totalLikes * 12 + totalRts * 25;

  setKPI(
    "followers",
    currentF.toLocaleString(),
    `+${currentF - prevF}`,
    currentF > prevF,
  );
  setKPI("engagement", avgEng, `+${(avgEng * 0.12).toFixed(1)}`, true);
  setKPI(
    "impressions",
    formatNum(impressions),
    `+${formatNum(Math.floor(impressions * 0.08))}`,
    true,
  );
  setKPI("revenue", `¥${(12 * 4980).toLocaleString()}`, "+¥4,980", true);

  renderSparkline(
    "spark-followers",
    followers.map((f) => f.count),
    "#6366f1",
  );
  renderSparkline(
    "spark-engagement",
    posts.slice(0, 14).map((p) => p.likes + p.rts),
    "#06b6d4",
  );
  renderSparkline(
    "spark-impressions",
    posts.slice(0, 14).map((p) => p.likes * 12),
    "#f59e0b",
  );
  renderSparkline(
    "spark-revenue",
    [
      0, 0, 4980, 4980, 9960, 9960, 14940, 14940, 19920, 24900, 29880, 34860,
      49800, 59760,
    ],
    "#10b981",
  );

  renderEngagementChart();
  renderTypeAvgChart();
  renderTimeHeatmap();
  renderBestWorstPosts();
}

function setKPI(id, value, change, positive) {
  document.getElementById(`kpi-${id}-value`).textContent = value;
  const changeEl = document.getElementById(`kpi-${id}-change`);
  changeEl.textContent = change;
  changeEl.className = `kpi-change ${positive ? "positive" : "negative"}`;
}

function formatNum(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return n.toLocaleString();
}

function renderSparkline(canvasId, data, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width,
    h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!data.length) return;
  const max = Math.max(...data),
    min = Math.min(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = i * step,
      y = h - ((v - min) / range) * (h - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + "30");
  grad.addColorStop(1, color + "00");
  ctx.fillStyle = grad;
  ctx.fill();
}

// === CHART.JS CHARTS ===
function destroyChart(key) {
  if (State.charts[key]) {
    State.charts[key].destroy();
    delete State.charts[key];
  }
}

const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#55556a", font: { size: 11 } },
    },
    y: {
      grid: { color: "rgba(255,255,255,0.04)" },
      ticks: { color: "#55556a", font: { size: 11 } },
    },
  },
};

function renderEngagementChart() {
  destroyChart("engagement");
  const posts = State.posts.slice().reverse();
  const labels = posts.map(
    (p) => `${p.date.getMonth() + 1}/${p.date.getDate()}`,
  );
  const uniqLabels = [...new Set(labels)];
  const aggregate = (metric) =>
    uniqLabels.map((l) => {
      const matching = posts.filter(
        (p) => `${p.date.getMonth() + 1}/${p.date.getDate()}` === l,
      );
      return matching.reduce((s, p) => s + p[metric], 0);
    });
  State.charts.engagement = new Chart(
    document.getElementById("chart-engagement"),
    {
      type: "line",
      data: {
        labels: uniqLabels,
        datasets: [
          {
            label: "いいね",
            data: aggregate("likes"),
            borderColor: "#6366f1",
            backgroundColor: "rgba(99,102,241,0.1)",
            fill: true,
            tension: 0.4,
            pointRadius: 2,
          },
          {
            label: "RT",
            data: aggregate("rts"),
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6,182,212,0.1)",
            fill: true,
            tension: 0.4,
            pointRadius: 2,
          },
          {
            label: "リプライ",
            data: aggregate("replies"),
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245,158,11,0.1)",
            fill: true,
            tension: 0.4,
            pointRadius: 2,
          },
        ],
      },
      options: { ...chartDefaults },
    },
  );
}

function renderTypeAvgChart() {
  destroyChart("typeAvg");
  const types = {};
  State.posts.forEach((p) => {
    if (!types[p.type]) types[p.type] = { sum: 0, count: 0 };
    types[p.type].sum += p.likes;
    types[p.type].count++;
  });
  const labels = Object.keys(types);
  const data = labels.map((t) => (types[t].sum / types[t].count).toFixed(1));
  const colors = [
    "#6366f1",
    "#06b6d4",
    "#f59e0b",
    "#10b981",
    "#f43f5e",
    "#a855f7",
    "#ec4899",
  ];
  State.charts.typeAvg = new Chart(document.getElementById("chart-type-avg"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors.slice(0, labels.length),
          borderRadius: 6,
          barThickness: 32,
        },
      ],
    },
    options: {
      ...chartDefaults,
      indexAxis: "y",
      plugins: { legend: { display: false } },
    },
  });
}

function renderTimeHeatmap() {
  destroyChart("timeHeatmap");
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const counts = hours.map((h) =>
    State.posts
      .filter((p) => p.date.getHours() === h)
      .reduce((s, p) => s + p.likes, 0),
  );
  State.charts.timeHeatmap = new Chart(
    document.getElementById("chart-time-heatmap"),
    {
      type: "bar",
      data: {
        labels: hours.map((h) => `${h}時`),
        datasets: [
          {
            data: counts,
            backgroundColor: counts.map((c) => {
              const max = Math.max(...counts) || 1;
              const ratio = c / max;
              return `rgba(99,102,241,${0.2 + ratio * 0.8})`;
            }),
            borderRadius: 4,
            barThickness: 16,
          },
        ],
      },
      options: { ...chartDefaults, plugins: { legend: { display: false } } },
    },
  );
}

function renderBestWorstPosts() {
  const sorted = [...State.posts].sort((a, b) => b.likes - a.likes);
  const best = sorted.slice(0, 5);
  const worst = sorted.slice(-5).reverse();
  const renderList = (items, containerId) => {
    document.getElementById(containerId).innerHTML = items
      .map(
        (p, i) => `
      <div class="post-rank-item">
        <div class="rank-position">${i + 1}</div>
        <div class="rank-text">${escHtml(p.text)}</div>
        <div class="rank-stats">
          <span class="rank-stat">❤️ <strong>${p.likes}</strong></span>
          <span class="rank-stat">🔁 <strong>${p.rts}</strong></span>
        </div>
      </div>`,
      )
      .join("");
  };
  renderList(best, "bestPosts");
  renderList(worst, "worstPosts");
}

// === POSTS TABLE ===
function renderPostsTable() {
  const tbody = document.getElementById("postsTableBody");
  const search = (
    document.getElementById("postSearch")?.value || ""
  ).toLowerCase();
  const rankFilter = document.getElementById("filterRank")?.value || "";
  const typeFilter = document.getElementById("filterType")?.value || "";
  let filtered = State.posts.filter((p) => {
    if (search && !p.text.toLowerCase().includes(search)) return false;
    if (rankFilter && p.rank !== rankFilter) return false;
    if (typeFilter && p.type !== typeFilter) return false;
    return true;
  });
  tbody.innerHTML = filtered
    .slice(0, 50)
    .map(
      (p) => `<tr>
    <td style="white-space:nowrap;font-family:var(--font-mono);font-size:0.75rem;color:var(--text-muted)">${fmt(p.date)}</td>
    <td class="post-text-cell" onclick="showPostModal(this)" data-text="${escAttr(p.text)}" data-likes="${p.likes}" data-rts="${p.rts}" data-replies="${p.replies}" data-type="${p.type}" data-rank="${p.rank}">${escHtml(p.text.substring(0, 60))}...</td>
    <td><span style="font-size:0.75rem;color:var(--text-secondary)">${p.type}</span></td>
    <td style="font-family:var(--font-mono);font-weight:600">${p.likes}</td>
    <td style="font-family:var(--font-mono)">${p.rts}</td>
    <td style="font-family:var(--font-mono)">${p.replies}</td>
    <td><span class="rank-badge rank-${p.rank}">${p.rank}</span></td>
    <td><button class="post-action-btn" onclick="showPostModal(this.closest('tr').querySelector('.post-text-cell'))">詳細</button></td>
  </tr>`,
    )
    .join("");
  // Attach filter listeners
  ["postSearch", "filterRank", "filterType"].forEach((id) => {
    const el = document.getElementById(id);
    if (el && !el._bound) {
      el.addEventListener("input", () => renderPostsTable());
      el._bound = true;
    }
  });
}

// === ANALYTICS CHARTS ===
function renderAnalyticsCharts() {
  // Follower trend
  destroyChart("followerTrend");
  const fData = DemoData.generateFollowers(60);
  State.charts.followerTrend = new Chart(
    document.getElementById("chart-follower-trend"),
    {
      type: "line",
      data: {
        labels: fData.map(
          (f) => `${f.date.getMonth() + 1}/${f.date.getDate()}`,
        ),
        datasets: [
          {
            label: "フォロワー",
            data: fData.map((f) => f.count),
            borderColor: "#6366f1",
            backgroundColor: "rgba(99,102,241,0.1)",
            fill: true,
            tension: 0.3,
            pointRadius: 1.5,
          },
        ],
      },
      options: { ...chartDefaults },
    },
  );
  // Rank distribution
  destroyChart("rankDist");
  const ranks = { S: 0, A: 0, B: 0, C: 0 };
  State.posts.forEach((p) => ranks[p.rank]++);
  State.charts.rankDist = new Chart(
    document.getElementById("chart-rank-dist"),
    {
      type: "doughnut",
      data: {
        labels: ["S", "A", "B", "C"],
        datasets: [
          {
            data: Object.values(ranks),
            backgroundColor: ["#fbbf24", "#6366f1", "#06b6d4", "#374151"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#8b8ba0", padding: 16, font: { size: 12 } },
          },
        },
      },
    },
  );
  // Length vs engagement scatter
  destroyChart("lengthEng");
  State.charts.lengthEng = new Chart(
    document.getElementById("chart-length-engagement"),
    {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "投稿",
            data: State.posts.map((p) => ({ x: p.charCount, y: p.likes })),
            backgroundColor: "rgba(99,102,241,0.5)",
            pointRadius: 4,
          },
        ],
      },
      options: {
        ...chartDefaults,
        scales: {
          x: {
            ...chartDefaults.scales.x,
            title: { display: true, text: "文字数", color: "#8b8ba0" },
          },
          y: {
            ...chartDefaults.scales.y,
            title: { display: true, text: "いいね数", color: "#8b8ba0" },
          },
        },
      },
    },
  );
  // Weekly KPI
  destroyChart("weeklyKpi");
  const weeks = [];
  for (let i = 3; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i * 7);
    weeks.push(`W${4 - i}`);
  }
  State.charts.weeklyKpi = new Chart(
    document.getElementById("chart-weekly-kpi"),
    {
      type: "bar",
      data: {
        labels: weeks,
        datasets: [
          {
            label: "合計いいね",
            data: weeks.map(() => Math.floor(Math.random() * 300 + 200)),
            backgroundColor: "rgba(99,102,241,0.7)",
            borderRadius: 6,
          },
          {
            label: "合計RT",
            data: weeks.map(() => Math.floor(Math.random() * 80 + 30)),
            backgroundColor: "rgba(6,182,212,0.7)",
            borderRadius: 6,
          },
        ],
      },
      options: {
        ...chartDefaults,
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: { color: "#8b8ba0", font: { size: 11 } },
          },
        },
      },
    },
  );
}

// === FUNNEL ===
function renderFunnel() {
  const data = DemoData.generateFunnel();
  const maxVal = data[0].value;
  const visual = document.getElementById("funnelVisual");
  visual.innerHTML = data
    .map((step, i) => {
      const width = Math.max(20, (step.value / maxVal) * 100);
      const rate =
        i > 0
          ? ((step.value / data[i - 1].value) * 100).toFixed(1) + "%"
          : "100%";
      const rateClass =
        i > 0 && step.value / data[i - 1].value < 0.1 ? "negative" : "positive";
      return `${i > 0 ? '<div class="funnel-arrow">↓</div>' : ""}
    <div class="funnel-step" style="background:var(--bg-card);border:1px solid var(--border)">
      <div class="funnel-bar" style="width:${width}%;background:${step.color}"></div>
      <span class="funnel-label">${step.label}</span>
      <span class="funnel-value">${step.value.toLocaleString()}</span>
      <span class="funnel-rate kpi-change ${rateClass}">${rate}</span>
    </div>`;
    })
    .join("");
  const insights = document.getElementById("funnelInsights");
  const noteToProfile = ((data[1].value / data[0].value) * 100).toFixed(1);
  const profileToNote = ((data[2].value / data[1].value) * 100).toFixed(1);
  const purchaseRate = ((data[5].value / data[4].value) * 100).toFixed(1);
  insights.innerHTML = `<h4 style="margin-bottom:12px;font-size:0.9rem">📊 ボトルネック分析</h4>
    <div class="funnel-insight-item"><span class="insight-icon">⚠️</span><span class="insight-text">プロフ訪問率 <strong>${noteToProfile}%</strong> — 目標2%${noteToProfile < 2 ? " → フック力の強化とリプライ営業の増加が必要" : " → 目標クリア✅"}</span></div>
    <div class="funnel-insight-item"><span class="insight-icon">${profileToNote > 10 ? "✅" : "⚠️"}</span><span class="insight-text">note訪問率 <strong>${profileToNote}%</strong> — 目標10%${profileToNote < 10 ? " → 固定ツイートとプロフ文の改善が必要" : " → 目標クリア✅"}</span></div>
    <div class="funnel-insight-item"><span class="insight-icon">${purchaseRate > 5 ? "✅" : "⚠️"}</span><span class="insight-text">購入率 <strong>${purchaseRate}%</strong> — 目標5%${purchaseRate < 5 ? " → 無料部分のクロージング強化が必要" : " → 目標クリア✅"}</span></div>`;
}

// === A/B TESTS ===
function renderABTests() {
  const grid = document.getElementById("abtestGrid");
  grid.innerHTML = State.abTests
    .map((t) => {
      const winner = t.resultA > t.resultB ? "A" : "B";
      return `<div class="abtest-card">
      <div class="abtest-title">${escHtml(t.name)}</div>
      <div class="abtest-target">${t.target}</div>
      <div class="abtest-comparison">
        <div class="abtest-variant ${winner === "A" ? "winner" : "loser"}">
          ${winner === "A" ? '<div class="winner-badge">WINNER</div>' : ""}
          <div class="variant-label">A</div>
          <div class="variant-value ${winner === "A" ? "winner-val" : ""}">${t.resultA}</div>
          <div class="variant-desc">${escHtml(t.varA)}</div>
        </div>
        <div class="abtest-variant ${winner === "B" ? "winner" : "loser"}">
          ${winner === "B" ? '<div class="winner-badge">WINNER</div>' : ""}
          <div class="variant-label">B</div>
          <div class="variant-value ${winner === "B" ? "winner-val" : ""}">${t.resultB}</div>
          <div class="variant-desc">${escHtml(t.varB)}</div>
        </div>
      </div>
      <div class="abtest-memo">💡 ${escHtml(t.memo)}</div>
    </div>`;
    })
    .join("");
}

// === CALENDAR ===
function renderCalendar() {
  const grid = document.getElementById("calendarGrid");
  const days = ["日", "月", "火", "水", "木", "金", "土"];
  let html = days.map((d) => `<div class="cal-day-header">${d}</div>`).join("");
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const offset = start.getDay();
  for (let i = 0; i < offset; i++)
    html += '<div class="cal-cell" style="background:transparent"></div>';
  const daysInMonth = new Date(
    now.getFullYear(),
    now.getMonth() + 1,
    0,
  ).getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    const dayPosts = State.posts.filter(
      (p) => p.date.getDate() === d && p.date.getMonth() === now.getMonth(),
    );
    const totalLikes = dayPosts.reduce((s, p) => s + p.likes, 0);
    const maxDay = 120;
    const intensity = Math.min(totalLikes / maxDay, 1);
    let bg = "#1e293b";
    if (dayPosts.length > 0) {
      if (intensity > 0.7) bg = "#a5b4fc";
      else if (intensity > 0.4) bg = "#6366f1";
      else if (intensity > 0.2) bg = "#4338ca";
      else bg = "#312e81";
    }
    html += `<div class="cal-cell" style="background:${bg}" title="${d}日: ${dayPosts.length}投稿, ${totalLikes}いいね">
      <span class="cal-cell-date">${d}</span>
      <span class="cal-cell-count">${dayPosts.length > 0 ? dayPosts.length + "投稿" : ""}</span>
    </div>`;
  }
  grid.innerHTML = html;
}

// === NOTES ===
function renderNotes() {
  const list = document.getElementById("notesList");
  const catLabels = {
    insight: "💡 気づき",
    decision: "🎯 意思決定",
    hypothesis: "🧪 仮説",
    competitor: "🕵️ 競合動向",
    improvement: "🔧 改善案",
  };
  list.innerHTML = State.notes.length
    ? State.notes
        .map(
          (n, i) => `
    <div class="note-card">
      <div class="note-header">
        <span class="note-title-text">${escHtml(n.title)}</span>
        <span class="note-category ${n.category}">${catLabels[n.category] || n.category}</span>
      </div>
      <div class="note-body">${escHtml(n.content)}</div>
      <div class="note-meta">
        <span class="note-date">${n.date}</span>
        <button class="note-delete" onclick="deleteNote(${i})">削除</button>
      </div>
    </div>`,
        )
        .join("")
    : '<p style="color:var(--text-muted);text-align:center;padding:40px">まだノートがありません。上のフォームから追加してください。</p>';
}

function deleteNote(i) {
  State.notes.splice(i, 1);
  localStorage.setItem("xm_notes", JSON.stringify(State.notes));
  renderNotes();
}

// === SETTINGS ===
function renderSettings() {
  const list = document.getElementById("accountsListFull");
  list.innerHTML = State.accounts
    .map(
      (a) => `<div class="account-row">
    <span class="account-avatar" style="background:${a.color}">${a.name[0]}</span>
    <div class="account-row-info">
      <div class="account-row-name">${a.name}</div>
      <div class="account-row-handle">${a.handle}</div>
      ${a.apiUrl ? `<div class="account-row-url">${a.apiUrl.substring(0, 50)}...</div>` : ""}
    </div>
    <span class="account-row-status ${a.apiUrl ? "status-connected" : "status-pending"}">${a.apiUrl ? "接続済" : "未接続"}</span>
  </div>`,
    )
    .join("");
  const connStatus = document.getElementById("connectionStatus");
  connStatus.innerHTML = State.accounts
    .map(
      (a) =>
        `<div class="conn-row"><span>${a.name} (${a.handle})</span><span style="color:${a.apiUrl ? "var(--accent-emerald)" : "var(--accent-amber)"}">${a.apiUrl ? "✅ 接続済" : "⚠️ 未接続"}</span></div>`,
    )
    .join("");
}

// === MULTI-ACCOUNT SUMMARY ===
function renderMultiAccountSummary() {
  const cards = document.getElementById("accountCards");
  cards.innerHTML = State.accounts
    .map((a) => {
      const posts = DemoData.generatePosts(a.id, 7);
      const likes = posts.reduce((s, p) => s + p.likes, 0);
      const fData = DemoData.generateFollowers(7);
      return `<div class="mini-account-card" onclick="document.querySelector('[data-id=${a.id}]').click()">
      <div class="mini-account-header">
        <span class="account-avatar" style="background:${a.color};width:28px;height:28px;font-size:0.7rem">${a.name[0]}</span>
        <div><div style="font-weight:600;font-size:0.85rem">${a.name}</div><div style="font-size:0.7rem;color:var(--text-muted)">${a.handle}</div></div>
      </div>
      <div class="mini-kpi-row">
        <div class="mini-kpi"><div class="mini-kpi-label">フォロワー</div><div class="mini-kpi-value">${fData[fData.length - 1].count}</div></div>
        <div class="mini-kpi"><div class="mini-kpi-label">週間いいね</div><div class="mini-kpi-value">${likes}</div></div>
        <div class="mini-kpi"><div class="mini-kpi-label">投稿数</div><div class="mini-kpi-value">${posts.length}</div></div>
      </div>
    </div>`;
    })
    .join("");
}

// === FORMS ===
function initForms() {
  document.getElementById("noteForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    State.notes.unshift({
      title: document.getElementById("noteTitle").value,
      category: document.getElementById("noteCategory").value,
      content: document.getElementById("noteContent").value,
      date: new Date().toLocaleString("ja-JP"),
    });
    localStorage.setItem("xm_notes", JSON.stringify(State.notes));
    e.target.reset();
    renderNotes();
  });
  document.getElementById("abtestForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    State.abTests.push({
      name: document.getElementById("abTestName").value,
      target: document.getElementById("abTestTarget").value,
      varA: document.getElementById("abVarA").value,
      varB: document.getElementById("abVarB").value,
      resultA: parseInt(document.getElementById("abResultA").value) || 0,
      resultB: parseInt(document.getElementById("abResultB").value) || 0,
      memo: document.getElementById("abMemo").value,
    });
    localStorage.setItem("xm_abtests", JSON.stringify(State.abTests));
    e.target.reset();
    renderABTests();
  });
  document.getElementById("addAccountBtn")?.addEventListener("click", () => {
    document.getElementById("addAccountForm").style.display = "block";
  });
  document.getElementById("cancelAddAccount")?.addEventListener("click", () => {
    document.getElementById("addAccountForm").style.display = "none";
  });
  document.getElementById("newAccountForm")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const colors = [
      "#6366f1",
      "#06b6d4",
      "#f59e0b",
      "#10b981",
      "#f43f5e",
      "#a855f7",
    ];
    State.accounts.push({
      id: "acc" + Date.now(),
      name: document.getElementById("newAccName").value,
      handle: document.getElementById("newAccHandle").value,
      color: colors[State.accounts.length % colors.length],
      apiUrl: document.getElementById("newAccApiUrl").value,
    });
    localStorage.setItem("xm_accounts", JSON.stringify(State.accounts));
    e.target.reset();
    document.getElementById("addAccountForm").style.display = "none";
    renderSettings();
    renderAccountList();
  });
  document.getElementById("syncBtn")?.addEventListener("click", () => {
    alert(
      "スプシ連携にはGAS Web App URLの設定が必要です。\n設定 → アカウント管理からURLを追加してください。",
    );
  });
  document.getElementById("exportBtn")?.addEventListener("click", exportCSV);
  document
    .getElementById("testConnectionBtn")
    ?.addEventListener("click", testConnection);
  // Table sorting
  document.querySelectorAll(".sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      State.posts.sort((a, b) => {
        const av = a[key],
          bv = b[key];
        return typeof av === "number"
          ? bv - av
          : String(bv).localeCompare(String(av));
      });
      renderPostsTable();
    });
  });
}

// === MODAL ===
function showPostModal(cell) {
  const modal = document.getElementById("postModal");
  const body = document.getElementById("postModalBody");
  body.innerHTML = `
    <div class="modal-post-text">${escHtml(cell.dataset.text)}</div>
    <div class="modal-stats">
      <div class="modal-stat"><div class="modal-stat-label">いいね</div><div class="modal-stat-value" style="color:#6366f1">❤️ ${cell.dataset.likes}</div></div>
      <div class="modal-stat"><div class="modal-stat-label">RT</div><div class="modal-stat-value" style="color:#06b6d4">🔁 ${cell.dataset.rts}</div></div>
      <div class="modal-stat"><div class="modal-stat-label">リプライ</div><div class="modal-stat-value" style="color:#f59e0b">💬 ${cell.dataset.replies}</div></div>
      <div class="modal-stat"><div class="modal-stat-label">ランク</div><div class="modal-stat-value"><span class="rank-badge rank-${cell.dataset.rank}">${cell.dataset.rank}</span></div></div>
    </div>
    <div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="post-action-btn" onclick="navigator.clipboard.writeText('${escAttr(cell.dataset.text)}');this.textContent='✅ コピー済'">📋 コピー</button>
    </div>`;
  modal.style.display = "flex";
  document.getElementById("modalClose").onclick = () =>
    (modal.style.display = "none");
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.style.display = "none";
  });
}

// === EXPORT ===
function exportCSV() {
  let csv = "\uFEFF日時,テキスト,型,いいね,RT,リプライ,ランク\n";
  State.posts.forEach((p) => {
    csv += `"${fmt(p.date)}","${p.text.replace(/"/g, '""')}","${p.type}",${p.likes},${p.rts},${p.replies},${p.rank}\n`;
  });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `x-monetize-export-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}

// === CONNECTION TEST ===
async function testConnection() {
  const btn = document.getElementById("testConnectionBtn");
  btn.textContent = "接続テスト中...";
  btn.disabled = true;
  for (const acc of State.accounts) {
    if (!acc.apiUrl) continue;
    try {
      const res = await fetch(acc.apiUrl + "?action=ping");
      const data = await res.json();
      if (data.status === "ok") {
        document
          .getElementById("syncStatus")
          .querySelector(".sync-dot")
          .classList.add("connected");
        document
          .getElementById("syncStatus")
          .querySelector(".sync-text").textContent = "接続済";
      }
    } catch (e) {
      console.warn("Connection failed for", acc.handle, e);
    }
  }
  btn.textContent = "接続テスト";
  btn.disabled = false;
  renderSettings();
}

// === HELPERS ===
function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  return s.replace(/'/g, "\\'").replace(/"/g, "&quot;");
}
function fmt(d) {
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
