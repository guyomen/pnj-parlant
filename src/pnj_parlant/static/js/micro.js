// Micro du joueur (page de jeu) : niveau sonore, fin de parole, ouverture de l'analyse. Logique sans DOM ;
// l'API audio du navigateur est injectable pour les tests.

// Micro demandé au navigateur : suppression d'écho (voix du PNJ dans les haut-parleurs), de bruit, gain automatique
export const CONTRAINTES_MICRO = { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } };

// Niveau d'un bloc d'échantillons (-1 à 1) : moyenne quadratique
export function niveauRms(echantillons) {
  if (!echantillons.length) return 0;
  let somme = 0;
  for (const x of echantillons) somme += x * x;
  return Math.sqrt(somme / echantillons.length);
}

// Analyse du son d'un micro ouvert : {ctx, analyser, niveau()} ; niveau() lit le niveau actuel. Firefox exige que
// l'AudioContext ait la même fréquence que le micro. En cas d'échec, le contexte créé est refermé (erreur levée).
export async function ouvrirAnalyse(stream, { AudioContext = globalThis.AudioContext } = {}) {
  const rate = stream.getAudioTracks()[0]?.getSettings().sampleRate;
  const ctx = rate ? new AudioContext({ sampleRate: rate }) : new AudioContext();
  try {
    if (ctx.state === "suspended") await ctx.resume();
    const analyser = ctx.createAnalyser();
    ctx.createMediaStreamSource(stream).connect(analyser);
    const echantillons = new Float32Array(analyser.fftSize);
    const niveau = () => { analyser.getFloatTimeDomainData(echantillons); return niveauRms(echantillons); };
    return { ctx, analyser, niveau };
  } catch (e) {
    ctx.close().catch(() => {});
    throw e;
  }
}

// Fin de parole d'un enregistrement (listenLocal) : seuil adaptatif, le bruit de fond est mesuré pendant la
// calibration (une demi-seconde), la voix est nettement au-dessus. ajouter(niveau, maintenant) renvoie vrai quand il
// faut arrêter : `silence` ms de silence après la voix, aucune voix pendant `attenteMax` ms, ou `dureeMax` ms en tout.
// dejaEntendu + bruit : le joueur vient de couper la parole au PNJ (voix déjà entendue, bruit déjà mesuré).
// muet() : rien reçu du tout (mauvais périphérique ou micro coupé), à ne pas envoyer à la transcription.
export function suiviEcoute({ debut, bruit = 0, dejaEntendu = false, calibrage = dejaEntendu ? 0 : 500, silence = 1200,
                              attenteMax = 8000, dureeMax = 30000, plancher = 0.004, facteur = 3 } = {}) {
  const s = { entendu: dejaEntendu, dernierSon: debut, pic: 0, bruit };
  s.ajouter = (niveau, maintenant) => {
    s.pic = Math.max(s.pic, niveau);
    if (maintenant - debut < calibrage) s.bruit = Math.max(s.bruit, niveau);
    const seuil = Math.max(plancher, s.bruit * facteur);
    if (maintenant - debut >= calibrage && niveau > seuil) { s.entendu = true; s.dernierSon = maintenant; }
    return (s.entendu && maintenant - s.dernierSon > silence) || (!s.entendu && maintenant - debut > attenteMax)
      || maintenant - debut > dureeMax;
  };
  s.muet = () => !s.entendu && s.pic < 0.0005;
  return s;
}

// Barre de niveau affichée pendant l'écoute (20 crans au plus)
export const barreNiveau = (niveau) => "▮".repeat(Math.min(20, Math.round(niveau * 200)));
