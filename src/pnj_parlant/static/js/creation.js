// Page de préparation de l'univers (creation.html) : scénario, apparence, lieux, PNJ. La logique sans DOM est
// dans js/fiche.js, js/apparence.js, js/univers.js et js/scene.js (testés) ; celui-ci relie la page à ces modules.
import { adressePortrait, esc, parLieu } from "./scene.js";
import { requete, retirer, signaler, verifierSante } from "./bandeau.js";
import { api as appel, verifierAcces } from "./api.js";
import { COULEURS, THEME_DEFAUT, appliquerTheme, confirmationImport, exporter, identifiant,
         importerFichiers, poserThemesPerso, resumeImport, tousLesThemes } from "./univers.js";
import { CHAMPS_FICHE, corpsScenario, ficheDuFormulaire, initiale, secretMasque, titreFiche, valeursFormulaire,
         voixDuGenre } from "./fiche.js";
import { alertesPalettes, confirmationSuppression, editionDeTheme, libelleSuppression, mention, messageSuppression,
         palettesDuMode, portraitsPerso as persoDe, themeEdite as themeDuFormulaire } from "./apparence.js";
const $ = (id) => document.getElementById(id);
let current = {};     // PNJ en cours d'édition (id présent = déjà dans la banque)
let dirty = false;    // modifications non enregistrées

// Serveur injoignable (requete) ou en panne (5xx : moteur indisponible, portrait impossible…) : signalé dans le
// bandeau sous la barre du haut, en plus du message près de l'action (js/api.js). Hors du PC du serveur, une
// écriture demande le mot de passe du MJ (js/api.js) ; une fois acceptée, l'alerte « lecture seule » disparaît.
async function api(path, body, method) {
  const data = await appel(path, body, method, { panne: true });
  if ((method ?? (body === undefined ? "GET" : "POST")) !== "GET") retirer("acces");
  return data;
}
// Champs réservés au MJ (secret d'un PNJ, notes du MJ du scénario et d'un lieu) : absents d'une réponse lue sans
// mot de passe. Le champ est alors grisé et jamais renvoyé : le serveur garde ce qu'il a (décision D1).
const MASQUE = "Masqué : mot de passe du MJ demandé sur cet appareil (rechargez la page pour le saisir).";
function masquerChamp(champ, masque) {
  champ.disabled = masque;
  champ.placeholder = masque ? MASQUE : champ.dataset.aide ?? champ.placeholder;
}

