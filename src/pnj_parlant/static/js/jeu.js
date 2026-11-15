// Page de jeu (index.html) : accueil (« / »), partie (« #jeu ») et options (« #options », js/options.js).
// La logique sans DOM est dans les autres modules de js/ (testés) ; celui-ci relie la page à ces modules.
import { adressePortrait, esc, segments, formatLine, interpelles, memeVoix, consignesEntree, texteExport,
         nomFichierExport, lieuEvoque, arrivee, parLieu, norm, lireExport, sceneImportee,
         consignesRecreation, detecteurVoix, partieValide,
         messageContexteMicro, choixModele, changementModele } from "./scene.js";
import { etatControles } from "./controles.js";
import { changerDeLieu, compteurVide, cumulerUsage, instantane, nouvellePartie, nouvelleScene, rejoindre, reprendreImport,
         restaurer, retirer, vider } from "./partie.js";
import { CONTRAINTES_MICRO, barreNiveau, ouvrirAnalyse, suiviEcoute } from "./micro.js";
import { auHasard, enchainerTours, oublierNonDit, ordreDesReponses, ordreDiscussion } from "./tours.js";
import { requete, retirer as retirerAlerte, signaler, verifierSante } from "./bandeau.js";
import { api, apiStream, lireReponse } from "./api.js";
import { initOptions, ouvrirOptions, refreshSys } from "./options.js";
import { chargerExemple, chargerTheme, confirmationImport, confirmationNouvelleTable, confirmationViderPartie,
         importerFichiers, resumeImport, resumeUnivers } from "./univers.js";

const $ = (id) => document.getElementById(id);
let cfg = { tts: null, intervention: 0.3 };  // /api/config : moteurs, voix, reconnaissance… (chargerConfig)
// La partie en cours (js/partie.js) : npcs (scène ; le premier est le principal), history (toute la scène),
// dernier (répond quand le joueur ne nomme personne), rencontres (PNJ croisés, pour l'export), lieuActuel
// ("" : aucun), positions (nom du PNJ → lieu où il se trouve pendant la partie ; sinon son lieu habituel).
const partie = nouvellePartie();
let busy = false;
let responseLength = "normal";
let contextLimit = null;
let tokenUsage = compteurVide();  // tokens de la conversation (js/partie.js)
let maxPnj = 3;       // PNJ en scène au plus : [dialogue] pnj_max du serveur (/api/config)
const PNJ_CONSEILLES = 3;  // au-delà, les petits modèles locaux suivent mal la scène
const COULEURS_PNJ = 3;    // couleurs des noms (npc-0 à npc-2), reprises en boucle
let lieux = [];        // lieux du scénario
let banque = [];       // PNJ de la banque : [{id, nom, metier, lieu}]
let proposition = null; // lieu où le joueur a proposé d'aller
let ici = [];          // PNJ présents dans le lieu, hors scène (boutons « Aborder »)

const statut = (t) => { $("status").textContent = t || ""; };

function afficherUsage() {
  const label = $("contextLabel"), bar = $("contextBar"), totals = $("usageTotals");
  bar.hidden = true;
  if (!tokenUsage.available) {
    label.textContent = contextLimit
      ? `Fenêtre de contexte : ${contextLimit.toLocaleString("fr-FR")} tokens (mesure au premier échange)`
      : "";
    totals.textContent = "";
    return;
  }
  const utilises = tokenUsage.lastInput + tokenUsage.lastOutput;
  if (contextLimit) {
    bar.max = contextLimit;
    bar.value = Math.min(utilises, contextLimit);
    bar.hidden = false;
    label.textContent = `Contexte (dernière requête + réponse) : ${utilises.toLocaleString("fr-FR")} / ` +
      `${contextLimit.toLocaleString("fr-FR")} tokens · reste ~${Math.max(0, contextLimit - utilises).toLocaleString("fr-FR")}`;
  } else {
    label.textContent = `Contexte au dernier échange : ${tokenUsage.lastInput.toLocaleString("fr-FR")} tokens · limite inconnue`;
  }
  totals.textContent = `Cumul : ${tokenUsage.input.toLocaleString("fr-FR")} tokens en entrée + ` +
    `${tokenUsage.output.toLocaleString("fr-FR")} en sortie`;
}

function reinitialiserUsage() {
  tokenUsage = compteurVide();
  afficherUsage();
}

// Erreur à montrer dans le bandeau sous la barre du haut (js/bandeau.js) ; même clé : remplace la précédente
const alerte = (message, niveau = "erreur", cle = message) => signaler(message, { cle, niveau });

// api, apiStream (js/api.js) : requête JSON ou NDJSON, serveur injoignable signalé dans le bandeau, erreurs en français

// --- Options (mémorisées dans ce navigateur) ----------------------------------
const OPTIONS = ["optInterrompre", "optCoupure", "optMulti", "optIntervention", "optEntree"];
const DESACTIVEES = ["optCoupure"];  // à essayer d'abord (écho des haut-parleurs) : désactivée par défaut

function loadOptions() {
  for (const id of OPTIONS) {
    let v = null;
    try { v = localStorage.getItem(id); } catch {}
    $(id).checked = v === null ? !DESACTIVEES.includes(id) : v === "1";  // le reste est activé par défaut
  }
}

function saveOptions() {
  for (const id of OPTIONS) try { localStorage.setItem(id, $(id).checked ? "1" : "0"); } catch {}
}

// Une sous-option ne compte que si « Plusieurs PNJ dans la scène » est cochée
const opt = (id) => $(id).checked && $("optMulti").checked;

