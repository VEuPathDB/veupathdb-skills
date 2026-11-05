# Coffee shops 2025 (synthetic)

Fictional data on twelve coffee shops in four regions of England: the teams
and staff working in each shop, the seasonal menus and menu items, and monthly
accounts, January to October 2025. Money is in pounds sterling (GBP), although
no column header says so.

Files: `regions.csv`, `coffee_shops.csv`, `teams.csv`, `staff.csv`,
`menus.csv`, `menu_items.csv`, `monthly_accounts.csv` and
`coffee-shops-data-dictionary.md`. The entity tree is region > coffee shop >
(team > staff member), (menu > menu item) and monthly account. There are 500
leaf records: 180 staff, 200 menu items and 120 monthly accounts.

This dataset is synthetic. ChatGPT wrote it, as if typed into spreadsheets by
hand, from this prompt:

> Please could you make me a small (~500 records of "leaf entities")
> multi-entity/relational synthetic tabular dataset? The entities could be
> something to do with coffee shops. Maybe
>
> region < coffee shop < team < staff
> coffee shop < menu < menu item
> coffee shop < something-to-do-with-turnover/accounting
>
> The synthetic data should pretend to be hand-entered into spreadsheets - so
> plenty of small typos. However, for this dataset let's assume all the
> keys/IDs and foreign/parent keys/IDs are correct. A child entity tabular file
> need only provide a column for the immediate parent entity.
>
> Column headings should not be completely self-explanatory, e.g. a "cost" or
> "price" heading should not state which currency.
>
> CSV or TSV - your choice.

The problems in it include typos in names and categories, three date formats
(`2025-01-01`, `01/05/25`, `31/10/2025`, and `2025/02-01`), comma decimals,
the letter O typed for zero, numbers marked uncertain with a trailing `?`, the
placeholders `-` and `n/a`, stray spaces, a shop named `-`, and staff names.

`spec.json` is the spec from a curation session with the tabular-to-stf skill
(Claude Sonnet, 26 October 2026, session
`28cb949f-04fa-420d-ac6e-d6d21eeef8aa`), with two changes: `inputDir` points
at `inputs`, and `team.team_extension` is `string` categorical. The session
used integer categorical to work around study-wrangler #95, which 1.0.54
fixes, so this fixture also guards against that bug.
