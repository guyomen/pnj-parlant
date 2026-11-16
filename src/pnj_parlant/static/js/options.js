// Vue Options de la page de jeu (index.html, « #options ») : rubriques, réglages du serveur (écrits dans
// config.toml et appliqués à chaud, mot de passe du MJ), état de la machine. Chargé par js/jeu.js, qui fournit la
// configuration de la partie et son rechargement (initOptions).
import { esc, groupeUtile, resumeModifs, valeurReglage } from "./scene.js";
import { requete, verifierSante } from "./bandeau.js";
import { api, enTeteMdp, garderMdp, lireReponse, mdpMJ } from "./api.js";

const $ = (id) => document.getElementById(id);
// config() : /api/config lu par la partie ; chargerConfig() : la relit (moteurs changés)
const deps = { config: () => ({}), chargerConfig: async () => {} };
export function initOptions({ config, chargerConfig }) {
  deps.config = config;
  deps.chargerConfig = chargerConfig;
}

// Ouverture de la vue : réglages relus (sauf modifications en attente), état de la machine, diagnostic
export function ouvrirOptions() {
  if (!Object.keys(modifsReglages).length) chargerReglages();
  refreshSys();
  verifierSante();
}

// --- Options : rubriques ---------------------------------------------------------------------------
// Un bouton par rubrique (carte de la colonne de droite) : il y fait défiler la page
function construireNav() {
  const cartes = [...document.querySelectorAll(".options-contenu > section[id]")];
  const intercalaires = { "opt-partie": "Ce navigateur", "opt-serveur": "Le serveur", "opt-machine": "État" };
  $("optionsNav").innerHTML = cartes.map(c => (intercalaires[c.id] ? `<span class="sep">${intercalaires[c.id]}</span>` : "")
    + `<button type="button" data-aller="${c.id}">${esc(c.dataset.titre)}</button>`).join("");
}
$("optionsNav").onclick = (e) => {
  const id = e.target.closest("[data-aller]")?.dataset.aller;
  if (!id) return;
  document.getElementById(id).scrollIntoView({ behavior: "smooth", block: "start" });
  for (const b of $("optionsNav").querySelectorAll("button")) b.classList.toggle("actif", b.dataset.aller === id);
};
construireNav();

// --- Options : réglages du serveur (écrits dans config.toml, appliqués aussitôt) --------------------
// /api/reglages : {groupes: [{id, titre, aide, si, reglages: [{cle, libelle, type, valeur, choix…}]}], protege, local}.
// Les modifications s'accumulent (modifsReglages) jusqu'à « Enregistrer ». Mot de passe du MJ : gardé le temps
// de l'onglet (sessionStorage, js/api.js : le même sert à modifier l'univers), envoyé dans l'en-tête X-Mot-De-Passe-MJ.
let reglagesServeur = null;
let modifsReglages = {};  // clé → nouvelle valeur ; secret : null = à effacer
const peutModifier = () => !!reglagesServeur && (reglagesServeur.protege ? !!mdpMJ() : reglagesServeur.local);
const tousLesReglages = () => reglagesServeur?.groupes.flatMap(g => g.reglages) ?? [];
const reglageDe = (cle) => tousLesReglages().find(r => r.cle === cle);
const idChamp = (cle) => `r-${cle.replaceAll(".", "-")}`;
const valeursCourantes = () => Object.fromEntries(tousLesReglages().map(r => [r.cle, r.cle in modifsReglages ? modifsReglages[r.cle] : r.valeur]));

function messageOptions(texte, erreur = false) {
  $("reglagesMessage").textContent = texte;
  $("reglagesMessage").classList.toggle("erreur", erreur);
}

