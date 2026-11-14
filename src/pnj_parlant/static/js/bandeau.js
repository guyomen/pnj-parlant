// Bandeau d'alertes sous la barre du haut, commun aux deux pages (élément #bandeau) :
// - problèmes du serveur (/api/sante) : dépendance absente, moteur injoignable, clé manquante… ;
// - erreurs des actions : serveur injoignable, moteur indisponible, micro refusé, synthèse en échec…
// Chaque alerte se ferme d'un clic ; une alerte du serveur fermée ne revient pas de l'onglet (sauf si son message
// change). Logique pure (fusion des alertes) dans scene.js, testée.
import { ajouterAlerte, alertesSante, esc } from "./scene.js";

const CLE_FERMEES = "alertes-fermees";  // sessionStorage : « clé|message » des alertes du serveur fermées
export const SERVEUR_INJOIGNABLE = "Serveur injoignable : vérifiez qu’il tourne toujours (fenêtre de lancer.bat "
  + "ou terminal), puis rechargez la page.";
let alertes = [];

const fermees = () => { try { return JSON.parse(sessionStorage.getItem(CLE_FERMEES) || "[]"); } catch { return []; } };

function afficher() {
  const zone = document.getElementById("bandeau");
  if (!zone) return;
  zone.hidden = !alertes.length;
  zone.innerHTML = alertes.map(a => `
    <div class="alerte ${a.niveau === "erreur" ? "erreur" : "avertissement"}">
      <p><strong>${a.niveau === "erreur" ? "Erreur" : "Attention"} :</strong> ${esc(a.message)}</p>
      <button type="button" class="fermer" data-fermer="${esc(a.cle)}" aria-label="Fermer ce message" title="Fermer">×</button>
    </div>`).join("");
}

// Affiche une alerte (niveau « erreur » ou « avertissement ») ; même clé : elle remplace la précédente
export function signaler(message, { cle = message, niveau = "erreur" } = {}) {
  alertes = ajouterAlerte(alertes, { cle, niveau, message });
  afficher();
}

export function retirer(cle) {
  if (!alertes.some(a => a.cle === cle)) return;
  alertes = alertes.filter(a => a.cle !== cle);
  afficher();
}

// fetch qui signale un serveur injoignable (et retire l'alerte dès qu'il répond de nouveau)
export async function requete(url, options) {
  try {
    const r = await fetch(url, options);
    retirer("serveur");
    return r;
  } catch (e) {
    if (e.name === "AbortError") throw e;  // requête annulée (Stop) : pas une panne
    signaler(SERVEUR_INJOIGNABLE, { cle: "serveur" });
    throw new Error(SERVEUR_INJOIGNABLE);
  }
}

// Problèmes du serveur : remplacent ceux du dernier diagnostic
export async function verifierSante() {
  let r;
  try { r = await requete("/api/sante"); } catch { return; }
  const d = r.ok ? await r.json().catch(() => null) : null;
  if (!d) return;
  alertes = alertesSante(alertes, d.problemes, fermees());
  afficher();
}

document.addEventListener("click", (e) => {
  const cle = e.target.closest?.("[data-fermer]")?.dataset.fermer;
  if (!cle) return;
  const a = alertes.find(x => x.cle === cle);
  if (a?.cle.startsWith("sante:")) {
    try { sessionStorage.setItem(CLE_FERMEES, JSON.stringify([...fermees(), `${a.cle}|${a.message}`])); } catch {}
  }
  retirer(cle);
});
