// Fonctions pures de la page de jeu (sans DOM ni réseau) : testées par tests/js/scene.test.mjs.

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Minuscules sans accents : « Écoute » → « ecoute »
export const norm = (s) => String(s ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

// --- Narration ------------------------------------------------------------------
// Le texte entre parenthèses décrit la scène (geste, ton…) : il est lu par une voix neutre de narrateur.
export const NARRATION = /(\([^)]*\)?)/;  // parenthèse fermante facultative : réponse coupée en cours de route

// [[morceau, narration ?], ...] : « (Il sourit.) Bienvenue ! » → [["Il sourit.", true], ["Bienvenue !", false]]
export const segments = (text) => text.split(NARRATION)
  .map(s => NARRATION.test(s) ? [s.replace(/[()]/g, "").trim(), true] : [s.trim(), false])
  .filter(([s]) => /[\p{L}\p{N}]/u.test(s));

// HTML d'une réplique : les descriptions en italique
export const formatLine = (text) => text.split(NARRATION)
  .map(s => NARRATION.test(s) ? `<em class="narration">${esc(s)}</em>` : esc(s)).join("");

// --- Qui répond ? -------------------------------------------------------------------
const MOTS_VIDES = new Set(["les", "des", "aux", "dit", "del", "van", "von"]);

// Mots qui désignent un PNJ : les mots de son nom, et le premier mot de son métier (« forgeron »)
export function motsCles(npc) {
  const mots = norm(npc.nom).split(/[^a-z0-9]+/);
  mots.push(norm(npc.metier).split(/[^a-z0-9]+/)[0]);
  return mots.filter(m => m.length >= 3 && !MOTS_VIDES.has(m));
}

// PNJ de `npcs` nommés (ou désignés par leur métier) dans la phrase du joueur, dans l'ordre où ils sont cités
export function interpelles(text, npcs) {
  const t = norm(text);
  const position = (n) => Math.min(...motsCles(n).map(m => {
    const i = t.search(new RegExp(`\\b${m}\\b`));
    return i < 0 ? Infinity : i;
  }));
  return npcs.map(n => ({ n, pos: position(n) })).filter(x => x.pos < Infinity)
    .sort((a, b) => a.pos - b.pos).map(x => x.n);
}

// PNJ à qui `auteur` vient de poser une question (« Et pour toi, Léonard ? ») : ils répondront eux-mêmes.
// Seules comptent les phrases interrogatives : « Léonard est un idiot. Une bière ? » n'appelle pas Léonard.
export function questionnes(reply, auteur, npcs) {
  const questions = reply.split(/(?<=[.!?…])\s+/).filter(phrase => phrase.includes("?")).join(" ");
  return questions ? interpelles(questions, npcs.filter(n => n !== auteur)) : [];
}

// --- Lieux ------------------------------------------------------------------------------
// Verbes de déplacement (sans accents) : « allons à la forge », « emmène-moi au port »…
const DEPLACEMENT = /\b(allons|allez|aller|va|vais|partons|partir|rendons|rendez|rends|rendre|retournons|retourner|rejoignons|rejoindre|emmene|emmenez|emmener|conduis|conduisez|conduire|menez|mene|direction)\b/;
const MOTS_VIDES_LIEU = new Set(["dans", "pour", "avec", "chez", "vers", "sous", "entre", "petit", "petite", "grand", "grande", "vieux", "vieille"]);

// Le lieu (autre que `actuel`) où le joueur propose d'aller, ou null : il faut un verbe de déplacement
// et un mot du nom du lieu (« Allons voir Brom à la forge » → « Forge de Brom »).
export function lieuEvoque(text, lieux, actuel) {
  const t = norm(text);
  if (!DEPLACEMENT.test(t)) return null;
  const position = (lieu) => Math.min(...norm(lieu.nom).split(/[^a-z0-9]+/)
    .filter(m => m.length >= 4 && !MOTS_VIDES_LIEU.has(m))
    .map(m => { const i = t.search(new RegExp(`\\b${m}\\b`)); return i < 0 ? Infinity : i; }));
  const candidats = lieux.filter(l => l.id !== actuel).map(l => ({ l, pos: position(l) }))
    .filter(x => x.pos < Infinity).sort((a, b) => a.pos - b.pos);
  return candidats.length ? candidats[0].l : null;
}

