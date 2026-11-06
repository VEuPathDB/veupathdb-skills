# Notes on the coffee shop spreadsheets

This is fictional data.

I've put these notes together so anyone picking up the spreadsheets can see what the columns are for. The menus and monthly figures are for January to October 2025. Money is in pounds (£).

## Regions

The areas we group the shops into for day-to-day management.

| Column | What it means |
| --- | --- |
| region_id | Our reference for the region. |
| name | What we call the region, e.g. South East. |
| area | A bit more detail about the area it covers. |
| contact | The person who looks after that region. |

## Coffee shops

The basic details for each of our shops.

| Column | What it means |
| --- | --- |
| shop_id | Our reference for the shop. |
| region_id | Which region the shop is in. |
| name | The shop's name. |
| town | The town or city it's in. |
| address | The street address. |
| opened | When the shop first opened. |
| seats | How many customers we can seat. |
| status | Whether the shop is open. |

## Teams

The teams working in each shop, such as the bar or kitchen team.

| Column | What it means |
| --- | --- |
| team_id | Our reference for the team. |
| shop_id | The shop where the team works. |
| name | What the team does. |
| shift | The shifts they usually cover: early, late or a mixture. |
| ext | Their internal phone extension. |

## Staff

Staff details and their usual working arrangements.

| Column | What it means |
| --- | --- |
| staff_id | The person's staff reference. |
| team_id | The team they work in. |
| first | First name. |
| surname | Surname. |
| role | Their job, e.g. barista or kitchen assistant. |
| start | When they started working for us. |
| hours | Their contracted hours per week. |
| rate | Their hourly pay before deductions. |
| contract | Whether they're full time or part time. |
| trained | Whether they've completed the required initial training. |
| notes | Things to remember about shifts, availability or training. |

## Menus

The seasonal menus used by the shops.

| Column | What it means |
| --- | --- |
| menu_id | Our reference for that menu. |
| shop_id | The shop using it. |
| name | The menu's name, usually the season and year. |
| from | The first day the menu is available. |
| to | The last day it's available. |
| service | Where or when it's offered, e.g. at the counter or all day. |

## Menu items

The food and drinks offered on each menu. A flat white can appear on several menus, so you'll see some of the same things more than once.

| Column | What it means |
| --- | --- |
| item_id | Our reference for the item on that menu. |
| menu_id | The menu it appears on. |
| name | What the food or drink is called. |
| group | The section it goes under, e.g. Coffee or Bakery. |
| size | The serving size, or whether it's sold by the slice, pot, etc. |
| price | What the customer pays for one serving, including VAT where applicable. |
| cost | Roughly what one serving costs us in ingredients or to buy in, before any VAT we can claim back. Doesn't include staff time or running the shop. |
| vegan | Whether it's intended to be suitable for vegans. |
| notes | Extra details about the item, supplier or availability. |

## Monthly accounts

One return per shop per month, with the main takings and running costs.

| Column | What it means |
| --- | --- |
| account_id | Our reference for the monthly return. |
| shop_id | The shop the figures are for. |
| period | The month being reported. We use the first of the month as the date. |
| sales | Sales for the whole month, with VAT taken off. |
| cost | What the food, drinks and ingredients sold that month cost us. |
| pay | Total staffing costs for the month, including the employer's costs on top of wages. |
| rent | The shop's rent for the month. |
| other | Other running costs for the month, separate from stock, staffing and rent. |
| txns | Number of customer purchases put through the till. One purchase can include several items. |
| status | How far we've got with checking or finalising the return. |
| notes | Anything useful to know about that month's figures, such as a repair bill or a supplier credit we're waiting for. |
