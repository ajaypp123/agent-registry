const $ = (id) => document.getElementById(id);

async function loadDefaults() {
  try {
    const res = await fetch("/api/defaults");
    const data = await res.json();
    $("config").value = data.config_text;
    $("repos").value = data.repos_text;
    $("config-hint").textContent = data.config_from_file
      ? "Loaded from conf.toml on the server. That file always wins; edits here are only used when it is missing."
      : "No conf.toml found on the server — this text is used as the configuration.";
    if (data.token_from_env) {
      $("token-hint").textContent = "GIT_TOKEN is set on the server. Leave blank to use it.";
    }
  } catch (e) {
    $("config-hint").textContent = `Failed to load defaults: ${e}`;
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function bulletList(items) {
  const ul = el("ul");
  items.forEach((item) => ul.appendChild(el("li", null, String(item))));
  return ul;
}

function renderPR(pr) {
  const card = el("div", "pr");

  const title = el("h3", "pr-title");
  const label = `${pr.repo}#${pr.number} — ${pr.title}`;
  if (typeof pr.url === "string" && /^https?:\/\//.test(pr.url)) {
    const link = el("a", null, label);
    link.href = pr.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    title.appendChild(link);
  } else {
    title.textContent = label;
  }
  card.appendChild(title);

  const meta = el("div", "meta");
  const chips = [
    ["chip", `author: ${pr.author}`],
    ["chip", `updated: ${pr.updated_at}`],
    ["chip", `${pr.head_branch || "?"} → ${pr.base_branch || "?"}`],
    ["chip", `${pr.changed_files || 0} files`],
    ["chip add", `+${pr.additions || 0}`],
    ["chip del", `-${pr.deletions || 0}`],
  ];
  (pr.labels || []).forEach((l) => chips.push(["chip", l]));
  chips.forEach(([cls, text]) => meta.appendChild(el("span", cls, text)));
  card.appendChild(meta);

  const summary = pr.structured_summary || {};
  if (summary.overview) {
    card.appendChild(el("div", "section-label", "Overview"));
    card.appendChild(el("p", null, summary.overview));
  }
  if ((summary.key_changes || []).length) {
    card.appendChild(el("div", "section-label", "Key changes"));
    card.appendChild(bulletList(summary.key_changes));
  }
  if ((summary.suggestions || []).length) {
    card.appendChild(el("div", "section-label", "Suggestions"));
    card.appendChild(bulletList(summary.suggestions));
  }
  if ((pr.files || []).length) {
    card.appendChild(el("div", "section-label", "Files"));
    card.appendChild(
      bulletList(
        pr.files.map(
          (f) => `${f.filename} (${f.status}, +${f.additions} -${f.deletions})`
        )
      )
    );
  }
  return card;
}

function renderResults(data) {
  const panel = $("results-panel");
  const list = $("results");
  list.replaceChildren();
  $("raw").textContent = data.report || "";
  $("results-title").textContent = `Results — ${data.prs.length} PR(s)`;

  if (!data.prs.length) {
    list.appendChild(el("p", "empty", "No unreviewed PRs found."));
  } else {
    data.prs.forEach((pr) => list.appendChild(renderPR(pr)));
  }
  panel.hidden = false;
}

async function run() {
  const button = $("run");
  const status = $("status");
  button.disabled = true;
  status.className = "status";
  status.textContent = "Running review… this can take a while on first run (model load).";

  try {
    const res = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        config_text: $("config").value,
        repos_text: $("repos").value,
        git_token: $("token").value,
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      status.className = "status error";
      status.textContent = data.detail || `Request failed (${res.status})`;
      return;
    }
    if (data.error) {
      status.className = "status error";
      status.textContent = data.error;
      return;
    }

    status.className = "status ok";
    status.textContent = `Done — scanned ${data.repos.length} repo(s).`;
    renderResults(data);
  } catch (e) {
    status.className = "status error";
    status.textContent = `Request failed: ${e}`;
  } finally {
    button.disabled = false;
  }
}

$("run").addEventListener("click", run);
$("toggle-raw").addEventListener("click", () => {
  const raw = $("raw");
  raw.hidden = !raw.hidden;
  $("toggle-raw").textContent = raw.hidden ? "Show raw report" : "Hide raw report";
});

loadDefaults();
