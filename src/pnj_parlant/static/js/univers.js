// Univers (scénario, lieux, PNJ de la banque) : chargement d'un exemple, d'un zip ou d'un dossier, export en zip.
// Partagé par l'accueil (index.html) et la page de préparation (creation.html).

export const URL_EXPORT = "/api/scenario/export";

// --- Thème graphique du scénario -----------------------------------------------------
// Thèmes prédéfinis : les mêmes couleurs que style.css ([data-theme=...], vérifié par les tests JS), ici pour
// l'éditeur de thèmes. Le premier est le thème par défaut. mode : "auto" (clair ou sombre selon l'appareil),
// "sombre" ou "clair" (une seule palette).
export const THEMES = [
  { id: "vert-de-gris", nom: "Vert-de-gris", resume: "Verre ancien et cire rouge", mode: "auto",
    clair: { bg: "#dce3db", surface: "#eef2ec", ink: "#18241f", muted: "#4d5f57", line: "#b9c7bd", glass: "#2f5d50", verdigris: "#6fa392", wax: "#9b2d2a", "wax-ink": "#fbefea" },
    sombre: { bg: "#121a17", surface: "#1c2723", ink: "#dce3db", muted: "#9db0a6", line: "#2e3d37", glass: "#7db8a6", verdigris: "#4f8a7b", wax: "#c0443f", "wax-ink": "#fff4f0" } },
  { id: "parchemin", nom: "Parchemin", resume: "Taverne, cuir et laiton", mode: "auto",
    clair: { bg: "#e9dfc9", surface: "#f6efdf", ink: "#2b2118", muted: "#6b5a48", line: "#d3c2a0", glass: "#7a4a1e", verdigris: "#b08a4a", wax: "#8e2a22", "wax-ink": "#fbefea" },
    sombre: { bg: "#1c1712", surface: "#27201a", ink: "#ede3cf", muted: "#b3a38a", line: "#3b3129", glass: "#d9a86a", verdigris: "#a07e44", wax: "#b4483a", "wax-ink": "#fff4ec" } },
  { id: "sylve", nom: "Sylve", resume: "Forêt féerique, mousse et baies", mode: "auto",
    clair: { bg: "#e1e9d6", surface: "#f2f6ea", ink: "#1d2617", muted: "#56644b", line: "#c2cfb1", glass: "#3f6b2a", verdigris: "#a88a2e", wax: "#7b3f8c", "wax-ink": "#f8effa" },
    sombre: { bg: "#11170e", surface: "#1a2316", ink: "#e3ead9", muted: "#a2b094", line: "#2c3826", glass: "#9bc77e", verdigris: "#c9a84e", wax: "#93509f", "wax-ink": "#fbf2fd" } },
  { id: "givre", nom: "Givre", resume: "Contrées du nord, glace et sang", mode: "auto",
    clair: { bg: "#dce4eb", surface: "#eef3f7", ink: "#16212b", muted: "#4c5d6c", line: "#b6c5d2", glass: "#2c5878", verdigris: "#7aa6c2", wax: "#9b2d3a", "wax-ink": "#fbeef0" },
    sombre: { bg: "#0f151b", surface: "#18212a", ink: "#dde5ec", muted: "#98a9b8", line: "#2a3744", glass: "#86b6d6", verdigris: "#4f7f9e", wax: "#b83c50", "wax-ink": "#fff1f3" } },
  { id: "donjon", nom: "Donjon", resume: "Pierre et torches, toujours sombre", mode: "sombre",
    sombre: { bg: "#131315", surface: "#1d1d21", ink: "#e4e1da", muted: "#a19c92", line: "#34343a", glass: "#e0a050", verdigris: "#9c6b2e", wax: "#b23a2e", "wax-ink": "#fff1e8" } },
];
export const THEME_DEFAUT = THEMES[0].id;
// Variables de couleur d'un thème, dans l'ordre de l'éditeur
export const COULEURS = [["bg", "Fond"], ["surface", "Cartes"], ["ink", "Texte"], ["muted", "Texte secondaire"],
  ["line", "Traits"], ["glass", "Couleur principale"], ["verdigris", "Couleur d’appoint"], ["wax", "Sceau « Parler »"],
  ["wax-ink", "Texte du sceau"]];