// Texte lu par le narrateur en arrivant dans un lieu ; `restent` : PNJ laissés derrière
export function arrivee(lieu, restent = []) {
  const depart = restent.length
    ? `${restent.map(n => n.nom).join(" et ")} ${restent.length > 1 ? "restent" : "reste"} derrière. ` : "";
  return `(${depart}Vous arrivez : ${lieu.nom}.${lieu.description ? " " + lieu.description : ""})`;
}

// Deux voix identiques (même nom de voix et même locuteur)
// Où se trouve un PNJ pendant la partie : là où on l'a laissé, sinon son lieu habituel ("" : nulle part)
export function position(pnj, lieux, positions = {}) {
  const id = positions[pnj.nom] ?? pnj.lieu ?? "";
  return lieux.some(l => l.id === id) ? id : "";
}

// PNJ regroupés par lieu, dans l'ordre des lieux du scénario (le lieu actuel d'abord), puis ceux sans lieu.
// → [{ lieu: {id, nom} | null, pnjs }] ; les lieux vides sont omis.
export function parLieu(pnjs, lieux, positions = {}, actuel = "") {
  const ordre = [...lieux.filter(l => l.id === actuel), ...lieux.filter(l => l.id !== actuel), null];
  return ordre.map(lieu => ({ lieu, pnjs: pnjs.filter(p => position(p, lieux, positions) === (lieu?.id ?? "")) }))
    .filter(g => g.pnjs.length);
}

export const memeVoix = (a, b) => !!a?.name && a.name === b?.name && (a.speaker ?? null) === (b?.speaker ?? null);

// --- PNJ qui entre en cours de discussion ---------------------------------------------
// Consignes de création : la scène, la personne demandée (`qui`, peut être vide), la conversation
export function consignesEntree(history, npcs, qui = "") {
  const presents = npcs.map(n => `${n.nom} (${n.metier})`).join(" et ");
  const conversation = history.slice(-12).map(m => `${m.speaker || "Voyageur"} : ${m.content}`).join("\n").slice(-2500);
  return [
    `Ce PNJ entre dans une scène déjà commencée, où se trouvent ${presents} et un voyageur.`,
    qui.trim() ? `Qui entre : ${qui.trim()}.`
      : "Qui entre : de préférence une personne évoquée dans la conversation, sinon quelqu'un qui a une bonne raison d'être là.",
    "Si la conversation parle de cette personne, reprends son nom, son métier et tout ce qui en a été dit.",
    "Sa salutation réagit à ce qui vient de se dire ; il peut interpeller les présents par leur nom.",
    `Conversation jusqu'ici :\n${conversation}`,
  ].join("\n");
}

// --- Export de la conversation ----------------------------------------------------------
// lignes : [[qui, texte], ...] tel qu'affiché (qui vide : narration, par exemple l'arrivée dans un lieu)
// lieu : nom du lieu de la scène au moment de l'export ("" : aucun)
export function texteExport(lignes, npcs, date, lieu = "") {
  const entete = [`Conversation avec ${npcs.map(n => `${n.nom}, ${n.metier}`).join(" ; ")}`,
                  ...npcs.map(n => npcs.length > 1 ? `${n.nom} : ${n.apparence}` : n.apparence),
                  ...(lieu ? [`Lieu : ${lieu}`] : []),
                  date.toLocaleString("fr-FR", { dateStyle: "full", timeStyle: "short" })].join("\n");
  const corps = lignes.map(([qui, t]) => qui ? `${qui} : ${t}` : t).join("\n\n");
  return `${entete}\n\n${SEPARATEUR}\n\n${corps}\n`;
}

const SEPARATEUR = "—".repeat(40);
const VOUS = "Vous";