// --- Affichage ---------------------------------------------------------------
// qui : le PNJ qui parle, ou null pour le joueur
function addLine(qui, text) {
  const div = document.createElement("div");
  div.className = qui ? `line npc-line npc-${Math.max(0, partie.npcs.indexOf(qui)) % COULEURS_PNJ}` : "line pj";
  div.innerHTML = `<span class="who">${qui ? esc(qui.nom) : "Vous"}</span><span class="text">${formatLine(text)}</span>`;
  $("log").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

// Journal affiché, ligne par ligne : [qui ("Vous", nom du PNJ, "" pour une narration), texte affiché]
const lignesDuLog = () => [...$("log").querySelectorAll(".line")]
  .map(l => [l.querySelector(".who")?.textContent ?? "", l.querySelector(".text").textContent]);

// Réaffiche un journal (conversation importée ou reprise) ; fiches : les PNJ qui y parlent
function afficherLignes(lignes, fiches) {
  $("log").innerHTML = "";
  for (const [qui, t] of lignes) {
    if (!qui) addNarration().querySelector(".text").innerHTML = formatLine(t);
    else addLine(qui === "Vous" ? null : fiches.find(f => f.nom === qui) ?? { nom: qui }, t);
  }
}

// Narration (arrivée dans un lieu…) : ni nom, ni bulle, lue par la voix du narrateur
function addNarration() {
  const div = document.createElement("div");
  div.className = "line narration-line";
  div.innerHTML = `<span class="text"></span>`;
  $("log").appendChild(div);
  return div;
}

const nomDuLieu = (id) => lieux.find(l => l.id === id)?.nom;

function renderCards() {
  $("cards").innerHTML = partie.npcs.length ? partie.npcs.map((n, i) => `
    <div class="pnj-card${i ? " second" : ""}">
      ${adressePortrait(n) ? `<img class="portrait" src="${adressePortrait(n)}" alt="Portrait de ${esc(n.nom)}">` : ""}
      <h1>${esc(n.nom)}</h1>
      <p class="metier">${esc(n.metier)}</p>
      <p>${esc(n.apparence)}</p>
      <p><span class="k">Caractère :</span> ${esc(n.personnalite)}</p>
      <p><span class="k">Humeur :</span> ${esc(n.humeur)}</p>
      ${nomDuLieu(partie.lieuActuel) ? `<p><span class="k">Se trouve :</span> ${esc(nomDuLieu(partie.lieuActuel))}</p>` : ""}
      ${nomDuLieu(n.lieu) && n.lieu !== partie.lieuActuel
        ? `<p><span class="k">Lieu habituel :</span> ${esc(nomDuLieu(n.lieu))}</p>` : ""}
      ${lieux.length ? `<label class="suit"><input type="checkbox" data-suit="${i}" ${n.suit ? "checked" : ""}>
        Vous accompagne quand vous changez de lieu</label>` : ""}
      ${i ? `<button class="ghost" data-retirer="${i}">Retirer de la scène</button>` : ""}
    </div>`).join("")
    : `<p class="empty">Aucun PNJ pour l’instant. Abordez quelqu’un ici, jouez un PNJ de la banque ou créez-en un.</p>`;
}

// Bloc « Lieu » : menu, description, PNJ de la banque qui se trouvent ici
function renderLieu() {
  $("lieuBloc").hidden = !lieux.length;
  $("lieuSel").innerHTML = `<option value="">— Aucun lieu —</option>`
    + lieux.map(l => `<option value="${esc(l.id)}">${esc(l.nom)}</option>`).join("");
  $("lieuSel").value = partie.lieuActuel;
  const lieu = lieux.find(l => l.id === partie.lieuActuel);
  $("lieuDesc").textContent = lieu?.description ?? "";
  // PNJ de la banque, et PNJ croisés pendant la partie (même inventés, pas encore enregistrés)
  const connus = [...banque, ...partie.rencontres.filter(r => !banque.some(b => b.nom === r.nom))];
  ici = lieu ? connus.filter(c => (partie.positions[c.nom] ?? c.lieu) === lieu.id && !partie.npcs.some(n => n.nom === c.nom)) : [];
  $("ici").innerHTML = !lieu ? ""
    : ici.length ? `<span class="k">Ici :</span>` + ici.map((c, i) =>
        `<button class="ghost" data-aborder="${i}">${esc(c.nom)} — ${esc(c.metier)}</button>`).join("")
    : `<span class="k">Personne d’autre ici.</span>`;
  renderBanque();
  setBusy(busy);
}

// Menu de la banque, regroupé par lieu où se trouve chaque PNJ pendant la partie (le lieu actuel d'abord)
function renderBanque() {
  const choisi = $("bankSel").value;
  const option = (n) => `<option value="${esc(n.id)}">${esc(n.nom)} — ${esc(n.metier)}</option>`;
  const groupes = parLieu(banque, lieux, partie.positions, partie.lieuActuel);
  $("bankSel").innerHTML = !banque.length ? `<option value="">Banque vide</option>`
    : !lieux.length ? banque.map(option).join("")
    : groupes.map(g => `<optgroup label="${esc(g.lieu ? g.lieu.nom + (g.lieu.id === partie.lieuActuel ? " (vous êtes ici)" : "")
                                                    : "Sans lieu")}">${g.pnjs.map(option).join("")}</optgroup>`).join("");
  if (banque.some(n => n.id === choisi)) $("bankSel").value = choisi;
}

// Action en cours (busy) : contrôles désactivés. À la fin d'une action, ceux qui attendaient (libre) repartent
// et la partie est sauvegardée.
function setBusy(b) {
  busy = b;
  appliquerControles();
  if (!b) {
    const a = attentesLibre; attentesLibre = []; a.forEach(r => r());
    sauverPartie();
  }
}

// État de chaque contrôle (etatControles, js/controles.js) appliqué à la page
function appliquerControles() {
  const e = etatControles({
    busy, npcs: partie.npcs, rencontres: partie.rencontres, maxPnj, multi: $("optMulti").checked, entree: $("optEntree").checked,
    interrompre: $("optInterrompre").checked, parole: !!parole,
    ecoute: $("micBtn").getAttribute("aria-pressed") === "true", microDispo: !!(cfg.stt_local || recognition),
    choixBanque: $("bankSel").value, modeleModifiable: !!choixModele(cfg.modele_dialogue)?.modifiable });
  for (const [id, v] of Object.entries(e.desactive)) $(id).disabled = v;
  for (const [id, v] of Object.entries(e.cache)) $(id).hidden = v;
  for (const btn of document.querySelectorAll("[data-aborder]")) btn.disabled = e.aborder;
  for (const btn of document.querySelectorAll("[data-retirer]")) btn.disabled = e.retirer;
  $("multiOpts").classList.toggle("inactif", !e.sousOptions);
  for (const c of $("multiOpts").querySelectorAll("input")) c.disabled = !e.sousOptions;
}

// Attend la fin de l'action en cours (utile quand le joueur a coupé la parole au PNJ : sa question
// part une fois que la réplique interrompue a fini de se ranger dans l'historique).
let attentesLibre = [];
const libre = () => busy ? new Promise(r => attentesLibre.push(r)) : Promise.resolve();

// --- Voix des PNJ ------------------------------------------------------------
// Prise de parole en cours : { ctrl, stop }. Le bouton Stop annule les requêtes (réponse du modèle,
// synthèses en préparation) via ctrl, et coupe le son qui joue via stop().
let parole = null;

function debutParole() {
  if (parole) stopNpc();  // une seule prise de parole à la fois : l'ancienne se tait (Stop ne l'atteindrait plus)
  parole = { ctrl: new AbortController(), stop: null };
  $("stopBtn").hidden = false;
  setBusy(busy);  // « Parler » devient un bouton pour interrompre
  arreterVeille();
  veiller(parole);
  return parole;
}

function finParole(p) {
  if (parole !== p) return;
  parole = null;
  arreterVeille();
  $("stopBtn").hidden = true;
  setBusy(busy);
}

// --- Couper la parole au PNJ en parlant (option) ------------------------------
// Pendant que le PNJ parle (ou réfléchit), le micro reste ouvert ; dès que le joueur parle assez fort et
// assez longtemps, le PNJ se tait et l'enregistrement continue avec le même micro : c'est sa question.
// La suppression d'écho du navigateur retire en principe la voix du PNJ, mais pas forcément celle de
// la synthèse du système (repli speechSynthesis) : avec des haut-parleurs, mieux vaut un casque.
let veille = null;  // { p, stream, ctx, timer, arret }

async function veiller(p) {
  if (!$("optCoupure").checked || !partie.npcs.length || !(cfg.stt_local || recognition)) return;
  if ($("micBtn").getAttribute("aria-pressed") === "true") return;  // le joueur parle déjà
  const v = { p, stream: null, ctx: null, timer: null, arret: false };
  veille = v;
  try {
    v.stream = await navigator.mediaDevices.getUserMedia(CONTRAINTES_MICRO);
    if (v.arret) return fermerVeille(v);
    const analyse = await ouvrirAnalyse(v.stream);
    v.ctx = analyse.ctx;
    if (v.arret) return fermerVeille(v);
    const det = detecteurVoix();
    v.timer = setInterval(() => {
      if (!det.ajouter(analyse.niveau(), performance.now())) return;
      // Le joueur parle : on garde le micro pour l'enregistrer, on fait taire le PNJ
      clearInterval(v.timer); v.ctx.close();
      veille = null;
      stopNpc();
      if (cfg.stt_local) listenLocal({ stream: v.stream, bruit: det.bruit });
      else { v.stream.getTracks().forEach(t => t.stop()); ecouterNavigateur(); }
    }, 50);
  } catch (e) {
    fermerVeille(v);
    if (veille === v) veille = null;
    if (e.name === "NotAllowedError") alerte("Micro refusé : impossible de couper le PNJ en parlant.", "avertissement", "micro");
  }
}

function fermerVeille(v) {
  clearInterval(v.timer);
  v.ctx?.close().catch(() => {});
  v.stream?.getTracks().forEach(t => t.stop());
}

function arreterVeille() {
  if (!veille) return;
  veille.arret = true;  // getUserMedia encore en attente : le micro sera refermé à son retour
  fermerVeille(veille);
  veille = null;
}

function stopNpc() {
  const p = parole;
  if (!p) return;
  finParole(p);
  p.ctrl.abort();
  p.stop?.();
  if ("speechSynthesis" in window) speechSynthesis.cancel();  // repli navigateur : termine la lecture
  statut("");
}

// Lance tout de suite la synthèse (Piper, Pocket TTS ou Edge) et renvoie une fonction qui joue
// le son : la phrase suivante se prépare ainsi pendant que la précédente est lue.
// onStart(morceau) est appelé au moment où chaque morceau commence à être dit (pour l'afficher).
function prepareSpeech(text, p, onStart, n) {
  const plays = segments(text).map(([t, narrateur]) => prepareSegment(t, narrateur, p, onStart, n));
  return async () => { for (const play of plays) await play(); };
}

// n : le PNJ qui parle, ou null pour une narration seule (arrivée dans un lieu)
function prepareSegment(text, narrateur, p, onStart, n) {
  // eviter : le narrateur ne prend la voix d'aucun PNJ de la scène
  const audioFile = cfg.tts && (narrateur || n?.voix?.name)
    ? fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ text, voice: n?.voix ?? {}, narrateur,
                                                 eviter: partie.npcs.map(x => x.voix).filter(Boolean) }),
                          signal: p.ctrl.signal })
        .then(r => {
          if (r.ok) return r.blob();
          alerte("La synthèse vocale du serveur a échoué : la voix du navigateur prend le relais.", "avertissement", "tts");
          return null;
        }).catch(() => null)
    : Promise.resolve(null);
  return async () => {
    const blob = await audioFile;
    if (p.ctrl.signal.aborted) return;  // interrompu par Stop
    onStart?.(narrateur ? `(${text})` : text);
    if (!blob) return browserSpeak(text, narrateur, n);  // repli sur la voix du navigateur
    const audio = new Audio(URL.createObjectURL(blob));
    await new Promise((res) => {
      p.stop = () => { audio.pause(); res(); };
      audio.onended = res; audio.onerror = res;
      audio.play().catch((e) => {
        // lecture refusée par le navigateur (son jamais autorisé sur cet onglet, souvent sur téléphone)
        if (e.name === "NotAllowedError") alerte("Le navigateur a bloqué le son : touchez la page, puis reposez la question.", "avertissement", "son");
        res();
      });
    });
    URL.revokeObjectURL(audio.src);
  };
}

