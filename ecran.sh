#!/usr/bin/env bash
# Coupe ou rallume l'interface graphique de Linux pour laisser toute la mémoire vidéo au modèle local.
# Le bureau et l'écran de connexion occupent environ 700 Mo de la carte graphique : sur une carte
# de 4 Go (NVIDIA T400), c'est ce qui manque pour que le modèle tourne à 100 % sur le GPU.
#
#   ./ecran.sh couper                 # jusqu'au prochain redémarrage du PC
#   ./ecran.sh couper --permanent     # le PC démarrera aussi sans écran graphique
#   ./ecran.sh rallumer [--permanent] # inverse
#   ./ecran.sh etat                   # mémoire vidéo et répartition CPU/GPU du modèle
#
# À lancer de préférence en SSH : couper l'écran ferme la session graphique et tout ce qui y tourne.
set -euo pipefail

OLLAMA_URL="http://127.0.0.1:11434"
CONTENEUR="pnj-ollama"

etat() {
  echo "Démarrage par défaut : $(systemctl get-default)"
  if systemctl is-active --quiet display-manager; then
    echo "Écran graphique      : allumé"
  else
    echo "Écran graphique      : coupé"
  fi
  if command -v nvidia-smi >/dev/null; then
    echo
    nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader \
      | awk -F', ' '{print "Carte graphique      : " $1 ", " $2 " utilisés sur " $3}'
    nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader \
      | sed 's/^/  calcul : /'
  fi
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTENEUR"; then
    echo
    docker exec "$CONTENEUR" ollama ps
  fi
}

# Décharge le modèle : il sera rechargé à la prochaine réplique, en profitant de la mémoire libérée.
decharger_modele() {
  local modele
  modele=$(docker exec "$CONTENEUR" ollama ps 2>/dev/null | awk 'NR>1 {print $1}') || return 0
  for m in $modele; do
    curl -s "$OLLAMA_URL/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null || true
    echo "Modèle $m déchargé : il sera rechargé sur la carte graphique à la prochaine réplique."
  done
}

action="${1:-}"
permanent=false
[[ "${2:-}" == "--permanent" ]] && permanent=true

case "$action" in
  couper)
    if [[ -z "${SSH_CONNECTION:-}" ]]; then
      echo "Attention : vous n'êtes pas en SSH. Couper l'écran va fermer cette session graphique,"
      read -r -p "et tout ce qui y est ouvert. Continuer ? [o/N] " rep
      [[ "$rep" =~ ^[oOyY]$ ]] || { echo "Annulé."; exit 1; }
    fi
    if $permanent; then
      sudo systemctl set-default multi-user.target
    fi
    sudo systemctl isolate multi-user.target
    sleep 3
    decharger_modele
    echo
    etat
    ;;
  rallumer)
    if $permanent; then
      sudo systemctl set-default graphical.target
    fi
    sudo systemctl isolate graphical.target
    echo "Écran graphique rallumé. Le modèle risque de ne plus tenir entièrement sur la carte graphique."
    ;;
  etat)
    etat
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
