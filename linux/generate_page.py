#!/usr/bin/env python3
"""generate_page.py — fabrique vault.html (liste consultable) et graph.html
(la carte du graphe) à partir de index.md. Sur macOS, en dépose aussi une
copie dans iCloud Drive pour l'iPhone ; sous Linux, cette étape est ignorée.

Usage : python3 generate_page.py [--vault ~/Vault]
"""

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent
NOM_DEFAUT = "Bobine"


def lire_config(*dossiers):
    """Lit config.env (clé=valeur) dans les dossiers donnés."""
    cfg = {}
    for dossier in dossiers:
        fichier = Path(dossier) / "config.env"
        if not fichier.is_file():
            continue
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            valeur = valeur.strip().strip('"').strip("'")
            if valeur:
                cfg[cle.strip()] = valeur
    return cfg


def lire_index(chemin):
    """Lit index.md et retourne une liste d'entrées
    {titre, lien, auteur, themes, contenu}. Fichier absent → liste vide."""
    entrees = []
    courant = None
    if not chemin.is_file():
        return entrees
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne.startswith("### "):
            courant = {"titre": ligne[4:].strip(), "lien": "", "auteur": "",
                       "themes": [], "contenu": ""}
            entrees.append(courant)
        elif courant is not None:
            for prefixe, champ in (("- lien :", "lien"),
                                   ("- auteur :", "auteur"),
                                   ("- contenu :", "contenu")):
                if ligne.startswith(prefixe):
                    courant[champ] = ligne[len(prefixe):].strip()
            if ligne.startswith("- thèmes :"):
                courant["themes"] = [t.strip() for t in
                                     ligne[len("- thèmes :"):].split(",")
                                     if t.strip()]
    return [e for e in entrees if e["titre"]]


def positions_initiales(entrees, iterations=700):
    """Simule la physique du graphe côté Python, pour livrer une carte déjà
    équilibrée : le navigateur (et l'aperçu iPhone) n'a plus qu'à l'afficher.
    Mêmes constantes que la simulation JS de graph.html."""
    import numpy as np  # dispo dans le venv (dépendance de faster-whisper)

    nb_fiches = len(entrees)
    theme_ids = {}
    edges = []
    nb = nb_fiches
    for i, e in enumerate(entrees):
        for t in e["themes"]:
            if t not in theme_ids:
                theme_ids[t] = nb
                nb += 1
            edges.append((i, theme_ids[t]))

    n = nb
    pos = np.zeros((n, 2))
    nt = n - nb_fiches
    for i in range(nb_fiches):
        a = (i / max(1, nb_fiches)) * 2 * np.pi
        pos[i] = (np.cos(a) * 320, np.sin(a) * 320)
    for k in range(nt):
        a = (k / max(1, nt)) * 2 * np.pi
        pos[nb_fiches + k] = (np.cos(a) * 160, np.sin(a) * 160)

    vel = np.zeros((n, 2))
    E = np.array(edges, dtype=int) if edges else np.zeros((0, 2), dtype=int)

    for _ in range(iterations):
        d = pos[:, None, :] - pos[None, :, :]
        d2 = (d ** 2).sum(-1)
        np.fill_diagonal(d2, np.inf)
        d2 = np.maximum(d2, 1.0)
        dist = np.sqrt(d2)
        force = (d / dist[..., None]) * (4200.0 / d2)[..., None]
        net = force.sum(axis=1)
        if len(E):
            dv = pos[E[:, 1]] - pos[E[:, 0]]
            dl = np.maximum(1.0, np.sqrt((dv ** 2).sum(-1)))
            fv = dv / dl[:, None] * ((dl - 115.0) * 0.028)[:, None]
            np.add.at(net, E[:, 0], fv)
            np.add.at(net, E[:, 1], -fv)
        vel += net
        vel += -pos * 0.006
        vel *= 0.84
        pos += vel

    return [[round(float(x), 1), round(float(y), 1)] for x, y in pos]