const speak = (text, p, onStart, n) => prepareSpeech(text, p, onStart, n)();

async function browserSpeak(text, narrateur, n) {
  if (!("speechSynthesis" in window)) return;
  await new Promise((res) => {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    u.pitch = narrateur ? 1 : n?.voix?.browser_pitch ?? 1;
    u.rate = narrateur ? 1 : n?.voix?.browser_rate ?? 1;
    const fr = speechSynthesis.getVoices().filter(v => v.lang.startsWith("fr"));
    // le narrateur prend la première voix française, chaque PNJ une des suivantes
    if (fr.length) u.voice = fr[narrateur ? 0 : (1 + Math.max(0, partie.npcs.indexOf(n))) % fr.length];
    u.onend = res; u.onerror = res;
    speechSynthesis.speak(u);
  });
}

// --- Scène : arrivée des PNJ -------------------------------------------------
// Le PNJ dit sa salutation ; chaque morceau s'affiche quand il est dit
async function saluer(n) {
  const p = debutParole();
  let line = null, said = "";
  try {
    await speak(n.salutation, p, (morceau) => {
      line ??= addLine(n, "");
      said += (said ? " " : "") + morceau;
      line.querySelector(".text").innerHTML = formatLine(said);
      line.scrollIntoView({ behavior: "smooth", block: "end" });
    }, n);
  } finally { finParole(p); }
}

// Nouvelle scène avec ce PNJ seul, dans son lieu habituel s'il en a un (on va le voir là où il est).
async function startScene(n) {
  reinitialiserUsage();
  nouvelleScene(partie, n, lieux);
  masquerProposition();
  $("log").innerHTML = "";
  renderCards();
  renderLieu();
  statut("");
  setBusy(true);
  await saluer(n);
}

// Le PNJ rejoint la scène en cours
async function joinScene(n) {
  if (partie.npcs.some(x => x.nom === n.nom)) throw new Error(`${n.nom} est déjà dans la scène.`);
  if (partie.npcs.some(x => memeVoix(x.voix, n.voix))) {  // deux PNJ de la scène n'ont jamais la même voix
    n.voix = await api("/api/voice", { ...n, eviter: partie.npcs.map(x => x.voix) });
  }
  rejoindre(partie, n);
  renderCards();
  renderLieu();
  statut(partie.npcs.length > PNJ_CONSEILLES ? `Scène de ${partie.npcs.length} PNJ : les petits modèles locaux suivent mal une scène chargée `
    + "(réponses plus lentes, PNJ qui se confondent). Vous pouvez limiter le nombre de PNJ dans les options." : "");
  setBusy(true);
  await saluer(n);
}