const CLE_THEME = "theme", CLE_CSS = "theme-css";  // gardés dans le navigateur : posés avant l'affichage

// Tous les thèmes proposés : prédéfinis (origine « predefini », ou « modifie » si l'univers les a changés),
// puis ceux de l'univers (« perso »). perso : {id: thème} de /api/styles.
export function tousLesThemes(perso = {}) {
  return [...THEMES.map(t => perso[t.id] ? { ...perso[t.id], id: t.id, origine: "modifie" } : { ...t, origine: "predefini" }),
          ...Object.entries(perso).filter(([id]) => !THEMES.some(t => t.id === id))
            .map(([id, t]) => ({ ...t, id, origine: "perso" }))];
}

// CSS des thèmes de l'univers. Sélecteurs un cran plus précis que ceux de style.css (html[…], body […]) :
// ils l'emportent même placés avant lui dans la page ; « body […] » sert aux aperçus de la page de préparation.
const variables = (p) => COULEURS.map(([c]) => `--${c}: ${p[c]};`).join(" ");
const OMBRE = { clair: "0 1px 2px rgb(24 36 31 / .06), 0 4px 14px rgb(24 36 31 / .05)",
                sombre: "0 1px 2px rgb(0 0 0 / .25), 0 4px 14px rgb(0 0 0 / .18)" };
const bloc = (sel, nom, p) => `${sel} { color-scheme: ${nom === "sombre" ? "dark" : "light"}; ${variables(p)} --ombre: ${OMBRE[nom]}; }`;
export function cssThemes(perso = {}) {
  return Object.entries(perso).map(([id, t]) => {
    if (!/^[a-z0-9-]{1,40}$/.test(id)) return "";
    const sel = `html[data-theme="${id}"], body [data-theme="${id}"]`;
    if (t.mode !== "auto") return bloc(sel, t.mode, t[t.mode]);
    return `${bloc(sel, "clair", t.clair)}\n@media (prefers-color-scheme: dark) { ${bloc(sel, "sombre", t.sombre)} }`;
  }).filter(Boolean).join("\n");
}