// --- Import d'une conversation exportée ---------------------------------------------------
// Relit le texte de texteExport (anciens exports compris, sans ligne « Lieu »).
// → { pnjs: [{nom, metier, apparence}], lignes: [[qui, texte]] (qui : nom, "Vous" ou "" pour une
//     narration), lieu: nom du lieu ou "" }. Lève une erreur si ce n'est pas une conversation exportée.
export function lireExport(texte) {
  const propre = (texte.charCodeAt(0) === 0xFEFF ? texte.slice(1) : texte).replace(/\r\n?/g, "\n");
  const coupure = propre.indexOf(`\n${SEPARATEUR}\n`);
  const entete = propre.slice(0, coupure).split("\n");
  if (coupure < 0 || !entete[0].startsWith("Conversation avec ")) {
    throw new Error("Ce fichier n’est pas une conversation exportée.");
  }
  const pnjs = entete[0].slice("Conversation avec ".length).split(" ; ").map(p => {
    const i = p.indexOf(", ");
    return i < 0 ? { nom: p.trim(), metier: "", apparence: "" }
                 : { nom: p.slice(0, i).trim(), metier: p.slice(i + 2).trim(), apparence: "" };
  });
  let lieu = "";
  for (const l of entete.slice(1)) {
    const p = pnjs.find(n => l.startsWith(`${n.nom} : `));
    if (pnjs.length > 1 && p) p.apparence = l.slice(p.nom.length + 3);
    else if (l.startsWith("Lieu : ")) lieu = l.slice(7);
  }
  if (pnjs.length === 1) pnjs[0].apparence = entete[1] ?? "";
  // le nom le plus long d'abord : « Brom le Jeune » avant « Brom »
  const auteurs = [...pnjs.map(p => p.nom), VOUS].sort((a, b) => b.length - a.length);
  const lignes = propre.slice(coupure + SEPARATEUR.length + 2).split(/\n\n+/).map(b => b.trim()).filter(Boolean)
    .map(b => {
      const qui = auteurs.find(a => b.startsWith(`${a} : `));
      return qui ? [qui, b.slice(qui.length + 3)] : ["", b];
    });
  if (!lieu) {  // ancien export : le dernier lieu où le narrateur a mené le voyageur
    for (const [qui, t] of lignes) {
      const m = !qui && t.match(/Vous arrivez : ([^.]+)\./);
      if (m) lieu = m[1];
    }
  }
  return { pnjs, lignes, lieu };
}

// PNJ encore dans la scène à la fin d'une conversation importée : ceux qui ont parlé depuis la dernière
// arrivée dans un lieu (ou depuis le début), les `max` derniers, dans l'ordre où ils ont parlé la première fois.
export function sceneImportee(lignes, max = 3) {
  let debut = 0;
  lignes.forEach(([qui, t], i) => { if (!qui && t.includes("Vous arrivez : ")) debut = i + 1; });
  const parlent = lignes.slice(debut).map(([qui]) => qui).filter(qui => qui && qui !== VOUS);
  const recents = [...new Set([...parlent].reverse())].slice(0, max);
  return [...new Set(parlent)].filter(qui => recents.includes(qui));
}

// Consignes pour recréer un PNJ d'une conversation importée qui n'est pas dans la banque
export function consignesRecreation(pnj, lignes) {
  const dits = lignes.filter(([qui]) => qui === pnj.nom).slice(-6).map(([, t]) => `- ${t}`);
  return [`Ce personnage existe déjà : garde exactement son nom (${pnj.nom}) et son métier (${pnj.metier}).`,
          pnj.apparence && `Apparence : ${pnj.apparence}`,
          dits.length && `Il a dit dans une conversation (garde la même personnalité) :\n${dits.join("\n")}`]
    .filter(Boolean).join("\n");
}

export function nomFichierExport(npcs, date) {
  const slug = norm(npcs.map(n => n.nom).join(" et ")).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "pnj";
  const p2 = (n) => String(n).padStart(2, "0");
  return `conversation-${slug}-${date.getFullYear()}-${p2(date.getMonth() + 1)}-${p2(date.getDate())}`
    + `-${p2(date.getHours())}h${p2(date.getMinutes())}.txt`;
}

// Détecteur de prise de parole au micro, alimenté par le niveau (RMS) mesuré à intervalles réguliers.
// Le bruit de fond est mesuré pendant `calibrage` ms ; ensuite, il y a voix quand le niveau dépasse
// `facteur` fois ce bruit (et au moins `plancher`) pendant `duree` ms, avec des creux de `trou` ms
// tolérés (la voix n'est pas continue). Un claquement bref ne déclenche donc rien.
export function detecteurVoix({ calibrage = 500, facteur = 4, plancher = 0.01, duree = 300, trou = 150 } = {}) {
  let debut = null, bruit = 0, depuis = null, dernierSon = null;
  return {
    get bruit() { return bruit; },
    get seuil() { return Math.max(plancher, bruit * facteur); },
    ajouter(niveau, t) {
      debut ??= t;
      if (t - debut < calibrage) { bruit = Math.max(bruit, niveau); return false; }
      if (niveau > this.seuil) { depuis ??= t; dernierSon = t; }
      else if (depuis !== null && t - dernierSon > trou) depuis = null;
      return depuis !== null && t - depuis >= duree;
    },
  };
}