function retirerDeLaScene(i) {
  const n = retirer(partie, i);
  sauverPartie();
  renderCards();
  renderLieu();
  statut(`${n.nom} quitte la scène.`);
}

// --- Lieux -------------------------------------------------------------------
// Change de lieu : les PNJ qui n'accompagnent pas le voyageur restent sur place, le narrateur décrit
// le nouveau lieu. Les compagnons gardent le souvenir de la conversation ; sans compagnon, elle repart à zéro.
async function changerLieu(id) {
  if (busy || id === partie.lieuActuel) return;
  masquerProposition();
  const { lieu, restent } = changerDeLieu(partie, id, lieux);
  renderCards();
  renderLieu();
  if (!lieu) return;
  setBusy(true);
  const p = debutParole();
  let line = null, said = "";
  try {
    await speak(arrivee(lieu, restent), p, (morceau) => {
      line ??= addNarration();
      said += (said ? " " : "") + morceau;
      line.querySelector(".text").innerHTML = formatLine(said);
      line.scrollIntoView({ behavior: "smooth", block: "end" });
    }, null);
  } catch (e) { alerte(e.message); }
  finally {
    finParole(p);
    setBusy(false);
  }
}

// Aborder un PNJ qui se trouve dans le lieu (`i` : rang dans `ici`) : il rejoint la scène (ou la remplace,
// sans l'option « Plusieurs PNJ »), sans effacer ce qui a été dit jusque-là.
async function aborder(i) {
  const c = ici[i];
  if (busy || !c) return;
  setBusy(true); statut("");
  try {
    // déjà croisé pendant la partie : on reprend sa fiche (voix, compagnon…) ; sinon, celle de la banque
    const n = partie.rencontres.find(r => r.nom === c.nom) ?? await api(`/api/bank/${encodeURIComponent(c.id)}`);
    if (!$("optMulti").checked) { partie.npcs = []; partie.history = []; }
    await joinScene(n);
  } catch (e) { alerte(e.message); }
  setBusy(false);
  if (partie.npcs.length) $("ask").focus();
}

function proposer(lieu) {
  proposition = lieu;
  $("propTexte").textContent = `Aller à : ${lieu.nom} ?`;
  $("proposition").hidden = false;
}

function masquerProposition() {
  proposition = null;
  $("proposition").hidden = true;
}

// Renvoie faux si le serveur n'a pas répondu (la partie gardée n'est alors ni restaurée ni réécrite)
async function chargerLieux() {
  const lus = await api("/api/lieux").catch(() => null);
  lieux = lus ?? [];
  if (!lieux.some(l => l.id === partie.lieuActuel)) partie.lieuActuel = "";
  renderLieu();
  renderCards();
  return !!lus;
}

async function generate() {
  if (busy) return;  // Entrée dans « Métier » pendant qu'un PNJ parle : ignorée
  setBusy(true); statut("Le PNJ prend forme…");
  try { await startScene(await api("/api/npc/generate", { role: $("role").value, lieu: partie.lieuActuel })); }
  catch (e) { alerte(e.message); }
  setBusy(false);
  if (partie.npcs.length) $("ask").focus();
}

// Un PNJ inventé d'après la conversation entre dans la scène
async function faireEntrer() {
  if (busy || !partie.npcs.length || partie.npcs.length >= maxPnj) return;
  const qui = $("entree").value.trim();
  setBusy(true); statut("Quelqu’un approche…");
  const consignes = consignesEntree(partie.history, partie.npcs, qui);
  try {
    await joinScene(await api("/api/npc/generate", { consignes, lieu: partie.lieuActuel }));  // un habitué du lieu
    $("entree").value = "";
  } catch (e) { alerte(e.message); }
  setBusy(false);
}

// --- Banque de PNJ -----------------------------------------------------------
async function refreshBank(selectId) {
  const lue = await api("/api/bank").catch(() => null);
  banque = lue ?? [];
  renderLieu();  // remplit aussi le menu de la banque
  if (selectId) $("bankSel").value = selectId;
  setBusy(busy);
  return !!lue;  // faux : serveur muet
}

// ajout : le PNJ rejoint la scène en cours au lieu d'en commencer une nouvelle
async function loadFromBank(ajout, id = $("bankSel").value) {
  if (busy) return;
  setBusy(true); statut("");
  try {
    const n = await api(`/api/bank/${encodeURIComponent(id)}`);
    await (ajout ? joinScene(n) : startScene(n));
  } catch (e) { alerte(e.message); }
  setBusy(false);
  if (partie.npcs.length) $("ask").focus();
}

async function saveToBank() {
  try {
    const noms = [];
    for (const n of partie.npcs.filter(n => !n.id)) {
      n.id = (await api("/api/bank", n)).id;
      noms.push(n.nom);
    }
    await refreshBank(partie.npcs[0].id);
    statut(`${noms.join(" et ")} ${noms.length > 1 ? "sont enregistrés" : "est enregistré"} dans la banque.`);
  } catch (e) { alerte(e.message); }
}

