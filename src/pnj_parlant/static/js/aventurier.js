// Aventurier joué et jets de dés (sans DOM). Facultatifs : sans aventurier, le joueur reste « le voyageur » et
// n'a que le dé sans bonus. Les bonus de chaque jet viennent du serveur (/api/aventuriers : `jets`,
// aventuriers.py) ; ici, on lance le dé et on écrit le résultat.

// Jet sans caractéristique (pas d'aventurier, ou jet de chance)
export const JET_LIBRE = { id: "libre", nom: "chance", groupe: "", carac: "", bonus: 0, avantage: false };
export const MODES = { normal: "Normal", avantage: "Avantage (dé bonus)", desavantage: "Désavantage (dé malus)" };

// « +3 », « −1 » (vrai signe moins), « +0 »
export const formaterBonus = (n) => (n < 0 ? `−${-n}` : `+${n}`);

// D&D 5e : modificateur d'un score de caractéristique (10 → +0, 15 → +2, 8 → −1)
export const modificateurDnd = (score) => Math.floor((score - 10) / 2);

// D&D 5e : bonus de maîtrise selon le niveau (+2 aux niveaux 1 à 4… +6 aux niveaux 17 à 20)
export const bonusDeMaitrise = (niveau) => 2 + Math.floor((Math.max(1, niveau || 1) - 1) / 4);

// Aperçu des bonus dans la fiche en cours d'édition (mêmes calculs que `jets` d'aventuriers.py, qui fait foi) :
// systeme = entrée de /api/systemes. → {caracs: {id: bonus}, competences: {id: bonus}, capacites: [bonus], maitrise}
export function apercuBonus(av, systeme) {
  const valeur = (c) => av.caracteristiques?.[c] ?? systeme.defaut;
  const mod = (c) => (systeme.scores ? modificateurDnd(valeur(c)) : valeur(c));
  const maitrise = bonusDeMaitrise(av.niveau);
  return {
    maitrise,
    caracs: Object.fromEntries(systeme.caracteristiques.map(c => [c.id, mod(c.id)])),
    competences: Object.fromEntries(systeme.competences.map(c =>
      [c.id, mod(c.carac) + maitrise * (av.maitrises?.[c.id] ?? 0)])),
    capacites: (av.capacites ?? []).map(c => mod(c.carac) + (c.bonus ?? 0)),
  };
}

// Un d20 (hasard : fonction [0, 1[ injectable dans les tests)
const d20 = (hasard) => 1 + Math.floor(hasard() * 20);

// Lance le jet : d20 + bonus ; avantage (dé bonus de COF) = deux d20, le meilleur ; désavantage = le pire.
// → {des: [d20…], naturel (le d20 gardé), bonus, total, mode}
export function lancer(jet, mode = "normal", hasard = Math.random) {
  const des = mode === "normal" ? [d20(hasard)] : [d20(hasard), d20(hasard)];
  const naturel = mode === "avantage" ? Math.max(...des) : mode === "desavantage" ? Math.min(...des) : des[0];
  return { des, naturel, bonus: jet.bonus, total: naturel + jet.bonus, mode };
}

// Ce que vaut le résultat, en mots (le PNJ ne voit jamais de chiffre) ; seuils des difficultés usuelles des deux
// systèmes : 10 facile, 15 moyen, 20 difficile. Un 20 naturel réussit toujours, un 1 naturel échoue toujours.
export function appreciation({ naturel, total }) {
  if (naturel === 20) return "réussite critique";
  if (naturel === 1) return "échec critique";
  if (total >= 20) return "excellent résultat";
  if (total >= 15) return "bon résultat";
  if (total >= 10) return "résultat moyen";
  if (total >= 5) return "mauvais résultat";
  return "très mauvais résultat";
}

// « de Force », « d’Agilité », « d’Histoire »
const de = (nom) => (/^[aeiouyhàâéèêëîïôûüœ]/i.test(nom) ? `d’${nom}` : `de ${nom}`);

// Ligne envoyée au PNJ (history) : « (Jet de Persuasion : bon résultat.) », sans chiffre
export const texteJet = (jet, r) => `(Jet ${de(jet.nom)} : ${appreciation(r)}.)`;

// Ligne du journal : « (Jet de Persuasion : 17, bon résultat.) »
export const affichageJet = (jet, r) => `(Jet ${de(jet.nom)} : ${r.total}, ${appreciation(r)}.)`;

// Détail du dé : « d20 : 14 +3 » ou « 2d20 (14, 6), garde 14 +3 »
export function detailJet(r) {
  const des = r.des.length > 1 ? `2d20 (${r.des.join(", ")}), garde ${r.naturel}` : `d20 : ${r.naturel}`;
  return r.bonus ? `${des} ${formaterBonus(r.bonus)}` : des;
}

// Menu des jets : [{groupe: "" | "Caractéristiques" | …, jets: [{jet, libelle}]}], le dé sans bonus en tête
export function menuJets(aventurier) {
  const groupes = [{ groupe: "", jets: [{ jet: JET_LIBRE, libelle: "d20 sans bonus" }] }];
  for (const jet of aventurier?.jets ?? []) {
    let g = groupes.find(x => x.groupe === jet.groupe);
    if (!g) groupes.push(g = { groupe: jet.groupe, jets: [] });
    const carac = jet.carac && jet.groupe !== "Caractéristiques" ? ` (${jet.carac})` : "";
    g.jets.push({ jet, libelle: `${jet.nom}${carac} ${formaterBonus(jet.bonus)}${jet.avantage ? " ★" : ""}` });
  }
  return groupes;
}

// Jet choisi dans le menu (id), sinon le dé sans bonus
export const jetChoisi = (aventurier, id) => aventurier?.jets?.find(j => j.id === id) ?? JET_LIBRE;

// « Paladin humain · D&D 5e, niveau 5 » : sous le nom de l'aventurier
export function resumeAventurier(av, systemes = {}) {
  const systeme = systemes[av.systeme]?.nom?.replace(/ \((\d+)e édition\)$/, " $1e");
  const jeu = systeme ? `${systeme}${av.niveau ? `, niveau ${av.niveau}` : ""}` : "";
  return [av.classe, jeu].filter(Boolean).join(" · ");
}

// Fiche envoyée avec chaque réplique : sans ce qui ne sert qu'à la page (jets, portrait)
export function ficheAventurier(av) {
  if (!av) return null;
  const { jets, portrait, ...fiche } = av;  // eslint-disable-line no-unused-vars
  return fiche;
}

// Adresse du portrait d'un aventurier, "" s'il n'en a pas (version = date : le cache suit l'image)
export const portraitAventurier = (av) =>
  av?.id && av.portrait ? `/api/aventuriers/${encodeURIComponent(av.id)}/portrait?v=${av.portrait}` : "";
