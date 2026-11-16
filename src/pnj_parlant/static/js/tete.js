// Script classique (pas un module), chargé dans le <head> des deux pages avant les feuilles de style : il pose
// le thème du scénario (et le CSS des thèmes de l'univers) gardés par le navigateur avant l'affichage, sans
// flash de l'ancien thème. Ils sont ensuite relus depuis le serveur (js/univers.js, chargerTheme).
try {
  document.documentElement.dataset.theme = localStorage.getItem("theme") || "";
  const css = localStorage.getItem("theme-css");
  if (css) document.head.appendChild(Object.assign(document.createElement("style"), { id: "themes-perso", textContent: css }));
} catch {}
