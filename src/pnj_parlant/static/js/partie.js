// La partie en cours (page de jeu) et ses transitions, sans DOM : la page les applique puis réaffiche.
//   npcs        PNJ de la scène ; le premier est le principal
//   history     toute la scène : [{speaker: nom du PNJ, ou null pour le joueur ou le narrateur, content}]
//   dernier     PNJ qui a parlé en dernier : il répond quand le joueur ne nomme personne
//   rencontres  tous les PNJ croisés depuis le début de la conversation (export, sauvegarde)
//   lieuActuel  identifiant du lieu de la scène ("" : aucun)
//   positions   nom du PNJ → lieu où il se trouve pendant la partie (sinon : son lieu habituel)
// Les transitions modifient la partie sur place (la page garde un seul objet).
import { VERSION_PARTIE, fichesRelues } from "./scene.js";

export const nouvellePartie = () =>
  ({ npcs: [], history: [], dernier: null, rencontres: [], lieuActuel: "", positions: {} });

// Remise à zéro (« Nouvelle table », nouvel univers chargé depuis l'accueil)
export function vider(partie) {
  Object.assign(partie, nouvellePartie());
}

const existe = (lieux, id) => !!lieux.find(l => l.id === id)?.nom;

// Nouvelle scène avec ce PNJ seul (il salue), dans le lieu où il se trouve s'il en a un : on va le voir là où il est.
export function nouvelleScene(partie, n, lieux) {
  const p = partie;
  p.npcs = [n];
  p.history = [{ speaker: n.nom, content: n.salutation }];
  p.dernier = n;
  p.rencontres = [n];
  const ou = p.positions[n.nom] ?? n.lieu;
  if (existe(lieux, ou)) p.lieuActuel = ou;
  if (p.lieuActuel) p.positions[n.nom] = p.lieuActuel;
}

// Le PNJ rejoint la scène en cours (il salue) ; il est désormais là où se trouve la scène
export function rejoindre(partie, n) {
  const p = partie;
  p.npcs.push(n);
  p.history.push({ speaker: n.nom, content: n.salutation });
  p.dernier = n;
  if (!p.rencontres.some(x => x.nom === n.nom)) p.rencontres.push(n);
  if (p.lieuActuel) p.positions[n.nom] = p.lieuActuel;
}

// Le PNJ de rang i quitte la scène ; renvoie sa fiche
export function retirer(partie, i) {
  const [n] = partie.npcs.splice(i, 1);
  if (partie.dernier === n) partie.dernier = partie.npcs[0];
  return n;
}

// Changement de lieu : les PNJ qui n'accompagnent pas le voyageur (`suit`) restent là où on les quitte, les
// compagnons suivent et gardent le souvenir de la conversation (une ligne de narration la complète) ; sans
// compagnon, elle repart à zéro. `id` inconnu = aucun lieu. Renvoie {lieu (ou undefined), restent}.
export function changerDeLieu(partie, id, lieux) {
  const p = partie;
  const lieu = lieux.find(l => l.id === id);
  const restent = p.npcs.filter(n => !n.suit);
  p.npcs = p.npcs.filter(n => n.suit);
  if (!p.npcs.includes(p.dernier)) p.dernier = p.npcs[0] ?? null;
  if (p.lieuActuel) for (const n of restent) p.positions[n.nom] = p.lieuActuel;
  p.lieuActuel = lieu ? id : "";
  for (const n of p.npcs) p.positions[n.nom] = p.lieuActuel || undefined;
  if (!p.npcs.length) p.history = [];
  else if (lieu) p.history.push({ speaker: null, content: `(Le voyageur et ses compagnons arrivent : ${lieu.nom}.)` });
  return { lieu, restent };
}

// Conversation importée (lireExport) : `lignes` [[qui, texte]], `fiches` (PNJ qui y parlent), `scene` (ceux qui
// restent en scène), `lieu` (identifiant, "" s'il n'existe plus). Répond ensuite le dernier de la scène à avoir parlé.
// Sans PNJ en scène, la conversation repart de zéro (comme en arrivant seul dans un lieu).
export function reprendreImport(partie, lignes, fiches, scene, lieu) {
  const p = partie;
  p.rencontres = fiches;
  p.npcs = scene;
  const parle = lignes.map(([qui]) => qui).filter(qui => scene.some(n => n.nom === qui));
  p.dernier = scene.find(n => n.nom === parle.at(-1)) ?? scene[0] ?? null;
  p.lieuActuel = lieu;
  for (const n of scene) p.positions[n.nom] = lieu || undefined;
  p.history = !scene.length ? [] : lignes.map(([qui, t]) => ({ speaker: qui && qui !== "Vous" ? qui : null, content: t }));
}

// Sauvegarde dans ce navigateur (JSON) : null s'il n'y a rien à garder. `lignes` : journal affiché, `tokenUsage` :
// compteur de tokens.
export function instantane(partie, lignes, tokenUsage) {
  const p = partie;
  if (!p.rencontres.length) return null;
  return { version: VERSION_PARTIE, rencontres: p.rencontres, scene: p.npcs.map(n => n.nom), dernier: p.dernier?.nom ?? null,
           history: p.history, lieuActuel: p.lieuActuel, positions: p.positions, lignes, tokenUsage };
}

// Reprend une sauvegarde déjà vérifiée (partieValide) : fiches relues sur le serveur fusionnées (fichesRelues,
// `relues` : fiche ou null par rencontre), lieu oublié s'il n'existe plus.
export function restaurer(partie, sauvegarde, relues, lieux) {
  const p = partie, s = sauvegarde;
  const scene = s.scene ?? [];
  p.rencontres = fichesRelues(s.rencontres, scene, relues);
  p.npcs = scene.map(nom => p.rencontres.find(r => r.nom === nom)).filter(Boolean);
  p.dernier = p.npcs.find(n => n.nom === s.dernier) ?? p.npcs[0] ?? null;
  p.history = s.history ?? [];
  p.lieuActuel = lieux.some(l => l.id === s.lieuActuel) ? s.lieuActuel : "";
  p.positions = s.positions ?? {};
}

// Compteur de tokens : `usage` ({input_tokens, output_tokens}) de la dernière réplique ajouté au cumul
export const compteurVide = () => ({ input: 0, output: 0, lastInput: null, lastOutput: 0, available: false });
export function cumulerUsage(compteur, usage) {
  compteur.lastInput = usage.input_tokens;
  compteur.lastOutput = usage.output_tokens;
  compteur.input += usage.input_tokens;
  compteur.output += usage.output_tokens;
  compteur.available = true;
  return compteur;
}
