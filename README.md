# Swiss Electricity Tariffs (ElCom/LINDAS)

Home Assistant Custom Integration that fetches Swiss electricity tariffs from the ElCom electricityprice dataset published on the LINDAS SPARQL endpoint.

Domain: `swiss_electricity_tariffs`

Features:
- Search and select a Swiss municipality (Gemeinde) during config flow
- Choose tariff year (default: current year)
- Sensors for total, energy, grid, fees, and metering price components
- Async-only I/O using Home Assistant's aiohttp client
- Daily caching via DataUpdateCoordinator; options allow changing update interval (hours)
- Robust model discovery to adapt to dataset schema differences

Data Source:
- SPARQL Endpoint: https://lindas.admin.ch/query
- Named Graph: https://lindas.admin.ch/elcom/electricityprice

## Installation (HACS)

1. Open HACS > Integrations
2. Add custom repository (if this is not listed on HACS): this repo URL
3. Search for "Swiss Electricity Tariffs" and install
4. Restart Home Assistant
5. Add the integration via Settings > Devices & Services > Add Integration

## Manual Installation

- Copy the `custom_components/swiss_electricity_tariffs` folder into your Home Assistant `config/custom_components/` directory.
- Restart Home Assistant
- Add integration via UI

## Configuration

1. Step 1: Enter a municipality name (e.g., "Erlenbach", "Balgach"). The integration performs a SPARQL search and displays up to 10 matches.
2. Step 2: Choose the tariff year. Default is your current local year.
3. Finish setup. The integration creates sensors:
   - Swiss Tariff {Municipality} Total Price
   - Swiss Tariff {Municipality} Energy Price
   - Swiss Tariff {Municipality} Grid Price
   - Swiss Tariff {Municipality} Fees Price
   - Swiss Tariff {Municipality} Metering Price

Attributes include municipality label/URI, year, source (ElCom/LINDAS), last update (ISO), and a limited list of raw observation ids.

Options:
- You can change municipality (with search), year, and update interval (hours). Default update interval is 24 hours.

## How it works

- The integration queries LINDAS using SPARQL (POST, JSON results).
- A discovery step learns which predicates represent municipality and year by sampling observation triples and scoring predicates using simple heuristics.
- Then it fetches observation triples filtered by the discovered predicates for the selected municipality and year.
- Finally, it maps predicates to price components (total/energy/grid/fees/metering) using keyword matching and exposes the first best match per component.

Notes:
- If multiple tariff profiles (e.g., household vs. business) exist, the integration picks the first best match and logs a debug message.
- Units are inferred from data (prefers CHF/kWh); metering may use CHF/month or CHF/year.

## Troubleshooting

- No results when searching:
  - Check your spelling; search is case-insensitive and matches substrings.
  - Try a shorter search term.
- Cannot connect / timeout:
  - Verify internet connectivity.
  - LINDAS endpoint may be rate-limited or temporarily unavailable.
  - Try again later.
- Sensors show `unknown`:
  - Not all municipalities/years may have complete data. Check Home Assistant logs on debug level for details.

## Privacy & Logging

- The integration logs debug information about query sizes and result counts, but not sensitive personal data.
- Municipality URIs and labels may appear in debug logs.

## Development

- Python: async/await only; no blocking calls.
- No external libraries required (uses Home Assistant's aiohttp session).
- Code style: type hints, no pandas.

## License

MIT