// --- Parties de la page : scénario (« #scenario »), lieux (« #lieux »), PNJ (« #pnj ») ---------
function afficherSection() {
  const section = { "#lieux": "lieux", "#pnj": "pnj", "#apparence": "apparence" }[location.hash] ?? "scenario";
  document.body.dataset.section = section;
  for (const a of document.querySelectorAll(".sections a")) {
    if (a.dataset.section === section) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}
window.addEventListener("hashchange", afficherSection);
afficherSection();

// Un point sur l'onglet d'une partie qui a des modifications non enregistrées
function majModifs() {
  const modifs = { scenario: scenarioModifie(), lieux: lieuxDirty, pnj: dirty, apparence: apparenceModifiee() };
  for (const a of document.querySelectorAll(".sections a")) a.classList.toggle("a-enregistrer", modifs[a.dataset.section]);
}
for (const type of ["input", "change", "click"]) document.addEventListener(type, () => queueMicrotask(majModifs));

// --- Fiche éditable ----------------------------------------------------------
function fillForm(npc) {
  current = npc;
  for (const [k, v] of Object.entries(valeursFormulaire(npc))) $(`f-${k}`).value = v;
  masquerChamp($("f-secret"), secretMasque(npc));  // fiche de la banque lue sans mot de passe
  $("mode").textContent = titreFiche(npc);
  $("demande").open = !npc.nom;  // la demande au modèle sert pour une fiche vierge
  $("portraitStatus").textContent = "";
  majPortrait();
  showVoice();
  dirty = false;
  renderBank();
  majModifs();
}

function readForm() {
  const valeurs = Object.fromEntries(CHAMPS_FICHE.map(k => [k, $(`f-${k}`).value]));
  return ficheDuFormulaire(current, valeurs, $("f-secret").disabled);  // secret non lu : gardé par le serveur
}

let allVoices = [];
function fillVoiceList() {
  const list = voixDuGenre(allVoices, $("f-genre").value);
  const sel = $("voiceSel");
  sel.innerHTML = `<option value="">— choisir une voix —</option>` +
    list.map(v => `<option value="${esc(v.name)}">${esc(v.label ?? v.name)}</option>`).join("");
  sel.value = list.some(v => v.name === current.voix?.name) ? current.voix.name : "";
}

async function loadEngine() {
  try {
    $("engineSel").value = (await api("/api/voice-engine")).actuel;
    allVoices = await api("/api/voices");
    showVoice();
  } catch {}
}

async function pickEngine() {
  try {
    await api("/api/voice-engine", { moteur: $("engineSel").value }, "PUT");
    allVoices = await api("/api/voices");
    await otherVoice();  // les voix d'un moteur ne valent pas pour l'autre
    $("saveStatus").textContent = "Moteur changé : réenregistrez le PNJ pour garder sa nouvelle voix.";
  } catch (e) { $("saveStatus").textContent = e.message; await loadEngine(); }
}

async function pickVoice() {
  const choix = $("voiceSel").value;
  if (!choix) return;
  try { current.voix = await api("/api/voice", { ...readForm(), choix }); showVoice(); dirty = true; listen(); }
  catch (e) { $("saveStatus").textContent = e.message; }
}

function showVoice() {
  fillVoiceList();
  const v = current.voix;
  $("voiceLabel").textContent = v?.name ? `Voix : ${v.label ?? v.name}` : "Voix : attribuée à l’enregistrement";
}

const confirmDiscard = () => !dirty || confirm("Les modifications de la fiche en cours seront perdues. Continuer ?");

// --- Portrait (facultatif : [portraits] moteur dans config.toml) ----------------------
// Seulement pour un PNJ enregistré : l'image est rangée à côté de sa fiche. La génération part de la fiche
// telle qu'elle est à l'écran (apparence modifiée comprise).
let portraitsActifs = false;        // un moteur de portraits est configuré sur le serveur
let peinture = false;               // génération en cours

function majPortrait() {
  const present = !!adressePortrait(current);
  $("portraitBloc").hidden = !portraitsActifs && !present;
  $("portraitBloc").classList.toggle("en-cours", peinture);
  $("portraitImg").hidden = !present;
  if (present && !$("portraitImg").src.endsWith(adressePortrait(current))) $("portraitImg").src = adressePortrait(current);
  $("portraitVide").hidden = present;
  $("portraitVide").textContent = initiale($("f-nom").value);
  $("portraitBtn").hidden = !portraitsActifs;
  $("portraitBtn").textContent = present ? "Refaire" : "Générer le portrait";
  $("portraitBtn").disabled = !current.id || peinture;
  $("portraitSuppr").hidden = !present || peinture;
  if (!current.id && portraitsActifs) $("portraitStatus").textContent = "Enregistrez le PNJ pour lui faire un portrait.";
}

$("portraitBtn").onclick = async () => {
  const id = current.id;
  peinture = true;
  majPortrait();
  $("portraitStatus").textContent = "Le portrait se peint… (en local, le tout premier télécharge le modèle : patience)";
  try {
    const r = await api(`/api/bank/${encodeURIComponent(id)}/portrait`, readForm());
    if (current.id === id) { current.portrait = r.portrait; $("portraitImg").title = r.prompt; }
    $("portraitStatus").textContent = "";
    await refreshBank();
  } catch (e) { $("portraitStatus").textContent = e.message; }
  peinture = false;
  majPortrait();
};
$("portraitSuppr").onclick = async () => {
  if (!confirm(`Retirer le portrait de ${current.nom} ?`)) return;
  try {
    await api(`/api/bank/${encodeURIComponent(current.id)}/portrait`, undefined, "DELETE");
    current.portrait = 0;
    await refreshBank();
  } catch (e) { $("portraitStatus").textContent = e.message; }
  majPortrait();
};
$("f-nom").addEventListener("input", () => { $("portraitVide").textContent = initiale($("f-nom").value); });

// --- Scénario ----------------------------------------------------------------
// dernière version enregistrée ; chaque enregistrement envoie tous les champs (PUT remplace le scénario entier)
let scenarioCharge = { monde: "", notes_mj: "", theme: THEME_DEFAUT, style_portrait: "" };
const scenarioModifie = () => $("monde").value !== scenarioCharge.monde || $("notes").value !== scenarioCharge.notes_mj;
// Enregistre `changements` par-dessus la version enregistrée (pas la saisie en cours du texte)
async function enregistrerScenario(changements) {
  // notes non lues (sans mot de passe) : non envoyées, gardées par le serveur
  const s = await api("/api/scenario", corpsScenario(scenarioCharge, changements, $("notes").disabled), "PUT");
  if ($("notes").disabled) {  // enregistré avec le mot de passe : les notes arrivent avec la réponse
    $("notes").value = s.notes_mj ?? "";
    masquerChamp($("notes"), !("notes_mj" in s));
  }
  return s;
}

// --- Apparence : thèmes et styles de portrait (prédéfinis, modifiés ou créés pour l'univers) -------------
// /api/styles : {themes: {id: thème de l'univers}, portraits: [{id, nom, resume, prompt, origine}]} ; PUT remplace
// tout. Choisir un thème ou un style l'enregistre aussitôt dans le scénario ; les éditeurs n'enregistrent qu'au clic.
let stylesUnivers = { themes: {}, portraits: [] };
const portraitsPerso = () => persoDe(stylesUnivers.portraits);  // styles propres à l'univers (js/apparence.js)

async function chargerStyles() {
  stylesUnivers = await api("/api/styles").catch(() => ({ themes: {}, portraits: [] }));
  poserThemesPerso(stylesUnivers.themes);
  afficherThemes();
  afficherStyles();
}
async function enregistrerStyles(themes, portraits) {
  stylesUnivers = await api("/api/styles", { themes, portraits }, "PUT");
  poserThemesPerso(stylesUnivers.themes);
  afficherThemes();
  afficherStyles();
}

// Thèmes : une carte par thème, dans ses propres couleurs (data-theme)
function afficherThemes() {
  $("themes").innerHTML = tousLesThemes(stylesUnivers.themes).map(t => `
    <div class="theme-carte">
      <label class="theme-choix" data-theme="${esc(t.id)}">
        <input type="radio" name="theme" value="${esc(t.id)}">
        <span class="pastilles" aria-hidden="true"><i style="background: var(--bg)"></i><i style="background: var(--glass)"></i><i style="background: var(--verdigris)"></i><i style="background: var(--wax)"></i></span>
        <span class="nom">${esc(t.nom)}</span><small>${esc(t.resume)}${mention(t.origine)}</small>
      </label>
      <button class="ghost petit" data-modifier-theme="${esc(t.id)}">Modifier</button>
    </div>`).join("");
  const radio = document.querySelector(`input[name=theme][value="${CSS.escape(scenarioCharge.theme ?? "")}"]`);
  if (radio) radio.checked = true;
}
const themeChoisi = () => document.querySelector("input[name=theme]:checked")?.value ?? THEME_DEFAUT;
function afficherTheme(id) {
  const theme = appliquerTheme(id);
  const radio = document.querySelector(`input[name=theme][value="${CSS.escape(theme)}"]`);
  if (radio) radio.checked = true;
  return theme;
}
$("themes").onchange = async () => {
  const theme = themeChoisi();
  document.documentElement.dataset.theme = theme;
  try {
    const s = await enregistrerScenario({ theme });
    scenarioCharge = { ...s, theme: afficherTheme(s.theme) };
    $("themeStatus").textContent = `Thème « ${tousLesThemes(stylesUnivers.themes).find(t => t.id === scenarioCharge.theme).nom} » enregistré.`;
  } catch (e) {
    $("themeStatus").textContent = e.message;
    afficherTheme(scenarioCharge.theme);
  }
};

// Éditeur de thème : palettes claire et sombre (couleurs une à une), aperçu en direct sur la page
let editionTheme = null;  // {id (null : nouveau), origine, nom, resume, mode, clair, sombre}
let themeModifie = false;
const APERCU = "apercu-theme";  // identifiant de l'aperçu d'un thème pas encore enregistré
const idApercu = () => editionTheme.id ?? APERCU;
for (const mode of ["clair", "sombre"]) {
  $(`palette-${mode}`).insertAdjacentHTML("beforeend", COULEURS.map(([c, nom]) => `
    <label class="couleur"><input type="color" data-mode="${mode}" data-couleur="${c}"> ${esc(nom)} <code></code></label>`).join(""));
}
const themeEdite = () =>
  themeDuFormulaire({ nom: $("et-nom").value, resume: $("et-resume").value, mode: $("et-mode").value }, editionTheme);
function apercuTheme() {
  const t = themeEdite();
  poserThemesPerso({ ...stylesUnivers.themes, [idApercu()]: { ...t, nom: t.nom || "Aperçu" } }, false);
  document.documentElement.dataset.theme = idApercu();
  for (const p of ["clair", "sombre"]) $(`palette-${p}`).hidden = !palettesDuMode(t.mode).includes(p);
  for (const input of document.querySelectorAll(".palette input[type=color]")) {
    input.value = editionTheme[input.dataset.mode][input.dataset.couleur];
    input.nextElementSibling.textContent = input.value;
  }
  $("et-alertes").innerHTML = alertesPalettes(t).map(a => `<li>${esc(a)}</li>`).join("");
}
function ouvrirEditeurTheme(id) {
  if (apparenceModifiee() && !confirm("Les modifications en cours de l’apparence seront perdues. Continuer ?")) return;
  fermerEditeurStyle();
  const { edition, base } = editionDeTheme(tousLesThemes(stylesUnivers.themes), id, scenarioCharge.theme);
  editionTheme = edition;
  $("et-nom").value = id ? base.nom : "";
  $("et-resume").value = id ? base.resume : "";
  $("et-mode").value = base.mode;
  $("editeurThemeTitre").textContent = id ? `Modifier « ${base.nom} »` : "Nouveau thème (à partir du thème choisi)";
  $("et-supprimer").hidden = !id || base.origine === "predefini";
  $("et-supprimer").textContent = libelleSuppression("theme", base.origine);
  $("et-status").textContent = "";
  $("editeurTheme").hidden = false;
  themeModifie = false;
  apercuTheme();
  $("editeurTheme").scrollIntoView({ behavior: "smooth", block: "nearest" });
  (id ? $("et-mode") : $("et-nom")).focus();
}
function fermerEditeurTheme() {
  if (!editionTheme) return;
  editionTheme = null;
  themeModifie = false;
  $("editeurTheme").hidden = true;
  poserThemesPerso(stylesUnivers.themes);  // retire l'aperçu
  afficherTheme(scenarioCharge.theme);
  majModifs();
}
$("themes").addEventListener("click", (e) => {
  const id = e.target.closest("[data-modifier-theme]")?.dataset.modifierTheme;
  if (id) ouvrirEditeurTheme(id);
});
$("nouveauThemeBtn").onclick = () => ouvrirEditeurTheme(null);
$("editeurTheme").addEventListener("input", (e) => {
  const { mode, couleur } = e.target.dataset;
  if (mode) editionTheme[mode][couleur] = e.target.value;
  themeModifie = true;
  apercuTheme();
});
$("et-annuler").onclick = fermerEditeurTheme;
$("et-enregistrer").onclick = async () => {
  const t = themeEdite();
  if (!t.nom) { $("et-status").textContent = "Donnez un nom au thème."; $("et-nom").focus(); return; }
  const id = editionTheme.id ?? identifiant(t.nom, tousLesThemes(stylesUnivers.themes).map(x => x.id).concat(APERCU));
  try {
    await enregistrerStyles({ ...stylesUnivers.themes, [id]: t }, portraitsPerso());
    if (!editionTheme.id) scenarioCharge = await enregistrerScenario({ theme: id });  // un nouveau thème est choisi
    fermerEditeurTheme();
    $("themeStatus").textContent = `Thème « ${t.nom} » enregistré.`;
  } catch (e) { $("et-status").textContent = e.message; }
};
$("et-supprimer").onclick = async () => {
  const { id, origine } = editionTheme;
  const nom = tousLesThemes(stylesUnivers.themes).find(t => t.id === id)?.nom;
  if (!confirm(confirmationSuppression("theme", origine, nom))) return;
  const themes = { ...stylesUnivers.themes };
  delete themes[id];
  try {
    await enregistrerStyles(themes, portraitsPerso());
    if (origine === "perso" && scenarioCharge.theme === id) scenarioCharge = await enregistrerScenario({ theme: "" });
    fermerEditeurTheme();
    $("themeStatus").textContent = messageSuppression("theme", origine, nom);
  } catch (e) { $("et-status").textContent = e.message; }
};

// Styles de portrait : carte visible si les portraits sont activés ; "" = style par défaut (config.toml),
// montré comme le premier (peinture)
const styleChoisi = () => document.querySelector("input[name=style]:checked")?.value ?? "";
function afficherStyles() {
  $("styles").innerHTML = stylesUnivers.portraits.map(st => `
    <div class="style-carte">
      <label class="style-choix">
        <input type="radio" name="style" value="${esc(st.id)}">
        <span class="nom">${esc(st.nom)}</span><small>${esc(st.resume)}${mention(st.origine)}</small>
      </label>
      <button class="ghost petit" data-modifier-style="${esc(st.id)}">Modifier</button>
    </div>`).join("");
  afficherStyle(scenarioCharge.style_portrait);
}
function afficherStyle(id) {
  const radio = document.querySelector(`input[name=style][value="${CSS.escape(id ?? "")}"]`) ?? document.querySelector("input[name=style]");
  if (radio) radio.checked = true;
  const liste = stylesUnivers.portraits;
  const nom = liste.find(st => st.id === (id || liste[0]?.id))?.nom;
  $("portraitStyle").textContent = nom ? `Style : ${nom} (onglet Apparence)` : "";
}
$("styles").onchange = async () => {
  try {
    const s = await enregistrerScenario({ style_portrait: styleChoisi() });
    scenarioCharge = { ...s, theme: scenarioCharge.theme };
    afficherStyle(s.style_portrait);
    $("styleStatus").textContent = `Style « ${stylesUnivers.portraits.find(st => st.id === styleChoisi())?.nom} » enregistré.`;
  } catch (e) {
    $("styleStatus").textContent = e.message;
    afficherStyle(scenarioCharge.style_portrait);
  }
};

// Éditeur de style : nom, résumé, description anglaise pour le générateur
let editionStyle = null;  // {id (null : nouveau), origine}
let styleModifie = false;
function ouvrirEditeurStyle(id) {
  if (apparenceModifiee() && !confirm("Les modifications en cours de l’apparence seront perdues. Continuer ?")) return;
  fermerEditeurTheme();
  const st = id ? stylesUnivers.portraits.find(x => x.id === id) : null;
  editionStyle = { id: id ?? null, origine: st?.origine ?? "perso" };
  $("es-nom").value = st?.nom ?? "";
  $("es-resume").value = st?.resume ?? "";
  $("es-prompt").value = st?.prompt ?? "";
  $("editeurStyleTitre").textContent = st ? `Modifier « ${st.nom} »` : "Nouveau style";
  $("es-supprimer").hidden = !st || st.origine === "predefini";
  $("es-supprimer").textContent = libelleSuppression("style", st?.origine);
  $("es-status").textContent = "";
  $("editeurStyle").hidden = false;
  styleModifie = false;
  $("editeurStyle").scrollIntoView({ behavior: "smooth", block: "nearest" });
  $(st ? "es-prompt" : "es-nom").focus();
  majModifs();
}
function fermerEditeurStyle() {
  if (!editionStyle) return;
  editionStyle = null;
  styleModifie = false;
  $("editeurStyle").hidden = true;
  majModifs();
}
$("styles").addEventListener("click", (e) => {
  const id = e.target.closest("[data-modifier-style]")?.dataset.modifierStyle;
  if (id) ouvrirEditeurStyle(id);
});
$("nouveauStyleBtn").onclick = () => ouvrirEditeurStyle(null);
$("editeurStyle").addEventListener("input", () => { styleModifie = true; });
$("es-annuler").onclick = fermerEditeurStyle;
$("es-enregistrer").onclick = async () => {
  const st = { nom: $("es-nom").value.trim(), resume: $("es-resume").value.trim(), prompt: $("es-prompt").value.trim() };
  if (!st.nom || !st.prompt) { $("es-status").textContent = "Donnez un nom et une description au style."; return; }
  const id = editionStyle.id ?? identifiant(st.nom, stylesUnivers.portraits.map(x => x.id));
  try {
    await enregistrerStyles(stylesUnivers.themes, { ...portraitsPerso(), [id]: st });
    if (!editionStyle.id) {  // un nouveau style est choisi
      scenarioCharge = { ...(await enregistrerScenario({ style_portrait: id })), theme: scenarioCharge.theme };
      afficherStyle(id);
    }
    fermerEditeurStyle();
    $("styleStatus").textContent = `Style « ${st.nom} » enregistré.`;
  } catch (e) { $("es-status").textContent = e.message; }
};
$("es-supprimer").onclick = async () => {
  const { id, origine } = editionStyle;
  const nom = stylesUnivers.portraits.find(st => st.id === id)?.nom;
  if (!confirm(confirmationSuppression("style", origine, nom))) return;
  const portraits = portraitsPerso();
  delete portraits[id];
  try {
    await enregistrerStyles(stylesUnivers.themes, portraits);
    if (origine === "perso" && scenarioCharge.style_portrait === id) {
      scenarioCharge = { ...(await enregistrerScenario({ style_portrait: "" })), theme: scenarioCharge.theme };
      afficherStyle("");
    }
    fermerEditeurStyle();
    $("styleStatus").textContent = messageSuppression("style", origine, nom);
  } catch (e) { $("es-status").textContent = e.message; }
};
const apparenceModifiee = () => (!!editionTheme && themeModifie) || (!!editionStyle && styleModifie);

async function loadScenario() {
  const s = await api("/api/scenario").catch(() => ({}));
  $("monde").value = s.monde || "";
  $("notes").value = s.notes_mj || "";
  masquerChamp($("notes"), !("notes_mj" in s));
  scenarioCharge = { monde: $("monde").value, notes_mj: $("notes").value, theme: afficherTheme(s.theme),
                     style_portrait: s.style_portrait || "" };
  afficherStyle(scenarioCharge.style_portrait);
  majModifs();
}
async function saveScenario() {
  try {
    const s = await enregistrerScenario({ monde: $("monde").value, notes_mj: $("notes").value });
    $("monde").value = s.monde;
    $("notes").value = s.notes_mj;
    scenarioCharge = { ...s, theme: afficherTheme(s.theme) };
    $("scenarioStatus").textContent = "Scénario enregistré.";
  } catch (e) { $("scenarioStatus").textContent = e.message; }
  majModifs();
}

// --- Partager l'univers (export zip, import zip ou dossier) ----------------------
$("exportUniversBtn").onclick = async () => {
  if (scenarioModifie() || lieuxDirty) {
    $("universStatus").textContent = "Enregistrez d’abord le scénario et les lieux : l’export prend la version enregistrée.";
    return;
  }
  $("universStatus").textContent = "";
  try { await exporter(); retirer("acces"); }  // export : secrets compris, donc mot de passe du MJ hors du PC
  catch (e) { $("universStatus").textContent = e.message; }
};
$("importZipBtn").onclick = () => $("importZip").click();
$("importDossierBtn").onclick = () => $("importDossier").click();
for (const id of ["importZip", "importDossier"]) {
  $(id).onchange = async () => {
    const fichiers = [...$(id).files];
    $(id).value = "";  // pour pouvoir réimporter le même fichier
    if (!fichiers.length || !confirm(confirmationImport(bank.length, $("garderPnj").checked))) return;
    try {
      const r = await importerFichiers(fichiers, $("garderPnj").checked);
      lieuxDirty = false;
      await chargerStyles();
      await Promise.all([loadScenario(), loadLieux(), refreshBank()]);
      if (current.id && !bank.some(n => n.id === current.id)) delete current.id;  // fiche retirée de la banque
      $("universStatus").textContent = resumeImport(r);
    } catch (e) { $("universStatus").textContent = e.message; }
    majModifs();
  };
}

// --- Lieux -------------------------------------------------------------------
let lieux = [];          // lieux enregistrés (menus « Lieu habituel »)
let lieuxEdit = [];      // lieux en cours d'édition
let lieuxDirty = false;

async function loadLieux() {
  lieux = await api("/api/lieux").catch(() => []);
  lieuxEdit = lieux.map(l => ({ ...l }));
  renderLieux();
  fillLieuOptions();
}

// Une carte par lieu : nom, description, notes du MJ, et les PNJ de la banque qui y vivent
function renderLieux() {
  $("nbLieux").textContent = lieux.length || "";
  $("lieuxListe").innerHTML = lieuxEdit.length ? lieuxEdit.map((l, i) => {
    const habitants = l.id ? bank.filter(n => n.lieu === l.id).map(n => n.nom) : [];
    return `
    <article class="carte lieu-fiche">
      <div class="titre">
        <input type="text" data-i="${i}" data-champ="nom" value="${esc(l.nom)}" placeholder="Nom du lieu (ex. Auberge du Sanglier)" aria-label="Nom du lieu">
        <button class="ghost petit" data-suppr="${i}" aria-label="Supprimer ${esc(l.nom)}">Supprimer</button>
      </div>
      <label for="lieu-${i}-description">Description <small>— lue par le narrateur, connue des PNJ</small></label>
      <textarea id="lieu-${i}-description" rows="3" data-i="${i}" data-champ="description" placeholder="Ex. : Une salle basse et enfumée, des tonneaux en guise de tables.">${esc(l.description)}</textarea>
      <label for="lieu-${i}-notes">Notes du MJ <small>— secrets du lieu</small></label>
      <textarea id="lieu-${i}-notes" rows="2" data-i="${i}" data-champ="notes_mj" ${"notes_mj" in l
        ? `placeholder="Ex. : Une trappe sous le comptoir mène aux égouts."` : `disabled placeholder="${esc(MASQUE)}"`}>${esc(l.notes_mj ?? "")}</textarea>
      <p class="habitants">
        <span>${habitants.length ? `PNJ : ${esc(habitants.join(", "))}` : l.id ? "Aucun PNJ ici." : "Lieu pas encore enregistré."}</span>
        ${l.id ? `<button class="ghost petit" data-creer="${esc(l.id)}">Créer un PNJ ici</button>` : ""}
      </p>
    </article>`;
  }).join("") : `<p class="vide">Aucun lieu : les PNJ ne sont rattachés à aucun endroit. Ajoutez-en un pour commencer.</p>`;
}

// Menus « Lieu habituel » de la demande et de la fiche
function fillLieuOptions() {
  for (const sel of document.querySelectorAll(".lieux-sel")) {
    const valeur = sel.id === "f-lieu" ? (current.lieu ?? "") : sel.value;
    sel.innerHTML = `<option value="">— Aucun —</option>`
      + lieux.map(l => `<option value="${esc(l.id)}">${esc(l.nom)}</option>`).join("");
    sel.value = lieux.some(l => l.id === valeur) ? valeur : "";
  }
}

$("lieuxListe").oninput = (e) => {
  const { i, champ } = e.target.dataset;
  if (i === undefined) return;
  lieuxEdit[Number(i)][champ] = e.target.value;
  lieuxDirty = true;
};
$("lieuxListe").onclick = (e) => {
  const creer = e.target.dataset.creer;
  if (creer !== undefined) {  // nouvelle fiche, demande au modèle préremplie avec ce lieu
    if (!confirmDiscard()) return;
    fillForm({});
    $("reqLieu").value = creer;
    location.hash = "pnj";
    $("reqRole").focus();
    return;
  }
  const i = e.target.dataset.suppr;
  if (i === undefined) return;
  const l = lieuxEdit[Number(i)];
  if (l.nom && !confirm(`Supprimer « ${l.nom} » ? Les PNJ qui y vivent n’auront plus de lieu habituel.`)) return;
  lieuxEdit.splice(Number(i), 1);
  lieuxDirty = true;
  renderLieux();
};
$("ajoutLieuBtn").onclick = () => {
  lieuxEdit.push({ nom: "", description: "", notes_mj: "" });
  lieuxDirty = true;
  renderLieux();
  $("lieuxListe").querySelector(".lieu-fiche:last-child input")?.focus();
};
$("saveLieuxBtn").onclick = async () => {
  try {
    lieux = await api("/api/lieux", lieuxEdit, "PUT");  // les lieux sans nom sont ignorés
    lieuxEdit = lieux.map(l => ({ ...l }));
    lieuxDirty = false;
    renderLieux();
    fillLieuOptions();
    renderBank();
    $("lieuxStatus").textContent = `${lieux.length} lieu${lieux.length > 1 ? "x" : ""} enregistré${lieux.length > 1 ? "s" : ""}.`;
  } catch (e) { $("lieuxStatus").textContent = e.message; }
  majModifs();
};

// --- Banque ------------------------------------------------------------------
let bank = [];
async function refreshBank() {
  bank = await api("/api/bank").catch(() => []);
  renderBank();
  if (!lieuxDirty) renderLieux();  // PNJ de chaque lieu (sans effacer une saisie en cours)
}
// Vignette : le portrait, sinon l'initiale (si les portraits sont activés)
const vignette = (n) => n.portrait ? `<img class="mini" src="${adressePortrait(n)}" alt="">`
  : portraitsActifs ? `<span class="mini" aria-hidden="true">${esc(initiale(n.nom))}</span>` : "";
// Banque groupée par lieu habituel ; le PNJ de la fiche est mis en évidence
function renderBank() {
  $("nbPnj").textContent = bank.length || "";
  $("bankList").innerHTML = bank.length ? parLieu(bank, lieux).map(({ lieu, pnjs }) =>
    `<li class="groupe">${lieu ? esc(lieu.nom) : "Sans lieu"}</li>` + pnjs.map(n => `
    <li class="${n.id === current.id ? "current" : ""}">
      <button class="who" data-edit="${esc(n.id)}">${vignette(n)}<span class="txt">${esc(n.nom)}<small>${esc(n.metier)}</small></span></button>
      <button class="ghost suppr" data-del="${esc(n.id)}" aria-label="Supprimer ${esc(n.nom)}" title="Supprimer">✕</button>
    </li>`).join("")).join("") : `<li class="vide">Aucun PNJ enregistré. Demandez-en un au modèle, ou remplissez la fiche.</li>`;
}
$("bankList").onclick = async (e) => {
  const edit = e.target.closest("[data-edit]")?.dataset.edit, del = e.target.closest("[data-del]")?.dataset.del;
  try {
    if (edit && confirmDiscard()) fillForm(await api(`/api/bank/${encodeURIComponent(edit)}`));
    if (del) {
      const n = bank.find(x => x.id === del);
      if (!confirm(`Supprimer « ${n?.nom} » de la banque ?`)) return;
      await api(`/api/bank/${encodeURIComponent(del)}`, undefined, "DELETE");
      if (current.id === del) { delete current.id; $("mode").textContent = "Proposition (non enregistrée)"; }
      await refreshBank();
    }
  } catch (err) { $("saveStatus").textContent = err.message; }
};

// --- Génération, enregistrement, voix ---------------------------------------
async function generate() {
  if (!confirmDiscard()) return;
  $("genBtn").disabled = true; $("genStatus").textContent = "Le PNJ prend forme…";
  try {
    fillForm(await api("/api/npc/generate", { role: $("reqRole").value, nom: $("reqNom").value,
                                              genre: $("reqGenre").value, consignes: $("reqConsignes").value,
                                              lieu: $("reqLieu").value }));
    $("genStatus").textContent = "";
    $("saveStatus").textContent = "Proposition prête : relisez et ajustez la fiche, puis enregistrez-la.";
    document.querySelector(".sheet").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { $("genStatus").textContent = e.message; }
  $("genBtn").disabled = false;
}

async function save() {
  const npc = readForm();
  if (!npc.nom || !npc.salutation) { $("saveStatus").textContent = "Il faut au moins un nom et une première réplique."; return; }
  try {
    const { id } = npc.id ? await api(`/api/bank/${encodeURIComponent(npc.id)}`, npc, "PUT")
                          : await api("/api/bank", npc);
    fillForm(await api(`/api/bank/${encodeURIComponent(id)}`));  // relit la voix attribuée par le serveur
    await refreshBank();
    $("saveStatus").textContent = `${npc.nom} est enregistré.`;
  } catch (e) { $("saveStatus").textContent = e.message; }
}

async function otherVoice() {
  try { current.voix = await api("/api/voice", readForm()); showVoice(); dirty = true; }
  catch (e) { $("saveStatus").textContent = e.message; }
}

// Une seule lecture à la fois : une nouvelle écoute coupe la précédente, et une réponse
// arrivée en retard (voix changée entre-temps) n'est pas jouée.
let player = null, listenId = 0;
function stopListen() {
  if (player) { player.pause(); URL.revokeObjectURL(player.src); player = null; }
}

async function listen() {
  const text = $("f-salutation").value.trim();
  if (!text) return;
  const id = ++listenId;
  stopListen();
  if (!current.voix?.name) await otherVoice();
  let blob;
  try {
    const r = await requete("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ text, voice: current.voix }) });
    if (id !== listenId) return;
    if (!r.ok) { $("saveStatus").textContent = "Synthèse vocale indisponible (voix absente, ou réseau coupé pour Edge)."; return; }
    blob = await r.blob();
  } catch (e) { if (id === listenId) $("saveStatus").textContent = e.message; return; }
  if (id !== listenId) return;
  stopListen();
  const audio = player = new Audio(URL.createObjectURL(blob));
  audio.onended = () => { if (player === audio) stopListen(); };  // fin de lecture : URL d'objet libérée
  audio.play().catch((e) => {
    if (player === audio) stopListen();
    if (e.name === "NotAllowedError") $("saveStatus").textContent = "Le navigateur a bloqué le son : cliquez de nouveau sur Écouter.";
  });
}

$("genBtn").onclick = generate;
$("saveBtn").onclick = save;
$("newBtn").onclick = () => { if (confirmDiscard()) { fillForm({}); $("saveStatus").textContent = ""; } };
$("voiceSel").onchange = pickVoice;
$("engineSel").onchange = pickEngine;
$("listenBtn").onclick = listen;
$("saveScenarioBtn").onclick = saveScenario;
document.querySelector(".sheet").addEventListener("input", () => { dirty = true; });
$("f-genre").addEventListener("change", otherVoice);  // une voix du nouveau genre
window.addEventListener("beforeunload", (e) => {
  if (dirty || lieuxDirty || scenarioModifie() || apparenceModifiee()) e.preventDefault();
});

loadEngine();
fillForm({});
api("/api/config").then(c => {
  portraitsActifs = !!c.portraits;
  $("stylesCarte").hidden = !portraitsActifs;
  majPortrait();
  renderBank();
}).catch(() => {});
verifierSante();
// Droits de cet appareil d'abord (mot de passe du MJ demandé s'il en faut un) : les secrets des PNJ et les notes du
// MJ ne sont envoyés qu'avec lui. Annuler = lecture seule, champs réservés au MJ grisés.
verifierAcces({ message: "Préparer l’univers depuis cet appareil demande le mot de passe du MJ." })
  .then((acces) => {
    if (acces.mj) return;
    signaler(acces.protege
      ? "Lecture seule : secrets des PNJ et notes du MJ masqués sur cet appareil. Le mot de passe du MJ sera demandé au premier enregistrement."
      : "Lecture seule : sans mot de passe du MJ (à définir dans les options, sur le PC du serveur), l’univers ne se modifie que depuis ce PC.",
      { cle: "acces", niveau: "avertissement" });
  })
  .catch((e) => signaler(e.message, { cle: "acces" }))
  .finally(() => {
    chargerStyles().then(loadScenario);
    loadLieux().then(refreshBank);
  });