// --- Export de la conversation -----------------------------------------------
// Télécharge un fichier texte avec le dialogue tel qu'il est affiché (descriptions comprises).
function exportConversation() {
  const date = new Date();
  const texte = texteExport(lignesDuLog(), partie.rencontres, date, nomDuLieu(partie.lieuActuel) ?? "");
  // BOM : le Bloc-notes de Windows affiche alors correctement les accents
  const bom = String.fromCharCode(0xFEFF);
  const url = URL.createObjectURL(new Blob([bom + texte], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nomFichierExport(partie.rencontres, date);
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// --- Import d'une conversation exportée -----------------------------------------
// Reprend la conversation là où elle s'était arrêtée : même lieu, mêmes PNJ, même historique (le modèle
// s'en souvient). Les PNJ sont pris dans la banque ; ceux qui n'y sont pas (inventés en cours de partie)
// sont recréés par le modèle d'après leur nom, leur métier, leur apparence et ce qu'ils ont dit.
async function importerConversation(fichier) {
  if (busy) return;
  let lu;
  try { lu = lireExport(await fichier.text()); } catch (e) { alerte(e.message); return; }
  if (partie.history.length > 1 && !confirm("Remplacer la conversation en cours par celle du fichier ?")) return;
  stopNpc();
  setBusy(true);
  try {
    const lieu = lieux.find(l => norm(l.nom) === norm(lu.lieu));
    const fiches = [];
    for (const p of lu.pnjs) {
      const enBanque = banque.find(b => b.nom === p.nom);
      let n = partie.rencontres.find(r => r.nom === p.nom)
        ?? (enBanque && await api(`/api/bank/${encodeURIComponent(enBanque.id)}`));
      if (!n) {
        statut(`${p.nom} n’est pas dans la banque : il reprend forme…`);
        n = await api("/api/npc/generate", { role: p.metier, nom: p.nom, lieu: lieu?.id ?? "",
                                             consignes: consignesRecreation(p, lu.lignes) })
          .catch((e) => { throw new Error(`Impossible de recréer ${p.nom} : ${e.message}`); });
        n = { ...n, nom: p.nom, metier: p.metier || n.metier, apparence: p.apparence || n.apparence };
      }
      fiches.push(n);
    }
    const scene = sceneImportee(lu.lignes, $("optMulti").checked ? maxPnj : 1).map(nom => fiches.find(f => f.nom === nom));
    for (let i = 1; i < scene.length; i++) {  // deux PNJ de la scène n'ont jamais la même voix
      const avant = scene.slice(0, i);
      if (avant.some(x => memeVoix(x.voix, scene[i].voix))) {
        // copie : si /api/voice échoue, la partie en cours reste intacte
        const n = { ...scene[i], voix: await api("/api/voice", { ...scene[i], eviter: avant.map(x => x.voix) }) };
        fiches[fiches.indexOf(scene[i])] = n;
        scene[i] = n;
      }
    }
    reprendreImport(partie, lu.lignes, fiches, scene, lieu?.id ?? "");
    reinitialiserUsage();
    masquerProposition();
    $("log").innerHTML = "";
    afficherLignes(lu.lignes, fiches);
    renderCards();
    renderLieu();
    statut(!partie.npcs.length ? "Conversation importée. Personne n’est resté avec vous : abordez quelqu’un ou jouez un PNJ."
      : lu.lieu && !lieu ? `Conversation importée. Le lieu « ${lu.lieu} » n’existe plus dans le scénario.`
      : "Conversation importée : vous pouvez la reprendre.");
  } catch (e) { alerte(e.message); }
  setBusy(false);
  if (partie.npcs.length) $("ask").focus();
}

// --- Dialogue : qui répond ? (js/tours.js) -------------------------------------
// Option « Interventions spontanées » : de temps en temps, un autre PNJ réagit à la suite
const intervention = () => ({ actif: opt("optIntervention"), proba: cfg.intervention ?? 0.3 });

async function send(text) {
  text = text.trim();
  if (!text || !partie.npcs.length || busy) return;
  $("ask").value = "";
  addLine(null, text);
  partie.history.push({ speaker: null, content: text });
  // « Allons à la forge » : on propose d'y aller (les PNJ répondent quand même, ils peuvent réagir)
  const evoque = lieuEvoque(text, lieux, partie.lieuActuel);
  if (evoque) proposer(evoque); else masquerProposition();
  // Le PNJ cité répond (tous ceux cités, dans l'ordre) ; sinon, celui qui a parlé en dernier
  await jouerTours(ordreDesReponses(interpelles(text, partie.npcs), partie.npcs, partie.dernier, intervention()));
}

// Question dictée au micro : envoyée si c'est possible, sinon laissée dans le champ (rien ne se perd)
function envoyerDictee(text) {
  if (!partie.npcs.length || busy) {
    $("ask").value = text;
    statut("Votre question est restée dans le champ : envoyez-la quand vous voulez.");
    return;
  }
  send(text).catch(e => alerte(e.message));
}

// Bouton « Laissez-les discuter » : un autre PNJ répond à celui qui vient de parler
async function discuter() {
  if (busy || partie.npcs.length < 2) return;
  await jouerTours(ordreDiscussion(partie.npcs, partie.dernier, intervention()));
}

// Les PNJ de `ordre` parlent l'un après l'autre (enchainerTours, js/tours.js). Chacun commence à écrire sa
// réplique pendant que le précédent parle encore, et l'entend en entier avant de répondre.
// Un PNJ à qui un autre pose une question répond juste après (au plus MAX_TOURS répliques d'affilée).
async function jouerTours(ordre) {
  setBusy(true);
  const p = debutParole();
  try {
    const { tours, voix } = await enchainerTours(ordre, { tour: (n, voice) => tourDe(n, p, voice),
                                                         presents: () => partie.npcs, signal: p.ctrl.signal });
    await voix;
    // Interrompu : chacun « se souvient » seulement de ce qu'il a eu le temps de dire
    if (p.ctrl.signal.aborted) tours.forEach(t => t.corriger());
  } finally {  // une erreur imprévue ne laisse pas les contrôles désactivés
    finParole(p);
    setBusy(false);
  }
}

// Réplique d'un PNJ : préparée phrase par phrase dès qu'elle arrive, affichée quand elle est dite.
// Renvoie quand le modèle a fini d'écrire ; t.voice se termine quand le PNJ a fini de parler.
async function tourDe(n, p, voice) {
  let line = null, reply = "", said = "", erreur = null;
  const entry = { speaker: n.nom, content: "" };
  voice = voice.then(() => {
    if (!line && !erreur && !p.ctrl.signal.aborted) statut(`${n.nom} réfléchit…`);
  });
  const show = (morceau) => {
    if (!line) { line = addLine(n, ""); statut(""); }
    said += (said ? " " : "") + morceau;
    line.querySelector(".text").innerHTML = formatLine(said);
    line.scrollIntoView({ behavior: "smooth", block: "end" });
  };
  try {
    const corps = { npc: n, presents: partie.npcs.filter(x => x !== n), history: partie.history, lieu: partie.lieuActuel };
    corps.longueur = responseLength;
    await apiStream("/api/npc/talk", corps, (item) => {
      if (p.ctrl.signal.aborted) return;
      if (item.error) throw new Error(item.error);
      if (item.usage) {
        cumulerUsage(tokenUsage, item.usage);
        afficherUsage();
        return;
      }
      reply += (reply ? " " : "") + item.phrase;
      voice = voice.then(prepareSpeech(item.phrase, p, show, n));
    }, p.ctrl.signal);
  } catch (e) {
    if (!p.ctrl.signal.aborted) { erreur = e; alerte(e.message); statut(""); }
  }
  if (reply) {
    entry.content = reply;
    partie.history.push(entry);
    partie.dernier = n;
  }
  return {
    voice, erreur, reply,
    corriger() { if (reply) oublierNonDit(partie.history, entry, said); },
  };
}

// --- Reconnaissance vocale du joueur ------------------------------------------
// Sur le serveur (faster-whisper, sans réseau) si config.toml le prévoit,
// sinon dans le navigateur (Web Speech API de Chrome / Edge, qui passe par internet).
function micPressed(on) {
  $("micBtn").setAttribute("aria-pressed", on ? "true" : "false");
  $("micBtn").textContent = on ? "J’écoute" : "Parler";
  setBusy(busy);  // le bouton reste cliquable pendant l'écoute, pour la terminer
}

const arretNavigateur = () => recognition?.stop();
let stopListening = arretNavigateur;
let ecouteLocale = false;  // posé avant d'ouvrir le micro : un double clic ne lance pas deux enregistrements
let transcription = null;  // AbortController de /api/stt : Échap annule la transcription

// Reconnaissance du navigateur : start() lève une erreur si elle écoute déjà (double clic)
function ecouterNavigateur() {
  try { recognition?.start(); } catch {}
}

// ouvert : { stream, bruit } quand le joueur vient de couper la parole au PNJ (micro déjà ouvert,
// bruit de fond déjà mesuré, voix déjà entendue)
async function listenLocal(ouvert = null) {
  if (ecouteLocale) { ouvert?.stream.getTracks().forEach(t => t.stop()); return; }
  ecouteLocale = true;
  let stream = ouvert?.stream;
  if (!stream) try {
    stream = await navigator.mediaDevices.getUserMedia(CONTRAINTES_MICRO);
  } catch (e) {
    ecouteLocale = false;
    alerte("Micro refusé. Autorisez-le dans le navigateur (et utilisez localhost ou HTTPS).", "erreur", "micro");
    return;
  }
  let rec, analyse;
  const chunks = [];
  try {
    rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => chunks.push(e.data);
    analyse = await ouvrirAnalyse(stream);  // referme son AudioContext s'il échoue
  } catch (e) {
    ecouteLocale = false;
    stream.getTracks().forEach(t => t.stop());
    alerte(`Micro inutilisable : ${e.message}`, "erreur", "micro");
    return;
  }
  const { ctx } = analyse;
  // Arrêt automatique après une seconde de silence, comme la reconnaissance du navigateur (suiviEcoute,
  // js/micro.js : seuil adaptatif d'après le bruit de fond mesuré pendant la première demi-seconde).
  const suivi = suiviEcoute({ debut: performance.now(), dejaEntendu: !!ouvert, bruit: ouvert?.bruit ?? 0 });
  const timer = setInterval(() => {
    const niveau = analyse.niveau();
    statut(`J’écoute… niveau ${barreNiveau(niveau)}`);
    if (suivi.ajouter(niveau, performance.now())) arreter();
  }, 100);

  // arrêt de CET enregistrement (la minuterie ne passe pas par la globale, qu'une autre écoute remplacerait)
  const arreter = () => { if (rec.state !== "inactive") rec.stop(); };
  stopListening = arreter;

  rec.onstop = async () => {
    clearInterval(timer); ctx.close(); stream.getTracks().forEach(t => t.stop());
    ecouteLocale = false;
    if (stopListening === arreter) stopListening = arretNavigateur;
    micPressed(false);
    // Même si le seuil n'a rien détecté, on laisse Whisper (qui filtre le silence) trancher,
    // sauf si le micro est réellement muet (signal nul : mauvais périphérique ou micro coupé).
    if (suivi.muet()) {
      statut("Micro muet : aucun signal reçu. Vérifiez le périphérique d’entrée choisi par le navigateur.");
      return;
    }
    await libre();  // réplique interrompue : elle finit de se ranger avant la question
    setBusy(true); statut("Je transcris…");
    let text = "";
    const ctrl = transcription = new AbortController();
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: rec.mimeType }), "micro.webm");
      form.append("indice", `Dialogue avec ${partie.npcs.map(n => `${n.nom}, ${n.metier}`).join(" ; ")}.`);
      const data = await lireReponse(await requete("/api/stt", { method: "POST", body: form, signal: ctrl.signal }));
      text = data.text;
      statut(text ? "" : "Je n’ai pas compris. Recommencez ou tapez votre question.");
    } catch (e) {
      if (e.name === "AbortError") statut("");  // Échap : transcription abandonnée
      else alerte(e.message);
    }
    if (transcription === ctrl) transcription = null;
    setBusy(false);
    if (text) envoyerDictee(text);
  };
  rec.start();
  micPressed(true);
}

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SR) {
  recognition = new SR();
  recognition.lang = "fr-FR";
  recognition.interimResults = true;
  recognition.continuous = false;
  let finalText = "";
  recognition.onstart = () => { finalText = ""; micPressed(true); };
  recognition.onresult = (ev) => {
    let interim = "";
    for (const r of ev.results) (r.isFinal ? (finalText = r[0].transcript) : (interim += r[0].transcript));
    $("ask").value = finalText || interim;
  };
  recognition.onerror = (ev) => {
    if (ev.error === "no-speech" || ev.error === "aborted") statut("Je n’ai rien entendu.");  // pas une panne
    else alerte(ev.error === "not-allowed"
      ? "Micro refusé. Autorisez-le dans le navigateur (et utilisez localhost ou HTTPS)."
      : `Reconnaissance vocale du navigateur : ${ev.error} (réseau coupé ?).`, "erreur", "micro");
  };
  recognition.onend = async () => {
    micPressed(false);
    if (!finalText) return;
    await libre();  // réplique interrompue : elle finit de se ranger avant la question
    envoyerDictee(finalText);
  };
}

