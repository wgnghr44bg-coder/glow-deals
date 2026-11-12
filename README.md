# Glow Deals

Site met de laagste prijzen voor Charlotte Tilbury make-up bij winkels die naar Nederland leveren.

- `update.py` haalt de prijzen op bij Notino, Breuninger, Space NK, Cult Beauty (VK) en Amazon USA en schrijft `docs/data.json`.
  Lukt een winkel niet, dan blijven de vorige prijzen van die winkel staan.
- `docs/index.html` is de site (GitHub Pages uit de map `docs`).
- `.github/workflows/update.yml` werkt de prijzen twee keer per dag bij.

Douglas, ICI Paris XL, de Bijenkorf, bol, Lookfantastic en de officiële site blokkeren automatisch ophalen;
daarvoor staan zoekknoppen op de site.

Lokaal bijwerken: `python update.py` (of `python update.py notino` voor één winkel).
