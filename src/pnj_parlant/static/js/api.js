// Appels au serveur, communs aux deux pages et à univers.js : serveur injoignable signalé dans le bandeau
// (requete, js/bandeau.js), erreurs du serveur rendues en français.
import { requete, signaler } from "./bandeau.js";

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

// Requête JSON : GET sans corps, POST avec (ou `method`). options : panne (voir lireReponse), signal, headers.
export async function api(path, body, method = body === undefined ? "GET" : "POST", { panne = false, signal, headers } = {}) {
  const opts = { method, headers: { "Content-Type": "application/json", ...headers }, signal };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return lireReponse(await requete(path, opts), { panne });
}