$("micBtn").onclick = () => {
  if ($("micBtn").getAttribute("aria-pressed") === "true") return stopListening();
  if ($("micBtn").disabled || ecouteLocale) return;  // micro en cours d'ouverture : pas de deuxième écoute
  stopNpc();  // le joueur coupe la parole au PNJ (le bouton n'est actif pendant qu'il parle qu'avec l'option)
  if (cfg.stt_local) listenLocal();
  else ecouterNavigateur();
};
$("stopBtn").onclick = stopNpc;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { stopNpc(); transcription?.abort(); }
  // Barre d'espace = bouton « Parler » dans la partie seulement (ailleurs, elle fait défiler la page), sauf quand
  // on écrit ou qu'un autre bouton a le focus
  if (e.key === " " && !e.repeat && document.body.dataset.vue === "jeu"
      && !e.target.closest?.("input, textarea, select, button, a, [contenteditable]")) {
    e.preventDefault();
    $("micBtn").click();
  }
});
$("genBtn").onclick = generate;
$("loadBtn").onclick = () => loadFromBank(false);
$("addBtn").onclick = () => loadFromBank(true);
$("saveBtn").onclick = saveToBank;
$("exportBtn").onclick = exportConversation;
$("importBtn").onclick = () => $("importFichier").click();
$("importFichier").onchange = async () => {
  const fichier = $("importFichier").files[0];
  $("importFichier").value = "";  // pour pouvoir réimporter le même fichier
  if (fichier) await importerConversation(fichier);
};
$("discuterBtn").onclick = () => discuter().catch(e => alerte(e.message));
$("entreeBtn").onclick = faireEntrer;
$("entree").addEventListener("keydown", (e) => { if (e.key === "Enter") faireEntrer(); });
$("cards").onclick = (e) => {
  const i = e.target.dataset?.retirer;
  if (i !== undefined && !busy) retirerDeLaScene(Number(i));
};
$("cards").onchange = (e) => {  // case « Vous accompagne »
  const i = e.target.dataset?.suit;
  if (i !== undefined && partie.npcs[Number(i)]) partie.npcs[Number(i)].suit = e.target.checked;
};
$("lieuSel").onchange = () => changerLieu($("lieuSel").value);
$("ici").onclick = (e) => { if (e.target.dataset?.aborder !== undefined) aborder(Number(e.target.dataset.aborder)); };
$("propOui").onclick = () => { if (proposition) changerLieu(proposition.id); };
$("propNon").onclick = masquerProposition;
for (const id of OPTIONS) $(id).onchange = () => { saveOptions(); setBusy(busy); };
$("optCoupure").addEventListener("change", () => { arreterVeille(); if (parole) veiller(parole); });
// --- Conversation en cours, gardée dans ce navigateur -----------------------------
// Rien ne se perd en allant à l'accueil, aux options, à la page de préparation, ni en rechargeant la page.
const CLE_PARTIE = "pnj-partie";
let partieRestauree = false;  // pas de sauvegarde avant d'avoir relu la précédente (lieux et banque lus)
let sauvegardeRefusee = false;  // stockage plein ou interdit : signalé une seule fois