TEMPLATE_LISTE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vault — mes Reels sauvegardés</title>
<style>
  :root { --bg:#f5f6f8; --card:#fff; --txt:#1b1e24; --muted:#69707d;
          --accent:#0b7cff; --chip:#eef1f5; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--txt); }
  header { position:sticky; top:0; z-index:5; padding:14px 16px 10px;
           background:rgba(245,246,248,.93); backdrop-filter:blur(8px);
           border-bottom:1px solid #e3e6ea; }
  h1 { font-size:18px; margin:0 0 10px; display:flex; align-items:baseline; gap:10px; }
  h1 span { color:var(--muted); font-weight:500; font-size:13px; flex:1; }
  h1 a { color:var(--accent); font-size:13px; font-weight:600; text-decoration:none; }
  #q { width:100%; padding:11px 14px; font-size:16px; border:1px solid #d7dbe1;
       border-radius:10px; outline:none; background:var(--card); }
  #q:focus { border-color:var(--accent); }
  #themes { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
  .chip { border:1px solid #d7dbe1; background:var(--card); color:var(--txt);
          border-radius:999px; padding:4px 10px; font-size:13px; cursor:pointer; }
  .chip b { color:var(--muted); font-weight:600; }
  .chip.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .chip.on b { color:#dbe9ff; }
  main { max-width:760px; margin:0 auto; padding:16px; }
  .card { background:var(--card); border:1px solid #e6e9ed; border-radius:12px;
          padding:14px 16px; margin-bottom:12px; }
  .card h2 { margin:0 0 4px; font-size:16px; }
  .card h2 a { color:var(--txt); text-decoration:none; }
  .card h2 a:hover { color:var(--accent); }
  .meta { color:var(--muted); font-size:13px; margin-bottom:8px; }
  .tags { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 8px; }
  .tag { background:var(--chip); border-radius:999px; padding:2px 9px; font-size:12px;
         color:var(--muted); }
  .contenu { font-size:14.5px; line-height:1.45; margin:0; }
  .vide { color:var(--muted); text-align:center; padding:40px 0; }
  footer { color:var(--muted); font-size:12px; text-align:center; padding:8px 16px 28px; }
  footer .signature { display:block; margin-top:6px; }
  footer .signature a { color:var(--accent); text-decoration:none; }
</style>
</head>
<body>
<header>
  <h1>Vault — mes Reels sauvegardés <span id="stats">__STATS__</span> <a href="graph.html">Carte &#128376;</a></h1>
  <input id="q" type="search" placeholder="Rechercher (titre, contenu, auteur)…" autocomplete="off">
  <div id="themes">__CHIPS__</div>
</header>
<main id="liste">__CARTES__</main>
<footer>Généré le __DATE__ · __COUNT__ fiches · Bobine · Régénérer : python3 generate_page.py
<span class="signature">🎞️ écrit et réalisé par Wahid Rouhli · <a href="https://github.com/wrouhli/bobine">github.com/wrouhli/bobine</a></span></footer>
<script>
const ENTREES = __DATA__;
const norm = s => (s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
const esc = s => (s||"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let filtreTexte = "", themesActifs = new Set();

function tousThemes(){
  const m = new Map();
  for (const e of ENTREES) for (const t of (e.themes||[])) m.set(t,(m.get(t)||0)+1);
  return [...m.entries()].sort((a,b) => b[1]-a[1]);
}
function renderThemes(){
  const box = document.getElementById("themes");
  box.innerHTML = tousThemes().map(([t,n]) =>
    '<button class="chip'+(themesActifs.has(t)?" on":"")+'" data-t="'+esc(t)+'">'+esc(t)+' <b>'+n+'</b></button>').join("");
  box.querySelectorAll(".chip").forEach(c => c.onclick = () => {
    const t = c.dataset.t;
    themesActifs.has(t) ? themesActifs.delete(t) : themesActifs.add(t);
    render();
  });
}
function visible(e){
  if (themesActifs.size && !(e.themes||[]).some(t => themesActifs.has(t))) return false;
  if (!filtreTexte) return true;
  return norm([e.titre, e.auteur, e.contenu, (e.themes||[]).join(" ")].join(" ")).includes(filtreTexte);
}
function render(){
  renderThemes();
  const liste = ENTREES.filter(visible);
  document.getElementById("stats").textContent = liste.length + " / " + ENTREES.length;
  document.getElementById("liste").innerHTML = liste.length ? liste.map(e =>
    '<article class="card">' +
      '<h2><a href="'+esc(e.lien)+'" target="_blank" rel="noopener">'+esc(e.titre)+'</a></h2>' +
      '<div class="meta">'+esc(e.auteur)+'</div>' +
      '<div class="tags">'+(e.themes||[]).map(t => '<span class="tag">'+esc(t)+'</span>').join("")+'</div>' +
      '<p class="contenu">'+esc(e.contenu)+'</p>' +
    '</article>').join("") : '<p class="vide">Rien ne correspond…</p>';
}
document.getElementById("q").addEventListener("input", ev => {
  filtreTexte = norm(ev.target.value.trim());
  render();
});
// Le contenu est déjà en HTML statique (visible même sans JavaScript, ex.
// dans l'aperçu Fichiers d'iOS) : ici on ne fait qu'activer les interactions.
document.querySelectorAll("#themes .chip").forEach(c => c.onclick = () => {
  const t = c.dataset.t;
  themesActifs.has(t) ? themesActifs.delete(t) : themesActifs.add(t);
  render();
});
</script>
</body>
</html>
"""


TEMPLATE_GRAPHE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Vault — la carte</title>
<style>
  html, body { margin:0; height:100%; background:#14161d; overflow:hidden;
               font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  canvas { display:none; touch-action:none; }
  #statique { position:fixed; inset:0; width:100%; height:100%; }
  header { position:fixed; top:0; left:0; right:0; display:flex; align-items:baseline;
           gap:10px; padding:12px 16px; color:#e7eaf1; z-index:2; pointer-events:none; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header span { color:#8b93a5; font-size:13px; flex:1; }
  header a { pointer-events:auto; color:#5ea3ff; text-decoration:none; font-size:14px; font-weight:600; }
  #hint { position:fixed; bottom:28px; left:0; right:0; text-align:center; color:#6b7285;
          font-size:12px; z-index:2; pointer-events:none; }
  #signature { position:fixed; bottom:8px; left:0; right:0; text-align:center; color:#6b7285;
               font-size:11px; z-index:2; pointer-events:none; }
  #signature a { pointer-events:auto; color:#5ea3ff; text-decoration:none; }
  #zoom { position:fixed; right:14px; bottom:44px; display:flex; flex-direction:column;
          gap:8px; z-index:3; }
  #zoom button { width:34px; height:34px; border-radius:8px; border:1px solid #2a2f3d;
                 background:rgba(30,34,46,.85); color:#cfd5e2; font-size:18px; cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>La carte du Vault</h1><span id="stats">__STATS_G__</span>
  <a href="vault.html">← Liste</a>
</header>
<div id="zoom"><button id="zi">+</button><button id="zo">−</button></div>
<div id="hint">Glisse les points · pince pour zoomer · touche un point pour ouvrir le Reel</div>
<div id="signature">🎞️ écrit et réalisé par Wahid Rouhli · <a href="https://github.com/wrouhli/bobine">github.com/wrouhli/bobine</a></div>
<canvas id="c"></canvas>
__SVG__
<script>
const FICHES = __ENTREES__;
const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
/* JavaScript actif : la carte interactive remplace le rendu statique */
document.getElementById("statique").style.display = "none";
canvas.style.display = "block";
let dpr = 1, W = 0, H = 0;
let interacted = false;

/* ---- le graphe : une fiche = un petit point, un theme = un gros point ---- */
const nodes = [], edges = [], themeIdx = new Map();
FICHES.forEach(f => nodes.push({ label: f.titre, type: "fiche", url: f.lien,
                                 x: 0, y: 0, vx: 0, vy: 0, r: 6 }));
FICHES.forEach((f, i) => {
  (f.themes || []).forEach(t => {
    let j = themeIdx.get(t);
    if (j === undefined) {
      j = nodes.length; themeIdx.set(t, j);
      nodes.push({ label: t, type: "theme", x: 0, y: 0, vx: 0, vy: 0, r: 13 });
    }
    edges.push({ s: i, t: j });
  });
});

/* ---- position de départ : equilibre calcule a la generation (Python),
        sinon disposition en deux cercles ---- */
const POS = __POS__;
if (POS && POS.length === nodes.length) {
  nodes.forEach((n, i) => { n.x = POS[i][0]; n.y = POS[i][1]; });
} else {
  const nf = FICHES.length, nt = nodes.length - nf;
  nodes.forEach((n, i) => {
    const isTheme = n.type === "theme";
    const k = isTheme ? (i - nf) : i;
    const total = Math.max(1, isTheme ? nt : nf);
    const a = (k / total) * Math.PI * 2;
    const rad = isTheme ? 160 : 320;
    n.x = Math.cos(a) * rad;
    n.y = Math.sin(a) * rad;
  });
}
document.getElementById("stats").textContent =
  FICHES.length + " fiches · " + themeIdx.size + " thèmes";

/* ---- physique (leger : l'equilibre est deja calcule cote Python) ---- */
function step() {
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 1) { d2 = 1; dx = 0.7; dy = 0.4; }
      const d = Math.sqrt(d2), f = 4200 / d2;
      const fx = dx / d * f, fy = dy / d * f;
      a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
    }
  }
  for (const e of edges) {
    const a = nodes[e.s], b = nodes[e.t];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const f = (d - 115) * 0.028;
    const fx = dx / d * f, fy = dy / d * f;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  }
  for (const n of nodes) {
    n.vx += -n.x * 0.006; n.vy += -n.y * 0.006;
    n.vx *= 0.84; n.vy *= 0.84;
    n.x += n.vx; n.y += n.vy;
  }
}

/* ---- camera ---- */
let zoom = 1, panX = 0, panY = 0;
function applyZoom(f, cx, cy) {
  const nz = Math.min(2.6, Math.max(0.3, zoom * f));
  if (nz === zoom) return;
  const wx = (cx - W / 2 - panX) / zoom, wy = (cy - H / 2 - panY) / zoom;
  zoom = nz;
  panX = cx - W / 2 - wx * zoom;
  panY = cy - H / 2 - wy * zoom;
}
function fitTargets() {
  let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
  for (const n of nodes) {
    minX = Math.min(minX, n.x - n.r); maxX = Math.max(maxX, n.x + n.r);
    minY = Math.min(minY, n.y - n.r - 22); maxY = Math.max(maxY, n.y + n.r + 36);
  }
  const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
  const tz = Math.min(2.2, Math.max(0.35, Math.min((W - 100) / bw, (H - 200) / bh)));
  return [tz, -((minX + maxX) / 2) * tz, -((minY + maxY) / 2) * tz];
}
function fitView() {
  const t = fitTargets();
  zoom = t[0]; panX = t[1]; panY = t[2];
}
function toWorld(sx, sy) { return { x: (sx - W / 2 - panX) / zoom, y: (sy - H / 2 - panY) / zoom }; }
function hit(sx, sy) {
  const p = toWorld(sx, sy);
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i], dx = n.x - p.x, dy = n.y - p.y, rr = n.r + 9;
    if (dx * dx + dy * dy < rr * rr) return n;
  }
  return null;
}

/* ---- dessin ---- */
function draw() {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#14161d";
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(W / 2 + panX, H / 2 + panY);
  ctx.scale(zoom, zoom);
  ctx.strokeStyle = "rgba(150,160,180,0.22)";
  ctx.lineWidth = 1;
  for (const e of edges) {
    const a = nodes[e.s], b = nodes[e.t];
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  for (const n of nodes) {
    if (n.type === "theme") {
      ctx.shadowColor = "rgba(94,163,255,.85)"; ctx.shadowBlur = 18;
      ctx.fillStyle = "#5ea3ff";
    } else {
      ctx.shadowColor = "rgba(220,228,240,.45)"; ctx.shadowBlur = 8;
      ctx.fillStyle = "#d9dee8";
    }
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
  }
  ctx.textAlign = "center";
  for (const n of nodes) {
    if (n.type === "theme") {
      ctx.fillStyle = "#a5caff";
      ctx.font = "600 13px -apple-system,sans-serif";
      ctx.fillText(n.label, n.x, n.y - n.r - 7);
    } else if (zoom > 0.5 || nodes.length <= 14) {
      ctx.fillStyle = "#8d95a8";
      ctx.font = "11px -apple-system,sans-serif";
      const t = n.label.length > 44 ? n.label.slice(0, 43) + "…" : n.label;
      ctx.fillText(t, n.x, n.y + n.r + 15);
    }
  }
  ctx.restore();
}

/* ---- interactions ---- */
const pointers = new Map();
let dragNode = null, panning = false, pinchPrev = null, downX = 0, downY = 0;

canvas.addEventListener("pointerdown", e => {
  interacted = true;
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  downX = e.clientX; downY = e.clientY;
  if (pointers.size === 2) { dragNode = null; pinchPrev = null; }
  else {
    const n = hit(e.clientX, e.clientY);
    if (n) { dragNode = n; }
    else { panning = true; }
  }
});
canvas.addEventListener("pointermove", e => {
  if (!pointers.has(e.pointerId)) return;
  const prev = pointers.get(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    const pts = [...pointers.values()];
    const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    const cx = (pts[0].x + pts[1].x) / 2, cy = (pts[0].y + pts[1].y) / 2;
    if (pinchPrev && pinchPrev.d > 0) applyZoom(d / pinchPrev.d, cx, cy);
    pinchPrev = { d: d };
    return;
  }
  if (dragNode) {
    const p = toWorld(e.clientX, e.clientY);
    dragNode.x = p.x; dragNode.y = p.y;
    dragNode.vx = 0; dragNode.vy = 0;
  } else if (panning) {
    panX += e.clientX - prev.x;
    panY += e.clientY - prev.y;
  }
});
function endPointer(e) {
  if (!pointers.has(e.pointerId)) return;
  pointers.delete(e.pointerId);
  if (dragNode) {
    const moved = Math.hypot(e.clientX - downX, e.clientY - downY);
    if (moved < 6 && dragNode.type === "fiche" && dragNode.url) {
      window.open(dragNode.url, "_blank");
    }
    dragNode = null;
  }
  if (pointers.size === 0) { panning = false; pinchPrev = null; }
}
canvas.addEventListener("pointerup", endPointer);
canvas.addEventListener("pointercancel", endPointer);
canvas.addEventListener("wheel", e => {
  e.preventDefault();
  interacted = true;
  applyZoom(Math.exp(-e.deltaY * 0.0012), e.clientX, e.clientY);
}, { passive: false });
document.getElementById("zi").onclick = () => {
  interacted = true;
  applyZoom(1.35, W / 2, H / 2);
};
document.getElementById("zo").onclick = () => {
  interacted = true;
  applyZoom(1 / 1.35, W / 2, H / 2);
};

/* ---- demarrage ---- */
function resize() {
  dpr = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.width = W + "px"; canvas.style.height = H + "px";
}
window.addEventListener("resize", resize);
resize();
zoom = Math.max(0.5, Math.min(1, W / 800));
fitView();

let frames = 0;
function loop() {
  step(); draw();
  frames += 1;
  if (!interacted) {
    const t = fitTargets();
    zoom += (t[0] - zoom) * 0.12;
    panX += (t[1] - panX) * 0.12;
    panY += (t[2] - panY) * 0.12;
  }
  requestAnimationFrame(loop);
}
loop();
</script>
</body>
</html>
"""


def rendre_chips(entrees):
    """Pastilles de thèmes en HTML statique (triées par fréquence)."""
    comptes = {}
    for e in entrees:
        for t in e["themes"]:
            comptes[t] = comptes.get(t, 0) + 1
    paires = sorted(comptes.items(), key=lambda kv: -kv[1])
    return "".join(
        '<button class="chip" data-t="' + html.escape(t, quote=True) + '">'
        + html.escape(t) + ' <b>' + str(n) + '</b></button>'
        for t, n in paires
    )


def rendre_cartes(entrees):
    """Cartes des fiches en HTML statique (même balisage que la version JS)."""
    if not entrees:
        return '<p class="vide">Aucune fiche pour l\'instant.</p>'
    cartes = []
    for e in entrees:
        tags = "".join('<span class="tag">' + html.escape(t) + '</span>'
                       for t in e["themes"])
        cartes.append(
            '<article class="card">'
            '<h2><a href="' + html.escape(e["lien"], quote=True)
            + '" target="_blank" rel="noopener">' + html.escape(e["titre"])
            + '</a></h2>'
            '<div class="meta">' + html.escape(e["auteur"]) + '</div>'
            '<div class="tags">' + tags + '</div>'
            '<p class="contenu">' + html.escape(e["contenu"]) + '</p>'
            '</article>'
        )
    return "".join(cartes)


def svg_statique(entrees, pos):
    """Carte du graphe en SVG statique : visible même sans JavaScript (aperçu
    Fichiers/iOS) ; le canvas interactif la remplace quand JS tourne."""
    nb_fiches = len(entrees)
    theme_idx, aretes = {}, []
    for i, e in enumerate(entrees):
        for t in e["themes"]:
            if t not in theme_idx:
                theme_idx[t] = nb_fiches + len(theme_idx)
            aretes.append((i, theme_idx[t]))
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    minx, maxx = min(xs) - 70, max(xs) + 70
    miny, maxy = min(ys) - 90, max(ys) + 90
    parties = []
    for s0, t0 in aretes:
        x1, y1 = pos[s0]
        x2, y2 = pos[t0]
        parties.append('<line x1="' + str(x1) + '" y1="' + str(y1) + '" x2="'
                       + str(x2) + '" y2="' + str(y2)
                       + '" stroke="rgba(150,160,180,0.22)" stroke-width="1.5"/>')
    for i, e in enumerate(entrees):
        x, y = pos[i]
        parties.append('<a href="' + html.escape(e["lien"], quote=True)
                       + '" target="_blank"><circle cx="' + str(x) + '" cy="'
                       + str(y) + '" r="10" fill="#d9dee8"/></a>')
    for t, j in theme_idx.items():
        x, y = pos[j]
        parties.append('<circle cx="' + str(x) + '" cy="' + str(y)
                       + '" r="20" fill="#5ea3ff"/>')
        parties.append('<text x="' + str(x) + '" y="' + str(y - 30)
                       + '" fill="#a5caff" font-size="26" font-weight="600" '
                       'text-anchor="middle" '
                       'font-family="-apple-system,sans-serif">'
                       + html.escape(t) + '</text>')
    return ('<svg id="statique" xmlns="http://www.w3.org/2000/svg" viewBox="'
            + str(int(minx)) + ' ' + str(int(miny)) + ' '
            + str(int(maxx - minx)) + ' ' + str(int(maxy - miny))
            + '" preserveAspectRatio="xMidYMid meet">'
            + "".join(parties) + '</svg>')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    args = ap.parse_args()
    vault = Path(args.vault)

    cfg = lire_config(Path(__file__).resolve().parent, vault)
    nom = cfg.get("NOM") or NOM_DEFAUT
    nom_html = html.escape(nom)
    carte = cfg.get("CARTE", "oui").strip().lower() not in ("non", "no", "n", "0", "false")
    sync_icloud = cfg.get("SYNC_ICLOUD", "oui").strip().lower() not in ("non", "no", "n", "0", "false")
    icloud = Path.home() / "Library/Mobile Documents" / ("com~apple~CloudDocs/" + nom)

    entrees = lire_index(vault / "index.md")
    donnees = json.dumps(entrees, ensure_ascii=False).replace("<", "\\u003c")

    lien_carte = ' <a href="graph.html">Carte &#128376;</a>'
    page = (TEMPLATE_LISTE
            .replace("__DATA__", donnees)
            .replace("__CARTES__", rendre_cartes(entrees))
            .replace("__CHIPS__", rendre_chips(entrees))
            .replace("__STATS__", str(len(entrees)) + " / " + str(len(entrees)))
            .replace("__DATE__", datetime.now().strftime("%d/%m/%Y %H:%M"))
            .replace("__COUNT__", str(len(entrees)))
            .replace("Vault — mes Reels sauvegardés", nom_html + " — mes Reels sauvegardés"))
    if not carte:
        page = page.replace(lien_carte, "")
    (vault / "vault.html").write_text(page, encoding="utf-8")
    print(f"vault.html généré — {len(entrees)} fiches")

    if carte and entrees:
        pos = positions_initiales(entrees)
        nb_themes = len({t for e in entrees for t in e["themes"]})
        graphe = (TEMPLATE_GRAPHE
                  .replace("__ENTREES__", donnees)
                  .replace("__POS__", json.dumps(pos))
                  .replace("__SVG__", svg_statique(entrees, pos))
                  .replace("__STATS_G__", str(len(entrees)) + " fiches · "
                           + str(nb_themes) + " thèmes")
                  .replace("La carte du Vault", "La carte du " + nom_html)
                  .replace("Vault — la carte", nom_html + " — la carte"))
        (vault / "graph.html").write_text(graphe, encoding="utf-8")
        print("graph.html généré — la carte du graphe")
    elif not carte:
        print("carte désactivée (CARTE=non dans config.env)")

    # Copie iCloud (pour l'iPhone) : uniquement vault.html, et seulement quand
    # on génère bien le Vault principal (= le dossier de ce script). Le graph
    # reste sur le Mac (décision utilisateur : pas besoin sur l'iPhone).
    if sys.platform != "darwin":
        print("copie iCloud ignorée (macOS uniquement).")
    elif not sync_icloud:
        print("copie iCloud désactivée (SYNC_ICLOUD=non dans config.env).")
    elif vault.resolve() == Path(__file__).resolve().parent:
        try:
            icloud.mkdir(parents=True, exist_ok=True)
            (icloud / "vault.html").write_text(page.replace(lien_carte, ""), encoding="utf-8")
            print(f"copie iCloud : {icloud} (vault.html seulement)")
        except OSError as e:
            print(f"copie iCloud impossible : {e}")
    else:
        print("vault différent du dossier du script — pas de copie iCloud (test ou usage local).")


if __name__ == "__main__":
    main()
