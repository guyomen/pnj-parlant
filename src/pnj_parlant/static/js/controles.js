// État des contrôles de la vue Partie (sans DOM) : setBusy (index.html) l'applique aux éléments de la page.

// e : {busy (action en cours), npcs (scène), rencontres, maxPnj, multi (« Plusieurs PNJ »), entree (« Faire entrer »),
//      interrompre (« Parler interrompt le PNJ »), parole (un PNJ parle), ecoute (le micro écoute), microDispo
//      (reconnaissance locale ou du navigateur), choixBanque (id choisi dans la banque, "" sinon), modeleModifiable}
// Renvoie {desactive: {id: bool}, cache: {id: bool}, aborder, retirer, sousOptions} : boutons « Aborder » et
// « Retirer de la scène » désactivés, sous-options de « Plusieurs PNJ » actives.
export function etatControles(e) {
  const b = e.busy, n = e.npcs.length, scene = n > 0, plein = n >= e.maxPnj;
  return {
    desactive: {
      genBtn: b,
      sendBtn: b || !scene,
      ask: b || !scene,
      // pendant que le PNJ parle, « Parler » lui coupe la parole (option) ; en écoute, il reste cliquable pour finir
      micBtn: !e.ecoute && ((b && !(e.parole && e.interrompre)) || !scene || !e.microDispo),
      saveBtn: b || !e.npcs.some(x => !x.id),  // tous déjà dans la banque
      exportBtn: !e.rencontres.length,
      importBtn: b,
      lieuSel: b,
      propOui: b,
      loadBtn: b || !e.choixBanque,
      addBtn: b || !scene || plein || !e.choixBanque || e.npcs.some(x => x.id === e.choixBanque),
      entreeBtn: b || !scene || plein,
      discuterBtn: b,
      modeleSel: b || !e.modeleModifiable,
    },
    cache: {
      addBtn: !e.multi,
      entreeRow: !(e.entree && e.multi) || !scene,  // faire entrer quelqu'un : seulement dans une scène
      discuterBtn: !e.multi || n < 2,
    },
    aborder: b || (plein && e.multi),
    retirer: b,
    sousOptions: e.multi,  // sans « Plusieurs PNJ », ses sous-options sont grisées
  };
}
