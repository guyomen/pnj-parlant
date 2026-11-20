// Mode MJ, commun aux deux pages : bouton « MJ » à droite de la barre du haut. En mode MJ, « Préparer l’univers »
// apparaît et la page Options montre tous les réglages du serveur ; sinon (mode joueur), les options de ce
// navigateur et l'état de la machine seulement. Le mode est gardé le temps de l'onglet (sessionStorage) et posé
// sur <html data-mj> (avant l'affichage par js/tete.js : pas de flash). C'est un confort d'affichage : le serveur
// garde ses propres contrôles (mot de passe du MJ, routes @mj).
import { requete } from "./bandeau.js";
import { demanderMotDePasse, garderMdp, lireReponse, mdpMJ } from "./api.js";

export const CLE_MODE = "mode-mj";
export const EVENEMENT = "mode-mj";  // émis sur document au changement de mode (detail : actif)

const MESSAGE_CONNEXION = "Mot de passe du MJ :";
const MESSAGE_INCORRECT = "Mot de passe du MJ incorrect. Réessayez :";
export const MESSAGE_SANS_MDP = "Aucun mot de passe du MJ n’est défini : le mode MJ ne s’ouvre que depuis le PC "
  + "du serveur (définissez-en un dans les options, sur ce PC, pour l’ouvrir depuis un autre appareil).";

export function modeMJ() {
  try { return globalThis.sessionStorage?.getItem(CLE_MODE) === "1"; } catch { return false; }
}

// Pose le mode (gardé, affiché, annoncé) ; le quitter oublie aussi le mot de passe du MJ
export function poserModeMJ(actif) {
  try {
    if (actif) globalThis.sessionStorage.setItem(CLE_MODE, "1");
    else globalThis.sessionStorage.removeItem(CLE_MODE);
  } catch { /* stockage refusé : le mode vaut pour cette page seulement */ }
  if (!actif) garderMdp("");
  afficherModeMJ(actif);
  const doc = globalThis.document;
  doc?.dispatchEvent?.(new CustomEvent(EVENEMENT, { detail: actif }));
}

// Comment ouvrir le mode MJ d'après /api/acces {protege, local} : "mot_de_passe" (un mot de passe existe : il
// est demandé, même sur le PC), "libre" (pas de mot de passe, PC du serveur) ou "impossible" (autre appareil).
export function ouvertureMJ(acces) {
  if (acces.protege) return "mot_de_passe";
  return acces.local ? "libre" : "impossible";
}

// Le mode gardé vaut-il encore ? (mot de passe ajouté ou retiré depuis, mot de passe oublié après un refus)
export function modeEncoreValide(acces, mdp) {
  const ouverture = ouvertureMJ(acces);
  return ouverture === "libre" || (ouverture === "mot_de_passe" && !!mdp);
}

// Ouvre le mode MJ : {ok, message?}. Le mot de passe (gardé s'il y en a un, sinon demandé) est vérifié par
// /api/reglages/verifier, qui l'exige même sur le PC du serveur ; jusqu'à « Annuler » (ok faux, sans message).
export async function connecterMJ() {
  const acces = await lireReponse(await requete("/api/acces"));
  const ouverture = ouvertureMJ(acces);
  if (ouverture === "impossible") return { ok: false, message: MESSAGE_SANS_MDP };
  if (ouverture === "libre") { poserModeMJ(true); return { ok: true }; }
  let mdp = mdpMJ(), message = MESSAGE_CONNEXION;
  for (;;) {
    if (!mdp) mdp = await demanderMotDePasse(message);
    if (!mdp) return { ok: false };
    const r = await requete("/api/reglages/verifier", { method: "POST", headers: { "Content-Type": "application/json" },
                                                         body: JSON.stringify({ mot_de_passe: mdp }) });
    if (r.ok) { garderMdp(mdp); poserModeMJ(true); return { ok: true }; }
    garderMdp("");
    if (r.status !== 403) {  // trop d'essais (429), panne : le message du serveur
      const d = await r.json().catch(() => ({}));
      return { ok: false, message: d.error || `Erreur serveur (${r.status})` };
    }
    mdp = "";
    message = MESSAGE_INCORRECT;
  }
}

// --- Bouton de la barre du haut (DOM par globalThis.document) -------------------------------------------
function afficherModeMJ(actif) {
  const doc = globalThis.document;
  if (!doc?.documentElement) return;
  doc.documentElement.toggleAttribute("data-mj", actif);
  const b = doc.getElementById("mjBtn");
  if (!b) return;
  b.setAttribute("aria-pressed", String(actif));
  b.title = actif ? "Mode MJ : cliquer pour revenir en mode joueur" : "Se connecter en MJ";
}

// Relie le bouton « MJ » ; `signaler(message)` affiche un refus. Au chargement, le mode gardé est revérifié
// (sans rien demander) : il est quitté s'il ne vaut plus.
export function initBoutonMJ({ signaler = () => {} } = {}) {
  const b = globalThis.document.getElementById("mjBtn");
  afficherModeMJ(modeMJ());
  b.addEventListener("click", async () => {
    if (modeMJ()) { poserModeMJ(false); return; }
    b.disabled = true;
    try {
      const r = await connecterMJ();
      if (r.message) signaler(r.message);
    } catch (e) { signaler(e.message); }
    b.disabled = false;
  });
  if (modeMJ()) {
    requete("/api/acces").then(lireReponse)
      .then((acces) => { if (!modeEncoreValide(acces, mdpMJ())) poserModeMJ(false); })
      .catch(() => {});
  }
}
