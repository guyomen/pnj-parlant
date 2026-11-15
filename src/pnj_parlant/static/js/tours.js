// Qui parle, et dans quel ordre (page de jeu) : sans DOM, le hasard est injecté pour les tests.
import { questionnes } from "./scene.js";

// Répliques d'affilée au plus quand les PNJ s'interpellent les uns les autres
export const MAX_TOURS = 4;

// Un élément de la liste au hasard ; hasard() rend un nombre de [0, 1) comme Math.random
export const auHasard = (liste, hasard = Math.random) => liste[Math.floor(hasard() * liste.length)];

// Option « Interventions spontanées » : de temps en temps (probabilité `proba`), un PNJ de la scène qui n'est pas
// déjà dans `ordre` réagit à la suite. `ordre` est complété sur place et renvoyé.
export function avecIntervention(ordre, npcs, { actif, proba = 0.3, hasard = Math.random } = {}) {
  const restants = npcs.filter(n => !ordre.includes(n));
  if (actif && restants.length && hasard() < proba) ordre.push(auHasard(restants, hasard));
  return ordre;
}

// Qui répond au joueur : tous les PNJ cités (dans l'ordre) ; un seul cité, ou personne (alors celui qui a parlé
// en dernier, sinon le premier de la scène), avec une intervention spontanée possible.
export function ordreDesReponses(cites, npcs, dernier, intervention = {}) {
  if (cites.length > 1) return cites;
  return avecIntervention(cites.length ? cites : [npcs.includes(dernier) ? dernier : npcs[0]], npcs, intervention);
}

// « Laissez-les discuter » : un autre PNJ que celui qui vient de parler répond (intervention possible ensuite)
export function ordreDiscussion(npcs, dernier, intervention = {}) {
  const autres = npcs.filter(n => n !== dernier);
  return avecIntervention([auHasard(autres, intervention.hasard)], npcs, intervention);
}

// Les PNJ questionnés par une réplique passent en tête de la file, dans l'ordre où ils sont cités, une seule fois
// chacun (retirés de leur place s'ils y étaient déjà). `file` est modifiée sur place et renvoyée.
export function prioriser(file, appeles) {
  for (const appele of [...appeles].reverse()) {
    const deja = file.indexOf(appele);
    if (deja >= 0) file.splice(deja, 1);
    file.unshift(appele);
  }
  return file;
}

// Les PNJ de `ordre` parlent l'un après l'autre : tour(n, voixPrecedente) écrit la réplique de n et renvoie
// {voice (fin de sa parole), erreur, reply}. Chacun commence pendant que le précédent parle encore. Un PNJ à qui
// une réplique pose une question répond juste après (au plus `max` répliques). Arrêt sur Stop (`signal`), sur une
// erreur, ou si le PNJ a quitté la scène (`presents()`). Renvoie {tours, voix : fin de la dernière parole}.
export async function enchainerTours(ordre, { tour, presents, signal, max = MAX_TOURS }) {
  const tours = [], file = [...ordre];
  let voix = Promise.resolve();
  while (file.length && tours.length < max) {
    const n = file.shift();
    if (signal?.aborted || !presents().includes(n)) break;
    const t = await tour(n, voix);
    tours.push(t);
    voix = t.voice;
    if (t.erreur) break;
    prioriser(file, questionnes(t.reply, n, presents()));
  }
  return { tours, voix };
}

// Réplique interrompue (Stop, ou le joueur coupe la parole) : le PNJ « se souvient » seulement de ce qu'il a eu le
// temps de dire. `entree` ({speaker, content}) est raccourcie à `dit`, ou retirée de `history` s'il n'a rien dit.
export function oublierNonDit(history, entree, dit) {
  if (dit) entree.content = dit;
  else if (history.includes(entree)) history.splice(history.indexOf(entree), 1);
}
