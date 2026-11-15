// Onglet Apparence de la page de préparation (creation.html), sans DOM : ce que partagent l'éditeur de thème et
// l'éditeur de style de portrait (origine prédéfinie, modifiée ou créée ; textes de suppression et de rétablissement),
// et les palettes d'un thème en cours d'édition.
import { THEMES, alertesContraste } from "./univers.js";

// Mention de l'origine d'un thème ou d'un style dans sa carte
export const mention = (origine) => ({ perso: " · créé pour l’univers", modifie: " · modifié pour l’univers" }[origine] ?? "");

// Styles de portrait propres à l'univers ({id: {nom, resume, prompt}}), à renvoyer dans PUT /api/styles, depuis la
// liste complète de GET /api/styles (prédéfinis compris)
export const portraitsPerso = (liste) => Object.fromEntries(liste.filter(st => st.origine !== "predefini")
  .map(st => [st.id, { nom: st.nom, resume: st.resume, prompt: st.prompt }]));

// Bouton de l'éditeur, question et message après coup : un prédéfini modifié est rétabli, un créé est supprimé.
// type : "theme" ou "style".
const MOTS = {
  theme: { le: "le thème", Le: "Thème", origine: "les couleurs d’origine", retrouve: "ses couleurs d’origine" },
  style: { le: "le style", Le: "Style", origine: "le style d’origine", retrouve: "sa description d’origine" },
};
export const libelleSuppression = (type, origine) =>
  origine === "modifie" ? `Rétablir ${type === "theme" ? "le thème" : "le style"} d’origine` : "Supprimer";
export const confirmationSuppression = (type, origine, nom) =>
  origine === "modifie" ? `Rétablir ${MOTS[type].origine} de « ${nom} » ?` : `Supprimer ${MOTS[type].le} « ${nom} » ?`;
export const messageSuppression = (type, origine, nom) =>
  origine === "modifie" ? `« ${nom} » a retrouvé ${MOTS[type].retrouve}.` : `${MOTS[type].Le} « ${nom} » supprimé.`;

// Palettes d'un thème selon son mode : les deux pour « auto », sinon la seule utilisée
export const palettesDuMode = (mode) => mode === "auto" ? ["clair", "sombre"] : [mode];

// Thème en cours d'édition, à partir d'un thème existant (`id`) ou du thème choisi par le scénario (nouveau thème) :
// {edition: {id (null : nouveau), origine, mode, clair, sombre}, base}. Palettes copiées (l'aperçu les modifie).
export function editionDeTheme(tous, id, themeChoisi) {
  const base = id ? tous.find(t => t.id === id) : tous.find(t => t.id === themeChoisi) ?? THEMES[0];
  const edition = { id: id ?? null, origine: id ? base.origine : "perso", mode: base.mode,
                    clair: { ...(base.clair ?? THEMES[0].clair) }, sombre: { ...(base.sombre ?? THEMES[0].sombre) } };
  return { edition, base };
}

// Thème à enregistrer : nom, résumé, mode, et seulement les palettes de ce mode
export function themeEdite({ nom, resume, mode }, edition) {
  const t = { nom: nom.trim(), resume: resume.trim(), mode };
  for (const palette of palettesDuMode(mode)) t[palette] = { ...edition[palette] };
  return t;
}

// Alertes de lisibilité des palettes du thème (contraste trop faible), en texte
export const alertesPalettes = (t) => palettesDuMode(t.mode).flatMap(p => alertesContraste(t[p])
  .map(a => `Palette ${p === "clair" ? "claire" : "sombre"} : ${a.quoi} peu lisible (contraste `
    + `${a.ratio.toFixed(1).replace(".", ",")}, ${String(a.seuil).replace(".", ",")} conseillé).`));
