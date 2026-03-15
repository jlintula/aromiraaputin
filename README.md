# Aromiraaputin

A lightweight proxy that fetches school and daycare lunch menus from [CGI Aromi](https://www.cgisaas.fi/) instances and serves them as simple JSON or embeddable HTML. Supports multiple cities with configurable Aromi endpoints.

## Why?

The official Aromi menu site is an Angular SPA that loads menu data via POST requests with complex JSON payloads. This makes it impossible to embed directly in Home Assistant's iframe card or any other simple HTML embed — you can't make POST requests from an iframe. This proxy handles the Aromi API communication and re-serves the menus as plain GET-based HTML pages that work anywhere.

## Features

- Fetches menus directly from the Aromi API (no headless browser needed)
- Multi-city support — built-in configs for Jyväskylä, Helsinki, and Tampere
- Easy to add new cities (any Aromi instance with the same API)
- Five time ranges: today, this week, next week, 3rd week, 4th week
- Clean HTML output with light/dark theme for iframe embedding
- Configurable favorite restaurants via environment variable
- In-memory caching (24h for restaurant list, 4h for menus)

## Quick start

```bash
docker compose up -d
```

Open http://localhost:8090/menu to browse menus, or use the API directly.

## Supported cities

| City | Aromi instance |
|---|---|
| Jyväskylä (default) | `aromimenu.cgisaas.fi/JyvaskylaAromieMenus` |
| Helsinki | `aromi.hel.fi/aromiemenus` |
| Tampere | `aromimenu.cgisaas.fi/TampereAromieMenus` |

Adding a new city requires only a new entry in the `CITIES` dict in `app/scraper.py` with the base URL and currentpage path.

## API

All endpoints accept an optional `city` parameter (default: `jyvaskyla`). Valid values: `jyvaskyla`, `helsinki`, `tampere`.

| Endpoint | Description |
|---|---|
| `GET /menu` | HTML picker UI with city selector |
| `GET /menu?restaurant={code}&range={today\|week\|nextweek\|week3\|week4}&theme={light\|dark}&city={city}` | Embeddable HTML menu |
| `GET /api/restaurants?city={city}` | JSON list of all restaurants grouped by type |
| `GET /api/menu?restaurant={code}&range={today\|week\|nextweek\|week3\|week4}&city={city}` | JSON menu data |
| `GET /health` | Health check |
| `GET /docs` | Swagger UI |

## Home Assistant

```yaml
type: iframe
url: "http://localhost:8090/menu?restaurant=KeltinmakiKOU&range=today&theme=dark&city=jyvaskyla"
aspect_ratio: "4:3"
```

## Configuration

| Environment variable | Description | Example |
|---|---|---|
| `AROMIRAAPUTIN_CITY` | Override default city (used when no `city` param is given) | `tampere` |
| `AROMIRAAPUTIN_FAVORITES` | Quick-access restaurants on the picker page (shown for default city). Format: `code:name,code:name` | `MyllytupaPK:Myllytuvan päiväkoti,KeltinmakiKOU:Keltinmäen koulu` |

Restaurant codes can be found via the `/api/restaurants?city={city}` endpoint.

## Docker image

Pre-built images are published to GitHub Container Registry on every push to `main`. Example `docker-compose.yml` file:

```yaml
services:
  aromiraaputin:
    image: ghcr.io/jlintula/aromiraaputin:latest
    ports:
      - "8090:8090"
    restart: unless-stopped
    environment:
      - AROMIRAAPUTIN_CITY=jyvaskyla
      - AROMIRAAPUTIN_FAVORITES=MyllytupaPK:Myllytuvan päiväkoti,KeltinmakiKOU:Keltinmäen koulu
```