// Contraste WCAG entre deux couleurs « #rrggbb » (1 à 21 ; 4,5 au moins pour un texte courant)
export function contraste(a, b) {
  const lum = (h) => {
    const [r, g, bl] = [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
      .map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// Couples de couleurs d'une palette dont le texte serait peu lisible (contraste < 4,5)
const PAIRES = [["ink", "bg", "Texte sur le fond"], ["muted", "surface", "Texte secondaire sur les cartes"],
                ["surface", "glass", "Texte des boutons"], ["wax-ink", "wax", "Texte du sceau « Parler »"]];
export const alertesContraste = (p) => PAIRES.map(([a, b, quoi]) => ({ quoi, ratio: contraste(p[a], p[b]) }))
  .filter(x => x.ratio < 4.5);

// Identifiant d'un nouveau thème ou style d'après son nom, différent de ceux de `pris`
export function identifiant(nom, pris) {
  const base = String(nom).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 34) || "perso";
  let id = base;
  for (let n = 2; pris.includes(id); n++) id = `${base}-${n}`;
  return id;
}

let themesPerso = {};  // thèmes de l'univers, posés par poserThemesPerso

// Pose le CSS des thèmes de l'univers dans la page ; garder : aussi pour le prochain chargement (sinon : aperçu)
export function poserThemesPerso(perso, garder = true) {
  if (garder) themesPerso = perso;
  let style = document.getElementById("themes-perso");
  if (!style) {
    style = Object.assign(document.createElement("style"), { id: "themes-perso" });
    document.head.appendChild(style);
  }
  style.textContent = cssThemes(perso);
  if (garder) try { localStorage.setItem(CLE_CSS, style.textContent); } catch {}
}

// Pose le thème sur la page (identifiant inconnu ou vide : thème par défaut) et le garde pour la prochaine fois
export function appliquerTheme(id) {
  const theme = tousLesThemes(themesPerso).some(t => t.id === id) ? id : THEME_DEFAUT;
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(CLE_THEME, theme); } catch {}
  return theme;
}

// Thème du scénario et thèmes de l'univers enregistrés sur le serveur (au chargement, ou après un import)
export async function chargerTheme() {
  const [s, st] = await Promise.all([fetch("/api/scenario"), fetch("/api/styles")]
    .map(p => p.then(r => r.json()).catch(() => null)));
  if (st) poserThemesPerso(st.themes ?? {});
  return s ? appliquerTheme(s.theme) : document.documentElement.dataset.theme;
}

// Fichiers utiles d'une sélection (zip, ou fiches .json et portraits d'un dossier choisi avec webkitdirectory)
export const fichiersImportables = (fichiers) => [...fichiers].filter(f => /\.(json|zip|png|jpe?g|webp)$/i.test(f.name));

const pluriel = (n, mot, s = "s") => `${n} ${mot}${n > 1 ? s : ""}`;

// Message après un import : r = réponse de /api/scenario/import ou /api/exemples/<id>
export function resumeImport(r) {
  const parties = [pluriel(r.lieux, "lieu", "x"), pluriel(r.pnj, "PNJ", "")];
  let texte = `Univers chargé : ${parties.join(" et ")}${r.scenario ? "" : ", sans texte d’univers"}.`;
  if (r.ignores?.length) texte += ` Fichiers ignorés : ${r.ignores.join(", ")}.`;
  return texte;
}

// Univers chargé, pour l'accueil
export const resumeUnivers = (nbLieux, nbPnj) => nbLieux || nbPnj
  ? `Univers actuel : ${pluriel(nbLieux, "lieu", "x")} et ${pluriel(nbPnj, "PNJ", "")}.`
  : "Aucun univers chargé : chargez-en un ci-dessous, ou créez le vôtre.";

// Question posée avant une nouvelle table (tout l'univers et la conversation sont supprimés)
export const confirmationNouvelleTable = (nbLieux, nbPnj) =>
  `Nouvelle table : le texte de l’univers, son thème, ${pluriel(nbLieux, "lieu", "x")} et `
  + `${pluriel(nbPnj, "PNJ", "")} de la banque seront supprimés, ainsi que la conversation en cours. `
  + "Exportez d’abord l’univers (page de préparation) pour le garder. Continuer ?";

// Question posée avant d'écraser la banque (nbPnj : PNJ actuellement enregistrés)
export function confirmationImport(nbPnj, garder) {
  return garder
    ? "Le texte de l’univers et les lieux seront remplacés ; les PNJ importés s’ajouteront à ceux de la banque. Continuer ?"
    : `L’univers, les lieux et ${pluriel(nbPnj, "PNJ", "")} de la banque seront remplacés. `
      + "Exportez d’abord l’univers actuel pour le garder. Continuer ?";
}

async function reponse(r) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Erreur serveur (${r.status})`);
  return data;
}

export async function importerFichiers(fichiers, garder) {
  const form = new FormData();
  for (const f of fichiersImportables(fichiers)) form.append("fichiers", f, f.name);
  form.append("remplacer", garder ? "0" : "1");
  return reponse(await fetch("/api/scenario/import", { method: "POST", body: form }));
}

export async function chargerExemple(id, garder) {
  return reponse(await fetch(`/api/exemples/${encodeURIComponent(id)}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ remplacer: !garder }) }));
}

export function exporter() {
  const a = document.createElement("a");
  a.href = URL_EXPORT;
  a.download = "";
  a.click();
}