async function chargerReglages() {
  try { reglagesServeur = await api("/api/reglages"); }
  catch (e) { $("acces").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  modifsReglages = {};
  afficherReglages();
}

function controle(reglage) {
  // valeur en attente d'enregistrement, s'il y en a une : la page réaffichée montre ce qui sera enregistré
  const r = reglage.type !== "secret" && reglage.cle in modifsReglages ? { ...reglage, valeur: modifsReglages[reglage.cle] } : reglage;
  const id = idChamp(r.cle), attr = `id="${id}" data-cle="${esc(r.cle)}"${peutModifier() ? "" : " disabled"}`;
  switch (r.type) {
    case "booleen":
      return `<input type="checkbox" role="switch" class="interrupteur" ${attr}${r.valeur ? " checked" : ""}>`;
    case "choix":
      return `<select ${attr}>${r.choix.map(([v, nom]) =>
        `<option value="${esc(v)}"${v === r.valeur ? " selected" : ""}>${esc(nom)}</option>`).join("")}</select>`;
    case "entier": case "nombre":
      return `<input type="number" inputmode="decimal" ${attr} value="${esc(r.valeur)}" min="${r.min}" max="${r.max}" step="${r.pas ?? (r.type === "entier" ? 1 : "any")}">`;
    case "secret":
      return `<input type="password" autocomplete="new-password" ${attr} placeholder="${r.defini ? "défini (vide : inchangé)" : "non défini"}">`
        + (r.defini ? `<button class="ghost petit" data-effacer="${esc(r.cle)}"${peutModifier() ? "" : " disabled"}>Effacer</button>` : "");
    default: {
      const liste = r.suggestions?.length
        ? `<datalist id="${id}-liste">${r.suggestions.map(x => `<option value="${esc(x)}">`).join("")}</datalist>` : "";
      return `<input type="${r.type === "url" ? "url" : "text"}" ${attr} value="${esc(r.valeur)}"${liste ? ` list="${id}-liste"` : ""}>${liste}`;
    }
  }
}

function afficherReglages() {
  const valeurs = valeursCourantes();
  $("fichierConfig").textContent = reglagesServeur.fichier ?? "en mémoire";
  $("reglagesServeur").innerHTML = reglagesServeur.groupes.map(g => `
    <section class="carte groupe" id="opt-g-${esc(g.id)}" data-titre="${esc(g.titre)}" data-groupe="${esc(g.id)}">
      <div class="tete-groupe"><h2>${esc(g.titre)}</h2><span class="etiquette" data-inutile hidden>non utilisé</span></div>
      ${g.aide ? `<p class="aide-groupe">${esc(g.aide)}</p>` : ""}
      ${g.reglages.map(r => `
      <div class="reglage${r.type === "booleen" ? " bool" : ""}" data-ligne="${esc(r.cle)}">
        <label class="texte" for="${idChamp(r.cle)}"><strong>${esc(r.libelle)}${r.redemarrage ? ` <span class="etiquette">au redémarrage</span>` : ""}</strong>${r.aide ? `<small>${esc(r.aide)}</small>` : ""}</label>
        <div class="controle">${controle(r)}</div>
      </div>`).join("")}
    </section>`).join("");
  majUtilite(valeurs);
  afficherAcces();
  majBarreReglages();
  construireNav();
}

// Groupes des moteurs non choisis : en retrait (toujours modifiables)
function majUtilite(valeurs = valeursCourantes()) {
  for (const g of reglagesServeur.groupes) {
    const carte = document.getElementById(`opt-g-${g.id}`), utile = groupeUtile(g, valeurs);
    carte.classList.toggle("inutile", !utile);
    carte.querySelector("[data-inutile]").hidden = utile;
  }
}

function afficherAcces() {
  const d = reglagesServeur;
  const fichier = d.fichier ? `Enregistrés dans <code>${esc(d.fichier)}</code> et appliqués aussitôt.` : "Appliqués aussitôt.";
  if (d.protege && mdpMJ()) {
    $("acces").innerHTML = `<p><strong>Déverrouillé.</strong> ${fichier}</p><button class="ghost petit" id="verrouiller">Verrouiller</button>`;
  } else if (d.protege) {
    $("acces").innerHTML = `<p>Protégés par le mot de passe du MJ.</p>
      <form id="formMdp"><input type="password" id="mdpSaisi" placeholder="Mot de passe du MJ" aria-label="Mot de passe du MJ"
        autocomplete="current-password"><button>Déverrouiller</button></form>`;
  } else if (d.local) {
    $("acces").innerHTML = `<p>Modifiables depuis ce PC. ${fichier} Pour les modifier depuis un autre appareil, définissez un mot de passe du MJ (rubrique Serveur).</p>`;
  } else {
    $("acces").innerHTML = `<p>Lecture seule : sans mot de passe du MJ, ces réglages ne se modifient que depuis le PC du serveur.</p>`;
  }
}
$("acces").addEventListener("submit", async (e) => {
  e.preventDefault();
  const mdp = $("mdpSaisi").value;
  try {
    await api("/api/reglages/verifier", { mot_de_passe: mdp });
    garderMdp(mdp);
    messageOptions("");
    afficherReglages();
  } catch (err) { messageOptions(err.message, true); }
});
$("acces").addEventListener("click", (e) => {
  if (e.target.id !== "verrouiller") return;
  garderMdp("");
  modifsReglages = {};  // verrouillé : elles ne pourraient plus être enregistrées
  messageOptions("");
  afficherReglages();
});

function majBarreReglages() {
  const n = Object.keys(modifsReglages).length;
  $("barreReglages").hidden = !n;
  $("reglagesNb").textContent = resumeModifs(n);
  for (const ligne of document.querySelectorAll("[data-ligne]")) ligne.classList.toggle("modifie", ligne.dataset.ligne in modifsReglages);
}

function noterChangement(e) {
  const cle = e.target.dataset.cle;
  if (!cle) return;
  const r = reglageDe(cle), v = valeurReglage(r.type, e.target);
  if (r.type === "secret") { if (v) modifsReglages[cle] = v; else delete modifsReglages[cle]; }
  else if (v === null || v === r.valeur) {
    delete modifsReglages[cle];
    // nombre vidé ou illisible : en quittant le champ, il reprend la valeur enregistrée (rien n'est en attente)
    if (v === null && e.type === "change") e.target.value = r.valeur;
  }
  else modifsReglages[cle] = v;
  if (cle.startsWith("moteurs.")) majUtilite();
  messageOptions("");
  majBarreReglages();
}
$("reglagesServeur").addEventListener("input", noterChangement);
$("reglagesServeur").addEventListener("change", noterChangement);
$("reglagesServeur").addEventListener("click", (e) => {
  const cle = e.target.dataset.effacer;
  if (!cle) return;
  modifsReglages[cle] = null;
  const champ = document.getElementById(idChamp(cle));
  champ.value = "";
  champ.placeholder = "sera effacé à l’enregistrement";
  majBarreReglages();
});
$("reglagesAnnuler").onclick = () => { modifsReglages = {}; afficherReglages(); messageOptions(""); };
$("reglagesEnregistrer").onclick = async () => {
  const changements = { ...modifsReglages };
  $("reglagesEnregistrer").disabled = true;
  let refuse = false;
  try {
    const r = await requete("/api/reglages", { method: "PUT", body: JSON.stringify({ changements }),
      headers: { "Content-Type": "application/json", ...enTeteMdp() } });
    refuse = r.status === 403;
    if (refuse) garderMdp("");
    const d = await lireReponse(r);
    if ("serveur.mot_de_passe_mj" in changements) garderMdp(changements["serveur.mot_de_passe_mj"] || "");
    reglagesServeur = d;
    modifsReglages = {};
    afficherReglages();
    messageOptions(`Enregistré${d.fichier ? ` dans ${d.fichier}` : ""} et appliqué.`
      + (d.redemarrage.length ? ` Au prochain démarrage du serveur : ${d.redemarrage.join(", ")}.` : ""));
    deps.chargerConfig();
    refreshSys();
    verifierSante();
  } catch (err) {
    // mot de passe refusé : champs verrouillés, modifications gardées (à enregistrer une fois déverrouillé)
    if (refuse) afficherReglages();
    messageOptions(err.message, true);
  }
  $("reglagesEnregistrer").disabled = false;
};
window.addEventListener("beforeunload", (e) => { if (Object.keys(modifsReglages).length) e.preventDefault(); });

// --- Options : état de la machine ---------------------------------------------------------------
const ligneSys = (titre, texte, alerte = false) =>
  `<div class="ligne"><span>${esc(titre)}</span><span${alerte ? ' class="alert"' : ""}>${texte}</span></div>`;
export async function refreshSys() {
  const box = $("sys");
  const cfg = deps.config();
  try {
    const e = await api("/api/etat");
    const m = cfg.moteurs ?? {};
    let h = ligneSys("Création", esc(m.creation ?? "—")) + ligneSys("Dialogues", esc(m.dialogue ?? "—"))
      + ligneSys("Voix", cfg.tts ? esc(cfg.tts) : "voix du navigateur")
      + ligneSys("Reconnaissance", cfg.stt_local ? "sur ce PC" : "navigateur")
      + ligneSys("Portraits", cfg.portraits ? esc(cfg.portraits === "local" ? "sur ce PC" : "en ligne") : "aucun");
    if (e.ollama) {
      h += e.ollama.ok
        ? ligneSys("Ollama", `actif — ${e.ollama.charges.length ? e.ollama.charges.map(x => `${esc(x.nom)} (${x.vram_mo} Mo en mémoire vidéo)`).join(", ") : "aucun modèle chargé"}`)
        : ligneSys("Ollama", "ne répond pas : démarrez-le (lancer.bat le fait sous Windows ; sous Linux : docker compose up -d).", true);
    }
    if (e.lmstudio) {
      h += e.lmstudio.ok ? ligneSys("LM Studio", `actif — ${esc(e.lmstudio.modele || "modèle chargé")}`)
                         : ligneSys("LM Studio", esc(e.lmstudio.message), true);
    }
    if (e.gpu) {
      const pct = Math.round(100 * e.gpu.memoire_mo / e.gpu.memoire_totale_mo);
      h += ligneSys(e.gpu.nom, `calcul ${e.gpu.usage} %, mémoire ${e.gpu.memoire_mo} / ${e.gpu.memoire_totale_mo} Mo`)
        + `<div class="bar"><i style="width:${pct}%"></i></div>`;
    } else {
      h += ligneSys("Carte graphique", "aucune carte NVIDIA détectée");
    }
    box.innerHTML = h;
  } catch { box.innerHTML = ligneSys("Serveur", "injoignable", true); }
}
setInterval(() => { if (!document.hidden && document.body.dataset.vue === "options") refreshSys(); }, 3000);
