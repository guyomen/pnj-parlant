// Fiche de PNJ et scénario de la page de préparation (creation.html), sans DOM : passage fiche ↔ champs du
// formulaire, champs réservés au MJ (absents d'une réponse lue sans son mot de passe : jamais renvoyés).

// Champs du formulaire, chacun dans l'élément « f-<champ> »
export const CHAMPS_FICHE = ["nom", "metier", "genre", "humeur", "timbre", "debit", "lieu", "apparence", "personnalite",
                             "connaissances", "secret", "salutation"];

// Valeur de chaque champ pour une fiche : connaissances une par ligne ; genre, timbre et débit par défaut
export function valeursFormulaire(npc) {
  const valeurs = {};
  for (const k of CHAMPS_FICHE) {
    const v = npc[k] ?? "";
    valeurs[k] = Array.isArray(v) ? v.join("\n") : v;
  }
  if (!npc.genre) valeurs.genre = "neutre";
  if (!npc.timbre) valeurs.timbre = "moyen";
  if (!npc.debit) valeurs.debit = "normal";
  return valeurs;
}

// Fiche lue dans le formulaire, par-dessus `courant` (id, voix, portrait…). `secretMasque` : le secret n'a pas été
// lu (sans mot de passe du MJ) ; il n'est pas envoyé et le serveur garde celui de la banque.
export function ficheDuFormulaire(courant, valeurs, secretMasque = false) {
  const npc = { ...courant };
  for (const k of CHAMPS_FICHE) npc[k] = String(valeurs[k] ?? "").trim();
  npc.connaissances = npc.connaissances.split("\n").map(s => s.trim()).filter(Boolean);
  if (secretMasque) delete npc.secret;
  return npc;
}

// Fiche de la banque lue sans le mot de passe du MJ : son secret est absent de la réponse
export const secretMasque = (npc) => !!npc.id && !("secret" in npc);

// Titre de la fiche en cours
export const titreFiche = (npc) => npc.id ? `Modification de ${npc.nom}` : (npc.nom ? "Proposition (non enregistrée)" : "Nouveau PNJ");

// Voix proposées pour un genre (toutes pour « neutre »)
export const voixDuGenre = (voix, genre) => voix.filter(v => genre === "neutre" || v.genre === genre);

// Initiale du nom, affichée à la place d'un portrait absent
export const initiale = (nom) => (String(nom ?? "").trim()[0] ?? "?").toUpperCase();

// Corps du PUT /api/scenario : `changements` par-dessus la version enregistrée (PUT remplace le scénario entier :
// un champ n'en efface pas un autre). Notes du MJ non lues (`notesMasquees`) : non envoyées, gardées par le serveur.
export function corpsScenario(enregistre, changements, notesMasquees = false) {
  const corps = { ...enregistre, ...changements };
  if (notesMasquees) delete corps.notes_mj;
  return corps;
}
