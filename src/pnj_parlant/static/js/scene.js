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

// Deux voix identiques (même nom de voix et même locuteur)
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
// lignes : [[qui, texte], ...] tel qu'affiché
export function texteExport(lignes, npcs, date) {
  const entete = [`Conversation avec ${npcs.map(n => `${n.nom}, ${n.metier}`).join(" ; ")}`,
                  ...npcs.map(n => npcs.length > 1 ? `${n.nom} : ${n.apparence}` : n.apparence),
                  date.toLocaleString("fr-FR", { dateStyle: "full", timeStyle: "short" })].join("\n");
  return `${entete}\n\n${"—".repeat(40)}\n\n${lignes.map(([qui, t]) => `${qui} : ${t}`).join("\n\n")}\n`;
}

export function nomFichierExport(npcs, date) {
  const slug = norm(npcs.map(n => n.nom).join(" et ")).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "pnj";
  const p2 = (n) => String(n).padStart(2, "0");
  return `conversation-${slug}-${date.getFullYear()}-${p2(date.getMonth() + 1)}-${p2(date.getDate())}`
    + `-${p2(date.getHours())}h${p2(date.getMinutes())}.txt`;
}
