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
import urllib.parse
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
<title>Vault — mes vidéos sauvegardées</title>
<link rel="icon" href="__FAVICON__">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f6f5f2">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#14111f">
<style>
  /* ---- jetons de couleurs : clair par défaut ---- */
  :root{
    --bg:#f6f5f2; --glow:none; --sticky:rgba(246,245,242,.9);
    --panel:#ffffff; --line:#e9e4dc;
    --ink:#1d1a24; --ink2:#57535f; --ink3:#8b8694;
    --violet:#6c4dff;
    --chipbg:transparent; --chipborder:#e9e4dc; --chipcolor:#57535f;
    --chiponbg:#1d1a24; --chiponcolor:#ffffff;
    --tagbg:#fbfaf8; --tagborder:#e9e4dc; --tagcolor:#57535f;
    --fieldbg:#ffffff; --fieldborder:#e9e4dc; --focusring:rgba(108,77,255,.10);
    --btnactive:rgba(29,26,36,.08);
    --filmdash:rgba(29,26,36,.10);
    --cardshadow:0 8px 26px rgba(29,26,36,.07);
    --cardhoverborder:#ded7cc;
    --mark:rgba(108,77,255,.18);
  }
  /* ---- jetons : sombre explicite ---- */
  :root[data-theme="dark"]{
    --bg:#14111f; --glow:radial-gradient(900px 320px at 50% -140px, rgba(108,77,255,.20), transparent 70%);
    --sticky:rgba(20,17,31,.9);
    --panel:rgba(255,255,255,.04); --line:rgba(255,255,255,.075);
    --ink:#efeaf9; --ink2:#b9b0d8; --ink3:#8079a2;
    --violet:#8b6dff;
    --chipbg:rgba(124,92,255,.13); --chipborder:rgba(139,109,255,.28); --chipcolor:#cfc6ff;
    --chiponbg:#8b6dff; --chiponcolor:#0f0c1d;
    --tagbg:rgba(255,255,255,.05); --tagborder:rgba(255,255,255,.075); --tagcolor:#b9b0d8;
    --fieldbg:rgba(255,255,255,.05); --fieldborder:rgba(255,255,255,.075); --focusring:rgba(108,77,255,.18);
    --btnactive:rgba(255,255,255,.12);
    --filmdash:rgba(255,255,255,.13);
    --cardshadow:none; --cardhoverborder:rgba(139,109,255,.38);
    --mark:rgba(139,109,255,.30);
  }
  /* ---- jetons : sombre système (sauf si l'utilisateur a forcé clair/sombre) ---- */
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --bg:#14111f; --glow:radial-gradient(900px 320px at 50% -140px, rgba(108,77,255,.20), transparent 70%);
      --sticky:rgba(20,17,31,.9);
      --panel:rgba(255,255,255,.04); --line:rgba(255,255,255,.075);
      --ink:#efeaf9; --ink2:#b9b0d8; --ink3:#8079a2;
      --violet:#8b6dff;
      --chipbg:rgba(124,92,255,.13); --chipborder:rgba(139,109,255,.28); --chipcolor:#cfc6ff;
      --chiponbg:#8b6dff; --chiponcolor:#0f0c1d;
      --tagbg:rgba(255,255,255,.05); --tagborder:rgba(255,255,255,.075); --tagcolor:#b9b0d8;
      --fieldbg:rgba(255,255,255,.05); --fieldborder:rgba(255,255,255,.075); --focusring:rgba(108,77,255,.18);
      --btnactive:rgba(255,255,255,.12);
      --filmdash:rgba(255,255,255,.13);
      --cardshadow:none; --cardhoverborder:rgba(139,109,255,.38);
      --mark:rgba(139,109,255,.30);
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--glow),var(--bg);color:var(--ink);
    font:15px/1.6 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,Roboto,sans-serif;
    -webkit-font-smoothing:antialiased}
  ::selection{background:var(--mark)}
  :focus-visible{outline:2px solid var(--violet);outline-offset:2px;border-radius:8px}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important; animation:none !important} }
  .wrap{max-width:1240px;margin:0 auto;padding:0 28px 64px}
  .tete{position:sticky;top:0;z-index:5;background:var(--sticky);
    backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);padding:18px 0 6px}
  header.top{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
  .brand{font-size:15px;font-weight:600;letter-spacing:.01em;white-space:nowrap}
  .brand .reel{color:var(--violet);margin-right:7px;position:relative;top:2px}
  .brand .sub{color:var(--ink3);font-weight:400;margin-left:8px}
  .search{position:relative;flex:1 1 260px;max-width:480px}
  .search svg{position:absolute;left:13px;top:50%;transform:translateY(-50%);opacity:.5}
  .search input{width:100%;padding:10px 13px 10px 38px;font-family:inherit;font-size:16px;color:var(--ink);
    background:var(--fieldbg);border:1px solid var(--fieldborder);border-radius:11px;outline:none;
    transition:border-color .15s,box-shadow .15s}
  .search input::placeholder{color:var(--ink3)}
  .search input:focus{border-color:var(--violet);box-shadow:0 0 0 4px var(--focusring)}
  .topright{display:flex;align-items:center;gap:14px;font-size:13px;color:var(--ink3);margin-left:auto}
  .topright a{color:var(--violet);text-decoration:none;font-weight:500}
  .topright a:hover{text-decoration:underline;text-underline-offset:3px}
  .theme{display:flex;gap:2px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:2px}
  .tbtn{width:27px;height:24px;display:grid;place-items:center;border:0;background:transparent;
    border-radius:7px;color:var(--ink3);cursor:pointer;padding:0}
  .tbtn:hover{color:var(--ink)}
  .tbtn.on{background:var(--btnactive);color:var(--ink)}
  .chips{display:flex;gap:8px;overflow-x:auto;padding:4px 0 10px;margin-top:10px;scrollbar-width:none}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:0 0 auto;font:inherit;font-size:12.5px;color:var(--chipcolor);background:var(--chipbg);
    border:1px solid var(--chipborder);border-radius:999px;padding:3px 11px;cursor:pointer;transition:all .12s}
  .chip .n{opacity:.6;font-size:.85em;margin-left:2px}
  .chip:hover{border-color:var(--violet)}
  .chip.on{background:var(--chiponbg);border-color:transparent;color:var(--chiponcolor);font-weight:600}
  .film{height:9px;margin:0 0 22px;
    background-image:repeating-linear-gradient(90deg, var(--filmdash) 0 11px, transparent 11px 24px);
    -webkit-mask:linear-gradient(90deg, transparent, #000 10%, #000 90%, transparent);
    mask:linear-gradient(90deg, transparent, #000 10%, #000 90%, transparent)}
  .mois{grid-column:1/-1;display:flex;align-items:center;gap:14px;margin:26px 0 0;
    font-size:12px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
  .mois::after{content:"";flex:1;height:1px;background:var(--line)}
  .grid > .mois:first-child{margin-top:8px}
  .grid > .vide{grid-column:1/-1}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px}
  .carte{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:16px;
    padding:18px 20px 14px;display:flex;flex-direction:column;gap:9px;
    transition:transform .15s,border-color .15s,box-shadow .15s}
  .carte:hover{transform:translateY(-2px);border-color:var(--cardhoverborder);box-shadow:var(--cardshadow)}
  .carte h2{font-size:16.5px;line-height:1.4;letter-spacing:-.008em;margin:0;font-weight:620;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .carte h2 a{color:inherit;text-decoration:none}
  .carte h2 a:hover{color:var(--violet)}
  .carte h2 a::after{content:"";position:absolute;inset:0;border-radius:16px}
  .carte h2 .ext{font-size:.68em;color:var(--violet);opacity:.6;margin-left:4px;vertical-align:super}
  .meta{font-size:12.5px;color:var(--ink3);display:flex;align-items:center;flex-wrap:wrap}
  .meta .pf{display:inline-flex;margin-right:6px;color:var(--ink3)}
  .meta .pf svg{display:block}
  .meta .date{opacity:.75}
  .meta .sep{margin:0 7px;opacity:.5}
  .res{margin:0;color:var(--ink2);font-size:14px;line-height:1.58;
    display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}
  mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 1px}
  .tags{margin-top:auto;padding-top:6px;display:flex;flex-wrap:wrap;gap:6px}
  .tag{position:relative;z-index:1;font:inherit;font-size:11.5px;color:var(--tagcolor);background:var(--tagbg);
    border:1px solid var(--tagborder);border-radius:999px;padding:2px 9px;cursor:pointer}
  .tag:hover{border-color:var(--violet);color:var(--violet)}
  .vide{color:var(--ink3);padding:30px 0;font-size:14px}
  footer{margin-top:46px;padding-top:18px;border-top:1px solid var(--line);
    color:var(--ink3);font-size:12.5px;text-align:center;line-height:2}
  footer code{font-size:12px;background:var(--tagbg);border:1px solid var(--tagborder);padding:1px 6px;border-radius:6px}
  footer .sig{color:var(--ink2)}
  @media (max-width:640px){
    .wrap{padding:0 18px 48px}
    .tete{padding-top:14px}
    .brand .sub{display:none}
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="tete">
    <header class="top">
      <div class="brand">
        <svg class="reel" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="2.1" fill="currentColor" stroke="none"/><circle cx="12" cy="5.7" r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="18.3" r="1.5" fill="currentColor" stroke="none"/><circle cx="5.7" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="18.3" cy="12" r="1.5" fill="currentColor" stroke="none"/></svg>Bobine<span class="sub">mes vidéos sauvegardées</span>
      </div>
      <div class="search">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.2-3.2"/></svg>
        <input id="q" type="search" placeholder="Rechercher (titre, contenu, auteur)…" autocomplete="off" aria-label="Rechercher dans les fiches">
      </div>
      <div class="topright">
        <span id="stats">__STATS__</span><a href="graph.html">Carte</a>
        <div class="theme" role="group" aria-label="Thème">
          <button type="button" class="tbtn" data-m="light" title="Clair" aria-label="Thème clair"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12h2.5M19 12h2.5M5 5l1.8 1.8M17.2 17.2L19 19M19 5l-1.8 1.8M6.8 17.2L5 19"/></svg></button>
          <button type="button" class="tbtn" data-m="dark" title="Sombre" aria-label="Thème sombre"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11Z"/></svg></button>
          <button type="button" class="tbtn" data-m="system" title="Système" aria-label="Thème système"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 0 0 17Z" fill="currentColor" stroke="none"/></svg></button>
        </div>
      </div>
    </header>
    <div class="chips" id="chips">__CHIPS__</div>
  </div>
  <div class="film"></div>
  <div id="liste" class="grid">__GROUPES__</div>
  <p class="vide" id="vide" style="display:none">Aucune fiche ne correspond. Essaie un autre mot ou enlève le filtre.</p>
  <footer>Généré le __DATE__ · __COUNT__ fiches · Bobine · Régénérer : <code>python3 generate_page.py</code><br>
  <span class="sig">🎞️ écrit et réalisé par Wahid Rouhli · <a href="https://github.com/wrouhli/bobine">github.com/wrouhli/bobine</a></span></footer>
</div>
<script>
(function(){
  /* ---- thème : clair / sombre / système ---- */
  var racine = document.documentElement;
  var tbtns = [].slice.call(document.querySelectorAll(".tbtn"));
  var CLE = "bobine-theme";
  var force = null;
  try { force = new URLSearchParams(location.search).get("theme"); } catch (e) {}
  function choisirTheme(mode, sauver){
    if (mode === "system") { racine.removeAttribute("data-theme"); }
    else { racine.setAttribute("data-theme", mode); }
    tbtns.forEach(function(b){
      var on = b.dataset.m === mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (sauver) { try { localStorage.setItem(CLE, mode); } catch (e) {} }
  }
  var initial = "system";
  if (force === "light" || force === "dark") { initial = force; }
  else { try { var v = localStorage.getItem(CLE); if (v === "light" || v === "dark" || v === "system") { initial = v; } } catch (e) {} }
  choisirTheme(initial, false);
  tbtns.forEach(function(b){ b.addEventListener("click", function(){ choisirTheme(b.dataset.m, true); }); });

  /* ---- recherche, filtres, surlignage ---- */
  var q = document.getElementById("q");
  var stats = document.getElementById("stats");
  var vide = document.getElementById("vide");
  var cartes = [].slice.call(document.querySelectorAll(".carte"));
  var moisBlocs = [].slice.call(document.querySelectorAll(".mois"));
  var pastilles = [].slice.call(document.querySelectorAll(".chip, .tag"));
  var actifs = {};
  var total = cartes.length;
  function norm(s){ return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  function esc(s){ return (s || "").replace(/[&<>"']/g, function(c){ return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]; }); }
  function surligner(texte, requete){
    var t = esc(texte);
    if (!requete) { return t; }
    var motif = esc(requete).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    try { return t.replace(new RegExp("(" + motif + ")", "gi"), "<mark>$1</mark>"); }
    catch (e) { return t; }
  }
  function nombreActifs(){ var n = 0; for (var t in actifs) { if (actifs[t]) { n++; } } return n; }
  function appliquer(){
    var requete = (q.value || "").trim();
    var vus = 0;
    cartes.forEach(function(c){
      var okTexte = !requete || norm(c.dataset.text).indexOf(norm(requete)) !== -1;
      var themes = c.dataset.themes ? c.dataset.themes.split("|") : [];
      var okTheme = nombreActifs() === 0 || themes.some(function(t){ return actifs[t]; });
      var ok = okTexte && okTheme;
      c.style.display = ok ? "" : "none";
      if (ok) { vus++; }
      var titre = c.querySelector("h2 .tt");
      var res = c.querySelector(".res");
      if (titre) { titre.innerHTML = surligner(c.dataset.titre || "", requete); }
      if (res) { res.innerHTML = surligner(c.dataset.contenu || "", requete); }
    });
    moisBlocs.forEach(function(m){
      var visible = false;
      var n = m.nextElementSibling;
      while (n && !n.classList.contains("mois")) {
        if (n.classList.contains("carte") && n.style.display !== "none") { visible = true; break; }
        n = n.nextElementSibling;
      }
      m.style.display = visible ? "" : "none";
    });
    stats.textContent = vus + " / " + total + " fiches";
    vide.style.display = vus ? "none" : "";
    pastilles.forEach(function(p){
      var on = !!actifs[p.dataset.t];
      p.classList.toggle("on", on);
      p.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  pastilles.forEach(function(p){
    p.addEventListener("click", function(){
      var t = p.dataset.t;
      if (actifs[t]) { delete actifs[t]; } else { actifs[t] = true; }
      appliquer();
    });
  });
  q.addEventListener("input", appliquer);
  document.addEventListener("keydown", function(ev){
    if (ev.key === "/" && document.activeElement !== q) { ev.preventDefault(); q.focus(); }
  });
  appliquer();
})();
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
<div id="hint">Glisse les points · pince pour zoomer · touche un point pour ouvrir la vidéo</div>
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


MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
               "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def dates_des_fiches(vault):
    """{url: 'AAAA-MM-JJ'} : la date de traitement de chaque fiche, lue dans raw/.

    C'est la source de la date affichée sur la page (« sauvegardée le… ») :
    elle existe déjà dans l'en-tête de chaque fiche (traite_le), y compris
    pour celles indexées avant l'arrivée des dates sur la page.
    """
    dates = {}
    dossier = Path(vault) / "raw"
    if not dossier.is_dir():
        return dates
    for fichier in sorted(dossier.glob("*.md")):
        if fichier.name.startswith("."):
            continue
        try:
            lignes = fichier.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        source, traite = "", ""
        for ligne in lignes[:40]:
            if ligne.startswith("---") and (source or traite):
                break
            if ligne.startswith("source:"):
                source = ligne.split(":", 1)[1].strip()
            elif ligne.startswith("traite_le:"):
                traite = ligne.split(":", 1)[1].strip()
        if source and traite:
            dates[normaliser_lien(source)] = traite
    return dates


def normaliser_lien(lien):
    """Clé de rapprochement fiche ↔ index : sans paramètres de suivi ni ancre.

    Instagram ajoute des paramètres (?stkn=…) qui changent d'un partage à
    l'autre : on les ignore des deux côtés pour que la bonne fiche (et donc
    la bonne date) soit toujours retrouvée.
    """
    l = (lien or "").strip()
    for coupe in ("?", "#"):
        if coupe in l:
            l = l.split(coupe, 1)[0]
    return l.rstrip("/")


def plateforme_de(lien):
    """Identifie la plateforme d'un lien (pour le petit glyphe des cartes)."""
    l = (lien or "").lower()
    if "youtube.com" in l or "youtu.be" in l:
        return "youtube"
    if "instagram.com" in l:
        return "instagram"
    if "tiktok.com" in l:
        return "tiktok"
    return ""


GLYPHES = {
    "youtube": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="2.6" y="5.4" width="18.8" height="13.2" rx="4"/><path d="M10.4 9.4l4.6 2.6-4.6 2.6z" fill="currentColor" stroke="none"/></svg>',
    "instagram": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.4" cy="6.6" r="1.2" fill="currentColor" stroke="none"/></svg>',
    "tiktok": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M14.8 4v9.4a3.7 3.7 0 1 1-2.8-3.57"/><path d="M14.8 4c.4 2.3 1.9 3.8 4.1 4"/></svg>',
}


def glyphe_plateforme(cle):
    """Le petit glyphe de plateforme (vide si inconnue)."""
    if cle not in GLYPHES:
        return ""
    return '<span class="pf" aria-hidden="true">' + GLYPHES[cle] + '</span>'


def libelle_mois(date_iso):
    """'2026-10-08' → 'Octobre 2026' (vide si la date manque)."""
    try:
        annee, mois = date_iso.split("-")[0], int(date_iso.split("-")[1])
        return MOIS_LONGS[mois - 1].capitalize() + " " + annee
    except (ValueError, IndexError):
        return ""


def formater_date(date_iso):
    """'2026-10-08' → '8 oct. 2026' (vide si la date manque)."""
    try:
        annee, mois, jour = date_iso.split("-")
        return str(int(jour)) + " " + MOIS_COURTS[int(mois) - 1] + " " + annee
    except (ValueError, IndexError):
        return ""


def preparer_entrees(entrees, vault):
    """Ajoute date + plateforme à chaque entrée, puis trie : récentes d'abord."""
    dates = dates_des_fiches(vault)
    for e in entrees:
        e["date"] = dates.get(normaliser_lien(e["lien"]), "")
        e["plateforme"] = plateforme_de(e["lien"])
    entrees.sort(key=lambda e: e["date"] or "", reverse=True)
    return entrees


def favicon():
    """Petite bobine violette, encodée en data URI (onglet + écran d'accueil)."""
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
           "<rect width='64' height='64' rx='14' fill='#6c4dff'/>"
           "<circle cx='32' cy='32' r='17' fill='none' stroke='#ffffff' stroke-width='6'/>"
           "<circle cx='32' cy='32' r='5.5' fill='#ffffff'/>"
           "<circle cx='32' cy='13.5' r='4' fill='#ffffff'/>"
           "<circle cx='32' cy='50.5' r='4' fill='#ffffff'/>"
           "<circle cx='13.5' cy='32' r='4' fill='#ffffff'/>"
           "<circle cx='50.5' cy='32' r='4' fill='#ffffff'/>"
           "</svg>")
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe="")


def rendre_chips(entrees):
    """Pastilles de thèmes en HTML statique (triées par fréquence)."""
    comptes = {}
    for e in entrees:
        for t in e["themes"]:
            comptes[t] = comptes.get(t, 0) + 1
    paires = sorted(comptes.items(), key=lambda kv: (-kv[1], kv[0]))
    return "".join(
        '<button type="button" class="chip" data-t="' + html.escape(t, quote=True)
        + '" aria-pressed="false">' + html.escape(t)
        + ' <span class="n">' + str(n) + '</span></button>'
        for t, n in paires
    )


def rendre_carte(e):
    """Une carte de fiche en HTML statique (visible même sans JavaScript)."""
    date = formater_date(e.get("date", ""))
    meta = glyphe_plateforme(e.get("plateforme", "")) + "<span>" + html.escape(e["auteur"]) + "</span>"
    if date:
        meta += '<span class="sep">·</span><span class="date">' + html.escape(date) + "</span>"
    tags = "".join(
        '<button type="button" class="tag" data-t="' + html.escape(t, quote=True)
        + '" aria-pressed="false">' + html.escape(t) + "</button>"
        for t in e["themes"]
    )
    texte_filtre = " ".join([e["titre"], e["auteur"], e["contenu"]] + e["themes"])
    return (
        '<article class="carte" data-themes="' + html.escape("|".join(e["themes"]), quote=True)
        + '" data-text="' + html.escape(texte_filtre, quote=True)
        + '" data-titre="' + html.escape(e["titre"], quote=True)
        + '" data-contenu="' + html.escape(e["contenu"], quote=True) + '">'
        + "<h2 title=\"" + html.escape(e["titre"], quote=True) + '">'
        + '<a href="' + html.escape(e["lien"], quote=True) + '" target="_blank" rel="noopener">'
        + '<span class="tt">' + html.escape(e["titre"]) + '</span><span class="ext">↗</span></a></h2>'
        + '<div class="meta">' + meta + "</div>"
        + '<p class="res">' + html.escape(e["contenu"]) + "</p>"
        + '<div class="tags">' + tags + "</div>"
        + "</article>"
    )


def rendre_liste(entrees):
    """Les cartes dans la grille, précédées d'un séparateur de mois (récentes d'abord)."""
    if not entrees:
        return ('<p class="vide">Aucune fiche pour l\'instant. '
                "Partage une vidéo depuis ton téléphone : elle apparaîtra ici.</p>")
    parties = []
    mois_courant = None
    for e in entrees:
        mois = libelle_mois(e.get("date", "")) or ""
        if mois and mois != mois_courant:
            parties.append('<div class="mois">' + html.escape(mois) + "</div>")
        mois_courant = mois
        parties.append(rendre_carte(e))
    return "".join(parties)


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
    entrees = preparer_entrees(entrees, vault)   # dates (via raw/), plateforme, tri récentes d'abord
    donnees = json.dumps(entrees, ensure_ascii=False).replace("<", "\\u003c")

    lien_carte = '<a href="graph.html">Carte</a>'
    page = (TEMPLATE_LISTE
            .replace("__FAVICON__", favicon())
            .replace("__GROUPES__", rendre_liste(entrees))
            .replace("__CHIPS__", rendre_chips(entrees))
            .replace("__STATS__", str(len(entrees)) + " / " + str(len(entrees)))
            .replace("__DATE__", datetime.now().strftime("%d/%m/%Y %H:%M"))
            .replace("__COUNT__", str(len(entrees)))
            .replace("Vault — mes vidéos sauvegardées", nom_html + " — mes vidéos sauvegardées"))
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
