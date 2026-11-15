// Appels au serveur, communs aux deux pages et à univers.js : serveur injoignable signalé dans le bandeau
// (requete, js/bandeau.js), erreurs du serveur rendues en français, mot de passe du MJ demandé quand il le faut.
import { requete, signaler } from "./bandeau.js";

// --- Mot de passe du MJ -------------------------------------------------------------------------------
// Hors du PC du serveur, modifier l'univers (et voir les secrets des PNJ et les notes du MJ) demande le mot de
// passe du MJ. Gardé le temps de l'onglet (sessionStorage, la même clé que la page Options), envoyé dans l'en-tête
// X-Mot-De-Passe-MJ, encodé : un en-tête n'admet pas d'accents (le serveur le décode).
export const CLE_MDP = "mdp-mj";
export const EN_TETE_MDP = "X-Mot-De-Passe-MJ";
export function mdpMJ() {
  try { return globalThis.sessionStorage?.getItem(CLE_MDP) || ""; } catch { return ""; }
}
export function garderMdp(mdp) {
  try { if (mdp) globalThis.sessionStorage.setItem(CLE_MDP, mdp); else globalThis.sessionStorage.removeItem(CLE_MDP); }
  catch { /* stockage refusé : le mot de passe sera redemandé */ }
}
export const enTeteMdp = (mdp = mdpMJ()) => (mdp ? { [EN_TETE_MDP]: encodeURIComponent(mdp) } : {});

const MESSAGE_MDP = "Modifier l’univers depuis cet appareil demande le mot de passe du MJ.";
const MESSAGE_INCORRECT = "Mot de passe du MJ incorrect. Réessayez :";

// Fenêtre du mot de passe (<dialog>) : renvoie le mot de passe saisi, ou null (Annuler, Échap). Remplaçable par
// poserDialogueMdp (tests). Une seule fenêtre à la fois : les demandes simultanées attendent la même réponse.
let dialogueMdp = (message) => new Promise((resolve) => {
  const doc = globalThis.document;
  if (!doc?.body || !doc.createElement("dialog").showModal) { resolve(null); return; }
  const d = doc.createElement("dialog");
  d.className = "dialogue-mdp";
  d.innerHTML = `<form method="dialog">
      <p></p>
      <label>Mot de passe du MJ <input type="password" autocomplete="current-password" required></label>
      <div class="actions"><button type="button" class="ghost">Annuler</button>
      <button value="ok">Valider</button></div>
    </form>`;
  d.querySelector("p").textContent = message;
  d.querySelector("button.ghost").onclick = () => d.close("");  // Entrée valide (premier bouton d'envoi)
  d.addEventListener("close", () => {
    const saisi = d.returnValue === "ok" ? d.querySelector("input").value : "";
    d.remove();
    resolve(saisi || null);
  });
  doc.body.append(d);
  d.showModal();
});
export function poserDialogueMdp(fn) { dialogueMdp = fn; }
let demandeEnCours = null;
export function demanderMotDePasse(message = MESSAGE_MDP) {
  demandeEnCours ??= Promise.resolve(dialogueMdp(message)).finally(() => { demandeEnCours = null; });
  return demandeEnCours;
}

// Requête avec le mot de passe du MJ gardé ; un 403 qui demande le mot de passe (`mot_de_passe` dans la réponse)
// l'oublie, ouvre la fenêtre et renvoie la requête avec le nouveau, jusqu'à « Annuler » (la réponse 403 est alors
// rendue). Le corps doit pouvoir être renvoyé (texte JSON, FormData). `message` : question de la première demande.
export async function envoyer(path, opts = {}, { message = MESSAGE_MDP } = {}) {
  for (;;) {
    const envoye = mdpMJ();
    const r = await requete(path, { ...opts, headers: { ...opts.headers, ...enTeteMdp(envoye) } });
    if (r.status !== 403) return r;
    const data = await (r.clone ? r.clone() : r).json().catch(() => ({}));
    if (!data.mot_de_passe) return r;
    if (mdpMJ() === envoye) garderMdp("");
    else if (mdpMJ()) continue;  // un autre appel vient d'en faire saisir un : on l'essaie
    const saisi = await demanderMotDePasse(envoye ? MESSAGE_INCORRECT : message);
    if (!saisi) return r;
    garderMdp(saisi);
  }
}

// Droits de cet appareil sur l'univers (/api/acces : {mj, protege, local}) ; si un mot de passe existe et que
// l'appareil ne l'a pas (ou plus : un mot de passe refusé est oublié), il est demandé (`demander`) jusqu'à
// « Annuler ». Lève une erreur en français (serveur injoignable, trop d'essais).
export async function verifierAcces({ demander = true, message = MESSAGE_MDP } = {}) {
  for (;;) {
    const envoye = mdpMJ();
    const acces = await lireReponse(await requete("/api/acces", { headers: enTeteMdp(envoye) }));
    if (acces.mj || !acces.protege) return acces;
    if (envoye && mdpMJ() === envoye) garderMdp("");
    if (!demander) return acces;
    const saisi = await demanderMotDePasse(envoye ? MESSAGE_INCORRECT : message);
    if (!saisi) return acces;
    garderMdp(saisi);
  }
}

// --- Requêtes --------------------------------------------------------------------------------------------
// Corps JSON d'une réponse ; erreur (message du serveur, sinon « Erreur serveur (code) ») si elle a échoué.
// panne : les erreurs 5xx (moteur indisponible, portrait impossible…) vont aussi au bandeau.
export async function lireReponse(r, { panne = false } = {}) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const message = data.error || `Erreur serveur (${r.status})`;
    if (panne && r.status >= 500) signaler(message);
    throw new Error(message);
  }
  return data;
}

// Requête JSON : GET sans corps, POST avec (ou `method`). options : panne (voir lireReponse), signal, headers,
// message (question du mot de passe). Passe par envoyer : mot de passe du MJ joint, et demandé si le serveur le réclame.
export async function api(path, body, method = body === undefined ? "GET" : "POST", { panne = false, signal, headers, message } = {}) {
  const opts = { method, headers: { "Content-Type": "application/json", ...headers }, signal };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return lireReponse(await envoyer(path, opts, message ? { message } : {}), { panne });
}
