// Univers (scénario, lieux, PNJ de la banque) : chargement d'un exemple, d'un zip ou d'un dossier, export en zip.
// Partagé par l'accueil (index.html) et la page de préparation (creation.html).

export const URL_EXPORT = "/api/scenario/export";

// --- Thème graphique du scénario -----------------------------------------------------
// Couleurs définies dans style.css ([data-theme=...]) ; le premier est le thème par défaut.
export const THEMES = [
  { id: "vert-de-gris", nom: "Vert-de-gris", resume: "Verre ancien et cire rouge" },
  { id: "parchemin", nom: "Parchemin", resume: "Taverne, cuir et laiton" },
  { id: "sylve", nom: "Sylve", resume: "Forêt féerique, mousse et baies" },
  { id: "givre", nom: "Givre", resume: "Contrées du nord, glace et sang" },
  { id: "donjon", nom: "Donjon", resume: "Pierre et torches, toujours sombre" },
];
export const THEME_DEFAUT = THEMES[0].id;
const CLE_THEME = "theme";  // gardé dans le navigateur : appliqué dès le chargement, avant la réponse du serveur

// Pose le thème sur la page (identifiant inconnu ou vide : thème par défaut) et le garde pour la prochaine fois
export function appliquerTheme(id) {
  const theme = THEMES.some(t => t.id === id) ? id : THEME_DEFAUT;
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(CLE_THEME, theme); } catch {}
  return theme;
}

// Thème du scénario enregistré sur le serveur (après le chargement, ou après un import d'univers)
export async function chargerTheme() {
  const s = await fetch("/api/scenario").then(r => r.json()).catch(() => null);
  return s ? appliquerTheme(s.theme) : document.documentElement.dataset.theme;
}

// Fichiers utiles d'une sélection (zip, ou fichiers .json d'un dossier choisi avec webkitdirectory)
export const fichiersImportables = (fichiers) => [...fichiers].filter(f => /\.(json|zip)$/i.test(f.name));

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