function sauverPartie() {
  if (!partieRestauree) return;
  try {
    const sauvegarde = instantane(partie, lignesDuLog(), tokenUsage);
    if (!sauvegarde) { localStorage.removeItem(CLE_PARTIE); return; }
    localStorage.setItem(CLE_PARTIE, JSON.stringify(sauvegarde));
  } catch {  // la partie continue, sans sauvegarde
    if (!sauvegardeRefusee) alerte("Ce navigateur refuse de garder la conversation (stockage plein ou interdit) : "
      + "elle sera perdue au rechargement. Exportez-la pour la garder.", "avertissement", "sauvegarde");
    sauvegardeRefusee = true;
  }
}

// Vide la partie en cours (nouvelle table, ou nouvel univers chargé depuis l'accueil)
function viderPartie() {
  stopNpc();
  vider(partie);
  masquerProposition();
  $("log").innerHTML = "";
  reinitialiserUsage();
  try { localStorage.removeItem(CLE_PARTIE); } catch {}
}

// Reprend la partie gardée dans ce navigateur. Les fiches sont relues sur le serveur (modifiées en préparation
// entre-temps) ; la partie garde son journal, qui accompagne le voyageur et les voix réattribuées (fichesRelues).
// Sauvegarde abîmée ou d'une autre version : effacée, la page démarre sans partie.
async function restaurerPartie() {
  let p = null;
  try { p = JSON.parse(localStorage.getItem(CLE_PARTIE) || "null"); } catch {}
  if (p === null) { partieRestauree = true; return; }
  try {
    if (!partieValide(p)) throw new Error("sauvegarde illisible");
    setBusy(true);
    // fiche supprimée (404), PNJ inventé ou serveur muet : la copie gardée reste
    const relues = await Promise.all(p.rencontres.map(r => r.id
      ? api(`/api/bank/${encodeURIComponent(r.id)}`).catch(() => null) : null));
    restaurer(partie, p, relues, lieux);
    tokenUsage = { ...tokenUsage, ...p.tokenUsage };
    afficherUsage();
    afficherLignes(p.lignes, partie.rencontres);
    renderCards();
    renderLieu();
  } catch {
    viderPartie();
    renderCards();
    renderLieu();
    alerte("La conversation gardée dans ce navigateur était illisible : elle a été effacée.", "avertissement", "sauvegarde");
  }
  partieRestauree = true;
  setBusy(false);
}
window.addEventListener("pagehide", sauverPartie);

