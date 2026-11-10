// Pilote Edge (protocole DevTools) comme un joueur : lieux, aborder, déplacement à la voix, compagnon.
import { spawn } from "node:child_process";

const [edge, profil] = process.argv.slice(2);
const navigateur = spawn(edge, ["--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=9333",
                                `--user-data-dir=${profil}`, "about:blank"], { stdio: "ignore" });
const pause = (ms) => new Promise(r => setTimeout(r, ms));
let cible;
for (let i = 0; i < 50 && !cible; i++) {
  await pause(200);
  try { cible = (await (await fetch("http://127.0.0.1:9333/json/list")).json()).find(t => t.type === "page"); } catch {}
}
const ws = new WebSocket(cible.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let n = 0; const attente = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); attente.get(d.id)?.(d); attente.delete(d.id); };
const cdp = (method, params = {}) => new Promise(r => { const id = ++n; attente.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const js = async (expression) => (await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
async function quand(expression, ms = 8000) {
  for (let t = 0; t < ms; t += 100) { if (await js(expression)) return true; await pause(100); }
  return false;
}
const resultats = [];
const verifier = (nom, ok) => { resultats.push(`${ok ? "OK  " : "ÉCHEC"} ${nom}`); };

// Voix du navigateur instantanée : le casque n'existe pas en mode sans écran
await cdp("Page.addScriptToEvaluateOnNewDocument", { source:
  "window.speechSynthesis.speak = (u) => setTimeout(() => u.onend && u.onend(), 5);" });
await cdp("Page.navigate", { url: "http://127.0.0.1:5917/" });
verifier("menu des lieux rempli (aucun + 2 lieux)", await quand(`document.querySelectorAll("#lieuSel option").length === 3`));

await js(`(() => { const s = document.getElementById("lieuSel"); s.value = "auberge-du-sanglier"; s.dispatchEvent(new Event("change")); })()`);
verifier("narration de l'arrivée à l'auberge", await quand(`document.querySelector(".narration-line")?.textContent.includes("Vous arrivez : Auberge du Sanglier. Une salle enfumée.")`));
verifier("Ysolde est là, Brom non", await quand(`(() => { const t = document.getElementById("ici").textContent; return t.includes("Ysolde") && !t.includes("Brom"); })()`));

await js(`[...document.querySelectorAll("[data-aborder]")].find(b => b.textContent.includes("Ysolde")).click()`);
verifier("aborder Ysolde : fiche et salutation", await quand(`document.querySelector(".pnj-card h1")?.textContent === "Ysolde" && document.getElementById("log").textContent.includes("Bienvenue au Sanglier")`));
await quand(`!document.getElementById("ask").disabled`);

await js(`(() => { document.getElementById("ask").value = "Allons à la forge de Brom !"; document.getElementById("sendBtn").click(); })()`);
verifier("proposition de déplacement", await quand(`!document.getElementById("proposition").hidden && document.getElementById("propTexte").textContent === "Aller à : Forge de Brom ?"`));
verifier("Ysolde répond depuis l'auberge", await quand(`document.getElementById("log").textContent.includes("Moi, Ysolde, je suis bien à Auberge du Sanglier")`));
await quand(`!document.getElementById("propOui").disabled`);

await js(`(() => { const c = document.querySelector("[data-suit='0']"); c.checked = true; c.dispatchEvent(new Event("change", { bubbles: true })); })()`);
await js(`document.getElementById("propOui").click()`);
verifier("arrivée à la forge, menu à jour", await quand(`document.getElementById("lieuSel").value === "forge-de-brom" && [...document.querySelectorAll(".narration-line")].some(l => l.textContent.includes("Vous arrivez : Forge de Brom"))`));
verifier("Ysolde a suivi, Brom est là", await quand(`document.querySelector(".pnj-card h1")?.textContent === "Ysolde" && document.getElementById("ici").textContent.includes("Brom")`));
verifier("fiche : se trouve à la forge, habituellement à l'auberge", await js(`(() => { const t = document.querySelector(".pnj-card").textContent; return t.includes("Se trouve : Forge de Brom") && t.includes("Lieu habituel : Auberge du Sanglier"); })()`));
verifier("proposition masquée", await js(`document.getElementById("proposition").hidden`));
await quand(`!document.getElementById("ask").disabled`);

await js(`(() => { document.getElementById("ask").value = "Tu te plais ici ?"; document.getElementById("sendBtn").click(); })()`);
verifier("Ysolde répond depuis la forge", await quand(`document.getElementById("log").textContent.includes("Moi, Ysolde, je suis bien à Forge de Brom")`));
await quand(`!document.getElementById("ask").disabled`);

// Sans compagnon : Ysolde reste à la forge quand on retourne à l'auberge
await js(`(() => { const c = document.querySelector("[data-suit='0']"); c.checked = false; c.dispatchEvent(new Event("change", { bubbles: true })); const s = document.getElementById("lieuSel"); s.value = "auberge-du-sanglier"; s.dispatchEvent(new Event("change")); })()`);
verifier("Ysolde reste derrière (narration, scène vide)", await quand(`[...document.querySelectorAll(".narration-line")].some(l => l.textContent.includes("Ysolde reste derrière")) && !document.querySelector(".pnj-card")`));
verifier("de retour à l'auberge, Ysolde n'y est plus", await quand(`!document.getElementById("ici").textContent.includes("Ysolde") && !document.getElementById("ici").textContent.includes("Brom")`));

verifier("banque regroupée par lieu, Ysolde avec Brom à la forge", await js(`[...document.querySelectorAll("#bankSel optgroup")].map(o => o.label + " : " + [...o.children].map(c => c.textContent.split(" — ")[0]).join(", ")).join(" | ")`) === "Forge de Brom : Brom, Ysolde");

// Ysolde est restée à la forge : on l'y retrouve
await js(`(() => { const s = document.getElementById("lieuSel"); s.value = "forge-de-brom"; s.dispatchEvent(new Event("change")); })()`);
verifier("Ysolde retrouvée à la forge, avec Brom", await quand(`(() => { const t = document.getElementById("ici").textContent; return t.includes("Ysolde") && t.includes("Brom"); })()`));

console.log(resultats.join("\n"));
ws.close(); navigateur.kill();
process.exit(resultats.some(r => r.startsWith("ÉCHEC")) ? 1 : 0);