// --- Vues : accueil (« / »), partie (« #jeu »), options (« #options ») ---------------
let vuePrecedente = "accueil";  // où revient le lien « Retour » des options
function afficherVue() {
  const vue = { "#jeu": "jeu", "#options": "options" }[location.hash] ?? "accueil";
  if (vue === "options" && document.body.dataset.vue !== "options") vuePrecedente = document.body.dataset.vue;
  const change = document.body.dataset.vue !== vue;
  document.body.dataset.vue = vue;
  document.title = { jeu: "Partie", options: "Options" }[vue] ? `${{ jeu: "Partie", options: "Options" }[vue]} - PNJ parlants` : "PNJ parlants";
  for (const a of document.querySelectorAll(".onglets [data-vue]")) {
    if (a.dataset.vue === vue) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  const versJeu = vuePrecedente === "jeu";
  $("optionsRetour").href = versJeu ? "#jeu" : "#";
  $("optionsRetour").textContent = versJeu ? "← Retour à la partie" : "← Retour à l’accueil";
  // au tour suivant : au premier affichage, le code des options (plus bas) n'est pas encore exécuté
  if (vue === "options") queueMicrotask(ouvrirOptions);
  if (vue === "accueil") majAccueil();
  window.scrollTo(0, 0);
  // changement de vue : le lecteur d'écran est amené au titre de la nouvelle vue (pas au premier affichage)
  if (change && firstVue) {
    const titre = { accueil: "accueilTitre", options: "optionsTitre", jeu: "cards" }[vue];
    const el = $(titre);
    if (el) { el.tabIndex = -1; el.focus({ preventScroll: true }); }
  }
  firstVue = true;
}
let firstVue = false;
window.addEventListener("hashchange", afficherVue);

// --- Accueil -------------------------------------------------------------------
let exemples = null;
async function majAccueil() {
  exemples ??= await api("/api/exemples").catch(() => null);  // échec : redemandés au prochain affichage
  $("exemplesListe").innerHTML = (exemples ?? []).map(e => `<button class="exemple" data-exemple="${esc(e.id)}">`
    + `Exemple : ${esc(e.nom)}<small>${esc(e.resume)}</small></button>`).join("");
  $("universActuel").textContent = resumeUnivers(lieux.length, banque.length);
  $("accHasardBtn").disabled = !banque.length;
  $("accReprendreBtn").hidden = !partie.npcs.length;
  $("accReprendreBtn").textContent = `Reprendre la conversation avec ${partie.npcs.map(n => n.nom).join(" et ")}`;
}

// Un nouveau PNJ remplace la conversation en cours : on demande avant de la perdre
const nouvelleConversation = () => partie.history.length <= 1
  || confirm("Commencer une nouvelle conversation ? Celle en cours sera remplacée (exportez-la pour la garder).");

$("accHasardBtn").onclick = () => {
  if (busy || !banque.length || !nouvelleConversation()) return;
  stopNpc();
  location.hash = "jeu";
  loadFromBank(false, auHasard(banque).id);
};
$("accInventerBtn").onclick = () => {
  if (busy || !nouvelleConversation()) return;
  stopNpc();
  $("role").value = $("accRole").value;
  location.hash = "jeu";
  generate();
};
$("accRole").addEventListener("keydown", (e) => { if (e.key === "Enter") $("accInventerBtn").click(); });
$("accReprendreBtn").onclick = () => { location.hash = "jeu"; };

// Nouvelle table : l'univers (scénario, thème, lieux, banque) est supprimé sur le serveur et la partie repart de zéro
$("nouvelleTableBtn").onclick = async () => {
  if (busy || !confirm(confirmationNouvelleTable(lieux.length, banque.length))) return;
  stopNpc();
  try { await api("/api/univers", undefined, "DELETE"); }
  catch (e) { $("accStatus").textContent = e.message; return; }
  viderPartie();
  await chargerLieux();
  await refreshBank();
  await chargerTheme();
  setBusy(false);
  $("accStatus").textContent = "";
  majAccueil();
};

const confirmerImport = () => !(banque.length || lieux.length)
  || confirm(confirmationImport(banque.length, $("accGarder").checked));
// Nouvel univers depuis l'accueil pendant une partie : on demande s'il faut la vider (refuser la garde)
async function importerUnivers(charger) {
  if (busy || !confirmerImport()) return;
  const vider = partie.rencontres.length > 0 && confirm(confirmationViderPartie(partie.npcs.map(n => n.nom)));
  $("accStatus").textContent = "Chargement…";
  try {
    const r = await charger($("accGarder").checked);
    if (vider) viderPartie();
    await chargerLieux();
    await refreshBank();
    await chargerTheme();
    $("accStatus").textContent = resumeImport(r);
  } catch (e) { $("accStatus").textContent = e.message; }
  majAccueil();
}
$("exemplesListe").onclick = (e) => {
  const b = e.target.closest("[data-exemple]");
  if (b) importerUnivers((garder) => chargerExemple(b.dataset.exemple, garder));
};
$("accZipBtn").onclick = () => $("accZip").click();
$("accDossierBtn").onclick = () => $("accDossier").click();
for (const id of ["accZip", "accDossier"]) {
  $(id).onchange = () => {
    const fichiers = [...$(id).files];
    $(id).value = "";  // pour pouvoir réimporter le même fichier
    if (fichiers.length) importerUnivers((garder) => importerFichiers(fichiers, garder));
  };
}

afficherVue();
loadOptions();
$("bankSel").onchange = () => setBusy(busy);
$("askForm").addEventListener("submit", (e) => e.preventDefault());  // Entrée envoie via « Envoyer », sans recharger
$("sendBtn").onclick = () => send($("ask").value).catch(e => alerte(e.message));
$("role").addEventListener("keydown", (e) => { if (e.key === "Enter") generate(); });
document.querySelectorAll("[data-length]").forEach((button) => {
  button.onclick = () => {
    responseLength = button.dataset.length;
    document.querySelectorAll("[data-length]").forEach((option) => {
      option.setAttribute("aria-pressed", option === button ? "true" : "false");
    });
  };
});

// Configuration du serveur pour la partie (moteurs, voix, reconnaissance…) : au chargement, et après un
// changement de réglages dans les options
async function chargerConfig(premiere = false) {
  const c = await api("/api/config").catch(() => null);
  if (!c) return;
  cfg = c;
  contextLimit = c.contexte_max;
  if (Number.isInteger(c.pnj_max) && c.pnj_max >= 1) maxPnj = c.pnj_max;
  afficherUsage();
  afficherModele();
  setBusy(busy);
  if (document.body.dataset.vue === "options") refreshSys();  // la carte Machine reprend la configuration
  const alerteMicro = messageContexteMicro(window.isSecureContext);
  if (premiere && alerteMicro) alerte(alerteMicro, "avertissement", "http");
  if (premiere && !c.stt_local && !recognition) statut("La saisie vocale demande Chrome ou Edge. Vous pouvez taper vos questions.");
  else if (premiere && !c.tts) statut("Synthèse vocale indisponible sur le serveur : la voix du navigateur sera utilisée.");
}
initOptions({ config: () => cfg, chargerConfig });  // vue Options (js/options.js)
chargerConfig(true);
verifierSante();

// --- Modèle de l'IA (vue Partie) ------------------------------------------------------------------
// Liste des modèles installés (Ollama ou LM Studio, selon [moteurs] dialogue ; cachée avec Claude). Le choix passe
// par PUT /api/reglages comme dans les options : même validation, mot de passe du MJ demandé hors du PC s'il
// existe (js/api.js, gardé pour l'onglet), appliqué à chaud. Désactivée pendant qu'un PNJ parle (setBusy).
function afficherModele() {
  const choix = choixModele(cfg.modele_dialogue);
  $("modeleBloc").hidden = !choix;
  if (!choix) return;
  $("modeleSel").innerHTML = choix.options.map(o => `<option value="${esc(o.valeur)}">${esc(o.libelle)}</option>`).join("");
  $("modeleSel").value = choix.valeur;
  $("modeleSel").title = !choix.modifiable
    ? "Sans mot de passe du MJ, le modèle ne se change que depuis le PC du serveur."
    : choix.cle === "local.modele" ? "Sert aussi à créer les PNJ si la création passe par Ollama." : "";
}
$("modeleSel").addEventListener("change", async () => {
  const choix = choixModele(cfg.modele_dialogue), choisi = $("modeleSel").value;
  const changements = changementModele(choix, choisi);
  if (!changements || busy) { $("modeleSel").value = choix?.valeur ?? ""; return; }
  setBusy(true);
  try {
    await api("/api/reglages", { changements }, "PUT",
              { message: "Changer le modèle de l’IA depuis cet appareil demande le mot de passe du MJ." });
    retirerAlerte("modele");
    statut(`Modèle de l’IA : ${choix.options.find(o => o.valeur === choisi)?.libelle ?? choisi}.`);
    await chargerConfig();
    verifierSante();
  } catch (e) {
    $("modeleSel").value = choix.valeur;
    alerte(e.message, "erreur", "modele");
  } finally {
    setBusy(false);
  }
});
setInterval(() => { if (!document.hidden) verifierSante(); }, 60000);

setBusy(false);
chargerTheme();
// Partie gardée : restaurée seulement si les lieux et la banque ont été lus (serveur injoignable : elle reste
// intacte dans le navigateur, sans être réécrite sans son lieu, jusqu'au rechargement)
(async () => {
  const lieuxLus = await chargerLieux();
  const banqueLue = await refreshBank();
  if (lieuxLus && banqueLue) await restaurerPartie();
  majAccueil();
})();
